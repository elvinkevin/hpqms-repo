/**
 * ============================================================================
 * HPQMS Public Patient Display
 * js/display-state.js — Frontend Runtime State Store
 * ============================================================================
 *
 * Responsibilities:
 *   - Own the in-memory display state
 *   - Accept authoritative DisplaySnapshot objects
 *   - Apply safe, targeted NotificationEvent mutations
 *   - Track backend connection state
 *   - Notify subscribers when state changes
 *
 * Explicitly does NOT:
 *   - Manipulate the DOM
 *   - Open WebSockets
 *   - Make HTTP requests
 *   - Play audio
 *   - Manage timers
 *   - Manage rotation
 *   - Manage alerts
 *   - Contain hospital business logic
 *
 * Architectural principle:
 *
 *      Backend
 *         │
 *         ├── DisplaySnapshot
 *         └── NotificationEvent
 *                   │
 *                   ▼
 *            display-state.js
 *                   │
 *                   ▼
 *             Immutable view
 *                   │
 *                   ▼
 *             Subscribers
 *
 * ============================================================================
 */

const CONNECTION_STATUS = Object.freeze({
    DISCONNECTED: "DISCONNECTED",
    CONNECTING: "CONNECTING",
    CONNECTED: "CONNECTED",
    RECONNECTING: "RECONNECTING",
    ERROR: "ERROR",
});

const QUEUE_STATUS = Object.freeze({
    WAITING: "WAITING",
    CALLED: "CALLED",
    IN_PROGRESS: "IN_PROGRESS",
    COMPLETED: "COMPLETED",
    NO_SHOW: "NO_SHOW",
    CANCELLED: "CANCELLED",
});

const EVENT_TYPE = Object.freeze({
    TOKEN_CALLED: "TOKEN_CALLED",
    TOKEN_SERVICE_STARTED: "TOKEN_SERVICE_STARTED",
    TOKEN_COMPLETED: "TOKEN_COMPLETED",
    TOKEN_CANCELLED: "TOKEN_CANCELLED",
    TOKEN_NO_SHOW: "TOKEN_NO_SHOW",
    PATIENT_ROUTED: "PATIENT_ROUTED",
    QUEUE_UPDATED: "QUEUE_UPDATED",
    ANNOUNCEMENT_CREATED: "ANNOUNCEMENT_CREATED",
    ANNOUNCEMENT_EXPIRED: "ANNOUNCEMENT_EXPIRED",
});


function createInitialState() {
    return {
        snapshot: {
            facility_name: null,
            server_timestamp: null,
            departments: [],
            announcements: [],
        },

        connection: {
            status: CONNECTION_STATUS.DISCONNECTED,
            connected_at: null,
            disconnected_at: null,
            last_error: null,
            reconnect_attempt: 0,
        },

        metadata: {
            initialized: false,
            stale: false,
            last_snapshot_at: null,
            last_event_at: null,
        },
    };
}


let state = createInitialState();

const subscribers = new Set();


/**
 * Return a deep, read-only-by-convention copy of current state.
 *
 * Consumers must never mutate the returned object and expect the
 * state store to track those mutations.
 */
function getState() {
    return structuredClone(state);
}


/**
 * Notify every registered subscriber.
 *
 * Subscriber errors are isolated so one broken listener does not
 * prevent the remaining listeners from receiving state updates.
 */
function notifySubscribers(reason) {
    const snapshot = getState();

    for (const subscriber of subscribers) {
        try {
            subscriber(snapshot, reason);
        } catch (error) {
            console.error(
                "[DisplayState] Subscriber error:",
                error
            );
        }
    }
}


/**
 * Replace the current display snapshot with an authoritative
 * backend snapshot.
 *
 * This is intentionally a replacement rather than a merge.
 * The backend is the source of truth.
 */
function setSnapshot(snapshot) {
    if (!snapshot || typeof snapshot !== "object") {
        throw new TypeError(
            "[DisplayState] setSnapshot() requires a valid snapshot object."
        );
    }

    state.snapshot = structuredClone({
        facility_name: snapshot.facility_name ?? null,
        server_timestamp: snapshot.server_timestamp ?? null,
        departments: Array.isArray(snapshot.departments)
            ? snapshot.departments
            : [],
        announcements: Array.isArray(snapshot.announcements)
            ? snapshot.announcements
            : [],
    });

    state.metadata.initialized = true;
    state.metadata.stale = false;
    state.metadata.last_snapshot_at = new Date().toISOString();

    notifySubscribers("SNAPSHOT_REPLACED");
}


/**
 * Update backend connection state.
 */
function setConnectionStatus(status, metadata = {}) {
    if (!Object.values(CONNECTION_STATUS).includes(status)) {
        throw new Error(
            `[DisplayState] Invalid connection status: ${status}`
        );
    }

    const now = new Date().toISOString();

    state.connection.status = status;

    if (status === CONNECTION_STATUS.CONNECTED) {
        state.connection.connected_at =
            metadata.connected_at ?? now;

        state.connection.last_error = null;

        if (metadata.reconnect_attempt !== undefined) {
            state.connection.reconnect_attempt =
                metadata.reconnect_attempt;
        }
    }

    if (
        status === CONNECTION_STATUS.DISCONNECTED ||
        status === CONNECTION_STATUS.ERROR
    ) {
        state.connection.disconnected_at =
            metadata.disconnected_at ?? now;
    }

    if (metadata.last_error !== undefined) {
        state.connection.last_error = metadata.last_error;
    }

    if (metadata.reconnect_attempt !== undefined) {
        state.connection.reconnect_attempt =
            metadata.reconnect_attempt;
    }

    notifySubscribers("CONNECTION_STATUS_CHANGED");
}


/**
 * Find a department by UUID/string representation.
 */
function findDepartment(departmentId) {
    if (!departmentId) {
        return null;
    }

    return state.snapshot.departments.find(
        department =>
            String(department.department_id) === String(departmentId)
    ) ?? null;
}


/**
 * Find an active token within a department.
 */
function findActiveToken(department, tokenNumber) {
    if (!department || !tokenNumber) {
        return null;
    }

    return department.active_tokens.find(
        token => token.token_number === tokenNumber
    ) ?? null;
}


/**
 * Remove a token from active_tokens.
 */
function removeActiveToken(department, tokenNumber) {
    if (!department || !Array.isArray(department.active_tokens)) {
        return null;
    }

    const index = department.active_tokens.findIndex(
        token => token.token_number === tokenNumber
    );

    if (index === -1) {
        return null;
    }

    return department.active_tokens.splice(index, 1)[0];
}


/**
 * Add a token to recent_tokens without creating duplicates.
 */
function addRecentToken(department, tokenNumber) {
    if (!department || !tokenNumber) {
        return;
    }

    if (!Array.isArray(department.recent_tokens)) {
        department.recent_tokens = [];
    }

    department.recent_tokens = department.recent_tokens.filter(
        token => token.token_number !== tokenNumber
    );

    department.recent_tokens.unshift({
        token_number: tokenNumber,
    });
}


/**
 * Handle TOKEN_CALLED.
 */
function handleTokenCalled(event) {
    const department = findDepartment(event.department_id);

    if (!department) {
        return;
    }

    if (!Array.isArray(department.active_tokens)) {
        department.active_tokens = [];
    }

    let token = findActiveToken(
        department,
        event.token_number
    );

    if (!token) {
        token = {
            token_number: event.token_number,
            service_point: event.service_point ?? null,
            status: QUEUE_STATUS.CALLED,
            called_at: event.occurred_at ?? null,
        };

        department.active_tokens.unshift(token);
    } else {
        token.status = QUEUE_STATUS.CALLED;
        token.service_point =
            event.service_point ?? token.service_point ?? null;
        token.called_at =
            event.occurred_at ?? token.called_at ?? null;
    }
}


/**
 * Handle TOKEN_SERVICE_STARTED.
 */
function handleTokenServiceStarted(event) {
    const department = findDepartment(event.department_id);

    if (!department) {
        return;
    }

    let token = findActiveToken(
        department,
        event.token_number
    );

    /*
     * A service-start event can occasionally arrive before the
     * display has received the corresponding TOKEN_CALLED event.
     *
     * Rather than silently losing the event, create the active
     * representation.
     */
    if (!token) {
        if (!Array.isArray(department.active_tokens)) {
            department.active_tokens = [];
        }

        token = {
            token_number: event.token_number,
            service_point: event.service_point ?? null,
            status: QUEUE_STATUS.IN_PROGRESS,
            called_at: event.occurred_at ?? null,
        };

        department.active_tokens.unshift(token);
        return;
    }

    token.status = QUEUE_STATUS.IN_PROGRESS;

    if (event.service_point) {
        token.service_point = event.service_point;
    }
}


/**
 * Handle TOKEN_COMPLETED.
 */
function handleTokenCompleted(event) {
    const department = findDepartment(event.department_id);

    if (!department) {
        return;
    }

    removeActiveToken(
        department,
        event.token_number
    );

    addRecentToken(
        department,
        event.token_number
    );
}


/**
 * Handle TOKEN_CANCELLED.
 */
function handleTokenCancelled(event) {
    const department = findDepartment(event.department_id);

    if (!department) {
        return;
    }

    removeActiveToken(
        department,
        event.token_number
    );
}

/**
 * Handle TOKEN_NO_SHOW.
 */
function handleTokenNoShow(event) {
    const department = findDepartment(event.department_id);

    if (!department) {
        return;
    }

    removeActiveToken(
        department,
        event.token_number
    );
}


/**
 * Handle PATIENT_ROUTED.
 *
 * Requires routing context containing source and target departments.
 */
function handlePatientRouted(event) {
    const sourceDepartment = findDepartment(
        event.source_department_id
    );

    const targetDepartment = findDepartment(
        event.target_department_id
    );

    /*
     * If the event does not contain enough routing context,
     * we deliberately refuse to guess.
     *
     * The application layer should request a fresh snapshot.
     */
    if (!sourceDepartment || !targetDepartment) {
        state.metadata.stale = true;
        return;
    }

    const token = removeActiveToken(
        sourceDepartment,
        event.token_number
    );

    /*
     * We may not have the token in the source department if
     * the display joined late or missed an earlier event.
     *
     * In that case, mark the snapshot stale rather than
     * inventing incomplete state.
     */
    if (!token) {
        state.metadata.stale = true;
        return;
    }

    if (!Array.isArray(targetDepartment.next_tokens)) {
        targetDepartment.next_tokens = [];
    }

    const alreadyExists = targetDepartment.next_tokens.some(
        nextToken =>
            nextToken.token_number === event.token_number
    );

    if (!alreadyExists) {
        targetDepartment.next_tokens.unshift({
            token_number: event.token_number,
        });
    }
}


/**
 * Handle ANNOUNCEMENT_CREATED.
 */
function handleAnnouncementCreated(event) {
    if (!event.message) {
        return;
    }

    if (!Array.isArray(state.snapshot.announcements)) {
        state.snapshot.announcements = [];
    }

    /*
     * Prevent duplicate announcement insertion.
     */
    if (
        event.announcement_id &&
        state.snapshot.announcements.some(
            announcement =>
                String(announcement.announcement_id) ===
                String(event.announcement_id)
        )
    ) {
        return;
    }

    state.snapshot.announcements.push({
        announcement_id: event.announcement_id,
        priority: event.announcement_priority ?? "INFO",
        message: event.message,
        starts_at: event.starts_at ?? null,
        expires_at: event.expires_at ?? null,
    });
}


/**
 * Handle ANNOUNCEMENT_EXPIRED.
 */
function handleAnnouncementExpired(event) {
    if (!event.announcement_id) {
        return;
    }

    state.snapshot.announcements =
        state.snapshot.announcements.filter(
            announcement =>
                String(announcement.announcement_id) !==
                String(event.announcement_id)
        );
}


/**
 * Apply a NotificationEvent to local state.
 *
 * This method deliberately performs only deterministic,
 * in-memory state mutations.
 */
function applyEvent(event) {
    if (!event || typeof event !== "object") {
        throw new TypeError(
            "[DisplayState] applyEvent() requires an event object."
        );
    }

    if (!event.event_type) {
        throw new Error(
            "[DisplayState] NotificationEvent requires event_type."
        );
    }

    switch (event.event_type) {
        case EVENT_TYPE.TOKEN_CALLED:
            handleTokenCalled(event);
            break;

        case EVENT_TYPE.TOKEN_SERVICE_STARTED:
            handleTokenServiceStarted(event);
            break;

        case EVENT_TYPE.TOKEN_COMPLETED:
            handleTokenCompleted(event);
            break;

        case EVENT_TYPE.TOKEN_CANCELLED:
            handleTokenCancelled(event);
            break;

        case EVENT_TYPE.TOKEN_NO_SHOW:
            handleTokenNoShow(event);
            break;

        case EVENT_TYPE.PATIENT_ROUTED:
            handlePatientRouted(event);
            break;

        case EVENT_TYPE.QUEUE_UPDATED:
            /*
             * Do not attempt to reconstruct queue state.
             * The snapshot is now considered stale.
             */
            state.metadata.stale = true;
            break;

        case EVENT_TYPE.ANNOUNCEMENT_CREATED:
            handleAnnouncementCreated(event);
            break;

        case EVENT_TYPE.ANNOUNCEMENT_EXPIRED:
            handleAnnouncementExpired(event);
            break;

        default:
            console.warn(
                `[DisplayState] Unknown event type: ${event.event_type}`
            );

            return;
    }

    state.metadata.last_event_at =
        event.occurred_at ?? new Date().toISOString();

    notifySubscribers(`EVENT_${event.event_type}`);
}


/**
 * Subscribe to state changes.
 *
 * Returns an unsubscribe function.
 */
function subscribe(listener) {
    if (typeof listener !== "function") {
        throw new TypeError(
            "[DisplayState] subscribe() requires a function."
        );
    }

    subscribers.add(listener);

    return function unsubscribe() {
        subscribers.delete(listener);
    };
}


/**
 * Reset state to its initial condition.
 */
function reset() {
    state = createInitialState();

    notifySubscribers("STATE_RESET");
}


export {
    CONNECTION_STATUS,
    QUEUE_STATUS,
    EVENT_TYPE,

    getState,
    setSnapshot,
    applyEvent,
    setConnectionStatus,
    subscribe,
    reset,
};