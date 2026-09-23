import { request, HTTP_METHOD } from "./api.js";
import { getAccessToken } from "./staff-session.js";

async function adminRequest(path, method = HTTP_METHOD.GET, body) {
    const token = getAccessToken();
    if (!token) throw new Error("Your session has expired. Please sign in again.");
    return request(path, {
        method,
        headers: { Authorization: `Bearer ${token}` },
        ...(body === undefined ? {} : { body }),
    });
}

export const getOverview = () => adminRequest("/admin/overview");
export const getDepartmentOverview = (id) => adminRequest(`/admin/departments/${encodeURIComponent(id)}/overview`);
export const getAuditLogs = (filters = {}) => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(filters)) if (value !== "" && value != null) query.set(key, value);
    const encoded = query.toString();
    return adminRequest(`/admin/audit-logs${encoded ? `?${encoded}` : ""}`);
};
export const getStaff = () => adminRequest("/staff/?active_only=false");
export const createStaff = (body) => adminRequest("/staff/", HTTP_METHOD.POST, body);
export const updateStaff = (id, body) => adminRequest(`/staff/${id}`, HTTP_METHOD.PUT, body);
export const updateStaffRole = (id, role) => adminRequest(`/staff/${id}/role`, HTTP_METHOD.PATCH, { role });
export const transferStaff = (id, dept_id) => adminRequest(`/staff/${id}/transfer`, HTTP_METHOD.PATCH, { dept_id });
export const resetStaffPassword = (id, new_password) => adminRequest(`/staff/${id}/reset-password`, HTTP_METHOD.PATCH, { new_password });
export const setStaffActive = (id, active) => adminRequest(`/staff/${id}/${active ? "activate" : "deactivate"}`, HTTP_METHOD.PATCH);
export const getDepartments = () => adminRequest("/departments");
export const createDepartment = (body) => adminRequest("/departments", HTTP_METHOD.POST, body);
export const updateDepartment = (id, body) => adminRequest(`/departments/${id}`, HTTP_METHOD.PATCH, body);
export const getServicePoints = (id) => adminRequest(`/departments/${id}/service-points`);
export const createServicePoint = (id, body) => adminRequest(`/departments/${id}/service-points`, HTTP_METHOD.POST, body);
export const updateServicePoint = (id, body) => adminRequest(`/service-points/${id}`, HTTP_METHOD.PATCH, body);
