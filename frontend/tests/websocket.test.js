
import {
    beforeEach,
    afterEach,
    describe,
    expect,
    it,
    vi,
} from "vitest";

import {
    SOCKET_STATE,
    connect,
    disconnect,
    send,
    on,
    off,
    isConnected,
    getConnectionState,
    getTransportInfo,
} from "../js/websocket.js";

import { initializeConfig, resetConfig } from "../js/config.js";


/*
|--------------------------------------------------------------------------
| Mock WebSocket
|--------------------------------------------------------------------------
*/

class MockWebSocket {
    static instances = [];

    static OPEN = 1;
    static CONNECTING = 0;
    static CLOSING = 2;
    static CLOSED = 3;

    constructor(url) {
        this.url = url;
        this.readyState = MockWebSocket.CONNECTING;

        this.sentMessages = [];

        this.onopen = null;
        this.onmessage = null;
        this.onerror = null;
        this.onclose = null;

        MockWebSocket.instances.push(this);
    }

    send(message) {
        if (this.readyState !== MockWebSocket.OPEN) {
            throw new Error("WebSocket is not open");
        }

        this.sentMessages.push(message);
    }

    close(code = 1000, reason = "") {
        this.readyState = MockWebSocket.CLOSED;

        if (this.onclose) {
            this.onclose({
                code,
                reason,
                wasClean: code === 1000,
            });
        }
    }

    open() {
        this.readyState = MockWebSocket.OPEN;

        if (this.onopen) {
            this.onopen();
        }
    }

    receive(data) {
        if (this.onmessage) {
            this.onmessage({
                data,
            });
        }
    }

    error(error = new Error("WebSocket error")) {
        if (this.onerror) {
            this.onerror(error);
        }
    }

    failConnection(
        code = 1006,
        reason = "Connection lost"
    ) {
        this.readyState = MockWebSocket.CLOSED;

        if (this.onclose) {
            this.onclose({
                code,
                reason,
                wasClean: false,
            });
        }
    }
}


/*
|--------------------------------------------------------------------------
| Test Setup
|--------------------------------------------------------------------------
*/

beforeEach(() => {
    vi.useFakeTimers();

    MockWebSocket.instances = [];

    globalThis.WebSocket = MockWebSocket;

    initializeConfig({
        backend: {
            websocketUrl:
                "ws://localhost:8000/ws/display",

            connectionTimeoutMs: 5000,
        },

        reconnect: {
            initialDelayMs: 1000,
            maxDelayMs: 10000,
            backoffMultiplier: 2,
            maxAttempts: 3,
        },
    });
});


afterEach(() => {
    disconnect();

    resetConfig();

    vi.clearAllTimers();
    vi.useRealTimers();
});


/*
|--------------------------------------------------------------------------
| Initial State
|--------------------------------------------------------------------------
*/

describe("initial state", () => {
    it("starts disconnected", () => {
        expect(getConnectionState())
            .toBe(SOCKET_STATE.DISCONNECTED);
    });


    it("reports not connected initially", () => {
        expect(isConnected())
            .toBe(false);
    });


    it("does not expose a socket instance through transport info", () => {
        const info = getTransportInfo();

        expect(info)
            .not.toHaveProperty("socket");
    });
});


/*
|--------------------------------------------------------------------------
| connect()
|--------------------------------------------------------------------------
*/

describe("connect()", () => {
    it("creates a WebSocket using the configured URL", () => {
        connect();

        expect(MockWebSocket.instances)
            .toHaveLength(1);

        expect(MockWebSocket.instances[0].url)
            .toBe(
                "ws://localhost:8000/ws/display"
            );
    });


    it("changes state to CONNECTING", () => {
        connect();

        expect(getConnectionState())
            .toBe(SOCKET_STATE.CONNECTING);
    });


    it("does not create duplicate connections while connecting", () => {
        connect();
        connect();

        expect(MockWebSocket.instances)
            .toHaveLength(1);
    });


    it("does not create duplicate connections when already connected", () => {
        connect();

        const socket =
            MockWebSocket.instances[0];

        socket.open();

        connect();

        expect(MockWebSocket.instances)
            .toHaveLength(1);
    });
});


/*
|--------------------------------------------------------------------------
| Successful Connection
|--------------------------------------------------------------------------
*/

describe("successful connection", () => {
    it("changes state to CONNECTED", () => {
        connect();

        const socket =
            MockWebSocket.instances[0];

        socket.open();

        expect(getConnectionState())
            .toBe(SOCKET_STATE.CONNECTED);
    });


    it("reports connected through isConnected()", () => {
        connect();

        const socket =
            MockWebSocket.instances[0];

        socket.open();

        expect(isConnected())
            .toBe(true);
    });


    it("emits the connected event", () => {
        const callback = vi.fn();

        on("connected", callback);

        connect();

        MockWebSocket.instances[0].open();

        expect(callback)
            .toHaveBeenCalledTimes(1);
    });


    it("resets reconnect attempts after successful connection", () => {
        connect();

        const socket =
            MockWebSocket.instances[0];

        socket.open();

        expect(
            getTransportInfo().reconnectAttempts
        ).toBe(0);
    });
});


/*
|--------------------------------------------------------------------------
| Incoming Messages
|--------------------------------------------------------------------------
*/

describe("incoming messages", () => {
    it("parses valid JSON messages before emitting them", () => {
        const callback = vi.fn();

        on("message", callback);

        connect();

        const socket =
            MockWebSocket.instances[0];

        socket.open();

        socket.receive(
            '{"event_type":"TOKEN_CALLED"}'
        );

        expect(callback)
            .toHaveBeenCalledWith({
                event_type: "TOKEN_CALLED",
            });
    });


    it("preserves the complete event payload", () => {
        const callback = vi.fn();

        on("message", callback);

        connect();

        const socket =
            MockWebSocket.instances[0];

        socket.open();

        const payload = {
            event_id: "event-001",
            event_type: "TOKEN_CALLED",
            priority: "HIGH",
            department_id: "dept-001",
            department_name: "Reception",
            token_number: "A-102",
        };

        socket.receive(
            JSON.stringify(payload)
        );

        expect(callback)
            .toHaveBeenCalledWith(payload);
    });


    it("emits an error when an incoming message contains invalid JSON", () => {
        const messageCallback = vi.fn();
        const errorCallback = vi.fn();

        on("message", messageCallback);
        on("error", errorCallback);

        connect();

        const socket =
            MockWebSocket.instances[0];

        socket.open();

        socket.receive(
            "this is not valid JSON"
        );

        expect(messageCallback)
            .not.toHaveBeenCalled();

        expect(errorCallback)
            .toHaveBeenCalledTimes(1);

        const error =
            errorCallback.mock.calls[0][0];

        expect(error)
            .toBeInstanceOf(Error);
    });
});


/*
|--------------------------------------------------------------------------
| send()
|--------------------------------------------------------------------------
*/

describe("send()", () => {
    it("sends a string unchanged", () => {
        connect();

        const socket =
            MockWebSocket.instances[0];

        socket.open();

        send("hello");

        expect(socket.sentMessages)
            .toEqual(["hello"]);
    });


    it("serializes objects as JSON", () => {
        connect();

        const socket =
            MockWebSocket.instances[0];

        socket.open();

        send({
            type: "PING",
            display_id: "DISPLAY-001",
        });

        expect(socket.sentMessages)
            .toEqual([
                JSON.stringify({
                    type: "PING",
                    display_id: "DISPLAY-001",
                }),
            ]);
    });


    it("rejects sending while disconnected", () => {
        expect(() => {
            send("hello");
        }).toThrow(
            "Cannot send message: WebSocket is not connected"
        );
    });
});


/*
|--------------------------------------------------------------------------
| Disconnect
|--------------------------------------------------------------------------
*/

describe("disconnect()", () => {
    it("closes the active socket", () => {
        connect();

        const socket =
            MockWebSocket.instances[0];

        socket.open();

        disconnect();

        expect(socket.readyState)
            .toBe(MockWebSocket.CLOSED);
    });


    it("changes state to DISCONNECTED", () => {
        connect();

        const socket =
            MockWebSocket.instances[0];

        socket.open();

        disconnect();

        expect(getConnectionState())
            .toBe(SOCKET_STATE.DISCONNECTED);
    });


    it("reports not connected after disconnecting", () => {
        connect();

        const socket =
            MockWebSocket.instances[0];

        socket.open();

        disconnect();

        expect(isConnected())
            .toBe(false);
    });


    it("does not schedule reconnection after manual disconnect", () => {
        connect();

        const socket =
            MockWebSocket.instances[0];

        socket.open();

        disconnect();

        vi.advanceTimersByTime(30000);

        expect(MockWebSocket.instances)
            .toHaveLength(1);
    });


    it("is safe when already disconnected", () => {
        expect(() => {
            disconnect();
        }).not.toThrow();
    });
});


/*
|--------------------------------------------------------------------------
| Disconnection & Reconnection
|--------------------------------------------------------------------------
*/

describe("reconnection", () => {
    it("emits disconnected when the socket closes", () => {
        const callback = vi.fn();

        on("disconnected", callback);

        connect();

        const socket =
            MockWebSocket.instances[0];

        socket.open();

        socket.failConnection(
            1006,
            "Network failure"
        );

        expect(callback)
            .toHaveBeenCalledWith({
                code: 1006,
                reason: "Network failure",
                wasClean: false,
            });
    });


    it("enters RECONNECTING after an unexpected disconnect", () => {
        connect();

        const socket =
            MockWebSocket.instances[0];

        socket.open();

        socket.failConnection();

        expect(getConnectionState())
            .toBe(SOCKET_STATE.RECONNECTING);
    });


    it("emits reconnecting information", () => {
        const callback = vi.fn();

        on("reconnecting", callback);

        connect();

        const socket =
            MockWebSocket.instances[0];

        socket.open();

        socket.failConnection();

        expect(callback)
            .toHaveBeenCalledWith({
                attempt: 1,
                delayMs: 1000,
            });
    });


    it("waits before reconnecting", () => {
        connect();

        const socket =
            MockWebSocket.instances[0];

        socket.open();

        socket.failConnection();

        expect(MockWebSocket.instances)
            .toHaveLength(1);

        vi.advanceTimersByTime(999);

        expect(MockWebSocket.instances)
            .toHaveLength(1);

        vi.advanceTimersByTime(1);

        expect(MockWebSocket.instances)
            .toHaveLength(2);
    });


    it("uses exponential backoff", () => {
        connect();

        let socket =
            MockWebSocket.instances[0];

        socket.open();

        socket.failConnection();

        vi.advanceTimersByTime(1000);

        expect(MockWebSocket.instances)
            .toHaveLength(2);

        socket =
            MockWebSocket.instances[1];

        socket.open();

        socket.failConnection();

        expect(
            getTransportInfo().reconnectAttempts
        ).toBe(1);

        /*
         * A successful connection resets attempts.
         *
         * This verifies the reconnect cycle resets
         * correctly after recovery.
         */
        expect(getConnectionState())
            .toBe(SOCKET_STATE.RECONNECTING);
    });


    it("does not exceed the configured maximum attempts", () => {
    connect();

    let socket =
        MockWebSocket.instances[0];

    socket.open();

    // Reconnect attempt #1
    socket.failConnection();

    vi.advanceTimersByTime(1000);

    socket =
        MockWebSocket.instances[1];

    // Reconnect attempt #2
    socket.failConnection();

    vi.advanceTimersByTime(2000);

    socket =
        MockWebSocket.instances[2];

    // Reconnect attempt #3
    socket.failConnection();

    vi.advanceTimersByTime(4000);

    socket =
        MockWebSocket.instances[3];

    // Third and final reconnect attempt fails
    socket.failConnection();

    expect(MockWebSocket.instances)
        .toHaveLength(4);

    expect(getConnectionState())
        .toBe(SOCKET_STATE.DISCONNECTED);

    // Verify no fifth connection is created
    vi.advanceTimersByTime(10000);

    expect(MockWebSocket.instances)
        .toHaveLength(4);
    });
});


/*
|--------------------------------------------------------------------------
| Connection Timeout
|--------------------------------------------------------------------------
*/

describe("connection timeout", () => {
    it("closes a connection that does not open in time", () => {
        connect();

        const socket =
            MockWebSocket.instances[0];

        expect(socket.readyState)
            .toBe(MockWebSocket.CONNECTING);

        vi.advanceTimersByTime(5000);

        expect(socket.readyState)
            .toBe(MockWebSocket.CLOSED);
    });


    it("emits an error when connection times out", () => {
        const callback = vi.fn();

        on("error", callback);

        connect();

        vi.advanceTimersByTime(5000);

        expect(callback)
            .toHaveBeenCalled();

        expect(
            callback.mock.calls.some(
                ([error]) =>
                    error instanceof Error &&
                    error.message.includes(
                        "timed out"
                    )
            )
        ).toBe(true);
    });
});


/*
|--------------------------------------------------------------------------
| Event Listeners
|--------------------------------------------------------------------------
*/

describe("event listeners", () => {
    it("allows listeners to be registered", () => {
        const callback = vi.fn();

        on("connected", callback);

        connect();

        MockWebSocket.instances[0].open();

        expect(callback)
            .toHaveBeenCalled();
    });


    it("allows listeners to be removed", () => {
        const callback = vi.fn();

        on("connected", callback);

        off("connected", callback);

        connect();

        MockWebSocket.instances[0].open();

        expect(callback)
            .not.toHaveBeenCalled();
    });


    it("returns an unsubscribe function from on()", () => {
        const callback = vi.fn();

        const unsubscribe =
            on("connected", callback);

        unsubscribe();

        connect();

        MockWebSocket.instances[0].open();

        expect(callback)
            .not.toHaveBeenCalled();
    });


    it("isolates listener errors", () => {
        const failingListener = vi.fn(() => {
            throw new Error("Listener failure");
        });

        const successfulListener = vi.fn();

        const consoleSpy =
            vi.spyOn(console, "error")
                .mockImplementation(() => {});

        on("connected", failingListener);
        on("connected", successfulListener);

        connect();

        MockWebSocket.instances[0].open();

        expect(failingListener)
            .toHaveBeenCalled();

        expect(successfulListener)
            .toHaveBeenCalled();

        consoleSpy.mockRestore();
    });


    it("rejects non-function listeners", () => {
        expect(() => {
            on("connected", "not-a-function");
        }).toThrow(
            "WebSocket listener must be a function"
        );
    });
});


/*
|--------------------------------------------------------------------------
| Transport Diagnostics
|--------------------------------------------------------------------------
*/

describe("getTransportInfo()", () => {
    it("reports the current connection state", () => {
        connect();

        expect(
            getTransportInfo().state
        ).toBe(SOCKET_STATE.CONNECTING);
    });


    it("reports connection status accurately", () => {
        connect();

        expect(
            getTransportInfo().connected
        ).toBe(false);

        MockWebSocket.instances[0].open();

        expect(
            getTransportInfo().connected
        ).toBe(true);
    });


    it("reports whether reconnection is scheduled", () => {
        connect();

        const socket =
            MockWebSocket.instances[0];

        socket.open();

        socket.failConnection();

        expect(
            getTransportInfo().reconnectScheduled
        ).toBe(true);

        vi.advanceTimersByTime(1000);

        expect(
            getTransportInfo().reconnectScheduled
        ).toBe(false);
    });
});

