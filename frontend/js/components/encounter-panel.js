/* ==========================================================================
   HPQMS Encounter Panel
   js/encounter-panel.js

   Manages the encounter workspace display and lifecycle.

   Responsibilities:
   - Identify current staff role
   - Load appropriate workspace from registry
   - Mount/update/unmount workspace on patient change
   - Handle workspace callbacks
   - Manage state transitions

   Does NOT:
   - Call staff-api.js directly
   - Manage queue state
   - Handle authentication

   ========================================================================== */

import {
    getMyActivePatient,
    subscribe as subscribeToQueueState,
} from "../staff-queue-state.js";

import {
    getStaffContext,
} from "../staff-actions.js";

import {
    getWorkspaceModule,
    hasWorkspace,
} from "../workspace-registry.js";

import {
    WORKSPACE,
    STAFF_ROLE,
} from "../staff-workspace-config.js";

import { saveClinicalAssessment, loadDepartments } from "../staff-actions.js";

let container = null;
let workspaceModule = null;
let panelRoot = null;
let workspaceMount = null;
let unsubscribeFromQueue = null;
let currentPatient = null;


/* ==========================================================================
   PUBLIC API
   ========================================================================== */

/**
 * Initialize the encounter panel.
 *
 * @param {HTMLElement} target - Container element
 */
export function initialize(target /*, options */) {
    if (!(target instanceof HTMLElement)) {
        throw new TypeError(
            "EncounterPanel target must be an HTMLElement."
        );
    }

    container = target;
    panelRoot = container;
    workspaceMount = panelRoot;

    if (!container.querySelector("#encounterWorkspaceMount")) {
        console.info(
            "EncounterPanel: No #encounterWorkspaceMount element found — " +
            "rendering into the provided container instead."
        );
    }

    // Subscribe to queue state changes
    unsubscribeFromQueue = subscribeToQueueState(() => {
        handleQueueStateChange();
    });

    // Initial render
    handleQueueStateChange();
}


/**
 * Clean up the encounter panel.
 */
export const mount = initialize;
export const unmount = destroy;

export function destroy() {
    unmountWorkspace();

    if (unsubscribeFromQueue) {
        unsubscribeFromQueue();
        unsubscribeFromQueue = null;
    }

    container = null;
    panelRoot = null;
    workspaceMount = null;
}


/* ==========================================================================
   STATE MANAGEMENT
   ========================================================================== */

/**
 * Called whenever queue state changes.
 * Determines if we need to mount a new workspace or update the current one.
 */
function handleQueueStateChange() {
    const patient = getMyActivePatient();

    // Check if patient changed
    if (patient?.queue_entry_id !== currentPatient?.queue_entry_id) {
        currentPatient = patient;

        // Patient changed (or patient became null)
        if (!patient) {
            unmountWorkspace();
            renderNoPatient();
            return;
        }

        // New patient: mount fresh workspace
        mountWorkspace(patient);
        return;
    }

    // Same patient: refresh the common summary + workspace update()
    if (patient) {
        updateEncounterSummary(patient);

        if (workspaceModule?.update) {
            workspaceModule.update(workspaceMount, { patient });
        }
    }
}


/* ==========================================================================
   WORKSPACE LIFECYCLE
   ========================================================================== */

/**
 * Mount the appropriate workspace for the current staff role.
 *
 * @param {Object} patient - The active patient
 */
// Ensure these are imported at the top of encounter-panel.js:


function mountWorkspace(patient) {
    const staffContext = getStaffContext();

    if (!staffContext.role) {
        renderError("Staff role not available.");
        return;
    }

    // Determine which workspace to use
    const workspaceKey = roleToWorkspaceKey(staffContext.role);

    if (!workspaceKey) {
        renderError(`No workspace found for role: ${staffContext.role}`);
        return;
    }

    if (!hasWorkspace(workspaceKey)) {
        renderError(`Workspace not registered: ${workspaceKey}`);
        return;
    }

    // Get the workspace module from the registry
    workspaceModule = getWorkspaceModule(workspaceKey);

    if (!workspaceModule?.mount) {
        renderError(
            `Workspace module does not have mount() function: ${workspaceKey}`
        );
        return;
    }

    // Render the shared encounter shell (header + patient summary),
    // then mount the role workspace into the inner mount point.
    renderEncounterShell(patient);

    try {
        // Mount the workspace with complete callbacks
        workspaceModule.mount(workspaceMount, {
            // D3.9 Clinical Documentation Persistence Callback
            onSaveClinicalAssessment: async (visitId, assessmentPayload) => {
                return await saveClinicalAssessment(visitId, assessmentPayload);
            },

            // D3.9 Department Drawer Callback
            onLoadDepartments: async () => {
                return await loadDepartments();
            },

            onRegistrationCompleted: async () => {
                // Called after registration is completed in Reception workspace
                console.log("Registration completed");
            },

            onPriorityChanged: async (newPriority) => {
                // Called when priority changes in Triage workspace
                console.log("Priority changed to:", newPriority);
            },

            onRetakeVitals: async () => {
                // Called when vitals are retaken in Triage workspace
                console.log("Vitals retake requested");
            },

            onActionCompleted: async () => {
                // Called after any workflow action completes
                // (route, discharge, no-show, complete, cancel, etc.)
                console.log("Action completed, refreshing state...");
            },
        });

    } catch (error) {
        console.error(`Error mounting workspace (${workspaceKey}):`, error);
        renderError(`Failed to load workspace: ${error.message}`);
    }
}


/**
 * Unmount the current workspace.
 */
function unmountWorkspace() {
    if (workspaceModule?.unmount) {
        try {
            workspaceModule.unmount();
        } catch (error) {
            console.error("Error unmounting workspace:", error);
        }
    }

    workspaceModule = null;

    if (panelRoot) {
        panelRoot.innerHTML = "";
    }

    workspaceMount = panelRoot;
}


/* ==========================================================================
   ENCOUNTER SHELL (shared header + patient summary)
   ========================================================================== */

/*
 * Restores the common "Active Encounter Workspace" header and the
 * patient summary strip (DOB/Age, Gender, Visit ID). These used to
 * be rendered by this panel for every role; they were dropped during
 * the workspace-registry refactor, which removed them from BOTH the
 * receptionist and triage encounter views.
 */
function renderEncounterShell(patient) {
    const details = getPatientDetails(patient);

    panelRoot.innerHTML = `
        <section class="encounter-panel encounter-active">

            <header class="encounter-panel-header">
                <div class="encounter-header-main">
                    <h2>
                        Active Encounter Workspace
                        <span
                            class="encounter-focus"
                            data-encounter-token>
                            ${escapeHtml(getToken(patient))}
                        </span>
                    </h2>
                    <h3
                        class="encounter-patient-name"
                        data-encounter-patient-name>
                        ${escapeHtml(getPatientName(patient))}
                    </h3>
                </div>
                <span
                    class="priority-badge ${getPriorityClass(patient)}"
                    data-encounter-priority>
                    ${escapeHtml(getPriorityLabel(patient))}
                </span>
            </header>

            <section class="patient-summary">
                <div class="patient-summary-item">
                    <span>DOB/Age</span>
                    <strong data-encounter-dob>
                        ${escapeHtml(getDobOrAge(patient))}
                    </strong>
                </div>
                <div class="patient-summary-item">
                    <span>Gender</span>
                    <strong data-encounter-gender>
                        ${escapeHtml(details.gender ?? "—")}
                    </strong>
                </div>
                <div class="patient-summary-item">
                    <span>Visit ID</span>
                    <strong
                        data-encounter-visit-id
                        title="${escapeHtml(
                            patient.visit?.visit_id ??
                            patient.visit_id ??
                            ""
                        )}">
                        ${escapeHtml(
                            patient.visit?.visit_id ??
                            patient.visit_id ??
                            "—"
                        )}
                    </strong>
                </div>
            </section>

            <section
                id="encounterWorkspaceMount"
                class="encounter-workspace"
                aria-live="polite">
            </section>

        </section>
    `;

    workspaceMount =
        panelRoot.querySelector("#encounterWorkspaceMount") || panelRoot;
}


function updateEncounterSummary(patient) {
    if (!panelRoot) return;

    const details = getPatientDetails(patient);

    const tokenElement = panelRoot.querySelector("[data-encounter-token]");
    const nameElement = panelRoot.querySelector("[data-encounter-patient-name]");
    const priorityElement = panelRoot.querySelector("[data-encounter-priority]");
    const dobElement = panelRoot.querySelector("[data-encounter-dob]");
    const genderElement = panelRoot.querySelector("[data-encounter-gender]");
    const visitIdElement = panelRoot.querySelector("[data-encounter-visit-id]");

    if (tokenElement) tokenElement.textContent = getToken(patient);
    if (nameElement) nameElement.textContent = getPatientName(patient);
    if (priorityElement) {
        priorityElement.textContent = getPriorityLabel(patient);
        priorityElement.className = `priority-badge ${getPriorityClass(patient)}`;
    }
    if (dobElement) dobElement.textContent = getDobOrAge(patient);
    if (genderElement) genderElement.textContent = details.gender ?? "—";
    if (visitIdElement) {
        visitIdElement.textContent =
            patient.visit?.visit_id ?? patient.visit_id ?? "—";
    }
}


/* ==========================================================================
   PATIENT DISPLAY HELPERS
   ========================================================================== */

function getPatientDetails(patient) {
    return patient?.visit?.patient || patient?.patient || patient || {};
}

function getToken(patient) {
    return (
        patient?.visit?.token_number ??
        patient?.token_number ??
        patient?.token ??
        "—"
    );
}

function getPatientName(patient) {
    const details = getPatientDetails(patient);
    const explicitName = patient?.patient_name ?? details?.patient_name;

    if (explicitName) {
        return explicitName;
    }

    return [
        details?.first_name,
        details?.last_name,
    ]
        .filter(Boolean)
        .join(" ")
        .trim() || "Patient";
}

function getDobOrAge(patient) {
    const details = getPatientDetails(patient);

    if (details?.date_of_birth) {
        return details.date_of_birth;
    }

    if (details?.estimated_age !== undefined && details?.estimated_age !== null) {
        return `${details.estimated_age} years`;
    }

    return "—";
}

function getPriorityLabel(patient) {
    return patient?.priority ?? "NORMAL";
}

function getPriorityClass(patient) {
    return `priority-${String(patient?.priority ?? "NORMAL").toLowerCase()}`;
}


/* ==========================================================================
   ROLE TO WORKSPACE MAPPING
   ========================================================================== */

/**
 * Map staff role to workspace key.
 *
 * @param {string} role - Staff role (from staff context)
 * @returns {string|null} - Workspace key or null if no mapping
 */
function roleToWorkspaceKey(role) {
    const roleToWorkspaceMap = {
        [STAFF_ROLE.RECEPTIONIST]: WORKSPACE.RECEPTION,
        [STAFF_ROLE.TRIAGE_NURSE]: WORKSPACE.TRIAGE,
        [STAFF_ROLE.DOCTOR]: WORKSPACE.DOCTOR,
        [STAFF_ROLE.NURSE]: WORKSPACE.DOCTOR,   // Same workspace as doctor (extensible)
        [STAFF_ROLE.ADMIN]: WORKSPACE.ADMIN,
    };

    return roleToWorkspaceMap[role] ?? null;
}


/* ==========================================================================
   RENDERING HELPERS
   ========================================================================== */

/**
 * Render "no patient" state.
 */
function renderNoPatient() {
    if (!workspaceMount) {
        return;
    }

    workspaceMount.innerHTML = `
        <div style="
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100%;
            gap: 1rem;
            color: #64748b;
            text-align: center;
            padding: 2rem;
        ">
            <div style="
                width: 48px;
                height: 48px;
                border-radius: 50%;
                background: #f1f5f9;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 24px;
            ">
                +
            </div>
            <h3 style="margin: 0; font-size: 16px; color: #1a1a1a;">
                No Active Patient
            </h3>
            <p style="margin: 0; font-size: 13px;">
                Call and start a patient to begin.
            </p>
        </div>
    `;
}


/**
 * Render error state.
 *
 * @param {string} message - Error message
 */
function renderError(message) {
    if (!workspaceMount) {
        return;
    }

    workspaceMount.innerHTML = `
        <div style="
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100%;
            gap: 1rem;
            color: #991b1b;
            text-align: center;
            padding: 2rem;
        ">
            <div style="
                width: 48px;
                height: 48px;
                border-radius: 50%;
                background: #fee2e2;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 24px;
                color: #991b1b;
            ">
                !
            </div>
            <h3 style="margin: 0; font-size: 16px; color: #991b1b;">
                Error Loading Workspace
            </h3>
            <p style="margin: 0; font-size: 13px; color: #64748b;">
                ${escapeHtml(message)}
            </p>
        </div>
    `;
}


/* ==========================================================================
   SECURITY
   ========================================================================== */

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}