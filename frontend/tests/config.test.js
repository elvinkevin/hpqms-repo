
import { beforeEach, describe, expect, it } from "vitest";

import {
    getConfig,
    getConfigValue,
    initializeConfig,
    resetConfig,
} from "../js/config.js";


/*
|--------------------------------------------------------------------------
| Test Fixtures
|--------------------------------------------------------------------------
*/

const VALID_OVERRIDES = {
    display: {
        id: "DISPLAY-001",
        name: "Main Waiting Area Display",
        facilityName: "HPQMS Hospital",
    },

    backend: {
        apiBaseUrl: "http://localhost:8000",
        websocketUrl: "ws://localhost:8000/ws/display",
        connectionTimeoutMs: 15000,
    },

    reconnect: {
        initialDelayMs: 2000,
        maxDelayMs: 60000,
        backoffMultiplier: 2,
        maxAttempts: 10,
    },

    rotation: {
        enabled: true,
        intervalMs: 20000,
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

    layout: {
        mode: "SINGLE_DEPARTMENT",
    },
};


/*
|--------------------------------------------------------------------------
| Setup
|--------------------------------------------------------------------------
*/

beforeEach(() => {
    resetConfig();
});


/*
|--------------------------------------------------------------------------
| Initialization
|--------------------------------------------------------------------------
*/

describe("initializeConfig()", () => {
    it("initializes successfully with default configuration", () => {
        expect(() => {
            initializeConfig();
        }).not.toThrow();
    });


    it("accepts valid configuration overrides", () => {
        initializeConfig(VALID_OVERRIDES);

        const config = getConfig();

        expect(config.display.id)
            .toBe("DISPLAY-001");

        expect(config.display.name)
            .toBe("Main Waiting Area Display");

        expect(config.backend.apiBaseUrl)
            .toBe("http://localhost:8000");
    });


    it("preserves unspecified default values", () => {
        initializeConfig({
            display: {
                id: "DISPLAY-001",
            },
        });

        const config = getConfig();

        expect(config.display.id)
            .toBe("DISPLAY-001");

        expect(config.display.name)
            .toBeDefined();

        expect(config.backend)
            .toBeDefined();

        expect(config.rotation)
            .toBeDefined();
    });


    it("deep-merges nested configuration", () => {
        initializeConfig({
            rotation: {
                intervalMs: 30000,
            },
        });

        const config = getConfig();

        expect(config.rotation.intervalMs)
            .toBe(30000);

        expect(config.rotation.enabled)
            .toBeDefined();
    });


    it("does not mutate the supplied overrides", () => {
        const overrides = {
            display: {
                id: "DISPLAY-001",
            },

            rotation: {
                intervalMs: 30000,
            },
        };

        const original = structuredClone(overrides);

        initializeConfig(overrides);

        expect(overrides)
            .toEqual(original);
    });


    it("can be initialized repeatedly with the latest configuration", () => {
        initializeConfig({
            display: {
                id: "DISPLAY-001",
            },
        });

        initializeConfig({
            display: {
                id: "DISPLAY-002",
            },
        });

        expect(getConfig().display.id)
            .toBe("DISPLAY-002");
    });
});


/*
|--------------------------------------------------------------------------
| Display Configuration
|--------------------------------------------------------------------------
*/

describe("display configuration", () => {
    it("requires a display identifier", () => {
        expect(() => {
            initializeConfig({
                display: {
                    id: "",
                },
            });
        }).toThrow();
    });


    it("accepts a display name", () => {
        initializeConfig({
            display: {
                id: "DISPLAY-001",
                name: "Reception Display",
            },
        });

        expect(getConfig().display.name)
            .toBe("Reception Display");
    });


    it("accepts a facility name", () => {
        initializeConfig({
            display: {
                id: "DISPLAY-001",
                facilityName: "HPQMS Hospital",
            },
        });

        expect(getConfig().display.facilityName)
            .toBe("HPQMS Hospital");
    });
});


describe("layout configuration", () => {
    it("uses the single-department layout by default", () => {
        expect(getConfig().layout.mode)
            .toBe("SINGLE_DEPARTMENT");
    });


    it("rejects an unsupported layout mode", () => {
        expect(() => {
            initializeConfig({
                layout: {
                    mode: "UNKNOWN",
                },
            });
        }).toThrow();
    });
});


/*
|--------------------------------------------------------------------------
| Backend Configuration
|--------------------------------------------------------------------------
*/

describe("backend configuration", () => {
    it("accepts a valid HTTP API URL", () => {
        initializeConfig({
            backend: {
                apiBaseUrl: "https://api.example.com",
            },
        });

        expect(getConfig().backend.apiBaseUrl)
            .toBe("https://api.example.com");
    });


    it("rejects an invalid API URL", () => {
        expect(() => {
            initializeConfig({
                backend: {
                    apiBaseUrl: "not-a-url",
                },
            });
        }).toThrow();
    });


    it("accepts a valid WebSocket URL", () => {
        initializeConfig({
            backend: {
                websocketUrl: "wss://api.example.com/ws/display",
            },
        });

        expect(getConfig().backend.websocketUrl)
            .toBe(
                "wss://api.example.com/ws/display"
            );
    });


    it("rejects an invalid WebSocket URL", () => {
        expect(() => {
            initializeConfig({
                backend: {
                    websocketUrl: "http://example.com/ws",
                },
            });
        }).toThrow();
    });


    it("rejects a non-positive connection timeout", () => {
        expect(() => {
            initializeConfig({
                backend: {
                    connectionTimeoutMs: 0,
                },
            });
        }).toThrow();
    });
});


/*
|--------------------------------------------------------------------------
| Reconnection Configuration
|--------------------------------------------------------------------------
*/

describe("reconnect configuration", () => {
    it("accepts valid reconnection settings", () => {
        initializeConfig({
            reconnect: {
                initialDelayMs: 1000,
                maxDelayMs: 30000,
                backoffMultiplier: 2,
                maxAttempts: 5,
            },
        });

        const reconnect = getConfig().reconnect;

        expect(reconnect.initialDelayMs)
            .toBe(1000);

        expect(reconnect.maxDelayMs)
            .toBe(30000);

        expect(reconnect.backoffMultiplier)
            .toBe(2);

        expect(reconnect.maxAttempts)
            .toBe(5);
    });


    it("rejects a negative initial delay", () => {
        expect(() => {
            initializeConfig({
                reconnect: {
                    initialDelayMs: -1,
                },
            });
        }).toThrow();
    });


    it("rejects max delay smaller than initial delay", () => {
        expect(() => {
            initializeConfig({
                reconnect: {
                    initialDelayMs: 10000,
                    maxDelayMs: 5000,
                },
            });
        }).toThrow();
    });


    it("rejects a backoff multiplier below one", () => {
        expect(() => {
            initializeConfig({
                reconnect: {
                    backoffMultiplier: 0.5,
                },
            });
        }).toThrow();
    });


    it("rejects an invalid maximum attempt count", () => {
        expect(() => {
            initializeConfig({
                reconnect: {
                    maxAttempts: 0,
                },
            });
        }).toThrow();
    });
});


/*
|--------------------------------------------------------------------------
| Timing Configuration
|--------------------------------------------------------------------------
*/

describe("timing configuration", () => {
    it("accepts valid rotation settings", () => {
        initializeConfig({
            rotation: {
                enabled: true,
                intervalMs: 15000,
            },
        });

        expect(getConfig().rotation.intervalMs)
            .toBe(15000);
    });


    it("rejects a non-positive rotation interval", () => {
        expect(() => {
            initializeConfig({
                rotation: {
                    intervalMs: 0,
                },
            });
        }).toThrow();
    });


    it("rejects a non-positive idle timeout", () => {
        expect(() => {
            initializeConfig({
                idle: {
                    timeoutMs: -100,
                },
            });
        }).toThrow();
    });


    it("rejects a non-positive snapshot refresh interval", () => {
        expect(() => {
            initializeConfig({
                snapshot: {
                    refreshIntervalMs: 0,
                },
            });
        }).toThrow();
    });
});


/*
|--------------------------------------------------------------------------
| Alert / Announcement Configuration
|--------------------------------------------------------------------------
*/

describe("alert and announcement configuration", () => {
    it("accepts valid alert durations", () => {
        initializeConfig({
            alerts: {
                defaultDurationMs: 5000,
                emergencyDurationMs: 15000,
            },
        });

        const alerts = getConfig().alerts;

        expect(alerts.defaultDurationMs)
            .toBe(5000);

        expect(alerts.emergencyDurationMs)
            .toBe(15000);
    });


    it("rejects invalid alert durations", () => {
        expect(() => {
            initializeConfig({
                alerts: {
                    defaultDurationMs: 0,
                },
            });
        }).toThrow();

        expect(() => {
            initializeConfig({
                alerts: {
                    emergencyDurationMs: -1,
                },
            });
        }).toThrow();
    });


    it("accepts announcement settings", () => {
        initializeConfig({
            announcements: {
                enabled: false,
                displayDurationMs: 20000,
            },
        });

        const announcements =
            getConfig().announcements;

        expect(announcements.enabled)
            .toBe(false);

        expect(announcements.displayDurationMs)
            .toBe(20000);
    });


    it("rejects an invalid announcement duration", () => {
        expect(() => {
            initializeConfig({
                announcements: {
                    displayDurationMs: 0,
                },
            });
        }).toThrow();
    });
});


/*
|--------------------------------------------------------------------------
| Feature Flags
|--------------------------------------------------------------------------
*/

describe("feature flags", () => {
    it("accepts boolean feature flags", () => {
        initializeConfig({
            features: {
                audio: false,
                announcements: true,
                multiDepartment: false,
            },
        });

        const features = getConfig().features;

        expect(features.audio)
            .toBe(false);

        expect(features.announcements)
            .toBe(true);

        expect(features.multiDepartment)
            .toBe(false);
    });


    it("rejects non-boolean feature flags", () => {
        expect(() => {
            initializeConfig({
                features: {
                    audio: "true",
                },
            });
        }).toThrow();
    });
});


/*
|--------------------------------------------------------------------------
| getConfig()
|--------------------------------------------------------------------------
*/

describe("getConfig()", () => {
    it("returns the complete configuration", () => {
        initializeConfig(VALID_OVERRIDES);

        const config = getConfig();

        expect(config).toHaveProperty("display");
        expect(config).toHaveProperty("backend");
        expect(config).toHaveProperty("reconnect");
        expect(config).toHaveProperty("rotation");
        expect(config).toHaveProperty("snapshot");
        expect(config).toHaveProperty("idle");
        expect(config).toHaveProperty("alerts");
        expect(config).toHaveProperty("announcements");
        expect(config).toHaveProperty("features");
    });


    it("returns a copy rather than the internal configuration", () => {
        initializeConfig(VALID_OVERRIDES);

        const configA = getConfig();
        const configB = getConfig();

        expect(configA)
            .not.toBe(configB);

        expect(configA.display)
            .not.toBe(configB.display);
    });


    it("prevents external mutation of internal configuration", () => {
        initializeConfig({
            display: {
                id: "DISPLAY-001",
            },
        });

        const config = getConfig();

        config.display.id = "HACKED";

        expect(getConfig().display.id)
            .toBe("DISPLAY-001");
    });
});


/*
|--------------------------------------------------------------------------
| getConfigValue()
|--------------------------------------------------------------------------
*/

describe("getConfigValue()", () => {
    beforeEach(() => {
        initializeConfig(VALID_OVERRIDES);
    });


    it("retrieves a nested configuration value", () => {
        expect(
            getConfigValue("display.id")
        ).toBe("DISPLAY-001");
    });


    it("retrieves deeply nested values", () => {
        expect(
            getConfigValue(
                "backend.connectionTimeoutMs"
            )
        ).toBe(15000);
    });


    it("returns undefined for an unknown path", () => {
        expect(
            getConfigValue("display.doesNotExist")
        ).toBeUndefined();
    });


    it("returns undefined for an unknown nested path", () => {
        expect(
            getConfigValue(
                "backend.doesNotExist.value"
            )
        ).toBeUndefined();
    });


    it("rejects an invalid path argument", () => {
        expect(() => {
            getConfigValue("");
        }).toThrow();

        expect(() => {
            getConfigValue(null);
        }).toThrow();
    });
});


/*
|--------------------------------------------------------------------------
| Reset
|--------------------------------------------------------------------------
*/

describe("resetConfig()", () => {
    it("restores the default configuration", () => {
        initializeConfig({
            display: {
                id: "CUSTOM-DISPLAY",
            },
        });

        resetConfig();

        const config = getConfig();

        expect(config.display.id)
            .not.toBe("CUSTOM-DISPLAY");
    });


    it("allows configuration to be initialized again after reset", () => {
        initializeConfig({
            display: {
                id: "DISPLAY-001",
            },
        });

        resetConfig();

        initializeConfig({
            display: {
                id: "DISPLAY-002",
            },
        });

        expect(getConfig().display.id)
            .toBe("DISPLAY-002");
    });
});

