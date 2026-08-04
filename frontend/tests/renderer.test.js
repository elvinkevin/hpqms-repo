

import { describe, it, expect, beforeEach, vi } from "vitest";

import {
    renderSnapshot,
    renderDepartments,
    renderDepartment,
    renderAnnouncements,
    renderConnectionStatus,
    clearRenderer,
} from "../js/renderer.js";


/* ==========================================================================
   DOM FIXTURE
   ========================================================================== */

function createDOM() {
    document.body.innerHTML = `
        <div id="display-app">

            <header id="display-header">

                <div id="facility-branding">
                    <img
                        id="facility-logo"
                        src=""
                        alt="Hospital Logo"
                        hidden
                    />

                    <h1 id="facility-name">
                        Loading Facility...
                    </h1>
                </div>

                <div id="display-meta">

                    <div
                        id="connection-indicator"
                        data-status="CONNECTING"
                    >
                        <span class="status-dot"></span>

                        <span id="connection-text">
                            CONNECTING
                        </span>
                    </div>

                    <time id="clock">
                        00:00:00
                    </time>

                </div>

            </header>


            <main id="display-main">

                <div id="primary-viewport">

                    <div id="viewport-loader">
                        <p>
                            Initializing Display Engine...
                        </p>
                    </div>

                </div>

            </main>


            <footer id="display-footer">

                <div id="announcement-wrapper">

                    <span id="announcement-label">
                        ANNOUNCEMENT
                    </span>

                    <div id="announcement-ticker">

                        <p id="announcement-text">
                            Welcome.
                        </p>

                    </div>

                </div>

                <div id="pagination-indicator" hidden>

                    <span id="pagination-text">
                        PAGE 1 OF 1
                    </span>

                    <div id="pagination-dots"></div>

                </div>

            </footer>

        </div>
    `;
}


/* ==========================================================================
   TEST DATA
   ========================================================================== */

function createSnapshot(overrides = {}) {
    return {
        facility_name: "Nairobi General Hospital",

        server_timestamp:
            "2026-07-31T12:00:00.000Z",

        departments: [
            {
                department_id: "dept-1",
                department_name: "Pharmacy",

                active_tokens: [
                    {
                        token_number: "P-014",
                        service_point: "Counter 2",
                        status: "CALLED",
                        called_at:
                            "2026-07-31T11:59:00.000Z",
                    },
                ],

                next_tokens: [
                    {
                        token_number: "P-015",
                    },
                    {
                        token_number: "P-016",
                    },
                ],

                recent_tokens: [
                    {
                        token_number: "P-013",
                    },
                ],

                waiting_count: 8,

                estimated_wait_minutes: 24,
            },

            {
                department_id: "dept-2",
                department_name: "Laboratory",

                active_tokens: [],

                next_tokens: [
                    {
                        token_number: "L-021",
                    },
                ],

                recent_tokens: [],

                waiting_count: 3,

                estimated_wait_minutes: 10,
            },
        ],

        announcements: [
            {
                announcement_id: "announcement-1",
                priority: "INFO",
                message:
                    "Please have your token ready.",
                starts_at: null,
                expires_at: null,
            },
        ],

        ...overrides,
    };
}


/* ==========================================================================
   SETUP
   ========================================================================== */

beforeEach(() => {
    createDOM();
});


/* ==========================================================================
   INITIALIZATION
   ========================================================================== */

describe("renderer initialization", () => {

    it("renders into the primary viewport", () => {

        renderSnapshot(createSnapshot());

        const viewport =
            document.querySelector("#primary-viewport");

        expect(viewport).not.toBeNull();

        expect(
            viewport.children.length
        ).toBeGreaterThan(0);
    });


    it("removes the loading state after rendering", () => {

        renderSnapshot(createSnapshot());

        expect(
            document.querySelector("#viewport-loader")
        ).toBeNull();
    });


    it("does not crash when the snapshot is empty", () => {

        expect(() => {
            renderSnapshot({
                facility_name: null,
                server_timestamp:
                    "2026-07-31T12:00:00.000Z",
                departments: [],
                announcements: [],
            });
        }).not.toThrow();
    });

});


/* ==========================================================================
   FACILITY BRANDING
   ========================================================================== */

describe("facility branding", () => {

    it("renders the facility name", () => {

        renderSnapshot(createSnapshot());

        expect(
            document.querySelector("#facility-name")
                .textContent
        ).toBe("Nairobi General Hospital");
    });


    it("handles a missing facility name", () => {

        renderSnapshot(
            createSnapshot({
                facility_name: null,
            })
        );

        const name =
            document.querySelector("#facility-name");

        expect(name).not.toBeNull();
        expect(name.textContent).toBeTruthy();
    });

});


/* ==========================================================================
   DEPARTMENT RENDERING
   ========================================================================== */

describe("department rendering", () => {

    it("renders every department", () => {

        renderSnapshot(createSnapshot());

        const departments =
            document.querySelectorAll(
                "[data-department-id]"
            );

        expect(departments).toHaveLength(2);
    });


    it("renders the department name", () => {

        renderSnapshot(createSnapshot());

        const department =
            document.querySelector(
                '[data-department-id="dept-1"]'
            );

        expect(department).not.toBeNull();

        expect(
            department.textContent
        ).toContain("Pharmacy");
    });


    it("associates the DOM node with the department id", () => {

        renderSnapshot(createSnapshot());

        const department =
            document.querySelector(
                '[data-department-id="dept-1"]'
            );

        expect(
            department.dataset.departmentId
        ).toBe("dept-1");
    });


    it("renders multiple departments independently", () => {

        renderSnapshot(createSnapshot());

        const pharmacy =
            document.querySelector(
                '[data-department-id="dept-1"]'
            );

        const laboratory =
            document.querySelector(
                '[data-department-id="dept-2"]'
            );

        expect(pharmacy.textContent)
            .toContain("Pharmacy");

        expect(laboratory.textContent)
            .toContain("Laboratory");
    });

});


/* ==========================================================================
   ACTIVE TOKENS
   ========================================================================== */

describe("active token rendering", () => {

    it("renders an active token", () => {

        renderSnapshot(createSnapshot());

        const department =
            document.querySelector(
                '[data-department-id="dept-1"]'
            );

        expect(
            department.textContent
        ).toContain("P-014");
    });


    it("renders the service point", () => {

        renderSnapshot(createSnapshot());

        const department =
            document.querySelector(
                '[data-department-id="dept-1"]'
            );

        expect(
            department.textContent
        ).toContain("Counter 2");
    });


    it("renders the token status", () => {

        renderSnapshot(createSnapshot());

        const department =
            document.querySelector(
                '[data-department-id="dept-1"]'
            );

        expect(
            department.textContent
        ).toContain("CALLED");
    });


    it("renders multiple active tokens", () => {

        const snapshot = createSnapshot();

        snapshot.departments[0].active_tokens.push({
            token_number: "P-017",
            service_point: "Counter 4",
            status: "IN_PROGRESS",
            called_at: null,
        });

        renderSnapshot(snapshot);

        const department =
            document.querySelector(
                '[data-department-id="dept-1"]'
            );

        expect(
            department.textContent
        ).toContain("P-014");

        expect(
            department.textContent
        ).toContain("P-017");
    });

});


/* ==========================================================================
   NEXT TOKENS
   ========================================================================== */

describe("next token rendering", () => {

    it("renders the next tokens", () => {

        renderSnapshot(createSnapshot());

        const department =
            document.querySelector(
                '[data-department-id="dept-1"]'
            );

        expect(
            department.textContent
        ).toContain("P-015");

        expect(
            department.textContent
        ).toContain("P-016");
    });


    it("renders next tokens in their supplied order", () => {

        renderSnapshot(createSnapshot());

        const department =
            document.querySelector(
                '[data-department-id="dept-1"]'
            );

        const text =
            department.textContent;

        expect(
            text.indexOf("P-015")
        ).toBeLessThan(
            text.indexOf("P-016")
        );
    });

});


/* ==========================================================================
   RECENT TOKENS
   ========================================================================== */

describe("recent token rendering", () => {

    it("renders recently processed tokens", () => {

        renderSnapshot(createSnapshot());

        const department =
            document.querySelector(
                '[data-department-id="dept-1"]'
            );

        expect(
            department.textContent
        ).toContain("P-013");
    });

});


/* ==========================================================================
   QUEUE STATISTICS
   ========================================================================== */

describe("queue statistics", () => {

    it("renders waiting count", () => {

        renderSnapshot(createSnapshot());

        const department =
            document.querySelector(
                '[data-department-id="dept-1"]'
            );

        expect(
            department.textContent
        ).toContain("8");
    });


    it("renders estimated waiting time", () => {

        renderSnapshot(createSnapshot());

        const department =
            document.querySelector(
                '[data-department-id="dept-1"]'
            );

        expect(
            department.textContent
        ).toContain("24");
    });


    it("handles a null estimated wait time", () => {

        const snapshot = createSnapshot();

        snapshot.departments[0]
            .estimated_wait_minutes = null;

        expect(() => {
            renderSnapshot(snapshot);
        }).not.toThrow();
    });

});


/* ==========================================================================
   ANNOUNCEMENTS
   ========================================================================== */

describe("announcement rendering", () => {

    it("renders the announcement message", () => {

        renderSnapshot(createSnapshot());

        expect(
            document.querySelector(
                "#announcement-text"
            ).textContent
        ).toContain(
            "Please have your token ready."
        );
    });


    it("renders an updated announcement", () => {

        renderAnnouncements([
            {
                announcement_id: "announcement-2",
                priority: "WARNING",
                message:
                    "Please remain seated until called.",
                starts_at: null,
                expires_at: null,
            },
        ]);

        expect(
            document.querySelector(
                "#announcement-text"
            ).textContent
        ).toContain(
            "Please remain seated until called."
        );
    });


    it("handles an empty announcement list", () => {

        expect(() => {
            renderAnnouncements([]);
        }).not.toThrow();
    });

});


/* ==========================================================================
   CONNECTION STATUS
   ========================================================================== */

describe("connection status rendering", () => {

    it("renders CONNECTED status", () => {

        renderConnectionStatus("CONNECTED");

        const indicator =
            document.querySelector(
                "#connection-indicator"
            );

        expect(
            indicator.dataset.status
        ).toBe("CONNECTED");

        expect(
            document.querySelector(
                "#connection-text"
            ).textContent
        ).toContain("CONNECTED");
    });


    it("renders CONNECTING status", () => {

        renderConnectionStatus("CONNECTING");

        expect(
            document.querySelector(
                "#connection-text"
            ).textContent
        ).toContain("CONNECTING");
    });


    it("renders DISCONNECTED status", () => {

        renderConnectionStatus("DISCONNECTED");

        expect(
            document.querySelector(
                "#connection-text"
            ).textContent
        ).toContain("DISCONNECTED");
    });

});


/* ==========================================================================
   REPEATED RENDERING
   ========================================================================== */

describe("repeated rendering", () => {

    it("does not duplicate departments", () => {

        const snapshot = createSnapshot();

        renderSnapshot(snapshot);
        renderSnapshot(snapshot);

        const departments =
            document.querySelectorAll(
                "[data-department-id]"
            );

        expect(departments).toHaveLength(2);
    });


    it("replaces old department state", () => {

        renderSnapshot(createSnapshot());

        const updated =
            createSnapshot({
                departments: [
                    {
                        department_id: "dept-3",
                        department_name: "Radiology",
                        active_tokens: [],
                        next_tokens: [],
                        recent_tokens: [],
                        waiting_count: 0,
                        estimated_wait_minutes: null,
                    },
                ],
            });

        renderSnapshot(updated);

        expect(
            document.querySelector(
                '[data-department-id="dept-1"]'
            )
        ).toBeNull();

        expect(
            document.querySelector(
                '[data-department-id="dept-3"]'
            )
        ).not.toBeNull();
    });

});


/* ==========================================================================
   CLEANUP
   ========================================================================== */

describe("clearRenderer()", () => {

    it("clears the primary viewport", () => {

        renderSnapshot(createSnapshot());

        clearRenderer();

        const viewport =
            document.querySelector(
                "#primary-viewport"
            );

        expect(viewport.innerHTML)
            .toBe("");
    });


    it("does not remove the viewport itself", () => {

        renderSnapshot(createSnapshot());

        clearRenderer();

        expect(
            document.querySelector(
                "#primary-viewport"
            )
        ).not.toBeNull();
    });

});


/* ==========================================================================
   DEFENSIVE BEHAVIOR
   ========================================================================== */

describe("defensive behavior", () => {

    it("does not crash when departments is empty", () => {

        expect(() => {
            renderSnapshot({
                facility_name: "HPQMS",
                server_timestamp:
                    "2026-07-31T12:00:00.000Z",
                departments: [],
                announcements: [],
            });
        }).not.toThrow();
    });


    it("does not crash when active_tokens is missing", () => {

        const snapshot = createSnapshot();

        delete snapshot
            .departments[0]
            .active_tokens;

        expect(() => {
            renderSnapshot(snapshot);
        }).not.toThrow();
    });


    it("does not crash when announcements are missing", () => {

        const snapshot = createSnapshot();

        delete snapshot.announcements;

        expect(() => {
            renderSnapshot(snapshot);
        }).not.toThrow();
    });

});