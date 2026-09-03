/* ==========================================================================
   HPQMS Staff Session Manager
   js/staff-session.js
   --------------------------------------------------------------------------
   Responsible only for persistence and retrieval of the authenticated
   staff session.

   It does NOT:
     - perform API requests
     - determine roles
     - manage queues
     - manage WebSockets
     - render UI

   Storage strategy:
     - sessionStorage when "Remember Me" is disabled.
     - localStorage when "Remember Me" is enabled.

   Never store staff passwords.
   ========================================================================== */

const SESSION_KEY = "hpqms_staff_session";

const STORAGE_TYPES = Object.freeze({
    SESSION: "session",
    LOCAL: "local",
});


/* ==========================================================================
   STORAGE HELPERS
   ========================================================================== */

function getStorage(type) {
    return type === STORAGE_TYPES.LOCAL
        ? window.localStorage
        : window.sessionStorage;
}


/* ==========================================================================
   SESSION WRITE
   ========================================================================== */

/**
 * Persist an authenticated staff session.
 *
 * @param {string} accessToken
 * @param {boolean} rememberMe
 */
export function saveSession(accessToken, rememberMe = false) {
    if (!accessToken) {
        throw new Error("Cannot save an empty access token.");
    }

    const targetStorage = getStorage(
        rememberMe
            ? STORAGE_TYPES.LOCAL
            : STORAGE_TYPES.SESSION
    );

    const otherStorage = getStorage(
        rememberMe
            ? STORAGE_TYPES.SESSION
            : STORAGE_TYPES.LOCAL
    );

    /*
     * Ensure an old session stored in the other storage mechanism does
     * not take precedence later.
     */
    otherStorage.removeItem(SESSION_KEY);

    targetStorage.setItem(
        SESSION_KEY,
        JSON.stringify({
            accessToken,
            rememberMe: Boolean(rememberMe),
        })
    );
}


/* ==========================================================================
   SESSION READ
   ========================================================================== */

/**
 * Retrieve the currently persisted staff session.
 *
 * Checks sessionStorage first, then localStorage.
 *
 * @returns {{accessToken: string, rememberMe: boolean}|null}
 */
export function getSession() {
    const sessionStorageSession =
        readSession(getStorage(STORAGE_TYPES.SESSION));

    if (sessionStorageSession) {
        return sessionStorageSession;
    }

    return readSession(
        getStorage(STORAGE_TYPES.LOCAL)
    );
}

function readSession(storage) {
    const raw = storage.getItem(SESSION_KEY);

    if (!raw) {
        return null;
    }

    try {
        const session = JSON.parse(raw);

        if (!session?.accessToken) {
            storage.removeItem(SESSION_KEY);
            return null;
        }

        return {
            accessToken: session.accessToken,
            rememberMe: Boolean(session.rememberMe),
        };
    } catch (error) {
        console.error(
            "[StaffSession] Invalid stored session:",
            error
        );

        storage.removeItem(SESSION_KEY);
        return null;
    }
}


/* ==========================================================================
   TOKEN ACCESS
   ========================================================================== */

/**
 * Return only the access token.
 *
 * @returns {string|null}
 */
export function getAccessToken() {
    return getSession()?.accessToken ?? null;
}


/* ==========================================================================
   SESSION STATE
   ========================================================================== */

/**
 * Check whether a persisted session exists.
 *
 * @returns {boolean}
 */
export function hasSession() {
    return Boolean(getAccessToken());
}


/**
 * Return whether the current session was saved with Remember Me.
 *
 * @returns {boolean}
 */
export function isRemembered() {
    return getSession()?.rememberMe === true;
}


/* ==========================================================================
   SESSION CLEAR
   ========================================================================== */

/**
 * Remove the staff session from both storage mechanisms.
 */
export function clearSession() {
    window.sessionStorage.removeItem(SESSION_KEY);
    window.localStorage.removeItem(SESSION_KEY);
}


/* ==========================================================================
   PUBLIC CONSTANTS
   ========================================================================== */

export {
    SESSION_KEY,
};