/* ==========================================================================
   HPQMS Staff Context
   js/staff-context.js

   Establishes and exposes the authenticated staff member's dashboard
   context.

   Source of truth:
       GET /auth/me

   Responsibilities:
       - Validate the authenticated staff profile
       - Derive workspace from role
       - Expose current staff context

   Does NOT:
       - Render UI
       - Manage queue state
       - Make queue mutations
       - Manage WebSockets
   ========================================================================== */

import { getWorkspaceForRole } from "./staff-workspace-config.js";


let context = {
    staffId: null,
    employeeId: null,
    firstName: null,
    lastName: null,
    role: null,
    departmentId: null,
    department: null,
    workspace: null,
    isOnDuty: false,
};


/* ==========================================================================
   CONTEXT INITIALIZATION
   ========================================================================== */

export function initializeStaffContext(user) {
    if (!user) {
        throw new Error("Authenticated staff profile is required.");
    }

    if (!user.staff_id) {
        throw new Error("Staff profile is missing staff_id.");
    }

    if (!user.role) {
        throw new Error("Staff profile is missing role.");
    }

    if (!user.dept_id) {
        throw new Error("Staff profile is missing department.");
    }

    const workspace = getWorkspaceForRole(user.role);

    if (!workspace) {
        throw new Error(
            `No dashboard workspace is configured for role "${user.role}".`
        );
    }

    context = {
        staffId: user.staff_id,
        employeeId: user.employee_id ?? null,
        firstName: user.first_name ?? null,
        lastName: user.last_name ?? null,
        role: user.role,
        departmentId: user.dept_id,
        department: user.department ?? null,
        workspace,
        isOnDuty: Boolean(user.is_on_duty),
    };

    return getStaffContext();
}


/* ==========================================================================
   ACCESSORS
   ========================================================================== */

export function getStaffContext() {
    return { ...context };
}

export function getStaffId() {
    return context.staffId;
}

export function getEmployeeId() {
    return context.employeeId;
}

export function getRole() {
    return context.role;
}

export function getDepartmentId() {
    return context.departmentId;
}

export function getWorkspace() {
    return context.workspace;
}

export function isOnDuty() {
    return context.isOnDuty;
}


/* ==========================================================================
   CLEAR
   ========================================================================== */

export function clearStaffContext() {
    context = {
        staffId: null,
        employeeId: null,
        firstName: null,
        lastName: null,
        role: null,
        departmentId: null,
        department: null,
        workspace: null,
        isOnDuty: false,
    };
}