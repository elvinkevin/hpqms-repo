/* ==========================================================================
   HPQMS Staff Dashboard — Workspace Registry
   js/workspace-registry.js

   Resolves a workspace key to its workspace module.

   The registry does not:
   - call APIs
   - manage state
   - perform authorization
   - render the dashboard

   It only answers:
       "Which workspace module belongs here?"
   ========================================================================== */

import { WORKSPACE } from "./staff-workspace-config.js";

import * as receptionWorkspace
    from "./workspaces/reception/reception-workspace.js";

import * as triageWorkspace
    from "./workspaces/triage/triage-workspace.js";

import * as doctorWorkspace
    from "./workspaces/doctor/doctor-workspace.js";

import * as adminWorkspace
    from "./workspaces/admin/admin-workspace.js";


const WORKSPACE_MODULES = Object.freeze({
    [WORKSPACE.RECEPTION]: receptionWorkspace,
    [WORKSPACE.TRIAGE]: triageWorkspace,
    [WORKSPACE.DOCTOR]: doctorWorkspace,
    [WORKSPACE.ADMIN]: adminWorkspace,
});


export function getWorkspaceModule(workspaceKey) {
    return WORKSPACE_MODULES[workspaceKey] ?? null;
}


export function hasWorkspace(workspaceKey) {
    return Object.prototype.hasOwnProperty.call(
        WORKSPACE_MODULES,
        workspaceKey
    );
}