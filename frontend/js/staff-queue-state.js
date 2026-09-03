/**
 * Local State Store for Staff Dashboard (Phase 4)
 *
 * Separates department-wide queue state from staff-owned active/no-show patients.
 * Serves as the single authoritative source of truth for queue data.
 */

const ACTIVE_STATUSES = new Set(["CALLED", "IN_PROGRESS"]);

let state = createInitialState();

/*
 * Subscribers are notified on state mutations (context change,
 * snapshot, event, selection). Returns an unsubscribe function.
 */
const subscribers = new Set();

function createInitialState() {
    return {
        // Context
        departmentId: null,
        staffId: null,

        // Queue
        queueEntries: [],
        noShowEntries: [],

        // Selection ("which row did the staff member click?")
        selectedQueueEntryId: null,

        // Encounter ("which patient am I currently serving?")
        activePatient: null,

        // Synchronization
        initialized: false,
        stale: false,
    };
}

function notify() {
    for (const listener of [...subscribers]) {
        try {
            listener(getState());
        } catch (error) {
            console.error("staff-queue-state listener failed:", error);
        }
    }
}

export function subscribe(listener) {
    if (typeof listener !== "function") {
        throw new TypeError("State listener must be a function");
    }

    subscribers.add(listener);

    return () => {
        subscribers.delete(listener);
    };
}

/**
 * Reset local state back to initial default and notify subscribers.
 */
export function clear() {
    state = createInitialState();
    notify();
}

/**
 * Get a isolated snapshot copy of current state to prevent external mutations.
 */
export function getState() {
    return {
        ...state,
        queueEntries: state.queueEntries.map((e) => ({ ...e })),
        noShowEntries: state.noShowEntries.map((e) => ({ ...e })),
        selectedQueueEntryId: state.selectedQueueEntryId,
        activePatient: state.activePatient ? { ...state.activePatient } : null,
    };
}

/**
 * Set current department and staff identity.
 * Clears state on context change and notifies subscribers exactly once.
 */
export function setContext(departmentId, staffId) {
    if (
        String(state.departmentId) !== String(departmentId) ||
        String(state.staffId) !== String(staffId)
    ) {
        state = createInitialState();
        state.departmentId = departmentId;
        state.staffId = staffId;
        notify();
    }
}

/**
 * Ingest full snapshot into state and derive active patient.
 */
export function setSnapshot(snapshot = {}) {
    state.queueEntries = Array.isArray(snapshot.queueEntries)
        ? [...snapshot.queueEntries]
        : [];

    state.noShowEntries = Array.isArray(snapshot.noShowEntries)
        ? [...snapshot.noShowEntries]
        : [];

    state.initialized = true;
    state.stale = false;

    /*
     * A fresh snapshot may no longer contain the previously selected
     * entry — drop the selection rather than pinning a stale row.
     */
    if (
        state.selectedQueueEntryId &&
        !state.queueEntries.some(
            (e) => e.queue_entry_id === state.selectedQueueEntryId
        )
    ) {
        state.selectedQueueEntryId = null;
    }

    rederiveActivePatient();
    notify();
}

/*
 * Selection — UI state. Deliberately separate from activePatient
 * (the encounter). Selecting a different queue row must never
 * disturb an in-progress encounter.
 */
export function selectQueueEntry(queueEntryId) {
    state.selectedQueueEntryId = queueEntryId || null;
    notify();
}

export function clearSelection() {
    state.selectedQueueEntryId = null;
    notify();
}

export function getSelectedQueueEntry() {
    if (!state.selectedQueueEntryId) {
        return null;
    }

    const selected = state.queueEntries.find(
        (e) => e.queue_entry_id === state.selectedQueueEntryId
    );

    return selected ? { ...selected } : null;
}

/*
 * Mark the local state as potentially out of sync with the server
 * (e.g. a QUEUE_UPDATED event we cannot apply locally). The shell
 * observes `stale` and triggers an authoritative snapshot fetch.
 */
export function markStale() {
    if (!state.stale) {
        state.stale = true;
        notify();
    }
}

/**
 * Check if a queue entry is assigned to the current active staff member.
 */
export function isMyPatient(entry) {
    if (
        state.staffId === null ||
        state.staffId === undefined ||
        !entry ||
        entry.assigned_staff_id === null ||
        entry.assigned_staff_id === undefined
    ) {
        return false;
    }
    return String(entry.assigned_staff_id) === String(state.staffId);
}

/**
 * Get all department queue entries (isolated copies).
 */
export function getDepartmentQueue() {
    return state.queueEntries.map((e) => ({ ...e }));
}

/**
 * Get active patient owned by current staff member (CALLED or IN_PROGRESS status).
 */
export function getMyActivePatient() {
    return state.activePatient ? { ...state.activePatient } : null;
}

/**
 * Get no-show entries assigned to current staff member.
 */
export function getMyNoShowEntries() {
    return state.noShowEntries
        .filter((entry) => isMyPatient(entry))
        .map((e) => ({ ...e }));
}

/**
 * Apply realtime WebSocket events directly to update internal state.
 */
export function applyEvent(event) {
    if (!event || typeof event !== "object" || !event.event_type) {
        return;
    }

    const { event_type, queue_entry_id, assigned_staff_id } = event;

    switch (event_type) {
        case "TOKEN_CALLED": {
            updateOrInsertQueueEntry(queue_entry_id, {
                status: "CALLED",
                ...(assigned_staff_id !== undefined
                    ? { assigned_staff_id }
                    : {}),
            });
            break;
        }

        case "TOKEN_SERVICE_STARTED": {
            updateOrInsertQueueEntry(queue_entry_id, {
                status: "IN_PROGRESS",
                ...(assigned_staff_id !== undefined
                    ? { assigned_staff_id }
                    : {}),
            });
            break;
        }

        case "TOKEN_REQUEUED": {
            // Remove from noShowEntries if it was previously marked as a no-show
            state.noShowEntries = state.noShowEntries.filter(
                (e) => e.queue_entry_id !== queue_entry_id
            );

            // Update entry state back to WAITING and clear staff assignment
            if (event.queue_entry) {
                updateOrInsertQueueEntry(queue_entry_id, {
                    ...event.queue_entry,
                    status: "WAITING",
                    assigned_staff_id: null,
                });
            } else {
                updateOrInsertQueueEntry(queue_entry_id, {
                    status: "WAITING",
                    assigned_staff_id: null,
                });
            }
            break;
        }

        case "TOKEN_COMPLETED":
        case "TOKEN_CANCELLED": {
            removeQueueEntry(queue_entry_id);
            break;
        }

        case "TOKEN_NO_SHOW": {
            const existingEntry = state.queueEntries.find(
                (e) => e.queue_entry_id === queue_entry_id
            );
            removeQueueEntry(queue_entry_id);

            const finalAssignedStaffId =
                assigned_staff_id !== undefined
                    ? assigned_staff_id
                    : existingEntry?.assigned_staff_id ?? null;

            const noShowEntry = {
                queue_entry_id,
                assigned_staff_id: finalAssignedStaffId,
                status: "NO_SHOW",
            };

            // Upsert into noShowEntries
            const existingNoShowIndex = state.noShowEntries.findIndex(
                (e) => e.queue_entry_id === queue_entry_id
            );
            if (existingNoShowIndex >= 0) {
                state.noShowEntries[existingNoShowIndex] = noShowEntry;
            } else {
                state.noShowEntries.push(noShowEntry);
            }
            break;
        }

        case "PATIENT_ROUTED": {
            if (event.queue_entry) {
                const incoming = event.queue_entry;
                updateOrInsertQueueEntry(incoming.queue_entry_id, incoming);
            } else if (queue_entry_id) {
                updateOrInsertQueueEntry(queue_entry_id, {
                    status: "WAITING",
                    dept_id: event.dept_id,
                });
            }
            break;
        }

        case "QUEUE_UPDATED": {
            state.stale = true;
            break;
        }

        default:
            return;
    }

    rederiveActivePatient();
    notify();
}

/**
 * Helper to update an existing entry or append a new entry in department queue.
 */
function updateOrInsertQueueEntry(queueEntryId, attributes) {
    if (!queueEntryId) return;

    const index = state.queueEntries.findIndex(
        (e) => e.queue_entry_id === queueEntryId
    );

    if (index >= 0) {
        state.queueEntries[index] = {
            ...state.queueEntries[index],
            ...attributes,
        };
    } else {
        state.queueEntries.push({
            queue_entry_id: queueEntryId,
            status: "WAITING",
            assigned_staff_id: null,
            ...attributes,
        });
    }
}

/**
 * Helper to remove an entry from department queue entries.
 */
function removeQueueEntry(queueEntryId) {
    if (!queueEntryId) return;
    state.queueEntries = state.queueEntries.filter(
        (e) => e.queue_entry_id !== queueEntryId
    );
}

/**
 * Internal helper to compute and set my active patient.
 */
function rederiveActivePatient() {
    const active = state.queueEntries.find(
        (entry) => isMyPatient(entry) && ACTIVE_STATUSES.has(entry.status)
    );

    state.activePatient = active ? { ...active } : null;
}