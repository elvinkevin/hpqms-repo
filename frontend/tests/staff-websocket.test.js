import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";

import {
    STAFF_SOCKET_STATE,
    connect,
    disconnect,
    send,
    on,
    off,
    isConnected,
    getConnectionState,
    getTransportInfo,
} from "../js/staff-websocket.js";

import * as configModule from "../js/config.js";


/* ==========================================================================
   Mock Configuration
   ========================================================================== */

vi.mock("../js/config.js", () => ({
    getConfig: vi.fn(() => ({
        backend: {
            websocketUrl: "ws://localhost:8000/ws",
            connectionTimeoutMs: 1000,
        },

        reconnect: {
            initialDelayMs: 100,
            maxDelayMs: 1000,
            backoffMultiplier: 2,
            maxAttempts: 3,
        },
    })),
}));


/* ==========================================================================
   Mock WebSocket
   ========================================================================== */

class MockWebSocket {
    static instances = [];

    static CONNECTING = 0;
    static OPEN = 1;
    static CLOSING = 2;
    static CLOSED = 3;

    constructor(url) {
        this.url = url;
        this.readyState = MockWebSocket.CONNECTING;

        this.onopen = null;
        this.onmessage = null;
        this.onerror = null;
        this.onclose = null;

        MockWebSocket.instances.push(this);
    }

    send(payload) {
        this.lastSentPayload = payload;
    }

    close() {
        this.readyState = MockWebSocket.CLOSED;

        if (this.onclose) {
            this.onclose({
                code: 1000,
                reason: "",
                wasClean: true,
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

    fail(event = {}) {
        if (this.onerror) {
            this.onerror(event);
        }
    }

    closeUnexpectedly(
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


/* ==========================================================================
   Test Setup
   ========================================================================== */

beforeEach(() => {
    vi.useFakeTimers();

    MockWebSocket.instances = [];

    globalThis.WebSocket = MockWebSocket;

    vi.clearAllMocks();

    disconnect();
});


afterEach(() => {
    disconnect();

    vi.useRealTimers();

    delete globalThis.WebSocket;
});


function getSocket() {
    return MockWebSocket.instances[
        MockWebSocket.instances.length - 1
    ];
}


/* ==========================================================================
   Initial State
   ========================================================================== */

describe("initial state", () => {

    it("starts disconnected", () => {
        expect(
            getConnectionState()
        ).toBe(
            STAFF_SOCKET_STATE.DISCONNECTED
        );
    });


    it("reports not connected initially", () => {
        expect(isConnected()).toBe(false);
    });


    it("does not expose a socket instance through transport info", () => {
        const info = getTransportInfo();

        expect(info).not.toHaveProperty("socket");
    });

});


/* ==========================================================================
   connect()
   ========================================================================== */

describe("connect()", () => {

    it("creates a WebSocket using the configured URL", () => {
        connect();

        expect(
            MockWebSocket.instances
        ).toHaveLength(1);

        expect(
            getSocket().url
        ).toBe(
            "ws://localhost:8000/ws"
        );
    });


    it("changes state to CONNECTING", () => {
        connect();

        expect(
            getConnectionState()
        ).toBe(
            STAFF_SOCKET_STATE.CONNECTING
        );
    });


    it("does not create duplicate connections while connecting", () => {
        connect();
        connect();

        expect(
            MockWebSocket.instances
        ).toHaveLength(1);
    });


    it("does not create duplicate connections when already connected", () => {
        connect();

        const socket = getSocket();

        socket.open();

        connect();

        expect(
            MockWebSocket.instances
        ).toHaveLength(1);
    });

});


/* ==========================================================================
   Successful Connection
   ========================================================================== */

describe("successful connection", () => {

    it("changes state to CONNECTED", () => {
        connect();

        getSocket().open();

        expect(
            getConnectionState()
        ).toBe(
            STAFF_SOCKET_STATE.CONNECTED
        );
    });


    it("reports connected through isConnected()", () => {
        connect();

        getSocket().open();

        expect(isConnected()).toBe(true);
    });


    it("emits the connected event", () => {
        const listener = vi.fn();

        on("connected", listener);

        connect();
        getSocket().open();

        expect(listener).toHaveBeenCalledTimes(1);
    });


    it("resets reconnect attempts after successful connection", () => {
        connect();

        getSocket().closeUnexpectedly();

        expect(
            getTransportInfo().reconnectAttempts
        ).toBe(1);

        vi.advanceTimersByTime(100);

        const reconnectingSocket = getSocket();

        reconnectingSocket.open();

        expect(
            getTransportInfo().reconnectAttempts
        ).toBe(0);
    });

});


/* ==========================================================================
   Incoming Messages
   ========================================================================== */

describe("incoming messages", () => {

    it("parses valid JSON messages before emitting them", () => {
        const listener = vi.fn();

        on("message", listener);

        connect();

        const socket = getSocket();

        socket.open();

        socket.receive(
            JSON.stringify({
                event_type: "TOKEN_CALLED",
                token_number: "W-101",
            })
        );

        expect(listener).toHaveBeenCalledTimes(1);

        expect(listener).toHaveBeenCalledWith({
            event_type: "TOKEN_CALLED",
            token_number: "W-101",
        });
    });


    it("preserves the complete event payload", () => {
        const listener = vi.fn();

        on("message", listener);

        connect();

        const socket = getSocket();

        socket.open();

        const payload = {
            event_id: "event-1",
            event_type: "TOKEN_CALLED",
            token_number: "W-101",
            department_id: "dept-1",
            department_name: "Reception",
            priority: "HIGH",
            service_point: "Room 1",
        };

        socket.receive(
            JSON.stringify(payload)
        );

        expect(listener).toHaveBeenCalledWith(
            payload
        );
    });


    it("emits an error when an incoming message contains invalid JSON", () => {
        const listener = vi.fn();

        on("error", listener);

        connect();

        const socket = getSocket();

        socket.open();

        socket.receive(
            "not valid JSON"
        );

        expect(listener).toHaveBeenCalledTimes(1);
    });

});


/* ==========================================================================
   send()
   ========================================================================== */

describe("send()", () => {

    it("sends a string unchanged", () => {
        connect();

        const socket = getSocket();

        socket.open();

        send("hello");

        expect(
            socket.lastSentPayload
        ).toBe("hello");
    });


    it("serializes objects as JSON", () => {
        connect();

        const socket = getSocket();

        socket.open();

        send({
            type: "PING",
            value: 123,
        });

        expect(
            socket.lastSentPayload
        ).toBe(
            JSON.stringify({
                type: "PING",
                value: 123,
            })
        );
    });


    it("rejects sending while disconnected", () => {
        expect(() => {
            send("hello");
        }).toThrow(
            "Cannot send message: Staff WebSocket is not connected"
        );
    });

});


/* ==========================================================================
   disconnect()
   ========================================================================== */

describe("disconnect()", () => {

    it("closes the active socket", () => {
        connect();

        const socket = getSocket();

        socket.open();

        const closeSpy = vi.spyOn(
            socket,
            "close"
        );

        disconnect();

        expect(
            closeSpy
        ).toHaveBeenCalledTimes(1);
    });


    it("changes state to DISCONNECTED", () => {
        connect();

        getSocket().open();

        disconnect();

        expect(
            getConnectionState()
        ).toBe(
            STAFF_SOCKET_STATE.DISCONNECTED
        );
    });


    it("reports not connected after disconnecting", () => {
        connect();

        getSocket().open();

        disconnect();

        expect(
            isConnected()
        ).toBe(false);
    });


    it("does not schedule reconnection after manual disconnect", () => {
        const reconnectingListener = vi.fn();

        on(
            "reconnecting",
            reconnectingListener
        );

        connect();

        getSocket().open();

        disconnect();

        vi.advanceTimersByTime(5000);

        expect(
            reconnectingListener
        ).not.toHaveBeenCalled();

        expect(
            MockWebSocket.instances
        ).toHaveLength(1);
    });


    it("is safe when already disconnected", () => {
        expect(() => {
            disconnect();
            disconnect();
        }).not.toThrow();
    });

});


/* ==========================================================================
   Reconnection
   ========================================================================== */

describe("reconnection", () => {

    it("emits disconnected when the socket closes", () => {
        const listener = vi.fn();

        on("disconnected", listener);

        connect();

        getSocket().open();

        getSocket().closeUnexpectedly(
            1006,
            "Connection lost"
        );

        expect(listener).toHaveBeenCalledTimes(1);

        expect(listener).toHaveBeenCalledWith({
            code: 1006,
            reason: "Connection lost",
            wasClean: false,
        });
    });


    it("enters RECONNECTING after an unexpected disconnect", () => {
        connect();

        getSocket().open();

        getSocket().closeUnexpectedly();

        expect(
            getConnectionState()
        ).toBe(
            STAFF_SOCKET_STATE.RECONNECTING
        );
    });


    it("emits reconnecting information", () => {
        const listener = vi.fn();

        on("reconnecting", listener);

        connect();

        getSocket().open();

        getSocket().closeUnexpectedly();

        expect(listener).toHaveBeenCalledTimes(1);

        expect(listener).toHaveBeenCalledWith({
            attempt: 1,
            delayMs: 100,
        });
    });


    it("waits before reconnecting", () => {
        connect();

        getSocket().open();

        getSocket().closeUnexpectedly();

        expect(
            MockWebSocket.instances
        ).toHaveLength(1);

        vi.advanceTimersByTime(99);

        expect(
            MockWebSocket.instances
        ).toHaveLength(1);

        vi.advanceTimersByTime(1);

        expect(
            MockWebSocket.instances
        ).toHaveLength(2);
    });


    it("uses exponential backoff", () => {
        connect();

        getSocket().open();

        getSocket().closeUnexpectedly();

        expect(
            getTransportInfo().reconnectAttempts
        ).toBe(1);

        vi.advanceTimersByTime(100);

        const secondSocket = getSocket();

        secondSocket.closeUnexpectedly();

        expect(
            getTransportInfo().reconnectAttempts
        ).toBe(2);

        vi.advanceTimersByTime(199);

        expect(
            MockWebSocket.instances
        ).toHaveLength(2);

        vi.advanceTimersByTime(1);

        expect(
            MockWebSocket.instances
        ).toHaveLength(3);
    });


    it("does not exceed the configured maximum attempts", () => {
        connect();

        getSocket().open();

        for (let attempt = 1; attempt <= 3; attempt++) {
            getSocket().closeUnexpectedly();

            vi.advanceTimersByTime(
                Math.min(
                    100 * Math.pow(2, attempt - 1),
                    1000
                )
            );
        }

        expect(
            getTransportInfo().reconnectAttempts
        ).toBe(3);

        expect(
            getConnectionState()
        ).toBe(
            STAFF_SOCKET_STATE.DISCONNECTED
        );
    });


   it("prevents automatic reconnection after manual disconnect", () => {
    connect();

    const socket = WebSocket.instances[0];

    socket.onopen();

    // Turn the close method into a trackable spy before calling disconnect
    vi.spyOn(socket, 'close');

    disconnect();

    expect(getConnectionState())
        .toBe(STAFF_SOCKET_STATE.DISCONNECTED);

    // This assertion will now pass successfully
    expect(socket.close)
        .toHaveBeenCalled();

    vi.advanceTimersByTime(100000);

    expect(WebSocket.instances)
        .toHaveLength(1);
});

});


/* ==========================================================================
   Connection Timeout
   ========================================================================== */

describe("connection timeout", () => {

    it("closes a connection that does not open in time", () => {
        connect();

        const socket = getSocket();

        const closeSpy = vi.spyOn(
            socket,
            "close"
        );

        vi.advanceTimersByTime(1000);

        expect(
            closeSpy
        ).toHaveBeenCalledTimes(1);
    });


    it("emits an error when connection times out", () => {
        const listener = vi.fn();

        on("error", listener);

        connect();

        vi.advanceTimersByTime(1000);

        expect(
            listener
        ).toHaveBeenCalledTimes(1);

        expect(
            listener.mock.calls[0][0]
        ).toBeInstanceOf(Error);

        expect(
            listener.mock.calls[0][0].message
        ).toBe(
            "Staff WebSocket connection timed out"
        );
    });

});


/* ==========================================================================
   Event Listeners
   ========================================================================== */

describe("event listeners", () => {

    it("allows listeners to be registered", () => {
        const listener = vi.fn();

        on("connected", listener);

        connect();
        getSocket().open();

        expect(listener).toHaveBeenCalledTimes(1);
    });


    it("allows listeners to be removed", () => {
        const listener = vi.fn();

        on("connected", listener);

        off("connected", listener);

        connect();
        getSocket().open();

        expect(listener).not.toHaveBeenCalled();
    });


    it("returns an unsubscribe function from on()", () => {
        const listener = vi.fn();

        const unsubscribe =
            on("connected", listener);

        unsubscribe();

        connect();
        getSocket().open();

        expect(listener).not.toHaveBeenCalled();
    });


    it("isolates listener errors", () => {
        const failingListener = vi.fn(() => {
            throw new Error("Listener failed");
        });

        const workingListener = vi.fn();

        const consoleSpy = vi
            .spyOn(console, "error")
            .mockImplementation(() => {});

        on(
            "connected",
            failingListener
        );

        on(
            "connected",
            workingListener
        );

        connect();
        getSocket().open();

        expect(
            failingListener
        ).toHaveBeenCalledTimes(1);

        expect(
            workingListener
        ).toHaveBeenCalledTimes(1);

        consoleSpy.mockRestore();
    });


    it("rejects non-function listeners", () => {
        expect(() => {
            on("connected", null);
        }).toThrow(
            "Staff WebSocket listener must be a function"
        );
    });



    it("unsubscribe removes a message listener", () => {
    const listener = vi.fn();

    const unsubscribe = on("message", listener);

    connect();

    const socket = WebSocket.instances[0];

    socket.onmessage({
        data: JSON.stringify({
            event_type: "TOKEN_CALLED",
        }),
    });

    expect(listener).toHaveBeenCalledTimes(1);

    unsubscribe();

    socket.onmessage({
        data: JSON.stringify({
            event_type: "TOKEN_COMPLETED",
        }),
    });

    expect(listener).toHaveBeenCalledTimes(1);
    });


it("forwards different queue events without interpreting them", () => {
    const listener = vi.fn();

    on("message", listener);

    connect();

    const socket = WebSocket.instances[0];

    const events = [
        {
            event_type: "TOKEN_CALLED",
            token_number: "W-101",
        },
        {
            event_type: "TOKEN_SERVICE_STARTED",
            token_number: "W-101",
        },
        {
            event_type: "TOKEN_COMPLETED",
            token_number: "W-101",
        },
        {
            event_type: "TOKEN_NO_SHOW",
            token_number: "W-102",
        },
        {
            event_type: "TOKEN_REQUEUED",
            token_number: "W-102",
        },
        {
            event_type: "QUEUE_UPDATED",
            department_id: "dept-001",
        },
    ];

    for (const event of events) {
        socket.onmessage({
            data: JSON.stringify(event),
        });
    }

    expect(listener).toHaveBeenCalledTimes(events.length);

    events.forEach((event, index) => {
        expect(listener.mock.calls[index][0])
            .toEqual(event);
    });
});
    
});


/* ==========================================================================
   Transport Diagnostics
   ========================================================================== */

describe("getTransportInfo()", () => {

    it("reports the current connection state", () => {
        expect(
            getTransportInfo().state
        ).toBe(
            STAFF_SOCKET_STATE.DISCONNECTED
        );

        connect();

        expect(
            getTransportInfo().state
        ).toBe(
            STAFF_SOCKET_STATE.CONNECTING
        );
    });


    it("reports connection status accurately", () => {
        connect();

        expect(
            getTransportInfo().connected
        ).toBe(false);

        getSocket().open();

        expect(
            getTransportInfo().connected
        ).toBe(true);

        disconnect();

        expect(
            getTransportInfo().connected
        ).toBe(false);
    });


    it("reports whether reconnection is scheduled", () => {
        connect();

        getSocket().open();

        expect(
            getTransportInfo().reconnectScheduled
        ).toBe(false);

        getSocket().closeUnexpectedly();

        expect(
            getTransportInfo().reconnectScheduled
        ).toBe(true);

        vi.advanceTimersByTime(100);

        expect(
            getTransportInfo().reconnectScheduled
        ).toBe(false);
    });

});


/* ==========================================================================
   Message Handling
   ========================================================================== */

describe("incoming messages", () => {
    it("emits a parsed payload through the message event", () => {
        const messageListener = vi.fn();

        on("message", messageListener);

        connect();

        const socket = getSocket();

        socket.open();

        socket.receive(
            JSON.stringify({
                event_type: "TOKEN_CALLED",
                queue_entry_id: "queue-1",
                assigned_staff_id: "staff-1",
            })
        );

        expect(messageListener).toHaveBeenCalledTimes(1);

        expect(messageListener).toHaveBeenCalledWith({
            event_type: "TOKEN_CALLED",
            queue_entry_id: "queue-1",
            assigned_staff_id: "staff-1",
        });
    });


    it("does not emit a message event for invalid JSON", () => {
        const messageListener = vi.fn();
        const errorListener = vi.fn();

        on("message", messageListener);
        on("error", errorListener);

        connect();

        const socket = getSocket();

        socket.open();

        socket.receive("not valid json");

        expect(messageListener).not.toHaveBeenCalled();
        expect(errorListener).toHaveBeenCalledTimes(1);
    });


    it("preserves the complete server event payload", () => {
        const messageListener = vi.fn();

        on("message", messageListener);

        connect();

        const socket = getSocket();

        socket.open();

        const event = {
            event_type: "TOKEN_NO_SHOW",
            queue_entry_id: "queue-42",
            assigned_staff_id: "staff-7",
            timestamp: "2026-08-17T10:00:00Z",
            metadata: {
                reason: "patient_not_present",
            },
        };

        socket.receive(JSON.stringify(event));

        expect(messageListener).toHaveBeenCalledWith(event);
    });
});