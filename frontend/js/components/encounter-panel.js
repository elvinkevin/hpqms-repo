/* ==========================================================================
   HPQMS Staff Dashboard — Encounter Panel
   components/encounter-panel.js

   Owns the common active-encounter presentation.

   It does NOT:
   - call the API
   - perform staff actions
   - implement clinical workflows
   - own queue state

   It consumes staff-queue-state and mounts the appropriate role workspace.
   ========================================================================== */

import {
    subscribe,
    getMyActivePatient,
} from "../staff-queue-state.js";

import {
    getWorkspaceModule,
} from "../workspace-registry.js";


import {
    getWorkspaceForRole,
} from "../staff-workspace-config.js";

/* ==========================================================================
   MODULE STATE
   ========================================================================== */

let container = null;
let unsubscribe = null;

let workspaceKey = null;
let workspaceModule = null;

let activePatientId = null;
let emptyStateVisible = false;


/* ==========================================================================
   PUBLIC API
   ========================================================================== */

/**
 * Mount the encounter panel.
 *
 * @param {HTMLElement} target
 * @param {Object} options
 * @param {string} options.workspace
 */
export function mount(target, options = {}) {
    if (!(target instanceof HTMLElement)) {
        throw new TypeError(
            "EncounterPanel mount target must be an HTMLElement."
        );
    }

    unmount();

    container = target;
    workspaceKey = options.workspace ?? null;
    activePatientId = null;
    emptyStateVisible = false;

    unsubscribe = subscribe(() => {
        handleStateChange();
    });

    handleStateChange();
}


/**
 * Unmount the entire encounter panel.
 */
export function unmount() {
    if (unsubscribe) {
        unsubscribe();
        unsubscribe = null;
    }

    destroyWorkspace();

    if (container) {
        container.innerHTML = "";
    }

    container = null;
    workspaceKey = null;
    activePatientId = null;
    emptyStateVisible = false;
}


/**
 * Change the active workspace without rebuilding the shell.
 *
 * Useful if the staff context changes.
 */
export function setWorkspace(nextWorkspaceKey) {
    if (workspaceKey === nextWorkspaceKey) {
        return;
    }

    workspaceKey = nextWorkspaceKey;

    const patient = getMyActivePatient();

    if (!patient) {
        activePatientId = null;
        renderEmptyState();
        return;
    }

    /*
     * Workspace changed while the same patient remains active.
     * Rebuild the role-specific workspace only.
     */
    renderEncounter(patient);
}


/**
 * Render the current encounter state.
 */
export function render() {
    handleStateChange();
}


/* ==========================================================================
   STATE CHANGE HANDLING
   ========================================================================== */

function handleStateChange() {
    if (!container) {
        return;
    }

    const patient = getMyActivePatient();

    if (!patient) {
        /*
         * Render the empty state whenever it is not already on
         * screen. This includes the very first state change after
         * mount — otherwise the panel stays completely blank for
         * any role that has not started a patient yet.
         */
        if (activePatientId !== null || workspaceModule || !emptyStateVisible) {
            activePatientId = null;
            renderEmptyState();
        }

        return;
    }

    const patientIdentity = getPatientIdentity(patient);

    /*
     * Same patient:
     *
     * Do NOT destroy/recreate the workspace.
     *
     * This protects unsaved form input inside Reception/Triage/Doctor
     * workspaces.
     */
    if (activePatientId === patientIdentity) {
        updateEncounter(patient);
        return;
    }

    /*
     * Different patient:
     * rebuild the encounter workspace.
     */
    activePatientId = patientIdentity;

    renderEncounter(patient);
}


/* ==========================================================================
   EMPTY STATE
   ========================================================================== */

function renderEmptyState() {
    destroyWorkspace();

    emptyStateVisible = true;

    if (!container) {
        return;
    }

    container.innerHTML = `
        <section class="encounter-panel encounter-empty">

            <header class="encounter-panel-header">
                <h2>Active Encounter Workspace</h2>
            </header>

            <div class="encounter-empty-content">

                <div
                    class="encounter-empty-icon"
                    aria-hidden="true">

                </div>

                <h3>No Active Patient</h3>

                <p>
                    Call and start a patient to begin an active encounter.
                </p>

            </div>

        </section>
    `;
}


/* ==========================================================================
   ACTIVE ENCOUNTER
   ========================================================================== */

function renderEncounter(patient) {
    destroyWorkspace();

    emptyStateVisible = false;

    if (!container) {
        return;
    }

    const details =
        patient.visit?.patient ||
        patient.patient ||
        patient;

    container.innerHTML = `
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

    mountWorkspace(patient);
}


/* ==========================================================================
   COMMON ENCOUNTER UPDATE
   ========================================================================== */

function updateEncounter(patient) {
    if (!container) {
        return;
    }

    const details =
        patient.visit?.patient ||
        patient.patient ||
        patient;

    const tokenElement =
        container.querySelector("[data-encounter-token]");

    const nameElement =
        container.querySelector("[data-encounter-patient-name]");

    const priorityElement =
        container.querySelector("[data-encounter-priority]");

    const dobElement =
        container.querySelector("[data-encounter-dob]");

    const genderElement =
        container.querySelector("[data-encounter-gender]");

    const visitIdElement =
        container.querySelector("[data-encounter-visit-id]");


    if (tokenElement) {
        tokenElement.textContent = getToken(patient);
    }

    if (nameElement) {
        nameElement.textContent = getPatientName(patient);
    }

    if (priorityElement) {
        priorityElement.textContent =
            getPriorityLabel(patient);

        priorityElement.className =
            `priority-badge ${getPriorityClass(patient)}`;
    }

    if (dobElement) {
        dobElement.textContent =
            getDobOrAge(patient);
    }

    if (genderElement) {
        genderElement.textContent =
            details.gender ?? "—";
    }

    if (visitIdElement) {
        visitIdElement.textContent =
            patient.visit?.visit_id ??
            patient.visit_id ??
            "—";
    }


    /*
     * Give the mounted workspace a chance to react to state changes
     * without destroying its DOM.
     */
    if (
        workspaceModule &&
        typeof workspaceModule.update === "function"
    ) {
        workspaceModule.update(
            container.querySelector("#encounterWorkspaceMount"),
            {
                patient,
            }
        );
    }
}


/* ==========================================================================
   WORKSPACE MOUNTING
   ========================================================================== */

function resolveWorkspace(role) {
    /*
     * Prefer the workspace key assigned to the logged-in staff
     * member at panel mount time. The active patient does not
     * carry a staff role, so role-based resolution is only a
     * fallback (and returns null for real patients).
     */
    const key =
        workspaceKey ??
        (role ? getWorkspaceForRole(role) : null);

    if (!key) {
        return null;
    }

    return getWorkspaceModule(key);
}


async function mountWorkspace(patient) {
    const workspaceMount = container?.querySelector(
        "#encounterWorkspaceMount"
    );

    if (!workspaceMount) {
        return;
    }

    const role =
        patient?.staff_role ??
        patient?.role ??
        null;

    const workspace = resolveWorkspace(role);

    if (!workspace) {
        workspaceMount.innerHTML = `
            <div class="workspace-placeholder">
                <h3>Encounter Workspace</h3>
                <p>
                    No workspace is available for this staff role.
                </p>
            </div>
        `;

        return;
    }

    workspaceModule = workspace;

    try {
        workspace.mount(workspaceMount);
    } catch (error) {
        console.error(
            "[EncounterPanel] Workspace failed to mount:",
            error
        );

        workspaceModule = null;

        renderWorkspaceError(
            workspaceMount,
            "The workspace for this role could not be loaded."
        );
    }
}

/* ==========================================================================
   WORKSPACE CLEANUP
   ========================================================================== */

function destroyWorkspace() {
    if (
        workspaceModule &&
        typeof workspaceModule.unmount === "function"
    ) {
        try {
            workspaceModule.unmount();
        } catch (error) {
            console.error(
                "[EncounterPanel] Workspace cleanup failed:",
                error
            );
        }
    }

    workspaceModule = null;
}


/* ==========================================================================
   WORKSPACE ERROR
   ========================================================================== */

function renderWorkspaceError(containerElement, message) {
    if (!containerElement) {
        return;
    }

    containerElement.innerHTML = `
        <div class="workspace-placeholder workspace-error">

            <h3>
                Encounter Workspace Unavailable
            </h3>

            <p>
                ${escapeHtml(message)}
            </p>

        </div>
    `;
}


/* ==========================================================================
   PATIENT IDENTITY
   ========================================================================== */

function getPatientIdentity(patient) {
    return (
        patient?.queue_entry_id ??
        patient?.visit?.visit_id ??
        patient?.visit_id ??
        patient?.patient_id ??
        patient?.id ??
        null
    );
}


/* ==========================================================================
   PATIENT DISPLAY HELPERS
   ========================================================================== */

function getToken(patient) {
    return (
        patient.visit?.token_number ??
        patient.token_number ??
        patient.token ??
        "—"
    );
}


function getPatientName(patient) {
    const details =
        patient.visit?.patient ||
        patient.patient ||
        patient;

    if (
        patient.patient_name ||
        details.patient_name
    ) {
        return (
            patient.patient_name ||
            details.patient_name
        );
    }

    const firstName =
        details.first_name ?? "";

    const lastName =
        details.last_name ?? "";

    const name =
        `${firstName} ${lastName}`.trim();

    return name || "Patient";
}


function getDobOrAge(patient) {
    const details =
        patient.visit?.patient ||
        patient.patient ||
        patient;

    if (details.date_of_birth) {
        return details.date_of_birth;
    }

    if (
        details.estimated_age !== undefined &&
        details.estimated_age !== null
    ) {
        return `${details.estimated_age} years`;
    }

    return "—";
}


function getPriorityLabel(patient) {
    return patient.priority ?? "NORMAL";
}


function getPriorityClass(patient) {
    return `priority-${String(
        patient.priority ?? "NORMAL"
    ).toLowerCase()}`;
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