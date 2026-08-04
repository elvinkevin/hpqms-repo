import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

import {
    IDLE_MODE,
    initializeIdleManager,

    enterStandby,
    enterAmbient,

    wake,
    resetIdleTimer,

    getIdleMode,
    getIdleState,

    isIdle,
    isStandby,
    isAmbient,

    resetIdleManager,
    destroyIdleManager,
} from "../js/idle-manager.js";


/* ==========================================================================
   DOM FIXTURE
   ========================================================================== */

function createDOM() {
    document.body.innerHTML = `
        <div id="display-shell"></div>

        <div id="idle-layer" hidden aria-hidden="true">

            <section
                id="standby-view"
                hidden
                class="idle-card standby-card"
            >
                <h2 id="standby-title">
                    All Services Are Available
                </h2>

                <p id="standby-subtitle">
                    Please take a token and wait for your number to be called.
                </p>
            </section>

            <section
                id="ambient-view"
                hidden
                class="idle-card ambient-card"
            >
                <time id="ambient-clock">
                    00:00
                </time>

                <span id="ambient-date">
                    Monday, 1 January
                </span>

                <div id="ambient-announcement-card">
                    <h3 id="ambient-title">
                        Health & Safety Notice
                    </h3>

                    <p id="ambient-health-text">
                        Please sanitize your hands.
                    </p>
                </div>
            </section>

        </div>
    `;
}


/* ==========================================================================
   TEST SETUP
   ========================================================================== */

beforeEach(() => {
    vi.useFakeTimers();

    createDOM();

    initializeIdleManager();
});


afterEach(() => {
    destroyIdleManager();

    vi.clearAllTimers();
    vi.useRealTimers();

    document.body.innerHTML = "";
});


/* ==========================================================================
   INITIALIZATION
   ========================================================================== */

describe("initialization", () => {

    it("initializes successfully", () => {
        expect(initializeIdleManager()).toBe(true);
    });


    it("starts in the active state", () => {
        expect(isIdle()).toBe(false);
    });


    it("starts with no idle mode", () => {
        expect(getIdleMode()).toBe(IDLE_MODE.NONE);
    });


    it("does not start in standby mode", () => {
        expect(isStandby()).toBe(false);
    });


    it("does not start in ambient mode", () => {
        expect(isAmbient()).toBe(false);
    });


    it("returns the complete initial idle state", () => {
        const state = getIdleState();

        expect(state).toEqual(
            expect.objectContaining({
                idle: false,
                mode: IDLE_MODE.NONE,
            })
        );
    });

});


/* ==========================================================================
   STANDBY MODE
   ========================================================================== */

describe("enterStandby()", () => {

    it("enters standby mode", () => {
        expect(enterStandby()).toBe(true);

        expect(isIdle()).toBe(true);
        expect(isStandby()).toBe(true);
        expect(isAmbient()).toBe(false);
        expect(getIdleMode()).toBe(IDLE_MODE.STANDBY);
    });


    it("shows the idle layer", () => {
        enterStandby();

        const idleLayer =
            document.getElementById("idle-layer");

        expect(idleLayer.hidden).toBe(false);
        expect(idleLayer.getAttribute("aria-hidden"))
            .toBe("false");
    });


    it("shows the standby view", () => {
        enterStandby();

        const standby =
            document.getElementById("standby-view");

        expect(standby.hidden).toBe(false);
    });


    it("keeps ambient view hidden", () => {
        enterStandby();

        const ambient =
            document.getElementById("ambient-view");

        expect(ambient.hidden).toBe(true);
    });


    it("updates idle state", () => {
        enterStandby();

        expect(getIdleState()).toEqual(
            expect.objectContaining({
                idle: true,
                mode: IDLE_MODE.STANDBY,
            })
        );
    });

});


/* ==========================================================================
   AMBIENT MODE
   ========================================================================== */

describe("enterAmbient()", () => {

    it("enters ambient mode", () => {
        expect(enterAmbient()).toBe(true);

        expect(isIdle()).toBe(true);
        expect(isAmbient()).toBe(true);
        expect(isStandby()).toBe(false);
        expect(getIdleMode()).toBe(IDLE_MODE.AMBIENT);
    });


    it("shows the idle layer", () => {
        enterAmbient();

        const idleLayer =
            document.getElementById("idle-layer");

        expect(idleLayer.hidden).toBe(false);
        expect(idleLayer.getAttribute("aria-hidden"))
            .toBe("false");
    });


    it("shows the ambient view", () => {
        enterAmbient();

        const ambient =
            document.getElementById("ambient-view");

        expect(ambient.hidden).toBe(false);
    });


    it("keeps standby view hidden", () => {
        enterAmbient();

        const standby =
            document.getElementById("standby-view");

        expect(standby.hidden).toBe(true);
    });


    it("updates idle state", () => {
        enterAmbient();

        expect(getIdleState()).toEqual(
            expect.objectContaining({
                idle: true,
                mode: IDLE_MODE.AMBIENT,
            })
        );
    });

});


/* ==========================================================================
   MODE TRANSITIONS
   ========================================================================== */

describe("idle mode transitions", () => {

    it("switches from standby to ambient", () => {
        enterStandby();

        expect(isStandby()).toBe(true);

        enterAmbient();

        expect(isStandby()).toBe(false);
        expect(isAmbient()).toBe(true);
    });


    it("switches from ambient to standby", () => {
        enterAmbient();

        expect(isAmbient()).toBe(true);

        enterStandby();

        expect(isAmbient()).toBe(false);
        expect(isStandby()).toBe(true);
    });


    it("does not leave both modes active", () => {
        enterStandby();

        enterAmbient();

        expect(isStandby()).toBe(false);
        expect(isAmbient()).toBe(true);
    });

});


/* ==========================================================================
   WAKE
   ========================================================================== */

describe("wake()", () => {

    it("exits standby mode", () => {
        enterStandby();

        expect(wake()).toBe(true);

        expect(isIdle()).toBe(false);
        expect(getIdleMode()).toBe(IDLE_MODE.NONE);
    });


    it("exits ambient mode", () => {
        enterAmbient();

        expect(wake()).toBe(true);

        expect(isIdle()).toBe(false);
        expect(getIdleMode()).toBe(IDLE_MODE.NONE);
    });


    it("hides the idle layer", () => {
        enterStandby();

        wake();

        const idleLayer =
            document.getElementById("idle-layer");

        expect(idleLayer.hidden).toBe(true);
        expect(idleLayer.getAttribute("aria-hidden"))
            .toBe("true");
    });


    it("hides standby view after waking", () => {
        enterStandby();

        wake();

        expect(
            document.getElementById("standby-view").hidden
        ).toBe(true);
    });


    it("hides ambient view after waking", () => {
        enterAmbient();

        wake();

        expect(
            document.getElementById("ambient-view").hidden
        ).toBe(true);
    });


    it("is safe when already awake", () => {
        expect(() => wake()).not.toThrow();

        expect(isIdle()).toBe(false);
        expect(getIdleMode()).toBe(IDLE_MODE.NONE);
    });

});


/* ==========================================================================
   IDLE TIMER
   ========================================================================== */

describe("resetIdleTimer()", () => {

    it("can reset the idle timer", () => {
        expect(() => resetIdleTimer()).not.toThrow();
    });


    it("keeps the display active after resetting", () => {
        resetIdleTimer();

        expect(isIdle()).toBe(false);
    });


    it("can reset the timer repeatedly", () => {
        expect(() => {
            resetIdleTimer();
            resetIdleTimer();
            resetIdleTimer();
        }).not.toThrow();
    });

});


/* ==========================================================================
   AUTOMATIC IDLE TRANSITION
   ========================================================================== */

describe("automatic idle behavior", () => {

    it("does not enter idle immediately", () => {
        expect(isIdle()).toBe(false);

        vi.advanceTimersByTime(100);

        expect(isIdle()).toBe(false);
    });


    it("does not leave multiple idle modes active", () => {
        enterStandby();

        expect(isStandby()).toBe(true);
        expect(isAmbient()).toBe(false);

        vi.advanceTimersByTime(100);

        expect(
            Number(isStandby()) +
            Number(isAmbient())
        ).toBe(1);
    });

});


/* ==========================================================================
   RESET
   ========================================================================== */

describe("resetIdleManager()", () => {

    it("returns the manager to active state", () => {
        enterStandby();

        resetIdleManager();

        expect(isIdle()).toBe(false);
        expect(getIdleMode()).toBe(IDLE_MODE.NONE);
    });


    it("clears standby mode", () => {
        enterStandby();

        resetIdleManager();

        expect(isStandby()).toBe(false);
    });


    it("clears ambient mode", () => {
        enterAmbient();

        resetIdleManager();

        expect(isAmbient()).toBe(false);
    });


    it("hides the idle layer", () => {
        enterStandby();

        resetIdleManager();

        expect(
            document.getElementById("idle-layer").hidden
        ).toBe(true);
    });


    it("can be initialized again after reset", () => {
        resetIdleManager();

        expect(initializeIdleManager()).toBe(true);

        expect(isIdle()).toBe(false);
    });

});


/* ==========================================================================
   DESTROY
   ========================================================================== */

describe("destroyIdleManager()", () => {

    it("can be destroyed safely", () => {
        expect(() => destroyIdleManager()).not.toThrow();
    });


    it("clears idle state", () => {
        enterStandby();

        destroyIdleManager();

        expect(isIdle()).toBe(false);
        expect(getIdleMode()).toBe(IDLE_MODE.NONE);
    });


    it("clears timers", () => {
        enterStandby();

        destroyIdleManager();

        expect(vi.getTimerCount()).toBe(0);
    });


    it("can be initialized again after destruction", () => {
        destroyIdleManager();

        expect(initializeIdleManager()).toBe(true);

        expect(isIdle()).toBe(false);
    });

});


/* ==========================================================================
   STATE API
   ========================================================================== */

describe("state getters", () => {

    it("reports standby correctly", () => {
        enterStandby();

        expect(isIdle()).toBe(true);
        expect(isStandby()).toBe(true);
        expect(isAmbient()).toBe(false);
    });


    it("reports ambient correctly", () => {
        enterAmbient();

        expect(isIdle()).toBe(true);
        expect(isStandby()).toBe(false);
        expect(isAmbient()).toBe(true);
    });


    it("returns a consistent state object", () => {
        enterAmbient();

        const state = getIdleState();

        expect(state.idle).toBe(true);
        expect(state.mode).toBe(IDLE_MODE.AMBIENT);
    });

});