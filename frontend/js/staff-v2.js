/* ========================================================================
   HPQMS Staff V2 Bootstrap
   js/staff-v2.js
   ======================================================================== */

import { getCurrentUser, getDepartments, logout } from "./staff-api.js";
import { getSession } from "./staff-session.js";
import {
    clearStaffContext,
    initializeStaffContext,
} from "./staff-context.js";
import { renderStaffHeader } from "./staff-header.js";

async function initializeDashboard() {
    if (!getSession()?.accessToken) {
        window.location.replace("./staff-login.html");
        return;
    }

    try {
        const user = await getCurrentUser();
        const departments = await getDepartments();
        const department = departments.find(
            (item) => String(item.dept_id) === String(user.dept_id)
        );

        const context = initializeStaffContext({
            ...user,
            department,
        });

        renderStaffHeader(context);
    } catch (error) {
        console.error("[StaffV2] Context initialization failed:", error);
        logout();
        clearStaffContext();
        window.location.replace("./staff-login.html");
    }
}

document.getElementById("logoutBtn")?.addEventListener("click", () => {
    logout();
    clearStaffContext();
    window.location.replace("./staff-login.html");
});

initializeDashboard();