/* ==========================================================================
   HPQMS Public Patient Display Board
   js/websocket.js — WebSocket Transport Layer
   ========================================================================== */

import { getConfig } from "./config.js";


/* ==========================================================================
   Constants
   ========================================================================== */

const SOCKET_STATE = Object.freeze({
    DISCONNECTED: "DISCONNECTED",
    CONNECTING: "CONNECTING",
    CONNECTED: "CONNECTED",
    RECONNECTING: "RECONNECTING",
});


/* ==========================================================================
   Internal State
   ========================================================================== */

let socket = null;

let state = SOCKET_STATE.DISCONNECTED;

let reconnectTimer = null;

let reconnectAttempts = 0;

let manuallyDisconnected = false;

const listeners = new Map();


/* ==========================================================================
   Event Management
   ========================================================================== */

/**
 * Register a listener for a WebSocket lifecycle event.
 *
 * Supported events:
 *
 * connected
 * message
 * disconnected
 * error
 * reconnecting
 */
function on(eventName, callback) {
    if (typeof callback !== "function") {
        throw new TypeError(
            "WebSocket listener must be a function"
        );
    }

    if (!listeners.has(eventName)) {
        listeners.set(eventName, new Set());
    }

    listeners.get(eventName).add(callback);

    return () => off(eventName, callback);
}


/**
 * Remove a previously registered listener.
 */
function off(eventName, callback) {
    const callbacks = listeners.get(eventName);

    if (!callbacks) {
        return;
    }

    callbacks.delete(callback);

    if (callbacks.size === 0) {
        listeners.delete(eventName);
    }
}


/**
 * Notify listeners.
 *
 * One failing listener must not prevent other listeners
 * from receiving the event.
 */
function emit(eventName, payload) {
    const callbacks = listeners.get(eventName);

    if (!callbacks) {
        return;
    }

    for (const callback of [...callbacks]) {
        try {
            callback(payload);
        } catch (error) {
            console.error(
                `WebSocket ${eventName} listener failed:`,
                error
            );
        }
    }
}


/* ==========================================================================
   State
   ========================================================================== */

/**
 * Update the internal transport state.
 */
function setState(nextState) {
    state = nextState;
}


/**
 * Return the current transport state.
 */
function getConnectionState() {
    return state;
}


/**
 * Return whether the socket is currently connected.
 */
function isConnected() {
    return (
        socket !== null &&
        socket.readyState === WebSocket.OPEN
    );
}


/* ==========================================================================
   Configuration
   ========================================================================== */

/**
 * Retrieve the current WebSocket configuration.
 */
function getWebSocketConfig() {
    const config = getConfig();

    return {
        url: config.backend.websocketUrl,
        connectionTimeoutMs:
            config.backend.connectionTimeoutMs,

        initialDelayMs:
            config.reconnect.initialDelayMs,

        maxDelayMs:
            config.reconnect.maxDelayMs,

        backoffMultiplier:
            config.reconnect.backoffMultiplier,

        maxAttempts:
            config.reconnect.maxAttempts,
    };
}


/* ==========================================================================
   Reconnection
   ========================================================================== */

/**
 * Calculate the next exponential backoff delay.
 */
function calculateReconnectDelay(attempt) {
    const config = getWebSocketConfig();

    const delay =
        config.initialDelayMs *
        Math.pow(
            config.backoffMultiplier,
            Math.max(0, attempt - 1)
        );

    return Math.min(
        delay,
        config.maxDelayMs
    );
}


/**
 * Determine whether another reconnect attempt is allowed.
 */
function canReconnect() {
    const config = getWebSocketConfig();

    return (
        config.maxAttempts === Infinity ||
        reconnectAttempts < config.maxAttempts
    );
}


/**
 * Schedule a reconnect attempt.
 */
function scheduleReconnect() {
    if (manuallyDisconnected) {
        return;
    }

    if (!canReconnect()) {
        setState(SOCKET_STATE.DISCONNECTED);

        return;
    }

    reconnectAttempts += 1;

    const delay =
        calculateReconnectDelay(reconnectAttempts);

    setState(SOCKET_STATE.RECONNECTING);

    emit("reconnecting", {
        attempt: reconnectAttempts,
        delayMs: delay,
    });

    clearReconnectTimer();

    reconnectTimer = setTimeout(() => {
        reconnectTimer = null;

        connectInternal();
    }, delay);
}


/**
 * Cancel a pending reconnect timer.
 */
function clearReconnectTimer() {
    if (reconnectTimer !== null) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }
}


/* ==========================================================================
   Connection
   ========================================================================== */

/**
 * Establish the WebSocket connection.
 *
 * Public entry point.
 */
function connect() {
    manuallyDisconnected = false;

    if (
        socket &&
        (
            socket.readyState === WebSocket.OPEN ||
            socket.readyState === WebSocket.CONNECTING
        )
    ) {
        return;
    }

    reconnectAttempts = 0;

    connectInternal();
}


/**
 * Internal connection implementation.
 */
function connectInternal() {
    if (manuallyDisconnected) {
        return;
    }

    const config = getWebSocketConfig();

    clearReconnectTimer();

    setState(SOCKET_STATE.CONNECTING);

    let connectionTimer = null;

    try {
        socket = new WebSocket(config.url);
    } catch (error) {
        socket = null;

        setState(SOCKET_STATE.DISCONNECTED);

        emit("error", error);

        scheduleReconnect();

        return;
    }

    connectionTimer = setTimeout(() => {
        if (
            socket &&
            socket.readyState === WebSocket.CONNECTING
        ) {
            socket.close();

            emit(
                "error",
                new Error(
                    "WebSocket connection timed out"
                )
            );
        }
    }, config.connectionTimeoutMs);


    /* ----------------------------------------------------------------------
       Open
       ---------------------------------------------------------------------- */

    socket.onopen = () => {
        if (connectionTimer !== null) {
            clearTimeout(connectionTimer);
            connectionTimer = null;
        }

        reconnectAttempts = 0;

        setState(SOCKET_STATE.CONNECTED);

        emit("connected");
    };


    /* ----------------------------------------------------------------------
       Message
       ---------------------------------------------------------------------- */

    socket.onmessage = (event) => {
    let payload;

    try {
        payload = JSON.parse(event.data);
    } catch (error) {
        console.error(
            "Failed to parse WebSocket message:",
            error
        );

        emit("error", error);

        return;
    }

    emit("message", payload);
};


    /* ----------------------------------------------------------------------
       Error
       ---------------------------------------------------------------------- */

    socket.onerror = (event) => {
        emit("error", event);
    };


    /* ----------------------------------------------------------------------
       Close
       ---------------------------------------------------------------------- */

    socket.onclose = (event) => {
        if (connectionTimer !== null) {
            clearTimeout(connectionTimer);
            connectionTimer = null;
        }

        socket = null;

        setState(SOCKET_STATE.DISCONNECTED);

        emit("disconnected", {
            code: event.code,
            reason: event.reason,
            wasClean: event.wasClean,
        });

        scheduleReconnect();
    };
}


/* ==========================================================================
   Sending
   ========================================================================== */

/**
 * Send a message through the active WebSocket.
 *
 * Strings are sent directly.
 * Objects are serialized as JSON.
 */
function send(message) {
    if (!isConnected()) {
        throw new Error(
            "Cannot send message: WebSocket is not connected"
        );
    }

    const payload =
        typeof message === "string"
            ? message
            : JSON.stringify(message);

    socket.send(payload);
}


/* ==========================================================================
   Disconnect
   ========================================================================== */

/**
 * Permanently disconnect the transport until connect()
 * is explicitly called again.
 */
function disconnect() {
    manuallyDisconnected = true;

    clearReconnectTimer();

    reconnectAttempts = 0;

    if (!socket) {
        setState(SOCKET_STATE.DISCONNECTED);

        return;
    }

    const currentSocket = socket;

    socket = null;

    setState(SOCKET_STATE.DISCONNECTED);

    currentSocket.close();
}


/* ==========================================================================
   Testing / Diagnostics
   ========================================================================== */

/**
 * Return a snapshot of transport state.
 *
 * This does not expose the actual WebSocket instance.
 */
function getTransportInfo() {
    return {
        state,
        connected: isConnected(),
        reconnectAttempts,
        reconnectScheduled: reconnectTimer !== null,
    };
}


/* ==========================================================================
   Public API
   ========================================================================== */

export {
    SOCKET_STATE,

    connect,
    disconnect,

    send,

    on,
    off,

    isConnected,
    getConnectionState,

    getTransportInfo,
};