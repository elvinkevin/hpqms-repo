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
    initializeRenderer,
    renderSnapshot,
    renderDepartments,
    renderConnectionStatus,
    clearRenderer,
    showLoader,
} from "./renderer.js";

import {
    initialize as initializeRotation,
    setDepartments,
    getCurrentDepartment,
    startRotation,
    stopRotation,
    focusDepartment,
    reset as resetRotation,
} from "./rotation-manager.js";

import {
    initializeIdleManager,
    resetIdleTimer,
    destroyIdleManager,
} from "./idle-manager.js";

import {
    initialize as initializeAlerts,
    setCallbacks as setAlertCallbacks,
    handleEvent as handleAlertEvent,
    reset as resetAlerts,
} from "./alert-manager.js";

import {
    initialize as initializeAudio,
    playTokenChime,
    reset as resetAudio,
    isUnlocked,
    unlockAudio,
} from "./audio-player.js";

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

let hasConnectedBefore = false;

let unsubscribeDisplayState = null;

const websocketSubscriptions = [];

let managersInitialized = false;

let latestNotificationEvent = null;

let clockIntervalId = null;

/*
 * Departments shown per rotation page on the ROTATING_BOARD
 * layout. Matches the default 2x2 CSS grid capacity; with
 * fewer departments on a page the board rotates within the
 * same set, with more it advances page by page.
 */
const BOARD_PAGE_SIZE = 4;


/* ==========================================================================
   DOM Helpers
   ========================================================================== */

function getElementById(id) {
    const element = document.getElementById(id);

    if (!element) {
        throw new Error(
            `Required display element #${id} was not found.`
        );
    }

    return element;
}


function setText(id, value) {
    getElementById(id).textContent =
        value ?? "";
}


/**
 * Apply the configured presentation strategy before the renderer creates
 * viewport content. Layout CSS is intentionally selected through this DOM
 * attribute so display configuration stays separate from markup.
 */
function applyLayoutMode(config) {
    document.body.dataset.layout =
        config.layout?.mode ?? "SINGLE_DEPARTMENT";
}


function updateClock() {
    const clock = document.getElementById("clock");

    if (!clock) {
        return;
    }

    const now = new Date();

    clock.dateTime = now.toISOString();
    clock.textContent = new Intl.DateTimeFormat(
        "en-KE",
        {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
            hour12: false,
        }
    ).format(now);
}


function startClock() {
    updateClock();

    if (clockIntervalId === null) {
        clockIntervalId = window.setInterval(updateClock, 1000);
    }
}


function stopClock() {
    if (clockIntervalId !== null) {
        window.clearInterval(clockIntervalId);
        clockIntervalId = null;
    }
}


function normalizeConnectionStatus(status) {
    switch (status) {
        case "CONNECTED":
        case "CONNECTING":
        case "DISCONNECTED":
            return status;

        case "RECONNECTING":
            return "CONNECTING";

        case "ERROR":
            return "DISCONNECTED";

        default:
            return "DISCONNECTED";
    }
}


/**
 * Narrow the snapshot departments down to the ones this screen is
 * pinned to via config.departments.selected (matching is done
 * case-insensitively on department_name).
 */
function filterSelectedDepartments(departments, config) {
    const selected = config.departments?.selected;

    if (!Array.isArray(selected) || selected.length === 0) {
        return departments;
    }

    const wanted = selected
        .map(name => String(name).trim().toLowerCase())
        .filter(name => name !== "");

    if (wanted.length === 0) {
        return departments;
    }

    const matches = departments.filter(department =>
        wanted.includes(
            String(department?.department_name ?? "")
                .trim()
                .toLowerCase()
        )
    );

    /*
     * Fall back to the full list when nothing matches —
     * a misconfigured screen must not go blank.
     */
    return matches.length > 0 ? matches : departments;
}


function getRenderableDepartments(snapshot) {
    const departments =
        Array.isArray(snapshot?.departments)
            ? snapshot.departments
            : [];

    const config = getConfig();

    const filtered =
        filterSelectedDepartments(departments, config);

    /*
     * SINGLE_DEPARTMENT always shows exactly one fixed
     * department, regardless of rotation settings.
     */
    if (config.layout?.mode === "SINGLE_DEPARTMENT") {
        return filtered.slice(0, 1);
    }

    if (
        config.layout?.mode === "ROTATING_BOARD" &&
        config.rotation.enabled &&
        departments.length > 1
    ) {
        /*
         * Show one department at a time; the grid arrangement
         * is reserved for the ATRIUM layout.
         */
        const currentDepartment =
            getCurrentDepartment();

        return currentDepartment
            ? [currentDepartment]
            : filtered.slice(0, 1);
    }

    return filtered;
}


function renderDisplayState(state = getState()) {
    const snapshot =
        state.snapshot ?? {};

    const departments =
        Array.isArray(snapshot.departments)
            ? snapshot.departments
            : [];

    const config = getConfig();

    const filteredDepartments =
        filterSelectedDepartments(departments, config);

    setDepartments(filteredDepartments);

    /*
     * Rotation only applies to the ROTATING_BOARD layout —
     * other layouts are fixed views.
     */
    if (
        config.layout?.mode === "ROTATING_BOARD" &&
        config.rotation.enabled &&
        departments.length > 1
    ) {
        startRotation();
    } else {
        stopRotation();
    }

    renderSnapshot({
        ...snapshot,
        departments:
            getRenderableDepartments(snapshot),
    });

    renderConnectionStatus(
        normalizeConnectionStatus(
            state.connection?.status
        )
    );

    resetIdleTimer();
}


function renderCurrentDepartment() {
    const state = getState();

    renderDepartments(
        getRenderableDepartments(state.snapshot)
    );
}


function showAlert(alert) {
    const layer =
        getElementById("alert-layer");

    const card =
        getElementById("alert-card");

    const alertType =
        alert.priority === "CRITICAL"
            ? "CRITICAL"
            : "CALLED";

    card.dataset.alertType =
        alertType;

    setText(
        "alert-badge",
        alertType === "CRITICAL"
            ? "PRIORITY ALERT"
            : "NOW SERVING"
    );

    setText(
        "alert-department",
        alert.department_name ?? ""
    );

    setText(
        "alert-token",
        alert.token_number ?? "TOKEN"
    );

    setText(
        "alert-service-point",
        alert.service_point ?? "SERVICE DESK"
    );

    setText(
        "alert-instruction",
        alert.message ??
        "Please proceed to the assigned service point."
    );

    layer.hidden = false;
    layer.setAttribute("aria-hidden", "false");
}


function dismissAlert() {
    const layer =
        document.getElementById("alert-layer");

    if (!layer) {
        return;
    }

    layer.hidden = true;
    layer.setAttribute("aria-hidden", "true");
}


function playAlertSound(alert) {
    void playTokenChime(alert);
}


/**
 * Show or hide the one-tap audio unlock overlay.
 *
 * The overlay blocks the display until the browser's autoplay
 * policy is satisfied. It is shown when audio is enabled but the
 * AudioContext is still suspended, and hidden once unlocked.
 */
function syncAudioUnlockOverlay() {
    const overlay =
        document.getElementById(
            "audio-unlock-layer"
        );

    if (!overlay) {
        return;
    }

    const config = getConfig();
    const audioEnabled =
        config.features.audio &&
        config.alerts.audioEnabled;

    if (!audioEnabled) {
        overlay.hidden = true;
        return;
    }

    if (isUnlocked()) {
        overlay.hidden = true;
        return;
    }

    overlay.hidden = false;
}


/**
 * Attach listeners that unlock audio and dismiss the overlay.
 */
function attachAudioUnlockHandlers() {
    const overlay =
        document.getElementById(
            "audio-unlock-layer"
        );

    if (!overlay) {
        return;
    }

    const button =
        document.getElementById(
            "audio-unlock-button"
        );

    const unlockAndHide = () => {
        unlockAudio().then(() => {
            syncAudioUnlockOverlay();
        });
    };

    if (button) {
        button.addEventListener(
            "click",
            unlockAndHide
        );
    }

    overlay.addEventListener(
        "click",
        unlockAndHide
    );

    overlay.addEventListener(
        "keydown",
        (event) => {
            if (
                event.key === "Enter" ||
                event.key === " "
            ) {
                event.preventDefault();
                unlockAndHide();
            }
        }
    );
}


function maybeFocusDepartment(event) {
    if (!event?.dept_id) {
        return;
    }

    if (
        event.event_type === "TOKEN_CALLED" ||
        event.priority === "HIGH" ||
        event.priority === "CRITICAL"
    ) {
        const focused =
            focusDepartment(event.dept_id);

        if (focused) {
            renderCurrentDepartment();
        }
    }
}


function initializeRuntimeManagers() {
    if (managersInitialized) {
        return;
    }

    const config = getConfig();

    initializeRenderer();
    showLoader();

    initializeRotation({
        rotationIntervalMs:
            config.rotation.intervalMs,
        onDepartmentChange:
            renderCurrentDepartment,
    });

    if (config.idle.enabled) {
        initializeIdleManager({
            idleTimeoutMs:
                config.idle.timeoutMs,
        });
    }

    initializeAlerts({
        defaultDurationMs:
            config.alerts.defaultDurationMs,
    });

    initializeAudio({
        enabled: config.features.audio &&
            config.alerts.audioEnabled,
        chimeVolume: config.alerts.chimeVolume,
        speakTokenNumber: config.alerts.speakTokenNumber,
        speechRate: config.alerts.speechRate,
        speechPitch: config.alerts.speechPitch,
        speechVolume: config.alerts.speechVolume,
        criticalChime: config.alerts.criticalChime,
    });

    setAlertCallbacks({
        show: showAlert,
        dismiss: dismissAlert,
        playSound:
            config.alerts.audioEnabled &&
                config.features.audio
                ? playAlertSound
                : null,
    });

    managersInitialized = true;
}


function resetRuntimeManagers() {
    if (!managersInitialized) {
        return;
    }

    destroyIdleManager();
    resetRotation();
    resetAlerts();
    resetAudio();
    clearRenderer();
    dismissAlert();

    managersInitialized = false;
}


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
    console.warn(
        "[DEBUG syncSnapshot] syncing =",
        syncing
    );

    if (syncing) {
        console.warn(
            "[DEBUG syncSnapshot] ALREADY SYNCING"
        );

        return getState();
    }

    syncing = true;

    console.warn(
        "[DEBUG syncSnapshot] STARTING API REQUEST"
    );

    try {
        const snapshot =
            await getDisplaySnapshot();

        setSnapshot(snapshot);

        return getState();
    } finally {
        syncing = false;

        console.warn(
            "[DEBUG syncSnapshot] FINISHED"
        );
    }
}


/**
 * Handle successful WebSocket connection.
 *
 * The initial application startup already performs an
 * authoritative snapshot synchronization.
 *
 * Subsequent successful connections are treated as
 * reconnections and therefore require snapshot recovery.
 */
async function handleConnected() {
    setConnectionStatus("CONNECTED");

    if (!hasConnectedBefore) {
        hasConnectedBefore = true;
        return;
    }

    try {
        await syncSnapshot();
    } catch (error) {
        handleError(error);
    }
}


/**
 * Handle incoming WebSocket data.
 *
 * websocket.js is responsible for transport and JSON parsing.
 * app.js orchestrates the parsed event between the application
 * managers and the display-state layer.
 *
 * Normal state-changing events are applied locally immediately.
 *
 * Events that alter the ordered waiting-token projection are reconciled
 * from the authoritative snapshot. A WebSocket event identifies the token
 * that changed, but cannot contain the newly promoted token beyond the
 * display's current next-token window.
 */
const QUEUE_PROJECTION_EVENTS = new Set([
    "TOKEN_CALLED",
    "TOKEN_REQUEUED",
    "QUEUE_UPDATED",
]);

function handleMessage(event) {
    console.warn("[WS EVENT RECEIVED]", event);

    if (typeof event === "string") {
        try {
            event = JSON.parse(event);
        } catch (error) {
            handleError(
                new Error(
                    "Received invalid WebSocket JSON",
                    { cause: error }
                )
            );
            return;
        }
    }

    if (!event || typeof event !== "object") {
        handleError(
            new Error(
                "Received invalid WebSocket event payload"
            )
        );
        return;
    }

    console.warn(
        "[WS EVENT PARSED]",
        event.event_type,
        event
    );

    try {
        latestNotificationEvent = event;

        /*
         * Alerts and department focus are application-level
         * concerns and should receive the event regardless of
         * whether it changes display state.
         */
        handleAlertEvent(event);

        maybeFocusDepartment(event);

        /*
         * CONNECTION_ESTABLISHED is handled by handleConnected().
         *
         * It is not a normal display-state mutation and should
         * not be passed to display-state.applyEvent().
         */
        if (event.event_type === "CONNECTION_ESTABLISHED") {
            return;
        }

        /*
         * Normal WebSocket events mutate the local display state immediately.
         */
        applyEvent(event);

        if (QUEUE_PROJECTION_EVENTS.has(event.event_type)) {
            void syncSnapshot().catch(handleError);
        }

    } catch (error) {
        handleError(error);
    } finally {
        latestNotificationEvent = null;
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
        subscribeDisplayState((state) => {
            try {
                renderDisplayState(state);
            } catch (error) {
                handleError(error);
            }
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
        const config = getConfig();

        applyLayoutMode(config);

        startClock();

        initializeRuntimeManagers();

        attachAudioUnlockHandlers();

        syncAudioUnlockOverlay();

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


function stop() {
    if (!started && !starting) {
        return;
    }

    disconnectWebSocket();

    unregisterWebSocketListeners();

    unregisterDisplayStateSubscription();

    resetRuntimeManagers();

    stopClock();

    started = false;

    starting = false;

    syncing = false;

    hasConnectedBefore = false;
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
