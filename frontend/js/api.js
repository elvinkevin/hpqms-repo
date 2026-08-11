/* ==========================================================================
   HPQMS Public Patient Display Board
   js/api.js — HTTP API Transport Layer
   ========================================================================== */

import { getConfig } from "./config.js";


/* ==========================================================================
   Constants
   ========================================================================== */

const HTTP_METHOD = Object.freeze({
    GET: "GET",
    POST: "POST",
    PUT: "PUT",
    PATCH: "PATCH",
    DELETE: "DELETE",
});


/* ==========================================================================
   Internal Helpers
   ========================================================================== */

/**
 * Build an API URL from the configured backend base URL.
 *
 * The configuration may contain either:
 *
 *     http://localhost:8000
 *
 * or:
 *
 *     http://localhost:8000/
 *
 * This helper prevents accidental double slashes.
 */
/**
 * Build an API URL from the configured backend base URL.
 * Automatically resolves localhost/127.0.0.1 to the active LAN host origin.
 */
function buildUrl(path) {
    if (typeof path !== "string" || path.trim() === "") {
        throw new TypeError("API path must be a non-empty string");
    }

    const config = getConfig();
    let baseUrl = config?.backend?.apiBaseUrl ?? config?.backend?.apiUrl;

    // Fallback if config is missing or invalid
    if (typeof baseUrl !== "string" || baseUrl.trim() === "") {
        baseUrl = window.location.origin;
    }

    // Dynamic LAN Auto-Detection:
    // If running from an IP like 192.168.1.70, replace hardcoded localhost/127.0.0.1
    // with current window origin so TV and other devices route properly.
    if (baseUrl.includes("localhost") || baseUrl.includes("127.0.0.1")) {
        const currentHost = window.location.hostname;
        if (currentHost !== "localhost" && currentHost !== "127.0.0.1") {
            const port = window.location.port ? `:${window.location.port}` : "";
            baseUrl = `${window.location.protocol}//${currentHost}${port}`;
        }
    }

    return `${baseUrl.replace(/\/+$/, "")}/${path.replace(/^\/+/, "")}`;
}

/**
 * Parse a response body.
 *
 * Empty responses are allowed.
 */
async function parseResponseBody(response) {
    const contentType =
        response.headers.get("content-type") || "";

    if (
        contentType
            .toLowerCase()
            .includes("application/json")
    ) {
        return response.json();
    }

    const text = await response.text();

    if (text === "") {
        return null;
    }

    return text;
}


/**
 * Create a useful API error.
 */
function createApiError(response, body) {
    let message =
        `API request failed with status ${response.status}`;

    if (body && typeof body === "object") {
        if (typeof body.detail === "string") {
            message = body.detail;
        } else if (typeof body.message === "string") {
            message = body.message;
        }
    } else if (typeof body === "string" && body.trim()) {
        message = body;
    }

    const error = new Error(message);

    error.name = "ApiError";
    error.status = response.status;
    error.statusText = response.statusText;
    error.body = body;

    return error;
}


/* ==========================================================================
   HTTP Request
   ========================================================================== */

/**
 * Execute an HTTP request against the HPQMS backend.
 *
 * This function does not interpret the response according to
 * application/domain rules. It only handles HTTP transport.
 */
async function request(
    path,
    {
        method = HTTP_METHOD.GET,
        body = undefined,
        headers = {},
        signal = undefined,
    } = {}
) {
    const url = buildUrl(path);

    const requestHeaders = {
        Accept: "application/json",
        ...headers,
    };

    const options = {
        method,
        headers: requestHeaders,
        signal,
    };

    if (body !== undefined) {
        if (
            typeof body === "object" &&
            body !== null
        ) {
            requestHeaders["Content-Type"] =
                "application/json";

            options.body = JSON.stringify(body);
        } else {
            options.body = body;
        }
    }

    let response;

    try {
        response = await fetch(url, options);
    } catch (error) {
        const networkError = new Error(
            "Unable to reach the HPQMS API",
            {
                cause: error,
            }
        );

        networkError.name = "ApiNetworkError";

        throw networkError;
    }

    const responseBody =
        await parseResponseBody(response);

    if (!response.ok) {
        throw createApiError(
            response,
            responseBody
        );
    }

    return responseBody;
}


/* ==========================================================================
   Display API
   ========================================================================== */

/**
 * Retrieve the authoritative display snapshot.
 *
 * This endpoint is particularly important after WebSocket
 * reconnection because the snapshot is the authoritative
 * source of current display state.
 */
async function getDisplaySnapshot(
    { signal = undefined } = {}
) {
    return request(
        "/display/snapshot",
        {
            method: HTTP_METHOD.GET,
            signal,
        }
    );
}


/* ==========================================================================
   Health / Connectivity
   ========================================================================== */

/**
 * Check whether the backend API is reachable.
 *
 * This is deliberately separate from WebSocket connectivity.
 */
async function checkHealth(
    { signal = undefined } = {}
) {
    return request(
        "/health",
        {
            method: HTTP_METHOD.GET,
            signal,
        }
    );
}


/* ==========================================================================
   Public API
   ========================================================================== */

export {
    HTTP_METHOD,

    request,

    getDisplaySnapshot,

    checkHealth,
};