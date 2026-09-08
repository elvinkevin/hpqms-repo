 /*HPQMS Staff Dashboard API Helpers
   js/staff-api.js
   --------------------------------------------------------------------------
   Responsibility:
     - Provide typed/convenient wrappers around Staff Dashboard API endpoints.
     - Attach the current authentication token to protected requests.
     - Cache the authenticated staff profile for the current application
       lifetime.

   Does NOT:
     - Persist authentication sessions.
     - Render UI.
     - Manage queue state.
     - Manage WebSockets.
     - Determine workspace permissions.

   Authentication persistence is handled by:
       staff-session.js

   UI action policy is handled by:
       staff-workspace-config.js

   Queue state is handled by:
       staff-queue-state.js

   Staff intent/actions are handled by:
       staff-actions.js

   Backend RBAC remains the final authority.
   ========================================================================== */

import { request, HTTP_METHOD } from "./api.js";

import {
    getAccessToken,
    saveSession,
    clearSession,
} from "./staff-session.js";


/* ==========================================================================
   APPLICATION AUTH STATE
   ========================================================================== */

/*
 * The access token itself is NOT stored here.
 *
 * staff-session.js is the source of truth for authentication persistence.
 *
 * This object only caches the /auth/me response for the current page
 * lifetime so other modules can retrieve the authenticated staff profile
 * without repeatedly calling the endpoint.
 */
let currentUser = null;


/* ==========================================================================
   AUTHENTICATION HEADERS
   ========================================================================== */

/**
 * Build headers for authenticated API requests.
 *
 * The token is retrieved from staff-session.js every time rather than
 * relying on a stale in-memory token.
 *
 * This is important after a page reload or redirect.
 */
function buildAuthHeaders() {
    const accessToken = getAccessToken();

    if (!accessToken) {
        return {};
    }

    return {
        Authorization: `Bearer ${accessToken}`,
    };
}


/* ==========================================================================
   AUTHENTICATION
   ========================================================================== */

/**
 * Authenticate a staff member.
 *
 * Backend contract:
 *
 * POST /auth/login
 *
 * {
 *     employee_id: string,
 *     password: string
 * }
 *
 * @param {{employee_id: string, password: string}} credentials
 * @param {boolean} rememberMe
 * @returns {Promise<object>}
 */
async function login(credentials, rememberMe = false) {
    const response = await request("/auth/login", {
        method: HTTP_METHOD.POST,
        body: credentials,
    });

    /*
     * The backend returns the access token.
     *
     * Persistence is delegated to staff-session.js.
     */
    if (!response?.access_token) {
        throw new Error(
            "Authentication succeeded but no access token was returned."
        );
    }

    saveSession(
        response.access_token,
        rememberMe
    );

    return response;
}


/**
 * Retrieve the authenticated staff profile.
 *
 * GET /auth/me
 */
async function getCurrentUser() {
    const response = await request("/auth/me", {
        method: HTTP_METHOD.GET,
        headers: buildAuthHeaders(),
    });

    currentUser = response;

    return response;
}


/**
 * Return the cached authenticated staff profile.
 *
 * This does NOT make an API request.
 */
function getCachedCurrentUser() {
    return currentUser;
}


/**
 * Clear authentication state.
 *
 * Token persistence is cleared through staff-session.js.
 */
function logout() {
    clearSession();
    currentUser = null;
}


/* ==========================================================================
   DEPARTMENTS
   ========================================================================== */

/**
 * Get all active hospital departments.
 *
 * GET /departments/active
 */
async function getDepartments() {
    return request("/departments/active", {
        method: HTTP_METHOD.GET,
        headers: buildAuthHeaders(),
    });
}


/* ==========================================================================
   QUEUE — READ
   ========================================================================== */

/**
 * Get the active queue for a department.
 *
 * GET /queue/department/{department_id}
 */
async function getDepartmentQueue(departmentId) {
    return request(`/queue/department/${departmentId}`, {
        method: HTTP_METHOD.GET,
        headers: buildAuthHeaders(),
    });
}


/**
 * Get the department's no-show queue.
 *
 * GET /queue/department/{department_id}/no-show
 */
async function getDepartmentNoShowQueue(departmentId) {
    return request(`/queue/department/${departmentId}/no-show`, {
        method: HTTP_METHOD.GET,
        headers: buildAuthHeaders(),
    });
}


/**
 * Get the next patient according to backend queue ordering.
 *
 * The backend determines:
 *   CRITICAL > URGENT > SEMI_URGENT > NORMAL
 *
 * and then arrival/sequence ordering within the same priority.
 *
 * GET /queue/department/{department_id}/next
 */
async function getNextPatient(departmentId) {
    return request(`/queue/department/${departmentId}/next`, {
        method: HTTP_METHOD.GET,
        headers: buildAuthHeaders(),
    });
}


/**
 * Get one queue entry.
 *
 * GET /queue/entry/{queue_entry_id}
 */
async function getQueueEntry(queueEntryId) {
    return request(`/queue/entry/${queueEntryId}`, {
        method: HTTP_METHOD.GET,
        headers: buildAuthHeaders(),
    });
}


/**
 * Get all queue entries belonging to a Visit.
 *
 * GET /queue/visit/{visit_id}
 */
async function getVisitQueue(visitId) {
    return request(`/queue/visit/${visitId}`, {
        method: HTTP_METHOD.GET,
        headers: buildAuthHeaders(),
    });
}


/* ==========================================================================
   QUEUE — STATUS ACTIONS
   ========================================================================== */

/**
 * Call a queue entry.
 *
 * PATCH /queue/{queue_entry_id}/call
 */
async function callQueueEntry(queueEntryId) {
    return request(`/queue/${queueEntryId}/call`, {
        method: HTTP_METHOD.PATCH,
        headers: buildAuthHeaders(),
    });
}


/**
 * Start service for a queue entry.
 *
 * PATCH /queue/{queue_entry_id}/start
 */
async function startQueueEntry(queueEntryId) {
    return request(`/queue/${queueEntryId}/start`, {
        method: HTTP_METHOD.PATCH,
        headers: buildAuthHeaders(),
    });
}


/**
 * Complete service for a queue entry.
 *
 * PATCH /queue/{queue_entry_id}/complete
 */
async function completeQueueEntry(queueEntryId) {
    return request(`/queue/${queueEntryId}/complete`, {
        method: HTTP_METHOD.PATCH,
        headers: buildAuthHeaders(),
    });
}


/**
 * Mark a queue entry as no-show.
 *
 * PATCH /queue/{queue_entry_id}/no-show
 */
async function markNoShowQueueEntry(queueEntryId) {
    return request(`/queue/${queueEntryId}/no-show`, {
        method: HTTP_METHOD.PATCH,
        headers: buildAuthHeaders(),
    });
}


/**
 * Requeue a no-show patient.
 *
 * PATCH /queue/{queue_entry_id}/requeue
 */
async function requeueQueueEntry(queueEntryId) {
    return request(`/queue/${queueEntryId}/requeue`, {
        method: HTTP_METHOD.PATCH,
        headers: buildAuthHeaders(),
    });
}


/**
 * Cancel the current queue step.
 *
 * PATCH /queue/{queue_entry_id}/cancel
 */
async function cancelQueueEntry(queueEntryId) {
    return request(`/queue/${queueEntryId}/cancel`, {
        method: HTTP_METHOD.PATCH,
        headers: buildAuthHeaders(),
    });
}


/**
 * Change queue priority.
 *
 * PATCH /queue/{queue_entry_id}/priority
 *
 * Body:
 * {
 *     priority: "NORMAL" | "SEMI_URGENT" | "URGENT" | "CRITICAL"
 * }
 *
 * NOTE: this is QueueEntry-level ordering priority, not the clinical
 * triage acuity recorded on the Visit via updateTriageAssessment()
 * below. Whether the two actually share one enum on the backend or are
 * tracked independently hasn't been confirmed — don't assume they're
 * interchangeable.
 */
async function setQueuePriority(queueEntryId, priority) {
    return request(`/queue/${queueEntryId}/priority`, {
        method: HTTP_METHOD.PATCH,
        headers: buildAuthHeaders(),
        body: {
            priority,
        },
    });
}


/* ==========================================================================
   PATIENT / REGISTRATION
   ========================================================================== */

/**
 * Complete registration for a patient.
 *
 * PATCH /patients/{patient_id}/complete-registration
 */
async function completePatientRegistration(patientId, data) {
    return request(
        `/patients/${patientId}/complete-registration`,
        {
            method: HTTP_METHOD.PATCH,
            headers: buildAuthHeaders(),
            body: data,
        }
    );
}


/* ==========================================================================
   ROUTING
   ========================================================================== */

/**
 * Transfer a Visit to another department.
 *
 * POST /routing/{visit_id}/transfer
 *
 * The backend:
 *   - completes the source QueueEntry
 *   - creates the destination QueueEntry
 *   - keeps the Visit ACTIVE
 */
async function transferPatient(visitId, payload) {
    return request(`/routing/${visitId}/transfer`, {
        method: HTTP_METHOD.POST,
        headers: buildAuthHeaders(),
        body: payload,
    });
}


/**
 * Discharge a patient.
 *
 * POST /routing/{visit_id}/discharge
 *
 * The backend:
 *   - completes the active QueueEntry
 *   - completes the Visit
 */
async function dischargePatient(visitId) {
    return request(`/routing/${visitId}/discharge`, {
        method: HTTP_METHOD.POST,
        headers: buildAuthHeaders(),
    });
}


/**
 * Get the patient's current Visit location.
 *
 * GET /routing/location/{visit_id}
 */
async function getCurrentLocation(visitId) {
    return request(`/routing/location/${visitId}`, {
        method: HTTP_METHOD.GET,
        headers: buildAuthHeaders(),
    });
}


/**
 * Get patient movement/routing history.
 *
 * GET /routing/history/{visit_id}
 */
async function getPatientHistory(visitId) {
    return request(`/routing/history/${visitId}`, {
        method: HTTP_METHOD.GET,
        headers: buildAuthHeaders(),
    });
}


/* ==========================================================================
   VISITS
   ========================================================================== */

/**
 * Explicitly complete a Visit.
 *
 * PATCH /visits/{visit_id}/complete
 *
 * Normally dischargePatient() should be preferred for clinical discharge
 * because RoutingService handles the active QueueEntry and Visit together.
 */
async function completeVisit(visitId) {
    return request(`/visits/${visitId}/complete`, {
        method: HTTP_METHOD.PATCH,
        headers: buildAuthHeaders(),
    });
}


/* ==========================================================================
   VITALS & TRIAGE ASSESSMENT
   --------------------------------------------------------------------------
   These previously used raw fetch() + localStorage.getItem('token')
   directly, bypassing buildAuthHeaders()/staff-session.js — if the
   session token isn't literally stored under the key 'token' (that's
   staff-session.js's business, not this file's), every call silently
   sent "Authorization: Bearer null" and would 401. They also hit
   `/api/visits/...`, but nothing else in this file uses an `/api`
   prefix — completeVisit() above already correctly calls
   `/visits/${visitId}/complete`, confirming the real path is
   `/visits/{visit_id}/...`, not `/api/visits/{visit_id}/...`. Rewritten
   to match this file's own request()/buildAuthHeaders() convention.
   ========================================================================== */

/**
 * Record a new vitals entry for a visit.
 *
 * POST /visits/{visit_id}/vitals
 *
 * Body fields mirror the Vitals ORM model directly (all optional):
 * { temperature, systolic_bp, diastolic_bp, heart_rate,
 *   respiratory_rate, oxygen_saturation, weight, height }
 *
 * Note: systolic_bp/diastolic_bp are flat top-level fields on the
 * backend, not a nested blood_pressure object.
 */
async function recordVitals(visitId, vitalsPayload) {
    return request(`/visits/${visitId}/vitals`, {
        method: HTTP_METHOD.POST,
        headers: buildAuthHeaders(),
        body: vitalsPayload,
    });
}


/**
 * Get the most recently recorded vitals for a visit (or null/None if
 * none have been recorded yet).
 *
 * GET /visits/{visit_id}/vitals/latest
 */
async function getLatestVitals(visitId) {
    return request(`/visits/${visitId}/vitals/latest`, {
        method: HTTP_METHOD.GET,
        headers: buildAuthHeaders(),
    });
}


/**
 * Get all vitals entries recorded for a visit, most recent first.
 *
 * GET /visits/{visit_id}/vitals
 */
async function getAllVitals(visitId) {
    return request(`/visits/${visitId}/vitals`, {
        method: HTTP_METHOD.GET,
        headers: buildAuthHeaders(),
    });
}


/**
 * Update chief complaint and/or triage assessment notes for
 * a visit. Supports partial updates — only send the fields you want to
 * change.
 *
 * PATCH /visits/{visit_id}/triage-assessment
 *
 * The response (VisitRead) includes latest_vitals for clinical context
 * — if vitals were just recorded via recordVitals() first, this
 * response will reflect them.
 *
 * UNCONFIRMED: exact field names on TriageAssessmentUpdate weren't
 * available — { chief_complaint, assessment, priority } is inferred
 * from the endpoint's docstring wording. Verify against the actual
 * Pydantic schema and correct if it doesn't match (in particular the
 * assessment-text field name).
 */
async function updateTriageAssessment(visitId, assessmentPayload) {
    return request(`/visits/${visitId}/triage-assessment`, {
        method: HTTP_METHOD.PATCH,
        headers: buildAuthHeaders(),
        body: assessmentPayload,
    });
}


/**
 * Fetch a hydrated visit record.
 *
 * GET /visits/{visit_id}
 *
 * UNCONFIRMED: this endpoint wasn't in the router shown — kept as a
 * best guess matching the /visits/{visit_id}/... pattern used above.
 * Remove or correct if it doesn't actually exist.
 */
// async function getVisitDetails(visitId) {
//     return request(`/visits/${visitId}`, {
//         method: HTTP_METHOD.GET,
//         headers: buildAuthHeaders(),
//     });
// }


/* ==========================================================================
   EXPORTS
   ========================================================================== */

export {
    /* Authentication */
    login,
    logout,
    getCurrentUser,
    getCachedCurrentUser,

    /* Departments */
    getDepartments,

    /* Queue — Read */
    getDepartmentQueue,
    getDepartmentNoShowQueue,
    getNextPatient,
    getQueueEntry,
    getVisitQueue,

    /* Queue — Actions */
    callQueueEntry,
    startQueueEntry,
    completeQueueEntry,
    markNoShowQueueEntry,
    requeueQueueEntry,
    cancelQueueEntry,
    setQueuePriority,

    /* Patient */
    completePatientRegistration,

    /* Routing */
    transferPatient,
    dischargePatient,
    getCurrentLocation,
    getPatientHistory,

    /* Visits */
    completeVisit,
    // getVisitDetails,

    /* Vitals & Triage Assessment */
    recordVitals,
    getLatestVitals,
    getAllVitals,
    updateTriageAssessment,
};
