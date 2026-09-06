/* ==========================================================================
   HPQMS Staff Dashboard — Action Layer (Phase 4 / A4.1d)
   js/staff-actions.js
   --------------------------------------------------------------------------
   Responsibility:
     - Translate staff intent into backend API operations.
     - Apply UI-level workspace/role policy before API calls.
     - Apply ownership/context guards where appropriate.
     - Feed successful queue mutations into staff-queue-state.
     - Trigger authoritative reconciliation after mutations.

   Architecture:

       UI / Components
              │
              ▼
       staff-actions.js
              │
              ├── UI policy
              ├── context validation
              ├── ownership validation
              │
              ▼
       staff-api.js
              │
              ▼
           Backend
              │
              ▼
       response / WS event
              │
              ▼
       staff-queue-state.js

   IMPORTANT:
     Backend RBAC and domain validation remain the ultimate authority.
     Frontend checks exist only for UX, early failure, and safe rendering.

   This module is the ONLY action layer that UI components should use.
   Components and staff.js must NOT call staff-api.js directly.
   ========================================================================== */

import {
    getNextPatient,
    callQueueEntry,
    startQueueEntry,
    completeQueueEntry,
    markNoShowQueueEntry,
    requeueQueueEntry,
    cancelQueueEntry,
    setQueuePriority,
    transferPatient,
    dischargePatient,
    getDepartments,
} from "./staff-api.js";

import {
    completePatientRegistration as apiCompletePatientRegistration,
} from "./staff-api.js";


import {
    applyEvent,
    getState,
    getMyActivePatient,
    getSelectedQueueEntry,
} from "./staff-queue-state.js";

import {
    canPerformAction,
    ACTION,
} from "./staff-workspace-config.js";


/* ==========================================================================
   STAFF CONTEXT
   ========================================================================== */

let staffContext = {
    staffId: null,
    role: null,
    departmentId: null,
};

/**
 * Set the current authenticated staff context.
 *
 * Called by staff.js after authentication and during logout/reset.
 *
 * @param {Object|null} user
 */
export function setStaffContext(user) {
    staffContext = {
        staffId: user?.staff_id ?? null,
        role: user?.role ?? null,
        departmentId: user?.dept_id ?? null,
    };
}

/**
 * Return a defensive copy of the current staff context.
 */
export function getStaffContext() {
    return { ...staffContext };
}


/* ==========================================================================
   RECONCILIATION
   ========================================================================== */

/*
 * staff.js owns the actual snapshot-fetching implementation.
 *
 * staff-actions.js only knows that it can request an authoritative
 * reconciliation after a successful backend mutation.
 */
let reconcileHandler = null;

/**
 * Register the shell's authoritative snapshot synchronization callback.
 *
 * @param {Function|null} handler
 */
export function registerReconcileHandler(handler) {
    reconcileHandler =
        typeof handler === "function"
            ? handler
            : null;
}

/**
 * Reconcile local queue state with the authoritative backend snapshot.
 *
 * This is the ONE mechanism this module uses to refresh
 * staff-queue-state after a mutation. There is deliberately no second,
 * differently-named refresh path — a `refreshQueueState()` call was
 * previously introduced in a duplicate registration function below
 * without ever being defined or imported anywhere, which threw
 * `ReferenceError: refreshQueueState is not defined` at runtime. If a
 * future change needs a different refresh strategy, change what
 * reconcile() does here rather than adding a second entry point.
 */
async function reconcile() {
    if (reconcileHandler) {
        await reconcileHandler();
    }
}


/* ==========================================================================
   ERROR HELPERS
   ========================================================================== */

/**
 * Create a predictable action error.
 *
 * @param {string} message
 * @param {number} status
 * @returns {Error}
 */
function createActionError(message, status) {
    const error = new Error(message);
    error.status = status;
    return error;
}


/* ==========================================================================
   CONTEXT / POLICY GUARDS
   ========================================================================== */

/**
 * Ensure the action is available to the current staff role.
 *
 * This is a UI policy check only. Backend RBAC remains authoritative.
 *
 * @param {string} action
 */
function assertCanPerform(action) {
    if (!canPerformAction(staffContext.role, action)) {
        throw createActionError(
            `Action "${action}" is not available in this workspace.`,
            403
        );
    }
}

/**
 * Ensure a staff member is authenticated and has the minimum context
 * required to perform an action.
 */
function assertStaffContext() {
    if (!staffContext.staffId) {
        throw createActionError(
            "Staff identity is not available.",
            401
        );
    }

    if (!staffContext.role) {
        throw createActionError(
            "Staff role is not available.",
            401
        );
    }
}

/**
 * Ensure the staff member has a department when an action requires one.
 */
function assertDepartmentContext() {
    if (!staffContext.departmentId) {
        throw createActionError(
            "Staff department is not available.",
            400
        );
    }
}

/**
 * Combined guard used by normal staff actions.
 */
function assertActionContext(action, requiresDepartment = false) {
    assertStaffContext();
    assertCanPerform(action);

    if (requiresDepartment) {
        assertDepartmentContext();
    }
}


/* ==========================================================================
   OWNERSHIP / TARGET RESOLUTION
   ========================================================================== */

/**
 * Check whether a queue entry belongs to the current staff member.
 *
 * @param {Object|null} entry
 * @returns {boolean}
 */
function isOwnedByMe(entry) {
    if (!entry || !staffContext.staffId) {
        return false;
    }

    if (
        entry.assigned_staff_id === null ||
        entry.assigned_staff_id === undefined
    ) {
        return false;
    }

    return (
        String(entry.assigned_staff_id) ===
        String(staffContext.staffId)
    );
}

/**
 * Resolve the queue entry an action should operate on.
 *
 * Priority:
 *
 *   1. Explicit entry ID matching the active encounter.
 *   2. Explicit entry ID matching the current selection.
 *   3. Explicit entry ID found in department queue.
 *   4. Current active encounter when no ID is supplied.
 *
 * The active encounter is deliberately separate from row selection.
 *
 * @param {string|null} entryId
 * @returns {Object|null}
 */
function resolveTargetEntry(entryId = null) {
    const { queueEntries = [] } = getState();
    const active = getMyActivePatient();

    if (entryId) {
        if (
            active &&
            String(active.queue_entry_id) === String(entryId)
        ) {
            return active;
        }

        const selected = getSelectedQueueEntry();

        if (
            selected &&
            String(selected.queue_entry_id) === String(entryId)
        ) {
            return selected;
        }

        return (
            queueEntries.find(
                (entry) =>
                    String(entry.queue_entry_id) === String(entryId)
            ) || null
        );
    }

    return active || null;
}

/**
 * Require a target queue entry.
 *
 * @param {string|null} entryId
 * @returns {Object}
 */
function requireTargetEntry(entryId = null) {
    const entry = resolveTargetEntry(entryId);

    if (!entry) {
        throw createActionError(
            "No patient is selected.",
            404
        );
    }

    return entry;
}

/**
 * Require that a queue entry belongs to the current staff member.
 *
 * @param {Object} entry
 */
function assertOwnership(entry) {
    if (!isOwnedByMe(entry)) {
        throw createActionError(
            "This patient is assigned to another staff member.",
            403
        );
    }
}


/* ==========================================================================
   QUEUE STATE INGESTION
   ========================================================================== */

/**
 * Apply a successful queue mutation to the local state store.
 *
 * The event type is explicitly supplied by the action that performed the
 * operation. We intentionally do NOT infer event semantics from the
 * resulting status.
 *
 * @param {Object} entry
 * @param {string} eventType
 */
function ingestQueueEntry(entry, eventType) {
    if (!entry?.queue_entry_id || !eventType) {
        return;
    }

    applyEvent({
        event_type: eventType,
        queue_entry_id: entry.queue_entry_id,
        assigned_staff_id: entry.assigned_staff_id,
        queue_entry: entry,
    });
}

/**
 * Apply the local mutation, then reconcile against the backend.
 *
 * The local update gives the UI immediate feedback.
 * Reconciliation guarantees convergence with the authoritative server.
 *
 * @param {Object} entry
 * @param {string} eventType
 * @returns {Promise<Object>}
 */
async function ingestAndReconcile(entry, eventType) {
    ingestQueueEntry(entry, eventType);
    await reconcile();
    return entry;
}


/* ==========================================================================
   DATA LOADING
   ========================================================================== */

/**
 * Load the list of available departments.
 *
 * This is a read operation. No reconciliation is needed.
 * Backend RBAC may filter the department list based on role/permissions.
 */
export async function loadDepartments() {
    assertStaffContext();

    return getDepartments();
}


/* ==========================================================================
   QUEUE ACTIONS
   ========================================================================== */

/**
 * Call the next patient in the current department.
 *
 * The frontend never chooses the next patient itself.
 * QueueService determines priority and arrival order.
 */
export async function callNextPatient() {
    assertActionContext(ACTION.CALL, true);

    const nextEntry = await getNextPatient(
        staffContext.departmentId
    );

    if (!nextEntry) {
        throw createActionError(
            "No waiting patients in the queue.",
            409
        );
    }

    const updatedEntry = await callQueueEntry(
        nextEntry.queue_entry_id
    );

    return ingestAndReconcile(
        updatedEntry,
        "TOKEN_CALLED"
    );
}


/**
 * Start service for a queue entry.
 *
 * Ownership is required because CALLED → IN_PROGRESS is a
 * staff-owned encounter transition.
 */
export async function startPatient(entryId = null) {
    assertActionContext(ACTION.START, true);

    const entry = requireTargetEntry(entryId);

    assertOwnership(entry);

    const updatedEntry = await startQueueEntry(
        entry.queue_entry_id
    );

    return ingestAndReconcile(
        updatedEntry,
        "TOKEN_SERVICE_STARTED"
    );
}


/**
 * Complete the current queue step.
 *
 * This completes the QueueEntry, not necessarily the Visit.
 * A Visit remains active if routing/another queue step follows.
 */
export async function completePatient(entryId = null) {
    assertActionContext(ACTION.COMPLETE, true);

    const entry = requireTargetEntry(entryId);

    assertOwnership(entry);

    const updatedEntry = await completeQueueEntry(
        entry.queue_entry_id
    );

    return ingestAndReconcile(
        updatedEntry,
        "TOKEN_COMPLETED"
    );
}


/**
 * Mark a patient as NO_SHOW.
 *
 * The queue entry leaves the active department queue and is represented
 * in the no-show collection.
 */
export async function markNoShowPatient(entryId = null) {
    assertActionContext(ACTION.NO_SHOW, true);

    const entry = requireTargetEntry(entryId);

    assertOwnership(entry);

    const updatedEntry = await markNoShowQueueEntry(
        entry.queue_entry_id
    );

    return ingestAndReconcile(
        updatedEntry,
        "TOKEN_NO_SHOW"
    );
}


/**
 * Requeue a specific NO_SHOW entry.
 *
 * Requeue does not operate against the active encounter because a
 * NO_SHOW entry belongs to the no-show collection.
 */
export async function requeuePatient(entryId) {
    assertActionContext(ACTION.REQUEUE, true);

    if (!entryId) {
        throw createActionError(
            "No queue entry specified.",
            404
        );
    }

    const updatedEntry = await requeueQueueEntry(entryId);

    return ingestAndReconcile(
        updatedEntry,
        "TOKEN_REQUEUED"
    );
}


/**
 * Cancel a queue step.
 *
 * Cancellation is intentionally resolved from the explicit entry
 * or active encounter, but ownership is NOT enforced here at the
 * frontend layer because cancellation policy differs from the
 * strictly staff-owned encounter transitions.
 *
 * Backend RBAC/domain rules remain authoritative.
 */
export async function cancelQueueStep(entryId = null) {
    assertActionContext(ACTION.CANCEL, true);

    const entry = requireTargetEntry(entryId);

    const updatedEntry = await cancelQueueEntry(
        entry.queue_entry_id
    );

    return ingestAndReconcile(
        updatedEntry,
        "TOKEN_CANCELLED"
    );
}


/**
 * Change queue priority / acuity.
 *
 * Backend enforces the actual role and lifecycle rules.
 * The workspace configuration mirrors the permitted roles.
 */
export async function updatePriority(entryId, priority) {
    assertActionContext(ACTION.SET_PRIORITY, true);

    if (!entryId || !priority) {
        throw createActionError(
            "Entry id and priority are required.",
            422
        );
    }

    const updatedEntry = await setQueuePriority(
        entryId,
        priority
    );

    return ingestAndReconcile(
        updatedEntry,
        "QUEUE_UPDATED"
    );
}


/* ==========================================================================
   REGISTRATION
   ========================================================================== */

/**
 * Complete registration for an existing patient.
 *
 * Registration is a patient-domain mutation rather than a queue-entry
 * lifecycle transition, so it is followed by authoritative reconciliation.
 *
 * This is the ONLY registration action UI components should call. A
 * second copy of this function — completePatientRegistration(), further
 * down this file in an earlier revision — bypassed assertActionContext()
 * entirely (no role/permission/department check) and called a
 * `refreshQueueState()` that was never defined or imported anywhere in
 * this module, which threw `ReferenceError: refreshQueueState is not
 * defined` on every real registration attempt. It has been removed
 * rather than patched, since patching it would still have left the
 * missing permission check in place. Callers (e.g.
 * reception-workspace.js) should import `completeRegistration`.
 */
export async function completeRegistration(
    patientId,
    registrationData
) {
    assertActionContext(
        ACTION.COMPLETE_REGISTRATION,
        true
    );

    if (!patientId) {
        throw createActionError(
            "Patient id is required.",
            422
        );
    }

    if (
        !registrationData ||
        typeof registrationData !== "object"
    ) {
        throw createActionError(
            "Registration data is required.",
            422
        );
    }

    const result = await apiCompletePatientRegistration(
        patientId,
        registrationData
    );

    await reconcile();

    return result;
}


/* ==========================================================================
   ROUTING
   ========================================================================== */

/**
 * Transfer a Visit to another department.
 *
 * Domain semantics:
 *
 *   source QueueEntry → COMPLETED
 *   destination QueueEntry → WAITING
 *   Visit remains ACTIVE
 *
 * Because this is a compound Visit-level operation, the backend response
 * is not treated as an ordinary queue lifecycle event. Reconciliation
 * establishes the authoritative resulting state.
 */
export async function transferToDepartment(
    visitId,
    payload
) {
    assertActionContext(
        ACTION.TRANSFER,
        true
    );

    if (!visitId) {
        throw createActionError(
            "Visit id is required.",
            422
        );
    }

    if (!payload?.target_dept_id) {
        throw createActionError(
            "Target department is required.",
            422
        );
    }

    const newEntry = await transferPatient(
        visitId,
        payload
    );

    await reconcile();

    return newEntry;
}


/**
 * Discharge a Visit from care.
 *
 * Domain semantics:
 *
 *   current QueueEntry → COMPLETED
 *   Visit → COMPLETED
 *
 * This is therefore a Visit-level compound operation and is reconciled
 * through an authoritative snapshot rather than manually constructing
 * queue events.
 */
export async function dischargeFromCare(visitId) {
    assertActionContext(
        ACTION.DISCHARGE,
        true
    );

    if (!visitId) {
        throw createActionError(
            "Visit id is required.",
            422
        );
    }

    const visit = await dischargePatient(visitId);

    await reconcile();

    return visit;
}


/* ==========================================================================
   PUBLIC POLICY EXPORTS
   ========================================================================== */

/*
 * Panels may use these helpers for rendering decisions without importing
 * staff-workspace-config.js directly.
 *
 * They remain UI policy helpers only; they do not replace backend RBAC.
 */
export {
    canPerformAction as canPerform,
    ACTION,
};