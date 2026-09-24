import { completeStaffPasswordChange } from "./staff-api.js";
import { saveSession } from "./staff-session.js";

const TOKEN_KEY = "hpqms_password_change_token";
const form = document.querySelector("[data-password-change-form]");
const errorBox = document.querySelector("[data-error]");
const submitButton = form?.querySelector("button[type=submit]");
const submitLabel = form?.querySelector("[data-submit-label]");
const spinner = form?.querySelector(".setup-spinner");

if (!sessionStorage.getItem(TOKEN_KEY)) {
    window.location.replace("./staff-login.html");
}

form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorBox.hidden = true;
    const values = Object.fromEntries(new FormData(form).entries());
    if (values.new_password !== values.confirm_password) {
        return showError("The password confirmation does not match.");
    }
    if (new TextEncoder().encode(values.new_password).length > 72) {
        return showError("Use a password that is no more than 72 UTF-8 bytes.");
    }
    if (!/[A-Z]/.test(values.new_password) || !/[a-z]/.test(values.new_password) ||
        !/\d/.test(values.new_password) || !/[^A-Za-z0-9]/.test(values.new_password)) {
        return showError("Use uppercase and lowercase letters, a number, and a symbol.");
    }

    setBusy(true);
    try {
        const result = await completeStaffPasswordChange({
            password_change_token: sessionStorage.getItem(TOKEN_KEY),
            new_password: values.new_password,
        });
        if (!result?.access_token || !result?.refresh_token) {
            throw new Error("Password saved, but a secure session could not be started. Sign in again with your new password.");
        }
        sessionStorage.removeItem(TOKEN_KEY);
        sessionStorage.removeItem("hpqms_admin_setup_token");
        saveSession(result.access_token, false);
        window.location.replace(result.staff?.role === "ADMIN" ? "./admin.html" : "./staff-v2.html");
    } catch (error) {
        if (error.status === 401 || error.status === 409) sessionStorage.removeItem(TOKEN_KEY);
        showError(error.message || "Your password could not be changed.");
    } finally {
        setBusy(false);
    }
});

function setBusy(busy) {
    submitButton.disabled = busy;
    submitLabel.textContent = busy ? "Saving password…" : "Save password";
    spinner.hidden = !busy;
}

function showError(message) {
    errorBox.textContent = message;
    errorBox.hidden = false;
}
