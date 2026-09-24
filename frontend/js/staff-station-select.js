/* ==========================================================================
   HPQMS Station Gate Controller
   js/staff-station-select.js

   Post-login interstitial: the staff member picks the physical service
   point they are working from this shift, then proceeds to the dashboard.

   Flow:
     1. Require an authenticated session (redirect to login otherwise).
     2. Load the department's service points.
     3. On continue → POST /auth/me/station/bind → redirect to dashboard.
     4. "Skip for now" proceeds unbound — the dashboard pill shows Offline.
   ========================================================================== */

import { request, HTTP_METHOD } from "./api.js";
import { getSession, getAccessToken, clearSession } from "./staff-session.js";
import { getDepartments } from "./staff-api.js";

const elements = {
    greeting: document.getElementById("greetingText"),
    error: document.getElementById("gateError"),
    stationList: document.getElementById("stationList"),
    continueBtn: document.getElementById("continueBtn"),
    skipBtn: document.getElementById("skipBtn"),
};

let servicePoints = [];
let selectedId = null;
let submitting = false;
let currentDepartmentName = "your department";

/* ==========================================================================
   AUTH GUARD
   ========================================================================== */

function requireSession() {
    if (!getSession()?.accessToken) {
        window.location.replace("./staff-login.html");
        return false;
    }

    return true;
}

/* ==========================================================================
   API
   ========================================================================== */

function buildAuthHeaders() {
    const token = getAccessToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
}

async function loadCurrentUser() {
    return request("/auth/me", {
        method: HTTP_METHOD.GET,
        headers: buildAuthHeaders(),
    });
}

async function bindStation(servicePointId) {
    return request("/auth/me/station/bind", {
        method: HTTP_METHOD.POST,
        headers: buildAuthHeaders(),
        body: { service_point_id: servicePointId },
    });
}

/* ==========================================================================
   RENDER
   ========================================================================== */

function showError(message) {
    if (!elements.error) return;

    elements.error.textContent = message;
    elements.error.classList.add("show");
}

function clearError() {
    elements.error?.classList.remove("show");
}

function renderStationList() {
    if (!elements.stationList) return;

    if (!servicePoints.length) {
        elements.stationList.innerHTML = `
            <div class="station-list-empty">
                No active service points are configured for ${escapeHtml(currentDepartmentName)}.
                Ask an administrator to set them up, or skip for now.
            </div>
        `;
        return;
    }

    elements.stationList.innerHTML = servicePoints.map((sp) => {
        const occupied = Boolean(sp.occupied);
        const disabled = occupied ? "disabled" : "";

        return `
            <label class="station-option ${occupied ? "occupied" : ""}" data-id="${escapeAttr(sp.service_point_id)}">
                <input type="radio" name="station" value="${escapeAttr(sp.service_point_id)}" ${disabled} />
                <span class="station-option-label">
                    ${escapeHtml(sp.label)}
                    <span class="station-option-code">${escapeHtml(sp.code)}</span>
                </span>
                <span class="station-option-type">${escapeHtml(sp.station_type ?? "COUNTER")}</span>
                ${occupied ? `<span class="station-option-occupied-tag">Occupied</span>` : ""}
            </label>
        `;
    }).join("");

    elements.stationList.querySelectorAll('input[type="radio"]').forEach((radio) => {
        radio.addEventListener("change", () => {
            if (!radio.checked) return;

            selectedId = radio.value;
            clearError();

            elements.stationList
                .querySelectorAll(".station-option")
                .forEach((option) => option.classList.remove("selected"));

            radio.closest(".station-option")?.classList.add("selected");

            if (elements.continueBtn) elements.continueBtn.disabled = false;
        });
    });
}

/* ==========================================================================
   ACTIONS
   ========================================================================== */

async function handleContinue() {
    if (!selectedId || submitting) return;

    submitting = true;
    clearError();

    if (elements.continueBtn) {
        elements.continueBtn.disabled = true;
        elements.continueBtn.textContent = "Binding station…";
    }

    try {
        await bindStation(selectedId);
        window.location.href = "./staff-v2.html";
    } catch (error) {
        showError(
            error?.message ||
            "Unable to bind the selected station. Please try again."
        );

        submitting = false;
        if (elements.continueBtn) {
            elements.continueBtn.disabled = false;
            elements.continueBtn.textContent = "Continue to Dashboard";
        }
    }
}

function handleSkip() {
    /*
     * Proceed unbound. The dashboard pill renders the Offline state and
     * station binding can happen later via the pill's switch popover.
     */
    window.location.href = "./staff-v2.html";
}

/* ==========================================================================
   INITIALIZATION
   ========================================================================== */

function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

function escapeAttr(value) {
    return escapeHtml(value);
}

async function initialize() {
    if (!requireSession()) return;

    elements.continueBtn?.addEventListener("click", handleContinue);
    elements.skipBtn?.addEventListener("click", handleSkip);

    try {
        const [user, departments] = await Promise.all([
            loadCurrentUser(),
            getDepartments(),
        ]);

        /*
         * Personalize the greeting using the authenticated profile.
         */
        const name = [user.first_name, user.last_name].filter(Boolean).join(" ");
        if (name && elements.greeting) {
            elements.greeting.textContent =
                `Hi ${name} — choose the service point you are working from this shift.`;
        }

        const department = departments.find(
            (item) => String(item.dept_id) === String(user.dept_id)
        );

        if (!department) {
            showError("Your department could not be resolved. Contact IT support.");
            return;
        }

        currentDepartmentName = `${department.name} (${department.department_code})`;
        if (name && elements.greeting) {
            elements.greeting.textContent =
                `Hi ${name} — choose a service point for ${currentDepartmentName}.`;
        }

        const points = await request(
            `/departments/${department.dept_id}/service-points`,
            {
                method: HTTP_METHOD.GET,
                headers: buildAuthHeaders(),
            }
        );

        servicePoints = Array.isArray(points)
            ? points.filter((point) => point.is_active !== false)
            : [];

        renderStationList();
    } catch (error) {
        console.error("[StationGate] Initialization failed:", error);

        if (error?.status === 401) {
            clearSession();
            window.location.replace("./staff-login.html");
            return;
        }

        showError(
            error?.message ||
            "Unable to load stations. Please try again."
        );
    }
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize);
} else {
    initialize();
}
