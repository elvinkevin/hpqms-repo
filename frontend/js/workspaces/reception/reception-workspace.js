/* ==========================================================================
   HPQMS Reception Workspace
   workspaces/reception/reception-workspace.js

   Reception-specific encounter workspace with fixed action buttons
   and drawer-based routing interface.

   Architecture:
   - Scrollable: encounter information section
   - Fixed: action button controls at bottom
   - Drawer: routing/transfer panel (like registration-drawer)

   ========================================================================== */

import {
    getMyActivePatient,
    subscribe,
} from "../../staff-queue-state.js";

import {
    completeRegistration,
} from "../../staff-actions.js";

import * as receptionActions
    from "./reception-actions.js";

import * as registrationDrawer
    from "../../components/registration-drawer.js";

import {
    getStaffContext,
    ACTION,
    canPerform as canPerformAction,
} from "../../staff-actions.js";


/*
 * Priority is a clinical decision. Only roles granted SET_PRIORITY in
 * their workspace config may choose a priority in the transfer drawer;
 * Reception sees the current priority read-only and the transfer
 * preserves it (no priority field is sent to the backend).
 */
function canSetPriority() {
    const { role } = getStaffContext();
    return canPerformAction(role, ACTION.SET_PRIORITY);
}


let container = null;
let unsubscribe = null;
let callbacks = {};
let lastRenderSignature = null;
let hasDismissedBanner = false;
let bannerDismissedForPatientId = null;

/*
 * The success banner must appear exactly once per patient per session.
 * sessionStorage (per-tab) survives page reloads, so a refresh no longer
 * re-shows a banner for a registration that completed earlier.
 */
const BANNER_SHOWN_KEY = "hpqms:regCompleteBanner:";

function wasBannerShown(patientId) {
    if (patientId == null) return false;
    try {
        return sessionStorage.getItem(BANNER_SHOWN_KEY + patientId) === "1";
    } catch {
        return false;
    }
}

function markBannerShown(patientId) {
    if (patientId == null) return;
    try {
        sessionStorage.setItem(BANNER_SHOWN_KEY + patientId, "1");
    } catch {
        /* storage unavailable — banner just behaves as before */
    }
}


/* ==========================================================================
   PUBLIC API
   ========================================================================== */

export function mount(target, options = {}) {
    if (!(target instanceof HTMLElement)) {
        throw new TypeError(
            "ReceptionWorkspace mount target must be an HTMLElement."
        );
    }

    unmount();

    container = target;
    callbacks = options;
    lastRenderSignature = null;

    unsubscribe = subscribe(() => {
        render();
    });

    render();
}


export function update(target, { patient } = {}) {
    if (container === target && patient) {
        render();
    }
}


export function unmount() {
    if (unsubscribe) {
        unsubscribe();
        unsubscribe = null;
    }

    registrationDrawer.destroy();
    destroyRoutingDrawer();

    if (container) {
        container.innerHTML = "";
    }

    container = null;
    callbacks = {};
    lastRenderSignature = null;
}


/* ==========================================================================
   RENDER
   ========================================================================== */

/* ==========================================================================
   RECEPTION WORKSPACE RENDER & SIGNATURE RECONCILIATION
   ========================================================================== */



export function render() {
    if (!container) {
        return;
    }

    const patient = getMyActivePatient();

    if (!patient) {
        if (lastRenderSignature !== null) {
            lastRenderSignature = null;
            bannerDismissedForPatientId = null;
            renderNoPatient();
        }
        return;
    }

    const signature = computeRenderSignature(patient);
    if (signature === lastRenderSignature) {
        return; // Prevents unnecessary DOM re-renders
    }
    lastRenderSignature = signature;

    renderReceptionEncounter(patient);
    markBannerShownIfRendered();
    handleBannerLifecycle(patient);
}

/**
 * Resets the render signature to force an immediate DOM re-render
 * after successful registration submission.
 */
export function forceWorkspaceRerender() {
    lastRenderSignature = null;
    render();
}

/* ==========================================================================
   BANNER DISMISSAL LIFECYCLE
   ========================================================================== */

/*
 * Flags the banner as shown the moment it is actually in the DOM,
 * so a reload during (or after) the auto-dismiss never resurrects it.
 */
function markBannerShownIfRendered() {
    const banner = container.querySelector("#registrationCompleteBanner");
    if (!banner) return;

    const patient = getMyActivePatient();
    const patientId =
        getPatientDetails(patient)?.patient_id ??
        patient?.patient_id;

    markBannerShown(patientId);
}

function handleBannerLifecycle(patient) {
    const details = getPatientDetails(patient);
    const isComplete = isRegistrationComplete(details);
    const patientId = details?.patient_id ?? patient?.patient_id;

    // Reset dismissal flag if a new patient is loaded into workspace
    if (bannerDismissedForPatientId !== patientId) {
        bannerDismissedForPatientId = null;
    }

    // Do not schedule dismissal if already dismissed for this patient
    if (!isComplete || bannerDismissedForPatientId === patientId) {
        const existingBanner = container.querySelector("#registrationCompleteBanner");
        if (existingBanner && bannerDismissedForPatientId === patientId) {
            existingBanner.remove();
        }
        return;
    }

    // Schedule auto-dismissal
    setTimeout(() => {
        const banner = container.querySelector("#registrationCompleteBanner");
        if (!banner) return;

        banner.style.transition = "opacity 0.4s ease, max-height 0.4s ease, margin 0.4s ease, padding 0.4s ease";
        banner.style.opacity = "0";
        banner.style.maxHeight = "0px";
        banner.style.paddingTop = "0px";
        banner.style.paddingBottom = "0px";
        banner.style.marginTop = "0px";
        banner.style.marginBottom = "0px";
        banner.style.overflow = "hidden";

        setTimeout(() => {
            banner.remove();
            bannerDismissedForPatientId = patientId; // Prevent re-rendering banner for this patient
        }, 400);
    }, 4000);
}

function computeRenderSignature(patient) {
    const details = getPatientDetails(patient);

    return JSON.stringify({
        id:
            patient.queue_entry_id ??
            patient.visit?.visit_id ??
            patient.visit_id ??
            details.patient_id ??
            null,
        status: patient.status,
        priority: patient.priority,
        complete: isRegistrationComplete(details),
        first_name: details.first_name,
        last_name: details.last_name,
        phone: details.phone,
        email: details.email,
    });
}



/* ==========================================================================
   MAIN VIEW
   ========================================================================== */

function renderReceptionEncounter(patient) {
    const details = getPatientDetails(patient);
    const registrationComplete = isRegistrationComplete(details);
    const queueStatus = patient.status ?? "—";

    container.innerHTML = `
        <section class="reception-workspace">

            <!-- Scrollable content area -->
            <div class="reception-scroll-container">

                <!-- Registration section -->
                <div class="reception-section">

                    <div class="reception-section-header">
                        <div>
                            <span class="reception-eyebrow">
                                REGISTRATION
                            </span>

                            <h3>
                                Patient Registration
                            </h3>
                        </div>

                        <span class="
                            registration-status
                            ${registrationComplete
                                ? "registration-complete"
                                : "registration-incomplete"}
                        ">
                            ${registrationComplete
                                ? "Complete"
                                : "Incomplete"}
                        </span>
                    </div>

                    ${
                        registrationComplete
                            ? wasBannerShown(getPatientDetails(patient)?.patient_id)
                                ? ""
                                : renderRegistrationComplete(patient)
                            : renderRegistrationRequired()
                    }

                </div>

                <div class="reception-divider"></div>

                <!-- Encounter information section -->
                <div class="reception-section">

                    <div class="reception-section-header">
                        <div>
                            <span class="reception-eyebrow">
                                ENCOUNTER
                            </span>

                            <h3>
                                Encounter Information
                            </h3>
                        </div>
                    </div>

                    ${renderEncounterInformation(patient)}

                </div>

            </div>

            <!-- Fixed action buttons at bottom -->
            ${
                queueStatus === "IN_PROGRESS" && registrationComplete
                    ? renderActionButtons(patient)
                    : ""
            }

        </section>
    `;

    attachListeners(patient);
}


/* ==========================================================================
   REGISTRATION STATES
   ========================================================================== */

function renderRegistrationRequired() {
    return `
        <div class="registration-alert">

            <div class="registration-alert-icon">
                !
            </div>

            <div class="registration-alert-content">

                <strong>
                    Registration information is incomplete
                </strong>

                <p>
                    Complete the patient's administrative information
                    before routing or completing the reception encounter.
                </p>

            </div>

        </div>

        <button
            type="button"
            class="reception-primary-action"
            id="openRegistrationBtn">

            Complete Registration

        </button>
    `;
}

/**
 * Renders the success banner and schedules a smooth collapse.
 */
function renderRegistrationComplete(patient) {
    const name = getPatientName(patient);

    return `
        <div id="registrationCompleteBanner" class="registration-complete-message">
            <div class="registration-check">✓</div>
            <div>
                <strong>Registration completed</strong>
                <p>${escapeHtml(name)} is fully registered.</p>
            </div>
        </div>
    `;
}

/**
 * Auto-dismisses the success banner after a delay without breaking layout.
 */
function scheduleRegistrationBannerDismissal(container, delayMs = 3500) {
    // If the banner was already dismissed during this active session, don't show it again
    if (hasDismissedBanner) {
        const banner = container.querySelector("#registrationCompleteBanner");
        if (banner) banner.remove();
        return;
    }

    setTimeout(() => {
        const banner = container.querySelector("#registrationCompleteBanner");
        if (!banner) return;

        // Apply CSS transition properties for vertical collapse
        banner.style.transition = "all 0.4s cubic-bezier(0.4, 0, 0.2, 1)";
        banner.style.opacity = "0";
        banner.style.maxHeight = "0px";
        banner.style.paddingTop = "0px";
        banner.style.paddingBottom = "0px";
        banner.style.marginTop = "0px";
        banner.style.marginBottom = "0px";
        banner.style.overflow = "hidden";

        setTimeout(() => {
            banner.remove();
            hasDismissedBanner = true; // Mark as dismissed for current session
        }, 400);
    }, delayMs);
}


/* ==========================================================================
   ENCOUNTER INFORMATION
   ========================================================================== */

function renderEncounterInformation(patient) {
    return `
        <div class="reception-encounter-grid">

            <div class="reception-info-item">
                <span>Queue Status</span>
                <strong>
                    ${escapeHtml(patient.status ?? "—")}
                </strong>
            </div>

            <div class="reception-info-item">
                <span>Priority</span>
                <strong>
                    ${escapeHtml(patient.priority ?? "NORMAL")}
                </strong>
            </div>

            <div class="reception-info-item">
                <span>Entry Type</span>
                <strong>
                    ${escapeHtml(
                        patient.entry_type ??
                        patient.visit?.entry_type ??
                        "—"
                    )}
                </strong>
            </div>

            <div class="reception-info-item">
                <span>Department</span>
                <strong>
                    ${escapeHtml(
                        patient.department?.name ??
                        patient.department_name ??
                        "Reception"
                    )}
                </strong>
            </div>

        </div>
    `;
}


/* ==========================================================================
   ACTION BUTTONS (FIXED)
   ========================================================================== */

function renderActionButtons(patient) {
    return `
        <div class="reception-action-controls">

            <button
                type="button"
                class="reception-workflow-btn reception-workflow-primary"
                id="completeReceptionBtn"
                data-action="complete">

                <span class="action-icon">✓</span>
                <span>Complete Encounter / Visit</span>

            </button>

            <div class="reception-workflow-secondary-row">

                <button
                    type="button"
                    class="reception-workflow-btn reception-workflow-secondary"
                    id="routePatientBtn"
                    data-action="route">

                    <span class="action-icon">↗</span>
                    <span>Transfer Dept</span>

                </button>

                <button
                    type="button"
                    class="reception-workflow-btn reception-workflow-secondary"
                    id="cancelEncounterBtn"
                    data-action="cancel">

                    <span class="action-icon">×</span>
                    <span>Cancel Encounter</span>

                </button>

            </div>

        </div>
    `;
}


/* ==========================================================================
   NO PATIENT
   ========================================================================== */

function renderNoPatient() {
    container.innerHTML = `
        <section class="reception-workspace reception-no-patient">

            <div class="reception-empty-icon">
                +
            </div>

            <h3>
                No Active Patient
            </h3>

            <p>
                Call and start a patient to begin the reception encounter.
            </p>

        </section>
    `;
}




/* ==========================================================================
   EVENT HANDLERS
   ========================================================================== */

function attachListeners(patient) {
    attachRegistrationListener(patient);
    attachActionListeners(patient);
}


function attachRegistrationListener(patient) {
    const registrationButton = container?.querySelector(
        "#openRegistrationBtn"
    );

    if (!registrationButton) {
        return;
    }

    registrationButton.addEventListener("click", () => {
        registrationDrawer.open(patient, {
            onSubmit: async (payload) => {
                await handleRegistration(patient, payload);
            },
        });
    });
}


function attachActionListeners(patient) {
    const completeBtn = container?.querySelector("#completeReceptionBtn");
    if (completeBtn) {
        completeBtn.addEventListener("click", () => {
            handleCompleteReception(patient);
        });
    }

    const routeBtn = container?.querySelector("#routePatientBtn");
    if (routeBtn) {
        routeBtn.addEventListener("click", () => {
            openRoutingDrawer(patient);
        });
    }

    const cancelBtn = container?.querySelector("#cancelEncounterBtn");
    if (cancelBtn) {
        cancelBtn.addEventListener("click", () => {
            handleCancelEncounter(patient);
        });
    }

    /*
     * Priority adjustment is deliberately NOT exposed to Reception —
     * priority is a clinical triage decision (SET_PRIORITY is not in
     * the receptionist workspace config). Only Transfer and Cancel
     * remain as secondary actions.
     */
}


/* ==========================================================================
   REGISTRATION ACTION
   ========================================================================== */

async function handleRegistration(patient, payload) {
    const details = getPatientDetails(patient);

    const patientId =
        details.patient_id ??
        patient.patient_id;

    if (!patientId) {
        showError(
            "Unable to identify the patient for registration."
        );
        return;
    }

    try {
        setActionBusy(true);

        await completeRegistration(patientId, payload);

        if (typeof callbacks.onRegistrationCompleted === "function") {
            await callbacks.onRegistrationCompleted();
        }

    } catch (error) {
        showError(
            error?.message ||
            "Unable to complete registration."
        );
    } finally {
        setActionBusy(false);
    }
}


/* ==========================================================================
   COMPLETE RECEPTION ACTION
   ========================================================================== */

async function handleCompleteReception(patient) {
    const queueEntryId = patient.queue_entry_id;

    if (!queueEntryId) {
        showError("Unable to complete: queue entry ID is missing.");
        return;
    }

    if (!confirm("Complete this Reception encounter?")) {
        return;
    }

    try {
        setActionBusy(true);

        await receptionActions.completeReceptionEncounter(queueEntryId);

        if (typeof callbacks.onActionCompleted === "function") {
            await callbacks.onActionCompleted();
        }

    } catch (error) {
        showError(
            error?.message ||
            "Unable to complete the Reception encounter."
        );
    } finally {
        setActionBusy(false);
    }
}


/* ==========================================================================
   CANCEL ENCOUNTER ACTION
   ========================================================================== */

async function handleCancelEncounter(patient) {
    const queueEntryId = patient.queue_entry_id;

    if (!queueEntryId) {
        showError("Unable to cancel: queue entry ID is missing.");
        return;
    }

    if (
        !confirm(
            "Cancel this Reception encounter? This action cannot be undone."
        )
    ) {
        return;
    }

    try {
        setActionBusy(true);

        await receptionActions.cancelReceptionEncounter(queueEntryId);

        if (typeof callbacks.onActionCompleted === "function") {
            await callbacks.onActionCompleted();
        }

    } catch (error) {
        showError(
            error?.message ||
            "Unable to cancel the Reception encounter."
        );
    } finally {
        setActionBusy(false);
    }
}


/* ==========================================================================
   ROUTING DRAWER (SIDEBAR)
   ========================================================================== */

let routingDrawer = null;

async function openRoutingDrawer(patient) {
    try {
        setActionBusy(true);

        const departments = await receptionActions.getDepartments();

        renderRoutingDrawer(
            patient,
            Array.isArray(departments)
                ? departments
                : departments?.items ?? []
        );

    } catch (error) {
        showError(
            error?.message ||
            "Unable to load available departments."
        );
    } finally {
        setActionBusy(false);
    }
}


function renderRoutingDrawer(patient, departments) {
    destroyRoutingDrawer();

    routingDrawer = document.createElement("div");
    routingDrawer.className = "reception-routing-drawer";

    routingDrawer.innerHTML = `
        <div class="reception-routing-drawer-overlay"></div>

        <div class="reception-routing-panel">

            <div class="reception-routing-header">

                <div>
                    <span class="reception-eyebrow">
                        PATIENT ROUTING
                    </span>

                    <h3>
                        Transfer Patient
                    </h3>
                </div>

                <button
                    type="button"
                    class="reception-routing-close"
                    data-close-routing>
                    ×
                </button>

            </div>

            <form id="routePatientForm" class="reception-routing-form">

                <div class="reception-routing-section">

                    <label for="routeDepartment">
                        Destination Department
                    </label>

                    <select
                        id="routeDepartment"
                        name="target_dept_id"
                        required
                        class="reception-routing-select">

                        <option value="">
                            Select department
                        </option>

                        ${departments
                            .filter(dept =>
                                isValidDestination(patient, dept)
                            )
                            .map(department => `
                                <option
                                    value="${escapeHtml(
                                        department.dept_id ??
                                        department.department_id
                                    )}">
                                    ${escapeHtml(
                                        department.name ??
                                        department.department_name ??
                                        department.code ??
                                        "Department"
                                    )}
                                </option>
                            `)
                            .join("")}

                    </select>

                </div>

                <div class="reception-routing-section">

                    ${canSetPriority()
                        ? `
                    <label for="routePriority">
                        Priority
                    </label>

                    <select
                        id="routePriority"
                        name="priority"
                        class="reception-routing-select">

                        <option value="NORMAL">Normal</option>
                        <option value="SEMI_URGENT">Semi-Urgent</option>
                        <option value="URGENT">Urgent</option>
                        <option value="CRITICAL">Critical</option>

                    </select>`
                        : `
                    <label>
                        Current Priority
                    </label>

                    <div class="reception-routing-priority-readonly">
                        ${escapeHtml(patient.priority ?? "NORMAL")}
                    </div>

                    <p class="reception-routing-priority-note">
                        Priority is preserved during transfer. Priority
                        changes are made by clinical staff.
                    </p>`}

                </div>

                <div class="reception-routing-section">

                    <label for="routeNotes">
                        Notes <span class="reception-optional">(optional)</span>
                    </label>

                    <textarea
                        id="routeNotes"
                        name="notes"
                        rows="4"
                        maxlength="1000"
                        placeholder="Optional routing notes..."
                        class="reception-routing-textarea"></textarea>

                </div>

                <div
                    class="reception-routing-error"
                    data-route-error
                    hidden></div>

                <div class="reception-routing-actions">

                    <button
                        type="button"
                        class="reception-routing-btn secondary"
                        data-close-routing>
                        Cancel
                    </button>

                    <button
                        type="submit"
                        class="reception-routing-btn primary">
                        Transfer Patient
                    </button>

                </div>

            </form>

        </div>
    `;

    document.body.appendChild(routingDrawer);

    const closeButtons = routingDrawer.querySelectorAll("[data-close-routing]");
    closeButtons.forEach(button => {
        button.addEventListener("click", destroyRoutingDrawer);
    });

    const overlay = routingDrawer.querySelector(".reception-routing-drawer-overlay");
    if (overlay) {
        overlay.addEventListener("click", destroyRoutingDrawer);
    }

    const form = routingDrawer.querySelector("#routePatientForm");
    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        await submitRoute(patient);
    });
}


async function submitRoute(patient) {
    if (!routingDrawer) {
        return;
    }

    const form = routingDrawer.querySelector("#routePatientForm");
    const data = new FormData(form);

    const targetDeptId = data.get("target_dept_id");

    /*
     * The priority field only exists in the DOM for clinical roles.
     * For Reception it is absent → priority is not sent and the
     * backend preserves the patient's current priority.
     */
    const priority = data.get("priority") || null;
    const notes = data.get("notes")?.trim() || null;

    if (!targetDeptId) {
        return;
    }

    const visitId =
        patient.visit_id ??
        patient.visit?.visit_id;

    if (!visitId) {
        showRoutingError(
            "Unable to route: visit ID is missing."
        );
        return;
    }

    try {
        setDrawerBusy(true);

        await receptionActions.routePatient(
            visitId,
            targetDeptId,
            {
                priority,
                notes,
            }
        );

        destroyRoutingDrawer();

        if (typeof callbacks.onActionCompleted === "function") {
            await callbacks.onActionCompleted();
        }

    } catch (error) {
        showRoutingError(
            error?.message ||
            "Unable to transfer patient."
        );
    } finally {
        setDrawerBusy(false);
    }
}


function destroyRoutingDrawer() {
    if (routingDrawer) {
        routingDrawer.remove();
        routingDrawer = null;
    }
}


/* ==========================================================================
   UI HELPERS
   ========================================================================== */

function setActionBusy(busy) {
    if (container) {
        container
            .querySelectorAll("button")
            .forEach(button => {
                button.disabled = busy;
            });
    }
}


function setDrawerBusy(busy) {
    if (routingDrawer) {
        routingDrawer
            .querySelectorAll("button, select, textarea")
            .forEach(element => {
                element.disabled = busy;
            });
    }
}


function showError(message) {
    if (!container) {
        return;
    }

    let error = container.querySelector(".reception-action-error");

    if (!error) {
        error = document.createElement("div");
        error.className = "reception-action-error";
        container.prepend(error);
    }

    error.textContent = message;
}


function showRoutingError(message) {
    if (!routingDrawer) {
        return;
    }

    const error = routingDrawer.querySelector("[data-route-error]");

    if (!error) {
        return;
    }

    error.textContent = message;
    error.hidden = false;
}


/* ==========================================================================
   DATA HELPERS
   ========================================================================== */

/**
 * Checks if a patient record contains all required registration fields.
 */
function isRegistrationComplete(details) {
    if (!details) return false;

    const explicitFlag =
        details?.registration_complete ??
        details?.is_registration_complete;

    if (explicitFlag !== undefined && explicitFlag !== null) {
        return Boolean(explicitFlag);
    }

    // Fallback: Check critical registration attributes
    const hasFirst = Boolean(details.first_name?.trim());
    const hasLast = Boolean(details.last_name?.trim());
    const hasDob = Boolean(details.date_of_birth);
    const hasGender = Boolean(details.gender);
    const hasContact = Boolean(details.phone?.trim() || details.email?.trim());

    return hasFirst && hasLast && hasDob && hasGender && hasContact;
}

function getPatientDetails(patient) {
    return (
        patient?.visit?.patient ||
        patient?.patient ||
        patient ||
        {}
    );
}


function getPatientName(patient) {
    const details = getPatientDetails(patient);

    const explicitName =
        patient?.patient_name ??
        details?.patient_name;

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


function isValidDestination(patient, department) {
    const currentDeptId =
        patient?.dept_id ??
        patient?.department?.dept_id;

    const destinationId =
        department?.dept_id ??
        department?.department_id;

    return String(destinationId) !== String(currentDeptId);
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