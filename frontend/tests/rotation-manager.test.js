
import {
    beforeEach,
    afterEach,
    describe,
    expect,
    it,
    vi,
} from "vitest";

import {
    DEFAULT_OPTIONS,

    initialize,

    setDepartments,
    getDepartments,

    getCurrentDepartment,
    selectDepartment,
    nextDepartment,
    previousDepartment,

    startRotation,
    stopRotation,
    isRotationActive,

    focusDepartment,
    clearPriorityFocus,
    isPriorityFocusActive,

    getState,

    reset,
} from "../js/rotation-manager.js";


/* ==========================================================================
   Fixtures
   ========================================================================== */

const departments = [
    {
        dept_id: "dept-1",
        department_name: "Reception",
        active_tokens: [
            {
                token_number: "A-001",
                status: "CALLED",
            },
        ],
        next_tokens: [
            {
                token_number: "A-002",
            },
        ],
        recent_tokens: [],
        waiting_count: 1,
        estimated_wait_minutes: 5,
    },

    {
        dept_id: "dept-2",
        department_name: "Triage",
        active_tokens: [],
        next_tokens: [
            {
                token_number: "A-003",
            },
        ],
        recent_tokens: [],
        waiting_count: 1,
        estimated_wait_minutes: 10,
    },

    {
        dept_id: "dept-3",
        department_name: "Consultation",
        active_tokens: [],
        next_tokens: [],
        recent_tokens: [
            {
                token_number: "A-004",
            },
        ],
        waiting_count: 0,
        estimated_wait_minutes: 0,
    },
];


const singleDepartment = [
    departments[0],
];


const emptyDepartments = [];


/* ==========================================================================
   Setup
   ========================================================================== */

beforeEach(() => {
    vi.useFakeTimers();

    reset();

    initialize();
});


afterEach(() => {
    reset();

    vi.useRealTimers();

    vi.restoreAllMocks();
});


/* ==========================================================================
   Initialization
   ========================================================================== */

describe("initialize()", () => {
    it("initializes successfully with defaults", () => {
        const state =
            getState();

        expect(state.initialized)
            .toBe(true);
    });


    it("accepts custom rotation options", () => {
        reset();

        const state =
            initialize({
                rotationIntervalMs: 5000,
                priorityFocusDurationMs: 3000,
            });

        expect(state.initialized)
            .toBe(true);
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


    it("rejects a non-positive rotation interval", () => {
        reset();

        expect(() => {
            initialize({
                rotationIntervalMs: 0,
            });
        }).toThrow(RangeError);
    });


    it("rejects a negative rotation interval", () => {
        reset();

        expect(() => {
            initialize({
                rotationIntervalMs: -1000,
            });
        }).toThrow(RangeError);
    });


    it("rejects a non-positive priority focus duration", () => {
        reset();

        expect(() => {
            initialize({
                priorityFocusDurationMs: 0,
            });
        }).toThrow(RangeError);
    });


    it("uses the documented defaults", () => {
        expect(DEFAULT_OPTIONS)
            .toEqual({
                rotationIntervalMs: 15000,
                priorityFocusDurationMs: 10000,
                onDepartmentChange: null,
            });
    });
});


/* ==========================================================================
   Initial State
   ========================================================================== */

describe("initial state", () => {
    it("starts without departments", () => {
        expect(
            getDepartments()
        ).toEqual([]);
    });


    it("starts without a current department", () => {
        expect(
            getCurrentDepartment()
        ).toBeNull();
    });


    it("starts with currentIndex at -1", () => {
        expect(
            getState().currentIndex
        ).toBe(-1);
    });


    it("starts with rotation inactive", () => {
        expect(
            isRotationActive()
        ).toBe(false);
    });


    it("starts without priority focus", () => {
        expect(
            isPriorityFocusActive()
        ).toBe(false);
    });
});


/* ==========================================================================
   setDepartments()
   ========================================================================== */

describe("setDepartments()", () => {
    it("sets the department collection", () => {
        expect(
            setDepartments(departments)
        ).toBe(true);

        expect(
            getDepartments()
        ).toHaveLength(3);
    });


    it("selects the first department initially", () => {
        setDepartments(departments);

        expect(
            getCurrentDepartment().dept_id
        ).toBe("dept-1");
    });


    it("sets currentIndex to zero initially", () => {
        setDepartments(departments);

        expect(
            getState().currentIndex
        ).toBe(0);
    });


    it("handles an empty department list", () => {
        setDepartments(emptyDepartments);

        expect(
            getDepartments()
        ).toEqual([]);

        expect(
            getCurrentDepartment()
        ).toBeNull();

        expect(
            getState().currentIndex
        ).toBe(-1);
    });


    it("rejects a non-array value", () => {
        expect(() => {
            setDepartments(null);
        }).toThrow(TypeError);
    });


    it("rejects an invalid department", () => {
        expect(() => {
            setDepartments([
                {
                    department_name:
                        "Missing ID",
                },
            ]);
        }).toThrow(TypeError);
    });


    it("rejects a department with a non-string ID", () => {
        expect(() => {
            setDepartments([
                {
                    dept_id: 123,
                },
            ]);
        }).toThrow(TypeError);
    });


    it("preserves the current department after refresh", () => {
        setDepartments(departments);

        selectDepartment("dept-2");

        setDepartments([
            departments[0],
            departments[1],
            departments[2],
        ]);

        expect(
            getCurrentDepartment().dept_id
        ).toBe("dept-2");
    });


    it("selects the first department if the current one disappears", () => {
        setDepartments(departments);

        selectDepartment("dept-3");

        setDepartments([
            departments[0],
            departments[1],
        ]);

        expect(
            getCurrentDepartment().dept_id
        ).toBe("dept-1");
    });


    it("does not mutate the supplied department list", () => {
        const input =
            structuredClone(departments);

        setDepartments(input);

        expect(input)
            .toEqual(departments);
    });
});


/* ==========================================================================
   Defensive Copies
   ========================================================================== */

describe("defensive copies", () => {
    it("returns copies of departments", () => {
        setDepartments(departments);

        const result =
            getDepartments();

        result[0].department_name =
            "MUTATED";

        expect(
            getDepartments()[0]
                .department_name
        ).toBe("Reception");
    });


    it("protects nested active token state", () => {
        setDepartments(departments);

        const result =
            getDepartments();

        result[0].active_tokens[0]
            .token_number = "MUTATED";

        expect(
            getDepartments()[0]
                .active_tokens[0]
                .token_number
        ).toBe("A-001");
    });


    it("protects nested next token state", () => {
        setDepartments(departments);

        const result =
            getDepartments();

        result[0].next_tokens[0]
            .token_number = "MUTATED";

        expect(
            getDepartments()[0]
                .next_tokens[0]
                .token_number
        ).toBe("A-002");
    });


    it("protects nested recent token state", () => {
        setDepartments(departments);

        const result =
            getDepartments();

        result[2].recent_tokens[0]
            .token_number = "MUTATED";

        expect(
            getDepartments()[2]
                .recent_tokens[0]
                .token_number
        ).toBe("A-004");
    });


    it("returns a defensive copy of currentDepartment", () => {
        setDepartments(departments);

        const current =
            getCurrentDepartment();

        current.department_name =
            "MUTATED";

        expect(
            getCurrentDepartment()
                .department_name
        ).toBe("Reception");
    });
});


/* ==========================================================================
   selectDepartment()
   ========================================================================== */

describe("selectDepartment()", () => {
    beforeEach(() => {
        setDepartments(departments);
    });


    it("selects a department by ID", () => {
        expect(
            selectDepartment("dept-2")
        ).toBe(true);

        expect(
            getCurrentDepartment()
                .dept_id
        ).toBe("dept-2");
    });


    it("updates currentIndex", () => {
        selectDepartment("dept-3");

        expect(
            getState().currentIndex
        ).toBe(2);
    });


    it("returns false for an unknown department", () => {
        expect(
            selectDepartment("missing")
        ).toBe(false);
    });


    it("rejects an empty department ID", () => {
        expect(() => {
            selectDepartment("");
        }).toThrow(TypeError);
    });


    it("rejects a non-string department ID", () => {
        expect(() => {
            selectDepartment(123);
        }).toThrow(TypeError);
    });
});


/* ==========================================================================
   nextDepartment()
   ========================================================================== */

describe("nextDepartment()", () => {
    it("moves to the next department", () => {
        setDepartments(departments);

        const next =
            nextDepartment();

        expect(next.dept_id)
            .toBe("dept-2");
    });


    it("updates currentIndex", () => {
        setDepartments(departments);

        nextDepartment();

        expect(
            getState().currentIndex
        ).toBe(1);
    });


    it("wraps around at the end", () => {
        setDepartments(departments);

        nextDepartment();
        nextDepartment();
        nextDepartment();

        expect(
            getCurrentDepartment()
                .dept_id
        ).toBe("dept-1");
    });


    it("handles a single department", () => {
        setDepartments(singleDepartment);

        const next =
            nextDepartment();

        expect(next.dept_id)
            .toBe("dept-1");

        expect(
            getState().currentIndex
        ).toBe(0);
    });


    it("handles an empty department list", () => {
        setDepartments([]);

        expect(
            nextDepartment()
        ).toBeNull();
    });
});


/* ==========================================================================
   previousDepartment()
   ========================================================================== */

describe("previousDepartment()", () => {
    it("moves to the previous department", () => {
        setDepartments(departments);

        selectDepartment("dept-2");

        const previous =
            previousDepartment();

        expect(previous.dept_id)
            .toBe("dept-1");
    });


    it("wraps around to the last department", () => {
        setDepartments(departments);

        const previous =
            previousDepartment();

        expect(previous.dept_id)
            .toBe("dept-3");
    });


    it("handles a single department", () => {
        setDepartments(singleDepartment);

        const previous =
            previousDepartment();

        expect(previous.dept_id)
            .toBe("dept-1");
    });


    it("handles an empty department list", () => {
        setDepartments([]);

        expect(
            previousDepartment()
        ).toBeNull();
    });
});


/* ==========================================================================
   Automatic Rotation
   ========================================================================== */

describe("automatic rotation", () => {
    it("does not start without initialization", () => {
        reset();

        expect(
            startRotation()
        ).toBe(false);
    });


    it("does not start with zero departments", () => {
        expect(
            startRotation()
        ).toBe(false);

        expect(
            isRotationActive()
        ).toBe(false);
    });


    it("does not start with one department", () => {
        setDepartments(singleDepartment);

        expect(
            startRotation()
        ).toBe(false);

        expect(
            isRotationActive()
        ).toBe(false);
    });


    it("starts with multiple departments", () => {
        setDepartments(departments);

        expect(
            startRotation()
        ).toBe(true);

        expect(
            isRotationActive()
        ).toBe(true);
    });


    it("rotates after the configured interval", () => {
        setDepartments(departments);

        initialize({
            rotationIntervalMs: 5000,
        });

        setDepartments(departments);

        startRotation();

        expect(
            getCurrentDepartment()
                .dept_id
        ).toBe("dept-1");

        vi.advanceTimersByTime(5000);

        expect(
            getCurrentDepartment()
                .dept_id
        ).toBe("dept-2");
    });


    it("continues rotating at each interval", () => {
        setDepartments(departments);

        initialize({
            rotationIntervalMs: 5000,
        });

        setDepartments(departments);

        startRotation();

        vi.advanceTimersByTime(5000);

        expect(
            getCurrentDepartment()
                .dept_id
        ).toBe("dept-2");

        vi.advanceTimersByTime(5000);

        expect(
            getCurrentDepartment()
                .dept_id
        ).toBe("dept-3");
    });


    it("wraps automatic rotation around", () => {
        setDepartments(departments);

        initialize({
            rotationIntervalMs: 5000,
        });

        setDepartments(departments);

        startRotation();

        vi.advanceTimersByTime(15000);

        expect(
            getCurrentDepartment()
                .dept_id
        ).toBe("dept-1");
    });


    it("does not create duplicate rotation timers", () => {
        setDepartments(departments);

        startRotation();
        startRotation();
        startRotation();

        vi.advanceTimersByTime(
            DEFAULT_OPTIONS.rotationIntervalMs
        );

        expect(
            getCurrentDepartment()
                .dept_id
        ).toBe("dept-2");
    });


    it("stops automatic rotation", () => {
        setDepartments(departments);

        startRotation();

        stopRotation();

        expect(
            isRotationActive()
        ).toBe(false);

        vi.advanceTimersByTime(
            DEFAULT_OPTIONS.rotationIntervalMs
        );

        expect(
            getCurrentDepartment()
                .dept_id
        ).toBe("dept-1");
    });


    it("can restart rotation after stopping", () => {
        setDepartments(departments);

        startRotation();

        stopRotation();

        startRotation();

        vi.advanceTimersByTime(
            DEFAULT_OPTIONS.rotationIntervalMs
        );

        expect(
            getCurrentDepartment()
                .dept_id
        ).toBe("dept-2");
    });
});


/* ==========================================================================
   Priority Focus
   ========================================================================== */

describe("focusDepartment()", () => {
    beforeEach(() => {
        setDepartments(departments);
    });


    it("focuses the requested department immediately", () => {
        expect(
            focusDepartment("dept-3")
        ).toBe(true);

        expect(
            getCurrentDepartment()
                .dept_id
        ).toBe("dept-3");
    });


    it("activates priority focus", () => {
        focusDepartment("dept-2");

        expect(
            isPriorityFocusActive()
        ).toBe(true);
    });


    it("returns false for an unknown department", () => {
        expect(
            focusDepartment("missing")
        ).toBe(false);

        expect(
            isPriorityFocusActive()
        ).toBe(false);
    });


    it("rejects an empty department ID", () => {
        expect(() => {
            focusDepartment("");
        }).toThrow(TypeError);
    });


    it("rejects a non-string department ID", () => {
        expect(() => {
            focusDepartment(123);
        }).toThrow(TypeError);
    });


    it("rejects an invalid focus duration", () => {
        expect(() => {
            focusDepartment(
                "dept-2",
                0
            );
        }).toThrow(RangeError);
    });


    it("temporarily suspends rotation", () => {
        initialize({
            rotationIntervalMs: 5000,
            priorityFocusDurationMs: 3000,
        });

        setDepartments(departments);

        startRotation();

        focusDepartment("dept-3");

        vi.advanceTimersByTime(5000);

        expect(
            getCurrentDepartment()
                .dept_id
        ).toBe("dept-3");
    });


    it("clears priority focus after its duration", () => {
        initialize({
            priorityFocusDurationMs: 3000,
        });

        setDepartments(departments);

        focusDepartment("dept-2");

        expect(
            isPriorityFocusActive()
        ).toBe(true);

        vi.advanceTimersByTime(3000);

        expect(
            isPriorityFocusActive()
        ).toBe(false);
    });


    it("resumes rotation after priority focus", () => {
        initialize({
            rotationIntervalMs: 5000,
            priorityFocusDurationMs: 3000,
        });

        setDepartments(departments);

        startRotation();

        focusDepartment("dept-3");

        vi.advanceTimersByTime(3000);

        expect(
            isPriorityFocusActive()
        ).toBe(false);

        vi.advanceTimersByTime(5000);

        expect(
            getCurrentDepartment()
                .dept_id
        ).toBe("dept-1");
    });


    it("uses the configured default focus duration", () => {
        initialize({
            priorityFocusDurationMs: 4000,
        });

        setDepartments(departments);

        focusDepartment("dept-2");

        vi.advanceTimersByTime(3999);

        expect(
            isPriorityFocusActive()
        ).toBe(true);

        vi.advanceTimersByTime(1);

        expect(
            isPriorityFocusActive()
        ).toBe(false);
    });


    it("supports a custom focus duration", () => {
        setDepartments(departments);

        focusDepartment(
            "dept-2",
            2000
        );

        vi.advanceTimersByTime(1999);

        expect(
            isPriorityFocusActive()
        ).toBe(true);

        vi.advanceTimersByTime(1);

        expect(
            isPriorityFocusActive()
        ).toBe(false);
    });
});


/* ==========================================================================
   clearPriorityFocus()
   ========================================================================== */

describe("clearPriorityFocus()", () => {
    it("clears an active priority focus", () => {
        setDepartments(departments);

        focusDepartment("dept-2");

        expect(
            isPriorityFocusActive()
        ).toBe(true);

        clearPriorityFocus();

        expect(
            isPriorityFocusActive()
        ).toBe(false);
    });


    it("is safe when no priority focus exists", () => {
        expect(() => {
            clearPriorityFocus();
        }).not.toThrow();
    });


    it("allows rotation to continue after clearing focus", () => {
        initialize({
            rotationIntervalMs: 5000,
        });

        setDepartments(departments);

        startRotation();

        focusDepartment("dept-3");

        clearPriorityFocus();

        vi.advanceTimersByTime(5000);

        expect(
            getCurrentDepartment()
                .dept_id
        ).toBe("dept-1");
    });
});


/* ==========================================================================
   Priority Focus + Rotation Interaction
   ========================================================================== */

describe("priority focus and rotation interaction", () => {
    it("does not advance while priority focus is active", () => {
        initialize({
            rotationIntervalMs: 5000,
            priorityFocusDurationMs: 10000,
        });

        setDepartments(departments);

        startRotation();

        focusDepartment("dept-3");

        vi.advanceTimersByTime(5000);

        expect(
            getCurrentDepartment()
                .dept_id
        ).toBe("dept-3");

        vi.advanceTimersByTime(5000);

        expect(
            getCurrentDepartment()
                .dept_id
        ).toBe("dept-3");
    });


    it("resumes normal rotation after focus expires", () => {
        initialize({
            rotationIntervalMs: 5000,
            priorityFocusDurationMs: 3000,
        });

        setDepartments(departments);

        startRotation();

        focusDepartment("dept-3");

        vi.advanceTimersByTime(3000);

        vi.advanceTimersByTime(5000);

        expect(
            getCurrentDepartment()
                .dept_id
        ).toBe("dept-1");
    });


    it("a second focus replaces the first focus timer", () => {
        initialize({
            priorityFocusDurationMs: 5000,
        });

        setDepartments(departments);

        focusDepartment("dept-2");

        vi.advanceTimersByTime(2000);

        focusDepartment("dept-3");

        vi.advanceTimersByTime(3000);

        expect(
            isPriorityFocusActive()
        ).toBe(true);

        vi.advanceTimersByTime(2000);

        expect(
            isPriorityFocusActive()
        ).toBe(false);
    });
});


/* ==========================================================================
   getState()
   ========================================================================== */

describe("getState()", () => {
    it("returns the complete manager state", () => {
        setDepartments(departments);

        const state =
            getState();

        expect(state)
            .toMatchObject({
                initialized: true,
                currentIndex: 0,
                rotationActive: false,
                priorityFocusActive: false,
                departmentCount: 3,
            });
    });


    it("returns the current department", () => {
        setDepartments(departments);

        const state =
            getState();

        expect(
            state.currentDepartment
                .dept_id
        ).toBe("dept-1");
    });


    it("protects state from external mutation", () => {
        setDepartments(departments);

        const state =
            getState();

        state.departments[0]
            .department_name = "MUTATED";

        state.currentDepartment
            .department_name = "MUTATED";

        expect(
            getState()
                .departments[0]
                .department_name
        ).toBe("Reception");

        expect(
            getState()
                .currentDepartment
                .department_name
        ).toBe("Reception");
    });
});


/* ==========================================================================
   reset()
   ========================================================================== */

describe("reset()", () => {
    it("clears departments", () => {
        setDepartments(departments);

        reset();

        expect(
            getDepartments()
        ).toEqual([]);
    });


    it("clears the current department", () => {
        setDepartments(departments);

        reset();

        expect(
            getCurrentDepartment()
        ).toBeNull();
    });


    it("resets the current index", () => {
        setDepartments(departments);

        reset();

        expect(
            getState().currentIndex
        ).toBe(-1);
    });


    it("stops automatic rotation", () => {
        setDepartments(departments);

        startRotation();

        reset();

        expect(
            isRotationActive()
        ).toBe(false);
    });


    it("clears priority focus", () => {
        setDepartments(departments);

        focusDepartment("dept-2");

        reset();

        expect(
            isPriorityFocusActive()
        ).toBe(false);
    });


    it("clears timers", () => {
        initialize({
            rotationIntervalMs: 5000,
            priorityFocusDurationMs: 5000,
        });

        setDepartments(departments);

        startRotation();

        focusDepartment("dept-3");

        reset();

        vi.advanceTimersByTime(10000);

        expect(
            getCurrentDepartment()
        ).toBeNull();
    });


    it("allows reinitialization after reset", () => {
        reset();

        initialize();

        expect(
            getState().initialized
        ).toBe(true);
    });
});

