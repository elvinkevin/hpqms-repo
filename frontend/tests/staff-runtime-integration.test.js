import {
    describe,
    it,
    expect,
    beforeEach,
    afterEach,
    vi,
} from "vitest";


/* ==========================================================================
   API MOCKS
   ========================================================================== */

const mockApi = {
    login: vi.fn(),
    logout: vi.fn(),
    getDepartments: vi.fn(),
    getDepartmentQueue: vi.fn(),
    getDepartmentNoShowQueue: vi.fn(),
    callQueueEntry: vi.fn(),
    startQueueEntry: vi.fn(),
    completeQueueEntry: vi.fn(),
    markNoShowQueueEntry: vi.fn(),
    requeueQueueEntry: vi.fn(),
    getNextPatient: vi.fn(),
    getCurrentUser: vi.fn(),
};


/* ==========================================================================
   STAFF WEBSOCKET MOCK
   ========================================================================== */

const mockWebSocket = {
    connect: vi.fn(),
    disconnect: vi.fn(),
    on: vi.fn(),
    off: vi.fn(),
};


/* ==========================================================================
   MODULE MOCKS
   ========================================================================== */

vi.mock("../js/staff-api.js", () => mockApi);

vi.mock("../js/staff-websocket.js", () => ({
    connect: mockWebSocket.connect,
    disconnect: mockWebSocket.disconnect,
    on: mockWebSocket.on,
    off: mockWebSocket.off,
}));


/* ==========================================================================
   DOM
   ========================================================================== */

function createDashboardDOM() {
    document.body.innerHTML = `
        <section id="login-panel">
            <form id="login-form">
                <input id="employee-id">
                <input id="password">
                <div id="login-error"></div>
            </form>
        </section>

        <div id="dashboard-subtitle"></div>

        <button id="logout-button"></button>

        <section id="queue-panel"></section>

        <div id="queue-state"></div>

        <table id="queue-table">
            <tbody id="queue-body"></tbody>
        </table>

        <section id="current-patient-panel"></section>

        <div id="current-token"></div>
        <div id="current-status"></div>
        <div id="current-patient"></div>
        <div id="current-priority"></div>
        <div id="current-owner"></div>

        <button id="call-button"></button>
        <button id="start-button"></button>
        <button id="noshow-button"></button>
        <button id="complete-button"></button>

        <div id="action-error"></div>

        <section id="no-show-panel"></section>

        <table id="no-show-table">
            <tbody id="no-show-body"></tbody>
        </table>

        <div id="no-show-state"></div>
    `;
}


/* ==========================================================================
   TEST DATA
   ========================================================================== */

const departmentId = "dept-reception";

const currentUser = {
    staff_id: "staff-1",
    first_name: "John",
    last_name: "Receptionist",
    dept_id: departmentId,
};

const waitingEntry = {
    queue_entry_id: "queue-1",
    sequence_number: 101,
    status: "WAITING",
    priority: "NORMAL",
    assigned_staff_id: null,
    visit: {
        token_number: "W-101",
        patient: {
            first_name: "Jane",
            last_name: "Doe",
        },
    },
};

const calledEntry = {
    queue_entry_id: "queue-1",
    sequence_number: 101,
    status: "CALLED",
    priority: "NORMAL",
    assigned_staff_id: "staff-1",
    visit: {
        token_number: "W-101",
        patient: {
            first_name: "Jane",
            last_name: "Doe",
        },
    },
};


/* ==========================================================================
   STAFF MODULE
   ========================================================================== */

let staff;


beforeEach(async () => {
    vi.clearAllMocks();

    createDashboardDOM();

    mockApi.getCurrentUser.mockResolvedValue(currentUser);

    mockApi.getDepartmentQueue.mockResolvedValue([
        waitingEntry,
    ]);

    mockApi.getDepartmentNoShowQueue.mockResolvedValue([]);

    mockWebSocket.on.mockReset();
    mockWebSocket.off.mockReset();

    /*
     * staff.js initializes automatically when login-form exists.
     */
    vi.resetModules();

    staff = await import("../js/staff.js");
});


afterEach(() => {
    document.body.innerHTML = "";
});


/* ==========================================================================
   HELPERS
   ========================================================================== */

function getWebSocketHandler(eventName) {
    const subscription = mockWebSocket.on.mock.calls.find(
        ([name]) => name === eventName
    );

    return subscription?.[1];
}

async function initializeStaffSession() {
    mockApi.login.mockResolvedValue({});
    mockApi.getCurrentUser.mockResolvedValue(currentUser);

    const form = document.querySelector("#login-form");

    document.querySelector("#employee-id").value = "EMP-001";
    document.querySelector("#password").value = "password";

    await form.dispatchEvent(
        new Event("submit", {
            bubbles: true,
            cancelable: true,
        })
    );

    await vi.waitFor(() => {
        expect(mockWebSocket.connect).toHaveBeenCalled();
    });
}

/* ==========================================================================
   INTEGRATION TESTS
   ========================================================================== */

describe("Staff Dashboard integration", () => {

    describe("department initialization", () => {

        it("loads the current staff member and department queue", async () => {
    await initializeStaffSession();

    expect(mockApi.getDepartmentQueue)
        .toHaveBeenCalledWith(departmentId);

    expect(mockApi.getDepartmentNoShowQueue)
        .toHaveBeenCalledWith(departmentId);

    expect(
        document.querySelector("#queue-body").children.length
    ).toBe(1);
    });

    });


    describe("WebSocket integration", () => {

        it("registers the expected WebSocket listeners", async () => {
            /*
             * Trigger the login/department flow manually through the
             * exported refresh path isn't enough to start the socket.
             *
             * The dashboard starts WebSocket during identifyDepartment(),
             * which is reached through login.
             */

            mockApi.login.mockResolvedValue({});
            mockApi.getCurrentUser.mockResolvedValue(currentUser);

            const form = document.querySelector("#login-form");

            document.querySelector("#employee-id").value =
                "EMP-001";

            document.querySelector("#password").value =
                "password";

            await form.dispatchEvent(
                new Event("submit", {
                    bubbles: true,
                    cancelable: true,
                })
            );

            /*
             * Allow the async login chain to complete.
             */
            await vi.waitFor(() => {
                expect(mockWebSocket.connect)
                    .toHaveBeenCalled();
            });

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


        it("refreshes the queue when a department queue event arrives", async () => {
            /*
             * Establish the department context and socket.
             */
            mockApi.login.mockResolvedValue({});
            mockApi.getCurrentUser.mockResolvedValue(currentUser);

            const form = document.querySelector("#login-form");

            document.querySelector("#employee-id").value =
                "EMP-001";

            document.querySelector("#password").value =
                "password";

            await form.dispatchEvent(
                new Event("submit", {
                    bubbles: true,
                    cancelable: true,
                })
            );

            await vi.waitFor(() => {
                expect(mockWebSocket.connect)
                    .toHaveBeenCalled();
            });

            /*
             * Ignore the initial queue loading calls.
             */
            mockApi.getDepartmentQueue.mockClear();
            mockApi.getDepartmentNoShowQueue.mockClear();

            const messageHandler =
                getWebSocketHandler("message");

            expect(messageHandler).toBeTypeOf("function");

            await messageHandler({
                event_type: "TOKEN_CALLED",
                dept_id: departmentId,
                queue_entry_id: "queue-1",
            });

            expect(mockApi.getDepartmentQueue)
                .toHaveBeenCalledWith(departmentId);

            expect(mockApi.getDepartmentNoShowQueue)
                .toHaveBeenCalledWith(departmentId);
        });


        it("refreshes every staff dashboard when a patient is requeued", async () => {
            await initializeStaffSession();

            mockApi.getDepartmentQueue.mockClear();
            mockApi.getDepartmentNoShowQueue.mockClear();

            const messageHandler = getWebSocketHandler("message");

            await messageHandler({
                event_type: "TOKEN_REQUEUED",
                dept_id: departmentId,
                queue_entry_id: "queue-1",
            });

            expect(mockApi.getDepartmentQueue)
                .toHaveBeenCalledWith(departmentId);

            expect(mockApi.getDepartmentNoShowQueue)
                .toHaveBeenCalledWith(departmentId);
        });


        it("ignores queue events belonging to another department", async () => {
            mockApi.login.mockResolvedValue({});
            mockApi.getCurrentUser.mockResolvedValue(currentUser);

            const form = document.querySelector("#login-form");

            document.querySelector("#employee-id").value =
                "EMP-001";

            document.querySelector("#password").value =
                "password";

            await form.dispatchEvent(
                new Event("submit", {
                    bubbles: true,
                    cancelable: true,
                })
            );

            await vi.waitFor(() => {
                expect(mockWebSocket.connect)
                    .toHaveBeenCalled();
            });

            mockApi.getDepartmentQueue.mockClear();
            mockApi.getDepartmentNoShowQueue.mockClear();

            const messageHandler =
                getWebSocketHandler("message");

            await messageHandler({
                event_type: "TOKEN_CALLED",
                dept_id: "dept-other",
                queue_entry_id: "queue-999",
            });

            expect(mockApi.getDepartmentQueue)
                .not.toHaveBeenCalled();

            expect(mockApi.getDepartmentNoShowQueue)
                .not.toHaveBeenCalled();
        });


        it("accepts PATIENT_ROUTED events targeting the current department", async () => {
            mockApi.login.mockResolvedValue({});
            mockApi.getCurrentUser.mockResolvedValue(currentUser);

            const form = document.querySelector("#login-form");

            document.querySelector("#employee-id").value =
                "EMP-001";

            document.querySelector("#password").value =
                "password";

            await form.dispatchEvent(
                new Event("submit", {
                    bubbles: true,
                    cancelable: true,
                })
            );

            await vi.waitFor(() => {
                expect(mockWebSocket.connect)
                    .toHaveBeenCalled();
            });

            mockApi.getDepartmentQueue.mockClear();
            mockApi.getDepartmentNoShowQueue.mockClear();

            const messageHandler =
                getWebSocketHandler("message");

            await messageHandler({
                event_type: "PATIENT_ROUTED",
                source_dept_id: "dept-triage",
                target_dept_id: departmentId,
                queue_entry_id: "queue-2",
            });

            expect(mockApi.getDepartmentQueue)
                .toHaveBeenCalledWith(departmentId);
        });

    });


    describe("queue actions", () => {

        it("calls the backend-determined next patient when Call is performed", async () => {
    mockApi.getDepartmentQueue.mockResolvedValue([waitingEntry]);
    mockApi.getDepartmentNoShowQueue.mockResolvedValue([]);

    await initializeStaffSession();

    mockApi.getNextPatient.mockResolvedValue(waitingEntry);

    mockApi.callQueueEntry.mockResolvedValue({
        ...calledEntry,
    });

    mockApi.getDepartmentQueue.mockResolvedValue([calledEntry]);

    staff.selectQueueEntry(
        waitingEntry.queue_entry_id
    );

    await staff.performTransition("call");

    expect(mockApi.getNextPatient)
        .toHaveBeenCalledWith(departmentId);

    expect(mockApi.callQueueEntry)
        .toHaveBeenCalledWith(
            waitingEntry.queue_entry_id
        );
    });


        it("starts the selected patient", async () => {
            const entry = {
                ...calledEntry,
                status: "CALLED",
                assigned_staff_id: currentUser.staff_id,
            };

           
            await initializeStaffSession();

            mockApi.getDepartmentQueue
                .mockResolvedValue([entry]);

            await staff.refreshQueue();

            staff.selectQueueEntry(
                entry.queue_entry_id
            );

            await staff.performTransition("start");

            expect(mockApi.startQueueEntry)
                .toHaveBeenCalledWith(
                    entry.queue_entry_id
                );

            
        });


        it("marks the selected patient as no-show", async () => {
            const entry = {
                ...calledEntry,
                status: "CALLED",
                assigned_staff_id: currentUser.staff_id,
            };

            mockApi.getDepartmentQueue
                .mockResolvedValue([entry]);

            mockApi.markNoShowQueueEntry.mockResolvedValue({
                ...entry,
                status: "NO_SHOW",
            });

            await initializeStaffSession();

            mockApi.getDepartmentQueue
                .mockResolvedValue([entry]);

            await staff.refreshQueue();

            staff.selectQueueEntry(
                entry.queue_entry_id
            );

            await staff.performTransition("noshow");

            expect(mockApi.markNoShowQueueEntry)
                .toHaveBeenCalledWith(
                    entry.queue_entry_id
                );
        });


        it("completes the selected patient", async () => {
            const entry = {
                ...calledEntry,
                status: "IN_PROGRESS",
                assigned_staff_id: currentUser.staff_id,
            };

            mockApi.getDepartmentQueue
                .mockResolvedValue([entry]);

            mockApi.completeQueueEntry.mockResolvedValue({
                ...entry,
                status: "COMPLETED",
            });

            await initializeStaffSession();

            mockApi.getDepartmentQueue
                .mockResolvedValue([entry]);

            await staff.refreshQueue();

            staff.selectQueueEntry(
                entry.queue_entry_id
            );

            await staff.performTransition("complete");

            expect(mockApi.completeQueueEntry)
                .toHaveBeenCalledWith(
                    entry.queue_entry_id
                );
        });

    });


   describe("authorization and conflict handling", () => {

    it("handles a 403 ownership error", async () => {
        await initializeStaffSession();

        const entry = {
            ...calledEntry,
            status: "CALLED",
            assigned_staff_id: "staff-2",
        };

        mockApi.getDepartmentQueue.mockResolvedValue([entry]);

        const error = new Error("Patient belongs to another staff member");
        error.status = 403;

        mockApi.startQueueEntry.mockRejectedValue(error);

        await staff.refreshQueue();
        staff.selectQueueEntry(entry.queue_entry_id);

        await staff.performTransition("start");

        expect(
            document.querySelector("#action-error").textContent
        ).toContain("assigned to another staff member");
        expect(mockApi.getDepartmentQueue).toHaveBeenCalled();
    });

    it("handles a 409 active-patient conflict", async () => {
        await initializeStaffSession();

        const entry = {
            ...calledEntry,
            status: "CALLED",
            assigned_staff_id: currentUser.staff_id,
        };

        mockApi.getDepartmentQueue.mockResolvedValue([entry]);

        const error = new Error("You already have an active patient.");
        error.status = 409;

        mockApi.startQueueEntry.mockRejectedValue(error);

        await staff.refreshQueue();
        staff.selectQueueEntry(entry.queue_entry_id);

        await staff.performTransition("start");

        expect(
            document.querySelector("#action-error").textContent
        ).toContain("You already have an active patient");
        expect(mockApi.getDepartmentQueue).toHaveBeenCalled();
    });

});

    describe("logout", () => {

        it("disconnects the staff WebSocket during logout", async () => {
            mockApi.login.mockResolvedValue({});
            mockApi.getCurrentUser.mockResolvedValue(currentUser);

            const form = document.querySelector("#login-form");

            document.querySelector("#employee-id").value =
                "EMP-001";

            document.querySelector("#password").value =
                "password";

            await form.dispatchEvent(
                new Event("submit", {
                    bubbles: true,
                    cancelable: true,
                })
            );

            await vi.waitFor(() => {
                expect(mockWebSocket.connect)
                    .toHaveBeenCalled();
            });

            document
                .querySelector("#logout-button")
                .click();

            expect(mockWebSocket.disconnect)
                .toHaveBeenCalled();

            expect(mockApi.logout)
                .toHaveBeenCalled();
        });

    });

});
