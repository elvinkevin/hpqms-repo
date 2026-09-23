/* ==========================================================================
   HPQMS Staff Login Controller
   js/staff-login.js
   --------------------------------------------------------------------------
   Responsible only for:
     - Login form interaction
     - Client-side validation
     - Calling the authentication API
     - Session establishment
     - Login error presentation
     - Redirecting to the staff dashboard

   It does NOT:
     - manage queue state
     - manage WebSockets
     - determine workspace
     - render dashboard components
   ========================================================================== */

import {
    login,
    getCurrentUser,
} from "./staff-api.js";

import {
    getSession,
} from "./staff-session.js";


/* ==========================================================================
   DOM REFERENCES
   ========================================================================== */

const elements = {
    loginForm: document.getElementById("loginForm"),

    employeeIdInput: document.getElementById("employeeId"),
    passwordInput: document.getElementById("password"),

    passwordToggle: document.getElementById("passwordToggle"),
    rememberMe: document.getElementById("rememberMe"),

    submitBtn: document.getElementById("submitBtn"),

    successMessage: document.getElementById("successMessage"),

    employeeIdError: document.getElementById("employeeIdError"),
    passwordError: document.getElementById("passwordError"),
};


/* ==========================================================================
   VALIDATION
   ========================================================================== */

function validateEmployeeId() {
    const value = elements.employeeIdInput.value.trim();

    if (!value) {
        showError(
            elements.employeeIdInput,
            elements.employeeIdError,
            "Employee ID is required"
        );

        return false;
    }

    /*
     * Keep this validation deliberately lightweight.
     * The backend remains authoritative for employee ID format.
     */
    if (value.length > 50) {
        showError(
            elements.employeeIdInput,
            elements.employeeIdError,
            "Employee ID is invalid"
        );

        return false;
    }

    clearError(
        elements.employeeIdInput,
        elements.employeeIdError
    );

    return true;
}


function validatePassword() {
    const value = elements.passwordInput.value;

    if (!value) {
        showError(
            elements.passwordInput,
            elements.passwordError,
            "Password is required"
        );

        return false;
    }

    /*
     * Do not enforce arbitrary password policy here.
     * Authentication policy belongs to the backend.
     */
    clearError(
        elements.passwordInput,
        elements.passwordError
    );

    return true;
}


function showError(input, errorElement, message) {
    input.classList.add("error");

    errorElement.textContent = message;
    errorElement.classList.add("show");
}


function clearError(input, errorElement) {
    input.classList.remove("error");
    errorElement.classList.remove("show");
}


/* ==========================================================================
   UI STATE
   ========================================================================== */

function setLoading(isLoading) {
    elements.submitBtn.disabled = isLoading;

    if (isLoading) {
        elements.submitBtn.classList.add("loading");
        elements.submitBtn.innerHTML =
            '<span class="spinner"></span> Signing in...';
    } else {
        elements.submitBtn.classList.remove("loading");
        elements.submitBtn.innerHTML = "Sign In";
    }
}


function clearLoginErrors() {
    clearError(
        elements.employeeIdInput,
        elements.employeeIdError
    );

    clearError(
        elements.passwordInput,
        elements.passwordError
    );
}


/* ==========================================================================
   ERROR HANDLING
   ========================================================================== */

function getLoginErrorMessage(error) {
    const status = error?.status;

    if (status === 401) {
        return "Invalid employee ID or password.";
    }

    if (status === 403) {
        return "Your account is not authorized to access the staff system.";
    }

    if (status === 429) {
        return "Too many login attempts. Please try again later.";
    }

    if (status >= 500) {
        return "The hospital system is temporarily unavailable.";
    }

    if (
        error instanceof TypeError ||
        error?.message?.toLowerCase().includes("network")
    ) {
        return "Unable to connect to the hospital system.";
    }

    return "Unable to sign in. Please try again.";
}


function showLoginFailure(error) {
    const message = getLoginErrorMessage(error);

    /*
     * Authentication errors should not reveal whether an employee ID
     * exists. Display the same generic credential failure for 401.
     */
    showError(
        elements.employeeIdInput,
        elements.employeeIdError,
        message
    );
}


/* ==========================================================================
   PASSWORD VISIBILITY
   ========================================================================== */

function initializePasswordToggle() {
    elements.passwordToggle?.addEventListener(
        "click",
        () => {
            const isPassword =
                elements.passwordInput.type === "password";

            elements.passwordInput.type =
                isPassword ? "text" : "password";

            const label =
                isPassword
                    ? "Hide password"
                    : "Show password";

            elements.passwordToggle.setAttribute(
                "aria-label",
                label
            );

            elements.passwordToggle.setAttribute(
                "title",
                label
            );
        }
    );
}


/* ==========================================================================
   REMEMBERED EMPLOYEE ID
   ========================================================================== */

const REMEMBERED_EMPLOYEE_KEY =
    "hpqms_remembered_employee";


function loadRememberedEmployee() {
    const remembered =
        window.localStorage.getItem(
            REMEMBERED_EMPLOYEE_KEY
        );

    if (!remembered) {
        return;
    }

    elements.employeeIdInput.value = remembered;
    elements.rememberMe.checked = true;

    elements.passwordInput.focus();
}


function saveRememberedEmployee(employeeId) {
    if (elements.rememberMe.checked) {
        window.localStorage.setItem(
            REMEMBERED_EMPLOYEE_KEY,
            employeeId
        );
    } else {
        window.localStorage.removeItem(
            REMEMBERED_EMPLOYEE_KEY
        );
    }
}


/* ==========================================================================
   LOGIN
   ========================================================================== */

async function handleLogin(event) {
    event.preventDefault();

    clearLoginErrors();

    const employeeIdValid =
        validateEmployeeId();

    const passwordValid =
        validatePassword();

    if (!employeeIdValid || !passwordValid) {
        return;
    }

    const employeeId =
        elements.employeeIdInput.value.trim();

    const password =
        elements.passwordInput.value;

    const rememberMe =
        elements.rememberMe.checked;

    setLoading(true);

    try {
        const auth = await login(
            {
                employee_id: employeeId,
                password,
            },
            rememberMe
        );

        /*
         * Store only the employee ID for convenience.
         * The password is never persisted.
         */
        saveRememberedEmployee(employeeId);

        elements.successMessage?.classList.add("show");

        /*
         * Authentication succeeded.
         * The dashboard now becomes responsible for loading /auth/me.
         */
        window.location.href = auth?.staff?.role === "ADMIN"
            ? "./admin.html"
            : "./staff-v2.html";

    } catch (error) {
        console.error(
            "[StaffLogin] Login failed:",
            error
        );

        showLoginFailure(error);

    } finally {
        setLoading(false);
    }
}


/* ==========================================================================
   INPUT EVENTS
   ========================================================================== */

function initializeValidation() {
    elements.employeeIdInput?.addEventListener(
        "blur",
        validateEmployeeId
    );

    elements.passwordInput?.addEventListener(
        "blur",
        validatePassword
    );

    elements.employeeIdInput?.addEventListener(
        "input",
        () => {
            if (
                elements.employeeIdError.classList.contains("show")
            ) {
                clearError(
                    elements.employeeIdInput,
                    elements.employeeIdError
                );
            }
        }
    );

    elements.passwordInput?.addEventListener(
        "input",
        () => {
            if (
                elements.passwordError.classList.contains("show")
            ) {
                clearError(
                    elements.passwordInput,
                    elements.passwordError
                );
            }
        }
    );
}


/* ==========================================================================
   EXISTING SESSION
   ========================================================================== */

async function redirectIfAlreadyAuthenticated() {
    const session = getSession();

    if (!session?.accessToken) {
        return false;
    }

    getCurrentUser()
        .then((user) => {
            window.location.replace(user.role === "ADMIN" ? "./admin.html" : "./staff-v2.html");
        })
        .catch(() => window.location.replace("./staff-v2.html"));

    return true;
}


/* ==========================================================================
   INITIALIZATION
   ========================================================================== */

async function initialize() {
    if (!elements.loginForm) {
        console.error(
            "[StaffLogin] Login form was not found."
        );

        return;
    }

    /*
     * If a valid persisted session exists, don't show the login form
     * again unnecessarily.
     */
    if (await redirectIfAlreadyAuthenticated()) {
        return;
    }

    initializePasswordToggle();
    initializeValidation();

    loadRememberedEmployee();

    elements.loginForm.addEventListener(
        "submit",
        handleLogin
    );
}


if (document.readyState === "loading") {
    document.addEventListener(
        "DOMContentLoaded",
        initialize
    );
} else {
    initialize();
}
