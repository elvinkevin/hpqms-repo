import { beforeEach, describe, expect, it } from "vitest";
import {
    applyEvent,
    clear,
    getDepartmentQueue,
    getMyActivePatient,
    getMyNoShowEntries,
    getState,
    isMyPatient,
    setContext,
    setSnapshot,
} from "../js/staff-queue-state.js";

describe("staff-queue-state", () => {
    beforeEach(() => {
        clear();
    });

    describe("initial state", () => {
        it("starts empty and uninitialized", () => {
            const state = getState();

            expect(state).toEqual({
                departmentId: null,
                staffId: null,
                queueEntries: [],
                noShowEntries: [],
                activePatient: null,
                initialized: false,
                stale: false,
            });
        });
    });

    describe("context", () => {
        it("stores the current department and staff identity", () => {
            setContext("dept-001", "staff-001");

            const state = getState();

            expect(state.departmentId).toBe("dept-001");
            expect(state.staffId).toBe("staff-001");
        });

        it("clears previously loaded state if context changes", () => {
            setContext("dept-001", "staff-001");
            setSnapshot({
                queueEntries: [
                    {
                        queue_entry_id: "queue-101",
                        assigned_staff_id: "staff-001",
                        status: "CALLED",
                    },
                ],
                noShowEntries: [],
            });

            // Switch staff context
            setContext("dept-001", "staff-002");

            const state = getState();
            expect(state.departmentId).toBe("dept-001");
            expect(state.staffId).toBe("staff-002");
            expect(state.queueEntries).toEqual([]);
            expect(state.initialized).toBe(false);
        });
    });

    describe("setSnapshot()", () => {
        it("ingests department queue and no-show entries into state", () => {
            setContext("dept-001", "staff-001");

            const rawSnapshot = {
                queueEntries: [
                    {
                        queue_entry_id: "queue-101",
                        assigned_staff_id: null,
                        status: "WAITING",
                    },
                    {
                        queue_entry_id: "queue-102",
                        assigned_staff_id: "staff-001",
                        status: "CALLED",
                    },
                ],
                noShowEntries: [
                    {
                        queue_entry_id: "queue-099",
                        assigned_staff_id: "staff-001",
                        status: "NO_SHOW",
                    },
                ],
            };

            setSnapshot(rawSnapshot);

            const state = getState();
            expect(state.initialized).toBe(true);
            expect(state.stale).toBe(false);
            expect(getDepartmentQueue()).toHaveLength(2);
        });

        it("derives my active patient upon ingesting snapshot", () => {
            setContext("dept-001", "staff-001");

            setSnapshot({
                queueEntries: [
                    {
                        queue_entry_id: "queue-101",
                        assigned_staff_id: null,
                        status: "WAITING",
                    },
                    {
                        queue_entry_id: "queue-102",
                        assigned_staff_id: "staff-001",
                        status: "IN_PROGRESS",
                    },
                ],
                noShowEntries: [],
            });

            expect(getMyActivePatient()).toEqual(
                expect.objectContaining({
                    queue_entry_id: "queue-102",
                    assigned_staff_id: "staff-001",
                    status: "IN_PROGRESS",
                })
            );
        });
    });

    describe("ownership checks: isMyPatient()", () => {
        it("identifies a patient assigned to the current staff member", () => {
            setContext("dept-001", "staff-001");

            const entry = {
                queue_entry_id: "queue-001",
                assigned_staff_id: "staff-001",
                status: "CALLED",
            };

            expect(isMyPatient(entry)).toBe(true);
        });

        it("handles numeric/string ID coercion correctly", () => {
            setContext("dept-001", "101");

            const entry = {
                queue_entry_id: "queue-001",
                assigned_staff_id: 101,
                status: "CALLED",
            };

            expect(isMyPatient(entry)).toBe(true);
        });

        it("does not identify another staff member's patient as mine", () => {
            setContext("dept-001", "staff-001");

            const entry = {
                queue_entry_id: "queue-001",
                assigned_staff_id: "staff-002",
                status: "CALLED",
            };

            expect(isMyPatient(entry)).toBe(false);
        });

        it("does not treat an unassigned patient as owned", () => {
            setContext("dept-001", "staff-001");

            const entry = {
                queue_entry_id: "queue-001",
                assigned_staff_id: null,
                status: "WAITING",
            };

            expect(isMyPatient(entry)).toBe(false);
        });

        it("returns false if staff context is not set", () => {
            const entry = {
                queue_entry_id: "queue-001",
                assigned_staff_id: "staff-001",
                status: "CALLED",
            };

            expect(isMyPatient(entry)).toBe(false);
        });
    });

    describe("getMyActivePatient()", () => {
        it("returns null if there is no active patient assigned to current staff", () => {
            setContext("dept-001", "staff-001");

            setSnapshot({
                queueEntries: [
                    {
                        queue_entry_id: "queue-101",
                        assigned_staff_id: null,
                        status: "WAITING",
                    },
                    {
                        queue_entry_id: "queue-102",
                        assigned_staff_id: "staff-002",
                        status: "CALLED",
                    },
                ],
                noShowEntries: [],
            });

            expect(getMyActivePatient()).toBeNull();
        });

        it("returns the active patient (CALLED status) owned by the current staff member", () => {
            setContext("dept-001", "staff-001");

            setSnapshot({
                queueEntries: [
                    {
                        queue_entry_id: "queue-101",
                        assigned_staff_id: null,
                        status: "WAITING",
                    },
                    {
                        queue_entry_id: "queue-102",
                        assigned_staff_id: "staff-002",
                        status: "CALLED",
                    },
                    {
                        queue_entry_id: "queue-103",
                        assigned_staff_id: "staff-001",
                        status: "CALLED",
                    },
                ],
                noShowEntries: [],
            });

            expect(getMyActivePatient()).toEqual(
                expect.objectContaining({
                    queue_entry_id: "queue-103",
                    assigned_staff_id: "staff-001",
                    status: "CALLED",
                })
            );
        });

        it("returns the active patient (IN_PROGRESS status) owned by the current staff member", () => {
            setContext("dept-001", "staff-001");

            setSnapshot({
                queueEntries: [
                    {
                        queue_entry_id: "queue-101",
                        assigned_staff_id: null,
                        status: "WAITING",
                    },
                    {
                        queue_entry_id: "queue-102",
                        assigned_staff_id: "staff-002",
                        status: "CALLED",
                    },
                    {
                        queue_entry_id: "queue-103",
                        assigned_staff_id: "staff-001",
                        status: "IN_PROGRESS",
                    },
                ],
                noShowEntries: [],
            });

            expect(getMyActivePatient()).toEqual(
                expect.objectContaining({
                    queue_entry_id: "queue-103",
                    assigned_staff_id: "staff-001",
                    status: "IN_PROGRESS",
                })
            );
        });

        it("ignores COMPLETED or NO_SHOW entries assigned to current staff", () => {
            setContext("dept-001", "staff-001");

            setSnapshot({
                queueEntries: [
                    {
                        queue_entry_id: "queue-101",
                        assigned_staff_id: "staff-001",
                        status: "COMPLETED",
                    },
                ],
                noShowEntries: [
                    {
                        queue_entry_id: "queue-102",
                        assigned_staff_id: "staff-001",
                        status: "NO_SHOW",
                    },
                ],
            });

            expect(getMyActivePatient()).toBeNull();
        });
    });

    describe("getMyNoShowEntries()", () => {
        it("returns only no-show patients assigned to the current staff member", () => {
            setContext("dept-001", "staff-001");

            setSnapshot({
                queueEntries: [],
                noShowEntries: [
                    {
                        queue_entry_id: "queue-101",
                        assigned_staff_id: "staff-001",
                        status: "NO_SHOW",
                    },
                    {
                        queue_entry_id: "queue-102",
                        assigned_staff_id: "staff-002",
                        status: "NO_SHOW",
                    },
                    {
                        queue_entry_id: "queue-103",
                        assigned_staff_id: "staff-001",
                        status: "NO_SHOW",
                    },
                ],
            });

            const myNoShows = getMyNoShowEntries();

            expect(myNoShows).toHaveLength(2);
            expect(myNoShows.map((entry) => entry.queue_entry_id)).toEqual([
                "queue-101",
                "queue-103",
            ]);
        });

        it("returns an empty array if no no-shows are assigned to current staff", () => {
            setContext("dept-001", "staff-001");

            setSnapshot({
                queueEntries: [],
                noShowEntries: [
                    {
                        queue_entry_id: "queue-102",
                        assigned_staff_id: "staff-002",
                        status: "NO_SHOW",
                    },
                ],
            });

            expect(getMyNoShowEntries()).toEqual([]);
        });
    });

    describe("clear()", () => {
        it("resets state to initial values", () => {
            setContext("dept-001", "staff-001");
            setSnapshot({
                queueEntries: [
                    {
                        queue_entry_id: "queue-101",
                        assigned_staff_id: "staff-001",
                        status: "CALLED",
                    },
                ],
                noShowEntries: [],
            });

            clear();

            expect(getState()).toEqual({
                departmentId: null,
                staffId: null,
                queueEntries: [],
                noShowEntries: [],
                activePatient: null,
                initialized: false,
                stale: false,
            });
        });
    });

    describe("applyEvent()", () => {
    beforeEach(() => {
        clear();
        setContext("dept-1", "staff-1");

        setSnapshot({
            queueEntries: [
                {
                    queue_entry_id: "q1",
                    status: "WAITING",
                    assigned_staff_id: null,
                },
                {
                    queue_entry_id: "q2",
                    status: "CALLED",
                    assigned_staff_id: "staff-1",
                },
                {
                    queue_entry_id: "q3",
                    status: "CALLED",
                    assigned_staff_id: "staff-2",
                },
            ],
            noShowEntries: [],
        });
    });

    it("updates a queue entry when TOKEN_CALLED is received", () => {
        applyEvent({
            event_type: "TOKEN_CALLED",
            queue_entry_id: "q1",
            assigned_staff_id: "staff-1",
        });

        const entry = getDepartmentQueue().find(
            (entry) => entry.queue_entry_id === "q1"
        );

        expect(entry).toMatchObject({
            queue_entry_id: "q1",
            status: "CALLED",
            assigned_staff_id: "staff-1",
        });
    });

    it("derives the called patient as my active patient", () => {
        applyEvent({
            event_type: "TOKEN_CALLED",
            queue_entry_id: "q1",
            assigned_staff_id: "staff-1",
        });

        expect(getMyActivePatient()).toMatchObject({
            queue_entry_id: "q1",
            status: "CALLED",
            assigned_staff_id: "staff-1",
        });
    });

  it("does not treat another staff member's called patient as mine", () => {
    setContext("dept-1", "staff-1");

    applyEvent({
        event_type: "TOKEN_CALLED",
        queue_entry_id: "q2",
        assigned_staff_id: "staff-2", // Must differ from active context ("staff-1")
    });

    expect(getMyActivePatient()).toBeNull();
});

    it("updates a queue entry to IN_PROGRESS", () => {
        applyEvent({
            event_type: "TOKEN_SERVICE_STARTED",
            queue_entry_id: "q2",
            assigned_staff_id: "staff-1",
        });

        const entry = getDepartmentQueue().find(
            (entry) => entry.queue_entry_id === "q2"
        );

        expect(entry.status).toBe("IN_PROGRESS");

        expect(getMyActivePatient()).toMatchObject({
            queue_entry_id: "q2",
            status: "IN_PROGRESS",
        });
    });

    it("removes a completed patient from the department queue", () => {
        applyEvent({
            event_type: "TOKEN_COMPLETED",
            queue_entry_id: "q2",
        });

        expect(
            getDepartmentQueue().some(
                (entry) => entry.queue_entry_id === "q2"
            )
        ).toBe(false);

        expect(getMyActivePatient()).toBeNull();
    });

    it("removes a cancelled patient from the department queue", () => {
        applyEvent({
            event_type: "TOKEN_CANCELLED",
            queue_entry_id: "q2",
        });

        expect(
            getDepartmentQueue().some(
                (entry) => entry.queue_entry_id === "q2"
            )
        ).toBe(false);
    });

    it("moves a patient into the no-show state", () => {
        applyEvent({
            event_type: "TOKEN_NO_SHOW",
            queue_entry_id: "q2",
            assigned_staff_id: "staff-1",
        });

        expect(
            getDepartmentQueue().some(
                (entry) => entry.queue_entry_id === "q2"
            )
        ).toBe(false);

        expect(getMyNoShowEntries()).toEqual([
            expect.objectContaining({
                queue_entry_id: "q2",
                status: "NO_SHOW",
                assigned_staff_id: "staff-1",
            }),
        ]);

        expect(getMyActivePatient()).toBeNull();
    });

    it("does not expose another staff member's no-show patient", () => {
        applyEvent({
            event_type: "TOKEN_NO_SHOW",
            queue_entry_id: "q3",
            assigned_staff_id: "staff-2",
        });

        expect(getMyNoShowEntries()).toEqual([]);
    });

    it("handles PATIENT_ROUTED with a complete queue entry", () => {
        applyEvent({
            event_type: "PATIENT_ROUTED",
            queue_entry: {
                queue_entry_id: "q4",
                status: "WAITING",
                assigned_staff_id: null,
            },
        });

        expect(
            getDepartmentQueue()
        ).toContainEqual(
            expect.objectContaining({
                queue_entry_id: "q4",
                status: "WAITING",
            })
        );
    });

    it("marks state stale when QUEUE_UPDATED is received", () => {
        applyEvent({
            event_type: "QUEUE_UPDATED",
        });

        expect(getState().stale).toBe(true);
    });

    it("ignores malformed events safely", () => {
        expect(() => applyEvent(null)).not.toThrow();
        expect(() => applyEvent({})).not.toThrow();
        expect(() => applyEvent("invalid")).not.toThrow();
    });

    it("ignores unknown event types safely", () => {
        expect(() =>
            applyEvent({
                event_type: "SOME_UNKNOWN_EVENT",
                queue_entry_id: "q1",
            })
        ).not.toThrow();

        expect(getState().stale).toBe(false);
    });
});

});