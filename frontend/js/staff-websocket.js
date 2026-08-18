/* ==========================================================================
   HPQMS Staff Dashboard
   js/staff-websocket.js — Staff WebSocket Transport Layer
   ========================================================================== */

import { getConfig } from "./config.js";


/* ==========================================================================
   Constants
   ========================================================================== */

const STAFF_SOCKET_STATE = Object.freeze({
    DISCONNECTED: "DISCONNECTED",
    CONNECTING: "CONNECTING",
    CONNECTED: "CONNECTED",
    RECONNECTING: "RECONNECTING",
});


/* ==========================================================================
   Internal State
   ========================================================================== */

let socket = null;

let state = STAFF_SOCKET_STATE.DISCONNECTED;

let reconnectTimer = null;

let reconnectAttempts = 0;

let manuallyDisconnected = false;

const listeners = new Map();


/* ==========================================================================
   Event Management
   ========================================================================== */

function on(eventName, callback) {
    if (typeof callback !== "function") {
        throw new TypeError(
            "Staff WebSocket listener must be a function"
        );
    }

    if (!listeners.has(eventName)) {
        listeners.set(eventName, new Set());
    }

    listeners.get(eventName).add(callback);

    return () => off(eventName, callback);
}


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
                `Staff WebSocket ${eventName} listener failed:`,
                error
            );
        }
    }
}


/* ==========================================================================
   State
   ========================================================================== */

function setState(nextState) {
    state = nextState;
}


function getConnectionState() {
    return state;
}


function isConnected() {
    return (
        socket !== null &&
        socket.readyState === WebSocket.OPEN
    );
}


/* ==========================================================================
   Configuration
   ========================================================================== */

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


function canReconnect() {
    const config = getWebSocketConfig();

    return (
        config.maxAttempts === Infinity ||
        reconnectAttempts < config.maxAttempts
    );
}


function clearReconnectTimer() {
    if (reconnectTimer !== null) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }
}


function scheduleReconnect() {
    if (manuallyDisconnected) {
        return;
    }

    if (!canReconnect()) {
        setState(STAFF_SOCKET_STATE.DISCONNECTED);
        return;
    }

    reconnectAttempts += 1;

    const delay =
        calculateReconnectDelay(reconnectAttempts);

    setState(STAFF_SOCKET_STATE.RECONNECTING);

    emit("reconnecting", {
        attempt: reconnectAttempts,
        delayMs: delay,
    });

    clearReconnectTimer();

    reconnectTimer = setTimeout(() => {
        reconnectTimer = null;

        if (!canReconnect()) {
            setState(STAFF_SOCKET_STATE.DISCONNECTED);
            return;
        }

        connectInternal();
    }, delay);
}

/* ==========================================================================
   Connection
   ========================================================================== */

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


function connectInternal() {
    if (manuallyDisconnected) {
        return;
    }

    const config = getWebSocketConfig();

    clearReconnectTimer();

    setState(STAFF_SOCKET_STATE.CONNECTING);

    let connectionTimer = null;

    try {
        socket = new WebSocket(config.url);
    } catch (error) {
        socket = null;

        setState(STAFF_SOCKET_STATE.DISCONNECTED);

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
                    "Staff WebSocket connection timed out"
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

        setState(STAFF_SOCKET_STATE.CONNECTED);

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
                "Failed to parse staff WebSocket message:",
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

        setState(STAFF_SOCKET_STATE.DISCONNECTED);

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

function send(message) {
    if (!isConnected()) {
        throw new Error(
            "Cannot send message: Staff WebSocket is not connected"
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

function disconnect() {
    manuallyDisconnected = true;

    clearReconnectTimer();

    reconnectAttempts = 0;

    if (!socket) {
        setState(STAFF_SOCKET_STATE.DISCONNECTED);
        return;
    }

    const currentSocket = socket;

    socket = null;

    setState(STAFF_SOCKET_STATE.DISCONNECTED);

    currentSocket.close();
}


/* ==========================================================================
   Diagnostics
   ========================================================================== */

function getTransportInfo() {
    return {
        state,
        connected: isConnected(),
        reconnectAttempts,
        reconnectScheduled:
            reconnectTimer !== null,
    };
}


/* ==========================================================================
   Public API
   ========================================================================== */

export {
    STAFF_SOCKET_STATE,

    connect,
    disconnect,

    send,

    on,
    off,

    isConnected,
    getConnectionState,

    getTransportInfo,
};