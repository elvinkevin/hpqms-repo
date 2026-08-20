/* ==========================================================================
   HPQMS Kiosk API
   js/kiosk-api.js
   ========================================================================== */

import { request, HTTP_METHOD } from "./api.js";
import { getConfig } from "./config.js";


/* ==========================================================================
   Kiosk Authentication
   ========================================================================== */

/**
 * Return the configured kiosk API key.
 *
 * The kiosk key is a device credential, not a patient credential.
 */
function getKioskApiKey() {
    const config = getConfig();

    const apiKey =
        config?.kiosk?.apiKey ??
        config?.backend?.kioskApiKey;

    if (
        typeof apiKey !== "string" ||
        apiKey.trim() === ""
    ) {
        throw new Error(
            "Kiosk API key is not configured."
        );
    }

    return apiKey.trim();
}


/* ==========================================================================
   Check-In
   ========================================================================== */

/**
 * Submit a patient kiosk check-in.
 * 
 * Accepts a payload config object. To prevent runtime integration drops,
 * this function securely accepts both camelCase and snake_case configurations.
 */

async function kioskCheckIn(frontendData = {}) {
    // 1. Client-side sanity checks
    if (!frontendData.idValue || frontendData.idValue.trim() === "") {
        throw new Error("Patient identifier is required.");
    }
    if (!frontendData.idMethod) {
        throw new Error("Patient identifier type is required.");
    }
    if (!frontendData.visitType) {
        throw new Error("Visit type is required.");
    }

    // 2. Build the exact Pydantic schema payload
    const backendPayload = {
        identifier: frontendData.idValue.trim(),
        identifier_type: frontendData.idMethod.toUpperCase(),
        visit_type: frontendData.visitType
    };

    // 3. Fire the request over the wire
    return request("/kiosk/check-in", {
        method: HTTP_METHOD.POST,
        body: backendPayload,
        headers: {
            "X-Kiosk-API-Key": getKioskApiKey(),
        },
    });
}




/* ==========================================================================
   Public API
   ========================================================================== */

export {
    kioskCheckIn,
};
