/**
 * ==========================================================================
 * HPQMS Public Patient Display Board
 * renderer.js — DOM Presentation Layer
 * ==========================================================================
 *
 * Responsibilities:
 * - Render display state into the DOM
 * - Render department queue information
 * - Render announcements
 * - Render pagination
 * - Render connection status
 * - Render loading / empty states
 *
 * Non-responsibilities:
 * - No WebSocket communication
 * - No queue state ownership
 * - No timers
 * - No rotation logic
 * - No alert queue management
 * - No backend communication
 *
 * The renderer receives state and turns it into presentation.
 * ========================================================================== */


/* ==========================================================================
   CONSTANTS
   ========================================================================== */

const SELECTORS = Object.freeze({
    facilityName: "#facility-name",

    connectionIndicator: "#connection-indicator",
    connectionText: "#connection-text",

    primaryViewport: "#primary-viewport",
    viewportLoader: "#viewport-loader",

    announcementWrapper: "#announcement-wrapper",
    announcementText: "#announcement-text",

    paginationIndicator: "#pagination-indicator",
    paginationText: "#pagination-text",
    paginationDots: "#pagination-dots",
});


const CONNECTION_STATES = Object.freeze({
    CONNECTING: "CONNECTING",
    CONNECTED: "CONNECTED",
    DISCONNECTED: "DISCONNECTED",
});


const MAX_RECENT_TOKENS = 5;


/* ==========================================================================
   INTERNAL STATE
   ========================================================================== */

let initialized = false;


/* ==========================================================================
   DOM HELPERS
   ========================================================================== */

/**
 * Resolve a DOM element.
 *
 * Throws a clear error when a required element is missing.
 */
function getElement(selector) {
    const element = document.querySelector(selector);

    if (!element) {
        throw new Error(
            `Renderer element not found: ${selector}`
        );
    }

    return element;
}


/**
 * Resolve an optional DOM element.
 *
 * Returns null when the element does not exist.
 */
function getOptionalElement(selector) {
    return document.querySelector(selector);
}


/**
 * Safely remove all children from an element.
 */
function clearElement(element) {
    while (element.firstChild) {
        element.removeChild(element.firstChild);
    }
}


/**
 * Create an element with optional class and text content.
 */
function createElement(
    tagName,
    {
        className = "",
        textContent = "",
    } = {}
) {
    const element = document.createElement(tagName);

    if (className) {
        element.className = className;
    }

    if (textContent !== "") {
        element.textContent = textContent;
    }

    return element;
}


/**
 * Normalize a value to a safe display string.
 */
function displayValue(
    value,
    fallback = "—"
) {
    if (
        value === null ||
        value === undefined ||
        value === ""
    ) {
        return fallback;
    }

    return String(value);
}


/* ==========================================================================
   INITIALIZATION
   ========================================================================== */

/**
 * Initialize the renderer.
 *
 * The function only validates that the required DOM shell exists.
 * It does not begin any timers or subscriptions.
 */
function initializeRenderer() {
    getElement(SELECTORS.facilityName);
    getElement(SELECTORS.connectionIndicator);
    getElement(SELECTORS.connectionText);
    getElement(SELECTORS.primaryViewport);
    getElement(SELECTORS.announcementText);
    getElement(SELECTORS.paginationIndicator);
    getElement(SELECTORS.paginationText);
    getElement(SELECTORS.paginationDots);

    initialized = true;

    return true;
}


/**
 * Check whether renderer has been initialized.
 */
function isRendererInitialized() {
    return initialized;
}


/* ==========================================================================
   FACILITY
   ========================================================================== */

/**
 * Render facility branding information.
 */
function renderFacility(
    facilityName
) {
    const element = getElement(
        SELECTORS.facilityName
    );

    element.textContent =
        displayValue(
            facilityName,
            "Hospital"
        );
}


/* ==========================================================================
   DEPARTMENT RENDERING
   ========================================================================== */

/**
 * Create an active token card.
 */
function createActiveTokenElement(token) {
    const item = createElement(
        "article",
        {
            className: "token-card token-card-active",
        }
    );

    const tokenNumber = createElement(
        "div",
        {
            className: "token-number",
            textContent: displayValue(
                token.token_number
            ),
        }
    );

    const status = createElement(
        "span",
        {
            className: "token-status",
            textContent: displayValue(
                token.status
            ),
        }
    );

    item.appendChild(tokenNumber);
    item.appendChild(status);

    if (token.service_point) {
        const servicePoint = createElement(
            "div",
            {
                className: "token-service-point",
                textContent: displayValue(
                    token.service_point
                ),
            }
        );

        item.appendChild(servicePoint);
    }

    return item;
}


/**
 * Create a next-token element.
 */
function createNextTokenElement(token) {
    const item = createElement(
        "li",
        {
            className: "next-token",
        }
    );

    item.textContent = displayValue(
        token.token_number
    );

    return item;
}


/**
 * Create a recently-completed token element.
 */
function createRecentTokenElement(token) {
    const item = createElement(
        "li",
        {
            className: "recent-token",
        }
    );

    item.textContent = displayValue(
        token.token_number
    );

    return item;
}


/**
 * Render a single department.
 *
 * This creates the DOM representation from scratch.
 * It does not retain queue state internally.
 */
function renderDepartment(department) {
    if (!department || typeof department !== "object") {
        throw new TypeError(
            "department must be an object"
        );
    }

    const container = createElement(
        "section",
        {
            className: "department-board",
        }
    );

    container.dataset.departmentId =
        displayValue(
            department.department_id,
            ""
        );

    /* --------------------------------------------------------------
       Department Header
       -------------------------------------------------------------- */

    const header = createElement(
        "header",
        {
            className: "department-header",
        }
    );

    const title = createElement(
        "h2",
        {
            className: "department-name",
            textContent: displayValue(
                department.department_name,
                "Department"
            ),
        }
    );

    header.appendChild(title);
    container.appendChild(header);


    /* --------------------------------------------------------------
       Active Tokens
       -------------------------------------------------------------- */

    const activeSection = createElement(
        "section",
        {
            className: "active-tokens-section",
        }
    );

    const activeHeading = createElement(
        "h3",
        {
            className: "section-title",
            textContent: "NOW SERVING",
        }
    );

    activeSection.appendChild(activeHeading);

    const activeContainer = createElement(
        "div",
        {
            className: "active-tokens",
        }
    );

    const activeTokens =
        Array.isArray(
            department.active_tokens
        )
            ? department.active_tokens
            : [];

    if (activeTokens.length === 0) {
        activeContainer.appendChild(
            createElement(
                "p",
                {
                    className: "empty-state",
                    textContent: "No tokens currently being served",
                }
            )
        );
    } else {
        activeTokens.forEach((token) => {
            activeContainer.appendChild(
                createActiveTokenElement(token)
            );
        });
    }

    activeSection.appendChild(activeContainer);
    container.appendChild(activeSection);


    /* --------------------------------------------------------------
       Queue Summary
       -------------------------------------------------------------- */

    const queueSummary = createElement(
        "section",
        {
            className: "queue-summary",
        }
    );

    const waiting = createElement(
        "div",
        {
            className: "waiting-count",
        }
    );

    const waitingLabel = createElement(
        "span",
        {
            className: "summary-label",
            textContent: "WAITING",
        }
    );

    const waitingValue = createElement(
        "strong",
        {
            className: "summary-value",
            textContent: displayValue(
                department.waiting_count,
                "0"
            ),
        }
    );

    waiting.appendChild(waitingLabel);
    waiting.appendChild(waitingValue);


    const waitTime = createElement(
        "div",
        {
            className: "estimated-wait",
        }
    );

    const waitLabel = createElement(
        "span",
        {
            className: "summary-label",
            textContent: "EST. WAIT",
        }
    );

    const waitValue =
        department.estimated_wait_minutes === null ||
        department.estimated_wait_minutes === undefined
            ? "—"
            : `${department.estimated_wait_minutes} min`;

    const waitValueElement = createElement(
        "strong",
        {
            className: "summary-value",
            textContent: waitValue,
        }
    );

    waitTime.appendChild(waitLabel);
    waitTime.appendChild(waitValueElement);

    queueSummary.appendChild(waiting);
    queueSummary.appendChild(waitTime);

    container.appendChild(queueSummary);


    /* --------------------------------------------------------------
       Next Tokens
       -------------------------------------------------------------- */

    const nextSection = createElement(
        "section",
        {
            className: "next-tokens-section",
        }
    );

    nextSection.appendChild(
        createElement(
            "h3",
            {
                className: "section-title",
                textContent: "NEXT",
            }
        )
    );

    const nextList = createElement(
        "ol",
        {
            className: "next-tokens",
        }
    );

    const nextTokens =
        Array.isArray(
            department.next_tokens
        )
            ? department.next_tokens
            : [];

    nextTokens.forEach((token) => {
        nextList.appendChild(
            createNextTokenElement(token)
        );
    });

    if (nextTokens.length === 0) {
        nextList.appendChild(
            createElement(
                "li",
                {
                    className: "empty-state",
                    textContent: "No patients waiting",
                }
            )
        );
    }

    nextSection.appendChild(nextList);
    container.appendChild(nextSection);


    /* --------------------------------------------------------------
       Recent Tokens
       -------------------------------------------------------------- */

    const recentSection = createElement(
        "section",
        {
            className: "recent-tokens-section",
        }
    );

    recentSection.appendChild(
        createElement(
            "h3",
            {
                className: "section-title",
                textContent: "RECENTLY SERVED",
            }
        )
    );

    const recentList = createElement(
        "ul",
        {
            className: "recent-tokens",
        }
    );

    const recentTokens =
        Array.isArray(
            department.recent_tokens
        )
            ? department.recent_tokens.slice(
                0,
                MAX_RECENT_TOKENS
            )
            : [];

    recentTokens.forEach((token) => {
        recentList.appendChild(
            createRecentTokenElement(token)
        );
    });

    recentSection.appendChild(recentList);
    container.appendChild(recentSection);

    return container;
}


/* ==========================================================================
   SNAPSHOT RENDERING
   ========================================================================== */

/**
 * Render all departments from a display snapshot.
 */
function renderDepartments(
    departments = []
) {
    const viewport = getElement(
        SELECTORS.primaryViewport
    );

    clearElement(viewport);

    if (
        !Array.isArray(departments) ||
        departments.length === 0
    ) {
        renderEmptyState();
        return;
    }

    const fragment =
        document.createDocumentFragment();

    departments.forEach((department) => {
        fragment.appendChild(
            renderDepartment(department)
        );
    });

    viewport.appendChild(fragment);
}


/**
 * Render the complete display snapshot.
 *
 * This is the main renderer entry point.
 */
function renderSnapshot(snapshot) {
    if (!snapshot || typeof snapshot !== "object") {
        throw new TypeError(
            "snapshot must be an object"
        );
    }

    if (!initialized) {
        initializeRenderer();
    }

    renderFacility(
        snapshot.facility_name
    );

    renderDepartments(
        snapshot.departments
    );

    renderAnnouncements(
        snapshot.announcements
    );

    hideLoader();

    return true;
}


/* ==========================================================================
   EMPTY / LOADING STATES
   ========================================================================== */

/**
 * Show the initial renderer loader.
 */
function showLoader(
    message = "Initializing Display Engine..."
) {
    const viewport = getElement(
        SELECTORS.primaryViewport
    );

    clearElement(viewport);

    const loader = createElement(
        "div",
        {
            className: "viewport-loader",
        }
    );

    loader.appendChild(
        createElement(
            "p",
            {
                textContent: message,
            }
        )
    );

    viewport.appendChild(loader);

    return true;
}


/**
 * Hide the loader if it exists.
 */
function hideLoader() {
    const loader = getOptionalElement(
        SELECTORS.viewportLoader
    );

    if (loader) {
        loader.remove();
    }
}


/**
 * Render an empty-state message.
 */
function renderEmptyState(
    message = "No queue information is currently available."
) {
    const viewport = getElement(
        SELECTORS.primaryViewport
    );

    clearElement(viewport);

    const emptyState = createElement(
        "div",
        {
            className: "viewport-empty-state",
        }
    );

    emptyState.appendChild(
        createElement(
            "p",
            {
                textContent: message,
            }
        )
    );

    viewport.appendChild(emptyState);

    return true;
}


/* ==========================================================================
   ANNOUNCEMENTS
   ========================================================================== */

/**
 * Render active announcements.
 *
 * The public ticker only displays the first active announcement.
 * The complete announcement collection remains owned by display-state.js.
 */
function renderAnnouncements(
    announcements = []
) {
    const wrapper = getElement(
        SELECTORS.announcementWrapper
    );

    const text = getElement(
        SELECTORS.announcementText
    );

    if (
        !Array.isArray(announcements) ||
        announcements.length === 0
    ) {
        text.textContent =
            "Welcome. Please have your token ready.";

        wrapper.dataset.priority = "INFO";

        return true;
    }

    const activeAnnouncements =
        announcements.filter(
            (announcement) =>
                announcement &&
                typeof announcement.message === "string" &&
                announcement.message.trim().length > 0
        );

    if (activeAnnouncements.length === 0) {
        text.textContent =
            "Welcome. Please have your token ready.";

        wrapper.dataset.priority = "INFO";

        return true;
    }

    const announcement =
        activeAnnouncements[0];

    text.textContent =
        announcement.message;

    wrapper.dataset.priority =
        displayValue(
            announcement.priority,
            "INFO"
        );

    return true;
}


/* ==========================================================================
   CONNECTION STATUS
   ========================================================================== */

/**
 * Render the current server connection status.
 */
function renderConnectionStatus(
    status
) {
    if (
        typeof status !== "string"
    ) {
        throw new TypeError(
            "connection status must be a string"
        );
    }

    const normalizedStatus =
        status.toUpperCase();

    if (
        !Object.prototype.hasOwnProperty.call(
            CONNECTION_STATES,
            normalizedStatus
        )
    ) {
        throw new RangeError(
            `Unknown connection status: ${status}`
        );
    }

    const indicator = getElement(
        SELECTORS.connectionIndicator
    );

    const text = getElement(
        SELECTORS.connectionText
    );

    indicator.dataset.status =
        normalizedStatus;

    indicator.setAttribute(
        "aria-label",
        `Server Connection Status: ${normalizedStatus}`
    );

    text.textContent =
        normalizedStatus;

    return true;
}


/* ==========================================================================
   PAGINATION
   ========================================================================== */

/**
 * Render pagination information.
 *
 * The renderer doesn't control which page is active.
 * It only presents the values supplied by the caller.
 */
function renderPagination(
    currentPage = 1,
    totalPages = 1
) {
    if (
        !Number.isInteger(currentPage) ||
        currentPage < 1
    ) {
        throw new RangeError(
            "currentPage must be a positive integer"
        );
    }

    if (
        !Number.isInteger(totalPages) ||
        totalPages < 1
    ) {
        throw new RangeError(
            "totalPages must be a positive integer"
        );
    }

    const indicator = getElement(
        SELECTORS.paginationIndicator
    );

    const text = getElement(
        SELECTORS.paginationText
    );

    const dots = getElement(
        SELECTORS.paginationDots
    );

    text.textContent =
        `PAGE ${currentPage} OF ${totalPages}`;

    clearElement(dots);

    for (
        let index = 1;
        index <= totalPages;
        index += 1
    ) {
        const dot = createElement(
            "span",
            {
                className:
                    index === currentPage
                        ? "pagination-dot active"
                        : "pagination-dot",
            }
        );

        dot.setAttribute(
            "aria-hidden",
            "true"
        );

        dots.appendChild(dot);
    }

    indicator.hidden =
        totalPages <= 1;

    return true;
}


/* ==========================================================================
   RENDERER STATE / CLEANUP
   ========================================================================== */

/**
 * Clear the main viewport.
 */
function clearRenderer() {
    const viewport = getElement(
        SELECTORS.primaryViewport
    );

    clearElement(viewport);

    return true;
}


/**
 * Return renderer metadata.
 *
 * Renderer intentionally does not own application state.
 */
function getRendererState() {
    return {
        initialized,
    };
}


/* ==========================================================================
   PUBLIC API
   ========================================================================== */

export {
    initializeRenderer,
    isRendererInitialized,

    renderSnapshot,
    renderFacility,
    renderDepartments,
    renderDepartment,

    renderAnnouncements,
    renderConnectionStatus,
    renderPagination,

    showLoader,
    hideLoader,
    renderEmptyState,

    clearRenderer,
    getRendererState,
};