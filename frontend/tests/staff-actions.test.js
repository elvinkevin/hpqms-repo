import { describe, it, expect, beforeEach, vi } from "vitest";

/*
 * staff-actions is tested against mocked API + REAL state store and
 * REAL workspace config, so the policy/store wiring is exercised.
 */

const mockApi = vi.hoisted(() => ({
    getNextPatient: vi.fn(),
    callQueueEntry: vi.fn(),
    startQueueEntry: vi.fn(),
    completeQueueEntry: vi.fn(),
    markNoShowQueueEntry: vi.fn(),
    requeueQueueEntry: vi.fn(),
    cancelQueueEntry: vi.fn(),
    setQueuePriority: vi.fn(),
    completePatientRegistration: vi.fn(),
    transferPatient: vi.fn(),
    dischargePatient: vi.fn(),
}));

vi.mock("../js/staff-api.js", () => mockApi);

import {
    setStaffContext,
    getStaffContext,
    registerReconcileHandler,
    callNextPatient,
    startPatient,
    completePatient,
    markNoShowPatient,
    requeuePatient,
    cancelQueueStep,
    updatePriority,
    transferToDepartment,
    dischargeFromCare,
} from "../js/staff-actions.js";

import {
    clear as clearQueueState,
    setContext,
    setSnapshot,
    getState,
    subscribe,
} from "../js/staff-queue-state.js";

import { STAFF_ROLE, ACTION, canPerformAction } from "../js/staff-workspace-config.js";

const DEPT = "dept-1";
const STAFF_A = "staff-a";
const STAFF_B = "staff-b";

function makeEntry(overrides = {}) {
    return {
        queue_entry_id: "q1",
        status: "WAITING",
        priority: "NORMAL",
        assigned_staff_id: null,
        ...overrides,
    };
}

let reconcileSpy;

beforeEach(() => {
    vi.clearAllMocks();
    clearQueueState();

    reconcileSpy = vi.fn().mockResolvedValue(undefined);
    registerReconcileHandler(reconcileSpy);

    setContext(DEPT, STAFF_A);
});

/* ==========================================================================
   STAFF CONTEXT
   ========================================================================== */

describe("staff context", () => {
    it("stores role/department/staff from the user profile", () => {
        setStaffContext({
            staff_id: STAFF_A,
            role: STAFF_ROLE.TRIAGE_NURSE,
            dept_id: DEPT,
        });

        expect(getStaffContext()).toEqual({
            staffId: STAFF_A,
            role: STAFF_ROLE.TRIAGE_NURSE,
            departmentId: DEPT,
        });
    });

    it("clears context on logout (null user)", () => {
        setStaffContext({
            staff_id: STAFF_A,
            role: STAFF_ROLE.DOCTOR,
            dept_id: DEPT,
        });

        setStaffContext(null);

        expect(getStaffContext()).toEqual({
            staffId: null,
            role: null,
            departmentId: null,
        });
    });
});

/* ==========================================================================
   ROLE GATING (UI policy — workspace config)
   ========================================================================== */

describe("role gating", () => {
    it("denies actions not in the role's workspace config", async () => {
        setStaffContext({
            staff_id: STAFF_A,
            role: STAFF_ROLE.RECEPTIONIST,
            dept_id: DEPT,
        });

        await expect(updatePriority("q1", "URGENT")).rejects.toMatchObject({
            status: 403,
        });

        expect(mockApi.setQueuePriority).not.toHaveBeenCalled();
    });

    it("denies transfer for a receptionist", async () => {
        setStaffContext({
            staff_id: STAFF_A,
            role: STAFF_ROLE.RECEPTIONIST,
            dept_id: DEPT,
        });

        await expect(
            transferToDepartment("visit-1", { target_dept_id: "dept-2" })
        ).rejects.toMatchObject({ status: 403 });

        expect(mockApi.transferPatient).not.toHaveBeenCalled();
    });

    it("allows priority for a triage nurse", async () => {
        setStaffContext({
            staff_id: STAFF_A,
            role: STAFF_ROLE.TRIAGE_NURSE,
            dept_id: DEPT,
        });

        mockApi.setQueuePriority.mockResolvedValue(makeEntry({ priority: "URGENT" }));

        await updatePriority("q1", "URGENT");

        expect(mockApi.setQueuePriority).toHaveBeenCalledWith("q1", "URGENT");
    });

    it("allows discharge only for a doctor", async () => {
        setStaffContext({
            staff_id: STAFF_A,
            role: STAFF_ROLE.DOCTOR,
            dept_id: DEPT,
        });

        mockApi.dischargePatient.mockResolvedValue({ visit_id: "visit-1" });

        await dischargeFromCare("visit-1");

        expect(mockApi.dischargePatient).toHaveBeenCalledWith("visit-1");
    });

    it("treats an unknown role as read-only", () => {
        expect(canPerformAction("UNKNOWN_ROLE", ACTION.CALL)).toBe(false);
    });
});

/* ==========================================================================
   CALL — backend-determined next patient
   ========================================================================== */

describe("callNextPatient", () => {
    it("asks the backend for the next patient, then calls it", async () => {
        setStaffContext({
            staff_id: STAFF_A,
            role: STAFF_ROLE.RECEPTIONIST,
            dept_id: DEPT,
        });

        const nextEntry = makeEntry({ queue_entry_id: "q-next" });
        const calledEntry = makeEntry({
            queue_entry_id: "q-next",
            status: "CALLED",
            assigned_staff_id: STAFF_A,
        });

        mockApi.getNextPatient.mockResolvedValue(nextEntry);
        mockApi.callQueueEntry.mockResolvedValue(calledEntry);

        const result = await callNextPatient();

        expect(mockApi.getNextPatient).toHaveBeenCalledWith(DEPT);
        expect(mockApi.callQueueEntry).toHaveBeenCalledWith("q-next");
        expect(result.status).toBe("CALLED");
    });

    it("raises a conflict when the queue is empty", async () => {
        setStaffContext({
            staff_id: STAFF_A,
            role: STAFF_ROLE.RECEPTIONIST,
            dept_id: DEPT,
        });

        mockApi.getNextPatient.mockResolvedValue(null);

        await expect(callNextPatient()).rejects.toMatchObject({ status: 409 });
        expect(mockApi.callQueueEntry).not.toHaveBeenCalled();
    });
});

/* ==========================================================================
   TARGET RESOLUTION — encounter takes precedence over selection
   ========================================================================== */

describe("target resolution", () => {
    it("rejects start when the entry belongs to another staff member", async () => {
        setStaffContext({
            staff_id: STAFF_A,
            role: STAFF_ROLE.DOCTOR,
            dept_id: DEPT,
        });

        setSnapshot({
            queueEntries: [
                makeEntry({
                    queue_entry_id: "q1",
                    status: "CALLED",
                    assigned_staff_id: STAFF_B,
                }),
            ],
        });

        await expect(startPatient("q1")).rejects.toMatchObject({ status: 403 });
        expect(mockApi.startQueueEntry).not.toHaveBeenCalled();
    });

    it("starts the active encounter even when another row is selected", async () => {
        setStaffContext({
            staff_id: STAFF_A,
            role: STAFF_ROLE.DOCTOR,
            dept_id: DEPT,
        });

        const myActive = makeEntry({
            queue_entry_id: "q-active",
            status: "CALLED",
            assigned_staff_id: STAFF_A,
        });

        const otherRow = makeEntry({
            queue_entry_id: "q-other",
            status: "CALLED",
            assigned_staff_id: STAFF_A,
        });

        setSnapshot({ queueEntries: [myActive, otherRow] });

        // Simulate the staff member clicking a different row afterwards.
        const { selectQueueEntry } = await import("../js/staff-queue-state.js");
        selectQueueEntry("q-other");

        mockApi.startQueueEntry.mockResolvedValue(
            makeEntry({ queue_entry_id: "q-active", status: "IN_PROGRESS", assigned_staff_id: STAFF_A })
        );

        const result = await startPatient(); // no explicit id → active encounter

        expect(mockApi.startQueueEntry).toHaveBeenCalledWith("q-active");
        expect(result.status).toBe("IN_PROGRESS");
    });
});

/* ==========================================================================
   STORE INGESTION & RECONCILE
   ========================================================================== */

describe("store ingestion", () => {
    beforeEach(() => {
        setStaffContext({
            staff_id: STAFF_A,
            role: STAFF_ROLE.RECEPTIONIST,
            dept_id: DEPT,
        });
    });

    it("feeds the action result through applyEvent and reconciles", async () => {
        const calledEntry = makeEntry({
            queue_entry_id: "q1",
            status: "CALLED",
            assigned_staff_id: STAFF_A,
        });

        setSnapshot({
            queueEntries: [
                makeEntry({
                    queue_entry_id: "q1",
                    status: "CALLED",
                    assigned_staff_id: STAFF_A,
                }),
            ],
        });

        mockApi.markNoShowQueueEntry.mockResolvedValue(
            makeEntry({ queue_entry_id: "q1", status: "NO_SHOW", assigned_staff_id: STAFF_A })
        );

        await markNoShowPatient("q1");

        const state = getState();

        expect(state.queueEntries).toHaveLength(0);
        expect(state.noShowEntries).toHaveLength(1);
        expect(state.noShowEntries[0].status).toBe("NO_SHOW");
        expect(reconcileSpy).toHaveBeenCalled();
    });

    it("removes a completed entry from the queue", async () => {
        setSnapshot({
            queueEntries: [
                makeEntry({
                    queue_entry_id: "q1",
                    status: "IN_PROGRESS",
                    assigned_staff_id: STAFF_A,
                }),
            ],
        });

        mockApi.completeQueueEntry.mockResolvedValue(
            makeEntry({ queue_entry_id: "q1", status: "COMPLETED" })
        );

        await completePatient("q1");

        expect(getState().queueEntries).toHaveLength(0);
    });

    it("moves a requeued no-show entry back to the waiting queue", async () => {
        setSnapshot({ queueEntries: [], noShowEntries: [makeEntry({ status: "NO_SHOW" })] });

        mockApi.requeueQueueEntry.mockResolvedValue(
            makeEntry({ queue_entry_id: "q1", status: "WAITING", assigned_staff_id: null })
        );

        await requeuePatient("q1");

        const state = getState();

        expect(state.queueEntries).toHaveLength(1);
        expect(state.queueEntries[0].status).toBe("WAITING");
    });

    it("ingests a cancelled step as removed from the queue", async () => {
        setStaffContext({
            staff_id: STAFF_A,
            role: STAFF_ROLE.DOCTOR,
            dept_id: DEPT,
        });

        setSnapshot({
            queueEntries: [
                makeEntry({
                    queue_entry_id: "q1",
                    status: "WAITING",
                    assigned_staff_id: null,
                }),
            ],
        });

        mockApi.cancelQueueEntry.mockResolvedValue(
            makeEntry({ queue_entry_id: "q1", status: "CANCELLED" })
        );

        await cancelQueueStep("q1");

        expect(getState().queueEntries).toHaveLength(0);
    });
});

/* ==========================================================================
   VALIDATION
   ========================================================================== */

describe("validation", () => {
    beforeEach(() => {
        setStaffContext({
            staff_id: STAFF_A,
            role: STAFF_ROLE.TRIAGE_NURSE,
            dept_id: DEPT,
        });
    });

    it("rejects a priority update without a priority value", async () => {
        await expect(updatePriority("q1", null)).rejects.toMatchObject({ status: 422 });
        expect(mockApi.setQueuePriority).not.toHaveBeenCalled();
    });

    it("rejects a transfer without a target department", async () => {
        await expect(
            transferToDepartment("visit-1", {})
        ).rejects.toMatchObject({ status: 422 });
        expect(mockApi.transferPatient).not.toHaveBeenCalled();
    });

    it("rejects a discharge without a visit id", async () => {
        setStaffContext({
            staff_id: STAFF_A,
            role: STAFF_ROLE.DOCTOR,
            dept_id: DEPT,
        });

        await expect(dischargeFromCare(null)).rejects.toMatchObject({ status: 422 });
        expect(mockApi.dischargePatient).not.toHaveBeenCalled();
    });
});
