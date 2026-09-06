export function mount(container, context) {
    container.innerHTML = `
        <div class="workspace-placeholder">
            <h3>Workspace Ready</h3>
            <p>Role-specific tools will appear here.</p>
        </div>
    `;
}

export function update(container, context) {
    // Intentionally empty for now.
}

export function unmount() {
    // No cleanup required yet.
}