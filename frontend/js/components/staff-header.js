/* ========================================================================
   HPQMS Staff Dashboard Header
   js/staff-header.js

   Presentation and interaction for the global dashboard header.
   ======================================================================== */

const headerElements = {
    departmentSelect: document.getElementById("departmentSelect"),
    staffName: document.getElementById("staffName") || document.querySelector(".staff-name"),
    staffRole: document.getElementById("staffRole") || document.querySelector(".staff-role"),
    logoutButton: document.getElementById("logoutBtn"),
    avatar: document.querySelector(".avatar"),
};

function formatRole(role) {
    if (!role) return "Staff";

    return role
        .replaceAll("_", " ")
        .toLowerCase()
        .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function getStaffName(context) {
    return [context.firstName, context.lastName]
        .filter(Boolean)
        .join(" ") || context.employeeId || "Staff Member";
}

function getInitials(context) {
    const initials = [context.firstName, context.lastName]
        .filter(Boolean)
        .map((name) => name.trim().charAt(0).toUpperCase())
        .join("");

    return initials || (context.employeeId || "S").trim().charAt(0).toUpperCase();
}

export function renderStaffHeader(context) {
    if (!context) return;

    if (headerElements.staffName) {
        headerElements.staffName.textContent = getStaffName(context);
    }

    if (headerElements.staffRole) {
        headerElements.staffRole.textContent = formatRole(context.role);
    }

    renderDepartment(context.department);

    if (headerElements.avatar) {
        headerElements.avatar.textContent = getInitials(context);
        headerElements.avatar.setAttribute(
            "aria-label",
            `${getStaffName(context)} profile`
        );
    }
}

export function renderDepartment(department) {
    if (!headerElements.departmentSelect) return;

    headerElements.departmentSelect.innerHTML = "";

    const option = document.createElement("option");
    option.value = department?.dept_id ?? department?.department_id ?? "";
    option.textContent = department?.name
        ?? department?.department_code
        ?? "Current Department";

    headerElements.departmentSelect.appendChild(option);
    headerElements.departmentSelect.disabled = true;
}

export function onLogout(handler) {
    headerElements.logoutButton?.addEventListener("click", () => {
        if (typeof handler === "function") handler();
    });
}


/* ==========================================================================
   STATION PILL
   --------------------------------------------------------------------------
   Compact service-point indicator in the header. Clicking it opens a
   small popover with the department's stations, letting the staff
   member switch or check out mid-shift.

   States:
     - Green dot  → bound to a station (label shown)
     - Grey dot   → unbound / offline ("No station")
   ========================================================================== */

const stationElements = {
    pill: null,
    popover: null,
};

let stationState = null;   // { service_point_id, code, label } | null
let stationPopoverOpen = false;

/**
 * Render/refresh the station pill.
 *
 * @param {object|null} station - StationBinding payload from /auth/me,
 *                                or null when unbound.
 * @param {object|null} department - Department context (for loading stations).
 */
export function renderStationPill(station, department = null) {
    const anchor = document.getElementById("staffProfile");
    if (!anchor) return;

    stationState = station;

    if (!stationElements.pill) {
        stationElements.pill = document.createElement("button");
        stationElements.pill.type = "button";
        stationElements.pill.id = "stationPill";
        stationElements.pill.className = "station-pill";
        stationElements.pill.setAttribute("aria-haspopup", "true");

        anchor.parentNode.insertBefore(stationElements.pill, anchor);
    }

    const pill = stationElements.pill;

    pill.innerHTML = station
        ? `<span class="station-pill-dot active"></span>
           <span class="station-pill-label">${escapeHtml(station.label)}</span>`
        : `<span class="station-pill-dot offline"></span>
           <span class="station-pill-label">No Station</span>`;

    pill.title = station
        ? `Checked in at ${station.label} — click to switch or check out`
        : "Not checked in to a station — click to select one";

    pill.onclick = () => toggleStationPopover(department);
}

function closeStationPopover() {
    stationElements.popover?.remove();
    stationElements.popover = null;
    stationPopoverOpen = false;

    document.removeEventListener("click", onOutsideClick);
}

function onOutsideClick(event) {
    if (!stationElements.popover) return;

    if (
        !stationElements.popover.contains(event.target) &&
        !stationElements.pill?.contains(event.target)
    ) {
        closeStationPopover();
    }
}

async function toggleStationPopover(department) {
    if (stationPopoverOpen) {
        closeStationPopover();
        return;
    }

    closeStationPopover();

    const popover = document.createElement("div");
    popover.id = "stationPopover";
    popover.className = "station-popover";

    popover.innerHTML = `<div class="station-popover-loading">Loading stations…</div>`;
    document.body.appendChild(popover);

    positionPopover(popover);

    stationElements.popover = popover;
    stationPopoverOpen = true;
    document.addEventListener("click", onOutsideClick);

    /*
     * Load stations for the popover. Failures degrade to an inline
     * error inside the popover, never a broken pill.
     */
    try {
        const { loadDepartmentServicePoints, checkInToServicePoint, checkOutOfServicePoint } =
            await import("../staff-actions.js");

        const points = await loadDepartmentServicePoints();
        const list = Array.isArray(points) ? points : [];

        popover.innerHTML = `
            <div class="station-popover-title">Switch Station</div>
            <div class="station-popover-list">
                ${list.length ? list.map((sp) => `
                    <button type="button"
                            class="station-popover-option
                                ${stationState && String(sp.service_point_id) === String(stationState.service_point_id) ? "current" : ""}"
                            data-id="${escapeHtml(sp.service_point_id)}">
                        ${escapeHtml(sp.label)}
                        <span class="station-popover-code">${escapeHtml(sp.code)}</span>
                    </button>
                `).join("") : `<div class="station-popover-empty">No stations configured.</div>`}
            </div>
            <button type="button" class="station-popover-checkout" id="stationPopoverCheckout"
                ${stationState ? "" : "disabled"}>
                Check Out
            </button>
        `;

        popover.querySelectorAll(".station-popover-option").forEach((option) => {
            option.addEventListener("click", async () => {
                try {
                    await checkInToServicePoint(option.dataset.id);
                    closeStationPopover();
                    window.location.reload(); // re-fetch /auth/me with new binding
                } catch (error) {
                    showPopoverError(popover, error);
                }
            });
        });

        popover.querySelector("#stationPopoverCheckout")?.addEventListener("click", async () => {
            try {
                await checkOutOfServicePoint();
                closeStationPopover();
                window.location.reload();
            } catch (error) {
                showPopoverError(popover, error);
            }
        });
    } catch (error) {
        console.error("[StaffHeader] Station popover load failed:", error);
        popover.innerHTML = `<div class="station-popover-empty">Unable to load stations.</div>`;
    }
}

function showPopoverError(popover, error) {
    const existing = popover.querySelector(".station-popover-error");
    if (existing) existing.remove();

    const message = document.createElement("div");
    message.className = "station-popover-error";
    message.textContent = error?.message || "Action failed.";
    popover.appendChild(message);
}

function positionPopover(popover) {
    const pillRect = stationElements.pill?.getBoundingClientRect();
    if (!pillRect) return;

    popover.style.top = `${pillRect.bottom + 8}px`;
    popover.style.right = `${window.innerWidth - pillRect.right}px`;
}

function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}
