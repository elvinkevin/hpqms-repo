/* ==========================================================================
   HPQMS Public Patient Display Board
   js/rotation-manager.js — Department Rotation Manager
   ========================================================================== */

/*
 * Responsibilities:
 *
 *   - Maintain the list of departments available for rotation
 *   - Track the currently displayed department
 *   - Rotate departments on a configurable interval
 *   - Allow manual department selection
 *   - Allow app.js to focus a specific department
 *   - Support starting/stopping rotation
 *   - Temporarily focus a department for priority events
 *   - Restore normal rotation after priority focus
 *
 * This module does NOT:
 *
 *   - access the DOM
 *   - render anything
 *   - communicate with the backend
 *   - mutate display-state.js
 *   - decide how departments are visually displayed
 *
 * Presentation is handled by app.js / renderer.js.
 */


/* ==========================================================================
   Constants
   ========================================================================== */

const DEFAULT_OPTIONS = Object.freeze({
    rotationIntervalMs: 15000,
    priorityFocusDurationMs: 10000,
    onDepartmentChange: null,
});


/* ==========================================================================
   Internal State
   ========================================================================== */

let initialized = false;

let options = {
    ...DEFAULT_OPTIONS,
};

let departments = [];

let currentIndex = -1;

let rotationTimer = null;

let rotationActive = false;

let priorityFocusActive = false;

let priorityFocusTimer = null;

let onDepartmentChange = null;


/* ==========================================================================
   Utility Functions
   ========================================================================== */

/**
 * Validate that a department has the minimum structure
 * required by the rotation manager.
 */
function isValidDepartment(department) {
    return (
        department !== null &&
        typeof department === "object" &&
        typeof department.dept_id === "string"
    );
}


/**
 * Validate a department collection.
 */
function validateDepartments(value) {
    if (!Array.isArray(value)) {
        throw new TypeError(
            "Departments must be an array"
        );
    }

    for (const department of value) {
        if (!isValidDepartment(department)) {
            throw new TypeError(
                "Each department must contain a string dept_id"
            );
        }
    }
}


/**
 * Return a defensive copy of a department.
 */
function cloneDepartment(department) {
    if (!department) {
        return null;
    }

    return {
        ...department,

        active_tokens:
            Array.isArray(department.active_tokens)
                ? department.active_tokens.map(
                    (token) => ({ ...token })
                )
                : department.active_tokens,

        next_tokens:
            Array.isArray(department.next_tokens)
                ? department.next_tokens.map(
                    (token) => ({ ...token })
                )
                : department.next_tokens,

        recent_tokens:
            Array.isArray(department.recent_tokens)
                ? department.recent_tokens.map(
                    (token) => ({ ...token })
                )
                : department.recent_tokens,
    };
}


/**
 * Return a defensive copy of the department list.
 */
function cloneDepartments() {
    return departments.map(
        cloneDepartment
    );
}


/**
 * Find the index of a department by ID.
 */
function findDepartmentIndex(departmentId) {
    return departments.findIndex(
        (department) =>
            department.dept_id ===
            departmentId
    );
}


/**
 * Clear the normal rotation timer.
 */
function clearRotationTimer() {
    if (rotationTimer !== null) {
        clearInterval(rotationTimer);

        rotationTimer = null;
    }
}


/**
 * Clear the priority focus timer.
 */
function clearPriorityFocusTimer() {
    if (priorityFocusTimer !== null) {
        clearTimeout(priorityFocusTimer);

        priorityFocusTimer = null;
    }
}


function notifyDepartmentChange(reason) {
    if (typeof onDepartmentChange === "function") {
        onDepartmentChange(
            getCurrentDepartment(),
            reason
        );
    }
}


/**
 * Move to the next department.
 */
function advanceRotation() {
    if (
        !initialized ||
        !rotationActive ||
        priorityFocusActive ||
        departments.length <= 1
    ) {
        return null;
    }

    currentIndex =
        (currentIndex + 1) %
        departments.length;

    const currentDepartment =
        getCurrentDepartment();

    notifyDepartmentChange("ROTATION_ADVANCED");

    return currentDepartment;
}


/* ==========================================================================
   Initialization
   ========================================================================== */

/**
 * Initialize the rotation manager.
 */
function initialize(customOptions = {}) {
    if (
        customOptions === null ||
        typeof customOptions !== "object"
    ) {
        throw new TypeError(
            "Rotation manager options must be an object"
        );
    }

    const mergedOptions = {
        ...DEFAULT_OPTIONS,
        ...customOptions,
    };

    if (
        !Number.isFinite(
            mergedOptions.rotationIntervalMs
        ) ||
        mergedOptions.rotationIntervalMs <= 0
    ) {
        throw new RangeError(
            "rotationIntervalMs must be positive"
        );
    }

    if (
        !Number.isFinite(
            mergedOptions.priorityFocusDurationMs
        ) ||
        mergedOptions.priorityFocusDurationMs <= 0
    ) {
        throw new RangeError(
            "priorityFocusDurationMs must be positive"
        );
    }

    if (
        mergedOptions.onDepartmentChange !== null &&
        typeof mergedOptions.onDepartmentChange !== "function"
    ) {
        throw new TypeError(
            "onDepartmentChange must be a function or null"
        );
    }

    options = mergedOptions;

    onDepartmentChange =
        mergedOptions.onDepartmentChange;

    initialized = true;

    return getState();
}


/* ==========================================================================
   Department Management
   ========================================================================== */

/**
 * Replace the department collection.
 *
 * This should normally be called whenever display-state
 * receives a fresh authoritative snapshot.
 */
function setDepartments(newDepartments) {
    if (!initialized) {
        return false;
    }

    validateDepartments(newDepartments);

    const previousDepartmentId =
        getCurrentDepartment()?.dept_id;

    departments =
        newDepartments.map(
            cloneDepartment
        );

    /*
     * Preserve the currently displayed department
     * if it still exists in the new snapshot.
     */
    if (previousDepartmentId) {
        const preservedIndex =
            findDepartmentIndex(
                previousDepartmentId
            );

        if (preservedIndex !== -1) {
            currentIndex =
                preservedIndex;

            notifyDepartmentChange("DEPARTMENTS_UPDATED");

            return true;
        }
    }

    /*
     * Otherwise select the first department.
     */
    currentIndex =
        departments.length > 0
            ? 0
            : -1;

    notifyDepartmentChange("DEPARTMENTS_UPDATED");

    return true;
}


/**
 * Return all departments.
 */
function getDepartments() {
    return cloneDepartments();
}


/* ==========================================================================
   Current Department
   ========================================================================== */

/**
 * Return the currently selected department.
 */
function getCurrentDepartment() {
    if (
        currentIndex < 0 ||
        currentIndex >= departments.length
    ) {
        return null;
    }

    return cloneDepartment(
        departments[currentIndex]
    );
}


/**
 * Select a department by ID.
 */
function selectDepartment(departmentId) {
    if (!initialized) {
        return false;
    }

    if (
        typeof departmentId !== "string" ||
        departmentId.length === 0
    ) {
        throw new TypeError(
            "departmentId must be a non-empty string"
        );
    }

    const index =
        findDepartmentIndex(
            departmentId
        );

    if (index === -1) {
        return false;
    }

    currentIndex = index;

    notifyDepartmentChange("DEPARTMENT_SELECTED");

    return true;
}


/**
 * Move to the next department manually.
 */
function nextDepartment() {
    if (!initialized) {
        return null;
    }

    if (departments.length === 0) {
        return null;
    }

    if (departments.length === 1) {
        currentIndex = 0;

        const currentDepartment =
            getCurrentDepartment();

        notifyDepartmentChange("DEPARTMENT_SELECTED");

        return currentDepartment;
    }

    currentIndex =
        (currentIndex + 1) %
        departments.length;

    const currentDepartment =
        getCurrentDepartment();

    notifyDepartmentChange("DEPARTMENT_SELECTED");

    return currentDepartment;
}


/**
 * Move to the previous department manually.
 */
function previousDepartment() {
    if (!initialized) {
        return null;
    }

    if (departments.length === 0) {
        return null;
    }

    if (departments.length === 1) {
        currentIndex = 0;

        const currentDepartment =
            getCurrentDepartment();

        notifyDepartmentChange("DEPARTMENT_SELECTED");

        return currentDepartment;
    }

    currentIndex =
        (currentIndex - 1 +
            departments.length) %
        departments.length;

    const currentDepartment =
        getCurrentDepartment();

    notifyDepartmentChange("DEPARTMENT_SELECTED");

    return currentDepartment;
}


/* ==========================================================================
   Automatic Rotation
   ========================================================================== */


/**
 * Arm the rotation timer, replacing any existing one.
 * Internal use only — bypasses the "already active" guard
 * so focus-resume logic can force a restart.
 */
function armRotationTimer() {
    clearRotationTimer();

    rotationActive = true;

    rotationTimer = setInterval(() => {
        advanceRotation();
    }, options.rotationIntervalMs);
}

function startRotation() {
    if (!initialized) return false;

    if (departments.length <= 1) {
        rotationActive = false;
        clearRotationTimer();
        return false;
    }

    if (rotationActive) {
        return true;
    }

    armRotationTimer();

    return true;
}

function stopRotation() {
    rotationActive = false;
    clearRotationTimer();
    return true;
}
/**
 * Check whether automatic rotation is active.
 */
function isRotationActive() {
    return rotationActive;
}


/* ==========================================================================
   Priority Department Focus
   ========================================================================== */

/**
 * Temporarily focus a department because of a
 * high-priority event.
 *
 * Example:
 *
 *   TOKEN_CALLED
 *   priority = CRITICAL
 *   dept_id = emergency department
 *
 * The display can immediately switch to that department.
 */
function focusDepartment(
    departmentId,
    durationMs = options.priorityFocusDurationMs
) {
    if (!initialized) {
        return false;
    }

    if (
        typeof departmentId !== "string" ||
        departmentId.length === 0
    ) {
        throw new TypeError(
            "departmentId must be a non-empty string"
        );
    }

    if (
        !Number.isFinite(durationMs) ||
        durationMs <= 0
    ) {
        throw new RangeError(
            "durationMs must be positive"
        );
    }

    const index =
        findDepartmentIndex(
            departmentId
        );

    if (index === -1) {
        return false;
    }

    /*
     * Select the target department immediately.
     */
    currentIndex = index;

    notifyDepartmentChange("PRIORITY_FOCUS_STARTED");

    /*
     * Temporarily suspend normal rotation.
     */
    priorityFocusActive = true;

    clearRotationTimer();

    clearPriorityFocusTimer();

    priorityFocusTimer = setTimeout(() => {
        priorityFocusActive = false;
        priorityFocusTimer = null;

        if (rotationActive) {
            armRotationTimer();
        }

        notifyDepartmentChange("PRIORITY_FOCUS_ENDED");
}, durationMs);

    return true;
}


/**
 * Cancel an active priority focus.
 */
function clearPriorityFocus() {
    clearPriorityFocusTimer();

    priorityFocusActive = false;

    if (rotationActive) {
        armRotationTimer();
    }

    notifyDepartmentChange("PRIORITY_FOCUS_CLEARED");

    return true;
}


/**
 * Check whether priority focus is active.
 */
function isPriorityFocusActive() {
    return priorityFocusActive;
}


/* ==========================================================================
   State
   ========================================================================== */

/**
 * Return the manager's current state.
 */
function getState() {
    return {
        initialized,

        departments:
            cloneDepartments(),

        currentIndex,

        currentDepartment:
            getCurrentDepartment(),

        rotationActive,

        priorityFocusActive,

        departmentCount:
            departments.length,
    };
}


/* ==========================================================================
   Reset
   ========================================================================== */

/**
 * Completely reset the rotation manager.
 */
function reset() {
    clearRotationTimer();

    clearPriorityFocusTimer();

    initialized = false;

    options = {
        ...DEFAULT_OPTIONS,
    };

    departments = [];

    currentIndex = -1;

    rotationActive = false;

    priorityFocusActive = false;

    onDepartmentChange = null;
}


/* ==========================================================================
   Public API
   ========================================================================== */

export {
    DEFAULT_OPTIONS,

    initialize,

    setDepartments,
    getDepartments,

    getCurrentDepartment,
    selectDepartment,
    nextDepartment,
    previousDepartment,

    startRotation,
    stopRotation,
    isRotationActive,

    focusDepartment,
    clearPriorityFocus,
    isPriorityFocusActive,

    getState,

    reset,
};
