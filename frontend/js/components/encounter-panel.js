export function getSelectedEntry(state) {
	if (!state?.selectedQueueEntryId) return null;

	return state.queueEntries.find(
		(entry) => entry.queue_entry_id === state.selectedQueueEntryId
	) || null;
}
