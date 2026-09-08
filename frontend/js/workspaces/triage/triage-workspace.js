/* ==========================================================================
   HPQMS Triage Workspace
   workspaces/triage/triage-workspace.js

   Triage-specific encounter workspace.
   - Displays vitals + chief complaint
   - Collects vitals AND assessment notes together via a single
     Assessment Drawer, then shows both read-only in the main view
   - Sets priority ONCE (key UX principle)
   - Routes with confirmed priority (read-only in drawer)

   -----------------------------------------------------------------------
   Single entry point for vitals + assessment
   -----------------------------------------------------------------------
   Vitals entry and assessment notes used to be two separate concerns:
   a "Retake" button that called an external callbacks.onRetakeVitals()
   hand-off, and a separate "Add Assessment" trigger for chief
   complaint/notes only (with no way to actually enter vitals values at
   all). Both now live in one Assessment Drawer, opened by one button
   next to the "Recorded Vitals" header — labeled "+ Add Assessment"
   when nothing has been recorded yet, and "↻ Retake" once it has. This
   preserves the vitals section's visual priority (the button sits next
   to the primary heading, not buried under Clinical Observations) and
   means onRetakeVitals is no longer called by this workspace at all —
   if a parent still wires that callback, it's now dead code there.

   ========================================================================== */

import {
    getMyActivePatient,
    subscribe,
} from "../../staff-queue-state.js";

import {
    updatePriority,
} from "../../staff-actions.js";

import * as triageActions
    from "./triage-actions.js";



let container = null;
let unsubscribe = null;
let callbacks = {};
let lastRenderSignature = null;

// The confirmed vitals + assessment (chief complaint + clinical notes),
// or null until the nurse has confirmed one via the Assessment Drawer.
// Drives the read-only summary shown in the main view. Shape:
// { vitals: { heart_rate, blood_pressure: {systolic, diastolic},
//   temperature, oxygen_saturation, recorded_at },
//   chief_complaint, notes, confirmed_at }
let confirmedAssessment = null;


/* ==========================================================================
   PUBLIC API
   ========================================================================== */

export function mount(target, options = {}) {
    if (!(target instanceof HTMLElement)) {
        throw new TypeError(
            "TriageWorkspace mount target must be an HTMLElement."
        );
    }

    unmount();

    container = target;
    callbacks = options;
    lastRenderSignature = null;
    confirmedAssessment = null;

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

    destroyRoutingDrawer();
    destroyAssessmentDrawer();
    destroyPriorityConfirm();
    pendingPriority = null;

    if (container) {
        container.innerHTML = "";
    }

    container = null;
    callbacks = {};
    lastRenderSignature = null;
    confirmedAssessment = null;
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

    const signature = computeRenderSignature(patient);
    if (signature === lastRenderSignature) {
        return;
    }
    lastRenderSignature = signature;

    renderTriageEncounter(patient);
}


function computeRenderSignature(patient) {
    return JSON.stringify({
        id: patient.queue_entry_id ?? patient.visit_id ?? null,
        status: patient.status,
        priority: patient.priority,
        first_name: patient.visit?.patient?.first_name,
        last_name: patient.visit?.patient?.last_name,
        // Confirming an assessment (vitals + notes) is a local-only
        // state change (see note at top of file) — including the whole
        // object here means confirming actually triggers a re-render
        // instead of being silently skipped by the signature guard.
        chief_complaint: getChiefComplaint(patient),
        triage_assessment: getTriageAssessment(patient),
        latest_vitals: getPersistedVitals(patient),
        assessment: confirmedAssessment,
    });
}


/* ==========================================================================
   MAIN VIEW
   ========================================================================== */

function renderTriageEncounter(patient) {
    const vitals = getVitals(patient);
    const hasVitals = Boolean(
        vitals.heart_rate ||
        vitals.blood_pressure ||
        vitals.temperature ||
        vitals.spo2
    );
    const chiefComplaint =
        confirmedAssessment?.chief_complaint ??
        getChiefComplaint(patient);
    const currentPriority = patient.priority ?? "NORMAL";

    container.innerHTML = `
        <section class="triage-workspace">

            <!-- Scrollable content area -->
            <div class="triage-scroll-container">

                <!-- 1. VITAL SIGNS SECTION -->
                <div class="triage-section">

                    <div class="triage-section-subheader">
                        <div>
                            <span class="triage-eyebrow">VITAL SIGNS</span>
                            <h3>Recorded Vitals ${vitals?.timestamp ? `(${vitals.timestamp})` : ''}</h3>
                        </div>
                        <button
                            type="button"
                            class="triage-retake-btn"
                            id="openAssessmentBtn"
                            title="${hasVitals ? 'Retake vitals & update assessment' : 'Record vitals & assessment'}">
                            ${hasVitals ? '↻ Retake Assessment' : '+ Add Assessment'}
                        </button>
                    </div>

                    <div class="triage-vitals-grid">
                        ${renderVitalCard('Heart Rate', vitals?.heart_rate, 'bpm', vitals?.heart_rate_abnormal, 'pulse')}
                        ${renderVitalCard('Blood Pressure', vitals?.blood_pressure, 'mmHg', vitals?.bp_abnormal, 'pulse')}
                        ${renderVitalCard('Temperature', vitals?.temperature, '°C', vitals?.temp_abnormal, 'thermometer')}
                        ${renderVitalCard('SpO2 Oxygen', vitals?.spo2, '%', vitals?.spo2_abnormal, 'airflow')}
                        ${renderVitalCard('Resp Rate', vitals?.respiratory_rate, 'bpm', vitals?.rr_abnormal, 'airflow')}
                    </div>

                </div>

                <!-- 2. CHIEF COMPLAINT SECTION -->
                <div class="triage-section">

                    <div>
                        <span class="triage-eyebrow">PRESENTATION</span>
                        <h3>Chief Complaint & Notes</h3>
                    </div>

                    ${chiefComplaint
                        ? `<div class="triage-chief-complaint">
                                <p class="triage-chief-complaint-text">
                                    ${escapeHtml(chiefComplaint)}
                                </p>
                            </div>`
                        : `<p style="color: var(--color-text-muted); font-size: 13px; margin: 0;">
                                No chief complaint recorded.
                            </p>`
                    }

                </div>

                <!-- 3. CLINICAL ASSESSMENT SECTION -->
                <div class="triage-section">

                    <div>
                        <span class="triage-eyebrow">ASSESSMENT</span>
                        <h3>Clinical Observations</h3>
                    </div>

                    ${getTriageAssessment(patient)
                        ? `<div class="triage-chief-complaint">
                                <p class="triage-chief-complaint-text">
                                    ${escapeHtml(getTriageAssessment(patient))}
                                </p>
                            </div>`
                        : `<p style="color: var(--color-text-muted); font-size: 13px; margin: 0;">
                                No assessment recorded yet. Use the button above the vital signs to
                                document vitals, chief complaint, and clinical findings.
                            </p>`
                    }

                </div>

                <!-- 4. TRIAGE PRIORITY SECTION -->
                <div class="triage-section">

                    <div>
                        <span class="triage-eyebrow">TRIAGE PRIORITY</span>
                        <h3>Patient Acuity Level</h3>
                    </div>

                    <div class="triage-priority-section">

                        <div class="triage-priority-current">
                            <span class="triage-priority-current-label">Current Priority</span>
                            <span class="triage-priority-badge ${currentPriority ? currentPriority.toLowerCase() : 'unassigned'}">
                                ${escapeHtml(currentPriority || 'UNASSIGNED')}
                            </span>
                        </div>

                        <!-- Queue priority determines this patient's routing order. -->
                        <div class="triage-priority-options">

                            <div class="triage-priority-option">
                                <input
                                    type="radio"
                                    id="priorityCritical"
                                    name="priority"
                                    value="CRITICAL"
                                    ${currentPriority === 'CRITICAL' ? 'checked' : ''}>
                                <label for="priorityCritical">Critical</label>
                            </div>

                            <div class="triage-priority-option">
                                <input
                                    type="radio"
                                    id="priorityUrgent"
                                    name="priority"
                                    value="URGENT"
                                    ${currentPriority === 'URGENT' ? 'checked' : ''}>
                                <label for="priorityUrgent">Urgent</label>
                            </div>

                            <div class="triage-priority-option">
                                <input
                                    type="radio"
                                    id="prioritySemiUrgent"
                                    name="priority"
                                    value="SEMI_URGENT"
                                    ${currentPriority === 'SEMI_URGENT' ? 'checked' : ''}>
                                <label for="prioritySemiUrgent">Semi-Urgent</label>
                            </div>

                            <div class="triage-priority-option">
                                <input
                                    type="radio"
                                    id="priorityNormal"
                                    name="priority"
                                    value="NORMAL"
                                    ${currentPriority === 'NORMAL' ? 'checked' : ''}>
                                <label for="priorityNormal">Normal</label>
                            </div>

                        </div>

                    </div>

                </div>

            </div>

            <!-- Fixed action buttons at bottom -->
            ${renderActionButtons(patient, currentPriority)}

        </section>
    `;

    attachListeners(patient);
}


/* ==========================================================================
   VITAL CARD RENDERING
   ========================================================================== */

function renderVitalCard(label, value, unit, isAbnormal = false, icon = 'pulse') {
    const vitalIcon = renderVitalIcon(icon);

    if (!value) {
        return `
            <div class="triage-vital-card">
                <span class="triage-vital-symbol" aria-hidden="true" style="position:absolute;top:14px;right:14px;width:18px;height:18px">${vitalIcon}</span>
                <div class="triage-vital-label">${escapeHtml(label)}</div>
                <div style="color: var(--color-text-muted); font-size: 13px;">
                    Not recorded
                </div>
            </div>
        `;
    }

    return `
        <div class="triage-vital-card ${isAbnormal ? 'abnormal' : ''}">
            <span class="triage-vital-symbol" aria-hidden="true" style="position:absolute;top:14px;right:14px;width:18px;height:18px">${vitalIcon}</span>
            <div class="triage-vital-label">${escapeHtml(label)}</div>
            <div class="triage-vital-value">
                ${escapeHtml(String(value))}
                <span class="triage-vital-unit">${escapeHtml(unit)}</span>
            </div>
            ${isAbnormal ? '<div class="triage-vital-icon">!</div>' : ''}
        </div>
    `;
}

function renderVitalIcon(icon) {
    const icons = {
        pulse: '<svg viewBox="0 0 24 24" width="18" height="18" style="width:18px;height:18px;display:block" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12h4l2.1-6 3.8 12 2.2-7H16l1.8-3 2.2 4H22"/></svg>',
        thermometer: '<svg viewBox="0 0 24 24" width="18" height="18" style="width:18px;height:18px;display:block" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 14.8V5a3 3 0 0 0-6 0v9.8a5 5 0 1 0 6 0Z"/><path d="M11 5v10"/></svg>',
        airflow: '<svg viewBox="0 0 24 24" width="18" height="18" style="width:18px;height:18px;display:block" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 8h11a3 3 0 1 0-3-3"/><path d="M3 12h15a3 3 0 1 1-3 3"/><path d="M3 16h8"/></svg>',
    };

    return icons[icon] ?? icons.pulse;
}


/* ==========================================================================
   ACTION BUTTONS (FIXED)
   ========================================================================== */

function renderActionButtons(patient, currentPriority) {
    return `
        <div class="triage-action-controls">

            <button
                type="button"
                class="triage-workflow-btn triage-workflow-primary"
                id="completeTriageBtn"
                data-action="complete-triage">

                <span class="triage-action-icon">✓</span>
                <span>Complete Triage & Route</span>

            </button>

        </div>
    `;
}


/* ==========================================================================
   NO PATIENT
   ========================================================================== */

function renderNoPatient() {
    container.innerHTML = `
        <section class="triage-workspace triage-no-patient">

            <div class="triage-empty-icon">
                +
            </div>

            <h3>
                No Active Patient
            </h3>

            <p>
                Call and start a patient to begin triage.
            </p>

        </section>
    `;
}


/* ==========================================================================
   EVENT HANDLERS
   ========================================================================== */

function attachListeners(patient) {
    attachPriorityListener();
    attachActionListeners(patient);
    attachAssessmentOpenListener(patient);
}


function attachPriorityListener() {
    const priorityRadios = container?.querySelectorAll('input[name="priority"]');

    if (!priorityRadios) return;

    priorityRadios.forEach(radio => {
        radio.addEventListener("change", async (e) => {
            if (e.target.checked) {
                await handlePriorityChange(e.target.value);
            }
        });
    });
}


/*
 * Priority/acuity is a consequential clinical decision, so selecting a
 * radio button does NOT change it immediately. Instead the change is
 * staged and a small confirm banner freezes the page until the nurse
 * confirms (applies the change) or cancels (the previous priority is
 * preserved and the radio reverts).
 */
let priorityConfirmOverlay = null;
let pendingPriority = null;


async function handlePriorityChange(newPriority) {
    const patient = getMyActivePatient();
    if (!patient?.queue_entry_id) {
        showError("Unable to update priority: queue entry ID missing.");
        render();
        return;
    }

    if (newPriority === (patient.priority ?? "NORMAL")) {
        return; // No actual change
    }

    openPriorityConfirm(patient, newPriority);
}


function openPriorityConfirm(patient, newPriority) {
    destroyPriorityConfirm();

    pendingPriority = newPriority;

    const currentPriority = patient.priority ?? "NORMAL";

    priorityConfirmOverlay = document.createElement("div");
    priorityConfirmOverlay.className = "triage-priority-confirm";

    priorityConfirmOverlay.innerHTML = `
        <div class="triage-priority-confirm-banner" role="alertdialog"
            aria-modal="true"
            aria-labelledby="priorityConfirmTitle">

            <h4 id="priorityConfirmTitle">Confirm acuity change</h4>

            <p>
                Change priority from
                <strong>${escapeHtml(currentPriority)}</strong> to
                <strong>${escapeHtml(newPriority)}</strong>?
            </p>

            <div class="triage-priority-confirm-actions">

                <button
                    type="button"
                    class="triage-confirm-btn triage-confirm-cancel"
                    data-priority-cancel>
                    Cancel
                </button>

                <button
                    type="button"
                    class="triage-confirm-btn triage-confirm-apply"
                    data-priority-confirm>
                    Confirm
                </button>

            </div>

        </div>
    `;

    priorityConfirmOverlay
        .querySelector("[data-priority-confirm]")
        .addEventListener("click", applyPriorityChange);

    priorityConfirmOverlay
        .querySelector("[data-priority-cancel]")
        .addEventListener("click", cancelPriorityChange);

    // Appended to <body> so re-renders of the workspace can never
    // wipe the confirmation while it is pending.
    document.body.appendChild(priorityConfirmOverlay);
}


async function applyPriorityChange() {
    const patient = getMyActivePatient();
    const newPriority = pendingPriority;

    if (!patient?.queue_entry_id || !newPriority) {
        destroyPriorityConfirm();
        render();
        return;
    }

    const confirmBtn = priorityConfirmOverlay?.querySelector(
        "[data-priority-confirm]"
    );
    if (confirmBtn) confirmBtn.disabled = true;

    try {
        await updatePriority(patient.queue_entry_id, newPriority);

        destroyPriorityConfirm();
        pendingPriority = null;

        if (typeof callbacks.onPriorityChanged === "function") {
            await callbacks.onPriorityChanged(newPriority);
        }

        // Queue state reconciles from the backend response, so the
        // "Current Priority" badge now reflects the new acuity.
        render();

    } catch (error) {
        destroyPriorityConfirm();
        pendingPriority = null;
        showError(error?.message || "Unable to update priority.");
        // Revert the radio button to the preserved priority
        render();
    }
}


function cancelPriorityChange() {
    destroyPriorityConfirm();
    pendingPriority = null;

    // The previous priority is preserved — re-render so the radio
    // selection reverts to the current acuity level.
    render();
}


function destroyPriorityConfirm() {
    if (priorityConfirmOverlay) {
        priorityConfirmOverlay.remove();
        priorityConfirmOverlay = null;
    }
}


function attachAssessmentOpenListener(patient) {
    const openBtn = container?.querySelector("#openAssessmentBtn");

    if (openBtn) {
        openBtn.addEventListener("click", () => {
            openAssessmentDrawer(patient);
        });
    }
}


function attachActionListeners(patient) {
    const completeBtn = container?.querySelector("#completeTriageBtn");
    if (completeBtn) {
        completeBtn.addEventListener("click", () => {
            handleCompleteTriageAndRoute(patient);
        });
    }
}


/* ==========================================================================
   ASSESSMENT DRAWER (vitals entry + chief complaint + clinical notes)
   ========================================================================== */

let assessmentDrawer = null;

/**
 * Opens the Triage Assessment Drawer, where the nurse enters vitals,
 * chief complaint, and clinical observations, then confirms. Reuses
 * the same visual chrome (.triage-routing-*) as the routing drawer
 * below — that CSS isn't actually routing-specific, it's a generic
 * slide-in panel, so there's no need for a parallel set of
 * "assessment" CSS classes just to get the same look. The vitals
 * number inputs use their own small .triage-vitals-input-* classes
 * (added alongside this file) since the existing .triage-routing-select
 * class bakes in a dropdown-arrow background meant for <select>, which
 * would look wrong on a plain number input.
 */
function openAssessmentDrawer(patient) {
    destroyAssessmentDrawer();

    const existingVitals = getRawVitals(patient);
    const chiefComplaint =
        confirmedAssessment?.chief_complaint ??
        getChiefComplaint(patient) ??
        "";
    const existingNotes = getTriageAssessment(patient) ?? "";
    const isEditing = Boolean(confirmedAssessment);

    assessmentDrawer = document.createElement("div");
    assessmentDrawer.className = "triage-routing-drawer";

    assessmentDrawer.innerHTML = `
        <div class="triage-routing-drawer-overlay"></div>

        <div class="triage-routing-panel">

            <div class="triage-routing-header">
                <div>
                    <span class="triage-eyebrow">TRIAGE ASSESSMENT</span>
                    <h3>${isEditing ? 'Update Assessment' : 'Record Assessment'}</h3>
                </div>

                <button
                    type="button"
                    class="triage-routing-close"
                    data-close-assessment>
                    ×
                </button>
            </div>

            <form id="triageAssessmentForm" class="triage-routing-form">

                <!-- 1. VITAL SIGNS SECTION -->
                <div class="triage-routing-section">
                    <label>Vital Signs</label>

                    <div class="triage-vitals-input-grid">

                        <div class="triage-vitals-input-field">
                            <label for="vitalsHeartRate">Heart Rate (bpm)</label>
                            <input
                                type="number"
                                id="vitalsHeartRate"
                                name="heart_rate"
                                min="0"
                                max="300"
                                placeholder="e.g. 78"
                                value="${existingVitals.heart_rate ?? ''}">
                        </div>

                        <!-- Fixed: Flat systolic_bp & diastolic_bp names -->
                        <div class="triage-vitals-input-field triage-vitals-bp">
                            <label>Blood Pressure (mmHg)</label>
                            <div class="triage-bp-inputs">
                                <input
                                    type="number"
                                    id="vitalsSystolic"
                                    name="systolic_bp"
                                    min="0"
                                    max="300"
                                    placeholder="Systolic"
                                    value="${existingVitals.systolic_bp ?? ''}">
                                <span>/</span>
                                <input
                                    type="number"
                                    id="vitalsDiastolic"
                                    name="diastolic_bp"
                                    min="0"
                                    max="200"
                                    placeholder="Diastolic"
                                    value="${existingVitals.diastolic_bp ?? ''}">
                            </div>
                        </div>

                        <div class="triage-vitals-input-field">
                            <label for="vitalsTemperature">Temperature (°C)</label>
                            <input
                                type="number"
                                step="0.1"
                                id="vitalsTemperature"
                                name="temperature"
                                min="30"
                                max="45"
                                placeholder="e.g. 36.8"
                                value="${existingVitals.temperature ?? ''}">
                        </div>

                        <div class="triage-vitals-input-field">
                            <label for="vitalsSpo2">SpO2 (%)</label>
                            <input
                                type="number"
                                id="vitalsSpo2"
                                name="oxygen_saturation"
                                min="0"
                                max="100"
                                placeholder="e.g. 98"
                                value="${existingVitals.oxygen_saturation ?? ''}">
                        </div>

                        <!-- Added: Respiratory Rate (Matching Vitals Model) -->
                        <div class="triage-vitals-input-field">
                            <label for="vitalsRespiratoryRate">Resp Rate (bpm)</label>
                            <input
                                type="number"
                                id="vitalsRespiratoryRate"
                                name="respiratory_rate"
                                min="0"
                                max="100"
                                placeholder="e.g. 16"
                                value="${existingVitals.respiratory_rate ?? ''}">
                        </div>

                        <!-- Added: Weight (Matching Vitals Model) -->
                        <div class="triage-vitals-input-field">
                            <label for="vitalsWeight">Weight (kg)</label>
                            <input
                                type="number"
                                step="0.1"
                                id="vitalsWeight"
                                name="weight"
                                min="0"
                                max="500"
                                placeholder="e.g. 70.5"
                                value="${existingVitals.weight ?? ''}">
                        </div>

                    </div>
                </div>

                <!-- 2. CHIEF COMPLAINT SECTION -->
                <div class="triage-routing-section">
                    <label for="assessmentChiefComplaint">Chief Complaint</label>
                    <textarea
                        id="assessmentChiefComplaint"
                        name="chief_complaint"
                        rows="2"
                        maxlength="500"
                        placeholder="What is the patient presenting with?"
                        class="triage-routing-textarea"
                    >${escapeHtml(chiefComplaint)}</textarea>
                </div>

                <!-- 3. CLINICAL ASSESSMENT (Fixed: name="triage_assessment") -->
                <div class="triage-routing-section">
                    <label for="assessmentNotesInput">Clinical Assessment</label>
                    <textarea
                        id="assessmentNotesInput"
                        name="triage_assessment"
                        rows="5"
                        maxlength="2000"
                        placeholder="Document clinical assessment, findings, and triage logic..."
                        class="triage-routing-textarea"
                    >${escapeHtml(existingNotes)}</textarea>

                    <small style="color: var(--color-text-muted); font-size: 11px;">
                        Character count: <span id="assessmentCharCount">${existingNotes.length}</span>/2000
                    </small>
                </div>

                <div class="triage-routing-error" data-assessment-error hidden></div>

                <div class="triage-routing-actions">
                    <button
                        type="button"
                        class="triage-routing-btn secondary"
                        data-close-assessment>
                        Cancel
                    </button>

                    <button
                        type="submit"
                        class="triage-routing-btn primary">
                        Confirm Assessment
                    </button>
                </div>

            </form>
        </div>
    `;

    document.body.appendChild(assessmentDrawer);

    const closeButtons = assessmentDrawer.querySelectorAll("[data-close-assessment]");
    closeButtons.forEach(button => {
        button.addEventListener("click", destroyAssessmentDrawer);
    });

    const overlay = assessmentDrawer.querySelector(".triage-routing-drawer-overlay");
    if (overlay) {
        overlay.addEventListener("click", destroyAssessmentDrawer);
    }

    const notesTextarea = assessmentDrawer.querySelector("#assessmentNotesInput");
    const charCount = assessmentDrawer.querySelector("#assessmentCharCount");
    notesTextarea?.addEventListener("input", () => {
        if (charCount) {
            charCount.textContent = notesTextarea.value.length;
        }
    });

    const form = assessmentDrawer.querySelector("#triageAssessmentForm");
    form.addEventListener("submit", (event) => {
        event.preventDefault();
        handleConfirmAssessment(form);
    });
}


async function handleConfirmAssessment(form) {
    const data = new FormData(form);

    // Extract assessment & routing text fields
    const chiefComplaint = (data.get("chief_complaint") || "").toString().trim();
    const triageAssessment = (data.get("triage_assessment") || "").toString().trim();

    // Extract vitals matching flat backend column names
    const heartRate = parseNumberOrNull(data.get("heart_rate"));
    const systolicBp = parseNumberOrNull(data.get("systolic_bp"));
    const diastolicBp = parseNumberOrNull(data.get("diastolic_bp"));
    const temperature = parseNumberOrNull(data.get("temperature"));
    const oxygenSaturation = parseNumberOrNull(data.get("oxygen_saturation"));
    const respiratoryRate = parseNumberOrNull(data.get("respiratory_rate"));
    const weight = parseNumberOrNull(data.get("weight"));

    // Validation checks
    if (!triageAssessment) {
        showAssessmentError("Clinical assessment notes are required before confirming.");
        return;
    }

    // Build flat vitals payload (matching ORM model)
    const vitalsPayload = {
        heart_rate: heartRate,
        systolic_bp: systolicBp,
        diastolic_bp: diastolicBp,
        temperature: temperature,
        oxygen_saturation: oxygenSaturation,
        respiratory_rate: respiratoryRate,
        weight: weight,
        recorded_at: new Date().toISOString()
    };

    // Update confirmed assessment local state
    confirmedAssessment = {
        vitals: vitalsPayload,
        chief_complaint: chiefComplaint || null,
        triage_assessment: triageAssessment,
        confirmed_at: new Date().toISOString()
    };

    // Optional API dispatch if integrating with live backend endpoints:

    try {
        const patient = getMyActivePatient();
        const visitId = patient?.visit_id ?? patient?.visit?.visit_id;

        if (!visitId) {
            showAssessmentError("Unable to identify the active visit for this patient.");
            return;
        }

        // 1. Post vitals if at least one vital sign entry was provided
        const hasVitals = Object.entries(vitalsPayload)
            .some(([key, val]) => key !== 'recorded_at' && val !== null);

        if (hasVitals) {
            await triageActions.recordPatientVitals(visitId, vitalsPayload);
        }

        // 2. Patch clinical assessment fields.
        await triageActions.updateAssessment(visitId, {
            chief_complaint: confirmedAssessment.chief_complaint,
            triage_assessment: confirmedAssessment.triage_assessment
        });

        destroyAssessmentDrawer();
        render(); // Trigger view re-render
    } catch (error) {
        showAssessmentError(error.message || "Failed to persist triage assessment.");
        return;
    }



    destroyAssessmentDrawer();
    render();
}


function destroyAssessmentDrawer() {
    if (assessmentDrawer) {
        assessmentDrawer.remove();
        assessmentDrawer = null;
    }
}


function showAssessmentError(message) {
    if (!assessmentDrawer) {
        return;
    }

    const error = assessmentDrawer.querySelector("[data-assessment-error]");

    if (!error) {
        return;
    }

    error.textContent = message;
    error.hidden = false;
}


/* ==========================================================================
   COMPLETE TRIAGE & ROUTE
   ========================================================================== */

async function handleCompleteTriageAndRoute(patient) {
    const visitId = patient.visit_id ?? patient.visit?.visit_id;

    if (!visitId) {
        showError("Unable to route: visit ID is missing.");
        return;
    }

    try {
        setActionBusy(true);

        const departments = await triageActions.getDepartments();

        renderRoutingDrawer(
            patient,
            Array.isArray(departments)
                ? departments
                : departments?.items ?? [],
            patient.priority ?? "NORMAL"  // Pass current priority (read-only)
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


/* ==========================================================================
   ROUTING DRAWER (READ-ONLY PRIORITY)
   ========================================================================== */

let routingDrawer = null;

function renderRoutingDrawer(patient, departments, readOnlyPriority) {
    destroyRoutingDrawer();

    routingDrawer = document.createElement("div");
    routingDrawer.className = "triage-routing-drawer";

    routingDrawer.innerHTML = `
        <div class="triage-routing-drawer-overlay"></div>

        <div class="triage-routing-panel">

            <div class="triage-routing-header">

                <div>
                    <span class="triage-eyebrow">PATIENT ROUTING</span>
                    <h3>Complete Triage & Route</h3>
                </div>

                <button
                    type="button"
                    class="triage-routing-close"
                    data-close-routing>
                    ×
                </button>

            </div>

            <form id="triageRouteForm" class="triage-routing-form">

                <div class="triage-routing-section">

                    <label for="routeDepartment">
                        Destination Department
                    </label>

                    <select
                        id="routeDepartment"
                        name="target_dept_id"
                        required
                        class="triage-routing-select">

                        <option value="">Select department</option>

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

                <div class="triage-routing-section">

                    <label>Priority</label>

                    <div class="triage-priority-readonly">
                        ${escapeHtml(readOnlyPriority)}
                        <div class="triage-priority-readonly-note">
                            Priority determined during triage.
                        </div>
                    </div>

                </div>

                <div class="triage-routing-section">

                    <label for="routeNotes">
                        Notes <span class="triage-optional">(optional)</span>
                    </label>

                    <textarea
                        id="routeNotes"
                        name="notes"
                        rows="4"
                        maxlength="1000"
                        placeholder="Clinical routing notes..."
                        class="triage-routing-textarea"></textarea>

                </div>

                <div
                    class="triage-routing-error"
                    data-route-error
                    hidden></div>

                <div class="triage-routing-actions">

                    <button
                        type="button"
                        class="triage-routing-btn secondary"
                        data-close-routing>
                        Cancel
                    </button>

                    <button
                        type="submit"
                        class="triage-routing-btn primary">
                        Route Patient
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

    const overlay = routingDrawer.querySelector(".triage-routing-drawer-overlay");
    if (overlay) {
        overlay.addEventListener("click", destroyRoutingDrawer);
    }

    const form = routingDrawer.querySelector("#triageRouteForm");
    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        await submitRoute(patient, readOnlyPriority);
    });
}


async function submitRoute(patient, readOnlyPriority) {
    if (!routingDrawer) {
        return;
    }

    const form = routingDrawer.querySelector("#triageRouteForm");
    const data = new FormData(form);

    const targetDeptId = data.get("target_dept_id");
    const notes = data.get("notes")?.trim() || null;

    if (!targetDeptId) {
        return;
    }

    const visitId =
        patient.visit_id ??
        patient.visit?.visit_id;

    if (!visitId) {
        showRoutingError("Unable to route: visit ID is missing.");
        return;
    }

    try {
        setDrawerBusy(true);

        // Route with the read-only priority that was set during triage
        await triageActions.routePatient(
            visitId,
            targetDeptId,
            {
                priority: readOnlyPriority,  // Use the confirmed priority
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
            "Unable to route patient."
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
            .querySelectorAll("button, textarea, input[type='radio']")
            .forEach(element => {
                element.disabled = busy;
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

    let error = container.querySelector(".triage-error");

    if (!error) {
        error = document.createElement("div");
        error.className = "triage-error";
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
 * Raw vitals values, preferring anything locally confirmed via the
 * Assessment Drawer over whatever the patient record already has —
 * this is what the drawer's inputs are prefilled from.
 */
function getRawVitals(patient) {
    return confirmedAssessment?.vitals ?? getPersistedVitals(patient) ?? {};
}

function getPersistedVitals(patient) {
    return patient?.vitals ?? patient?.latest_vitals ?? patient?.visit?.latest_vitals ?? null;
}

/**
 * Derives display-ready vitals (formatted values + abnormal flags)
 * from a raw vitals object matching the flat ORM database schema.
 */
function deriveVitalsDisplay(vitals) {
    if (!vitals) return null;

    const sys = vitals.systolic_bp;
    const dia = vitals.diastolic_bp;

    return {
        timestamp: vitals.recorded_at ? formatTime(vitals.recorded_at) : null,
        heart_rate: vitals.heart_rate,
        heart_rate_abnormal:
            vitals.heart_rate != null &&
            (vitals.heart_rate > 100 || vitals.heart_rate < 60),

        // Formatted directly from flat systolic_bp / diastolic_bp
        blood_pressure: formatBloodPressure(sys, dia),
        bp_abnormal:
            (sys != null && (sys > 140 || sys < 90)) ||
            (dia != null && (dia > 90 || dia < 60)),

        temperature: vitals.temperature,
        temp_abnormal:
            vitals.temperature != null &&
            (vitals.temperature > 38.0 || vitals.temperature < 36.0),

        spo2: vitals.oxygen_saturation,
        spo2_abnormal:
            vitals.oxygen_saturation != null && vitals.oxygen_saturation < 95,

        respiratory_rate: vitals.respiratory_rate ?? null,
        rr_abnormal:
            vitals.respiratory_rate != null &&
            (vitals.respiratory_rate > 20 || vitals.respiratory_rate < 12),

        weight: vitals.weight ?? null,
    };
}

/**
 * Formats flat systolic and diastolic integer values into a single "120/80" string.
 */
function formatBloodPressure(systolic, diastolic) {
    if (systolic == null || diastolic == null) {
        return null;
    }
    return `${systolic}/${diastolic}`;
}

function getVitals(patient) {
    const rawVitals = getRawVitals(patient);
    return rawVitals ? deriveVitalsDisplay(rawVitals) : null;
}

function parseNumberOrNull(value) {
    if (value === null || value === undefined) {
        return null;
    }
    const strVal = String(value).trim();
    if (strVal === "") {
        return null;
    }
    const parsed = Number(strVal);
    return Number.isFinite(parsed) ? parsed : null;
}

function getChiefComplaint(patient) {
    return (
        patient?.visit?.chief_complaint ||
        patient?.chief_complaint ||
        null
    );
}

function getTriageAssessment(patient) {
    return (
        confirmedAssessment?.triage_assessment ??
        patient?.triage_assessment ??
        patient?.visit?.triage_assessment ??
        null
    );
}

function formatTime(timestamp) {
    if (!timestamp) return null;

    const date = new Date(timestamp);
    if (isNaN(date.getTime())) return null;

    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');

    return `${hours}:${minutes}`;
}

function isValidDestination(patient, department) {
    const currentDeptId = patient?.dept_id ?? patient?.visit?.dept_id;
    const destinationId = department?.dept_id ?? department?.department_id;

    if (currentDeptId == null || destinationId == null) {
        return false;
    }

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
