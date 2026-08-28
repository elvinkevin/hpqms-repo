
import {
    beforeEach,
    afterEach,
    describe,
    expect,
    it,
    vi,
} from "vitest";

import {
    ALERT_PRIORITY,
    ALERT_EVENT_TYPES,

    initialize,
    setCallbacks,

    handleEvent,

    getState,
    getActiveAlert,
    getQueuedAlerts,

    dismiss,
    clearQueue,
    reset,
} from "../js/alert-manager.js";


/* ==========================================================================
   Fixtures
   ========================================================================== */

const tokenCalledEvent = {
    event_id:
        "00000000-0000-0000-0000-000000000001",

    event_type: "TOKEN_CALLED",

    priority: "HIGH",

    occurred_at:
        "2026-07-31T10:00:00Z",

    token_number: "A-001",

    visit_id:
        "00000000-0000-0000-0000-000000000002",

    queue_entry_id:
        "00000000-0000-0000-0000-000000000003",

    dept_id:
        "00000000-0000-0000-0000-000000000004",

    department_name: "Outpatient",

    service_point: "Room 1",

    message: "Token A-001 called",

    targets: [
        "PUBLIC_DISPLAY",
    ],
};


const normalTokenEvent = {
    ...tokenCalledEvent,

    event_id:
        "00000000-0000-0000-0000-000000000010",

    priority: "NORMAL",

    token_number: "A-002",

    message: "Token A-002 called",
};


const criticalTokenEvent = {
    ...tokenCalledEvent,

    event_id:
        "00000000-0000-0000-0000-000000000020",

    priority: "CRITICAL",

    token_number: "E-001",

    message: "Emergency token E-001 called",
};


const announcementEvent = {
    ...tokenCalledEvent,

    event_id:
        "00000000-0000-0000-0000-000000000030",

    event_type: "ANNOUNCEMENT_CREATED",

    priority: "NORMAL",

    token_number: null,

    message: "Hospital announcement",
};


const completedEvent = {
    ...tokenCalledEvent,

    event_id:
        "00000000-0000-0000-0000-000000000040",

    event_type: "TOKEN_COMPLETED",
};


/* ==========================================================================
   Callback Fixtures
   ========================================================================== */

let showAlert;
let dismissAlert;
let playSound;


beforeEach(() => {
    vi.useFakeTimers();

    showAlert = vi.fn();
    dismissAlert = vi.fn();
    playSound = vi.fn();

    reset();

    initialize();

    setCallbacks({
        show: showAlert,
        dismiss: dismissAlert,
        playSound,
    });
});


afterEach(() => {
    reset();

    vi.useRealTimers();

    vi.restoreAllMocks();
});


/* ==========================================================================
   Constants
   ========================================================================== */

describe("constants", () => {
    it("defines the expected alert priorities", () => {
        expect(ALERT_PRIORITY)
            .toEqual({
                LOW: 1,
                NORMAL: 2,
                HIGH: 3,
                CRITICAL: 4,
            });
    });


    it("defines supported alert event types", () => {
        expect(ALERT_EVENT_TYPES)
            .toContain("TOKEN_CALLED");

        expect(ALERT_EVENT_TYPES)
            .toContain(
                "ANNOUNCEMENT_CREATED"
            );
    });
});


/* ==========================================================================
   initialize()
   ========================================================================== */

describe("initialize()", () => {
    it("initializes successfully", () => {
        reset();

        const state = initialize();

        expect(state.initialized)
            .toBe(true);
    });


    it("accepts custom options", () => {
        reset();

        initialize({
            defaultDurationMs: 8000,
            maxQueueSize: 10,
            deduplicationWindowMs: 5000,
        });

        expect(
            getState().initialized
        ).toBe(true);
    });


    it("rejects null options", () => {
        reset();

        expect(() => {
            initialize(null);
        }).toThrow(TypeError);
    });


    it("rejects non-object options", () => {
        reset();

        expect(() => {
            initialize("invalid");
        }).toThrow(TypeError);
    });


    it("rejects non-positive alert duration", () => {
        reset();

        expect(() => {
            initialize({
                defaultDurationMs: 0,
            });
        }).toThrow(RangeError);
    });


    it("rejects a negative queue size", () => {
        reset();

        expect(() => {
            initialize({
                maxQueueSize: -1,
            });
        }).toThrow(RangeError);
    });


    it("rejects a zero queue size", () => {
        reset();

        expect(() => {
            initialize({
                maxQueueSize: 0,
            });
        }).toThrow(RangeError);
    });


    it("rejects a fractional queue size", () => {
        reset();

        expect(() => {
            initialize({
                maxQueueSize: 1.5,
            });
        }).toThrow(RangeError);
    });


    it("rejects a negative deduplication window", () => {
        reset();

        expect(() => {
            initialize({
                deduplicationWindowMs: -1,
            });
        }).toThrow(RangeError);
    });
});


/* ==========================================================================
   setCallbacks()
   ========================================================================== */

describe("setCallbacks()", () => {
    it("accepts valid callbacks", () => {
        expect(() => {
            setCallbacks({
                show: vi.fn(),
                dismiss: vi.fn(),
                playSound: vi.fn(),
            });
        }).not.toThrow();
    });


    it("allows callbacks to be omitted", () => {
        expect(() => {
            setCallbacks();
        }).not.toThrow();
    });


    it("rejects an invalid show callback", () => {
        expect(() => {
            setCallbacks({
                show: "invalid",
            });
        }).toThrow(TypeError);
    });


    it("rejects an invalid dismiss callback", () => {
        expect(() => {
            setCallbacks({
                dismiss: "invalid",
            });
        }).toThrow(TypeError);
    });


    it("rejects an invalid sound callback", () => {
        expect(() => {
            setCallbacks({
                playSound: "invalid",
            });
        }).toThrow(TypeError);
    });
});


/* ==========================================================================
   Initial State
   ========================================================================== */

describe("initial state", () => {
    it("starts without an active alert", () => {
        expect(getActiveAlert())
            .toBeNull();
    });


    it("starts with an empty queue", () => {
        expect(getQueuedAlerts())
            .toEqual([]);
    });


    it("reports an empty queue size", () => {
        expect(
            getState().queueSize
        ).toBe(0);
    });
});


/* ==========================================================================
   handleEvent()
   ========================================================================== */

describe("handleEvent()", () => {
    it("accepts a supported alert event", () => {
        const accepted =
            handleEvent(tokenCalledEvent);

        expect(accepted)
            .toBe(true);
    });


    it("shows the first alert immediately", () => {
        handleEvent(tokenCalledEvent);

        expect(showAlert)
            .toHaveBeenCalledTimes(1);

        expect(showAlert)
            .toHaveBeenCalledWith(
                expect.objectContaining({
                    alert_id:
                        tokenCalledEvent.event_id,

                    event_type:
                        "TOKEN_CALLED",

                    priority:
                        "HIGH",

                    token_number:
                        "A-001",
                })
            );
    });


    it("plays the alert sound", () => {
        handleEvent(tokenCalledEvent);

        expect(playSound)
            .toHaveBeenCalledTimes(1);

        expect(playSound)
            .toHaveBeenCalledWith(
                expect.objectContaining({
                    token_number: "A-001",
                })
            );
    });


    it("stores the active alert", () => {
        handleEvent(tokenCalledEvent);

        expect(
            getActiveAlert()
        ).toEqual(
            expect.objectContaining({
                alert_id:
                    tokenCalledEvent.event_id,

                token_number: "A-001",

                priority: "HIGH",
            })
        );
    });


    it("ignores unsupported event types", () => {
        const accepted =
            handleEvent(completedEvent);

        expect(accepted)
            .toBe(false);

        expect(showAlert)
            .not.toHaveBeenCalled();

        expect(playSound)
            .not.toHaveBeenCalled();
    });


    it("rejects null events", () => {
        expect(
            handleEvent(null)
        ).toBe(false);
    });


    it("rejects primitive events", () => {
        expect(
            handleEvent("TOKEN_CALLED")
        ).toBe(false);
    });


    it("rejects events before initialization", () => {
        reset();

        expect(
            handleEvent(tokenCalledEvent)
        ).toBe(false);

        expect(showAlert)
            .not.toHaveBeenCalled();
    });
});


/* ==========================================================================
   Priority Handling
   ========================================================================== */

describe("priority handling", () => {
    it("maps LOW to the lowest priority value", () => {
        handleEvent({
            ...tokenCalledEvent,
            event_id: "low-event",
            priority: "LOW",
        });

        expect(
            getActiveAlert().priority_value
        ).toBe(1);
    });


    it("maps NORMAL correctly", () => {
        handleEvent(normalTokenEvent);

        expect(
            getActiveAlert().priority_value
        ).toBe(2);
    });


    it("maps HIGH correctly", () => {
        handleEvent(tokenCalledEvent);

        expect(
            getActiveAlert().priority_value
        ).toBe(3);
    });


    it("maps CRITICAL correctly", () => {
        handleEvent(criticalTokenEvent);

        expect(
            getActiveAlert().priority_value
        ).toBe(4);
    });


    it("promotes a higher-priority alert immediately", () => {
        handleEvent(normalTokenEvent);

        handleEvent(criticalTokenEvent);

        expect(showAlert)
            .toHaveBeenCalledTimes(2);

        expect(
            getActiveAlert().token_number
        ).toBe("E-001");
    });


    it("dismisses the previous alert during promotion", () => {
        handleEvent(normalTokenEvent);

        handleEvent(criticalTokenEvent);

        expect(dismissAlert)
            .toHaveBeenCalledTimes(1);

        expect(dismissAlert)
            .toHaveBeenCalledWith(
                expect.objectContaining({
                    token_number: "A-002",
                })
            );
    });


    it("does not promote an equal-priority alert", () => {
        handleEvent(tokenCalledEvent);

        handleEvent({
            ...tokenCalledEvent,
            event_id: "second-high-event",
            token_number: "A-003",
        });

        expect(showAlert)
            .toHaveBeenCalledTimes(1);

        expect(
            getActiveAlert().token_number
        ).toBe("A-001");
    });


    it("does not promote a lower-priority alert", () => {
        handleEvent(criticalTokenEvent);

        handleEvent(normalTokenEvent);

        expect(showAlert)
            .toHaveBeenCalledTimes(1);

        expect(
            getActiveAlert().token_number
        ).toBe("E-001");
    });
});


/* ==========================================================================
   Queueing
   ========================================================================== */

describe("alert queue", () => {
    it("queues alerts while another alert is active", () => {
        handleEvent(tokenCalledEvent);

        handleEvent(normalTokenEvent);

        expect(
            getQueuedAlerts()
        ).toHaveLength(1);
    });


    it("does not queue the active alert", () => {
        handleEvent(tokenCalledEvent);

        expect(
            getQueuedAlerts()
        ).toHaveLength(0);
    });


    it("orders queued alerts by priority", () => {
    // Keep a CRITICAL alert active so all subsequent
    // alerts are placed into the queue.
    handleEvent(criticalTokenEvent);

    handleEvent({
        ...normalTokenEvent,
        event_id: "queue-low",
        priority: "LOW",
        token_number: "A-003",
    });

    handleEvent({
        ...normalTokenEvent,
        event_id: "queue-normal",
        priority: "NORMAL",
        token_number: "A-004",
    });

    handleEvent({
        ...normalTokenEvent,
        event_id: "queue-high",
        priority: "HIGH",
        token_number: "A-005",
    });

    const queue = getQueuedAlerts();

    expect(queue).toHaveLength(3);

    expect(queue[0].priority)
        .toBe("HIGH");

    expect(queue[1].priority)
        .toBe("NORMAL");

    expect(queue[2].priority)
        .toBe("LOW");
    });


    it("preserves FIFO order for equal priorities", () => {
        handleEvent(tokenCalledEvent);

        handleEvent({
            ...normalTokenEvent,
            event_id: "normal-1",
            token_number: "A-002",
        });

        handleEvent({
            ...normalTokenEvent,
            event_id: "normal-2",
            token_number: "A-003",
        });

        const queue =
            getQueuedAlerts();

        expect(queue[0].token_number)
            .toBe("A-002");

        expect(queue[1].token_number)
            .toBe("A-003");
    });


    it("shows the next queued alert after dismissal", () => {
        handleEvent(tokenCalledEvent);

        handleEvent(normalTokenEvent);

        dismiss();

        expect(
            getActiveAlert().token_number
        ).toBe("A-002");
    });


    it("removes the queued alert after promotion", () => {
        handleEvent(tokenCalledEvent);

        handleEvent(normalTokenEvent);

        dismiss();

        expect(
            getQueuedAlerts()
        ).toHaveLength(0);
    });


    it("respects the maximum queue size", () => {
        reset();

        initialize({
            maxQueueSize: 2,
        });

        setCallbacks({
            show: showAlert,
            dismiss: dismissAlert,
            playSound,
        });

        handleEvent(tokenCalledEvent);

        handleEvent({
            ...normalTokenEvent,
            event_id: "queue-1",
            token_number: "A-002",
        });

        handleEvent({
            ...normalTokenEvent,
            event_id: "queue-2",
            token_number: "A-003",
        });

        handleEvent({
            ...normalTokenEvent,
            event_id: "queue-3",
            token_number: "A-004",
        });

        expect(
            getQueuedAlerts()
        ).toHaveLength(2);
    });


    it("returns false when a low-priority alert is rejected from a full queue", () => {
        reset();

        initialize({
            maxQueueSize: 2,
        });

        setCallbacks({
            show: showAlert,
            dismiss: dismissAlert,
            playSound,
        });

        handleEvent(tokenCalledEvent);

        handleEvent({
            ...normalTokenEvent,
            event_id: "queue-1",
            priority: "HIGH",
            token_number: "A-002",
        });

        handleEvent({
            ...normalTokenEvent,
            event_id: "queue-2",
            priority: "HIGH",
            token_number: "A-003",
        });

        const accepted =
            handleEvent({
                ...normalTokenEvent,
                event_id: "queue-low",
                priority: "LOW",
                token_number: "A-004",
            });

        expect(accepted)
            .toBe(false);

        expect(
            getQueuedAlerts()
        ).toHaveLength(2);
    });


    it("replaces the lowest queued alert when a higher-priority alert arrives", () => {
        reset();

        initialize({
            maxQueueSize: 2,
        });

        setCallbacks({
            show: showAlert,
            dismiss: dismissAlert,
            playSound,
        });

        handleEvent(tokenCalledEvent);

        handleEvent({
            ...normalTokenEvent,
            event_id: "queue-low",
            priority: "LOW",
            token_number: "A-002",
        });

        handleEvent({
            ...normalTokenEvent,
            event_id: "queue-normal",
            priority: "NORMAL",
            token_number: "A-003",
        });

        handleEvent({
            ...normalTokenEvent,
            event_id: "queue-critical",
            priority: "HIGH",
            token_number: "A-004",
        });

        const queue =
            getQueuedAlerts();

        expect(queue)
            .toHaveLength(2);

        expect(
            queue.map(
                (alert) =>
                    alert.token_number
            )
        ).toEqual([
            "A-004",
            "A-003",
        ]);
    });
});


/* ==========================================================================
   Deduplication
   ========================================================================== */

describe("deduplication", () => {
    it("rejects the same event twice", () => {
        expect(
            handleEvent(tokenCalledEvent)
        ).toBe(true);

        expect(
            handleEvent(tokenCalledEvent)
        ).toBe(false);
    });


    it("does not show duplicate alerts", () => {
        handleEvent(tokenCalledEvent);

        handleEvent(tokenCalledEvent);

        expect(showAlert)
            .toHaveBeenCalledTimes(1);
    });


    it("does not play duplicate sounds", () => {
        handleEvent(tokenCalledEvent);

        handleEvent(tokenCalledEvent);

        expect(playSound)
            .toHaveBeenCalledTimes(1);
    });


    it("allows the same event after the deduplication window", () => {
        reset();

        initialize({
            deduplicationWindowMs: 3000,
        });

        setCallbacks({
            show: showAlert,
            dismiss: dismissAlert,
            playSound,
        });

        handleEvent(tokenCalledEvent);

        vi.advanceTimersByTime(3001);

        dismiss();

        expect(
            handleEvent(tokenCalledEvent)
        ).toBe(true);
    });
});


/* ==========================================================================
   Alert Duration
   ========================================================================== */

describe("alert duration", () => {
    it("automatically dismisses an expired alert", () => {
        handleEvent(tokenCalledEvent);

        expect(getActiveAlert())
            .not.toBeNull();

        vi.advanceTimersByTime(5000);

        expect(getActiveAlert())
            .toBeNull();
    });


    it("calls the dismiss callback when an alert expires", () => {
        handleEvent(tokenCalledEvent);

        vi.advanceTimersByTime(5000);

        expect(dismissAlert)
            .toHaveBeenCalledTimes(1);
    });


    it("shows the next queued alert after expiration", () => {
        handleEvent(tokenCalledEvent);

        handleEvent(normalTokenEvent);

        vi.advanceTimersByTime(5000);

        expect(
            getActiveAlert().token_number
        ).toBe("A-002");
    });
});


/* ==========================================================================
   dismiss()
   ========================================================================== */

describe("dismiss()", () => {
    it("returns false when no alert is active", () => {
        expect(
            dismiss()
        ).toBe(false);
    });


    it("returns true when an alert is dismissed", () => {
        handleEvent(tokenCalledEvent);

        expect(
            dismiss()
        ).toBe(true);
    });


    it("clears the active alert", () => {
        handleEvent(tokenCalledEvent);

        dismiss();

        expect(getActiveAlert())
            .toBeNull();
    });


    it("calls the dismiss callback", () => {
        handleEvent(tokenCalledEvent);

        dismiss();

        expect(dismissAlert)
            .toHaveBeenCalledTimes(1);
    });
});


/* ==========================================================================
   clearQueue()
   ========================================================================== */

describe("clearQueue()", () => {
    it("clears queued alerts", () => {
        handleEvent(tokenCalledEvent);

        handleEvent(normalTokenEvent);

        const count =
            clearQueue();

        expect(count)
            .toBe(1);

        expect(
            getQueuedAlerts()
        ).toEqual([]);
    });


    it("does not clear the active alert", () => {
        handleEvent(tokenCalledEvent);

        clearQueue();

        expect(getActiveAlert())
            .not.toBeNull();
    });


    it("returns zero when the queue is already empty", () => {
        expect(
            clearQueue()
        ).toBe(0);
    });
});


/* ==========================================================================
   Defensive State Access
   ========================================================================== */

describe("defensive state access", () => {
    it("returns a copy of the active alert", () => {
        handleEvent(tokenCalledEvent);

        const state =
            getState();

        state.activeAlert.token_number =
            "MUTATED";

        expect(
            getActiveAlert().token_number
        ).toBe("A-001");
    });


    it("returns a copy of the queued alerts", () => {
        handleEvent(tokenCalledEvent);

        handleEvent(normalTokenEvent);

        const queue =
            getQueuedAlerts();

        queue[0].token_number =
            "MUTATED";

        expect(
            getQueuedAlerts()[0].token_number
        ).toBe("A-002");
    });


    it("does not expose the original event object", () => {
        handleEvent(tokenCalledEvent);

        const state =
            getState();

        state.activeAlert.event.token_number =
            "MUTATED";

        expect(
            getActiveAlert()
                .event
                .token_number
        ).toBe("A-001");
    });
});


/* ==========================================================================
   reset()
   ========================================================================== */

describe("reset()", () => {
    it("clears the active alert", () => {
        handleEvent(tokenCalledEvent);

        reset();

        expect(getActiveAlert())
            .toBeNull();
    });


    it("clears the queue", () => {
        handleEvent(tokenCalledEvent);

        handleEvent(normalTokenEvent);

        reset();

        expect(
            getQueuedAlerts()
        ).toEqual([]);
    });


    it("marks the manager uninitialized", () => {
        reset();

        expect(
            getState().initialized
        ).toBe(false);
    });


    it("clears pending timers", () => {
        handleEvent(tokenCalledEvent);

        reset();

        vi.advanceTimersByTime(10000);

        expect(dismissAlert)
            .not.toHaveBeenCalled();
    });


    it("allows initialization after reset", () => {
        reset();

        initialize();

        expect(
            getState().initialized
        ).toBe(true);
    });
});

