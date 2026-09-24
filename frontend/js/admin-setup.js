import { completeAdminSetup } from "./staff-api.js";
import { saveSession } from "./staff-session.js";

const SETUP_TOKEN_KEY = "hpqms_admin_setup_token";
const form = document.querySelector("[data-admin-setup-form]");
const errorBox = document.querySelector("[data-error]");
const submitButton = form?.querySelector("button[type=submit]");
const submitLabel = form?.querySelector("[data-submit-label]");
const spinner = form?.querySelector(".setup-spinner");

if (!sessionStorage.getItem(SETUP_TOKEN_KEY)) {
    window.location.replace("./staff-login.html");
}

form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorBox.hidden = true;

    const values = Object.fromEntries(new FormData(form).entries());
    if (values.new_password !== values.confirm_password) {
        showError("The password confirmation does not match.");
        form.elements.confirm_password.focus();
        return;
    }
    if (new TextEncoder().encode(values.new_password).length > 72) {
        showError("Use a password that is no more than 72 UTF-8 bytes.");
        form.elements.new_password.focus();
        return;
    }
    if (!/[A-Z]/.test(values.new_password) || !/[a-z]/.test(values.new_password) ||
        !/\d/.test(values.new_password) || !/[^A-Za-z0-9]/.test(values.new_password)) {
        showError("Use uppercase and lowercase letters, a number, and a symbol in your password.");
        form.elements.new_password.focus();
        return;
    }

    setBusy(true);
    try {
        const result = await completeAdminSetup({
            setup_token: sessionStorage.getItem(SETUP_TOKEN_KEY),
            first_name: values.first_name,
            last_name: values.last_name,
            new_password: values.new_password,
        });
        if (!result?.access_token || !result?.refresh_token) {
            throw new Error("Setup completed, but the secure session could not be started. Sign in again with your new password.");
        }
        sessionStorage.removeItem(SETUP_TOKEN_KEY);
        saveSession(result.access_token, false);
        window.location.replace("./admin.html");
    } catch (error) {
        if (error.status === 401 || error.status === 409) {
            sessionStorage.removeItem(SETUP_TOKEN_KEY);
            showError(`${error.message} Return to sign in and start again.`);
        } else {
            showError(error.message || "Administrator setup could not be completed.");
        }
    } finally {
        setBusy(false);
    }
});

function setBusy(busy) {
    submitButton.disabled = busy;
    submitLabel.textContent = busy ? "Securing your account…" : "Complete setup";
    spinner.hidden = !busy;
}

function showError(message) {
    errorBox.textContent = message;
    errorBox.hidden = false;
}
