 /* ==========================================================================
   HPQMS Staff Workspace Configuration
   js/staff-workspace-config.js

   Frontend workspace/action policy.

   IMPORTANT:
   This configuration controls what the UI exposes.
   Backend RBAC remains the final authority.
   ========================================================================== */


/* ==========================================================================
   WORKSPACE TYPES
   ========================================================================== */

const WORKSPACE = Object.freeze({
    RECEPTION: "RECEPTION",
    TRIAGE: "TRIAGE",
    DOCTOR: "DOCTOR",
    ADMIN: "ADMIN",
});


/* ==========================================================================
   STAFF ROLES
   ========================================================================== */

const STAFF_ROLE = Object.freeze({
    RECEPTIONIST: "RECEPTIONIST",
    NURSE: "NURSE",
    TRIAGE_NURSE: "TRIAGE_NURSE",
    DOCTOR: "DOCTOR",
    ADMIN: "ADMIN",
});


/* ==========================================================================
   ACTION TYPES
   ========================================================================== */

const ACTION = Object.freeze({
    CALL: "CALL",
    START: "START",
    COMPLETE: "COMPLETE",
    NO_SHOW: "NO_SHOW",
    REQUEUE: "REQUEUE",
    CANCEL: "CANCEL",

    SET_PRIORITY: "SET_PRIORITY",

    COMPLETE_REGISTRATION: "COMPLETE_REGISTRATION",

    TRANSFER: "TRANSFER",
    DISCHARGE: "DISCHARGE",

    VIEW_LOCATION: "VIEW_LOCATION",
    VIEW_HISTORY: "VIEW_HISTORY",
});


/* ==========================================================================
   ROLE → WORKSPACE
   ========================================================================== */

const ROLE_WORKSPACE = Object.freeze({
    [STAFF_ROLE.RECEPTIONIST]: WORKSPACE.RECEPTION,

    [STAFF_ROLE.NURSE]: WORKSPACE.RECEPTION,

    [STAFF_ROLE.TRIAGE_NURSE]: WORKSPACE.TRIAGE,

    [STAFF_ROLE.DOCTOR]: WORKSPACE.DOCTOR,

    [STAFF_ROLE.ADMIN]: WORKSPACE.ADMIN,
});


/* ==========================================================================
   ROLE → ALLOWED ACTIONS
   ========================================================================== */

const WORKSPACE_ACTIONS = Object.freeze({

    [STAFF_ROLE.RECEPTIONIST]: Object.freeze([
        ACTION.CALL,
        ACTION.START,
        ACTION.COMPLETE,
        ACTION.NO_SHOW,
        ACTION.REQUEUE,
        ACTION.CANCEL,
        ACTION.COMPLETE_REGISTRATION,
    ]),

    [STAFF_ROLE.NURSE]: Object.freeze([
        ACTION.CALL,
        ACTION.START,
        ACTION.COMPLETE,
        ACTION.NO_SHOW,
        ACTION.REQUEUE,
        ACTION.CANCEL,
    ]),

    [STAFF_ROLE.TRIAGE_NURSE]: Object.freeze([
        ACTION.CALL,
        ACTION.START,
        ACTION.COMPLETE,
        ACTION.NO_SHOW,
        ACTION.REQUEUE,

        ACTION.SET_PRIORITY,

        ACTION.TRANSFER,
    ]),

    [STAFF_ROLE.DOCTOR]: Object.freeze([
        ACTION.CALL,
        ACTION.START,
        ACTION.COMPLETE,
        ACTION.NO_SHOW,
        ACTION.REQUEUE,
        ACTION.CANCEL,

        ACTION.SET_PRIORITY,

        ACTION.TRANSFER,
        ACTION.DISCHARGE,
    ]),

    /*
     * Admin has backend authority but the staff workspace is intentionally
     * read-only. Administrative operations belong in the admin area.
     */
    [STAFF_ROLE.ADMIN]: Object.freeze([]),
});


/* ==========================================================================
   PUBLIC HELPERS
   ========================================================================== */

function getWorkspaceForRole(role) {
    return ROLE_WORKSPACE[role] ?? null;
}


function getActionsForRole(role) {
    return WORKSPACE_ACTIONS[role] ?? [];
}


function canPerformAction(role, action) {
    return getActionsForRole(role).includes(action);
}


function isReadOnlyRole(role) {
    return role === STAFF_ROLE.ADMIN;
}


function isKnownRole(role) {
    return Object.prototype.hasOwnProperty.call(
        ROLE_WORKSPACE,
        role
    );
}


/* ==========================================================================
   EXPORTS
   ========================================================================== */

export {
    WORKSPACE,
    STAFF_ROLE,
    ACTION,
    ROLE_WORKSPACE,
    WORKSPACE_ACTIONS,

    getWorkspaceForRole,
    getActionsForRole,
    canPerformAction,
    isReadOnlyRole,
    isKnownRole,
};