// config.js
//      │
//      ├── display
//      ├── profile
//      ├── layout
//      ├── departments
//      ├── rotation
//      ├── alerts
//      ├── idle
//      ├── features
//      ├── branding
//      └── network


/* ==========================================================================
   HPQMS Public Patient Display Board
   js/config.js — Runtime Configuration
   ========================================================================== */

/* ==========================================================================
   Dynamic Host Resolution
   ========================================================================== */

function resolveDynamicUrls() {
    const isBrowser = typeof window !== "undefined" && window.location;
    const backendPort = "8000";
    const protocol = isBrowser && window.location.protocol !== "file:"
        ? window.location.protocol
        : "http:";
    const hostname = isBrowser && window.location.hostname
        ? window.location.hostname
        : "localhost";
    const frontendPort = isBrowser ? window.location.port : "";
    const backendHost = frontendPort === backendPort
        ? window.location.host
        : `${hostname}:${backendPort}`;
    const wsProtocol = protocol === "https:" ? "wss:" : "ws:";

    return {
        apiBaseUrl: `${protocol}//${backendHost}/api`,
        websocketUrl: `${wsProtocol}//${backendHost}/ws/display`,
    };
}

const dynamicBackendDefaults = resolveDynamicUrls();

const DEFAULT_CONFIG = {
    display: {
        id: "DISPLAY-001",
        name: "Public Patient Display",
        facilityName: "HPQMS Hospital",
    },
    // Add kiosk configuration block
    kiosk: {
        apiKey: "generate-a-long-random-value", // Set your actual key or dev default here
    },

    layout: {
        mode: "SINGLE_DEPARTMENT",
    },

    backend: {
        apiBaseUrl: dynamicBackendDefaults.apiBaseUrl,
        websocketUrl: dynamicBackendDefaults.websocketUrl,
        connectionTimeoutMs: 10000,
    },

    reconnect: {
        initialDelayMs: 1000,
        maxDelayMs: 30000,
        backoffMultiplier: 2,
        maxAttempts: Infinity,
    },

    rotation: {
        enabled: true,
        intervalMs: 15000,
    },

    snapshot: {
        refreshIntervalMs: 300000,
    },

    idle: {
        enabled: true,
        timeoutMs: 120000,
    },

    alerts: {
        audioEnabled: true,
        defaultDurationMs: 5000,
        emergencyDurationMs: 15000,
        chimeVolume: 0.5,
        speakTokenNumber: true,
        criticalChime: true,
        speechRate: 1.0,
        speechPitch: 1.0,
        speechVolume: 1.0,
    },

    announcements: {
        enabled: true,
        displayDurationMs: 10000,
    },

    features: {
        audio: true,
        announcements: true,
        multiDepartment: true,
    },

};


/* ==========================================================================
   Internal State
   ========================================================================== */

let currentConfig = deepClone(DEFAULT_CONFIG);


/* ==========================================================================
   Utility Functions
   ========================================================================== */

/**
 * Create a deep copy of a configuration object.
 */
function deepClone(value) {
    if (value === undefined) {
        return undefined;
    }

    return structuredClone(value);
}




/**
 * Recursively merge source into target.
 *
 * Objects are merged.
 * Primitive values and arrays are replaced.
 */
function deepMerge(target, source) {
    if (!source || typeof source !== "object") {
        return target;
    }

    for (const key of Object.keys(source)) {
        const sourceValue = source[key];

        if (
            sourceValue !== null &&
            typeof sourceValue === "object" &&
            !Array.isArray(sourceValue)
        ) {
            if (
                !target[key] ||
                typeof target[key] !== "object" ||
                Array.isArray(target[key])
            ) {
                target[key] = {};
            }

            deepMerge(target[key], sourceValue);
        } else {
            target[key] = sourceValue;
        }
    }

    return target;
}


/* ==========================================================================
   Validation
   ========================================================================== */

function assertPositiveNumber(value, fieldName) {
    if (
        typeof value !== "number" ||
        !Number.isFinite(value) ||
        value <= 0
    ) {
        throw new Error(
            `${fieldName} must be a positive number`
        );
    }
}


function assertNonNegativeNumber(value, fieldName) {
    if (
        typeof value !== "number" ||
        !Number.isFinite(value) ||
        value < 0
    ) {
        throw new Error(
            `${fieldName} must be a non-negative number`
        );
    }
}


/**
 * Assert that a number falls within an inclusive range [min, max].
 */
function assertNumberRange(value, fieldName, min, max) {
    if (
        typeof value !== "number" ||
        !Number.isFinite(value) ||
        value < min ||
        value > max
    ) {
        throw new Error(
            `${fieldName} must be a number between ${min} and ${max}`
        );
    }
}


function assertBoolean(value, fieldName) {
    if (typeof value !== "boolean") {
        throw new Error(
            `${fieldName} must be a boolean`
        );
    }
}


function assertHttpUrl(value, fieldName) {
    const httpRegex = /^https?:\/\/[^\s$.?#].[^\s]*$/i;
    if (typeof value !== "string" || !httpRegex.test(value)) {
        throw new Error(`${fieldName} must be a valid HTTP/HTTPS URL`);
    }
}

function assertWebSocketUrl(value, fieldName) {
    const wsRegex = /^wss?:\/\/[^\s$.?#].[^\s]*$/i;
    if (typeof value !== "string" || !wsRegex.test(value)) {
        throw new Error(`${fieldName} must be a valid WebSocket URL`);
    }
}



/**
 * Validate the complete runtime configuration.
 */
function validateConfig(config) {

    const apiKey = config.kiosk?.apiKey ?? config.backend?.kioskApiKey;

    if (typeof apiKey !== "string" || apiKey.trim() === "") {
        throw new Error(
            "kiosk.apiKey or backend.kioskApiKey must be a non-empty string"
        );
    }
    /* Display */

    if (
        typeof config.display.id !== "string" ||
        config.display.id.trim() === ""
    ) {
        throw new Error(
            "display.id must be a non-empty string"
        );
    }


    /* Backend */

    assertHttpUrl(
        config.backend.apiBaseUrl,
        "backend.apiBaseUrl"
    );

    assertWebSocketUrl(
        config.backend.websocketUrl,
        "backend.websocketUrl"
    );

    assertPositiveNumber(
        config.backend.connectionTimeoutMs,
        "backend.connectionTimeoutMs"
    );


    /* Reconnection */

    assertPositiveNumber(
        config.reconnect.initialDelayMs,
        "reconnect.initialDelayMs"
    );

    assertPositiveNumber(
        config.reconnect.maxDelayMs,
        "reconnect.maxDelayMs"
    );

    if (
        config.reconnect.maxDelayMs <
        config.reconnect.initialDelayMs
    ) {
        throw new Error(
            "reconnect.maxDelayMs must be greater than or equal to initialDelayMs"
        );
    }


    /* Layout */

    const supportedLayoutModes = new Set([
        "ROOM",
        "SINGLE_DEPARTMENT",
        "ROTATING_BOARD",
        "ATRIUM",
    ]);

    if (!supportedLayoutModes.has(config.layout?.mode)) {
        throw new Error(
            "layout.mode must be one of ROOM, SINGLE_DEPARTMENT, ROTATING_BOARD, or ATRIUM"
        );
    }

    if (
        typeof config.reconnect.backoffMultiplier !== "number" ||
        !Number.isFinite(config.reconnect.backoffMultiplier) ||
        config.reconnect.backoffMultiplier < 1
    ) {
        throw new Error(
            "reconnect.backoffMultiplier must be at least 1"
        );
    }

           if (
        config.reconnect.maxAttempts !== Infinity &&
        (
            typeof config.reconnect.maxAttempts !== "number" ||
            !Number.isInteger(config.reconnect.maxAttempts) ||
            config.reconnect.maxAttempts < 1
        )
    ) {
        throw new Error(
            "reconnect.maxAttempts must be a positive integer or Infinity"
        );
    }


    


    /* Rotation */

    assertBoolean(
        config.rotation.enabled,
        "rotation.enabled"
    );

    assertPositiveNumber(
        config.rotation.intervalMs,
        "rotation.intervalMs"
    );


    /* Snapshot */

    assertPositiveNumber(
        config.snapshot.refreshIntervalMs,
        "snapshot.refreshIntervalMs"
    );


    /* Idle */

    assertBoolean(
        config.idle.enabled,
        "idle.enabled"
    );

    assertPositiveNumber(
        config.idle.timeoutMs,
        "idle.timeoutMs"
    );


    /* Alerts */

    assertBoolean(
        config.alerts.audioEnabled,
        "alerts.audioEnabled"
    );

    assertPositiveNumber(
        config.alerts.defaultDurationMs,
        "alerts.defaultDurationMs"
    );

    assertPositiveNumber(
        config.alerts.emergencyDurationMs,
        "alerts.emergencyDurationMs"
    );


    assertNumberRange(
        config.alerts.chimeVolume,
        "alerts.chimeVolume",
        0, 1
    );

    assertBoolean(
        config.alerts.speakTokenNumber,
        "alerts.speakTokenNumber"
    );

    assertBoolean(
        config.alerts.criticalChime,
        "alerts.criticalChime"
    );

    assertNumberRange(
        config.alerts.speechRate,
        "alerts.speechRate",
        0.1, 10
    );

    assertNumberRange(
        config.alerts.speechPitch,
        "alerts.speechPitch",
        0, 2
    );

    assertNumberRange(
        config.alerts.speechVolume,
        "alerts.speechVolume",
        0, 1
    );


    /* Announcements */

    assertBoolean(
        config.announcements.enabled,
        "announcements.enabled"
    );

    assertPositiveNumber(
        config.announcements.displayDurationMs,
        "announcements.displayDurationMs"
    );


    /* Features */

    assertBoolean(
        config.features.audio,
        "features.audio"
    );

    assertBoolean(
        config.features.announcements,
        "features.announcements"
    );

    assertBoolean(
        config.features.multiDepartment,
        "features.multiDepartment"
    );
}


/* ==========================================================================
   Public API
   ========================================================================== */

/**
 * Initialize or replace runtime configuration.
 *
 * Overrides are deeply merged with the defaults.
 */
export function initializeConfig(overrides = {}) {
    if (
        overrides === null ||
        typeof overrides !== "object" ||
        Array.isArray(overrides)
    ) {
        throw new Error(
            "Configuration overrides must be an object"
        );
    }

    const nextConfig = deepClone(DEFAULT_CONFIG);

    deepMerge(nextConfig, deepClone(overrides));

    validateConfig(nextConfig);

    currentConfig = nextConfig;

    return getConfig();
}


/**
 * Return a defensive copy of the current configuration.
 */
export function getConfig() {
    return deepClone(currentConfig);
}


/**
 * Retrieve a nested configuration value using dot notation.
 *
 * Example:
 *
 * getConfigValue("backend.apiBaseUrl")
 */
export function getConfigValue(path) {
    if (
        typeof path !== "string" ||
        path.trim() === ""
    ) {
        throw new Error(
            "Configuration path must be a non-empty string"
        );
    }

    const segments = path.split(".");
    let value = currentConfig;

    for (const segment of segments) {
        if (
            value === null ||
            value === undefined ||
            typeof value !== "object" ||
            !(segment in value)
        ) {
            return undefined;
        }

        value = value[segment];
    }

    return deepClone(value);
}





/**
 * Reset configuration to the default values.
 */
export function resetConfig() {
    currentConfig = deepClone(DEFAULT_CONFIG);
}


/* ==========================================================================
   Initialization
   ========================================================================== */

validateConfig(currentConfig);
