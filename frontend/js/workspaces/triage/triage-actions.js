/* ==========================================================================
   HPQMS Triage Workspace Actions
   workspaces/triage/triage-actions.js

   Triage-specific intent layer.

   This file:
   - hides Triage-only business rules from the UI
   - does NOT manipulate the DOM
   - does NOT manage application state directly
   - calls staff-actions.js, not staff-api.js directly
   ========================================================================== */

import {
    transferToDepartment,
    loadDepartments,
    recordVitals,
    saveTriageAssessment,
} from "../../staff-actions.js";


/* ==========================================================================
   DATA LOADING
   ========================================================================== */

/**
 * Loads the list of available departments for patient transfer/routing.
 */
export async function getDepartments() {
    return loadDepartments();
}


/* ==========================================================================
   VITALS & ASSESSMENT INTENTS
   ========================================================================== */

/**
 * Records patient vital signs.
 *
 * @param {string|number} visitId
 * @param {Object} vitalsData - Flat vitals payload: { systolic_bp, diastolic_bp, heart_rate, temperature, oxygen_saturation, respiratory_rate, weight }
 */
export async function recordPatientVitals(visitId, vitalsData) {
    return recordVitals(visitId, vitalsData);
}

/**
 * Persists triage clinical assessment notes.
 *
 * @param {string|number} visitId
 * @param {Object} assessmentData - { chief_complaint, triage_assessment }
 */
export async function updateAssessment(visitId, { chief_complaint, triage_assessment }) {
    return saveTriageAssessment(visitId, {
        chief_complaint,
        triage_assessment,
    });
}


/* ==========================================================================
   ROUTING
   ========================================================================== */

/**
 * Route/transfer a patient from Triage to a target department.
 *
 * @param {string|number} visitId
 * @param {string|number} targetDeptId
 * @param {Object} options
 * @param {string} [options.priority="NORMAL"] - QueuePriority enum: CRITICAL, URGENT, SEMI_URGENT, NORMAL
 * @param {string|null} [options.notes=null]
 */
export async function routePatient(
    visitId,
    targetDeptId,
    {
        priority = "NORMAL",
        notes = null,
    } = {}
) {
    return transferToDepartment(visitId, {
        target_dept_id: targetDeptId,
        reason: "DEPARTMENT_TRANSFER",
        priority,
        notes,
    });
}
