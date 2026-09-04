/* ==========================================================================
   HPQMS Staff Dashboard — GlobalShell (A4.1e rebuild)
   --------------------------------------------------------------------------
   Thin controller over the state store.

   Data flow (no component ever calls staff-api directly for state changes):

       WebSocket event / user intent
               ↓
       action handler (this file)
               ↓
       staff-api.js  →  backend
               ↓
       staff-queue-state.js  (single source of truth, notifies subscribers)
               ↓
       render(state)

   Selection ("which row did I click?") is deliberately separate from
   the active encounter ("which patient am I serving?") — see
   selectedQueueEntryId vs activePatient in staff-queue-state.js.

   The previous monolithic controller is preserved as staff.js.old and
   serves as the reference implementation for legacy behavior.
   ========================================================================== */

import {
    logout,
    getDepartmentQueue,
    getDepartmentNoShowQueue,
    callQueueEntry,
    startQueueEntry,
    completeQueueEntry,
    markNoShowQueueEntry,
    requeueQueueEntry,
    getNextPatient,
    getCurrentUser,
    completePatientRegistration,
} from "./staff-api.js";

import {
    getSession,
} from "./staff-session.js";

import {
    clearStaffContext,
    initializeStaffContext,
} from "./staff-context.js";

import {
    connect as connectStaffWebSocket,
    disconnect as disconnectStaffWebSocket,
    on as onStaffWebSocket,
    off as offStaffWebSocket,
} from "./staff-websocket.js";

import {
    clear as clearQueueState,
    setContext,
    setSnapshot,
    applyEvent,
    selectQueueEntry,
    getSelectedQueueEntry,
    getMyActivePatient,
    isMyPatient,
    markStale,
    subscribe,
} from "./staff-queue-state.js";

/* ==========================================================================
   DOM REFERENCES
   ========================================================================== */

const elements = {
    dashboardSubtitle: document.getElementById("dashboard-subtitle"),
    logoutButton: document.getElementById("logout-button"),
    queuePanel: document.getElementById("queue-panel"),
    queueState: document.getElementById("queue-state"),
    queueTable: document.getElementById("queue-table"),
    queueBody: document.getElementById("queue-body"),
    currentPatientPanel: document.getElementById("current-patient-panel"),
    currentToken: document.getElementById("current-token"),
    currentStatus: document.getElementById("current-status"),
    currentPatient: document.getElementById("current-patient"),
    currentPriority: document.getElementById("current-priority"),
    currentOwner: document.getElementById("current-owner"),
    callButton: document.getElementById("call-button"),
    startButton: document.getElementById("start-button"),
    noShowButton: document.getElementById("noshow-button"),
    completeButton: document.getElementById("complete-button"),
    actionError: document.getElementById("action-error"),
    noShowPanel: document.getElementById("no-show-panel"),
    noShowTable: document.getElementById("no-show-table"),
    noShowBody: document.getElementById("no-show-body"),
    noShowState: document.getElementById("no-show-state"),

    // Registration drawer
    registrationOverlay: document.getElementById("registration-overlay"),
    registrationDrawer: document.getElementById("registration-drawer"),
    drawerCloseButton: document.getElementById("drawer-close-button"),
    drawerCancelButton: document.getElementById("drawer-cancel-button"),
    drawerSubmitButton: document.getElementById("drawer-submit-button"),
    drawerError: document.getElementById("drawer-error"),
    patientRegistrationForm: document.getElementById("patient-registration-form"),
    registrationFirstName: document.getElementById("registration-first-name"),
    registrationLastName: document.getElementById("registration-last-name"),
    registrationDateOfBirth: document.getElementById("registration-date-of-birth"),
    registrationGender: document.getElementById("registration-gender"),
    registrationNationalId: document.getElementById("registration-national-id"),
    registrationPhone: document.getElementById("registration-phone"),
    registrationEmail: document.getElementById("registration-email"),
    registrationBloodType: document.getElementById("registration-blood-type"),
    registrationAllergies: document.getElementById("registration-allergies"),
};

/* ==========================================================================
   SHELL-LOCAL (NON-QUEUE) STATE
   Only identity/session lives here — all queue data lives in the store.
   ========================================================================== */

let currentUser = null;
let wsSubscriptions = [];
let drawerOpen = false;

const STAFF_QUEUE_EVENTS = new Set([
    "TOKEN_CALLED",
    "TOKEN_SERVICE_STARTED",
    "TOKEN_COMPLETED",
    "TOKEN_CANCELLED",
    "TOKEN_NO_SHOW",
    "TOKEN_REQUEUED",
    "PATIENT_ROUTED",
    "QUEUE_UPDATED",
]);

/* ==========================================================================
   LABELS & PURE HELPERS (preserved from reference implementation)
   ========================================================================== */

function showElement(element) {
    if (!element) return;
    element.classList.remove("hidden");
}

function hideElement(element) {
    if (!element) return;
    element.classList.add("hidden");
}

function setText(element, text) {
    if (!element) return;
    element.textContent = text ?? "";
}

function setStatus(text) {
    setText(elements.dashboardSubtitle, text);
}

function showError(message) {
    if (elements.actionError) {
        setText(elements.actionError, message);
        showElement(elements.actionError);
    }
}

function clearError() {
    if (elements.actionError) {
        hideElement(elements.actionError);
        setText(elements.actionError, "");
    }
}

function getQueueTokenLabel(entry) {
    return entry?.visit?.token_number || `#${entry?.sequence_number ?? "?"}`;
}

function getPatientLabel(entry) {
    if (!entry) return "Unknown patient";

    const visit = entry.visit || null;
    const patient = visit?.patient || visit?.patient_summary || null;

    if (!patient) {
        return "Unknown patient";
    }

    const fullName = [patient.first_name, patient.last_name].filter(Boolean).join(" ");
    if (fullName) {
        return fullName;
    }

    if (patient.temporary_identifier) return `Temp ID: ${patient.temporary_identifier}`;
    if (patient.national_id) return `ID: ${patient.national_id}`;

    return "Unknown patient";
}

/*
 * Pure action-state derivation — queue-engine capability + ownership.
 * Kept as an exported test seam (same signature as the legacy file).
 */
function getActionStatesForTest(entry, user) {
    if (!entry) {
        return {
            call: false,
            start: false,
            noShow: false,
            complete: false,
        };
    }

    const isOwner = user && String(entry.assigned_staff_id) === String(user.staff_id);

    return {
        call: entry.status === "WAITING" && !entry.assigned_staff_id,
        start: entry.status === "CALLED" && isOwner,
        noShow: entry.status === "CALLED" && isOwner,
        complete: entry.status === "IN_PROGRESS" && isOwner,
    };
}

function getActionStates(entry) {
    return getActionStatesForTest(entry, currentUser);
}

function isPatientRegistrationComplete(queueEntry) {
    if (!queueEntry || !queueEntry.visit) {
        return false;
    }

    const patient = queueEntry.visit.patient || queueEntry.visit.patient_summary;
    if (!patient) {
        return false;
    }

    return !!(
        patient.first_name &&
        patient.last_name &&
        patient.date_of_birth &&
        patient.gender
    );
}

/* ==========================================================================
   RENDERING (driven exclusively by store state via subscription)
   ========================================================================== */

function renderQueueTable(state) {
    if (!elements.queueBody) return;

    elements.queueBody.innerHTML = "";

    const entries = state.queueEntries;

    if (entries.length === 0) {
        hideElement(elements.queueTable);
        if (elements.queueState) {
            elements.queueState.textContent = state.initialized
                ? "No active queue entries found for this department."
                : "Log in to view department queue entries.";
        }
        showElement(elements.queueState);
        return;
    }

    hideElement(elements.queueState);
    showElement(elements.queueTable);

    for (const entry of entries) {
        const tr = document.createElement("tr");
        tr.classList.add("queue-row");
        tr.dataset.entryId = entry.queue_entry_id;

        if (entry.queue_entry_id === state.selectedQueueEntryId) {
            tr.classList.add("selected");
        }

        tr.innerHTML = `
            <td>${getQueueTokenLabel(entry)}</td>
            <td>${getPatientLabel(entry)}</td>
            <td>${entry.priority}</td>
            <td>${entry.status}</td>
        `;

        tr.addEventListener("click", () => {
            selectQueueEntry(entry.queue_entry_id);
        });

        elements.queueBody.appendChild(tr);
    }
}

function renderNoShowTable(state) {
    showElement(elements.noShowPanel);

    if (!elements.noShowBody) return;

    elements.noShowBody.innerHTML = "";

    const entries = state.noShowEntries;

    if (entries.length === 0) {
        hideElement(elements.noShowTable);
        showElement(elements.noShowState);

        if (elements.noShowState) {
            elements.noShowState.textContent =
                "No patients are currently marked as no-show.";
        }

        return;
    }

    hideElement(elements.noShowState);
    showElement(elements.noShowTable);

    for (const entry of entries) {
        const tr = document.createElement("tr");
        tr.dataset.entryId = entry.queue_entry_id;

        tr.innerHTML = `
            <td>${getQueueTokenLabel(entry)}</td>
            <td>${getPatientLabel(entry)}</td>
            <td>${entry.priority}</td>
            <td>${entry.status}</td>
            <td>
                <button
                    type="button"
                    class="button-primary requeue-button"
                    data-entry-id="${entry.queue_entry_id}"
                >
                    Re-Queue
                </button>
            </td>
        `;

        elements.noShowBody.appendChild(tr);
    }
}

function updateOwnershipDisplay(entry) {
    if (!elements.currentOwner) return;

    if (!entry || !entry.assigned_staff_id) {
        elements.currentOwner.textContent = "Owner: Unassigned";
        elements.currentOwner.className = "current-owner unassigned";
        return;
    }

    if (currentUser && String(entry.assigned_staff_id) === String(currentUser.staff_id)) {
        elements.currentOwner.textContent =
            `Owner: You (${currentUser.first_name || currentUser.staff_id})`;
        elements.currentOwner.className = "current-owner owner";
    } else {
        elements.currentOwner.textContent = `Owner: Staff ${entry.assigned_staff_id}`;
        elements.currentOwner.className = "current-owner other-owner";
    }
}

/*
 * The encounter panel renders the ACTIVE PATIENT, not the selection.
 * A queue-row click changes selection only; an in-progress encounter
 * is pinned until the queue entry leaves CALLED/IN_PROGRESS.
 */
function renderEncounterPanel(state) {
    const active = state.activePatient;
    const selected = getSelectedQueueEntry();

    const displayEntry = active || selected;

    if (!displayEntry) {
        hideElement(elements.currentPatientPanel);
        return;
    }

    if (elements.currentToken) {
        setText(elements.currentToken, getQueueTokenLabel(displayEntry));
    }
    if (elements.currentStatus) {
        setText(elements.currentStatus, displayEntry.status);
    }
    if (elements.currentPatient) {
        setText(elements.currentPatient, getPatientLabel(displayEntry));
    }
    if (elements.currentPriority) {
        setText(elements.currentPriority, displayEntry.priority);
    }

    showElement(elements.currentPatientPanel);
    updateOwnershipDisplay(displayEntry);

    const states = getActionStates(displayEntry);

    setButtonState(elements.callButton, states.call, "button-primary");
    setButtonState(elements.startButton, states.start, "button-secondary");
    setButtonState(elements.noShowButton, states.noShow, "button-danger");
    setButtonState(elements.completeButton, states.complete, "button-danger");
}

function setButtonState(button, enabled, enabledClass) {
    if (!button) return;

    button.disabled = !enabled;
    button.classList.toggle(enabledClass, enabled);
    button.classList.toggle("button-disabled", !enabled);
}

function render(state) {
    renderQueueTable(state);
    renderNoShowTable(state);
    renderEncounterPanel(state);
}

/* ==========================================================================
   SERVER SYNCHRONIZATION
   ========================================================================== */

let syncInProgress = false;
let syncPending = false;

/*
 * Authoritative snapshot fetch + reconcile into the store.
 * Coalesced: concurrent triggers collapse into one round-trip.
 *
 * The store is updated FIRST via applyEvent() deltas (instant UI);
 * this sync exists to reconcile drift and to load the initial view.
 */
async function syncFromServer() {
    if (!currentUser?.dept_id) {
        return;
    }

    if (syncInProgress) {
        syncPending = true;
        return;
    }

    syncInProgress = true;

    try {
        const [activeQueue, noShows] = await Promise.all([
            getDepartmentQueue(currentUser.dept_id),
            getDepartmentNoShowQueue(currentUser.dept_id),
        ]);

        setSnapshot({
            queueEntries: activeQueue,
            noShowEntries: noShows,
        });
    } catch (error) {
        console.error(error);
        showError(error.message || "Unable to refresh queue. Please try again.");
    } finally {
        syncInProgress = false;

        if (syncPending) {
            syncPending = false;
            await syncFromServer();
        }
    }
}

/* Backwards-compatible alias used by the existing test-suite. */
const refreshQueue = syncFromServer;

/* ==========================================================================
   ACTION HANDLERS (intent → API → store → render)
   ========================================================================== */

async function performTransition(action) {
    const entry = getMyActivePatient() || getSelectedQueueEntry();

    if (!entry) {
        return;
    }

    try {
        setStatus(`Performing ${action}...`);
        clearError();

        let updatedEntry = null;

        if (action === "call") {
            const nextEntry = await getNextPatient(currentUser.dept_id);

            if (!nextEntry) {
                throw new Error("No waiting patients in the queue.");
            }

            updatedEntry = await callQueueEntry(nextEntry.queue_entry_id);
        } else if (action === "start") {
            updatedEntry = await startQueueEntry(entry.queue_entry_id);
        } else if (action === "noshow") {
            updatedEntry = await markNoShowQueueEntry(entry.queue_entry_id);
        } else if (action === "complete") {
            updatedEntry = await completeQueueEntry(entry.queue_entry_id);
        }

        /*
         * The backend response is authoritative — feed it back through
         * the store as an event-equivalent update, then reconcile.
         */
        if (updatedEntry) {
            if (!updatedEntry.visit?.patient && entry?.visit?.patient) {
                updatedEntry.visit = entry.visit;
            }

            applyEvent({
                event_type: "QUEUE_UPDATED",
            });

            applyEvent({
                event_type: entryToEventType(updatedEntry),
                queue_entry_id: updatedEntry.queue_entry_id,
                assigned_staff_id: updatedEntry.assigned_staff_id,
                queue_entry: updatedEntry,
            });
        }

        await syncFromServer();

        if (
            action === "start" &&
            !isPatientRegistrationComplete(getMyActivePatient())
        ) {
            openRegistrationDrawer();
            return;
        }

        const current = getMyActivePatient();
        setStatus(
            `Ready — ${current ? getQueueTokenLabel(current) : "no current patient"}`
        );

    } catch (error) {
        console.error(error);

        if (error && error.status === 403) {
            showError("This patient is assigned to another staff member.");
            await syncFromServer();
            return;
        }

        if (error && error.status === 409) {
            showError(error.message || "You already have an active patient.");
            await syncFromServer();
            return;
        }

        showError(error.message || "Action failed. Please try again.");
        await syncFromServer();
    }
}

/*
 * Map a queue-entry object to the store event type that represents
 * its status, so action results flow through the same applyEvent()
 * path as WebSocket events.
 */
function entryToEventType(entry) {
    switch (entry?.status) {
        case "WAITING": return "TOKEN_REQUEUED";
        case "CALLED": return "TOKEN_CALLED";
        case "IN_PROGRESS": return "TOKEN_SERVICE_STARTED";
        case "NO_SHOW": return "TOKEN_NO_SHOW";
        case "COMPLETED": return "TOKEN_COMPLETED";
        case "CANCELLED": return "TOKEN_CANCELLED";
        default: return "QUEUE_UPDATED";
    }
}

async function handleRequeue(queueEntryId, buttonElement) {
    if (buttonElement) {
        buttonElement.disabled = true;
    }

    try {
        clearError();
        setStatus("Re-queuing patient...");

        await requeueQueueEntry(queueEntryId);

        await syncFromServer();

        const current = getMyActivePatient();
        setStatus(
            `Ready — ${current ? getQueueTokenLabel(current) : "no current patient"}`
        );

    } catch (error) {
        console.error("Failed to requeue entry:", error);
        showError(error.message || "Unable to re-queue patient.");
        await syncFromServer();
    } finally {
        if (buttonElement) {
            buttonElement.disabled = false;
        }
    }
}

/* ==========================================================================
   AUTHENTICATION & CONTEXT
   ========================================================================== */

async function identifyDepartment() {
    try {
        setStatus("Loading staff profile...");

        currentUser = await getCurrentUser();
        const context = initializeStaffContext(currentUser);

        setContext(context.departmentId, context.staffId);

        await syncFromServer();

        startStaffWebSocket();

        setStatus(
            `Ready — ${currentUser.first_name} ${currentUser.last_name}`
        );
    } catch (error) {
        console.error(error);

        if (error.status === 403) {
            showError(
                "You are not authorized to access this department."
            );
        } else {
            showError(
                error.message || "Unable to load department."
            );
        }

        setStatus("Unable to load department");
    }
}

function handleLogout() {
    stopStaffWebSocket();
    logout();

    currentUser = null;
    clearStaffContext();

    syncInProgress = false;
    syncPending = false;

    closeRegistrationDrawer();
    clearQueueState();

    hideElement(elements.logoutButton);
    hideElement(elements.currentPatientPanel);
    hideElement(elements.queueTable);

    setStatus("Session ended");

    clearError();
}

/* ==========================================================================
   WEBSOCKET → STORE WIRING
   ========================================================================== */

function eventBelongsToCurrentDepartment(event) {
    if (!event || !currentUser?.dept_id) {
        return false;
    }

    const departmentId = String(currentUser.dept_id);

    if (event.dept_id && String(event.dept_id) === departmentId) {
        return true;
    }

    if (event.event_type === "PATIENT_ROUTED") {
        return (
            String(event.source_dept_id) === departmentId ||
            String(event.target_dept_id) === departmentId
        );
    }

    return false;
}

/*
 * Event pipeline:
 *   WS message → department filter → applyEvent (instant local update)
 *   → coalesced authoritative reconcile via syncFromServer().
 *
 * Local-first means the UI reacts immediately even on a slow network;
 * the reconcile guarantees eventual consistency with the backend.
 */
async function handleStaffWebSocketMessage(event) {
    if (!event || typeof event !== "object") {
        return;
    }

    if (!STAFF_QUEUE_EVENTS.has(event.event_type)) {
        return;
    }

    if (!eventBelongsToCurrentDepartment(event)) {
        return;
    }

    console.log(
        "[STAFF WS] Department queue event:",
        event.event_type,
        event
    );

    if (event.event_type === "QUEUE_UPDATED") {
        markStale();
    } else {
        applyEvent(event);
    }

    await syncFromServer();
}

function registerStaffWebSocketListeners() {
    if (wsSubscriptions.length > 0) {
        return;
    }

    const subscriptions = [
        [
            "connected",
            async () => {
                console.log("[STAFF WS] Connected");
                await syncFromServer();
            },
        ],

        ["message", handleStaffWebSocketMessage],

        [
            "disconnected",
            () => console.warn("[STAFF WS] Disconnected"),
        ],

        [
            "reconnecting",
            (details) => console.warn("[STAFF WS] Reconnecting:", details),
        ],

        [
            "error",
            (error) => console.error("[STAFF WS] Error:", error),
        ],
    ];

    for (const [eventName, callback] of subscriptions) {
        onStaffWebSocket(eventName, callback);
        wsSubscriptions.push({ eventName, callback });
    }
}

function unregisterStaffWebSocketListeners() {
    for (const { eventName, callback } of wsSubscriptions) {
        offStaffWebSocket(eventName, callback);
    }

    wsSubscriptions = [];
}

function startStaffWebSocket() {
    registerStaffWebSocketListeners();
    connectStaffWebSocket();
}

function stopStaffWebSocket() {
    disconnectStaffWebSocket();
    unregisterStaffWebSocketListeners();
}

/* ==========================================================================
   REGISTRATION DRAWER (behavior preserved from reference implementation)
   ========================================================================== */

function prefillRegistrationForm(queueEntry) {
    if (!queueEntry || !queueEntry.visit) {
        return;
    }

    const patient = queueEntry.visit.patient || queueEntry.visit.patient_summary;
    if (!patient) {
        return;
    }

    const fieldMap = [
        ["registrationFirstName", patient.first_name],
        ["registrationLastName", patient.last_name],
        ["registrationDateOfBirth", patient.date_of_birth],
        ["registrationGender", patient.gender],
        ["registrationNationalId", patient.national_id],
        ["registrationPhone", patient.phone],
        ["registrationEmail", patient.email],
        ["registrationBloodType", patient.blood_type],
        ["registrationAllergies", patient.allergies],
    ];

    for (const [elementKey, value] of fieldMap) {
        if (elements[elementKey] && value) {
            elements[elementKey].value = value;
        }
    }
}

function clearRegistrationForm() {
    if (elements.patientRegistrationForm) {
        elements.patientRegistrationForm.reset();
    }
    clearDrawerError();
}

function openRegistrationDrawer() {
    const active = getMyActivePatient() || getSelectedQueueEntry();

    if (!active) {
        return;
    }

    drawerOpen = true;
    clearRegistrationForm();
    prefillRegistrationForm(active);

    if (elements.registrationOverlay) {
        elements.registrationOverlay.classList.add("active");
    }
    if (elements.registrationDrawer) {
        elements.registrationDrawer.classList.add("active");
        elements.registrationDrawer.classList.remove("closing");
    }

    if (elements.registrationFirstName) {
        elements.registrationFirstName.focus();
    }
}

function closeRegistrationDrawer() {
    drawerOpen = false;

    if (elements.registrationDrawer) {
        elements.registrationDrawer.classList.add("closing");
        setTimeout(() => {
            if (elements.registrationDrawer) {
                elements.registrationDrawer.classList.remove("active");
                elements.registrationDrawer.classList.remove("closing");
            }
        }, 300);
    }

    if (elements.registrationOverlay) {
        elements.registrationOverlay.classList.remove("active");
    }

    clearRegistrationForm();
}

function showDrawerError(message) {
    if (elements.drawerError) {
        elements.drawerError.textContent = message;
        elements.drawerError.classList.add("active");
    }
}

function clearDrawerError() {
    if (elements.drawerError) {
        elements.drawerError.classList.remove("active");
        elements.drawerError.textContent = "";
    }
}

async function handleRegistrationSubmit(event) {
    if (event) {
        event.preventDefault();
    }

    const entry = getMyActivePatient() || getSelectedQueueEntry();

    if (!entry || !entry.visit) {
        showDrawerError("No patient selected. Please select a patient.");
        return;
    }

    const patient = entry.visit.patient || entry.visit.patient_summary;
    if (!patient || !patient.patient_id) {
        showDrawerError("Unable to identify patient. Please try again.");
        return;
    }

    if (elements.drawerSubmitButton) {
        elements.drawerSubmitButton.disabled = true;
    }

    try {
        clearDrawerError();
        setStatus("Completing patient registration...");

        const registrationData = {
            first_name: (elements.registrationFirstName?.value || "").trim(),
            last_name: (elements.registrationLastName?.value || "").trim(),
            date_of_birth: elements.registrationDateOfBirth?.value || "",
            gender: elements.registrationGender?.value || "",
            national_id: (elements.registrationNationalId?.value || "").trim() || null,
            phone: (elements.registrationPhone?.value || "").trim() || null,
            email: (elements.registrationEmail?.value || "").trim() || null,
            blood_type: (elements.registrationBloodType?.value || "").trim() || null,
            allergies: (elements.registrationAllergies?.value || "").trim() || null,
        };

        if (!registrationData.first_name) {
            throw new Error("First name is required.");
        }
        if (!registrationData.last_name) {
            throw new Error("Last name is required.");
        }
        if (!registrationData.date_of_birth) {
            throw new Error("Date of birth is required.");
        }
        if (!registrationData.gender) {
            throw new Error("Gender is required.");
        }

        await completePatientRegistration(patient.patient_id, registrationData);

        await syncFromServer();
        closeRegistrationDrawer();

        const current = getMyActivePatient();
        setStatus(
            `Ready — ${current ? getQueueTokenLabel(current) : "no current patient"}`
        );

    } catch (error) {
        console.error("[REGISTRATION ERROR]", error);
        showDrawerError(
            error.message || "Unable to complete registration. Please try again."
        );
        setStatus("Registration failed");

    } finally {
        if (elements.drawerSubmitButton) {
            elements.drawerSubmitButton.disabled = false;
        }
    }
}

/* ==========================================================================
   KEYBOARD SHORTCUTS & EVENT WIRING
   ========================================================================== */

function setupKeyboardShortcuts() {
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && drawerOpen) {
            event.preventDefault();
            closeRegistrationDrawer();
            return;
        }

        if ((event.ctrlKey || event.metaKey) && event.key === "Enter" && drawerOpen) {
            event.preventDefault();
            handleRegistrationSubmit();
        }
    });
}

function attachEventListeners() {
    if (elements.logoutButton) {
        elements.logoutButton.addEventListener("click", handleLogout);
    }
    if (elements.callButton) {
        elements.callButton.addEventListener("click", () => performTransition("call"));
    }
    if (elements.startButton) {
        elements.startButton.addEventListener("click", () => performTransition("start"));
    }
    if (elements.noShowButton) {
        elements.noShowButton.addEventListener("click", () => performTransition("noshow"));
    }
    if (elements.completeButton) {
        elements.completeButton.addEventListener("click", () => performTransition("complete"));
    }

    if (elements.drawerCloseButton) {
        elements.drawerCloseButton.addEventListener("click", closeRegistrationDrawer);
    }
    if (elements.drawerCancelButton) {
        elements.drawerCancelButton.addEventListener("click", closeRegistrationDrawer);
    }
    if (elements.drawerSubmitButton) {
        elements.drawerSubmitButton.addEventListener("click", handleRegistrationSubmit);
    }
    if (elements.registrationOverlay) {
        elements.registrationOverlay.addEventListener("click", (event) => {
            if (event.target === elements.registrationOverlay) {
                closeRegistrationDrawer();
            }
        });
    }
    if (elements.patientRegistrationForm) {
        elements.patientRegistrationForm.addEventListener("submit", handleRegistrationSubmit);
    }

    // No-show requeue (event delegation)
    if (elements.noShowBody) {
        elements.noShowBody.addEventListener("click", (event) => {
            const button = event.target.closest(".requeue-button");

            if (!button || button.disabled) {
                return;
            }

            const { entryId } = button.dataset;

            if (entryId) {
                handleRequeue(entryId, button);
            }
        });
    }
}

/* ==========================================================================
   INITIALIZATION
   ========================================================================== */

async function restoreStaffSession() {
    if (!getSession()?.accessToken) {
        setStatus("Please sign in to manage the queue");
        return false;
    }

    showElement(elements.logoutButton);
    await identifyDepartment();
    return true;
}

function initializeStaffApp() {
    setupKeyboardShortcuts();
    attachEventListeners();

    // The render loop: every store mutation re-renders the panels.
    subscribe(render);

    showElement(elements.queuePanel);

    if (elements.queueState) {
        elements.queueState.textContent =
            "Log in to view department queue entries.";
        showElement(elements.queueState);
    }

    restoreStaffSession();
}

if (document.getElementById("dashboard-subtitle")) {
    initializeStaffApp();
}

/* ==========================================================================
   EXPORTS (compatibility surface for the existing test-suite)
   ========================================================================== */

export {
    getActionStates,
    getActionStatesForTest,
    getPatientLabel,
    getQueueTokenLabel,
    updateOwnershipDisplay,
    selectQueueEntry,
    refreshQueue,
    handleRequeue,
    performTransition,
    openRegistrationDrawer,
    closeRegistrationDrawer,
    restoreStaffSession,
};
