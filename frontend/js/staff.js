/* ==========================================================================
   HPQMS Staff Dashboard
   js/staff.js
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
    element.classList.remove("hidden");
}

function hideElement(element) {
    element.classList.add("hidden");
}

function setText(element, text) {
    element.textContent = text ?? "";
}

function setStatus(text) {
    setText(elements.dashboardSubtitle, text);
}

function showError(message) {
    setText(elements.loginError, message);
    elements.loginError.classList.remove("hidden");

    if (elements.actionError) {
        setText(elements.actionError, message);
        elements.actionError.classList.remove("hidden");
    }
}

function clearError() {
    elements.loginError.classList.add("hidden");
    setText(elements.loginError, "");

    if (elements.actionError) {
        elements.actionError.classList.add("hidden");
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

    // Fallbacks if first/last name fields are empty strings or null
    if (patient.temporary_identifier) return `Temp ID: ${patient.temporary_identifier}`;
    if (patient.national_id) return `ID: ${patient.national_id}`;

    return "Unknown patient";
}

function renderQueueTable() {
    elements.queueBody.innerHTML = "";

    if (queueEntries.length === 0) {
        hideElement(elements.queueTable);
        elements.queueState.textContent = "No active queue entries found for this department.";
        showElement(elements.queueState);
        return;
    }

    hideElement(elements.queueState);
    showElement(elements.queueTable);

    for (const entry of queueEntries) {
        const tr = document.createElement("tr");
        tr.classList.add("queue-row");
        tr.dataset.entryId = entry.queue_entry_id;

        if (
            selectedQueueEntry &&
            selectedQueueEntry.queue_entry_id === entry.queue_entry_id
        ) {
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

    const isOwner =
        user &&
        String(entry.assigned_staff_id) === String(user.staff_id);

    return {
        call:
            entry.status === "WAITING" &&
            !entry.assigned_staff_id,

        start:
            entry.status === "CALLED" &&
            isOwner,

        noShow:
            entry.status === "CALLED" &&
            isOwner,

        complete:
            entry.status === "IN_PROGRESS" &&
            isOwner,
    };
}

function getActionStates(entry) {
    return getActionStatesForTest(entry, currentUser);
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

                console.log(
                    "[STAFF WS] Connected"
                );

                /*
                 * The connection may have been established after
                 * the initial queue load, so recover authoritative
                 * state when connected.
                 */
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

                console.warn(
                    "[STAFF WS] Disconnected"
                );
            },
        ],

        [
            "reconnecting",
            (details) => {
                websocketConnected = false;

                console.warn(
                    "[STAFF WS] Reconnecting:",
                    details
                );
            },
        ],

        [
            "error",
            (error) => {
                console.error(
                    "[STAFF WS] Error:",
                    error
                );
            },
        ],
    ];

    for (const [eventName, callback] of subscriptions) {
        onStaffWebSocket(
            eventName,
            callback
        );

        staffWebSocketSubscriptions.push({
            eventName,
            callback,
        });
    }
}

function unregisterStaffWebSocketListeners() {
    for (const {
        eventName,
        callback,
    } of staffWebSocketSubscriptions) {
        offStaffWebSocket(
            eventName,
            callback
        );
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

function updateCurrentPatientPanel() {
    if (!selectedQueueEntry) {
        hideElement(elements.currentPatientPanel);
        return;
    }

    setText(elements.currentToken, getQueueTokenLabel(selectedQueueEntry));
    setText(elements.currentStatus, selectedQueueEntry.status);
    setText(elements.currentPatient, getPatientLabel(selectedQueueEntry));
    setText(elements.currentPriority, selectedQueueEntry.priority);
    showElement(elements.currentPatientPanel);

    // Update ownership display for the selected entry
    updateOwnershipDisplay(selectedQueueEntry);

    const states = getActionStates(selectedQueueEntry);

    elements.callButton.disabled = !states.call;
    elements.startButton.disabled = !states.start;
    elements.noShowButton.disabled = !states.noShow;
    elements.completeButton.disabled = !states.complete;

    elements.callButton.className = states.call ? "button-primary" : "button-disabled";
    elements.startButton.className = states.start ? "button-secondary" : "button-disabled";
    elements.noShowButton.className = states.noShow ? "button-danger" : "button-disabled";
    elements.completeButton.className = states.complete ? "button-danger" : "button-disabled";
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

    elements.noShowBody.innerHTML = "";

    if (noShowEntries.length === 0) {
        hideElement(elements.noShowTable);
        showElement(elements.noShowState);

        elements.noShowState.textContent =
            "No patients are currently marked as no-show.";

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
        noShowEntries = await getDepartmentNoShowQueue(
            selectedDepartmentId
        );

        console.log(
            "No-Show Queue Count:",
            noShowEntries.length,
            noShowEntries
        );

        renderNoShowTable();
    } catch (error) {
        console.error("Unable to refresh no-show queue:", error);

        setText(
            elements.noShowState,
            "Unable to load no-show patients."
        );

        showElement(elements.noShowState);
    }
}


async function refreshQueue() {
    if (!selectedDepartmentId) {
        return;
    }

    /*
     * If a refresh is already running, remember that another
     * refresh was requested rather than starting competing
     * HTTP requests.
     */
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

            /*
             * Run one final refresh so that events received
             * while the previous request was running are not lost.
             */
            await refreshQueue();
        }
    }
}
async function requeueNoShowEntry(queueEntryId) {
    try {
        clearError();

        setStatus("Re-queuing patient...");

        const updatedEntry = await requeueQueueEntry(
            queueEntryId
        );

        console.log(
            "[REQUEUE SUCCESS]",
            updatedEntry
        );

        /*
         * Refresh both active and no-show queues.
         *
         * The patient should disappear from NO_SHOW
         * and reappear in the active queue.
         */
        await refreshQueue();

        setStatus(
            `Ready — ${selectedQueueEntry
                ? getQueueTokenLabel(selectedQueueEntry)
                : "no current patient"
            }`
        );

    } catch (error) {
        console.error(
            "[REQUEUE FAILED]",
            error
        );

        showError(
            error.message ||
            "Unable to re-queue patient."
        );
    }
}

async function performTransition(action) {
    if (!selectedQueueEntry) {
        return;
    }

    try {
        setStatus(`Performing ${action}...`);

        let updatedEntry = null;

        clearError();

        if (action === "call") {
            // CALL must always target the backend-determined next patient.
            // This guarantees priority ordering is respected even if
            // another queue row is currently selected.
            const nextEntry = await getNextPatient(selectedDepartmentId);

            if (!nextEntry) {
                throw new Error("No waiting patients in the queue.");
            }

            updatedEntry = await callQueueEntry(
                nextEntry.queue_entry_id
            );

            // The patient actually called may be different from the
            // previously selected queue entry.
            selectedQueueEntry = updatedEntry;

        } else if (action === "start") {
            updatedEntry = await startQueueEntry(
                selectedQueueEntry.queue_entry_id
            );

        } else if (action === "noshow") {
            updatedEntry = await markNoShowQueueEntry(
                selectedQueueEntry.queue_entry_id
            );

        } else if (action === "complete") {
            updatedEntry = await completeQueueEntry(
                selectedQueueEntry.queue_entry_id
            );
        }

        // Keep existing visit/patient data if the patch response
        // returns an unpopulated visit.
        if (updatedEntry) {
            if (
                !updatedEntry.visit?.patient &&
                selectedQueueEntry?.visit?.patient
            ) {
                updatedEntry.visit = selectedQueueEntry.visit;
            }

            selectedQueueEntry = updatedEntry;
        }

        // Re-fetch the entire department queue with fresh selectinloads.
        await refreshQueue();

        setStatus(
            `Ready — ${selectedQueueEntry
                ? getQueueTokenLabel(selectedQueueEntry)
                : "no current patient"
            }`
        );

    } catch (error) {
        console.error(error);

        // Handle common authorization/conflict responses with clear UX
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

    hideElement(elements.logoutButton);
    hideElement(elements.currentPatientPanel);
    hideElement(elements.queueTable);

    showElement(elements.loginPanel);

    setStatus("Please sign in to manage the queue");

    elements.queueBody.innerHTML = "";
    elements.queueState.textContent =
        "Log in to view department queue entries.";

    showElement(elements.queueState);

    clearError();
}


function eventBelongsToCurrentDepartment(event) {
    if (!event || !selectedDepartmentId) {
        return false;
    }

    const departmentId = String(selectedDepartmentId);

    if (
        event.department_id &&
        String(event.department_id) === departmentId
    ) {
        return true;
    }

    /*
     * PATIENT_ROUTED contains source and target department IDs
     * rather than necessarily using department_id.
     */
    if (
        event.event_type === "PATIENT_ROUTED"
    ) {
        return (
            String(event.source_department_id) === departmentId ||
            String(event.target_department_id) === departmentId
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
    // 1. Prevent duplicate clicks
    if (buttonElement) {
        buttonElement.disabled = true;
    }

    try {
        clearError();
        setStatus("Re-queuing patient...");

        // 2. Perform API transition & refresh queue state
        await requeueQueueEntry(queueEntryId);
        const updatedState = await refreshQueue(); 

        // Use updated state or fall back to selectedQueueEntry
        const currentActive = updatedState?.selectedQueueEntry ?? selectedQueueEntry;

        setStatus(
            `Ready — ${
                currentActive
                    ? getQueueTokenLabel(currentActive)
                    : "no current patient"
            }`
        );

    } catch (error) {
        console.error("Failed to requeue entry:", error);

        showError(
            error.message || "Unable to re-queue patient."
        );

        // 3. Reset status text on failure
        setStatus("Ready — no current patient");
    } finally {
        if (buttonElement) {
            buttonElement.disabled = false;
        }
    }
}


function attachEventListeners() {
    elements.loginForm.addEventListener("submit", handleLogin);
    elements.logoutButton.addEventListener("click", handleLogout);
    elements.callButton.addEventListener("click", () => performTransition("call"));
    elements.startButton.addEventListener("click", () => performTransition("start"));
    elements.noShowButton.addEventListener("click", () => performTransition("noshow"));
    elements.completeButton.addEventListener("click", () => performTransition("complete"));

    // Event delegation for dynamically rendered no-show table rows
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

function initialize() {
    attachEventListeners();
    setStatus("Please sign in to manage the queue");
    showElement(elements.queuePanel);
    elements.queueBody.innerHTML = "";
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
};
