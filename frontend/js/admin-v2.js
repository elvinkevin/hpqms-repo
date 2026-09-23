import { getCurrentUser, logout } from "./staff-api.js";
import * as adminWorkspace from "./workspaces/admin/admin-workspace.js";

const root = document.getElementById("adminRoot");

async function initializeAdminDashboard() {
    try {
        const user = await getCurrentUser();
        if (user.role !== "ADMIN") {
            window.location.replace("./staff-v2.html");
            return;
        }

        adminWorkspace.mount(root, {
            firstName: user.first_name,
            lastName: user.last_name,
            role: user.role,
            onLogout: () => {
                adminWorkspace.unmount();
                logout();
                window.location.replace("./staff-login.html");
            },
        });
    } catch (error) {
        console.error("[AdminDashboard] Session check failed:", error);
        logout();
        window.location.replace("./staff-login.html");
    }
}

initializeAdminDashboard();
