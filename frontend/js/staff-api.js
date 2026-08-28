/* ==========================================================================
   HPQMS Staff Dashboard API Helpers
   js/staff-api.js
   ========================================================================== */

import { request, HTTP_METHOD } from "./api.js";

const authState = {
    accessToken: null,
    currentUser: null,
};

function buildAuthHeaders() {
    if (!authState.accessToken) {
        return {};
    }

    return {
        Authorization: `Bearer ${authState.accessToken}`,
    };
}

async function login(credentials) {
    const response = await request("/auth/login", {
        method: HTTP_METHOD.POST,
        body: credentials,
    });

    authState.accessToken = response.access_token;

    return response;
}


async function getCurrentUser() {
    const response = await request("/auth/me", {
        method: HTTP_METHOD.GET,
        headers: buildAuthHeaders(),
    });

    authState.currentUser = response;

    return response;
}

function logout() {
    authState.accessToken = null;
    authState.currentUser = null;
}


async function getDepartments() {
    return request("/departments/active", {
        method: HTTP_METHOD.GET,
        headers: buildAuthHeaders(),
    });
}

async function getDepartmentQueue(departmentId) {
    return request(`/queue/department/${departmentId}`, {
        method: HTTP_METHOD.GET,
        headers: buildAuthHeaders(),
    });
}

async function getDepartmentNoShowQueue(departmentId) {
    return request(`/queue/department/${departmentId}/no-show`, {
        method: HTTP_METHOD.GET,
        headers: buildAuthHeaders(),
    });
}

async function callQueueEntry(queueEntryId) {
    return request(`/queue/${queueEntryId}/call`, {
        method: HTTP_METHOD.PATCH,
        headers: buildAuthHeaders(),
    });
}

async function startQueueEntry(queueEntryId) {
    return request(`/queue/${queueEntryId}/start`, {
        method: HTTP_METHOD.PATCH,
        headers: buildAuthHeaders(),
    });
}

async function completeQueueEntry(queueEntryId) {
    return request(`/queue/${queueEntryId}/complete`, {
        method: HTTP_METHOD.PATCH,
        headers: buildAuthHeaders(),
    });
}

async function markNoShowQueueEntry(queueEntryId) {
    return request(`/queue/${queueEntryId}/no-show`, {
        method: HTTP_METHOD.PATCH,
        headers: buildAuthHeaders(),
    });
}

async function requeueQueueEntry(queueEntryId) {
    return request(`/queue/${queueEntryId}/requeue`, {
        method: HTTP_METHOD.PATCH,
        headers: buildAuthHeaders(),
    });
}

async function getNextPatient(departmentId) {
    return request(`/queue/department/${departmentId}/next`, {
        method: HTTP_METHOD.GET,
        headers: buildAuthHeaders(),
    });
}

async function completePatientRegistration(patientId, data) {
    return request(`/patients/${patientId}/complete-registration`, {
        method: HTTP_METHOD.PATCH,
        headers: buildAuthHeaders(),
        body: data,
    });
}


export {
    login,
    logout,
    getDepartments,
    getDepartmentQueue,
    getDepartmentNoShowQueue,
    callQueueEntry,
    startQueueEntry,
    completeQueueEntry,
    markNoShowQueueEntry,
    requeueQueueEntry,
    getNextPatient,
    getCurrentUser,
    completePatientRegistration,
};