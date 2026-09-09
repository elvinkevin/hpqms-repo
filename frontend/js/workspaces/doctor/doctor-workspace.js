/*
 * ==========================================================================
 * HPQMS Doctor Workspace
 * workspaces/doctor/doctor-workspace.js
 *
 * Responsibilities:
 * - Display persisted triage information
 * - Provide doctor clinical consultation fields
 * - Manage doctor-specific clinical draft
 * - Change queue priority
 * - Route/refer patient
 * - Discharge patient
 *
 * This module does NOT:
 * - call fetch directly
 * - own queue state
 * - perform generic queue actions
 * - manage WebSocket connections
 * - implement laboratory/pharmacy orders
 * ==========================================================================
 */

import {
    getMyActivePatient,
    subscribe,
} from "../../staff-queue-state.js";

import {
    updatePriority,
    transferToDepartment,
    dischargeFromCare,
} from "../../staff-actions.js";


let container = null;
let unsubscribe = null;
let callbacks = {};

let lastRenderSignature = null;

let draft = {
    clinicalFindings: "",
    diagnosis: "",
    treatmentPlan: "",
};

let draftVisitId = null;

let priorityConfirmOverlay = null;
let pendingPriority = null;

let routingDrawer = null;
let dischargeOverlay = null;


/* ==========================================================================
   PUBLIC API
   ========================================================================== */

export function mount(target, options = {}) {
    if (!(target instanceof HTMLElement)) {
        throw new TypeError(
            "DoctorWorkspace mount target must be an HTMLElement."
        );
    }

    unmount();

    container = target;
    callbacks = options;

    lastRenderSignature = null;

    resetDraft();

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

    destroyPriorityConfirm();
    destroyRoutingDrawer();
    destroyDischargeOverlay();

    if (container) {
        container.innerHTML = "";
    }

    container = null;
    callbacks = {};

    lastRenderSignature = null;

    resetDraft();
}


/* ==========================================================================
   RENDER
   ========================================================================== */

export function render() {
    if (!container) {
        return;
    }

    const patient = getMyActivePatient();

    if (!patient) {
        if (lastRenderSignature !== null) {
            lastRenderSignature = null;
            renderNoPatient();
        }

        return;
    }

    prepareDraftForPatient(patient);

    const signature = computeRenderSignature(patient);

    if (signature === lastRenderSignature) {
        return;
    }

    lastRenderSignature = signature;

    renderDoctorEncounter(patient);
}


function computeRenderSignature(patient) {
    return JSON.stringify({
        id: patient.queue_entry_id ?? patient.visit_id ?? null,
        status: patient.status,
        priority: patient.priority,

        first_name: patient.visit?.patient?.first_name,
        last_name: patient.visit?.patient?.last_name,

        chief_complaint: getChiefComplaint(patient),
        triage_assessment: getTriageAssessment(patient),
        vitals: getPersistedVitals(patient),

        clinical_findings: getPersistedClinicalFindings(patient),
        diagnosis: getPersistedDiagnosis(patient),
        treatment_plan: getPersistedTreatmentPlan(patient),

        draft,
    });
}


/* ==========================================================================
   MAIN VIEW
   ========================================================================== */

function renderDoctorEncounter(patient) {
    const priority = patient.priority ?? "NORMAL";

    const chiefComplaint = getChiefComplaint(patient);
    const triageAssessment = getTriageAssessment(patient);
    const vitals = deriveVitals(getPersistedVitals(patient));

    container.innerHTML = `
        <section class="doctor-workspace">

            <div class="doctor-scroll-container">

                <!-- ======================================================
                     TRIAGE SUMMARY
                     ====================================================== -->

                <div class="doctor-section">

                    <div class="doctor-section-header">
                        <div>
                            <span class="doctor-eyebrow">
                                TRIAGE INFORMATION
                            </span>


                        </div>

                        <span class="doctor-readonly-badge">
                            READ-ONLY
                        </span>
                    </div>


                    <!-- Chief Complaint -->

                    <div class="doctor-summary-block">

                        <span class="doctor-field-label">
                            Chief Complaint
                        </span>

                        ${
                            chiefComplaint
                                ? `
                                    <p class="doctor-summary-text">
                                        ${escapeHtml(chiefComplaint)}
                                    </p>
                                  `
                                : `
                                    <p class="doctor-empty-text">
                                        No chief complaint recorded.
                                    </p>
                                  `
                        }

                    </div>


                    <!-- Vitals -->
                    <span class="doctor-field-label">
                            vitals
                        </span>
                    <div class="doctor-vitals-grid">

                        ${renderVital(
                            "Heart Rate",
                            vitals.heart_rate,
                            "bpm"
                        )}

                        ${renderVital(
                            "Blood Pressure",
                            vitals.blood_pressure,
                            "mmHg"
                        )}

                        ${renderVital(
                            "Temperature",
                            vitals.temperature,
                            "°C"
                        )}

                        ${renderVital(
                            "SpO₂",
                            vitals.oxygen_saturation,
                            "%"
                        )}

                        ${renderVital(
                            "Resp. Rate",
                            vitals.respiratory_rate,
                            "bpm"
                        )}

                    </div>


                    <!-- Triage Assessment -->

                    <div class="doctor-summary-block">

                        <span class="doctor-field-label">
                            Triage Assessment
                        </span>

                        ${
                            triageAssessment
                                ? `
                                    <p class="doctor-summary-text">
                                        ${escapeHtml(triageAssessment)}
                                    </p>
                                  `
                                : `
                                    <p class="doctor-empty-text">
                                        No triage assessment recorded.
                                    </p>
                                  `
                        }

                    </div>

                </div>


                <!-- ======================================================
                     PRIORITY
                     ====================================================== -->

                <div class="doctor-section">

                    <div class="doctor-section-header">

                        <div>
                            <span class="doctor-eyebrow">
                                CLINICAL PRIORITY
                            </span>

                            <h3>
                                Patient Acuity
                            </h3>
                        </div>

                    </div>


                    <div class="doctor-priority-row">

                        <div>
                            <span class="doctor-field-label">
                                Current Priority
                            </span>

                            <span
                                class="doctor-priority-badge
                                    ${priority.toLowerCase()}">
                                ${escapeHtml(priority)}
                            </span>
                        </div>


                        <div class="doctor-priority-options">

                            ${renderPriorityOption(
                                "CRITICAL",
                                "Critical",
                                priority
                            )}

                            ${renderPriorityOption(
                                "URGENT",
                                "Urgent",
                                priority
                            )}

                            ${renderPriorityOption(
                                "SEMI_URGENT",
                                "Semi-Urgent",
                                priority
                            )}

                            ${renderPriorityOption(
                                "NORMAL",
                                "Normal",
                                priority
                            )}

                        </div>

                    </div>

                </div>


                <!-- ======================================================
                     DOCTOR CONSULTATION
                     ====================================================== -->

                <div class="doctor-section">

                    <div class="doctor-section-header">

                        <div>
                            <span class="doctor-eyebrow">
                                CONSULTATION
                            </span>


                        </div>

                    </div>


                    <!-- Clinical Findings -->

                    <div class="doctor-form-field">

                        <label for="doctorClinicalFindings">
                            Clinical Findings
                        </label>

                        <textarea
                            id="doctorClinicalFindings"
                            name="clinical_findings"
                            rows="5"
                            maxlength="3000"
                            placeholder="Document history, examination findings, and relevant observations..."
                        >${escapeHtml(draft.clinicalFindings)}</textarea>

                        <small>
                            <span id="clinicalFindingsCount">
                                ${draft.clinicalFindings.length}
                            </span>/3000
                        </small>

                    </div>


                    <!-- Diagnosis -->

                    <div class="doctor-form-field">

                        <label for="doctorDiagnosis">
                            Diagnosis
                        </label>

                        <textarea
                            id="doctorDiagnosis"
                            name="diagnosis"
                            rows="3"
                            maxlength="1000"
                            placeholder="Enter the clinical diagnosis..."
                        >${escapeHtml(draft.diagnosis)}</textarea>

                        <small>
                            <span id="diagnosisCount">
                                ${draft.diagnosis.length}
                            </span>/1000
                        </small>

                    </div>


                    <!-- Treatment Plan -->

                    <div class="doctor-form-field">

                        <label for="doctorTreatmentPlan">
                            Treatment / Clinical Plan
                        </label>

                        <textarea
                            id="doctorTreatmentPlan"
                            name="treatment_plan"
                            rows="5"
                            maxlength="3000"
                            placeholder="Document treatment, instructions, follow-up, or other clinical plans..."
                        >${escapeHtml(draft.treatmentPlan)}</textarea>

                        <small>
                            <span id="treatmentPlanCount">
                                ${draft.treatmentPlan.length}
                            </span>/3000
                        </small>

                    </div>


                    <div
                        class="doctor-form-error"
                        data-doctor-error
                        hidden>
                    </div>


                    <button
                        type="button"
                        class="doctor-save-btn"
                        id="saveClinicalAssessmentBtn">

                        Save Clinical Assessment

                    </button>

                </div>

            </div>


            <!-- ==========================================================
                 FIXED ENCOUNTER ACTIONS
                 ========================================================== -->

            <div class="doctor-action-controls">

                <button
                    type="button"
                    class="doctor-workflow-btn doctor-transfer-btn"
                    id="doctorRouteBtn">

                    <span>↗</span>
                    <span>Route / Refer Patient</span>

                </button>


                <button
                    type="button"
                    class="doctor-workflow-btn doctor-discharge-btn"
                    id="doctorDischargeBtn">

                    <span>✓</span>
                    <span>Discharge Patient</span>

                </button>

            </div>

        </section>
    `;

    attachListeners(patient);
}


/* ==========================================================================
   VITALS
   ========================================================================== */

function renderVital(label, value, unit) {
    return `
        <div class="doctor-vital-card">

            <span class="doctor-vital-label">
                ${escapeHtml(label)}
            </span>

            ${
                value !== null &&
                value !== undefined &&
                value !== ""
                    ? `
                        <span class="doctor-vital-value">
                            ${escapeHtml(String(value))}
                            <small>${escapeHtml(unit)}</small>
                        </span>
                      `
                    : `
                        <span class="doctor-vital-empty">
                            Not recorded
                        </span>
                      `
            }

        </div>
    `;
}


function deriveVitals(vitals) {
    if (!vitals) {
        return {
            heart_rate: null,
            blood_pressure: null,
            temperature: null,
            oxygen_saturation: null,
            respiratory_rate: null,
        };
    }

    return {
        heart_rate: vitals.heart_rate ?? null,

        blood_pressure:
            vitals.blood_pressure ??
            formatBloodPressure(
                vitals.systolic_bp,
                vitals.diastolic_bp
            ),

        temperature: vitals.temperature ?? null,

        oxygen_saturation:
            vitals.oxygen_saturation ?? null,

        respiratory_rate:
            vitals.respiratory_rate ?? null,
    };
}


function formatBloodPressure(systolic, diastolic) {
    if (systolic == null || diastolic == null) {
        return null;
    }

    return `${systolic}/${diastolic}`;
}


/* ==========================================================================
   PRIORITY
   ========================================================================== */

function renderPriorityOption(value, label, currentPriority) {
    return `
        <label class="doctor-priority-option">

            <input
                type="radio"
                name="doctorPriority"
                value="${value}"
                ${currentPriority === value ? "checked" : ""}
            >

            <span>
                ${escapeHtml(label)}
            </span>

        </label>
    `;
}


function attachPriorityListener() {
    const radios = container?.querySelectorAll(
        'input[name="doctorPriority"]'
    );

    if (!radios) {
        return;
    }

    radios.forEach(radio => {
        radio.addEventListener("change", async event => {
            if (event.target.checked) {
                await handlePriorityChange(event.target.value);
            }
        });
    });
}


async function handlePriorityChange(newPriority) {
    const patient = getMyActivePatient();

    if (!patient?.queue_entry_id) {
        showError("Unable to update priority: queue entry ID missing.");
        render();
        return;
    }

    const currentPriority = patient.priority ?? "NORMAL";

    if (newPriority === currentPriority) {
        return;
    }

    openPriorityConfirm(patient, newPriority);
}


function openPriorityConfirm(patient, newPriority) {
    destroyPriorityConfirm();

    pendingPriority = newPriority;

    const currentPriority = patient.priority ?? "NORMAL";

    priorityConfirmOverlay = document.createElement("div");

    priorityConfirmOverlay.className =
        "doctor-priority-confirm";

    priorityConfirmOverlay.innerHTML = `
        <div
            class="doctor-priority-confirm-banner"
            role="alertdialog"
            aria-modal="true">

            <h4>
                Confirm priority change
            </h4>

            <p>
                Change priority from
                <strong>${escapeHtml(currentPriority)}</strong>
                to
                <strong>${escapeHtml(newPriority)}</strong>?
            </p>

            <div class="doctor-confirm-actions">

                <button
                    type="button"
                    class="doctor-confirm-cancel"
                    data-priority-cancel>
                    Cancel
                </button>

                <button
                    type="button"
                    class="doctor-confirm-apply"
                    data-priority-confirm>
                    Confirm
                </button>

            </div>

        </div>
    `;

    priorityConfirmOverlay
        .querySelector("[data-priority-confirm]")
        ?.addEventListener("click", applyPriorityChange);

    priorityConfirmOverlay
        .querySelector("[data-priority-cancel]")
        ?.addEventListener("click", cancelPriorityChange);

    document.body.appendChild(priorityConfirmOverlay);
}


async function applyPriorityChange() {
    const patient = getMyActivePatient();
    const newPriority = pendingPriority;

    if (!patient?.queue_entry_id || !newPriority) {
        destroyPriorityConfirm();
        return;
    }

    const button = priorityConfirmOverlay?.querySelector(
        "[data-priority-confirm]"
    );

    if (button) {
        button.disabled = true;
    }

    try {
        await updatePriority(
            patient.queue_entry_id,
            newPriority
        );

        destroyPriorityConfirm();

        pendingPriority = null;

        if (typeof callbacks.onPriorityChanged === "function") {
            await callbacks.onPriorityChanged(newPriority);
        }

        render();

    } catch (error) {

        destroyPriorityConfirm();

        pendingPriority = null;

        showError(
            error?.message ||
            "Unable to update priority."
        );

        render();
    }
}


function cancelPriorityChange() {
    destroyPriorityConfirm();

    pendingPriority = null;

    render();
}


function destroyPriorityConfirm() {
    if (priorityConfirmOverlay) {
        priorityConfirmOverlay.remove();
        priorityConfirmOverlay = null;
    }
}


// Module-level guard against rapid double-clicks
let isSavingAssessment = false;

async function handleSaveClinicalAssessment() {
    // 1. Double-click guard
    if (isSavingAssessment) {
        return;
    }

    const patient = getMyActivePatient();

    if (!patient) {
        showError("No active patient.");
        return;
    }

    // Safely extract visit_id from top-level or nested patient.visit
    const visitId = patient.visit_id ?? patient.visit?.visit_id;

    if (!visitId) {
        showError("Active patient has no associated visit record.");
        return;
    }

    if (!draft.clinicalFindings.trim()) {
        showError("Clinical findings are required before saving.");
        return;
    }

    if (!draft.diagnosis.trim()) {
        showError("Diagnosis is required before saving.");
        return;
    }

    if (typeof callbacks.onSaveClinicalAssessment !== "function") {
        showError("Clinical assessment persistence is not connected.");
        return;
    }

    try {
        isSavingAssessment = true;
        setClinicalBusy(true);

        // Normalize payload to snake_case for backend schemas
        const assessmentPayload = {
            clinical_findings: draft.clinicalFindings.trim(),
            diagnosis: draft.diagnosis.trim(),
            treatment_plan: draft.treatmentPlan.trim(),
        };

        // Pass positional arguments: (visitId, assessmentPayload)
        await callbacks.onSaveClinicalAssessment(visitId, assessmentPayload);

        clearDoctorError();

        // Success UX Feedback
        setSaveButtonSuccess();

        if (typeof callbacks.onClinicalAssessmentSaved === "function") {
            await callbacks.onClinicalAssessmentSaved();
        }

    } catch (error) {
        showError(
            error?.message || "Unable to save clinical assessment."
        );
    } finally {
        isSavingAssessment = false;
        setClinicalBusy(false);
    }
}

/**
 * Updates save button state and label during network operation
 */
function setClinicalBusy(isBusy) {
    const saveButton = container?.querySelector("#saveClinicalAssessmentBtn");
    if (!saveButton) return;

    saveButton.disabled = isBusy;
    if (isBusy) {
        saveButton.textContent = "Saving...";
    }
}

/**
 * Provides transient visual success feedback on the save button
 */
function setSaveButtonSuccess() {
    const saveButton = container?.querySelector("#saveClinicalAssessmentBtn");
    if (!saveButton) return;

    saveButton.textContent = "Saved ✓";
    saveButton.classList.add("btn-success");

    setTimeout(() => {
        if (saveButton) {
            saveButton.textContent = "Save Clinical Assessment";
            saveButton.classList.remove("btn-success");
        }
    }, 2500);
}
/* ==========================================================================
   ROUTING
   ========================================================================== */

async function openRouting() {
    const patient = getMyActivePatient();

    const visitId =
        patient?.visit_id ??
        patient?.visit?.visit_id;

    if (!visitId) {
        showError("Unable to route: visit ID is missing.");
        return;
    }

    if (
        typeof callbacks.onLoadDepartments !== "function"
    ) {
        showError(
            "Department routing is not connected."
        );
        return;
    }

    try {

        setActionBusy(true);

        const departments =
            await callbacks.onLoadDepartments();

        renderRoutingDrawer(
            patient,
            Array.isArray(departments)
                ? departments
                : departments?.items ?? []
        );

    } catch (error) {

        showError(
            error?.message ||
            "Unable to load departments."
        );

    } finally {

        setActionBusy(false);

    }
}


function renderRoutingDrawer(patient, departments) {
    destroyRoutingDrawer();

    routingDrawer = document.createElement("div");

    routingDrawer.className =
        "doctor-routing-drawer";

    routingDrawer.innerHTML = `
        <div class="doctor-routing-overlay"></div>

        <div class="doctor-routing-panel">

            <div class="doctor-routing-header">

                <div>
                    <span class="doctor-eyebrow">
                        CLINICAL REFERRAL
                    </span>

                    <h3>
                        Route / Refer Patient
                    </h3>
                </div>

                <button
                    type="button"
                    class="doctor-routing-close"
                    data-close-routing>
                    ×
                </button>

            </div>


            <form
                id="doctorRoutingForm"
                class="doctor-routing-form">

                <div class="doctor-routing-section">

                    <label for="doctorRouteDepartment">
                        Destination Department
                    </label>

                    <select
                        id="doctorRouteDepartment"
                        name="target_dept_id"
                        required>

                        <option value="">
                            Select department
                        </option>

                        ${departments
                            .filter(dept =>
                                isValidDestination(
                                    patient,
                                    dept
                                )
                            )
                            .map(dept => `
                                <option
                                    value="${escapeHtml(
                                        dept.dept_id ??
                                        dept.department_id
                                    )}">

                                    ${escapeHtml(
                                        dept.name ??
                                        dept.department_name ??
                                        dept.code ??
                                        "Department"
                                    )}

                                </option>
                            `)
                            .join("")}

                    </select>

                </div>


                <div class="doctor-routing-section">

                    <label>
                        Current Priority
                    </label>

                    <div class="doctor-routing-priority">
                        ${escapeHtml(
                            patient.priority ?? "NORMAL"
                        )}
                    </div>

                </div>


                <div class="doctor-routing-section">

                    <label for="doctorRouteNotes">
                        Clinical Referral Notes
                    </label>

                    <textarea
                        id="doctorRouteNotes"
                        name="notes"
                        rows="5"
                        maxlength="1000"
                        placeholder="Explain the clinical reason for referral..."
                        required></textarea>

                </div>


                <div
                    class="doctor-routing-error"
                    data-route-error
                    hidden>
                </div>


                <div class="doctor-routing-actions">

                    <button
                        type="button"
                        class="doctor-routing-btn secondary"
                        data-close-routing>
                        Cancel
                    </button>

                    <button
                        type="submit"
                        class="doctor-routing-btn primary">
                        Confirm Referral
                    </button>

                </div>

            </form>

        </div>
    `;


    document.body.appendChild(routingDrawer);


    routingDrawer
        .querySelectorAll("[data-close-routing]")
        .forEach(button => {
            button.addEventListener(
                "click",
                destroyRoutingDrawer
            );
        });


    routingDrawer
        .querySelector(".doctor-routing-overlay")
        ?.addEventListener(
            "click",
            destroyRoutingDrawer
        );


    routingDrawer
        .querySelector("#doctorRoutingForm")
        ?.addEventListener(
            "submit",
            async event => {
                event.preventDefault();

                await submitRouting(
                    patient
                );
            }
        );
}


async function submitRouting(patient) {
    if (!routingDrawer) {
        return;
    }

    const form =
        routingDrawer.querySelector(
            "#doctorRoutingForm"
        );

    const data = new FormData(form);

    const targetDeptId =
        data.get("target_dept_id");

    const notes =
        data.get("notes")?.trim() || null;

    if (!targetDeptId) {
        showRoutingError(
            "Select a destination department."
        );
        return;
    }

    if (!notes) {
        showRoutingError(
            "Clinical referral notes are required."
        );
        return;
    }

    const visitId =
        patient.visit_id ??
        patient.visit?.visit_id;

    try {

        setDrawerBusy(true);

        /*
         * Doctor-specific routing action.
         *
         * The action layer is responsible for supplying
         * CLINICAL_REFERRAL as the transfer reason.
         */
        await transferToDepartment(
            visitId,
            {
                target_dept_id: targetDeptId,
                reason: "CLINICAL_REFERRAL",
                priority:
                    patient.priority ?? "NORMAL",
                notes,
            }
        );

        destroyRoutingDrawer();

        if (
            typeof callbacks.onActionCompleted ===
            "function"
        ) {
            await callbacks.onActionCompleted();
        }

    } catch (error) {

        showRoutingError(
            error?.message ||
            "Unable to refer patient."
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
   DISCHARGE
   ========================================================================== */

function openDischargeConfirmation() {
    const patient = getMyActivePatient();

    if (!patient) {
        return;
    }

    destroyDischargeOverlay();

    dischargeOverlay =
        document.createElement("div");

    dischargeOverlay.className =
        "doctor-discharge-overlay";

    dischargeOverlay.innerHTML = `
        <div
            class="doctor-discharge-dialog"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="doctorDischargeTitle">

            <h3 id="doctorDischargeTitle">
                Discharge Patient?
            </h3>

            <p>
                This will complete the patient's
                current visit. Make sure the clinical
                assessment has been completed.
            </p>

            <div class="doctor-discharge-actions">

                <button
                    type="button"
                    class="doctor-discharge-cancel"
                    data-discharge-cancel>
                    Cancel
                </button>

                <button
                    type="button"
                    class="doctor-discharge-confirm"
                    data-discharge-confirm>
                    Confirm Discharge
                </button>

            </div>

        </div>
    `;


    dischargeOverlay
        .querySelector(
            "[data-discharge-cancel]"
        )
        ?.addEventListener(
            "click",
            destroyDischargeOverlay
        );


    dischargeOverlay
        .querySelector(
            "[data-discharge-confirm]"
        )
        ?.addEventListener(
            "click",
            handleDischarge
        );


    document.body.appendChild(
        dischargeOverlay
    );
}


async function handleDischarge() {
    const patient = getMyActivePatient();

    const visitId =
        patient?.visit_id ??
        patient?.visit?.visit_id;

    if (!visitId) {
        destroyDischargeOverlay();

        showError(
            "Unable to discharge: visit ID is missing."
        );

        return;
    }

    const button =
        dischargeOverlay?.querySelector(
            "[data-discharge-confirm]"
        );

    if (button) {
        button.disabled = true;
    }

    try {

        await dischargeFromCare(
            visitId
        );

        destroyDischargeOverlay();

        if (
            typeof callbacks.onActionCompleted ===
            "function"
        ) {
            await callbacks.onActionCompleted();
        }

    } catch (error) {

        if (button) {
            button.disabled = false;
        }

        const message =
            error?.message ||
            "Unable to discharge patient.";

        const dialog =
            dischargeOverlay?.querySelector(
                ".doctor-discharge-dialog"
            );

        if (dialog) {
            const errorElement =
                document.createElement("div");

            errorElement.className =
                "doctor-discharge-error";

            errorElement.textContent =
                message;

            dialog.prepend(errorElement);
        }
    }
}


function destroyDischargeOverlay() {
    if (dischargeOverlay) {
        dischargeOverlay.remove();
        dischargeOverlay = null;
    }
}


/* ==========================================================================
   CLINICAL LISTENERS
   ========================================================================== */

function attachClinicalListeners() {
    const findings = container?.querySelector(
        "#doctorClinicalFindings"
    );

    const diagnosis = container?.querySelector(
        "#doctorDiagnosis"
    );

    const treatmentPlan = container?.querySelector(
        "#doctorTreatmentPlan"
    );

    const findingsCount = container?.querySelector(
        "#clinicalFindingsCount"
    );

    const diagnosisCount = container?.querySelector(
        "#diagnosisCount"
    );

    const treatmentCount = container?.querySelector(
        "#treatmentPlanCount"
    );

    findings?.addEventListener("input", event => {
        draft.clinicalFindings = event.target.value;

        if (findingsCount) {
            findingsCount.textContent =
                draft.clinicalFindings.length;
        }
    });

    diagnosis?.addEventListener("input", event => {
        draft.diagnosis = event.target.value;

        if (diagnosisCount) {
            diagnosisCount.textContent =
                draft.diagnosis.length;
        }
    });

    treatmentPlan?.addEventListener("input", event => {
        draft.treatmentPlan = event.target.value;

        if (treatmentCount) {
            treatmentCount.textContent =
                draft.treatmentPlan.length;
        }
    });

    const saveButton = container?.querySelector(
        "#saveClinicalAssessmentBtn"
    );

    saveButton?.addEventListener(
        "click",
        handleSaveClinicalAssessment
    );
}


/* ==========================================================================
   LISTENERS
   ========================================================================== */

function attachListeners(patient) {
    attachPriorityListener();
    attachClinicalListeners();

    container
        ?.querySelector("#doctorRouteBtn")
        ?.addEventListener(
            "click",
            openRouting
        );

    container
        ?.querySelector("#doctorDischargeBtn")
        ?.addEventListener(
            "click",
            openDischargeConfirmation
        );
}


/* ==========================================================================
   DRAFT MANAGEMENT
   ========================================================================== */

function resetDraft() {
    draft = {
        clinicalFindings: "",
        diagnosis: "",
        treatmentPlan: "",
    };

    draftVisitId = null;
}


function prepareDraftForPatient(patient) {
    const visitId =
        patient?.visit_id ??
        patient?.visit?.visit_id ??
        null;

    if (!visitId) {
        return;
    }

    if (draftVisitId === visitId) {
        return;
    }

    draftVisitId = visitId;

    draft = {
        clinicalFindings:
            getPersistedClinicalFindings(patient),

        diagnosis:
            getPersistedDiagnosis(patient),

        treatmentPlan:
            getPersistedTreatmentPlan(patient),
    };
}


/* ==========================================================================
   PERSISTED CLINICAL DATA
   ========================================================================== */

function getPersistedClinicalFindings(patient) {
    return (
        patient?.visit?.clinical_findings ??
        patient?.clinical_findings ??
        ""
    );
}


function getPersistedDiagnosis(patient) {
    return (
        patient?.visit?.diagnosis ??
        patient?.diagnosis ??
        ""
    );
}


function getPersistedTreatmentPlan(patient) {
    return (
        patient?.visit?.treatment_plan ??
        patient?.treatment_plan ??
        ""
    );
}


function getChiefComplaint(patient) {
    return (
        patient?.visit?.chief_complaint ??
        patient?.chief_complaint ??
        ""
    );
}


function getTriageAssessment(patient) {
    return (
        patient?.visit?.triage_assessment ??
        patient?.triage_assessment ??
        ""
    );
}


function getPersistedVitals(patient) {
    return (
        patient?.vitals ??
        patient?.latest_vitals ??
        patient?.visit?.latest_vitals ??
        null
    );
}


/* ==========================================================================
   DESTINATION HELPERS
   ========================================================================== */

function isValidDestination(patient, department) {
    const currentDeptId =
        patient?.dept_id ??
        patient?.visit?.dept_id;

    const destinationId =
        department?.dept_id ??
        department?.department_id;

    if (
        currentDeptId == null ||
        destinationId == null
    ) {
        return false;
    }

    return (
        String(destinationId) !==
        String(currentDeptId)
    );
}


/* ==========================================================================
   UI STATE
   ========================================================================== */

function setActionBusy(busy) {
    if (!container) {
        return;
    }

    container
        .querySelectorAll(
            "button, textarea, input, select"
        )
        .forEach(element => {
            element.disabled = busy;
        });
}


function setDrawerBusy(busy) {
    if (!routingDrawer) {
        return;
    }

    routingDrawer
        .querySelectorAll(
            "button, textarea, select"
        )
        .forEach(element => {
            element.disabled = busy;
        });
}





/* ==========================================================================
   ERROR HANDLING
   ========================================================================== */

function showError(message) {
    if (!container) {
        return;
    }

    let error =
        container.querySelector(
            "[data-doctor-error]"
        );

    if (!error) {
        error =
            document.createElement("div");

        error.className =
            "doctor-error";

        container.prepend(error);
    }

    error.textContent = message;
    error.hidden = false;
}


function clearDoctorError() {
    const error =
        container?.querySelector(
            "[data-doctor-error]"
        );

    if (error) {
        error.textContent = "";
        error.hidden = true;
    }
}


function showRoutingError(message) {
    const error =
        routingDrawer?.querySelector(
            "[data-route-error]"
        );

    if (!error) {
        return;
    }

    error.textContent = message;
    error.hidden = false;
}


/* ==========================================================================
   NO PATIENT
   ========================================================================== */

function renderNoPatient() {
    container.innerHTML = `
        <section class="doctor-workspace doctor-no-patient">

            <div class="doctor-empty-icon">
                +
            </div>

            <h3>
                No Active Patient
            </h3>

            <p>
                Call and start a patient to begin
                the clinical consultation.
            </p>

        </section>
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