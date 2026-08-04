/* ==========================================================================
   HPQMS Public Patient Display
   idle-manager.js — Idle / Standby / Ambient Display Management
   ========================================================================== */

/**
 * Idle Manager
 *
 * Responsibilities:
 * - Monitor display inactivity.
 * - Enter standby mode after the configured idle timeout.
 * - Enter ambient/screensaver mode after the configured ambient timeout.
 * - Wake the display when activity occurs.
 * - Maintain the ambient clock and date.
 *
 * This module deliberately does NOT:
 * - modify display state
 * - manage WebSocket connections
 * - render queue data
 * - play audio
 * - manage alerts
 * - manage rotation
 *
 * app.js remains responsible for orchestration.
 */


/* ==========================================================================
   CONSTANTS
   ========================================================================== */

const IDLE_MODE = Object.freeze({
    NONE: undefined,
    STANDBY: "STANDBY",
    AMBIENT: "AMBIENT",
});


/* ==========================================================================
   INTERNAL STATE
   ========================================================================== */

let initialized = false;

let currentMode = IDLE_MODE.NONE;

let idleTimer = null;
let ambientTimer = null;
let ambientClockTimer = null;

let options = {
    idleTimeoutMs: 5 * 60 * 1000,
    ambientTimeoutMs: 15 * 60 * 1000,
    ambientClockIntervalMs: 1000,
};

let elements = {
    displayShell: null,
    idleLayer: null,
    standbyView: null,
    ambientView: null,
    ambientClock: null,
    ambientDate: null,
};

let activityListenersAttached = false;


/* ==========================================================================
   DOM HELPERS
   ========================================================================== */

/**
 * Resolve all DOM elements required by the idle manager.
 */
function resolveElements(root = document) {
    elements.displayShell =
        root.getElementById("display-shell");

    elements.idleLayer =
        root.getElementById("idle-layer");

    elements.standbyView =
        root.getElementById("standby-view");

    elements.ambientView =
        root.getElementById("ambient-view");

    elements.ambientClock =
        root.getElementById("ambient-clock");

    elements.ambientDate =
        root.getElementById("ambient-date");

    return elements;
}


/**
 * Ensure the required DOM exists.
 */
function hasRequiredElements() {
    return Boolean(
        elements.idleLayer &&
        elements.standbyView &&
        elements.ambientView
    );
}


/* ==========================================================================
   TIMER MANAGEMENT
   ========================================================================== */

function clearIdleTimer() {
    if (idleTimer !== null) {
        clearTimeout(idleTimer);
        idleTimer = null;
    }
}


function clearAmbientTimer() {
    if (ambientTimer !== null) {
        clearTimeout(ambientTimer);
        ambientTimer = null;
    }
}


function clearAmbientClockTimer() {
    if (ambientClockTimer !== null) {
        clearInterval(ambientClockTimer);
        ambientClockTimer = null;
    }
}


/**
 * Clear all internal timers.
 */
function clearTimers() {
    clearIdleTimer();
    clearAmbientTimer();
    clearAmbientClockTimer();
}


/* ==========================================================================
   AMBIENT CLOCK
   ========================================================================== */

/**
 * Update the large ambient clock.
 */
function updateAmbientClock() {
    if (!elements.ambientClock) {
        return;
    }

    const now = new Date();

    elements.ambientClock.textContent =
        now.toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
        });
}


/**
 * Update the ambient date.
 */
function updateAmbientDate() {
    if (!elements.ambientDate) {
        return;
    }

    const now = new Date();

    elements.ambientDate.textContent =
        now.toLocaleDateString([], {
            weekday: "long",
            day: "numeric",
            month: "long",
        });
}


/**
 * Update ambient time/date immediately and schedule future updates.
 */
function startAmbientClock() {
    clearAmbientClockTimer();

    updateAmbientClock();
    updateAmbientDate();

    ambientClockTimer = setInterval(() => {
        updateAmbientClock();
        updateAmbientDate();
    }, options.ambientClockIntervalMs);
}


function stopAmbientClock() {
    clearAmbientClockTimer();
}


/* ==========================================================================
   VIEW MANAGEMENT
   ========================================================================== */

/**
 * Hide the idle layer completely.
 */
function hideIdleLayer() {
    if (!elements.idleLayer) {
        return;
    }

    elements.idleLayer.hidden = true;
    elements.idleLayer.setAttribute("aria-hidden", "true");
}


/**
 * Show the idle layer.
 */
function showIdleLayer() {
    if (!elements.idleLayer) {
        return;
    }

    elements.idleLayer.hidden = false;
    elements.idleLayer.setAttribute("aria-hidden", "false");
}


/**
 * Hide both idle views.
 */
function hideIdleViews() {
    if (elements.standbyView) {
        elements.standbyView.hidden = true;
    }

    if (elements.ambientView) {
        elements.ambientView.hidden = true;
    }
}


/**
 * Display standby mode.
 */
function showStandbyView() {
    hideIdleViews();

    if (elements.standbyView) {
        elements.standbyView.hidden = false;
    }

    showIdleLayer();
    stopAmbientClock();

    currentMode = IDLE_MODE.STANDBY;
}


/**
 * Display ambient/screensaver mode.
 */
function showAmbientView() {
    hideIdleViews();

    if (elements.ambientView) {
        elements.ambientView.hidden = false;
    }

    showIdleLayer();
    startAmbientClock();

    currentMode = IDLE_MODE.AMBIENT;
}


/**
 * Return the display to normal operation.
 */
function hideIdleMode() {
    hideIdleViews();
    hideIdleLayer();
    stopAmbientClock();

    currentMode = IDLE_MODE.NONE;
}


/* ==========================================================================
   IDLE TRANSITIONS
   ========================================================================== */

/**
 * Enter standby mode after inactivity.
 */
function enterStandby() {
    if (!initialized) {
        return false;
    }

    if (currentMode === IDLE_MODE.STANDBY) {
        return false;
    }

    showStandbyView();

    scheduleAmbientMode();

    return true;
}


/**
 * Enter ambient mode.
 */
function enterAmbient() {
    if (!initialized) {
        return false;
    }

    if (currentMode === IDLE_MODE.AMBIENT) {
        return false;
    }

    showAmbientView();

    return true;
}


/**
 * Schedule transition from standby to ambient mode.
 */
function scheduleAmbientMode() {
    clearAmbientTimer();

    ambientTimer = setTimeout(() => {
        ambientTimer = null;
        enterAmbient();
    }, options.ambientTimeoutMs);
}


/* ==========================================================================
   ACTIVITY / WAKE MANAGEMENT
   ========================================================================== */

/**
 * Restart the inactivity countdown.
 */
function scheduleIdleTimeout() {
    clearIdleTimer();

    idleTimer = setTimeout(() => {
        idleTimer = null;
        enterStandby();
    }, options.idleTimeoutMs);
}


/**
 * Wake the display from standby/ambient mode.
 *
 * Activity does not need to be forwarded anywhere else.
 */
function wake() {
    if (!initialized) {
        return false;
    }

    const wasIdle =
        currentMode !== IDLE_MODE.NONE;

    clearTimers();

    hideIdleMode();

    scheduleIdleTimeout();

    return wasIdle;
}


/**
 * Reset the inactivity countdown.
 *
 * Useful when another application event should count
 * as activity even though it wasn't a DOM interaction.
 */
function resetIdleTimer() {
    if (!initialized) {
        return false;
    }

    clearIdleTimer();

    if (currentMode === IDLE_MODE.NONE) {
        scheduleIdleTimeout();
    }

    return true;
}


/* ==========================================================================
   ACTIVITY LISTENERS
   ========================================================================== */

function handleActivity() {
    wake();
}


const ACTIVITY_EVENTS = [
    "mousemove",
    "mousedown",
    "touchstart",
    "keydown",
    "click",
];


function attachActivityListeners() {
    if (activityListenersAttached) {
        return;
    }

    ACTIVITY_EVENTS.forEach((eventName) => {
        document.addEventListener(
            eventName,
            handleActivity,
            { passive: true }
        );
    });

    activityListenersAttached = true;
}


function detachActivityListeners() {
    if (!activityListenersAttached) {
        return;
    }

    ACTIVITY_EVENTS.forEach((eventName) => {
        document.removeEventListener(
            eventName,
            handleActivity
        );
    });

    activityListenersAttached = false;
}


/* ==========================================================================
   INITIALIZATION
   ========================================================================== */

/**
 * Initialize the idle manager.
 *
 * @param {Object} config
 * @param {number} config.idleTimeoutMs
 * @param {number} config.ambientTimeoutMs
 * @param {number} config.ambientClockIntervalMs
 * @param {Document} config.root
 */
function initializeIdleManager(config = {}) {
    const {
        idleTimeoutMs = options.idleTimeoutMs,
        ambientTimeoutMs = options.ambientTimeoutMs,
        ambientClockIntervalMs = options.ambientClockIntervalMs,
        root = document,
    } = config;

    if (
        !Number.isFinite(idleTimeoutMs) ||
        idleTimeoutMs <= 0
    ) {
        throw new RangeError(
            "idleTimeoutMs must be positive"
        );
    }

    if (
        !Number.isFinite(ambientTimeoutMs) ||
        ambientTimeoutMs <= 0
    ) {
        throw new RangeError(
            "ambientTimeoutMs must be positive"
        );
    }

    if (
        !Number.isFinite(ambientClockIntervalMs) ||
        ambientClockIntervalMs <= 0
    ) {
        throw new RangeError(
            "ambientClockIntervalMs must be positive"
        );
    }

    options = {
        idleTimeoutMs,
        ambientTimeoutMs,
        ambientClockIntervalMs,
    };

    resolveElements(root);

    initialized = true;

    currentMode = IDLE_MODE.NONE;

    clearTimers();
    hideIdleMode();

    attachActivityListeners();

    scheduleIdleTimeout();

    return true;
}


/* ==========================================================================
   STATE ACCESS
   ========================================================================== */

/**
 * Get the current idle mode.
 */
function getIdleMode() {
    return currentMode;
}


/**
 * Check whether the display is currently idle.
 */
function isIdle() {
    return currentMode !== IDLE_MODE.NONE;
}


/**
 * Check whether standby mode is active.
 */
function isStandby() {
    return currentMode === IDLE_MODE.STANDBY;
}


/**
 * Check whether ambient mode is active.
 */
function isAmbient() {
    return currentMode === IDLE_MODE.AMBIENT;
}


/**
 * Get a safe copy of the manager state.
 */
function getIdleState() {
    return {
        initialized,
        mode: currentMode,
        idle: isIdle(),
        standby: isStandby(),
        ambient: isAmbient(),
    };
}


/* ==========================================================================
   RESET / DESTROY
   ========================================================================== */

/**
 * Reset the idle manager to its initial state.
 */
function resetIdleManager() {
    clearTimers();

    detachActivityListeners();

    hideIdleMode();

    initialized = false;
    currentMode = IDLE_MODE.NONE;

    return true;
}


/**
 * Destroy the manager and release all resources.
 */
function destroyIdleManager() {
    return resetIdleManager();
}


/* ==========================================================================
   PUBLIC API
   ========================================================================== */

export {
    IDLE_MODE,

    initializeIdleManager,

    enterStandby,
    enterAmbient,

    wake,
    resetIdleTimer,

    getIdleMode,
    getIdleState,

    isIdle,
    isStandby,
    isAmbient,

    resetIdleManager,
    destroyIdleManager,
};