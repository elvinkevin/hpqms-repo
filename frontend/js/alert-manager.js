/* ==========================================================================
   HPQMS Public Patient Display Board
   js/alert-manager.js — Alert & Notification Manager
   ========================================================================== */

/*
 * The alert manager is responsible for:
 *
 *   - deciding whether an event requires an alert
 *   - determining alert priority
 *   - preventing duplicate alerts
 *   - managing the active alert
 *   - queueing alerts that cannot be shown immediately
 *   - expiring alerts
 *   - delegating presentation to external callbacks
 *
 * It does NOT:
 *
 *   - access the DOM
 *   - connect to WebSocket
 *   - call the API
 *   - mutate display-state.js
 *   - play audio directly
 *
 * Presentation is delegated through callbacks supplied to initialize().
 */


/* ==========================================================================
   Constants
   ========================================================================== */

const ALERT_PRIORITY = Object.freeze({
    LOW: 1,
    NORMAL: 2,
    HIGH: 3,
    CRITICAL: 4,
});


const ALERT_EVENT_TYPES = Object.freeze([
    "TOKEN_CALLED",
    "ANNOUNCEMENT_CREATED",
]);


const DEFAULT_OPTIONS = Object.freeze({
    defaultDurationMs: 5000,

    maxQueueSize: 20,

    deduplicationWindowMs: 3000,
});


/* ==========================================================================
   Internal State
   ========================================================================== */

let initialized = false;

let options = {
    ...DEFAULT_OPTIONS,
};

let activeAlert = null;

let alertQueue = [];

let alertTimer = null;

let recentAlerts = new Map();


/*
 * Presentation callbacks.
 *
 * These are deliberately injected so that the manager
 * remains independent from the DOM/audio implementation.
 */
let callbacks = {
    show: null,
    dismiss: null,
    playSound: null,
};


/* ==========================================================================
   Utility Functions
   ========================================================================== */

/**
 * Convert a NotificationPriority into a sortable numeric priority.
 */
function getPriorityValue(priority) {
    return ALERT_PRIORITY[priority] ?? 0;
}


/**
 * Determine whether an event should produce an alert.
 */
function isAlertEvent(event) {
    if (!event || typeof event !== "object") {
        return false;
    }

    return ALERT_EVENT_TYPES.includes(
        event.event_type
    );
}


/**
 * Generate a stable identifier for deduplication.
 */
function getAlertKey(event) {
    if (event.event_id) {
        return event.event_id;
    }

    return [
        event.event_type,
        event.token_number ?? "",
        event.dept_id ?? "",
        event.message ?? "",
    ].join(":");
}


/**
 * Normalize an incoming NotificationEvent into
 * the internal alert representation.
 */
function normalizeAlert(event) {
    const priority =
        event.priority ?? "NORMAL";

    return {
        alert_id: getAlertKey(event),

        event_type: event.event_type,

        priority,

        priority_value:
            getPriorityValue(priority),

        token_number:
            event.token_number ?? null,

        dept_id:
            event.dept_id ?? null,

        department_name:
            event.department_name ?? null,

        service_point:
            event.service_point ?? null,

        message:
            event.message ?? null,

        occurred_at:
            event.occurred_at ??
            new Date().toISOString(),

        duration_ms:
            options.defaultDurationMs,

        event,
    };
}


/**
 * Check whether the event was recently processed.
 */
function isDuplicate(alert) {
    const previous =
        recentAlerts.get(alert.alert_id);

    if (!previous) {
        return false;
    }

    return (
        Date.now() - previous <
        options.deduplicationWindowMs
    );
}


/**
 * Record an alert as recently processed.
 */
function recordAlert(alert) {
    recentAlerts.set(
        alert.alert_id,
        Date.now()
    );
}


/**
 * Remove expired deduplication entries.
 */
function cleanupRecentAlerts() {
    const now = Date.now();

    for (
        const [
            alertId,
            timestamp,
        ] of recentAlerts
    ) {
        if (
            now - timestamp >=
            options.deduplicationWindowMs
        ) {
            recentAlerts.delete(alertId);
        }
    }
}


/**
 * Sort alerts by priority while preserving
 * FIFO order within the same priority.
 */
function sortQueue() {
    alertQueue.sort(
        (a, b) =>
            b.priority_value -
            a.priority_value
    );
}


/* ==========================================================================
   Alert Presentation
   ========================================================================== */

/**
 * Display an alert through the injected presentation layer.
 */
function presentAlert(alert) {
    activeAlert = alert;

    if (typeof callbacks.show === "function") {
        callbacks.show(alert);
    }

    if (
        typeof callbacks.playSound ===
        "function"
    ) {
        callbacks.playSound(alert);
    }

    startAlertTimer(alert);
}


/**
 * Start the expiration timer for an alert.
 */
function startAlertTimer(alert) {
    clearAlertTimer();

    alertTimer = setTimeout(() => {
        /*
         * Only expire the alert if it is still
         * the currently active alert.
         */
        if (
            activeAlert?.alert_id ===
            alert.alert_id
        ) {
            dismissActiveAlert();
        }
    }, alert.duration_ms);
}


/**
 * Clear the current alert timer.
 */
function clearAlertTimer() {
    if (alertTimer !== null) {
        clearTimeout(alertTimer);

        alertTimer = null;
    }
}


/**
 * Dismiss the current alert and display the
 * next queued alert, if one exists.
 */
function dismissActiveAlert() {
    clearAlertTimer();

    const dismissed =
        activeAlert;

    activeAlert = null;

    if (
        dismissed &&
        typeof callbacks.dismiss ===
            "function"
    ) {
        callbacks.dismiss(dismissed);
    }

    processQueue();
}


/**
 * Process the next alert in the queue.
 */
function processQueue() {
    if (activeAlert) {
        return;
    }

    if (alertQueue.length === 0) {
        return;
    }

    const nextAlert =
        alertQueue.shift();

    presentAlert(nextAlert);
}


/* ==========================================================================
   Event Handling
   ========================================================================== */

/**
 * Handle a NotificationEvent.
 *
 * Returns true if the event resulted in an
 * alert being accepted by the manager.
 */
function handleEvent(event) {
    if (!initialized) {
        return false;
    }

    if (!isAlertEvent(event)) {
        return false;
    }

    cleanupRecentAlerts();

    const alert =
        normalizeAlert(event);

    if (isDuplicate(alert)) {
        return false;
    }

    recordAlert(alert);

    /*
     * If nothing is currently being displayed,
     * show the alert immediately.
     */
    if (!activeAlert) {
        presentAlert(alert);

        return true;
    }

    /*
     * Higher-priority alerts should be promoted
     * immediately rather than waiting behind a
     * lower-priority alert.
     */
    if (
        alert.priority_value >
        activeAlert.priority_value
    ) {
        const previous =
            activeAlert;

        clearAlertTimer();

        activeAlert = null;

        if (
            typeof callbacks.dismiss ===
            "function"
        ) {
            callbacks.dismiss(previous);
        }

        presentAlert(alert);

        return true;
    }

    /*
     * Otherwise queue the alert.
     */
    if (
        alertQueue.length >=
        options.maxQueueSize
    ) {
        /*
         * If the queue is full, discard the
         * lowest-priority queued alert when
         * the incoming alert is more important.
         */
        sortQueue();

        const lowestPriority =
            alertQueue[
                alertQueue.length - 1
            ];

        if (
            alert.priority_value >
            lowestPriority.priority_value
        ) {
            alertQueue.pop();

            alertQueue.push(alert);

            sortQueue();

            return true;
        }

        return false;
    }

    alertQueue.push(alert);

    sortQueue();

    return true;
}


/* ==========================================================================
   Initialization
   ========================================================================== */

/**
 * Initialize the alert manager.
 *
 * Initialization is explicit so importing the module
 * has no side effects.
 */
function initialize(customOptions = {}) {
    if (
        customOptions === null ||
        typeof customOptions !== "object"
    ) {
        throw new TypeError(
            "Alert manager options must be an object"
        );
    }

    options = {
        ...DEFAULT_OPTIONS,
        ...customOptions,
    };

    if (
        !Number.isFinite(
            options.defaultDurationMs
        ) ||
        options.defaultDurationMs <= 0
    ) {
        throw new RangeError(
            "defaultDurationMs must be positive"
        );
    }

    if (
        !Number.isInteger(
            options.maxQueueSize
        ) ||
        options.maxQueueSize <= 0
    ) {
        throw new RangeError(
            "maxQueueSize must be a positive integer"
        );
    }

    if (
        !Number.isFinite(
            options.deduplicationWindowMs
        ) ||
        options.deduplicationWindowMs < 0
    ) {
        throw new RangeError(
            "deduplicationWindowMs must be non-negative"
        );
    }

    initialized = true;

    return getState();
}


/**
 * Configure presentation callbacks.
 */
function setCallbacks({
    show = null,
    dismiss = null,
    playSound = null,
} = {}) {
    if (
        show !== null &&
        typeof show !== "function"
    ) {
        throw new TypeError(
            "show callback must be a function or null"
        );
    }

    if (
        dismiss !== null &&
        typeof dismiss !== "function"
    ) {
        throw new TypeError(
            "dismiss callback must be a function or null"
        );
    }

    if (
        playSound !== null &&
        typeof playSound !== "function"
    ) {
        throw new TypeError(
            "playSound callback must be a function or null"
        );
    }

    callbacks = {
        show,
        dismiss,
        playSound,
    };
}


/* ==========================================================================
   State Access
   ========================================================================== */

/**
 * Return a defensive copy of manager state.
 */
function getState() {
    return {
        initialized,

        activeAlert: activeAlert
            ? {
                ...activeAlert,
                event: activeAlert.event
                    ? {
                        ...activeAlert.event,
                    }
                    : null,
            }
            : null,

        queuedAlerts: alertQueue.map(
            (alert) => ({
                ...alert,
                event: alert.event
                    ? {
                        ...alert.event,
                    }
                    : null,
            })
        ),

        queueSize:
            alertQueue.length,
    };
}


/**
 * Return the currently active alert.
 */
function getActiveAlert() {
    return activeAlert
        ? {
            ...activeAlert,
            event: activeAlert.event
                ? {
                    ...activeAlert.event,
                }
                : null,
        }
        : null;
}


/**
 * Return a copy of the current queue.
 */
function getQueuedAlerts() {
    return alertQueue.map(
        (alert) => ({
            ...alert,
            event: alert.event
                ? {
                    ...alert.event,
                }
                : null,
        })
    );
}


/* ==========================================================================
   Manual Controls
   ========================================================================== */

/**
 * Manually dismiss the current alert.
 */
function dismiss() {
    if (!activeAlert) {
        return false;
    }

    dismissActiveAlert();

    return true;
}


/**
 * Clear the entire alert queue.
 *
 * The currently active alert remains visible.
 */
function clearQueue() {
    const count =
        alertQueue.length;

    alertQueue = [];

    return count;
}


/**
 * Completely reset the manager.
 */
function reset() {
    clearAlertTimer();

    activeAlert = null;

    alertQueue = [];

    recentAlerts.clear();

    initialized = false;

    options = {
        ...DEFAULT_OPTIONS,
    };

    callbacks = {
        show: null,
        dismiss: null,
        playSound: null,
    };
}


/* ==========================================================================
   Public API
   ========================================================================== */

export {
    ALERT_PRIORITY,
    ALERT_EVENT_TYPES,

    initialize,
    setCallbacks,

    handleEvent,

    getState,
    getActiveAlert,
    getQueuedAlerts,

    dismiss,
    clearQueue,
    reset,
};