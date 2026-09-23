import * as api from "../../admin-api.js";

let root;
let context;
let activeTab = "overview";
let overview;
let staff = [];
let departments = [];
let audit = [];
let selectedDepartment = "";
let busy = false;
let timer;

const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const notice = (message, kind = "error") => {
    const el = root?.querySelector("[data-notice]");
    if (el) { el.textContent = message; el.className = `admin-notice ${kind}`; el.hidden = false; }
};

export function mount(container, userContext = {}) {
    root = container;
    context = userContext;
    activeTab = "overview";
    root.innerHTML = `
      <div class="admin-dashboard">
        <aside class="admin-sidebar">
          <div class="admin-sidebar-brand"><span class="admin-brand-mark">+</span><div><strong>Hospital Admin</strong><small>Operations console</small></div></div>
          <nav aria-label="Admin dashboard sections">
            <button class="admin-nav active" data-tab="overview"><span>▦</span>Overview</button>
            <button class="admin-nav" data-tab="staff"><span>♙</span>Staff</button>
            <button class="admin-nav" data-tab="departments"><span>▤</span>Departments</button>
            <button class="admin-nav" data-tab="audit"><span>◷</span>Audit trail</button>
            <button class="admin-nav future" disabled title="Not available in the backend yet"><span>⌁</span>Analytics <em>Planned</em></button>
          </nav>
          <div class="admin-sidebar-foot"><span class="admin-online-dot"></span>Connected to hospital API<button class="admin-sidebar-logout" data-action="logout">Log out</button></div>
        </aside>
        <section class="admin-main">
          <header class="admin-topbar"><div><div class="admin-eyebrow">ADMINISTRATION</div><h1 data-page-title>Hospital overview</h1></div><div class="admin-top-actions"><span class="admin-user"><span class="admin-user-avatar">${esc((userContext.firstName || "A").slice(0,1))}</span><span><b>${esc(`${userContext.firstName || "Admin"} ${userContext.lastName || ""}`)}</b><small>Administrator</small></span></span><button class="admin-refresh" data-action="refresh" aria-label="Refresh data">↻</button></div></header>
          <div data-notice class="admin-notice" hidden></div>
          <div data-content class="admin-content"><div class="admin-loading"><span class="admin-spinner"></span>Loading dashboard…</div></div>
          <footer class="admin-footer"><span>Horizon General Hospital</span><span data-last-updated></span></footer>
        </section>
      </div>`;
    root.addEventListener("click", onClick);
    root.addEventListener("submit", onSubmit);
    root.addEventListener("change", onChange);
    root.addEventListener("reset", onReset);
    loadAll().catch(showError);
    // TODO(frontend): replace interval polling when a dedicated admin WebSocket channel is available.
    timer = setInterval(() => { if (activeTab === "overview") loadOverview().catch(showError); }, 60_000);
}

export function update() { /* Admin data refresh is controlled by this workspace. */ }

export function unmount() {
    clearInterval(timer);
    root?.removeEventListener("click", onClick);
    root?.removeEventListener("submit", onSubmit);
    root?.removeEventListener("change", onChange);
    root?.removeEventListener("reset", onReset);
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
    const cards = [["Waiting", t.waiting, "Patients waiting for service", "teal"], ["In service", t.in_progress, "Currently being attended", "blue"], ["Urgent waiting", overview.critical_waiting, "Urgent or critical patients", "red"], ["Staff on duty", t.staff_on_duty, `${t.staff_active ?? 0} active staff`, "green"], ["Active visits", t.active_visits, "Visits currently open", "purple"], ["Appointments", t.appointments_today, "Scheduled today", "amber"]];
    return `<div class="admin-card-grid">${cards.map(([label, value, sub, color]) => `<article class="admin-stat-card ${color}"><span class="admin-stat-icon">${label === "Urgent waiting" ? "!" : "•"}</span><div><span>${esc(label)}</span><strong>${Number(value || 0)}</strong><small>${esc(sub)}</small></div></article>`).join("")}</div>
      <div class="admin-overview-grid"><section class="admin-panel"><div class="admin-panel-head"><div><h2>Department queues</h2><p>Current patient flow by department</p></div><span class="admin-live-label"><i></i> Live snapshot</span></div><div class="admin-table-wrap"><table><thead><tr><th>Department</th><th>Waiting</th><th>Called</th><th>In service</th><th>Urgent</th><th>On duty</th></tr></thead><tbody>${(overview.departments || []).map((d) => `<tr><td><button class="admin-link" data-action="drill" data-id="${esc(d.dept_id)}">${esc(d.name)}</button><small class="admin-cell-sub">${esc(d.code || "")}</small></td><td><b>${d.waiting || 0}</b></td><td>${d.called || 0}</td><td>${d.in_progress || 0}</td><td>${Number(d.critical_waiting || 0) ? `<span class="admin-pill danger">${d.critical_waiting}</span>` : "—"}</td><td>${d.staff_on_duty || 0}</td></tr>`).join("") || `<tr><td colspan="6">No department data.</td></tr>`}</tbody></table></div><div data-drill-result></div></section>
      <section class="admin-panel"><div class="admin-panel-head"><div><h2>On-duty roster</h2><p>${(overview.on_duty_staff || []).length} staff members checked in</p></div></div><div class="admin-roster">${(overview.on_duty_staff || []).map((s) => `<div class="admin-roster-row"><span class="admin-roster-avatar">${esc((s.full_name || "?").slice(0,1))}</span><span class="admin-roster-info"><b>${esc(s.full_name)}</b><small>${esc(s.role)} · ${esc(s.service_point_label || "No station")}</small></span><span class="admin-online-dot"></span></div>`).join("") || `<div class="admin-empty-inline">No staff currently on duty</div>`}</div></section></div>
      <p class="admin-footnote">Snapshot refreshes every 60 seconds. <span class="admin-todo">TODO: replace polling with admin WebSocket updates when the backend channel is available.</span></p>`;
}

function renderStaff() {
    return `<section class="admin-panel"><div class="admin-panel-head"><div><h2>Staff directory</h2><p>${staff.length} staff records · Role changes, transfers, password resets and account status</p></div><button class="admin-button primary" data-action="toggle-create-staff">＋ Add staff</button></div><div data-create-staff class="admin-form-panel" hidden><form data-form="staff-create" class="admin-inline-form"><input name="employee_id" placeholder="Employee ID" required><input name="first_name" placeholder="First name" required><input name="last_name" placeholder="Last name" required><select name="role">${roles()}</select><select name="dept_id">${departmentOptions()}</select><input name="password" type="password" placeholder="Initial password" required minlength="8"><button class="admin-button primary">Create staff</button></form></div><div class="admin-table-wrap"><table><thead><tr><th>Staff member</th><th>Employee ID</th><th>Department</th><th>Role</th><th>Station</th><th>Status</th><th>Actions</th></tr></thead><tbody>${staff.map((s) => `<tr><td><b>${esc(s.first_name)} ${esc(s.last_name)}</b></td><td>${esc(s.employee_id)}</td><td>${esc(departments.find((d) => d.dept_id === s.dept_id)?.name || s.department_name || "—")}</td><td><span class="admin-role-tag">${esc(s.role)}</span></td><td>${s.active_service_point_id ? "Assigned" : "—"}</td><td><span class="admin-pill ${s.is_active ? "success" : "muted"}">${s.is_active ? "Active" : "Inactive"}</span></td><td><div class="admin-row-actions"><button data-action="edit-staff" data-id="${s.staff_id}">Edit</button><button data-action="role" data-id="${s.staff_id}" title="Change role">Role</button><button data-action="transfer" data-id="${s.staff_id}" title="Transfer department">Transfer</button><button data-action="password" data-id="${s.staff_id}" title="Reset password">Reset password</button><button data-action="status" data-id="${s.staff_id}" data-active="${s.is_active}" class="${s.is_active ? "danger-text" : ""}">${s.is_active ? "Deactivate" : "Activate"}</button></div></td></tr>`).join("") || `<tr><td colspan="7">No staff records found.</td></tr>`}</tbody></table></div></section>`;
}

function renderDepartments() {
    const selected = departments.find((d) => d.dept_id === selectedDepartment) || departments[0];
    if (selected && selectedDepartment !== selected.dept_id) selectedDepartment = selected.dept_id;
    return `<div class="admin-dept-layout"><section class="admin-panel"><div class="admin-panel-head"><div><h2>Departments</h2><p>Configure hospital departments</p></div><button class="admin-button primary" data-action="toggle-create-dept">＋ Add department</button></div><div data-create-dept class="admin-form-panel" hidden><form data-form="department-create" class="admin-inline-form"><input name="name" placeholder="Department name" required><input name="department_code" placeholder="Code" maxlength="10" required><select name="type">${["OPD", "EMERGENCY", "SPECIALIST", "PAEDS"].map((x) => `<option>${x}</option>`).join("")}</select><input name="max_capacity" type="number" min="1" value="50" aria-label="Maximum capacity"><button class="admin-button primary">Create department</button></form></div><div class="admin-table-wrap"><table><thead><tr><th>Name</th><th>Code</th><th>Type</th><th>Capacity</th><th>Status</th><th></th></tr></thead><tbody>${departments.map((d) => `<tr><td><b>${esc(d.name)}</b></td><td>${esc(d.department_code)}</td><td>${esc(d.type)}</td><td>${d.max_capacity}</td><td><span class="admin-pill ${d.is_active ? "success" : "muted"}">${d.is_active ? "Active" : "Inactive"}</span></td><td><div class="admin-row-actions"><button class="admin-row-button" data-action="dept-edit" data-id="${d.dept_id}">Edit</button><button class="admin-row-button" data-action="dept-status" data-id="${d.dept_id}" data-active="${d.is_active}">${d.is_active ? "Deactivate" : "Activate"}</button></div></td></tr>`).join("") || `<tr><td colspan="6">No departments available.</td></tr>`}</tbody></table></div></section>
      <section class="admin-panel"><div class="admin-panel-head"><div><h2>Service points</h2><p>Stations configured for a department</p></div></div><label class="admin-field-label">Department<select data-department-select>${departmentOptions(selectedDepartment)}</select></label><div data-service-points class="admin-service-list">${selected ? `<div class="admin-loading"><span class="admin-spinner"></span>Loading service points…</div>` : empty("Create a department to configure service points.")}</div></section></div><p class="admin-footnote">TODO: add richer department editing and service-point availability controls as configuration needs grow.</p>`;
}

function renderAudit() {
    return `<section class="admin-panel"><div class="admin-panel-head"><div><h2>Administrative activity</h2><p>Recent changes recorded in the audit ledger</p></div></div><form data-form="audit-filter" class="admin-filter-form"><input name="action" placeholder="Filter by action (e.g. ROLE_CHANGED)"><input name="staff_id" placeholder="Staff ID"><input name="entity_type" placeholder="Entity type"><input name="entity_id" placeholder="Entity ID"><button class="admin-button secondary">Apply filters</button><button class="admin-row-button" type="reset">Clear</button></form><div class="admin-table-wrap"><table><thead><tr><th>Time</th><th>Action</th><th>Entity</th><th>Entity ID</th><th>Performed by</th><th>Details</th></tr></thead><tbody>${audit.map((item) => `<tr><td>${esc(new Date(item.created_at).toLocaleString())}</td><td><span class="admin-role-tag">${esc(item.action)}</span></td><td>${esc(item.entity_type)}</td><td><code>${esc(item.entity_id)}</code></td><td><code>${esc(item.performed_by || "System")}</code></td><td>${esc(JSON.stringify(item.payload || {}))}</td></tr>`).join("") || `<tr><td colspan="6">No audit records match these filters.</td></tr>`}</tbody></table></div><p class="admin-footnote">Showing up to 50 records. TODO: add pagination controls for larger audit histories.</p></section>`;
}

function empty(text) { return `<div class="admin-empty">${esc(text)}</div>`; }
function roles() { return ["RECEPTIONIST", "NURSE", "TRIAGE_NURSE", "DOCTOR", "ADMIN"].map((role) => `<option value="${role}">${role.replaceAll("_", " ")}</option>`).join(""); }
function departmentOptions(value = "") { return departments.map((d) => `<option value="${d.dept_id}" ${String(d.dept_id) === String(value) ? "selected" : ""}>${esc(d.name)}${d.is_active ? "" : " (inactive)"}</option>`).join(""); }

async function onClick(event) {
    const button = event.target.closest("[data-action], [data-tab]");
    if (!button || busy) return;
    if (button.dataset.tab) { activeTab = button.dataset.tab; render(); if (activeTab === "departments") loadServicePoints(); return; }
    const { action, id } = button.dataset;
    try {
        if (action === "logout") return context?.onLogout?.();
        if (action === "refresh") return await reloadCurrent();
        if (action === "drill") {
            const d = await api.getDepartmentOverview(id);
            const output = root.querySelector("[data-drill-result]");
            output.innerHTML = `<div class="admin-drill-card"><b>${esc(d.name)} detail</b><span>Waiting ${d.waiting} · Called ${d.called} · In service ${d.in_progress} · Urgent ${d.critical_waiting} · Staff on duty ${d.staff_on_duty}</span></div>`;
        }
        if (action === "toggle-create-staff") root.querySelector("[data-create-staff]").hidden = !root.querySelector("[data-create-staff]").hidden;
        if (action === "toggle-create-dept") root.querySelector("[data-create-dept]").hidden = !root.querySelector("[data-create-dept]").hidden;
        if (action === "role") { const s = staff.find((x) => x.staff_id === id); const value = prompt(`New role for ${s.first_name} ${s.last_name}:\n${["RECEPTIONIST", "NURSE", "TRIAGE_NURSE", "DOCTOR", "ADMIN"].join(", ")}`, s.role); if (value) await api.updateStaffRole(id, value.toUpperCase()); await reloadCurrent(); }
        if (action === "edit-staff") { const s = staff.find((x) => x.staff_id === id); const first_name = prompt("First name", s.first_name); if (first_name === null) return; const last_name = prompt("Last name", s.last_name); if (last_name === null) return; const specialization = prompt("Specialization (leave blank to clear)", s.specialization || ""); if (specialization === null) return; await api.updateStaff(id, { first_name, last_name, specialization: specialization || null }); await reloadCurrent(); }
        if (action === "transfer") { const s = staff.find((x) => x.staff_id === id); const value = prompt(`Enter the destination department ID for ${s.first_name} ${s.last_name}:\n${departments.map((d) => `${d.name}: ${d.dept_id}`).join("\n")}`); if (value) await api.transferStaff(id, value.trim()); await reloadCurrent(); }
        if (action === "password") { const value = prompt("Enter a temporary password (at least 8 characters):"); if (value) { await api.resetStaffPassword(id, value); notice("Password reset successfully.", "success"); } }
        if (action === "status") { await api.setStaffActive(id, button.dataset.active !== "true"); await reloadCurrent(); }
        if (action === "dept-status") { await api.updateDepartment(id, { is_active: button.dataset.active !== "true" }); departments = await api.getDepartments(); render(); }
        if (action === "dept-edit") { const d = departments.find((x) => x.dept_id === id); const name = prompt("Department name", d.name); if (name === null) return; const department_code = prompt("Department code", d.department_code); if (department_code === null) return; const max_capacity = prompt("Maximum capacity", d.max_capacity); if (max_capacity === null) return; await api.updateDepartment(id, { name, department_code, max_capacity: Number(max_capacity) }); departments = await api.getDepartments(); render(); }
        if (action === "service-point-status") { await api.updateServicePoint(id, { is_active: button.dataset.active !== "true" }); await loadServicePoints(); }
        if (action === "service-point-edit") { const point = await api.getServicePoints(selectedDepartment).then((items) => items.find((item) => item.service_point_id === id)); if (!point) return; const label = prompt("Station label", point.label); if (label === null) return; const code = prompt("Station code", point.code); if (code === null) return; await api.updateServicePoint(id, { label, code }); await loadServicePoints(); }
    } catch (error) { showError(error); }
}

async function onSubmit(event) {
    const form = event.target.closest("form[data-form]");
    if (!form) return;
    event.preventDefault();
    const data = Object.fromEntries(new FormData(form).entries());
    try {
        if (form.dataset.form === "staff-create") {
            await api.createStaff({ ...data, role: data.role, dept_id: data.dept_id });
            staff = await api.getStaff(); form.reset(); root.querySelector("[data-create-staff]").hidden = true;
        } else if (form.dataset.form === "department-create") {
            data.max_capacity = Number(data.max_capacity);
            const created = await api.createDepartment(data); departments = await api.getDepartments(); selectedDepartment = created.dept_id; render(); await loadServicePoints(); return;
        } else if (form.dataset.form === "service-point-create") {
            await api.createServicePoint(selectedDepartment, data);
            await loadServicePoints();
            notice("Service point created.", "success");
            return;
        } else if (form.dataset.form === "audit-filter") {
            audit = await api.getAuditLogs({ ...data, limit: 50 });
        }
        render();
    } catch (error) { showError(error); }
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
    try {
        const points = await api.getServicePoints(selectedDepartment);
        target.innerHTML = `<form data-form="service-point-create" class="admin-service-create"><input name="code" placeholder="Code" required><input name="label" placeholder="Desk or room label" required><select name="station_type"><option>COUNTER</option><option>ROOM</option><option>WINDOW</option><option>DOOR</option></select><button class="admin-button secondary">Add station</button></form>${points.map((p) => `<div class="admin-service-row"><span class="admin-service-icon">⌂</span><span><b>${esc(p.label)}</b><small>${esc(p.code)} · ${esc(p.station_type)}</small></span><span class="admin-pill ${p.is_active ? "success" : "muted"}">${p.is_active ? "Active" : "Inactive"}</span><button class="admin-row-button" data-action="service-point-edit" data-id="${p.service_point_id}">Edit</button><button class="admin-row-button" data-action="service-point-status" data-id="${p.service_point_id}" data-active="${p.is_active}">${p.is_active ? "Disable" : "Enable"}</button></div>`).join("") || `<div class="admin-empty-inline">No service points configured.</div>`}`;
    } catch (error) { target.innerHTML = empty(error.message); }
}

async function showError(error) { console.error("[AdminDashboard]", error); notice(error?.message || "The request could not be completed."); }
