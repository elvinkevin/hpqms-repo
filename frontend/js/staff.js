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
} from "./staff-api.js";

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

function getActionStates(status) {
    return {
        call: status === "WAITING",
        start: status === "CALLED",
        noShow: status === "CALLED",
        complete: status === "IN_PROGRESS",
    };
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

    const states = getActionStates(selectedQueueEntry.status);

    elements.callButton.disabled = !states.call;
    elements.startButton.disabled = !states.start;
    elements.noShowButton.disabled = !states.noShow;
    elements.completeButton.disabled = !states.complete;

    elements.callButton.className = states.call ? "button-primary" : "button-disabled";
    elements.startButton.className = states.start ? "button-secondary" : "button-disabled";
    elements.noShowButton.className = states.noShow ? "button-danger" : "button-disabled";
    elements.completeButton.className = states.complete ? "button-danger" : "button-disabled";
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
        setText(
            elements.noShowState,
            "No patients are currently marked as no-show."
        );
        showElement(elements.noShowState);
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
                    class="button-primary requeue-button"
                    data-entry-id="${entry.queue_entry_id}"
                >
                    RE-QUEUE
                </button>
            </td>
        `;

        const button = tr.querySelector(".requeue-button");

        button.addEventListener("click", () => {
            requeueNoShowEntry(entry.queue_entry_id);
        });

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

    try {
        queueEntries = await getDepartmentQueue(selectedDepartmentId);

        noShowEntries = await getDepartmentNoShowQueue(
            selectedDepartmentId
        );

        console.log(
            "Queue Refresh Snapshot",
            {
                active: queueEntries,
                noShow: noShowEntries,
            }
        );

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
            "Unable to refresh queue. Please try again."
        );
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
            `Ready — ${
                selectedQueueEntry
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
            `Ready — ${
                selectedQueueEntry
                    ? getQueueTokenLabel(selectedQueueEntry)
                    : "no current patient"
            }`
        );

    } catch (error) {
        console.error(error);
        showError(error.message || "Action failed. Please try again.");
    }
}

async function identifyDepartment() {
    try {
        setStatus("Loading department queue...");
        const departments = await getDepartments();
        selectedDepartmentId = departments[0]?.dept_id ?? null;

        if (!selectedDepartmentId) {
            throw new Error("No active departments available.");
        }

        await refreshQueue();
        setStatus("Ready");
    } catch (error) {
        console.error(error);
        showError(error.message || "Unable to load department.");
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
    logout();
    queueEntries = [];
    noShowEntries = [];
    selectedQueueEntry = null;
    selectedDepartmentId = null;
    hideElement(elements.logoutButton);
    hideElement(elements.currentPatientPanel);
    hideElement(elements.queuePanel);
    hideElement(elements.noShowPanel);
    showElement(elements.loginPanel);
    setStatus("Please sign in to manage the queue");
    elements.queueBody.innerHTML = "";
    elements.queueState.textContent = "Log in to view department queue entries.";
    showElement(elements.queueState);
    clearError();
}

function attachEventListeners() {
    elements.loginForm.addEventListener("submit", handleLogin);
    elements.logoutButton.addEventListener("click", handleLogout);
    elements.callButton.addEventListener("click", () => performTransition("call"));
    elements.startButton.addEventListener("click", () => performTransition("start"));
    elements.noShowButton.addEventListener("click", () => performTransition("noshow"));
    elements.completeButton.addEventListener("click", () => performTransition("complete"));
}

function initialize() {
    attachEventListeners();
    setStatus("Please sign in to manage the queue");
    showElement(elements.queuePanel);
    elements.queueBody.innerHTML = "";
}

initialize();
