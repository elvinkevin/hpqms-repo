/* ==========================================================================
   HPQMS Staff Dashboard - OPTION 2: MODAL DRAWER IMPLEMENTATION
   WORKFLOW: SELECT → CALL → START SERVICE (auto-opens registration drawer if incomplete)
   
   Key Features:
   - Slide-over drawer (right-side panel) for registration
   - Auto-trigger when START SERVICE clicked on incomplete patient
   - Keyboard shortcuts: ESC to close, Ctrl/Cmd+Enter to save
   - Partial background visibility for context
   ========================================================================== */

import {
    login,
    logout,
    getDepartments,
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
    connect as connectStaffWebSocket,
    disconnect as disconnectStaffWebSocket,
    on as onStaffWebSocket,
    off as offStaffWebSocket,
} from "./staff-websocket.js";

const elements = {
    loginPanel: document.getElementById("login-panel"),
    loginForm: document.getElementById("login-form"),
    employeeId: document.getElementById("employee-id"),
    password: document.getElementById("password"),
    loginError: document.getElementById("login-error"),
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

    // Drawer elements
    registrationOverlay: document.getElementById("registration-overlay"),
    registrationDrawer: document.getElementById("registration-drawer"),
    drawerCloseButton: document.getElementById("drawer-close-button"),
    drawerCancelButton: document.getElementById("drawer-cancel-button"),
    drawerSubmitButton: document.getElementById("drawer-submit-button"),
    drawerError: document.getElementById("drawer-error"),

    // Registration form fields
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

let selectedDepartmentId = null;
let queueEntries = [];
let noShowEntries = [];
let selectedQueueEntry = null;
let currentUser = null;
let staffWebSocketSubscriptions = [];
let websocketConnected = false;
let queueRefreshInProgress = false;
let queueRefreshPending = false;
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
    if (elements.loginError) {
        setText(elements.loginError, message);
        showElement(elements.loginError);
    }

    if (elements.actionError) {
        setText(elements.actionError, message);
        showElement(elements.actionError);
    }
}

function clearError() {
    if (elements.loginError) {
        hideElement(elements.loginError);
        setText(elements.loginError, "");
    }

    if (elements.actionError) {
        hideElement(elements.actionError);
        setText(elements.actionError, "");
    }
}

function getQueueTokenLabel(entry) {
    return entry.visit?.token_number || `#${entry.sequence_number}`;
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

function renderQueueTable() {
    if (!elements.queueBody) return;
    
    elements.queueBody.innerHTML = "";

    if (queueEntries.length === 0) {
        hideElement(elements.queueTable);
        if (elements.queueState) {
            elements.queueState.textContent = "No active queue entries found for this department.";
        }
        showElement(elements.queueState);
        return;
    }

    hideElement(elements.queueState);
    showElement(elements.queueTable);

    for (const entry of queueEntries) {
        const tr = document.createElement("tr");
        tr.classList.add("queue-row");
        tr.dataset.entryId = entry.queue_entry_id;

        if (selectedQueueEntry && selectedQueueEntry.queue_entry_id === entry.queue_entry_id) {
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

function updateCurrentPatientPanel() {
    if (!selectedQueueEntry) {
        hideElement(elements.currentPatientPanel);
        return;
    }

    if (elements.currentToken) {
        setText(elements.currentToken, getQueueTokenLabel(selectedQueueEntry));
    }
    if (elements.currentStatus) {
        setText(elements.currentStatus, selectedQueueEntry.status);
    }
    if (elements.currentPatient) {
        setText(elements.currentPatient, getPatientLabel(selectedQueueEntry));
    }
    if (elements.currentPriority) {
        setText(elements.currentPriority, selectedQueueEntry.priority);
    }
    
    showElement(elements.currentPatientPanel);
    updateOwnershipDisplay(selectedQueueEntry);

    const states = getActionStates(selectedQueueEntry);

    if (elements.callButton) {
        elements.callButton.disabled = !states.call;
        elements.callButton.classList.toggle("button-primary", states.call);
        elements.callButton.classList.toggle("button-disabled", !states.call);
    }

    if (elements.startButton) {
        elements.startButton.disabled = !states.start;
        elements.startButton.classList.toggle("button-secondary", states.start);
        elements.startButton.classList.toggle("button-disabled", !states.start);
    }

    if (elements.noShowButton) {
        elements.noShowButton.disabled = !states.noShow;
        elements.noShowButton.classList.toggle("button-danger", states.noShow);
        elements.noShowButton.classList.toggle("button-disabled", !states.noShow);
    }

    if (elements.completeButton) {
        elements.completeButton.disabled = !states.complete;
        elements.completeButton.classList.toggle("button-danger", states.complete);
        elements.completeButton.classList.toggle("button-disabled", !states.complete);
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
        elements.currentOwner.textContent = `Owner: You (${currentUser.first_name || currentUser.staff_id})`;
        elements.currentOwner.className = "current-owner owner";
    } else {
        elements.currentOwner.textContent = `Owner: Staff ${entry.assigned_staff_id}`;
        elements.currentOwner.className = "current-owner other-owner";
    }
}

function selectQueueEntry(queueEntryId) {
    selectedQueueEntry = queueEntries.find(
        (entry) => entry.queue_entry_id === queueEntryId
    );

    renderQueueTable();
    updateCurrentPatientPanel();
}

function renderNoShowTable() {
    showElement(elements.noShowPanel);

    if (!elements.noShowBody) return;

    elements.noShowBody.innerHTML = "";

    if (noShowEntries.length === 0) {
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

    for (const entry of noShowEntries) {
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

async function refreshNoShowQueue() {
    if (!selectedDepartmentId) {
        return;
    }

    try {
        noShowEntries = await getDepartmentNoShowQueue(selectedDepartmentId);
        renderNoShowTable();
    } catch (error) {
        console.error("Unable to refresh no-show queue:", error);
    }
}

async function refreshQueue() {
    if (!selectedDepartmentId) {
        return;
    }

    if (queueRefreshInProgress) {
        queueRefreshPending = true;
        return;
    }

    queueRefreshInProgress = true;

    try {
        const [activeQueue, noShows] = await Promise.all([
            getDepartmentQueue(selectedDepartmentId),
            getDepartmentNoShowQueue(selectedDepartmentId),
        ]);

        queueEntries = activeQueue;
        noShowEntries = noShows;

        if (!selectedQueueEntry) {
            selectedQueueEntry = queueEntries[0] || null;
        } else {
            selectedQueueEntry =
                queueEntries.find(
                    (entry) =>
                        entry.queue_entry_id ===
                        selectedQueueEntry.queue_entry_id
                ) ||
                queueEntries[0] ||
                null;
        }

        renderQueueTable();
        renderNoShowTable();
        updateCurrentPatientPanel();

        } catch (error) {
        console.error(error);
        showError(
            error.message ||
            "Unable to refresh queue. Please try again."
        );
    } finally {
        queueRefreshInProgress = false;

        if (queueRefreshPending) {
            queueRefreshPending = false;
            await refreshQueue();
        }
    }
}

async function requeueNoShowEntry(queueEntryId) {
    try {
        clearError();
        setStatus("Re-queuing patient...");

        const updatedEntry = await requeueQueueEntry(queueEntryId);
        await refreshQueue();

        setStatus(
            `Ready — ${selectedQueueEntry
                ? getQueueTokenLabel(selectedQueueEntry)
                : "no current patient"
            }`
        );

    } catch (error) {
        console.error("[REQUEUE FAILED]", error);
        showError(error.message || "Unable to re-queue patient.");
    }
}

/* ============================================================
   DRAWER MANAGEMENT FUNCTIONS
   ============================================================ */

function prefillRegistrationForm(queueEntry) {
    if (!queueEntry || !queueEntry.visit) {
        return;
    }

    const patient = queueEntry.visit.patient || queueEntry.visit.patient_summary;
    if (!patient) {
        return;
    }

    if (elements.registrationFirstName && patient.first_name) {
        elements.registrationFirstName.value = patient.first_name;
    }
    if (elements.registrationLastName && patient.last_name) {
        elements.registrationLastName.value = patient.last_name;
    }
    if (elements.registrationDateOfBirth && patient.date_of_birth) {
        elements.registrationDateOfBirth.value = patient.date_of_birth;
    }
    if (elements.registrationGender && patient.gender) {
        elements.registrationGender.value = patient.gender;
    }
    if (elements.registrationNationalId && patient.national_id) {
        elements.registrationNationalId.value = patient.national_id;
    }
    if (elements.registrationPhone && patient.phone) {
        elements.registrationPhone.value = patient.phone;
    }
    if (elements.registrationEmail && patient.email) {
        elements.registrationEmail.value = patient.email;
    }
    if (elements.registrationBloodType && patient.blood_type) {
        elements.registrationBloodType.value = patient.blood_type;
    }
    if (elements.registrationAllergies && patient.allergies) {
        elements.registrationAllergies.value = patient.allergies;
    }
}

function clearRegistrationForm() {
    if (elements.patientRegistrationForm) {
        elements.patientRegistrationForm.reset();
    }
    if (elements.drawerError) {
        elements.drawerError.classList.remove("active");
        elements.drawerError.textContent = "";
    }
}

function openRegistrationDrawer() {
    if (!selectedQueueEntry) {
        return;
    }

    drawerOpen = true;
    clearRegistrationForm();
    prefillRegistrationForm(selectedQueueEntry);

    if (elements.registrationOverlay) {
        elements.registrationOverlay.classList.add("active");
    }
    if (elements.registrationDrawer) {
        elements.registrationDrawer.classList.add("active");
        elements.registrationDrawer.classList.remove("closing");
    }

    // Focus first field
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

async function handleRegistrationSubmit(event) {
    if (event) {
        event.preventDefault();
    }

    if (!selectedQueueEntry || !selectedQueueEntry.visit) {
        showDrawerError("No patient selected. Please select a patient.");
        return;
    }

    const patient = selectedQueueEntry.visit.patient || selectedQueueEntry.visit.patient_summary;
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

        const result = await completePatientRegistration(
            patient.patient_id,
            registrationData
        );

        console.log("[REGISTRATION SUCCESS]", result);

        await refreshQueue();
        closeRegistrationDrawer();
        setStatus(`Ready — ${getQueueTokenLabel(selectedQueueEntry)}`);

    } catch (error) {
        console.error("[REGISTRATION ERROR]", error);
        const message = error.message || "Unable to complete registration. Please try again.";
        showDrawerError(message);
        setStatus("Registration failed");

    } finally {
        if (elements.drawerSubmitButton) {
            elements.drawerSubmitButton.disabled = false;
        }
    }
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

/* ============================================================
   TRANSITION & ACTION HANDLERS
   ============================================================ */

async function performTransition(action) {
    if (!selectedQueueEntry) {
        return;
    }

    try {
        setStatus(`Performing ${action}...`);

        let updatedEntry = null;
        clearError();

        if (action === "call") {
            const nextEntry = await getNextPatient(selectedDepartmentId);

            if (!nextEntry) {
                throw new Error("No waiting patients in the queue.");
            }

            updatedEntry = await callQueueEntry(nextEntry.queue_entry_id);
            selectedQueueEntry = updatedEntry;

        } else if (action === "start") {
            updatedEntry = await startQueueEntry(selectedQueueEntry.queue_entry_id);

        } else if (action === "noshow") {
            updatedEntry = await markNoShowQueueEntry(selectedQueueEntry.queue_entry_id);

        } else if (action === "complete") {
            updatedEntry = await completeQueueEntry(selectedQueueEntry.queue_entry_id);
        }

        if (updatedEntry) {
            if (
                !updatedEntry.visit?.patient &&
                selectedQueueEntry?.visit?.patient
            ) {
                updatedEntry.visit = selectedQueueEntry.visit;
            }

            selectedQueueEntry = updatedEntry;
        }

        await refreshQueue();

        // AUTO-TRIGGER DRAWER: Open registration drawer if patient is incomplete after START SERVICE
        if (action === "start" && !isPatientRegistrationComplete(selectedQueueEntry)) {
            openRegistrationDrawer();
            return;
        }

        setStatus(
            `Ready — ${selectedQueueEntry
                ? getQueueTokenLabel(selectedQueueEntry)
                : "no current patient"
            }`
        );

    } catch (error) {
        console.error(error);

        if (error && error.status === 403) {
            showError("This patient is assigned to another staff member.");
            try {
                await refreshQueue();
            } catch (e) {
                console.error("refresh after 403 failed", e);
            }
            return;
        }

        if (error && error.status === 409) {
            showError(error.message || "You already have an active patient.");
            try {
                await refreshQueue();
            } catch (e) {
                console.error("refresh after 409 failed", e);
            }
            return;
        }

        showError(error.message || "Action failed. Please try again.");

        try {
            await refreshQueue();
        } catch (e) {
            console.error("refresh after failure failed", e);
        }
    }
}

async function identifyDepartment() {
    try {
        setStatus("Loading staff profile...");

        currentUser = await getCurrentUser();

        if (!currentUser?.dept_id) {
            throw new Error(
                "Your staff account is not assigned to a department."
            );
        }

       selectedDepartmentId = currentUser.dept_id;

       await refreshQueue();

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

async function handleLogin(event) {
    event.preventDefault();
    clearError();

    const credentials = {
        employee_id: elements.employeeId.value.trim(),
        password: elements.password.value,
    };

    if (!credentials.employee_id || !credentials.password) {
        showError("Employee ID and password are required.");
        return;
    }

    try {
        setStatus("Signing in...");
        await login(credentials);
        hideElement(elements.loginPanel);
        showElement(elements.logoutButton);
        showElement(elements.queuePanel);
        await identifyDepartment();
    } catch (error) {
        console.error(error);
        showError(error.message || "Login failed. Check credentials.");
        setStatus("Sign in to manage the queue");
    }
}

function handleLogout() {
    stopStaffWebSocket();

    logout();

    currentUser = null;
    queueEntries = [];
    selectedQueueEntry = null;
    selectedDepartmentId = null;

    queueRefreshInProgress = false;
    queueRefreshPending = false;

    closeRegistrationDrawer();

    hideElement(elements.logoutButton);
    hideElement(elements.currentPatientPanel);
    hideElement(elements.queueTable);

    showElement(elements.loginPanel);

    setStatus("Please sign in to manage the queue");

    if (elements.queueBody) {
        elements.queueBody.innerHTML = "";
    }
    if (elements.queueState) {
        elements.queueState.textContent =
            "Log in to view department queue entries.";
        showElement(elements.queueState);
    }

    clearError();
}

function registerStaffWebSocketListeners() {
    if (staffWebSocketSubscriptions.length > 0) {
        return;
    }

    const subscriptions = [
        [
            "connected",
            async () => {
                websocketConnected = true;
                console.log("[STAFF WS] Connected");
                await refreshQueue();
            },
        ],

        [
            "message",
            handleStaffWebSocketMessage,
        ],

        [
            "disconnected",
            () => {
                websocketConnected = false;
                console.warn("[STAFF WS] Disconnected");
            },
        ],

        [
            "reconnecting",
            (details) => {
                websocketConnected = false;
                console.warn("[STAFF WS] Reconnecting:", details);
            },
        ],

        [
            "error",
            (error) => {
                console.error("[STAFF WS] Error:", error);
            },
        ],
    ];

    for (const [eventName, callback] of subscriptions) {
        onStaffWebSocket(eventName, callback);
        staffWebSocketSubscriptions.push({ eventName, callback });
    }
}

function unregisterStaffWebSocketListeners() {
    for (const { eventName, callback } of staffWebSocketSubscriptions) {
        offStaffWebSocket(eventName, callback);
    }

    staffWebSocketSubscriptions = [];
    websocketConnected = false;
}

function startStaffWebSocket() {
    registerStaffWebSocketListeners();
    connectStaffWebSocket();
}

function stopStaffWebSocket() {
    disconnectStaffWebSocket();
    unregisterStaffWebSocketListeners();
}

function eventBelongsToCurrentDepartment(event) {
    if (!event || !selectedDepartmentId) {
        return false;
    }

    const departmentId = String(selectedDepartmentId);

    if (
        event.dept_id &&
        String(event.dept_id) === departmentId
    ) {
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

    await refreshQueue();
}

async function handleRequeue(queueEntryId, buttonElement) {
    if (!buttonElement) return;
    
    buttonElement.disabled = true;

    try {
        clearError();
        setStatus("Re-queuing patient...");

        await requeueQueueEntry(queueEntryId);
        await refreshQueue(); 

        setStatus(
            `Ready — ${
                selectedQueueEntry
                    ? getQueueTokenLabel(selectedQueueEntry)
                    : "no current patient"
            }`
        );

    } catch (error) {
        console.error("Failed to requeue entry:", error);
        showError(error.message || "Unable to re-queue patient.");
        setStatus("Ready — no current patient");

    } finally {
        buttonElement.disabled = false;
    }
}

/* ============================================================
   KEYBOARD SHORTCUTS
   ============================================================ */

function setupKeyboardShortcuts() {
    document.addEventListener("keydown", (event) => {
        // ESC to close drawer
        if (event.key === "Escape" && drawerOpen) {
            event.preventDefault();
            closeRegistrationDrawer();
            return;
        }

        // Ctrl/Cmd + Enter to save and close
        if ((event.ctrlKey || event.metaKey) && event.key === "Enter" && drawerOpen) {
            event.preventDefault();
            handleRegistrationSubmit();
            return;
        }
    });
}

function attachEventListeners() {
    if (elements.loginForm) {
        elements.loginForm.addEventListener("submit", handleLogin);
    }
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

    // Drawer controls
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

    // Registration form
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

function initialize() {
    setupKeyboardShortcuts();
    attachEventListeners();
    setStatus("Please sign in to manage the queue");
    showElement(elements.queuePanel);
    if (elements.queueBody) {
        elements.queueBody.innerHTML = "";
    }
}

if (document.getElementById("login-form")) {
    initialize();
}

export {
    getActionStates,
    getPatientLabel,
    getQueueTokenLabel,
    updateOwnershipDisplay,
    selectQueueEntry,
    refreshQueue,
    handleRequeue,
    performTransition,
    getActionStatesForTest,
    openRegistrationDrawer,
    closeRegistrationDrawer,
};