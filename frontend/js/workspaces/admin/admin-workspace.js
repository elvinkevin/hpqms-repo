import * as api from "../../admin-api.js";
import * as adminSocket from "../../admin-websocket.js";

let root;
let context;
let activeTab = "overview";
let overview;
let staff = [];
let staffPage = 1;
let staffQuery = "";
let departments = [];
let audit = [];
let selectedDepartment = "";
let servicePointLoadVersion = 0;
let busy = false;
let confirmDialogAction = null;
let timer;
let noticeTimer;

const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const notice = (message, kind = "error") => {
    const el = root?.querySelector("[data-notice]");
    clearTimeout(noticeTimer);
    noticeTimer = undefined;
    if (el) {
        el.textContent = message;
        el.className = `admin-notice ${kind}`;
        el.hidden = false;
        el.style.display = "";
        el.setAttribute("role", kind === "success" ? "status" : "alert");
        if (kind === "success") {
            noticeTimer = setTimeout(() => {
                if (root?.contains(el) && el.textContent === message) {
                    el.hidden = true;
                    el.style.display = "none";
                }
                noticeTimer = undefined;
            }, 3500);
        }
    }
};

export function mount(container, userContext = {}) {
    root = container;
    context = userContext;
    activeTab = "overview";
    root.innerHTML = `
      <div class="admin-dashboard">
        <aside class="admin-sidebar" id="adminSidebar">
          <div class="admin-sidebar-brand"><span class="admin-brand-mark"><svg viewBox="0 0 52 52" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><circle cx="26" cy="26" r="25" fill="#0F5B78"/><circle cx="26" cy="26" r="25" fill="url(#adminLogoGrad)"/><circle cx="26" cy="26" r="17" fill="#FFFFFF"/><path d="M26 16V36M16 26H36" stroke="#13A6A6" stroke-width="5" stroke-linecap="round"/><defs><linearGradient id="adminLogoGrad" x1="0" y1="0" x2="52" y2="52" gradientUnits="userSpaceOnUse"><stop stop-color="#0F5B78"/><stop offset="1" stop-color="#13A6A6"/></linearGradient></defs></svg></span><div><strong>Horizon General Hospital</strong><small>Quality Care. Every Patient.</small></div></div>
          <button class="admin-sidebar-toggle" id="sidebarToggle" type="button" aria-label="Collapse sidebar" aria-controls="adminSidebar" aria-expanded="true" title="Collapse sidebar">‹</button>
          <nav aria-label="Admin dashboard sections">
            <button class="admin-nav active" data-tab="overview"><span>▦</span><span class="admin-nav-label">Overview</span></button>
            <button class="admin-nav" data-tab="staff"><span>♙</span><span class="admin-nav-label">Staff</span></button>
            <button class="admin-nav" data-tab="departments"><span>▤</span><span class="admin-nav-label">Departments</span></button>
            <button class="admin-nav" data-tab="audit"><span>◷</span><span class="admin-nav-label">Audit trail</span></button>
            <button class="admin-nav future" disabled title="Not available in the backend yet"><span>⌁</span><span class="admin-nav-label">Analytics <em>Planned</em></span></button>
          </nav>
          <div class="admin-sidebar-foot"><span class="admin-online-dot"></span><span class="admin-sidebar-foot-text">Connected to hospital API</span><button class="admin-sidebar-logout" data-action="logout">Log out</button></div>
        </aside>
        <section class="admin-main">
          <header class="admin-topbar"><div><div class="admin-eyebrow">ADMINISTRATION</div><h1 data-page-title>Hospital overview</h1></div><div class="admin-top-actions"><div class="admin-user"><span class="admin-user-avatar">${esc(`${(userContext.firstName || "A").slice(0, 1)}${(userContext.lastName || "").slice(0, 1)}`)}</span><span><b>${esc(`${userContext.firstName || "Admin"} ${userContext.lastName || ""}`)}</b><small>${esc(userContext.role || "ADMIN")} · ${esc(userContext.employeeId || "")}</small></span></div><button class="admin-refresh" data-action="refresh" aria-label="Refresh data">↻</button></div></header>
          <div data-notice class="admin-notice" hidden></div>
          <div data-content class="admin-content"><div class="admin-loading"><span class="admin-spinner"></span>Loading dashboard…</div></div>
          <footer class="admin-footer"><span data-footer-brand>Horizon General Hospital</span><span data-last-updated></span></footer>
        </section>
      </div>`;
    root.addEventListener("click", onClick);
    root.addEventListener("submit", onSubmit);
    root.addEventListener("change", onChange);
    root.addEventListener("reset", onReset);
    root.addEventListener("input", onInput);

    // Sidebar collapsible toggle
    const sidebar = root.querySelector("#adminSidebar");
    const toggleBtn = root.querySelector("#sidebarToggle");
    if (toggleBtn && sidebar) {
        toggleBtn.addEventListener("click", () => {
            const collapsed = sidebar.classList.toggle("collapsed");
            toggleBtn.textContent = collapsed ? "›" : "‹";
            toggleBtn.title = collapsed ? "Expand sidebar" : "Collapse sidebar";
            toggleBtn.setAttribute("aria-label", toggleBtn.title);
            toggleBtn.setAttribute("aria-expanded", String(!collapsed));
        });
    }

    loadAll().catch(showError);
    // Live updates: the backend pushes ADMIN_OVERVIEW_CHANGED pings over the
    // /ws/admin channel; polling remains only as a fallback while offline.
    adminSocket.on("overview-changed", onLiveChange);
    adminSocket.connect();
    timer = setInterval(() => { if (activeTab === "overview" && !adminSocket.isConnected()) loadOverview().catch(showError); }, 60_000);
}

let liveRefreshTimer;
function onLiveChange() {
    if (activeTab !== "overview") return;
    // Debounce bursts of events into a single refresh.
    clearTimeout(liveRefreshTimer);
    liveRefreshTimer = setTimeout(() => { loadOverview().catch(showError); }, 400);
}

export function update() { /* Admin data refresh is controlled by this workspace. */ }

export function unmount() {
    clearInterval(timer);
    clearTimeout(noticeTimer);
    clearTimeout(liveRefreshTimer);
    adminSocket.off("overview-changed", onLiveChange);
    adminSocket.disconnect();
    root?.removeEventListener("click", onClick);
    root?.removeEventListener("submit", onSubmit);
    root?.removeEventListener("change", onChange);
    root?.removeEventListener("reset", onReset);
    root?.removeEventListener("input", onInput);
    root = null;
}

async function loadAll() {
    const results = await Promise.allSettled([api.getOverview(), api.getStaff(), api.getDepartments(), api.getAuditLogs({ limit: 50 })]);
    if (results[0].status === "fulfilled") overview = results[0].value;
    if (results[1].status === "fulfilled") staff = results[1].value;
    if (results[2].status === "fulfilled") departments = results[2].value;
    if (results[3].status === "fulfilled") audit = results[3].value;
    const failed = results.find((result) => result.status === "rejected");
    render();
    if (failed) notice(failed.reason?.message || "Some dashboard data could not be loaded.");
}

async function loadOverview() { overview = await api.getOverview(); render(); }
async function reloadCurrent() {
    busy = true;
    try {
        if (activeTab === "overview") overview = await api.getOverview();
        if (activeTab === "staff") staff = await api.getStaff();
        if (activeTab === "departments") departments = await api.getDepartments();
        if (activeTab === "audit") audit = await api.getAuditLogs({ limit: 50 });
        render();
    } finally { busy = false; }
}

function render() {
    if (!root) return;
    root.querySelectorAll(".admin-nav[data-tab]").forEach((button) => button.classList.toggle("active", button.dataset.tab === activeTab));
    root.querySelector("[data-page-title]").textContent = ({ overview: "Hospital overview", staff: "Staff management", departments: "Departments & service points", audit: "Audit trail" })[activeTab];
    root.querySelector("[data-last-updated]").textContent = overview?.generated_at ? `Updated ${new Date(overview.generated_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` : "";
    const content = root.querySelector("[data-content]");
    content.innerHTML = activeTab === "overview" ? renderOverview() : activeTab === "staff" ? renderStaff() : activeTab === "departments" ? renderDepartments() : renderAudit();
}

function renderOverview() {
    if (!overview) return empty("Overview is not available yet.");
    const t = overview.totals || {};
    const cards = [["Waiting", t.waiting, "Patients waiting for service", "teal"], ["In service", t.in_progress, "Currently being attended", "blue"], ["Urgent waiting", overview.critical_waiting, "Urgent or critical patients", "red"], ["Staff on duty", t.staff_on_duty, `${t.staff_active ?? 0} active accounts · sign-in starts shift`, "green"], ["Active visits", t.active_visits, "Visits currently open", "purple"], ["Appointments", t.appointments_today, "Scheduled today", "amber"]];
    return `<div class="admin-card-grid">${cards.map(([label, value, sub, color]) => `<article class="admin-stat-card ${color}"><span class="admin-stat-icon">${label === "Urgent waiting" ? "!" : "•"}</span><div><span>${esc(label)}</span><strong>${Number(value || 0)}</strong><small>${esc(sub)}</small></div></article>`).join("")}</div>
      <div class="admin-overview-grid"><section class="admin-panel queue-panel"><div class="admin-panel-head"><div><h2>Department queues</h2><p>Current patient flow by department</p></div><span class="admin-live-label"><i></i> Live snapshot</span></div><div class="admin-table-wrap"><table><thead><tr><th>Department</th><th>Waiting</th><th>Called</th><th>In service</th><th>Urgent</th><th>On duty</th></tr></thead><tbody>${(overview.departments || []).map((d) => `<tr><td><button class="admin-link" data-action="drill" data-id="${esc(d.dept_id)}">${esc(d.name)}</button><small class="admin-cell-sub">${esc(d.code || "")}</small></td><td><b>${d.waiting || 0}</b></td><td>${d.called || 0}</td><td>${d.in_progress || 0}</td><td>${Number(d.critical_waiting || 0) ? `<span class="admin-pill danger">${d.critical_waiting}</span>` : "—"}</td><td>${d.staff_on_duty || 0}</td></tr>`).join("") || `<tr><td colspan="6">No department data.</td></tr>`}</tbody></table></div><div data-drill-result></div></section>
      <section class="admin-panel"><div class="admin-panel-head"><div><h2>On-duty roster</h2><p>${(overview.on_duty_staff || []).length} staff explicitly checked in for a shift</p></div></div><div class="admin-roster">${(overview.on_duty_staff || []).map((s) => `<div class="admin-roster-row"><span class="admin-roster-avatar">${esc((s.full_name || "?").slice(0,1))}</span><span class="admin-roster-info"><b>${esc(s.full_name)}</b><small>${esc(s.role)} · ${esc(s.service_point_label || "No station")}</small></span><span class="admin-online-dot"></span></div>`).join("") || `<div class="admin-empty-inline">No staff currently on duty</div>`}</div></section></div>
      <p class="admin-footnote">Staff sign-in starts a shift automatically. The header toggle can end or resume the shift; logout ends it and releases the station. Station binding remains separately managed. Snapshot updates live via WebSocket, with a 60-second fallback refresh.</p>`;
}

function renderStaff() {
    const pageSize = 8;

    // Client-side filter across the 4 searchable columns
    const q = staffQuery.trim().toLowerCase();
    const filtered = q
        ? staff.filter((s) => {
              const deptName = (departments.find((d) => d.dept_id === s.dept_id)?.name || s.department_name || "").toLowerCase();
              return (
                  `${s.first_name} ${s.last_name}`.toLowerCase().includes(q) ||
                  (s.employee_id || "").toLowerCase().includes(q) ||
                  deptName.includes(q) ||
                  (s.role || "").toLowerCase().includes(q)
              );
          })
        : staff;

    const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
    staffPage = Math.min(Math.max(1, staffPage), pageCount);
    const start = filtered.length ? (staffPage - 1) * pageSize + 1 : 0;
    const end = Math.min(staffPage * pageSize, filtered.length);
    const pageStaff = filtered.slice(start ? start - 1 : 0, end);

    const hasQuery = q.length > 0;
    const subtitle = hasQuery
        ? `${filtered.length} of ${staff.length} staff match "${esc(staffQuery)}"`
        : `${staff.length} staff records · Shift status is separate from account status and station assignment`;

    const html = `<section class="admin-panel"><div class="admin-panel-head admin-panel-head--staff"><div class="admin-panel-head-left"><div><h2>Staff directory</h2><p>${subtitle}</p></div><div class="admin-staff-search"><span class="admin-staff-search-icon">⌕</span><input class="admin-staff-search-input" data-staff-search type="search" placeholder="Search by name, ID, department, role…" value="${esc(staffQuery)}" autocomplete="off" spellcheck="false" aria-label="Search staff"><button class="admin-staff-search-clear" data-action="staff-search-clear" aria-label="Clear search" ${hasQuery ? "" : "hidden"}>✕</button></div></div><button class="admin-button primary" data-action="open-create-staff-drawer">＋ Add staff</button></div><div class="admin-table-wrap"><table><thead><tr><th>Staff member</th><th>Employee ID</th><th>Department</th><th>Role</th><th>Station</th><th>Shift</th><th>Account</th><th>Actions</th></tr></thead><tbody>${pageStaff.map((s) => { const isSelf = String(s.employee_id) === String(context?.employeeId || ""); return `<tr><td><b>${esc(s.first_name)} ${esc(s.last_name)}</b></td><td>${esc(s.employee_id)}</td><td>${esc(departments.find((d) => d.dept_id === s.dept_id)?.name || s.department_name || "—")}</td><td><span class="admin-role-tag">${esc(s.role)}</span></td><td>${s.active_service_point_id ? "Assigned" : "—"}</td><td><span class="admin-pill ${s.is_on_duty ? "success" : "muted"}">${s.is_on_duty ? "On duty" : "Off duty"}</span></td><td><span class="admin-pill ${s.is_active ? "success" : "muted"}">${s.is_active ? "Active" : "Inactive"}</span></td><td><div class="admin-row-actions"><button class="admin-button secondary admin-manage-button" data-action="manage-staff" data-id="${s.staff_id}">Manage</button><div class="admin-menu-wrap"><button class="admin-overflow-trigger" data-action="staff-menu" data-id="${s.staff_id}" aria-label="More actions for ${esc(s.first_name)} ${esc(s.last_name)}" aria-expanded="false">⋮</button><div class="admin-overflow-menu" data-staff-menu="${s.staff_id}" role="menu" hidden>${s.is_active ? (isSelf ? "" : `<button role="menuitem" data-action="staff-toggle-active" data-id="${s.staff_id}" data-active="true" class="danger-text">Deactivate account</button>`) : `<button role="menuitem" data-action="staff-toggle-active" data-id="${s.staff_id}" data-active="false">Activate account</button>`}<button role="menuitem" data-action="staff-reset-password" data-id="${s.staff_id}">Reset account</button></div></div></div></td></tr>`; }).join("") || `<tr><td colspan="8" class="admin-search-empty">${hasQuery ? `No staff match "<strong>${esc(staffQuery)}</strong>"` : "No staff records found."}</td></tr>`}</tbody></table></div><nav class="admin-pagination" aria-label="Staff directory pages"><span>Showing ${start}–${end} of ${filtered.length} record${filtered.length !== 1 ? "s" : ""}${hasQuery ? ` (filtered)` : ""}</span><div class="admin-pagination-controls"><button data-action="staff-page" data-page="${staffPage - 1}" ${staffPage <= 1 ? "disabled" : ""}>‹ Prev</button>${Array.from({ length: pageCount }, (_, index) => index + 1).map((page) => `<button data-action="staff-page" data-page="${page}" class="${page === staffPage ? "active" : ""}" ${page === staffPage ? 'aria-current="page"' : ""}>${page}</button>`).join("")}<button data-action="staff-page" data-page="${staffPage + 1}" ${staffPage >= pageCount ? "disabled" : ""}>Next ›</button></div></nav></section>`;

    return html;
}

function onInput(event) {
    if (!event.target.matches("[data-staff-search]")) return;
    staffQuery = event.target.value;
    staffPage = 1;
    render();
    // Restore caret after re-render since the table re-renders on each keystroke.
    const input = root.querySelector("[data-staff-search]");
    if (input) { input.focus(); const end = input.value.length; input.setSelectionRange(end, end); }
}

function renderDepartments() {
    const selected = departments.find((d) => d.dept_id === selectedDepartment) || departments[0];
    if (selected && selectedDepartment !== selected.dept_id) selectedDepartment = selected.dept_id;
    return `<div class="admin-dept-layout"><section class="admin-panel"><div class="admin-panel-head"><div><h2>Departments</h2><p>Configure hospital departments</p></div><button class="admin-button primary" data-action="toggle-create-dept">＋ Add department</button></div><div data-create-dept class="admin-form-panel" hidden><form data-form="department-create" class="admin-inline-form"><input name="name" placeholder="Department name" required><input name="department_code" placeholder="Code" maxlength="10" required><select name="type">${["OPD", "EMERGENCY", "SPECIALIST", "PAEDS"].map((x) => `<option>${x}</option>`).join("")}</select><input name="max_capacity" type="number" min="1" value="50" aria-label="Maximum capacity"><button class="admin-button primary">Create department</button></form></div><div class="admin-table-wrap"><table><thead><tr><th>Name</th><th>Code</th><th>Type</th><th>Capacity</th><th>Status</th><th></th></tr></thead><tbody>${departments.map((d) => { const isReservedAdminDept = String(d.department_code || "").toUpperCase() === "ADMIN"; return `<tr><td><b>${esc(d.name)}</b></td><td>${esc(d.department_code)}</td><td>${esc(d.type)}</td><td>${d.max_capacity}</td><td><span class="admin-pill ${d.is_active ? "success" : "muted"}">${d.is_active ? "Active" : "Inactive"}</span></td><td><div class="admin-row-actions"><button class="admin-row-button ${isReservedAdminDept ? "admin-dept-edit-only" : ""}" data-action="dept-edit" data-id="${d.dept_id}">Edit</button>${isReservedAdminDept ? "" : `<button class="admin-row-button" data-action="dept-status" data-id="${d.dept_id}" data-active="${d.is_active}">${d.is_active ? "Deactivate" : "Activate"}</button>`}</div></td></tr>`; }).join("") || `<tr><td colspan="6">No departments available.</td></tr>`}</tbody></table></div></section>
      <section class="admin-panel"><div class="admin-panel-head"><div><h2>Service points</h2><p>Stations configured for a department</p></div></div><label class="admin-field-label">Department<select data-department-select>${departmentOptions(selectedDepartment)}</select></label><div data-service-points class="admin-service-list">${selected ? `<div class="admin-loading"><span class="admin-spinner"></span>Loading service points…</div>` : empty("Create a department to configure service points.")}</div></section></div><p class="admin-footnote">TODO: add richer department editing and service-point availability controls as configuration needs grow.</p>`;
}

function renderAudit() {
    return `<section class="admin-panel"><div class="admin-panel-head"><div><h2>Administrative activity</h2><p>Recent changes recorded in the audit ledger</p></div></div><form data-form="audit-filter" class="admin-filter-form"><input name="action" placeholder="Filter by action (e.g. ROLE_CHANGED)"><input name="staff_id" placeholder="Staff ID"><input name="entity_type" placeholder="Entity type"><input name="entity_id" placeholder="Entity ID"><button class="admin-button secondary">Apply filters</button><button class="admin-row-button" type="reset">Clear</button></form><div class="admin-table-wrap"><table><thead><tr><th>Time</th><th>Action</th><th>Entity</th><th>Entity ID</th><th>Performed by</th><th>Details</th></tr></thead><tbody>${audit.map((item) => `<tr><td>${esc(new Date(item.created_at).toLocaleString())}</td><td><span class="admin-role-tag">${esc(item.action)}</span></td><td>${esc(item.entity_type)}</td><td><code>${esc(item.entity_id)}</code></td><td><code>${esc(item.performed_by || "System")}</code></td><td>${esc(JSON.stringify(item.payload || {}))}</td></tr>`).join("") || `<tr><td colspan="6">No audit records match these filters.</td></tr>`}</tbody></table></div><p class="admin-footnote">Showing up to 50 records. TODO: add pagination controls for larger audit histories.</p></section>`;
}

function empty(text) { return `<div class="admin-empty">${esc(text)}</div>`; }
function roles() { return ["RECEPTIONIST", "NURSE", "TRIAGE_NURSE", "DOCTOR", "ADMIN"].map((role) => `<option value="${role}">${role.replaceAll("_", " ")}</option>`).join(""); }
function departmentOptions(value = "") { return departments.map((d) => `<option value="${d.dept_id}" ${String(d.dept_id) === String(value) ? "selected" : ""}>${esc(d.name)}${d.is_active ? "" : " (inactive)"}</option>`).join(""); }

function closeStaffMenus() {
    root?.querySelectorAll("[data-staff-menu]").forEach((menu) => { menu.hidden = true; });
    root?.querySelectorAll('[data-action="staff-menu"]').forEach((button) => button.setAttribute("aria-expanded", "false"));
}

function closeStaffDrawer() { root?.querySelector("[data-staff-drawer-backdrop]")?.remove(); }

function closeCreateStaffDrawer() { root?.querySelector("[data-create-staff-drawer-backdrop]")?.remove(); }

function closePasswordDialog() { root?.querySelector("[data-password-dialog-backdrop]")?.remove(); }

function closeConfirmDialog() {
    root?.querySelector("[data-confirm-dialog-backdrop]")?.remove();
    confirmDialogAction = null;
}

function closeDeptEditDialog() { root?.querySelector("[data-dept-edit-backdrop]")?.remove(); }

function closeServicePointEditDialog() { root?.querySelector("[data-sp-edit-backdrop]")?.remove(); }

// In-workspace confirmation popup replacing native browser confirm().
function openConfirmDialog({ kicker = "Please confirm", title, message, confirmLabel = "Confirm", onConfirm }) {
    closeConfirmDialog();
    root.insertAdjacentHTML("beforeend", `<div class="admin-password-backdrop" data-confirm-dialog-backdrop><section class="admin-password-dialog admin-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="confirm-dialog-title"><button class="admin-password-close" type="button" data-action="close-confirm-dialog" aria-label="Close">×</button><span class="admin-drawer-kicker">${esc(kicker)}</span><h2 id="confirm-dialog-title">${esc(title)}</h2><p>${esc(message)}</p><footer><button class="admin-button secondary" type="button" data-action="close-confirm-dialog">Cancel</button><button class="admin-button danger" type="button" data-action="confirm-dialog-confirm">${esc(confirmLabel)}</button></footer></section></div>`);
    confirmDialogAction = onConfirm;
}

function openDeptEditDialog(d) {
    closeDeptEditDialog();
    root.insertAdjacentHTML("beforeend", `<div class="admin-password-backdrop" data-dept-edit-backdrop><section class="admin-password-dialog admin-edit-dialog" role="dialog" aria-modal="true" aria-labelledby="dept-edit-title"><button class="admin-password-close" type="button" data-action="close-dept-edit-dialog" aria-label="Close">×</button><span class="admin-drawer-kicker">Department administration</span><h2 id="dept-edit-title">Edit department</h2><form data-form="department-edit" data-dept-id="${esc(d.dept_id)}"><label>Department name<input name="name" value="${esc(d.name)}" required></label><label>Department code<input name="department_code" value="${esc(d.department_code)}" maxlength="10" required></label><label>Maximum capacity<input name="max_capacity" type="number" min="1" value="${esc(d.max_capacity)}" required></label><footer><button class="admin-button secondary" type="button" data-action="close-dept-edit-dialog">Cancel</button><button class="admin-button primary">Save changes</button></footer></form></section></div>`);
    root.querySelector("[data-dept-edit-backdrop] input")?.focus();
}

async function openServicePointEditDialog(id) {
    const point = await api.getServicePoints(selectedDepartment).then((items) => items.find((item) => item.service_point_id === id));
    if (!point) return;
    closeServicePointEditDialog();
    root.insertAdjacentHTML("beforeend", `<div class="admin-password-backdrop" data-sp-edit-backdrop><section class="admin-password-dialog admin-edit-dialog" role="dialog" aria-modal="true" aria-labelledby="sp-edit-title"><button class="admin-password-close" type="button" data-action="close-sp-edit-dialog" aria-label="Close">×</button><span class="admin-drawer-kicker">Service point administration</span><h2 id="sp-edit-title">Edit service point</h2><form data-form="service-point-edit" data-sp-id="${esc(id)}"><label>Station label<input name="label" value="${esc(point.label)}" required></label><label>Station code<input name="code" value="${esc(point.code)}" required></label><footer><button class="admin-button secondary" type="button" data-action="close-sp-edit-dialog">Cancel</button><button class="admin-button primary">Save changes</button></footer></form></section></div>`);
    root.querySelector("[data-sp-edit-backdrop] input")?.focus();
}

function secureRandomIndex(max) {
    if (!globalThis.crypto?.getRandomValues || !Number.isInteger(max) || max < 1 || max > 256) {
        throw new Error("Secure password generation is unavailable in this browser.");
    }
    const limit = Math.floor(256 / max) * max;
    const bytes = new Uint8Array(1);
    do { crypto.getRandomValues(bytes); } while (bytes[0] >= limit);
    return bytes[0] % max;
}

function generateTemporaryPassword(length = 18) {
    const groups = ["ABCDEFGHJKLMNPQRSTUVWXYZ", "abcdefghijkmnopqrstuvwxyz", "23456789", "!@#$%&*+-=?"];
    const all = groups.join("");
    const chars = groups.map((group) => group[secureRandomIndex(group.length)]);
    while (chars.length < length) chars.push(all[secureRandomIndex(all.length)]);
    for (let index = chars.length - 1; index > 0; index -= 1) {
        const swap = secureRandomIndex(index + 1);
        [chars[index], chars[swap]] = [chars[swap], chars[index]];
    }
    return chars.join("");
}

function showStaffCreatedModal({ firstName, lastName, employeeId, password }) {
    root.insertAdjacentHTML("beforeend", `<div class="admin-password-backdrop" data-staff-created-backdrop><section class="admin-password-dialog admin-staff-created-dialog" role="dialog" aria-modal="true" aria-labelledby="staff-created-title"><button class="admin-password-close" type="button" data-action="close-staff-created" aria-label="Close">×</button><span class="admin-drawer-kicker">Staff account ready</span><h2 id="staff-created-title">Staff created successfully</h2><p>Provide these temporary sign-in details to <b>${esc(firstName)} ${esc(lastName)}</b>. They must choose a personal password at first sign-in. This password is shown only once.</p><label>Employee ID<input data-created-employee-id type="text" value="${esc(employeeId)}" readonly></label><label>Temporary password<input data-created-password type="text" value="${esc(password)}" readonly spellcheck="false"></label><div class="admin-password-error admin-copy-status" data-copy-status role="status" hidden></div><footer><button class="admin-button secondary" type="button" data-action="close-staff-created">Done</button><button class="admin-button primary" type="button" data-action="copy-staff-credentials">Copy details</button></footer></section></div>`);
    root.querySelector("[data-created-employee-id]")?.focus();
}

async function copyStaffCredentials() {
    const id = root.querySelector("[data-created-employee-id]")?.value || "";
    const password = root.querySelector("[data-created-password]")?.value || "";
    const statusEl = root.querySelector("[data-copy-status]");
    const details = `Employee ID: ${id}\nTemporary password: ${password}`;
    try {
        if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(details);
        else {
            const temporary = document.createElement("textarea");
            temporary.value = details;
            temporary.style.position = "fixed";
            temporary.style.opacity = "0";
            document.body.append(temporary);
            temporary.select();
            const copied = document.execCommand("copy");
            temporary.remove();
            if (!copied) throw new Error("Clipboard access was denied.");
        }
        statusEl.textContent = "Credentials copied. Share them securely.";
        statusEl.hidden = false;
    } catch {
        statusEl.textContent = "Could not copy automatically. Select and copy the details above.";
        statusEl.hidden = false;
    }
}

function openPasswordDialog(id) {
    const member = staff.find((item) => item.staff_id === id);
    if (!member) return;
    closeStaffMenus();
    closePasswordDialog();
    root.insertAdjacentHTML("beforeend", `<div class="admin-password-backdrop" data-password-dialog-backdrop><section class="admin-password-dialog admin-reset-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="password-dialog-title"><button class="admin-password-close" type="button" data-action="close-password-dialog" aria-label="Close">×</button><span class="admin-drawer-kicker">Emergency lockout override</span><h2 id="password-dialog-title">Reset staff account?</h2><p>Are you sure you want to invalidate <b>${esc(member.first_name)} ${esc(member.last_name)}</b>'s current password? Any active session will stop working, and their current station will be released. A single-use recovery code will be shown after reset.</p><footer><button class="admin-button secondary" type="button" data-action="close-password-dialog">Cancel</button><button class="admin-button primary admin-reset-account-button" type="button" data-action="confirm-staff-reset" data-id="${esc(id)}">Reset account</button></footer></section></div>`);
}

function showRecoveryCodeModal({ member, recoveryCode, expiresInMinutes }) {
    root.insertAdjacentHTML("beforeend", `<div class="admin-password-backdrop" data-recovery-code-backdrop><section class="admin-password-dialog admin-recovery-code-dialog" role="dialog" aria-modal="true" aria-labelledby="recovery-code-title"><button class="admin-password-close" type="button" data-action="close-recovery-code" aria-label="Close">×</button><span class="admin-drawer-kicker">Account recovery</span><h2 id="recovery-code-title">Password invalidated successfully</h2><p>Provide this single-use recovery code to <b>${esc(member.first_name)} ${esc(member.last_name)}</b>. They enter it with their employee ID on the standard sign-in page, then choose a new private password.</p><label>Recovery code<input class="admin-recovery-code-value" data-recovery-code type="text" value="${esc(recoveryCode)}" readonly spellcheck="false" aria-label="One-time recovery code"></label><p class="admin-recovery-expiry">This code expires in ${Number(expiresInMinutes) || 15} minutes and can only be used once.</p><div class="admin-copy-status" data-recovery-copy-status role="status" hidden></div><footer><button class="admin-button secondary" type="button" data-action="close-recovery-code">Done</button><button class="admin-button primary" type="button" data-action="copy-recovery-code">Copy recovery code</button></footer></section></div>`);
    root.querySelector("[data-recovery-code]")?.focus();
}

async function copyRecoveryCode() {
    const code = root.querySelector("[data-recovery-code]")?.value || "";
    const statusEl = root.querySelector("[data-recovery-copy-status]");
    try {
        if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(code);
        else {
            const temporary = document.createElement("textarea");
            temporary.value = code;
            temporary.style.position = "fixed";
            temporary.style.opacity = "0";
            document.body.append(temporary);
            temporary.select();
            const copied = document.execCommand("copy");
            temporary.remove();
            if (!copied) throw new Error("Clipboard access was denied.");
        }
        statusEl.textContent = "Recovery code copied. Share it directly and securely.";
    } catch {
        statusEl.textContent = "Could not copy automatically. Select and copy the code above.";
    }
    statusEl.hidden = false;
}

function openCreateStaffDrawer() {
    closeCreateStaffDrawer();
    closeStaffDrawer();
    root.insertAdjacentHTML("beforeend", `<div class="admin-drawer-backdrop" data-create-staff-drawer-backdrop><aside class="admin-staff-drawer admin-create-staff-drawer" role="dialog" aria-modal="true" aria-labelledby="create-staff-drawer-title"><header><div><span class="admin-drawer-kicker">Staff administration</span><h2 id="create-staff-drawer-title">Add new staff member</h2><p>Provision credentials and configure departmental assignment</p></div><button class="admin-drawer-close" type="button" data-action="close-create-staff-drawer" aria-label="Close">✕</button></header><form data-form="staff-create" class="admin-drawer-form-grid"><div class="admin-drawer-field full-width"><label>Employee ID<input name="employee_id" placeholder="e.g. EMP-TRIAGE01" required pattern="EMP-[A-Za-z0-9]{1,8}-?[0-9]{2,4}" title="Format: EMP-<DEPTCODE><sequence>, e.g. EMP-TRIAGE01"></label></div><div class="admin-drawer-field"><label>First name<input name="first_name" placeholder="First name" required></label></div><div class="admin-drawer-field"><label>Last name<input name="last_name" placeholder="Last name" required></label></div><div class="admin-drawer-field"><label>Role<select name="role">${roles()}</select></label></div><div class="admin-drawer-field"><label>Department<select name="dept_id">${departmentOptions()}</select></label></div><div class="admin-drawer-field full-width"><label>Temporary password</label><div class="admin-password-generate"><input name="password" type="text" placeholder="Generate temporary password" required minlength="8" maxlength="72" autocomplete="new-password" aria-label="Temporary password"><button class="admin-button secondary" type="button" data-action="generate-staff-password">Generate password</button></div></div><p class="admin-drawer-note full-width">A secure temporary password is required at first sign-in. The password will be displayed once after account creation.</p><footer class="full-width"><button class="admin-button secondary" type="button" data-action="close-create-staff-drawer">Cancel</button><button class="admin-button primary" type="submit">Create staff</button></footer></form></aside></div>`);
    root.querySelector("[data-create-staff-drawer-backdrop] input")?.focus();
}

function openStaffDrawer(id) {
    const member = staff.find((item) => item.staff_id === id);
    if (!member) return;
    closeStaffDrawer();
    closeCreateStaffDrawer();
    root.insertAdjacentHTML("beforeend", `<div class="admin-drawer-backdrop" data-staff-drawer-backdrop><aside class="admin-staff-drawer" role="dialog" aria-modal="true" aria-labelledby="staff-drawer-title"><header><div><span class="admin-drawer-kicker">Staff management</span><h2 id="staff-drawer-title">${esc(member.first_name)} ${esc(member.last_name)}</h2><p>${esc(member.employee_id)} · ${esc(member.is_on_duty ? "On duty" : "Off duty")}</p></div><button class="admin-drawer-close" type="button" data-action="close-staff-drawer" aria-label="Close">✕</button></header><form data-form="staff-manage" data-staff-id="${esc(id)}"><label>First name<input name="first_name" value="${esc(member.first_name)}" required></label><label>Last name<input name="last_name" value="${esc(member.last_name)}" required></label><label>Specialization<input name="specialization" value="${esc(member.specialization || "")}" placeholder="Optional"></label><label>Role<select name="role">${roles().replace(`value="${esc(member.role)}"`, `value="${esc(member.role)}" selected`)}</select></label><label>Department<select name="dept_id">${departmentOptions(member.dept_id)}</select></label><p class="admin-drawer-note">Role and department changes are saved through the current admin APIs.</p><footer><button class="admin-button secondary" type="button" data-action="close-staff-drawer">Cancel</button><button class="admin-button primary">Save changes</button></footer></form></aside></div>`);
    root.querySelector("[data-staff-drawer-backdrop] input")?.focus();
}

async function onClick(event) {
    if (!event.target.closest(".admin-menu-wrap")) closeStaffMenus();
    if (event.target.matches("[data-staff-drawer-backdrop]")) { closeStaffDrawer(); return; }
    if (event.target.matches("[data-create-staff-drawer-backdrop]")) { closeCreateStaffDrawer(); return; }
    if (event.target.matches("[data-password-dialog-backdrop]")) { closePasswordDialog(); return; }
    if (event.target.matches("[data-confirm-dialog-backdrop]")) { closeConfirmDialog(); return; }
    if (event.target.matches("[data-dept-edit-backdrop]")) { closeDeptEditDialog(); return; }
    if (event.target.matches("[data-sp-edit-backdrop]")) { closeServicePointEditDialog(); return; }
    if (event.target.matches("[data-staff-created-backdrop]")) { event.target.remove(); return; }
    if (event.target.matches("[data-recovery-code-backdrop]")) { event.target.remove(); return; }
    const button = event.target.closest("[data-action], [data-tab]");
    if (!button || busy) return;
    if (button.dataset.tab) { activeTab = button.dataset.tab; render(); if (activeTab === "departments") loadServicePoints(); return; }
    const { action, id } = button.dataset;
    try {
        if (action === "logout") return context?.onLogout?.();
        if (action === "staff-search-clear") { staffQuery = ""; render(); root.querySelector("[data-staff-search]")?.focus(); return; }
        if (action === "staff-page") { staffPage = Number(button.dataset.page); render(); return; }
        if (action === "staff-menu") {
            const menu = root.querySelector(`[data-staff-menu="${CSS.escape(id)}"]`);
            const opening = menu?.hidden;
            closeStaffMenus();
            if (menu && opening) { menu.hidden = false; button.setAttribute("aria-expanded", "true"); }
            return;
        }
        if (action === "manage-staff") { openStaffDrawer(id); return; }
        if (action === "close-staff-drawer") { closeStaffDrawer(); return; }
        if (action === "open-create-staff-drawer" || action === "toggle-create-staff") { openCreateStaffDrawer(); return; }
        if (action === "close-create-staff-drawer") { closeCreateStaffDrawer(); return; }
        if (action === "staff-reset-password") { openPasswordDialog(id); return; }
        if (action === "close-password-dialog") { closePasswordDialog(); return; }
        if (action === "close-confirm-dialog") { closeConfirmDialog(); return; }
        if (action === "close-dept-edit-dialog") { closeDeptEditDialog(); return; }
        if (action === "close-sp-edit-dialog") { closeServicePointEditDialog(); return; }
        if (action === "confirm-dialog-confirm") { const runConfirm = confirmDialogAction; closeConfirmDialog(); if (typeof runConfirm === "function") await runConfirm(); return; }
        if (action === "confirm-staff-reset") {
            const member = staff.find((item) => item.staff_id === id);
            if (!member) return;
            const result = await api.resetStaffPassword(id);
            closePasswordDialog();
            staff = staff.map((item) => item.staff_id === id
                ? { ...item, is_on_duty: false, active_service_point_id: null }
                : item);
            render();
            showRecoveryCodeModal({ member, recoveryCode: result.recovery_code, expiresInMinutes: result.expires_in_minutes });
            return;
        }
        if (action === "close-recovery-code") { root.querySelector("[data-recovery-code-backdrop]")?.remove(); return; }
        if (action === "copy-recovery-code") { await copyRecoveryCode(); return; }
        if (action === "generate-staff-password") {
            const input = root.querySelector('form[data-form="staff-create"] [name="password"]');
            if (input) input.value = generateTemporaryPassword();
            return;
        }
        if (action === "close-staff-created") { root.querySelector("[data-staff-created-backdrop]")?.remove(); return; }
        if (action === "copy-staff-credentials") { await copyStaffCredentials(); return; }
        if (action === "staff-toggle-active") {
            const s = staff.find((x) => x.staff_id === id);
            const activating = button.dataset.active !== "true";
            if (activating) {
                await api.setStaffActive(id, true);
                await reloadCurrent();
                return;
            }
            openConfirmDialog({
                kicker: "Account administration",
                title: `Deactivate ${s?.first_name || "this staff member"}'s account?`,
                message: "This immediately ends the staff member's access to the system. Any active session stops working and their station is released.",
                confirmLabel: "Deactivate account",
                onConfirm: async () => { await api.setStaffActive(id, false); await reloadCurrent(); },
            });
            return;
        }
        if (action === "refresh") return await reloadCurrent();
        if (action === "drill") {
            const d = await api.getDepartmentOverview(id);
            const output = root.querySelector("[data-drill-result]");
            output.innerHTML = `<div class="admin-drill-card"><b>${esc(d.name)} detail</b><span>Waiting ${d.waiting} · Called ${d.called} · In service ${d.in_progress} · Urgent ${d.critical_waiting} · Staff on duty ${d.staff_on_duty}</span></div>`;
        }
        if (action === "toggle-create-dept") root.querySelector("[data-create-dept]").hidden = !root.querySelector("[data-create-dept]").hidden;
        if (action === "dept-status") {
            const activating = button.dataset.active !== "true";
            if (activating) {
                await api.updateDepartment(id, { is_active: true });
                departments = await api.getDepartments();
                render();
                return;
            }
            const d = departments.find((x) => x.dept_id === id);
            openConfirmDialog({
                kicker: "Department administration",
                title: `Deactivate ${d?.name || "this department"}?`,
                message: "This department is removed from kiosk routing and stops accepting new queue entries. Existing queue entries are unaffected.",
                confirmLabel: "Deactivate department",
                onConfirm: async () => { await api.updateDepartment(id, { is_active: false }); departments = await api.getDepartments(); render(); },
            });
            return;
        }
        if (action === "dept-edit") { const d = departments.find((x) => x.dept_id === id); if (d) openDeptEditDialog(d); return; }
        if (action === "service-point-status") {
            const activating = button.dataset.active !== "true";
            if (activating) {
                await api.updateServicePoint(id, { is_active: true });
                await loadServicePoints();
                return;
            }
            openConfirmDialog({
                kicker: "Service point administration",
                title: "Disable this service point?",
                message: "New patients will no longer be routed or called to this station. Staff assigned here should be moved to another station first.",
                confirmLabel: "Disable service point",
                onConfirm: async () => { await api.updateServicePoint(id, { is_active: false }); await loadServicePoints(); },
            });
            return;
        }
        if (action === "service-point-edit") { await openServicePointEditDialog(id); return; }
    } catch (error) { showError(error); }
}

async function onSubmit(event) {
    const form = event.target.closest("form[data-form]");
    if (!form) return;
    event.preventDefault();
    const data = Object.fromEntries(new FormData(form).entries());
    try {
        if (form.dataset.form === "staff-create") {
            const createdCredentialDetails = {
                firstName: data.first_name,
                lastName: data.last_name,
                employeeId: data.employee_id,
                password: data.password,
            };
            await api.createStaff({ ...data, role: data.role, dept_id: data.dept_id });
            staff = await api.getStaff().catch(() => staff);
            closeCreateStaffDrawer();
            render();
            showStaffCreatedModal(createdCredentialDetails);
            return;
        } else if (form.dataset.form === "staff-manage") {
            const id = form.dataset.staffId;
            const original = staff.find((item) => item.staff_id === id);
            await api.updateStaff(id, { first_name: data.first_name, last_name: data.last_name, specialization: data.specialization || null });
            if (data.role !== original.role) await api.updateStaffRole(id, data.role);
            if (data.dept_id !== String(original.dept_id)) await api.transferStaff(id, data.dept_id);
            closeStaffDrawer();
            staff = await api.getStaff();
            render();
            notice("Staff details updated.", "success");
        } else if (form.dataset.form === "department-create") {
            data.max_capacity = Number(data.max_capacity);
            const created = await api.createDepartment(data); departments = await api.getDepartments(); selectedDepartment = created.dept_id; render(); await loadServicePoints(); return;
        } else if (form.dataset.form === "department-edit") {
            const id = form.dataset.deptId;
            await api.updateDepartment(id, { name: data.name, department_code: data.department_code, max_capacity: Number(data.max_capacity) });
            closeDeptEditDialog();
            departments = await api.getDepartments();
            render();
            notice("Department updated.", "success");
            return;
        } else if (form.dataset.form === "service-point-edit") {
            const id = form.dataset.spId;
            await api.updateServicePoint(id, { label: data.label, code: data.code });
            closeServicePointEditDialog();
            await loadServicePoints();
            notice("Service point updated.", "success");
            return;
        } else if (form.dataset.form === "service-point-create") {
            await api.createServicePoint(selectedDepartment, data);
            await loadServicePoints();
            notice("Service point created.", "success");
            return;
        } else if (form.dataset.form === "audit-filter") {
            audit = await api.getAuditLogs({ ...data, limit: 50 });
        }
        render();
    } catch (error) {
        if (form.dataset.form === "staff-manage") {
            // Profile, role, and transfer endpoints commit independently; refresh to show any saved portion.
            staff = await api.getStaff().catch(() => staff);
            closeStaffDrawer();
            render();
            notice(`${error?.message || "The update could not be completed."} Check the refreshed staff record; earlier changes may have saved.`, "error");
            return;
        }
        showError(error);
    }
}

async function onChange(event) {
    if (!event.target.matches("[data-department-select]")) return;
    selectedDepartment = event.target.value;
    await loadServicePoints();
}

async function onReset(event) {
    if (!event.target.matches('form[data-form="audit-filter"]')) return;
    event.preventDefault();
    audit = await api.getAuditLogs({ limit: 50 });
    render();
}

async function loadServicePoints() {
    const target = root?.querySelector("[data-service-points]");
    if (!target || !selectedDepartment) return;
    const departmentId = selectedDepartment;
    const loadVersion = ++servicePointLoadVersion;
    try {
        const points = await api.getServicePoints(departmentId);
        if (loadVersion !== servicePointLoadVersion || departmentId !== selectedDepartment) return;
        target.innerHTML = `<form data-form="service-point-create" class="admin-service-create"><input name="code" placeholder="Code" required><input name="label" placeholder="Desk or room label" required><select name="station_type"><option>COUNTER</option><option>ROOM</option><option>WINDOW</option><option>DOOR</option></select><button class="admin-button secondary">Add station</button></form>${points.map((p) => `<div class="admin-service-row"><span class="admin-service-icon">⌂</span><span><b>${esc(p.label)}</b><small>${esc(p.code)} · ${esc(p.station_type)}</small></span><span class="admin-pill ${p.is_active ? "success" : "muted"}">${p.is_active ? "Active" : "Inactive"}</span><button class="admin-row-button" data-action="service-point-edit" data-id="${p.service_point_id}">Edit</button><button class="admin-row-button" data-action="service-point-status" data-id="${p.service_point_id}" data-active="${p.is_active}">${p.is_active ? "Disable" : "Enable"}</button></div>`).join("") || `<div class="admin-empty-inline">No service points configured.</div>`}`;
    } catch (error) {
        if (loadVersion === servicePointLoadVersion && departmentId === selectedDepartment) target.innerHTML = empty(error.message);
    }
}

async function showError(error) { console.error("[AdminDashboard]", error); notice(error?.message || "The request could not be completed."); }
