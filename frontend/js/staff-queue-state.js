/**
 * Local State Store for Staff Dashboard (Phase 4)
 *
 * Separates department-wide queue state from staff-owned active/no-show patients.
 */

const ACTIVE_STATUSES = new Set(["CALLED", "IN_PROGRESS"]);

let state = createInitialState();

function createInitialState() {
    return {
        departmentId: null,
        staffId: null,

        queueEntries: [],
        noShowEntries: [],

        activePatient: null,

        initialized: false,
        stale: false,
    };
}

/**
 * Reset local state back to initial default.
 */
export function clear() {
    state = createInitialState();
}

/**
 * Get a shallow copy of the current state container.
 */
export function getState() {
    return { ...state };
}

/**
 * Set current department and staff identity.
 * Clears state if context changes.
 */
export function setContext(departmentId, staffId) {
    if (
        String(state.departmentId) !== String(departmentId) ||
        String(state.staffId) !== String(staffId)
    ) {
        clear();
        state.departmentId = departmentId;
        state.staffId = staffId;
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

    rederiveActivePatient();
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
 * Get all department queue entries.
 */
export function getDepartmentQueue() {
    return [...state.queueEntries];
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
    return state.noShowEntries.filter((entry) => isMyPatient(entry));
}

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

        // --- NEW CASE ADDED HERE ---
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
                    department_id: event.department_id,
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