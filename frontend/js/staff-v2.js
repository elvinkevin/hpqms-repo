/* ========================================================================
   HPQMS Staff V2 Bootstrap
   js/staff-v2.js
   ======================================================================== */

import {
    getCurrentUser,
    getDepartments,
    getDepartmentQueue,
    getDepartmentNoShowQueue,
    logout,
} from "./staff-api.js";
import { getSession } from "./staff-session.js";
import {
    clearStaffContext,
    initializeStaffContext,
    getStaffContext,
} from "./staff-context.js";
import { onLogout, renderStaffHeader, renderStationPill } from "./components/staff-header.js";
import {
    mount as mountEncounterPanel,
    unmount as unmountEncounterPanel,
} from "./components/encounter-panel.js";
import {
    getWorkspaceForRole,
} from "./staff-workspace-config.js";
import {
    initializeQueuePanel,
    renderQueuePanel,
} from "./components/queue-panel.js";
import {
    callNextPatient,
    markNoShowPatient,
    registerReconcileHandler,
    requeuePatient,
    setStaffContext,
    startPatient,
} from "./staff-actions.js";
import {
    applyEvent,
    getMyActivePatient,
    getSelectedQueueEntry,
    setContext,
    setSnapshot,
    subscribe,
} from "./staff-queue-state.js";
import {
    connect as connectStaffWebSocket,
    disconnect as disconnectStaffWebSocket,
    off as offStaffWebSocket,
    on as onStaffWebSocket,
} from "./staff-websocket.js";

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

let currentContext = null;
let syncInProgress = false;
let syncPending = false;
let websocketSubscriptions = [];

function setStatus(message) {
    const lastUpdated = document.getElementById("lastUpdated");
    if (lastUpdated) lastUpdated.textContent = message;
}

function showActionError(error) {
    console.error("[StaffV2] Workflow action failed:", error);
    setStatus(error?.message || "Unable to complete that action.");
}

async function synchronizeQueue() {
    if (!currentContext?.departmentId) return;

    if (syncInProgress) {
        syncPending = true;
        return;
    }

    syncInProgress = true;
    try {
        const [queueEntries, noShowEntries] = await Promise.all([
            getDepartmentQueue(currentContext.departmentId),
            getDepartmentNoShowQueue(currentContext.departmentId),
        ]);

        setSnapshot({ queueEntries, noShowEntries });
    } finally {
        syncInProgress = false;
        if (syncPending) {
            syncPending = false;
            await synchronizeQueue();
        }
    }
}

function eventBelongsToDepartment(event) {
    const departmentId = String(currentContext?.departmentId || "");
    if (!departmentId) return false;

    return (
        String(event?.dept_id || "") === departmentId
        || (
            event?.event_type === "PATIENT_ROUTED"
            && (
                String(event.source_dept_id || "") === departmentId
                || String(event.target_dept_id || "") === departmentId
            )
        )
    );
}

async function handleWebSocketMessage(event) {
    if (!STAFF_QUEUE_EVENTS.has(event?.event_type) || !eventBelongsToDepartment(event)) {
        return;
    }

    if (event.event_type !== "QUEUE_UPDATED") {
        applyEvent(event);
    }

    await synchronizeQueue();
}

function startStaffWebSocket() {
    const subscriptions = [
        ["message", handleWebSocketMessage],
        ["connected", synchronizeQueue],
    ];

    for (const [eventName, callback] of subscriptions) {
        onStaffWebSocket(eventName, callback);
        websocketSubscriptions.push({ eventName, callback });
    }

    connectStaffWebSocket();
}

function stopStaffWebSocket() {
    disconnectStaffWebSocket();
    for (const { eventName, callback } of websocketSubscriptions) {
        offStaffWebSocket(eventName, callback);
    }
    websocketSubscriptions = [];
}

async function runAction(action) {
    try {
        if (action === "call") {
            await callNextPatient();
        } else {
            const selected = getMyActivePatient() || getSelectedQueueEntry();
            if (!selected) {
                throw new Error("Select a patient first.");
            }

            if (action === "start") {
                await startPatient(selected.queue_entry_id);
            } else if (action === "no-show") {
                await markNoShowPatient(selected.queue_entry_id);
            }
        }
    } catch (error) {
        showActionError(error);
    }
}

async function requeueEntry(entryId, button) {
    if (!entryId) return;
    if (button) button.disabled = true;

    try {
        await requeuePatient(entryId);
    } catch (error) {
        showActionError(error);
    } finally {
        if (button) button.disabled = false;
    }
}

async function initializeDashboard() {
    if (!getSession()?.accessToken) {
        window.location.replace("./staff-login.html");
        return;
    }

    try {
        const user = await getCurrentUser();

        if (user.role === "ADMIN") {
            window.location.replace("./admin.html");
            return;
        }

        /*
         * STATION GATE — an unbound staff member is routed to the
         * station selection interstitial before the dashboard loads.
         */
        if (!user.station) {
            window.location.replace("./staff-station-select.html");
            return;
        }

        const departments = await getDepartments();
        const department = departments.find(
            (item) => String(item.dept_id) === String(user.dept_id)
        );

        const context = initializeStaffContext({
            ...user,
            department,
        });

        currentContext = context;
        setStaffContext(user);
        setContext(context.departmentId, context.staffId);
        registerReconcileHandler(synchronizeQueue);
        renderStaffHeader(context);

        /*
         * The shell resolves the workspace from the authenticated
         * role — the encounter panel never performs authorization.
         */
        mountEncounterPanel(
            document.getElementById("encounterMount"),
            { workspace: getWorkspaceForRole(user.role) }
        );

        /*
         * Top-bar station pill — compact indicator with a switch/
         * checkout popover. Replaces the in-column service point bar.
         */
        renderStationPill(user.station, department);

        await synchronizeQueue();
        startStaffWebSocket();
        setStatus(`Ready - ${context.firstName} ${context.lastName}`);
    } catch (error) {
        console.error("[StaffV2] Context initialization failed:", error);
        logout();
        clearStaffContext();
        window.location.replace("./staff-login.html");
    }
}

function handleLogout() {
    stopStaffWebSocket();
    unmountEncounterPanel();
    logout();
    setStaffContext(null);
    clearStaffContext();
    window.location.replace("./staff-login.html");
}

subscribe(renderQueuePanel);
initializeQueuePanel({
    onRefresh: synchronizeQueue,
    onRequeue: requeueEntry,
});
document.getElementById("callNextBtn")?.addEventListener("click", () => runAction("call"));
document.getElementById("startServiceBtn")?.addEventListener("click", () => runAction("start"));
document.getElementById("markNoShowBtn")?.addEventListener("click", () => runAction("no-show"));
onLogout(handleLogout);

initializeDashboard();
