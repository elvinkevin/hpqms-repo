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

   Supported workspaces:
   - RECEPTION (receptionist staff)
   - TRIAGE (triage nurse)
   - DOCTOR (doctor/clinical staff)
   - ADMIN (administrator)
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


/**
 * Get the workspace module for a given workspace key.
 *
 * @param {string} workspaceKey - The workspace identifier
 * @returns {Object|null} - The workspace module or null if not found
 */
export function getWorkspaceModule(workspaceKey) {
    if (!workspaceKey) {
        return null;
    }

    return WORKSPACE_MODULES[workspaceKey] ?? null;
}


/**
 * Check if a workspace exists in the registry.
 *
 * @param {string} workspaceKey - The workspace identifier
 * @returns {boolean}
 */
export function hasWorkspace(workspaceKey) {
    return Object.prototype.hasOwnProperty.call(
        WORKSPACE_MODULES,
        workspaceKey
    );
}


/**
 * Get all available workspaces.
 *
 * @returns {Array<string>} - Array of workspace keys
 */
export function getAvailableWorkspaces() {
    return Object.keys(WORKSPACE_MODULES);
}