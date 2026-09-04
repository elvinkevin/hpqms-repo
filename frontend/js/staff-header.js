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
