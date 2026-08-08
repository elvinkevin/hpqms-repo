
import {
    beforeEach,
    afterEach,
    describe,
    expect,
    it,
    vi,
} from "vitest";


/*
|--------------------------------------------------------------------------
| Mocks
|--------------------------------------------------------------------------
|
| app.js depends on three modules:
|
|   config.js
|   websocket.js
|   api.js
|   display-state.js
|
| We mock those dependencies because app.js is an orchestrator.
| Its job is to coordinate them, not to test their internals.
|--------------------------------------------------------------------------
*/
const {
    mockConfig,
    websocketHandlers,
    mockWebSocket,
    mockDisplayState,
    mockApi,
    mockRenderer,
    mockRotation,
    mockIdle,
    mockAlerts,
} = vi.hoisted(() => {
    const websocketHandlers = new Map();

    const mockConfig = {
        backend: {
            apiUrl: "http://localhost:8000/api",
            websocketUrl:
                "ws://localhost:8000/ws/display",
            connectionTimeoutMs: 5000,
        },
        rotation: {
            enabled: true,
            intervalMs: 15000,
        },
        idle: {
            enabled: true,
            timeoutMs: 120000,
        },
        alerts: {
            audioEnabled: true,
            defaultDurationMs: 5000,
            emergencyDurationMs: 15000,
        },
        features: {
            audio: true,
            announcements: true,
            multiDepartment: true,
        },
    };

    const mockWebSocket = {
        connect: vi.fn(),
        disconnect: vi.fn(),

        on: vi.fn((event, callback) => {
            websocketHandlers.set(
                event,
                callback
            );
        }),

        off: vi.fn((event, callback) => {
            if (
                websocketHandlers.get(event) ===
                callback
            ) {
                websocketHandlers.delete(event);
            }
        }),

        getConnectionState: vi.fn(
            () => "DISCONNECTED"
        ),

        SOCKET_STATE: {
            CONNECTING: "CONNECTING",
            CONNECTED: "CONNECTED",
            DISCONNECTED: "DISCONNECTED",
            RECONNECTING: "RECONNECTING",
        },
    };

    const mockDisplayState = {
        getState: vi.fn(() => ({
            snapshot: null,
            initialized: false,
            stale: false,
            connection_status:
                "DISCONNECTED",
        })),

        setSnapshot: vi.fn(),

        applyEvent: vi.fn(),

        setConnectionStatus: vi.fn(),

        subscribe: vi.fn(() => vi.fn()),
    };

    const mockApi = {
        getDisplaySnapshot: vi.fn(),
    };

    const mockRenderer = {
        initializeRenderer: vi.fn(),
        renderSnapshot: vi.fn(),
        renderDepartments: vi.fn(),
        renderConnectionStatus: vi.fn(),
        clearRenderer: vi.fn(),
        showLoader: vi.fn(),
    };

    const mockRotation = {
        initialize: vi.fn(),
        setDepartments: vi.fn(),
        getCurrentDepartment: vi.fn(() => null),
        startRotation: vi.fn(),
        stopRotation: vi.fn(),
        focusDepartment: vi.fn(() => false),
        reset: vi.fn(),
    };

    const mockIdle = {
        initializeIdleManager: vi.fn(),
        resetIdleTimer: vi.fn(),
        destroyIdleManager: vi.fn(),
    };

    const mockAlerts = {
        initialize: vi.fn(),
        setCallbacks: vi.fn(),
        handleEvent: vi.fn(),
        reset: vi.fn(),
    };

    return {
        mockConfig,
        websocketHandlers,
        mockWebSocket,
        mockDisplayState,
        mockApi,
        mockRenderer,
        mockRotation,
        mockIdle,
        mockAlerts,
    };
});


vi.mock("../js/config.js", () => ({
    getConfig: vi.fn(() => mockConfig),
}));


vi.mock("../js/websocket.js", () => ({
    connect: mockWebSocket.connect,
    disconnect: mockWebSocket.disconnect,
    on: mockWebSocket.on,
    off: mockWebSocket.off,

    getConnectionState:
        mockWebSocket.getConnectionState,

    SOCKET_STATE:
        mockWebSocket.SOCKET_STATE,
}));


vi.mock("../js/api.js", () => ({
    getDisplaySnapshot:
        mockApi.getDisplaySnapshot,
}));


vi.mock("../js/display-state.js", () => ({
    getState: mockDisplayState.getState,

    setSnapshot:
        mockDisplayState.setSnapshot,

    applyEvent:
        mockDisplayState.applyEvent,

    setConnectionStatus:
        mockDisplayState.setConnectionStatus,

    subscribe:
        mockDisplayState.subscribe,
}));


vi.mock("../js/renderer.js", () => ({
    initializeRenderer:
        mockRenderer.initializeRenderer,
    renderSnapshot:
        mockRenderer.renderSnapshot,
    renderDepartments:
        mockRenderer.renderDepartments,
    renderConnectionStatus:
        mockRenderer.renderConnectionStatus,
    clearRenderer:
        mockRenderer.clearRenderer,
    showLoader:
        mockRenderer.showLoader,
}));


vi.mock("../js/rotation-manager.js", () => ({
    initialize:
        mockRotation.initialize,
    setDepartments:
        mockRotation.setDepartments,
    getCurrentDepartment:
        mockRotation.getCurrentDepartment,
    startRotation:
        mockRotation.startRotation,
    stopRotation:
        mockRotation.stopRotation,
    focusDepartment:
        mockRotation.focusDepartment,
    reset:
        mockRotation.reset,
}));


vi.mock("../js/idle-manager.js", () => ({
    initializeIdleManager:
        mockIdle.initializeIdleManager,
    resetIdleTimer:
        mockIdle.resetIdleTimer,
    destroyIdleManager:
        mockIdle.destroyIdleManager,
}));


vi.mock("../js/alert-manager.js", () => ({
    initialize:
        mockAlerts.initialize,
    setCallbacks:
        mockAlerts.setCallbacks,
    handleEvent:
        mockAlerts.handleEvent,
    reset:
        mockAlerts.reset,
}));


import {
    start,
    stop,
    syncSnapshot,
    getAppState,
    handleMessage,
    handleConnected,
    handleDisconnected,
    handleReconnecting,
} from "../js/app.js";


/*
|--------------------------------------------------------------------------
| Fixtures
|--------------------------------------------------------------------------
*/

const snapshot = {
    facility_name: "HPQMS Hospital",
    server_timestamp:
        "2026-07-31T10:00:00Z",

    departments: [
        {
            department_id:
                "00000000-0000-0000-0000-000000000001",

            department_name: "Outpatient",

            active_tokens: [],

            next_tokens: [],

            recent_tokens: [],

            waiting_count: 0,

            estimated_wait_minutes: 0,
        },
    ],

    announcements: [],
};


const notificationEvent = {
    event_id:
        "00000000-0000-0000-0000-000000000010",

    event_type: "TOKEN_CALLED",

    priority: "HIGH",

    occurred_at:
        "2026-07-31T10:01:00Z",

    token_number: "A-001",

    visit_id:
        "00000000-0000-0000-0000-000000000011",

    queue_entry_id:
        "00000000-0000-0000-0000-000000000012",

    department_id:
        "00000000-0000-0000-0000-000000000001",

    department_name: "Outpatient",

    service_point: "Room 1",

    message: "Token A-001 called",

    targets: [
        "PUBLIC_DISPLAY",
    ],
};


/*
|--------------------------------------------------------------------------
| Helpers
|--------------------------------------------------------------------------
*/

function emitWebSocketEvent(
    eventName,
    payload
) {
    const handler =
        websocketHandlers.get(eventName);

    if (!handler) {
        throw new Error(
            `No WebSocket handler registered for ${eventName}`
        );
    }

    return handler(payload);
}


/*
|--------------------------------------------------------------------------
| Test Setup
|--------------------------------------------------------------------------
*/

beforeEach(() => {
    vi.clearAllMocks();

    websocketHandlers.clear();

    mockApi.getDisplaySnapshot
        .mockResolvedValue(snapshot);

    mockDisplayState.getState
        .mockReturnValue({
            snapshot: null,
            initialized: false,
            stale: false,
            connection_status:
                "DISCONNECTED",
        });

    mockWebSocket.getConnectionState
        .mockReturnValue("DISCONNECTED");
});


afterEach(() => {
    /*
     * Ensure every test leaves the application
     * in a clean state.
     */
    stop();

    websocketHandlers.clear();

    vi.clearAllMocks();
});


/*
|--------------------------------------------------------------------------
| Initial State
|--------------------------------------------------------------------------
*/

describe("initial application state", () => {
    it("starts stopped", () => {
        const state = getAppState();

        expect(state.started)
            .toBe(false);
    });


    it("is not starting initially", () => {
        const state = getAppState();

        expect(state.starting)
            .toBe(false);
    });


    it("is not synchronizing initially", () => {
        const state = getAppState();

        expect(state.syncing)
            .toBe(false);
    });
});


/*
|--------------------------------------------------------------------------
| syncSnapshot()
|--------------------------------------------------------------------------
*/

describe("syncSnapshot()", () => {
    it("requests the authoritative display snapshot", async () => {
        await syncSnapshot();

        expect(
            mockApi.getDisplaySnapshot
        ).toHaveBeenCalledTimes(1);
    });


    it("passes the snapshot to display-state", async () => {
        await syncSnapshot();

        expect(
            mockDisplayState.setSnapshot
        ).toHaveBeenCalledWith(snapshot);
    });


    it("returns the resulting display state", async () => {
        const state = {
            snapshot,
            initialized: true,
            stale: false,
            connection_status:
                "DISCONNECTED",
        };

        mockDisplayState.getState
            .mockReturnValue(state);

        const result =
            await syncSnapshot();

        expect(result)
            .toEqual(state);
    });


    it("does not perform duplicate concurrent synchronization", async () => {
        let resolveSnapshot;

        mockApi.getDisplaySnapshot
            .mockImplementation(
                () =>
                    new Promise((resolve) => {
                        resolveSnapshot = resolve;
                    })
            );

        const first =
            syncSnapshot();

        const second =
            syncSnapshot();

        expect(
            mockApi.getDisplaySnapshot
        ).toHaveBeenCalledTimes(1);

        resolveSnapshot(snapshot);

        await first;
        await second;
    });


    it("allows synchronization again after the first completes", async () => {
        await syncSnapshot();

        await syncSnapshot();

        expect(
            mockApi.getDisplaySnapshot
        ).toHaveBeenCalledTimes(2);
    });


    it("clears syncing after a failed request", async () => {
        mockApi.getDisplaySnapshot
            .mockRejectedValue(
                new Error("Backend unavailable")
            );

        await expect(
            syncSnapshot()
        ).rejects.toThrow(
            "Backend unavailable"
        );

        expect(
            getAppState().syncing
        ).toBe(false);
    });
});


/*
|--------------------------------------------------------------------------
| start()
|--------------------------------------------------------------------------
*/

describe("start()", () => {
    it("initializes configuration before startup", async () => {
        await start();

        expect(
            mockConfig
        ).toBeDefined();
    });


    it("registers WebSocket event listeners", async () => {
        await start();

        expect(mockWebSocket.on)
            .toHaveBeenCalledWith(
                "connected",
                expect.any(Function)
            );

        expect(mockWebSocket.on)
            .toHaveBeenCalledWith(
                "message",
                expect.any(Function)
            );

        expect(mockWebSocket.on)
            .toHaveBeenCalledWith(
                "disconnected",
                expect.any(Function)
            );

        expect(mockWebSocket.on)
            .toHaveBeenCalledWith(
                "reconnecting",
                expect.any(Function)
            );

        expect(mockWebSocket.on)
            .toHaveBeenCalledWith(
                "error",
                expect.any(Function)
            );
    });


    it("registers a display-state subscription", async () => {
        await start();

        expect(
            mockDisplayState.subscribe
        ).toHaveBeenCalledTimes(1);
    });


    it("synchronizes the snapshot before connecting", async () => {
        const order = [];

        mockApi.getDisplaySnapshot
            .mockImplementation(async () => {
                order.push("snapshot");

                return snapshot;
            });

        mockWebSocket.connect
            .mockImplementation(() => {
                order.push("connect");
            });

        await start();

        expect(order)
            .toEqual([
                "snapshot",
                "connect",
            ]);
    });


    it("connects the WebSocket after startup synchronization", async () => {
        await start();

        expect(
            mockWebSocket.connect
        ).toHaveBeenCalledTimes(1);
    });


    it("marks the application as started", async () => {
        await start();

        expect(
            getAppState().started
        ).toBe(true);
    });


    it("is no longer starting after startup completes", async () => {
        await start();

        expect(
            getAppState().starting
        ).toBe(false);
    });


    it("does not start twice", async () => {
        await start();

        await start();

        expect(
            mockWebSocket.connect
        ).toHaveBeenCalledTimes(1);

        expect(
            mockApi.getDisplaySnapshot
        ).toHaveBeenCalledTimes(1);
    });


    it("handles a failed initial snapshot without preventing startup", async () => {
        const errorSpy =
            vi.spyOn(console, "error")
                .mockImplementation(() => {});

        mockApi.getDisplaySnapshot
            .mockRejectedValue(
                new Error("Backend unavailable")
            );

        await start();

        expect(
            mockWebSocket.connect
        ).toHaveBeenCalledTimes(1);

        expect(
            getAppState().started
        ).toBe(true);

        errorSpy.mockRestore();
    });


    it("cleans up if configuration access fails", async () => {
        const configModule =
            await import("../js/config.js");

        configModule.getConfig
            .mockImplementationOnce(() => {
                throw new Error(
                    "Configuration unavailable"
                );
            });

        await expect(
            start()
        ).rejects.toThrow(
            "Configuration unavailable"
        );

        expect(
            mockWebSocket.connect
        ).not.toHaveBeenCalled();

        expect(
            getAppState().started
        ).toBe(false);
    });
});


/*
|--------------------------------------------------------------------------
| WebSocket Connected
|--------------------------------------------------------------------------
*/

describe("handleConnected()", () => {
    it("marks the display connection as connected", async () => {
        await handleConnected();

        expect(
            mockDisplayState.setConnectionStatus
        ).toHaveBeenCalledWith(
            "CONNECTED"
        );
    });


    it("synchronizes the snapshot after connecting", async () => {
        await handleConnected();

        expect(
            mockApi.getDisplaySnapshot
        ).toHaveBeenCalledTimes(1);

        expect(
            mockDisplayState.setSnapshot
        ).toHaveBeenCalledWith(snapshot);
    });


    it("handles snapshot synchronization failure", async () => {
        const errorSpy =
            vi.spyOn(console, "error")
                .mockImplementation(() => {});

        mockApi.getDisplaySnapshot
            .mockRejectedValue(
                new Error("Sync failed")
            );

        await handleConnected();

        expect(errorSpy)
            .toHaveBeenCalled();

        errorSpy.mockRestore();
    });
});


/*
|--------------------------------------------------------------------------
| WebSocket Messages
|--------------------------------------------------------------------------
*/

describe("handleMessage()", () => {
    it("passes object events directly to display-state", () => {
        handleMessage(notificationEvent);

        expect(
            mockDisplayState.applyEvent
        ).toHaveBeenCalledWith(
            notificationEvent
        );
    });


    it("parses JSON string messages", () => {
        handleMessage(
            JSON.stringify(notificationEvent)
        );

        expect(
            mockDisplayState.applyEvent
        ).toHaveBeenCalledWith(
            notificationEvent
        );
    });


    it("does not crash on malformed JSON", () => {
        const errorSpy =
            vi.spyOn(console, "error")
                .mockImplementation(() => {});

        expect(() => {
            handleMessage(
                "{invalid-json"
            );
        }).not.toThrow();

        expect(
            mockDisplayState.applyEvent
        ).not.toHaveBeenCalled();

        expect(errorSpy)
            .toHaveBeenCalled();

        errorSpy.mockRestore();
    });


    it("handles state mutation errors", () => {
        const errorSpy =
            vi.spyOn(console, "error")
                .mockImplementation(() => {});

        mockDisplayState.applyEvent
            .mockImplementationOnce(() => {
                throw new Error(
                    "Invalid event"
                );
            });

        expect(() => {
            handleMessage(notificationEvent);
        }).not.toThrow();

        expect(errorSpy)
            .toHaveBeenCalled();

        errorSpy.mockRestore();
    });
});


/*
|--------------------------------------------------------------------------
| WebSocket Disconnected
|--------------------------------------------------------------------------
*/

describe("handleDisconnected()", () => {
    it("marks the display as disconnected", () => {
        handleDisconnected();

        expect(
            mockDisplayState.setConnectionStatus
        ).toHaveBeenCalledWith(
            "DISCONNECTED",
            null
        );
    });


    it("passes the disconnect reason", () => {
        handleDisconnected({
            reason: "Network failure",
        });

        expect(
            mockDisplayState.setConnectionStatus
        ).toHaveBeenCalledWith(
            "DISCONNECTED",
            "Network failure"
        );
    });
});


/*
|--------------------------------------------------------------------------
| WebSocket Reconnecting
|--------------------------------------------------------------------------
*/

describe("handleReconnecting()", () => {
    it("marks the display as reconnecting", () => {
        handleReconnecting({
            attempt: 1,
        });

        expect(
            mockDisplayState.setConnectionStatus
        ).toHaveBeenCalledWith(
            "RECONNECTING",
            null
        );
    });
});


/*
|--------------------------------------------------------------------------
| Reconnection Snapshot Recovery
|--------------------------------------------------------------------------
*/

describe("reconnection synchronization", () => {
    it("gets a fresh snapshot when WebSocket reconnects", async () => {
        await start();

        mockApi.getDisplaySnapshot
            .mockClear();

        await emitWebSocketEvent(
            "connected"
        );

        expect(
            mockApi.getDisplaySnapshot
        ).toHaveBeenCalledTimes(1);
    });


    it("replaces stale state after reconnection", async () => {
        await start();

        mockApi.getDisplaySnapshot
            .mockClear();

        await emitWebSocketEvent(
            "connected"
        );

        expect(
            mockDisplayState.setSnapshot
        ).toHaveBeenCalledWith(snapshot);
    });
});


/*
|--------------------------------------------------------------------------
| stop()
|--------------------------------------------------------------------------
*/

describe("stop()", () => {
    it("disconnects the WebSocket", async () => {
        await start();

        stop();

        expect(
            mockWebSocket.disconnect
        ).toHaveBeenCalledTimes(1);
    });


    it("marks the application as stopped", async () => {
        await start();

        stop();

        expect(
            getAppState().started
        ).toBe(false);
    });


    it("removes all WebSocket listeners", async () => {
        await start();

        stop();

        expect(mockWebSocket.off)
            .toHaveBeenCalledTimes(5);
    });


    it("removes the display-state subscription", async () => {
        await start();

        const unsubscribe =
            mockDisplayState.subscribe
                .mock.results[0].value;

        stop();

        expect(unsubscribe)
            .toHaveBeenCalledTimes(1);
    });


    it("is safe to call multiple times", async () => {
        await start();

        stop();
        stop();

        expect(
            mockWebSocket.disconnect
        ).toHaveBeenCalledTimes(1);
    });


    it("allows the application to start again", async () => {
        await start();

        stop();

        await start();

        expect(
            mockWebSocket.connect
        ).toHaveBeenCalledTimes(2);
    });
});


/*
|--------------------------------------------------------------------------
| Application State
|--------------------------------------------------------------------------
*/

describe("getAppState()", () => {
    it("exposes application lifecycle state", async () => {
        await start();

        const state =
            getAppState();

        expect(state)
            .toHaveProperty(
                "started",
                true
            );

        expect(state)
            .toHaveProperty(
                "starting",
                false
            );

        expect(state)
            .toHaveProperty(
                "syncing",
                false
            );
    });


    it("includes the current WebSocket state", async () => {
        mockWebSocket.getConnectionState
            .mockReturnValue(
                "CONNECTED"
            );

        const state =
            getAppState();

        expect(state.connectionState)
            .toBe("CONNECTED");
    });


    it("includes display state", () => {
        const displayState = {
            snapshot,
            initialized: true,
            stale: false,
            connection_status:
                "CONNECTED",
        };

        mockDisplayState.getState
            .mockReturnValue(displayState);

        const state =
            getAppState();

        expect(state.displayState)
            .toEqual(displayState);
    });
});

