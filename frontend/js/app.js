/* ==========================================================================
   HPQMS Public Patient Display Board
   js/app.js — Application Orchestrator
   ========================================================================== */

import {
    getConfig,
} from "./config.js";

import {
    connect as connectWebSocket,
    disconnect as disconnectWebSocket,
    on as onWebSocket,
    off as offWebSocket,
    getConnectionState,
    SOCKET_STATE,
} from "./websocket.js";

import {
    getDisplaySnapshot,
} from "./api.js";

import {
    getState,
    setSnapshot,
    applyEvent,
    setConnectionStatus,
    subscribe as subscribeDisplayState,
} from "./display-state.js";


/* ==========================================================================
   Internal State
   ========================================================================== */

let started = false;

let starting = false;

let syncing = false;

let unsubscribeDisplayState = null;

const websocketSubscriptions = [];


/* ==========================================================================
   Application State
   ========================================================================== */

/**
 * Return high-level application state.
 *
 * This intentionally combines application lifecycle information
 * with the underlying display state without exposing mutable
 * internals.
 */
function getAppState() {
    return {
        started,
        starting,
        syncing,
        connectionState: getConnectionState(),
        displayState: getState(),
    };
}


/* ==========================================================================
   Snapshot Synchronization
   ========================================================================== */

/**
 * Retrieve the authoritative display snapshot from the backend
 * and replace the current display state.
 *
 * This is used:
 *
 * 1. During initial application startup.
 * 2. After a successful WebSocket reconnection.
 *
 * Events are never replayed to recover missed state.
 */
async function syncSnapshot() {
    if (syncing) {
        return getState();
    }

    syncing = true;

    try {
        const snapshot =
            await getDisplaySnapshot();

        setSnapshot(snapshot);

        return getState();
    } finally {
        syncing = false;
    }
}


/* ==========================================================================
   WebSocket Event Handlers
   ========================================================================== */

/**
 * Handle successful WebSocket connection.
 *
 * Every successful connection performs an authoritative
 * snapshot synchronization.
 */
async function handleConnected() {
    setConnectionStatus("CONNECTED");

    try {
        await syncSnapshot();
    } catch (error) {
        handleError(error);
    }
}


/**
 * Handle incoming WebSocket data.
 *
 * websocket.js deliberately does not interpret messages.
 * app.js is responsible for parsing the transport payload
 * and passing the resulting event into the state layer.
 */
function handleMessage(rawMessage) {
    let event;

    try {
        if (typeof rawMessage === "string") {
            event = JSON.parse(rawMessage);
        } else {
            event = rawMessage;
        }
    } catch (error) {
        handleError(
            new Error(
                "Received invalid WebSocket JSON",
                {
                    cause: error,
                }
            )
        );

        return;
    }

    try {
        applyEvent(event);
    } catch (error) {
        handleError(error);
    }
}


/**
 * Handle WebSocket disconnection.
 */
function handleDisconnected(details) {
    setConnectionStatus(
        "DISCONNECTED",
        details?.reason ?? null
    );
}


/**
 * Handle WebSocket reconnection attempt.
 *
 * We only record the transport state here.
 * websocket.js owns the actual reconnection algorithm.
 */
function handleReconnecting(details) {
    setConnectionStatus(
        "RECONNECTING",
        null
    );

    return details;
}


/**
 * Handle WebSocket errors.
 *
 * The transport module owns recovery behavior.
 * app.js only records the failure and lets the transport
 * layer determine whether reconnection should occur.
 */
function handleError(error) {
    console.error(
        "HPQMS display application error:",
        error
    );
}


/* ==========================================================================
   Subscription Management
   ========================================================================== */

/**
 * Register all WebSocket listeners used by the application.
 */
function registerWebSocketListeners() {
    const subscriptions = [
        [
            "connected",
            handleConnected,
        ],

        [
            "message",
            handleMessage,
        ],

        [
            "disconnected",
            handleDisconnected,
        ],

        [
            "reconnecting",
            handleReconnecting,
        ],

        [
            "error",
            handleError,
        ],
    ];

    for (const [eventName, callback] of subscriptions) {
        onWebSocket(eventName, callback);

        websocketSubscriptions.push({
            eventName,
            callback,
        });
    }
}


/**
 * Remove all WebSocket listeners registered by this application.
 */
function unregisterWebSocketListeners() {
    for (const {
        eventName,
        callback,
    } of websocketSubscriptions) {
        offWebSocket(
            eventName,
            callback
        );
    }

    websocketSubscriptions.length = 0;
}


/**
 * Subscribe to display-state changes.
 *
 * This creates the bridge future renderers/managers can use.
 *
 * app.js itself does not manipulate the DOM.
 */
function registerDisplayStateSubscription() {
    unsubscribeDisplayState =
        subscribeDisplayState(() => {
            /*
             * Intentionally empty for now.
             *
             * Future application managers/renderers can
             * subscribe directly to display-state.js or
             * be orchestrated here.
             */
        });
}


/**
 * Remove the application display-state subscription.
 */
function unregisterDisplayStateSubscription() {
    if (unsubscribeDisplayState) {
        unsubscribeDisplayState();

        unsubscribeDisplayState = null;
    }
}


/* ==========================================================================
   Application Lifecycle
   ========================================================================== */

/**
 * Start the display application.
 *
 * Startup sequence:
 *
 *     register listeners
 *             ↓
 *     synchronize snapshot
 *             ↓
 *     connect WebSocket
 */
async function start() {
    if (started || starting) {
        return getAppState();
    }

    starting = true;

    try {
        /*
         * Read configuration before starting.
         *
         * This also ensures configuration has been
         * initialized before dependent modules operate.
         */
        getConfig();

        registerWebSocketListeners();

        registerDisplayStateSubscription();

        /*
         * Get authoritative state before opening the
         * live event stream.
         */
        try {
            await syncSnapshot();
        } catch (error) {
            handleError(error);
        }

        started = true;

        connectWebSocket();

        return getAppState();
    } catch (error) {
        /*
         * If startup itself fails, clean up any
         * partially registered resources.
         */
        unregisterWebSocketListeners();
        unregisterDisplayStateSubscription();

        throw error;
    } finally {
        starting = false;
    }
}


/**
 * Stop the display application.
 *
 * Shutdown is intentionally idempotent.
 */
function stop() {
    if (!started && !starting) {
        return;
    }

    disconnectWebSocket();

    unregisterWebSocketListeners();

    unregisterDisplayStateSubscription();

    started = false;

    starting = false;

    syncing = false;
}


/* ==========================================================================
   Public API
   ========================================================================== */

export {
    start,
    stop,

    syncSnapshot,

    getAppState,

    handleMessage,
    handleConnected,
    handleDisconnected,
    handleReconnecting,
    handleError,
};