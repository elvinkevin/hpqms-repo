import {
	getState,
	selectQueueEntry,
} from "../staff-queue-state.js";

const elements = {
	activeCount: document.getElementById("activeCount"),
	lastUpdated: document.getElementById("lastUpdated"),
	searchInput: document.getElementById("searchInput"),
	queueBody: document.getElementById("queueTableBody"),
	noShowBody: document.getElementById("noshowTableBody"),
	noShowState: document.getElementById("noshowState"),
	noShowPanel: document.getElementById("noshowPanel"),
	queueTableWrapper: document.querySelector(".queue-table-wrapper"),
	queueFooter: document.querySelector(".queue-footer"),
	statusTabs: [...document.querySelectorAll(".status-tab")],
};

let activeFilter = "all";
let searchTerm = "";

function getPatient(entry) {
	return entry?.visit?.patient || entry?.visit?.patient_summary || {};
}

function getPatientName(entry) {
	const patient = getPatient(entry);
	return [patient.first_name, patient.last_name].filter(Boolean).join(" ")
		|| patient.temporary_identifier
		|| patient.national_id
		|| "Unknown patient";
}

function getToken(entry) {
	return entry?.visit?.token_number || `#${entry?.sequence_number ?? "?"}`;
}

function matchesFilter(entry) {
	const status = entry.status?.toLowerCase().replace("_", "-");
	const matchesStatus = activeFilter === "all" || status === activeFilter;
	const haystack = `${getToken(entry)} ${getPatientName(entry)}`.toLowerCase();
	return matchesStatus && haystack.includes(searchTerm);
}

function renderQueue(state) {
	if (!elements.queueBody) return;

	const entries = activeFilter === "no-show"
		? []
		: state.queueEntries.filter(matchesFilter);
	elements.queueBody.innerHTML = "";

	for (const entry of entries) {
		const row = document.createElement("tr");
		row.className = "queue-row";
		row.dataset.entryId = entry.queue_entry_id;
		if (entry.queue_entry_id === state.selectedQueueEntryId) {
			row.classList.add("selected");
		}

		row.innerHTML = `
			<td class="token-id">${getToken(entry)}</td>
			<td class="patient-name">${getPatientName(entry)}</td>
			<td class="wait-time">${entry.wait_time_minutes ?? "-"}</td>
			<td><span class="priority ${String(entry.priority || "").toLowerCase()}">${entry.priority || "-"}</span></td>
			<td><span class="status ${String(entry.status || "").toLowerCase().replace("_", "-" )}">${entry.status || "-"}</span></td>
		`;
		row.addEventListener("click", () => selectQueueEntry(entry.queue_entry_id));
		elements.queueBody.appendChild(row);
	}
}

function renderNoShow(state) {
	if (!elements.noShowBody) return;

	elements.noShowBody.innerHTML = "";
	for (const entry of state.noShowEntries) {
		const row = document.createElement("tr");
		row.dataset.entryId = entry.queue_entry_id;
		row.innerHTML = `
			<td>${getToken(entry)}</td>
			<td><button type="button" class="noshow-btn requeue-button" data-entry-id="${entry.queue_entry_id}">Re-Queue</button></td>
		`;
		elements.noShowBody.appendChild(row);
	}

	if (elements.noShowState) {
		elements.noShowState.textContent = state.noShowEntries.length
			? ""
			: "No patients are currently marked as no-show.";
	}
}

export function renderQueuePanel(state = getState()) {
	const activeEntries = state.queueEntries.filter(
		(entry) => ["WAITING", "CALLED", "IN_PROGRESS"].includes(entry.status)
	);
	const statusCounts = activeEntries.reduce((counts, entry) => {
		const status = entry.status?.toLowerCase().replace("_", "-");
		counts[status] = (counts[status] || 0) + 1;
		return counts;
	}, {});

	if (elements.activeCount) {
		elements.activeCount.textContent = `${activeEntries.length + state.noShowEntries.length} Active`;
	}
	if (elements.lastUpdated) {
		elements.lastUpdated.textContent = `Last updated: ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
	}

	for (const tab of elements.statusTabs) {
		const count = tab.dataset.status === "all"
			? activeEntries.length
			: tab.dataset.status === "no-show"
				? state.noShowEntries.length
			: statusCounts[tab.dataset.status] || 0;
		const countElement = tab.querySelector(".status-count");
		if (countElement) countElement.textContent = count;
	}

	if (elements.noShowPanel) {
		elements.noShowPanel.classList.toggle("hidden", activeFilter !== "no-show");
	}
	if (elements.queueTableWrapper) {
		elements.queueTableWrapper.classList.toggle("hidden", activeFilter === "no-show");
	}
	if (elements.queueFooter) {
		elements.queueFooter.classList.toggle("hidden", activeFilter !== "all");
	}

	renderQueue(state);
	renderNoShow(state);
}

export function initializeQueuePanel({ onRefresh, onRequeue } = {}) {
	elements.searchInput?.addEventListener("input", (event) => {
		searchTerm = event.target.value.trim().toLowerCase();
		renderQueuePanel();
	});

	for (const tab of elements.statusTabs) {
		tab.addEventListener("click", () => {
			activeFilter = tab.dataset.status || "all";
			elements.statusTabs.forEach((item) => item.classList.toggle("active", item === tab));
			renderQueuePanel();
		});
	}

	document.getElementById("refreshBtn")?.addEventListener("click", () => onRefresh?.());
	elements.noShowBody?.addEventListener("click", (event) => {
		const button = event.target.closest(".requeue-button");
		if (button) onRequeue?.(button.dataset.entryId, button);
	});
}
