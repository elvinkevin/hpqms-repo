import {
    afterEach,
    beforeEach,
    describe,
    expect,
    it,
    vi,
} from "vitest";

import { readFileSync } from "node:fs";
import { resolve } from "node:path";


const {
    websocketHandlers,
    mockWebSocket,
    mockApi,
} = vi.hoisted(() => {
    const websocketHandlers = new Map();

    const mockWebSocket = {
        connect: vi.fn(),
        disconnect: vi.fn(),
        on: vi.fn((event, callback) => {
            websocketHandlers.set(event, callback);
        }),
        off: vi.fn((event, callback) => {
            if (websocketHandlers.get(event) === callback) {
                websocketHandlers.delete(event);
            }
        }),
        getConnectionState: vi.fn(() => "DISCONNECTED"),
        SOCKET_STATE: {
            CONNECTING: "CONNECTING",
            CONNECTED: "CONNECTED",
            DISCONNECTED: "DISCONNECTED",
            RECONNECTING: "RECONNECTING",
        },
    };

    const mockApi = {
        getDisplaySnapshot: vi.fn(),
    };

    return {
        websocketHandlers,
        mockWebSocket,
        mockApi,
    };
});


vi.mock("../js/websocket.js", () => ({
    connect: mockWebSocket.connect,
    disconnect: mockWebSocket.disconnect,
    on: mockWebSocket.on,
    off: mockWebSocket.off,
    getConnectionState: mockWebSocket.getConnectionState,
    SOCKET_STATE: mockWebSocket.SOCKET_STATE,
}));


vi.mock("../js/api.js", () => ({
    getDisplaySnapshot: mockApi.getDisplaySnapshot,
}));


import {
    initializeConfig,
    resetConfig,
} from "../js/config.js";

import {
    reset as resetDisplayState,
} from "../js/display-state.js";

import {
    start,
    stop,
    handleMessage,
} from "../js/app.js";


const indexHtml = readFileSync(
    resolve("frontend/display.html"),
    "utf8"
);


const bodyHtml =
    (
        indexHtml.match(/<body[^>]*>([\s\S]*)<\/body>/i)?.[1] ?? ""
    ).replace(
        /<script\b[\s\S]*?<\/script>/gi,
        ""
    );


const snapshot = {
    facility_name: "HPQMS Hospital",
    server_timestamp: "2026-08-04T10:00:00Z",
    departments: [
        {
            department_id: "dept-opd",
            department_name: "Outpatient",
            active_tokens: [
                {
                    token_number: "OPD-001",
                    status: "WAITING",
                    service_point: "Room 1",
                },
            ],
            next_tokens: [],
            recent_tokens: [],
            waiting_count: 1,
            estimated_wait_minutes: 8,
        },
        {
            department_id: "dept-pharmacy",
            department_name: "Pharmacy",
            active_tokens: [],
            next_tokens: [
                {
                    token_number: "P-014",
                    status: "WAITING",
                },
            ],
            recent_tokens: [],
            waiting_count: 1,
            estimated_wait_minutes: 4,
        },
    ],
    announcements: [
        {
            announcement_id: "ann-1",
            message: "Please have your token ready.",
            priority: "INFO",
        },
    ],
};


const tokenCalledEvent = {
    event_id: "event-1",
    event_type: "TOKEN_CALLED",
    priority: "HIGH",
    occurred_at: "2026-08-04T10:01:00Z",
    token_number: "P-014",
    department_id: "dept-pharmacy",
    department_name: "Pharmacy",
    service_point: "Counter 2",
    message: "Token P-014 called to Counter 2",
};


function setupDom() {
    document.body.innerHTML = bodyHtml;
}


async function flushPromises() {
    await Promise.resolve();
    await Promise.resolve();
}


beforeEach(() => {
    vi.clearAllMocks();
    websocketHandlers.clear();

    setupDom();

    resetConfig();
    resetDisplayState();

    initializeConfig({
        rotation: {
            enabled: true,
            intervalMs: 1000,
        },
        idle: {
            enabled: false,
            timeoutMs: 60000,
        },
        alerts: {
            audioEnabled: false,
            defaultDurationMs: 5000,
        },
    });

    mockApi.getDisplaySnapshot
        .mockResolvedValue(snapshot);
});


afterEach(() => {
    stop();
    resetDisplayState();
    resetConfig();
    websocketHandlers.clear();
    document.body.innerHTML = "";
});


describe("frontend runtime integration", () => {
    it("renders the initial snapshot through app startup", async () => {
        await start();

        expect(document.body.dataset.layout)
            .toBe("SINGLE_DEPARTMENT");

        expect(
            document.querySelector("#facility-name")?.textContent
        ).toContain("HPQMS Hospital");

        expect(
            document.querySelector("#primary-viewport")?.textContent
        ).toContain("Outpatient");

        expect(
            document.querySelector("#announcement-text")?.textContent
        ).toContain("Please have your token ready.");

        expect(mockWebSocket.connect)
            .toHaveBeenCalledTimes(1);
    });


    it("routes a TOKEN_CALLED event through alert, state, focus, and render", async () => {
        await start();

        handleMessage(tokenCalledEvent);

        await flushPromises();

        expect(
            document.querySelector("#alert-layer")?.hidden
        ).toBe(false);

        expect(
            document.querySelector("#alert-token")?.textContent
        ).toContain("P-014");

        expect(
            document.querySelector("#alert-service-point")?.textContent
        ).toContain("Counter 2");

        expect(
            document.querySelector("#primary-viewport")?.textContent
        ).toContain("Pharmacy");

        expect(
            document.querySelector("#primary-viewport")?.textContent
        ).toContain("P-014");
    });


    it("refreshes the authoritative snapshot after QUEUE_UPDATED", async () => {
        await start();

        mockApi.getDisplaySnapshot.mockClear();

        handleMessage({
            event_id: "event-queue",
            event_type: "QUEUE_UPDATED",
            occurred_at: "2026-08-04T10:02:00Z",
        });

        await flushPromises();

        expect(mockApi.getDisplaySnapshot)
            .toHaveBeenCalledTimes(1);
    });
});
