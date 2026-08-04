
import {
    beforeEach,
    afterEach,
    describe,
    expect,
    it,
    vi,
} from "vitest";

import {
    HTTP_METHOD,
    request,
    getDisplaySnapshot,
    checkHealth,
} from "../js/api.js";

import {
    initializeConfig,
    resetConfig,
} from "../js/config.js";


/*
|--------------------------------------------------------------------------
| Test Setup
|--------------------------------------------------------------------------
*/

beforeEach(() => {
    initializeConfig({
        backend: {
            apiUrl: "http://localhost:8000/api",
            websocketUrl: "ws://localhost:8000/ws/display",
            connectionTimeoutMs: 5000,
        },
    });

    globalThis.fetch = vi.fn();
});


afterEach(() => {
    resetConfig();

    vi.restoreAllMocks();
});


/*
|--------------------------------------------------------------------------
| Helpers
|--------------------------------------------------------------------------
*/

function mockJsonResponse(
    body,
    {
        status = 200,
        statusText = "OK",
        headers = {},
    } = {}
) {
    return {
        ok: status >= 200 && status < 300,
        status,
        statusText,

        headers: {
            get: vi.fn((name) => {
                if (
                    name.toLowerCase() ===
                    "content-type"
                ) {
                    return (
                        headers["content-type"] ??
                        "application/json"
                    );
                }

                return headers[name] ?? null;
            }),
        },

        json: vi.fn().mockResolvedValue(body),

        text: vi.fn().mockResolvedValue(
            typeof body === "string"
                ? body
                : JSON.stringify(body)
        ),
    };
}


function mockTextResponse(
    body,
    {
        status = 200,
        statusText = "OK",
    } = {}
) {
    return {
        ok: status >= 200 && status < 300,
        status,
        statusText,

        headers: {
            get: vi.fn(() => "text/plain"),
        },

        json: vi.fn(),

        text: vi.fn().mockResolvedValue(body),
    };
}


/*
|--------------------------------------------------------------------------
| HTTP_METHOD
|--------------------------------------------------------------------------
*/

describe("HTTP_METHOD", () => {
    it("provides the supported HTTP methods", () => {
        expect(HTTP_METHOD).toEqual({
            GET: "GET",
            POST: "POST",
            PUT: "PUT",
            PATCH: "PATCH",
            DELETE: "DELETE",
        });
    });
});


/*
|--------------------------------------------------------------------------
| request() — URL Construction
|--------------------------------------------------------------------------
*/

describe("request() URL construction", () => {
    it("combines the configured API URL with the request path", async () => {
        fetch.mockResolvedValue(
            mockJsonResponse({
                success: true,
            })
        );

        await request("/test");

        expect(fetch)
            .toHaveBeenCalledWith(
                "http://localhost:8000/api/test",
                expect.any(Object)
            );
    });


    it("handles a base URL with a trailing slash", async () => {
        resetConfig();

        initializeConfig({
            backend: {
                apiUrl:
                    "http://localhost:8000/api/",
                websocketUrl:
                    "ws://localhost:8000/ws/display",
                connectionTimeoutMs: 5000,
            },
        });

        fetch.mockResolvedValue(
            mockJsonResponse({
                success: true,
            })
        );

        await request("/test");

        expect(fetch.mock.calls[0][0])
            .toBe(
                "http://localhost:8000/api/test"
            );
    });


    it("handles a path without a leading slash", async () => {
        fetch.mockResolvedValue(
            mockJsonResponse({
                success: true,
            })
        );

        await request("test");

        expect(fetch.mock.calls[0][0])
            .toBe(
                "http://localhost:8000/api/test"
            );
    });


    it("rejects an empty path", async () => {
        await expect(
            request("")
        ).rejects.toThrow(
            "API path must be a non-empty string"
        );
    });


    it("rejects a non-string path", async () => {
        await expect(
            request(null)
        ).rejects.toThrow(
            "API path must be a non-empty string"
        );
    });
});


/*
|--------------------------------------------------------------------------
| request() — GET
|--------------------------------------------------------------------------
*/

describe("request() GET requests", () => {
    it("uses GET by default", async () => {
        fetch.mockResolvedValue(
            mockJsonResponse({
                success: true,
            })
        );

        await request("/test");

        expect(fetch.mock.calls[0][1])
            .toMatchObject({
                method: "GET",
            });
    });


    it("uses the requested HTTP method", async () => {
        fetch.mockResolvedValue(
            mockJsonResponse({
                success: true,
            })
        );

        await request("/test", {
            method: HTTP_METHOD.POST,
        });

        expect(fetch.mock.calls[0][1])
            .toMatchObject({
                method: "POST",
            });
    });


    it("includes JSON Accept headers", async () => {
        fetch.mockResolvedValue(
            mockJsonResponse({
                success: true,
            })
        );

        await request("/test");

        expect(fetch.mock.calls[0][1].headers)
            .toMatchObject({
                Accept: "application/json",
            });
    });
});


/*
|--------------------------------------------------------------------------
| request() — JSON Response
|--------------------------------------------------------------------------
*/

describe("request() JSON responses", () => {
    it("returns parsed JSON", async () => {
        const payload = {
            success: true,
            message: "Hello",
        };

        fetch.mockResolvedValue(
            mockJsonResponse(payload)
        );

        const result =
            await request("/test");

        expect(result)
            .toEqual(payload);
    });


    it("parses JSON only once", async () => {
        const response =
            mockJsonResponse({
                success: true,
            });

        fetch.mockResolvedValue(response);

        await request("/test");

        expect(response.json)
            .toHaveBeenCalledTimes(1);
    });
});


/*
|--------------------------------------------------------------------------
| request() — Text Response
|--------------------------------------------------------------------------
*/

describe("request() text responses", () => {
    it("returns text for non-JSON responses", async () => {
        fetch.mockResolvedValue(
            mockTextResponse("OK")
        );

        const result =
            await request("/test");

        expect(result)
            .toBe("OK");
    });


    it("returns null for an empty response body", async () => {
        fetch.mockResolvedValue(
            mockTextResponse("")
        );

        const result =
            await request("/test");

        expect(result)
            .toBeNull();
    });
});


/*
|--------------------------------------------------------------------------
| request() — Request Body
|--------------------------------------------------------------------------
*/

describe("request() request body", () => {
    it("serializes object bodies as JSON", async () => {
        fetch.mockResolvedValue(
            mockJsonResponse({
                success: true,
            })
        );

        const body = {
            display_id: "DISPLAY-001",
            enabled: true,
        };

        await request("/test", {
            method: HTTP_METHOD.POST,
            body,
        });

        const options =
            fetch.mock.calls[0][1];

        expect(options.body)
            .toBe(JSON.stringify(body));

        expect(options.headers)
            .toMatchObject({
                "Content-Type":
                    "application/json",
            });
    });


    it("passes string bodies through unchanged", async () => {
        fetch.mockResolvedValue(
            mockJsonResponse({
                success: true,
            })
        );

        await request("/test", {
            method: HTTP_METHOD.POST,
            body: "hello",
        });

        expect(fetch.mock.calls[0][1].body)
            .toBe("hello");
    });


    it("does not add Content-Type when no body exists", async () => {
        fetch.mockResolvedValue(
            mockJsonResponse({
                success: true,
            })
        );

        await request("/test");

        expect(
            fetch.mock.calls[0][1].headers
                ["Content-Type"]
        ).toBeUndefined();
    });
});


/*
|--------------------------------------------------------------------------
| request() — Custom Headers
|--------------------------------------------------------------------------
*/

describe("request() headers", () => {
    it("accepts custom headers", async () => {
        fetch.mockResolvedValue(
            mockJsonResponse({
                success: true,
            })
        );

        await request("/test", {
            headers: {
                Authorization:
                    "Bearer test-token",
            },
        });

        expect(fetch.mock.calls[0][1].headers)
            .toMatchObject({
                Accept: "application/json",
                Authorization:
                    "Bearer test-token",
            });
    });


    it("allows custom headers to override defaults", async () => {
        fetch.mockResolvedValue(
            mockJsonResponse({
                success: true,
            })
        );

        await request("/test", {
            headers: {
                Accept: "application/custom",
            },
        });

        expect(fetch.mock.calls[0][1].headers.Accept)
            .toBe("application/custom");
    });
});


/*
|--------------------------------------------------------------------------
| request() — Abort Signal
|--------------------------------------------------------------------------
*/

describe("request() abort signal", () => {
    it("passes the abort signal to fetch", async () => {
        fetch.mockResolvedValue(
            mockJsonResponse({
                success: true,
            })
        );

        const controller =
            new AbortController();

        await request("/test", {
            signal: controller.signal,
        });

        expect(fetch.mock.calls[0][1].signal)
            .toBe(controller.signal);
    });
});


/*
|--------------------------------------------------------------------------
| request() — HTTP Errors
|--------------------------------------------------------------------------
*/

describe("request() HTTP errors", () => {
    it("rejects non-2xx responses", async () => {
        fetch.mockResolvedValue(
            mockJsonResponse(
                {
                    detail: "Display not found",
                },
                {
                    status: 404,
                    statusText: "Not Found",
                }
            )
        );

        await expect(
            request("/test")
        ).rejects.toThrow(
            "Display not found"
        );
    });


    it("exposes the HTTP status on the error", async () => {
        fetch.mockResolvedValue(
            mockJsonResponse(
                {
                    detail: "Forbidden",
                },
                {
                    status: 403,
                    statusText: "Forbidden",
                }
            )
        );

        try {
            await request("/test");
        } catch (error) {
            expect(error.name)
                .toBe("ApiError");

            expect(error.status)
                .toBe(403);

            expect(error.statusText)
                .toBe("Forbidden");
        }
    });


    it("preserves the response body on API errors", async () => {
        const body = {
            detail: "Invalid display",
            code: "DISPLAY_INVALID",
        };

        fetch.mockResolvedValue(
            mockJsonResponse(
                body,
                {
                    status: 400,
                    statusText: "Bad Request",
                }
            )
        );

        try {
            await request("/test");
        } catch (error) {
            expect(error.body)
                .toEqual(body);
        }
    });


    it("uses a message field when detail is unavailable", async () => {
        fetch.mockResolvedValue(
            mockJsonResponse(
                {
                    message: "Something went wrong",
                },
                {
                    status: 500,
                    statusText: "Internal Server Error",
                }
            )
        );

        await expect(
            request("/test")
        ).rejects.toThrow(
            "Something went wrong"
        );
    });


    it("uses response text when the error body is plain text", async () => {
        fetch.mockResolvedValue(
            mockTextResponse(
                "Server unavailable",
                {
                    status: 503,
                    statusText: "Service Unavailable",
                }
            )
        );

        await expect(
            request("/test")
        ).rejects.toThrow(
            "Server unavailable"
        );
    });


    it("falls back to the HTTP status when no error message exists", async () => {
        fetch.mockResolvedValue(
            mockJsonResponse(
                {},
                {
                    status: 500,
                    statusText: "Internal Server Error",
                }
            )
        );

        await expect(
            request("/test")
        ).rejects.toThrow(
            "API request failed with status 500"
        );
    });
});


/*
|--------------------------------------------------------------------------
| request() — Network Errors
|--------------------------------------------------------------------------
*/

describe("request() network errors", () => {
    it("converts fetch failures into an ApiNetworkError", async () => {
        fetch.mockRejectedValue(
            new Error("Network unavailable")
        );

        await expect(
            request("/test")
        ).rejects.toMatchObject({
            name: "ApiNetworkError",
            message:
                "Unable to reach the HPQMS API",
        });
    });


    it("preserves the original network error as the cause", async () => {
        const originalError =
            new Error("Connection refused");

        fetch.mockRejectedValue(
            originalError
        );

        try {
            await request("/test");
        } catch (error) {
            expect(error.cause)
                .toBe(originalError);
        }
    });
});


/*
|--------------------------------------------------------------------------
| getDisplaySnapshot()
|--------------------------------------------------------------------------
*/

describe("getDisplaySnapshot()", () => {
    it("requests the display snapshot endpoint", async () => {
        fetch.mockResolvedValue(
            mockJsonResponse({
                departments: [],
                announcements: [],
            })
        );

        await getDisplaySnapshot();

        expect(fetch.mock.calls[0][0])
            .toBe(
                "http://localhost:8000/api/display/snapshot"
            );
    });


    it("uses GET for the display snapshot", async () => {
        fetch.mockResolvedValue(
            mockJsonResponse({
                departments: [],
                announcements: [],
            })
        );

        await getDisplaySnapshot();

        expect(fetch.mock.calls[0][1])
            .toMatchObject({
                method: "GET",
            });
    });


    it("returns the snapshot response", async () => {
        const snapshot = {
            facility_name: "HPQMS Hospital",
            departments: [],
            announcements: [],
        };

        fetch.mockResolvedValue(
            mockJsonResponse(snapshot)
        );

        const result =
            await getDisplaySnapshot();

        expect(result)
            .toEqual(snapshot);
    });


    it("passes an abort signal to the snapshot request", async () => {
        fetch.mockResolvedValue(
            mockJsonResponse({
                departments: [],
            })
        );

        const controller =
            new AbortController();

        await getDisplaySnapshot({
            signal: controller.signal,
        });

        expect(fetch.mock.calls[0][1].signal)
            .toBe(controller.signal);
    });
});


/*
|--------------------------------------------------------------------------
| checkHealth()
|--------------------------------------------------------------------------
*/

describe("checkHealth()", () => {
    it("requests the health endpoint", async () => {
        fetch.mockResolvedValue(
            mockJsonResponse({
                status: "ok",
            })
        );

        await checkHealth();

        expect(fetch.mock.calls[0][0])
            .toBe(
                "http://localhost:8000/api/health"
            );
    });


    it("uses GET for the health request", async () => {
        fetch.mockResolvedValue(
            mockJsonResponse({
                status: "ok",
            })
        );

        await checkHealth();

        expect(fetch.mock.calls[0][1])
            .toMatchObject({
                method: "GET",
            });
    });


    it("returns the health response", async () => {
        const health = {
            status: "ok",
            service: "hpqms",
        };

        fetch.mockResolvedValue(
            mockJsonResponse(health)
        );

        const result =
            await checkHealth();

        expect(result)
            .toEqual(health);
    });
});

