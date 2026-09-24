/* ==========================================================================
   HPQMS Admin Dashboard
   js/admin-websocket.js — Admin live-update WebSocket transport
   ==========================================================================

   Connects to the authenticated /ws/admin channel (JWT passed as a query
   parameter) and re-emits `ADMIN_OVERVIEW_CHANGED` pings to listeners.
   Handles reconnects with exponential backoff; consumers fall back to
   interval polling while the socket is down.
   ========================================================================== */

import { getConfig } from "./config.js";
import { getAccessToken } from "./staff-session.js";

const STATE = Object.freeze({
    DISCONNECTED: "DISCONNECTED",
    CONNECTING: "CONNECTING",
    CONNECTED: "CONNECTED",
    RECONNECTING: "RECONNECTING",
});

const MAX_ATTEMPTS_TRACKED = 6;

let socket = null;
let state = STATE.DISCONNECTED;
let reconnectTimer = null;
let reconnectAttempts = 0;
let manuallyDisconnected = false;
const listeners = new Map();

function on(eventName, callback) {
    if (typeof callback !== "function") throw new TypeError("listener must be a function");
    if (!listeners.has(eventName)) listeners.set(eventName, new Set());
    listeners.get(eventName).add(callback);
    return () => off(eventName, callback);
}

function off(eventName, callback) {
    const callbacks = listeners.get(eventName);
    if (!callbacks) return;
    callbacks.delete(callback);
    if (callbacks.size === 0) listeners.delete(eventName);
}

function emit(eventName, payload) {
    for (const callback of [...(listeners.get(eventName) || [])]) {
        try { callback(payload); } catch (error) { console.error(`Admin WebSocket ${eventName} listener failed:`, error); }
    }
}

function setState(next) { state = next; }

function isConnected() { return socket !== null && socket.readyState === WebSocket.OPEN; }

function getConnectionState() { return state; }

function clearReconnectTimer() {
    if (reconnectTimer !== null) { clearTimeout(reconnectTimer); reconnectTimer = null; }
}

function scheduleReconnect() {
    if (manuallyDisconnected) return;
    reconnectAttempts += 1;
    const delay = Math.min(1000 * 2 ** Math.max(0, reconnectAttempts - 1), 30_000);
    setState(STATE.RECONNECTING);
    emit("reconnecting", { attempt: reconnectAttempts, delayMs: delay });
    clearReconnectTimer();
    reconnectTimer = setTimeout(() => { reconnectTimer = null; connectInternal(); }, delay);
}

function buildUrl() {
    const url = getConfig().backend.adminWebsocketUrl;
    const token = getAccessToken();
    if (!token) throw new Error("No access token for the admin live-update channel.");
    return `${url}?token=${encodeURIComponent(token)}`;
}

function connect() {
    manuallyDisconnected = false;
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) return;
    reconnectAttempts = 0;
    connectInternal();
}

function connectInternal() {
    if (manuallyDisconnected) return;
    clearReconnectTimer();

    let url;
    try { url = buildUrl(); } catch (error) {
        setState(STATE.DISCONNECTED);
        emit("error", error);
        return;
    }

    setState(STATE.CONNECTING);

    try { socket = new WebSocket(url); } catch (error) {
        socket = null;
        setState(STATE.DISCONNECTED);
        emit("error", error);
        scheduleReconnect();
        return;
    }

    socket.onopen = () => {
        reconnectAttempts = 0;
        setState(STATE.CONNECTED);
        emit("connected");
    };

    socket.onmessage = (event) => {
        let payload;
        try { payload = JSON.parse(event.data); } catch (error) {
            console.error("Failed to parse admin WebSocket message:", error);
            emit("error", error);
            return;
        }
        if (payload?.event_type === "ADMIN_OVERVIEW_CHANGED") emit("overview-changed", payload);
        emit("message", payload);
    };

    socket.onerror = (event) => emit("error", event);

    socket.onclose = (event) => {
        socket = null;
        setState(STATE.DISCONNECTED);
        emit("disconnected", { code: event.code, reason: event.reason, wasClean: event.wasClean });
        scheduleReconnect();
    };
}

function disconnect() {
    manuallyDisconnected = true;
    clearReconnectTimer();
    reconnectAttempts = 0;
    if (!socket) { setState(STATE.DISCONNECTED); return; }
    const current = socket;
    socket = null;
    setState(STATE.DISCONNECTED);
    current.close();
}

export {
    STATE as ADMIN_SOCKET_STATE,
    connect,
    disconnect,
    on,
    off,
    isConnected,
    getConnectionState,
};
