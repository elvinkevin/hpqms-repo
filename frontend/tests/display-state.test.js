import { beforeEach, describe, expect, it, vi } from "vitest";

import {
    CONNECTION_STATUS,
    EVENT_TYPE,
    QUEUE_STATUS,
    getState,
    setSnapshot,
    applyEvent,
    setConnectionStatus,
    subscribe,
    reset,
} from "../js/display-state.js";


/*
|--------------------------------------------------------------------------
| Test Fixtures
|--------------------------------------------------------------------------
*/

const DEPARTMENT_A = "11111111-1111-1111-1111-111111111111";
const DEPARTMENT_B = "22222222-2222-2222-2222-222222222222";

const TOKEN_A = "A-001";
const TOKEN_B = "A-002";

function createSnapshot(overrides = {}) {
    return {
        facility_name: "HPQMS Hospital",
        server_timestamp: "2026-07-31T10:00:00Z",

        departments: [
            {
                dept_id: DEPARTMENT_A,
                department_name: "Reception",

                active_tokens: [],

                next_tokens: [
                    {
                        token_number: TOKEN_A,
                    },
                ],

                recent_tokens: [],

                waiting_count: 1,

                estimated_wait_minutes: 5,
            },

            {
                dept_id: DEPARTMENT_B,
                department_name: "Triage",

                active_tokens: [],

                next_tokens: [],

                recent_tokens: [],

                waiting_count: 0,

                estimated_wait_minutes: null,
            },
        ],

        announcements: [],

        ...overrides,
    };
}


function createEvent(overrides = {}) {
    return {
        event_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",

        event_type: EVENT_TYPE.TOKEN_CALLED,

        priority: "HIGH",

        occurred_at: "2026-07-31T10:01:00Z",

        token_number: TOKEN_A,

        visit_id: null,

        queue_entry_id: null,

        dept_id: DEPARTMENT_A,

        department_name: "Reception",

        service_point: "Counter 1",

        source_dept_id: null,
        source_department_name: null,

        target_dept_id: null,
        target_department_name: null,

        announcement_id: null,
        announcement_priority: null,

        starts_at: null,
        expires_at: null,

        message: null,

        targets: ["PUBLIC_DISPLAY"],

        ...overrides,
    };
}


/*
|--------------------------------------------------------------------------
| Setup
|--------------------------------------------------------------------------
*/

beforeEach(() => {
    reset();
});


/*
|--------------------------------------------------------------------------
| Initial State
|--------------------------------------------------------------------------
*/

describe("initial state", () => {
    it("starts with an empty display snapshot", () => {
        const state = getState();

        expect(state.snapshot.facility_name).toBeNull();
        expect(state.snapshot.server_timestamp).toBeNull();
        expect(state.snapshot.departments).toEqual([]);
        expect(state.snapshot.announcements).toEqual([]);
    });


    it("starts disconnected", () => {
        const state = getState();

        expect(state.connection.status).toBe(
            CONNECTION_STATUS.DISCONNECTED
        );
    });


    it("starts uninitialized and fresh", () => {
        const state = getState();

        expect(state.metadata.initialized).toBe(false);
        expect(state.metadata.stale).toBe(false);
        expect(state.metadata.last_snapshot_at).toBeNull();
        expect(state.metadata.last_event_at).toBeNull();
    });
});


/*
|--------------------------------------------------------------------------
| Snapshot Management
|--------------------------------------------------------------------------
*/

describe("setSnapshot()", () => {
    it("replaces the current snapshot", () => {
        const snapshot = createSnapshot();

        setSnapshot(snapshot);

        const state = getState();

        expect(state.snapshot).toEqual(snapshot);
    });


    it("marks the state as initialized", () => {
        setSnapshot(createSnapshot());

        const state = getState();

        expect(state.metadata.initialized).toBe(true);
    });


    it("marks the state as fresh", () => {
        setSnapshot(createSnapshot());

        const state = getState();

        expect(state.metadata.stale).toBe(false);
    });


    it("records when the snapshot was received", () => {
        setSnapshot(createSnapshot());

        const state = getState();

        expect(state.metadata.last_snapshot_at).not.toBeNull();
    });


    it("replaces old snapshot data rather than merging it", () => {
        setSnapshot(
            createSnapshot({
                facility_name: "Old Facility",
            })
        );

        setSnapshot(
            createSnapshot({
                facility_name: "New Facility",
                departments: [],
            })
        );

        const state = getState();

        expect(state.snapshot.facility_name).toBe(
            "New Facility"
        );

        expect(state.snapshot.departments).toEqual([]);
    });


    it("rejects an invalid snapshot", () => {
        expect(() => setSnapshot(null)).toThrow();
        expect(() => setSnapshot(undefined)).toThrow();
        expect(() => setSnapshot("invalid")).toThrow();
    });
});


/*
|--------------------------------------------------------------------------
| State Isolation
|--------------------------------------------------------------------------
*/

describe("getState()", () => {
    it("returns a copy rather than the internal state object", () => {
        const snapshot = createSnapshot();

        setSnapshot(snapshot);

        const stateA = getState();
        const stateB = getState();

        expect(stateA).not.toBe(stateB);
        expect(stateA.snapshot).not.toBe(stateB.snapshot);
    });


    it("prevents external mutation of internal state", () => {
        setSnapshot(createSnapshot());

        const state = getState();

        state.snapshot.facility_name = "HACKED";
        state.snapshot.departments.push({
            dept_id: "malicious",
        });

        const actualState = getState();

        expect(actualState.snapshot.facility_name)
            .toBe("HPQMS Hospital");

        expect(actualState.snapshot.departments)
            .toHaveLength(2);
    });
});


/*
|--------------------------------------------------------------------------
| Subscriptions
|--------------------------------------------------------------------------
*/

describe("subscribe()", () => {
    it("notifies subscribers when the snapshot changes", () => {
        const listener = vi.fn();

        subscribe(listener);

        setSnapshot(createSnapshot());

        expect(listener).toHaveBeenCalledTimes(1);
        expect(listener).toHaveBeenCalledWith(
            expect.any(Object),
            "SNAPSHOT_REPLACED"
        );
    });


    it("notifies subscribers when an event changes state", () => {
        const listener = vi.fn();

        subscribe(listener);

        setSnapshot(createSnapshot());

        listener.mockClear();

        applyEvent(
            createEvent({
                event_type: EVENT_TYPE.TOKEN_CALLED,
            })
        );

        expect(listener).toHaveBeenCalledTimes(1);
    });


    it("allows a subscriber to unsubscribe", () => {
        const listener = vi.fn();

        const unsubscribe = subscribe(listener);

        unsubscribe();

        setSnapshot(createSnapshot());

        expect(listener).not.toHaveBeenCalled();
    });


    it("isolates subscriber errors", () => {
        const brokenListener = vi.fn(() => {
            throw new Error("Subscriber failure");
        });

        const healthyListener = vi.fn();

        subscribe(brokenListener);
        subscribe(healthyListener);

        expect(() => {
            setSnapshot(createSnapshot());
        }).not.toThrow();

        expect(healthyListener).toHaveBeenCalled();
    });
});


/*
|--------------------------------------------------------------------------
| Connection State
|--------------------------------------------------------------------------
*/

describe("setConnectionStatus()", () => {
    it("changes the connection status", () => {
        setConnectionStatus(
            CONNECTION_STATUS.CONNECTING
        );

        expect(getState().connection.status)
            .toBe(CONNECTION_STATUS.CONNECTING);
    });


    it("records connection time", () => {
        setConnectionStatus(
            CONNECTION_STATUS.CONNECTED
        );

        expect(getState().connection.connected_at)
            .not.toBeNull();
    });


    it("clears the previous connection error when connected", () => {
        setConnectionStatus(
            CONNECTION_STATUS.ERROR,
            {
                last_error: "Connection failed",
            }
        );

        setConnectionStatus(
            CONNECTION_STATUS.CONNECTED
        );

        expect(getState().connection.last_error)
            .toBeNull();
    });


    it("records disconnect time", () => {
        setConnectionStatus(
            CONNECTION_STATUS.DISCONNECTED
        );

        expect(getState().connection.disconnected_at)
            .not.toBeNull();
    });


    it("rejects invalid connection status", () => {
        expect(() => {
            setConnectionStatus("INVALID_STATUS");
        }).toThrow();
    });
});


/*
|--------------------------------------------------------------------------
| TOKEN_CALLED
|--------------------------------------------------------------------------
*/

describe("TOKEN_CALLED", () => {
    beforeEach(() => {
        setSnapshot(createSnapshot());
    });


    it("adds a newly called token to active_tokens", () => {
        applyEvent(
            createEvent({
                token_number: TOKEN_A,
                event_type: EVENT_TYPE.TOKEN_CALLED,
            })
        );

        const department =
            getState().snapshot.departments[0];

        expect(department.active_tokens).toHaveLength(1);

        expect(department.active_tokens[0]).toMatchObject({
            token_number: TOKEN_A,
            status: QUEUE_STATUS.CALLED,
            service_point: "Counter 1",
        });
    });


    it("does not create duplicate active tokens", () => {
        const event = createEvent({
            event_type: EVENT_TYPE.TOKEN_CALLED,
        });

        applyEvent(event);
        applyEvent(event);

        const department =
            getState().snapshot.departments[0];

        expect(
            department.active_tokens.filter(
                token => token.token_number === TOKEN_A
            )
        ).toHaveLength(1);
    });


    it("updates an existing active token", () => {
        applyEvent(
            createEvent({
                event_type: EVENT_TYPE.TOKEN_CALLED,
                service_point: "Counter 1",
            })
        );

        applyEvent(
            createEvent({
                event_type: EVENT_TYPE.TOKEN_CALLED,
                service_point: "Counter 3",
            })
        );

        const token =
            getState()
                .snapshot
                .departments[0]
                .active_tokens[0];

        expect(token.service_point)
            .toBe("Counter 3");
    });


    it("updates last_event_at", () => {
        applyEvent(
            createEvent({
                event_type: EVENT_TYPE.TOKEN_CALLED,
            })
        );

        expect(getState().metadata.last_event_at)
            .toBe("2026-07-31T10:01:00Z");
    });
});


/*
|--------------------------------------------------------------------------
| TOKEN_SERVICE_STARTED
|--------------------------------------------------------------------------
*/

describe("TOKEN_SERVICE_STARTED", () => {
    beforeEach(() => {
        setSnapshot(createSnapshot());

        applyEvent(
            createEvent({
                event_type: EVENT_TYPE.TOKEN_CALLED,
            })
        );
    });


    it("changes CALLED to IN_PROGRESS", () => {
        applyEvent(
            createEvent({
                event_type:
                    EVENT_TYPE.TOKEN_SERVICE_STARTED,
                service_point: "Consultation Room 1",
            })
        );

        const token =
            getState()
                .snapshot
                .departments[0]
                .active_tokens[0];

        expect(token.status)
            .toBe(QUEUE_STATUS.IN_PROGRESS);

        expect(token.service_point)
            .toBe("Consultation Room 1");
    });


    it("creates an active token if TOKEN_CALLED was missed", () => {
        reset();

        setSnapshot(createSnapshot());

        applyEvent(
            createEvent({
                event_type:
                    EVENT_TYPE.TOKEN_SERVICE_STARTED,
                token_number: TOKEN_B,
            })
        );

        const token =
            getState()
                .snapshot
                .departments[0]
                .active_tokens[0];

        expect(token.token_number)
            .toBe(TOKEN_B);

        expect(token.status)
            .toBe(QUEUE_STATUS.IN_PROGRESS);
    });
});


/*
|--------------------------------------------------------------------------
| TOKEN_COMPLETED
|--------------------------------------------------------------------------
*/

describe("TOKEN_COMPLETED", () => {
    beforeEach(() => {
        setSnapshot(createSnapshot());

        applyEvent(
            createEvent({
                event_type: EVENT_TYPE.TOKEN_CALLED,
            })
        );
    });


    it("removes the token from active_tokens", () => {
        applyEvent(
            createEvent({
                event_type: EVENT_TYPE.TOKEN_COMPLETED,
            })
        );

        const department =
            getState().snapshot.departments[0];

        expect(department.active_tokens)
            .toHaveLength(0);
    });


    it("moves the token into recent_tokens", () => {
        applyEvent(
            createEvent({
                event_type: EVENT_TYPE.TOKEN_COMPLETED,
            })
        );

        const department =
            getState().snapshot.departments[0];

        expect(department.recent_tokens)
            .toContainEqual({
                token_number: TOKEN_A,
            });
    });


    it("does not duplicate recent tokens", () => {
        const event = createEvent({
            event_type: EVENT_TYPE.TOKEN_COMPLETED,
        });

        applyEvent(event);
        applyEvent(event);

        const department =
            getState().snapshot.departments[0];

        expect(
            department.recent_tokens.filter(
                token => token.token_number === TOKEN_A
            )
        ).toHaveLength(1);
    });
});


/*
|--------------------------------------------------------------------------
| TOKEN_NO_SHOW
|--------------------------------------------------------------------------
*/

describe("TOKEN_NO_SHOW", () => {
    it("removes a no-show token from active_tokens", () => {
        setSnapshot(createSnapshot());

        applyEvent(
            createEvent({
                event_type: EVENT_TYPE.TOKEN_CALLED,
            })
        );

        applyEvent(
            createEvent({
                event_type: EVENT_TYPE.TOKEN_NO_SHOW,
            })
        );

        const department =
            getState().snapshot.departments[0];

        expect(department.active_tokens)
            .toHaveLength(0);
    });
});


/*
|--------------------------------------------------------------------------
| PATIENT_ROUTED
|--------------------------------------------------------------------------
*/

describe("PATIENT_ROUTED", () => {
    it("moves the token from source to target department", () => {
        setSnapshot(createSnapshot());

        applyEvent(
            createEvent({
                event_type: EVENT_TYPE.TOKEN_CALLED,
                dept_id: DEPARTMENT_A,
            })
        );

        applyEvent(
            createEvent({
                event_type: EVENT_TYPE.PATIENT_ROUTED,

                token_number: TOKEN_A,

                source_dept_id: DEPARTMENT_A,
                source_department_name: "Reception",

                target_dept_id: DEPARTMENT_B,
                target_department_name: "Triage",
            })
        );

        const state = getState();

        const source =
            state.snapshot.departments[0];

        const target =
            state.snapshot.departments[1];

        expect(source.active_tokens)
            .toHaveLength(0);

        expect(target.next_tokens)
            .toContainEqual({
                token_number: TOKEN_A,
            });
    });


    it("does not duplicate the routed token", () => {
        setSnapshot(createSnapshot());

        applyEvent(
            createEvent({
                event_type: EVENT_TYPE.TOKEN_CALLED,
            })
        );

        const event = createEvent({
            event_type: EVENT_TYPE.PATIENT_ROUTED,

            source_dept_id: DEPARTMENT_A,
            target_dept_id: DEPARTMENT_B,
        });

        applyEvent(event);

        /*
         * Second application should not create another
         * next-token entry.
         */
        applyEvent(event);

        const target =
            getState().snapshot.departments[1];

        expect(
            target.next_tokens.filter(
                token => token.token_number === TOKEN_A
            )
        ).toHaveLength(1);
    });


    it("marks state stale when routing context is incomplete", () => {
        setSnapshot(createSnapshot());

        applyEvent(
            createEvent({
                event_type: EVENT_TYPE.PATIENT_ROUTED,

                source_dept_id: null,
                target_dept_id: null,
            })
        );

        expect(getState().metadata.stale)
            .toBe(true);
    });
});


/*
|--------------------------------------------------------------------------
| QUEUE_UPDATED
|--------------------------------------------------------------------------
*/

describe("QUEUE_UPDATED", () => {
    it("marks the snapshot stale", () => {
        setSnapshot(createSnapshot());

        expect(getState().metadata.stale)
            .toBe(false);

        applyEvent(
            createEvent({
                event_type: EVENT_TYPE.QUEUE_UPDATED,
            })
        );

        expect(getState().metadata.stale)
            .toBe(true);
    });


    it("does not attempt to mutate queue state", () => {
        setSnapshot(createSnapshot());

        const before =
            getState().snapshot.departments;

        applyEvent(
            createEvent({
                event_type: EVENT_TYPE.QUEUE_UPDATED,
            })
        );

        const after =
            getState().snapshot.departments;

        expect(after).toEqual(before);
    });


    it("clears stale state after a fresh snapshot", () => {
        setSnapshot(createSnapshot());

        applyEvent(
            createEvent({
                event_type: EVENT_TYPE.QUEUE_UPDATED,
            })
        );

        expect(getState().metadata.stale)
            .toBe(true);

        setSnapshot(createSnapshot());

        expect(getState().metadata.stale)
            .toBe(false);
    });
});


/*
|--------------------------------------------------------------------------
| ANNOUNCEMENT_CREATED
|--------------------------------------------------------------------------
*/

describe("ANNOUNCEMENT_CREATED", () => {
    it("adds an announcement", () => {
        setSnapshot(createSnapshot());

        applyEvent(
            createEvent({
                event_type:
                    EVENT_TYPE.ANNOUNCEMENT_CREATED,

                announcement_id:
                    "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",

                announcement_priority: "WARNING",

                message: "Clinic closes at 5 PM.",

                starts_at:
                    "2026-07-31T10:00:00Z",

                expires_at:
                    "2026-07-31T17:00:00Z",
            })
        );

        const announcements =
            getState().snapshot.announcements;

        expect(announcements).toHaveLength(1);

        expect(announcements[0]).toMatchObject({
            announcement_id:
                "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",

            priority: "WARNING",

            message: "Clinic closes at 5 PM.",
        });
    });


    it("does not duplicate announcements", () => {
        setSnapshot(createSnapshot());

        const event = createEvent({
            event_type:
                EVENT_TYPE.ANNOUNCEMENT_CREATED,

            announcement_id:
                "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",

            announcement_priority: "INFO",

            message: "Welcome to HPQMS.",
        });

        applyEvent(event);
        applyEvent(event);

        expect(
            getState().snapshot.announcements
        ).toHaveLength(1);
    });
});


/*
|--------------------------------------------------------------------------
| ANNOUNCEMENT_EXPIRED
|--------------------------------------------------------------------------
*/

describe("ANNOUNCEMENT_EXPIRED", () => {
    it("removes the matching announcement", () => {
        setSnapshot(
            createSnapshot({
                announcements: [
                    {
                        announcement_id:
                            "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",

                        priority: "WARNING",

                        message: "Clinic closes at 5 PM.",

                        starts_at: null,
                        expires_at: null,
                    },
                ],
            })
        );

        applyEvent(
            createEvent({
                event_type:
                    EVENT_TYPE.ANNOUNCEMENT_EXPIRED,

                announcement_id:
                    "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            })
        );

        expect(
            getState().snapshot.announcements
        ).toHaveLength(0);
    });


    it("does not remove unrelated announcements", () => {
        setSnapshot(
            createSnapshot({
                announcements: [
                    {
                        announcement_id:
                            "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",

                        priority: "INFO",

                        message: "Announcement A.",

                        starts_at: null,
                        expires_at: null,
                    },

                    {
                        announcement_id:
                            "cccccccc-cccc-cccc-cccc-cccccccccccc",

                        priority: "WARNING",

                        message: "Announcement B.",

                        starts_at: null,
                        expires_at: null,
                    },
                ],
            })
        );

        applyEvent(
            createEvent({
                event_type:
                    EVENT_TYPE.ANNOUNCEMENT_EXPIRED,

                announcement_id:
                    "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
            })
        );

        const announcements =
            getState().snapshot.announcements;

        expect(announcements).toHaveLength(1);

        expect(
            announcements[0].announcement_id
        ).toBe(
            "cccccccc-cccc-cccc-cccc-cccccccccccc"
        );
    });
});


/*
|--------------------------------------------------------------------------
| Missing / Unknown Events
|--------------------------------------------------------------------------
*/

describe("defensive behavior", () => {
    it("does not crash when an event references a missing department", () => {
        setSnapshot(createSnapshot());

        expect(() => {
            applyEvent(
                createEvent({
                    dept_id:
                        "99999999-9999-9999-9999-999999999999",
                })
            );
        }).not.toThrow();
    });


    it("does not crash on an unknown event type", () => {
        setSnapshot(createSnapshot());

        expect(() => {
            applyEvent({
                event_type: "SOMETHING_UNKNOWN",
            });
        }).not.toThrow();
    });


    it("rejects invalid event input", () => {
        expect(() => applyEvent(null)).toThrow();

        expect(() => applyEvent(undefined)).toThrow();

        expect(() => applyEvent("invalid")).toThrow();
    });


    it("rejects events without event_type", () => {
        expect(() => {
            applyEvent({
                token_number: TOKEN_A,
            });
        }).toThrow();
    });
});


/*
|--------------------------------------------------------------------------
| Reset
|--------------------------------------------------------------------------
*/

describe("reset()", () => {
    it("restores the initial state", () => {
        setSnapshot(createSnapshot());

        setConnectionStatus(
            CONNECTION_STATUS.CONNECTED
        );

        reset();

        const state = getState();

        expect(state.snapshot.departments)
            .toEqual([]);

        expect(state.snapshot.announcements)
            .toEqual([]);

        expect(state.connection.status)
            .toBe(CONNECTION_STATUS.DISCONNECTED);

        expect(state.metadata.initialized)
            .toBe(false);

        expect(state.metadata.stale)
            .toBe(false);
    });


    it("notifies subscribers", () => {
        const listener = vi.fn();

        subscribe(listener);

        reset();

        expect(listener).toHaveBeenCalledWith(
            expect.any(Object),
            "STATE_RESET"
        );
    });
});