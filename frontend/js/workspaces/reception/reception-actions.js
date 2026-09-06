/* ==========================================================================
   HPQMS Reception Workspace Actions
   workspaces/reception/reception-actions.js

   Reception-specific intent layer.

   This file:
   - hides Reception-only business rules (e.g. DIRECT_ROUTING) from the UI
   - does NOT manipulate the DOM
   - does NOT manage application state directly

   IMPORTANT: this file calls staff-actions.js, not staff-api.js.
   staff-actions.js is the only module permitted to call staff-api.js —
   it's what applies role/permission checks, ownership checks, and feeds
   successful mutations into staff-queue-state via reconcile(). An
   earlier version of this file called completeQueueEntry/
   cancelQueueEntry/transferPatient from staff-api.js directly, which
   skipped all of that: no permission check, no ownership check, and —
   most visibly — no reconciliation, so the queue state never learned a
   mutation had happened and the UI stayed stale after every action.
   ========================================================================== */

import {
    completePatient,
    cancelQueueStep,
    transferToDepartment,
    loadDepartments,
    getStaffContext,
    ACTION,
    canPerform as canPerformAction,
} from "../../staff-actions.js";


/* ==========================================================================
   CLINICAL PRIORITY AUTHORITY
   ========================================================================== */

/*
 * "Reception routes patients. Clinical staff determine clinical urgency."
 *
 * Only roles whose workspace config grants SET_PRIORITY may choose a
 * priority in the transfer drawer. Reception sees the current priority
 * as read-only and the transfer preserves it (priority omitted → the
 * backend carries it over to the new queue entry).
 */
function canSetPriority() {
    const { role } = getStaffContext();
    return canPerformAction(role, ACTION.SET_PRIORITY);
}


/* ==========================================================================
   DATA LOADING
   ========================================================================== */

/**
 * Loads the list of available departments for routing.
 *
 * Goes through staff-actions.js so it respects any role-based
 * department visibility rules.
 */
export async function getDepartments() {
    return loadDepartments();
}


/* ==========================================================================
   ROUTING
   ========================================================================== */

/**
 * Routes a Reception encounter to another department.
 *
 * Reception always uses DIRECT_ROUTING — that's a Reception business
 * rule, so it's fixed here rather than left for the UI to specify.
 */
export async function routePatient(
    visitId,
    targetDeptId,
    {
        priority = null,
        notes = null,
    } = {}
) {
    /*
     * priority === null → omitted from the payload → the backend
     * preserves the patient's existing priority. Only clinical roles
     * ever send an explicit priority.
     */
    const payload = {
        target_dept_id: targetDeptId,
        reason: "DIRECT_ROUTING",
        notes,
    };

    if (priority) {
        payload.priority = priority;
    }

    return transferToDepartment(visitId, payload);
}


/* ==========================================================================
   ENCOUNTER ACTIONS
   ========================================================================== */

/**
 * Completes the current Reception queue entry.
 *
 * IMPORTANT:
 * This does NOT complete the Visit.
 * It only closes the Reception queue entry and updates the queue state.
 */
export async function completeReceptionEncounter(queueEntryId) {
    return completePatient(queueEntryId);
}


/**
 * Cancels the current Reception queue entry.
 */
export async function cancelReceptionEncounter(queueEntryId) {
    return cancelQueueStep(queueEntryId);
}