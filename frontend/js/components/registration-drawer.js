/* ==========================================================================
   HPQMS Staff Dashboard — Registration Drawer
   js/components/registration-drawer.js

   Owns the complete patient registration UI.

   Responsibilities:
   - Render registration drawer
   - Pre-fill available patient information
   - Validate registration input
   - Submit registration through the supplied action
   - Handle loading/error/success states

   Does NOT:
   - own queue state
   - fetch patients
   - perform API calls directly
   - determine staff permissions
   ========================================================================== */

let overlay = null;
let drawer = null;
let patient = null;
let submitHandler = null;
let isDirty = false;


/* ==========================================================================
   PUBLIC API
   ========================================================================== */

/**
 * Opens the Registration Drawer.
 * @param {Object} patientData - Active patient object
 * @param {Object} options - Configuration containing { onSubmit }
 */
export function open(patientData, options = {}) {
    if (!patientData) {
        throw new Error("Registration drawer requires a patient.");
    }

    patient = patientData;

    // 1. Store callback directly in module-level scope
    submitHandler = typeof options.onSubmit === "function" ? options.onSubmit : null;

    // 2. Render drawer DOM structure. render() attaches its own
    //    listeners internally (see bottom of render()) — do not call
    //    attachListeners() again here, or every close/cancel/overlay
    //    click ends up with two identical handlers.
    render();

    // 3. Reveal drawer UI
    show();
}


export function close(force = false) {
    if (!overlay) {
        return;
    }

    if (!force && isDirty) {
        const confirmed = window.confirm(
            "You have unsaved registration information. Close without saving?"
        );

        if (!confirmed) {
            return;
        }
    }

    destroy();
}


export function isOpen() {
    return Boolean(overlay);
}


/**
 * Full teardown: removes the DOM and clears all module state. This is
 * the public "close everything" entry point.
 *
 * NOTE: render() does its own lighter-weight DOM reset (resetDom())
 * rather than calling this — destroy() nulls `patient` and
 * `submitHandler`, which render() still needs mid-build. Calling
 * destroy() from inside render() previously wiped the very state
 * open() had just set, so every drawer opened blank and every submit
 * failed with "submit handler is not configured."
 */
export function destroy() {
    resetDom();

    patient = null;
    submitHandler = null;
    isDirty = false;

    document.removeEventListener("keydown", handleEscape);
    document.body.classList.remove("registration-drawer-open");
}


/**
 * Removes any existing drawer DOM without touching `patient` /
 * `submitHandler`. Safe to call at the top of render() to clear a
 * stale previous instance before building a fresh one.
 */
function resetDom() {
    if (overlay) {
        overlay.remove();
    }

    overlay = null;
    drawer = null;
}


/* ==========================================================================
   RENDER
   ========================================================================== */

function render() {
    resetDom();

    const details = getPatientDetails(patient);

    overlay = document.createElement("div");
    overlay.className = "registration-overlay";
    overlay.setAttribute("aria-hidden", "false");

    drawer = document.createElement("aside");
    drawer.className = "registration-drawer";
    drawer.setAttribute("role", "dialog");
    drawer.setAttribute("aria-modal", "true");
    drawer.setAttribute(
        "aria-labelledby",
        "registrationDrawerTitle"
    );

    drawer.innerHTML = `
        <header class="registration-drawer-header">
            <div>
                <span class="registration-eyebrow">
                    RECEPTION
                </span>

                <h2 id="registrationDrawerTitle">
                    Complete Patient Registration
                </h2>

                <p>
                    Complete the required administrative information
                    before continuing with this patient.
                </p>
            </div>

            <button
                type="button"
                class="registration-close-btn"
                id="registrationCloseBtn"
                aria-label="Close registration">
                ×
            </button>
        </header>

        <div class="registration-drawer-body">

            ${renderPatientContext(details)}

            <form
                id="registrationForm"
                class="registration-form"
                novalidate>

                <section class="registration-section">
                    <div class="registration-section-heading">
                        <h3>Patient Identity</h3>
                        <p>Required administrative information.</p>
                    </div>

                    <div class="registration-grid">

                        ${inputField(
                            "first_name",
                            "First Name",
                            details.first_name,
                            true
                        )}

                        ${inputField(
                            "last_name",
                            "Last Name",
                            details.last_name,
                            true
                        )}

                        ${inputField(
                            "date_of_birth",
                            "Date of Birth",
                            details.date_of_birth,
                            true,
                            "date"
                        )}

                        ${selectField(
                            "gender",
                            "Gender",
                            details.gender,
                            [
                                ["", "Select gender"],
                                ["Male", "Male"],
                                ["Female", "Female"],
                                ["Other", "Other"],
                            ],
                            true
                        )}

                    </div>
                </section>


                <section class="registration-section">
                    <div class="registration-section-heading">
                        <h3>Identity & Contact</h3>
                        <p>
                            Provide at least one contact method.
                        </p>
                    </div>

                    <div class="registration-grid">

                        ${inputField(
                            "national_id",
                            "National ID",
                            details.national_id
                        )}

                        ${inputField(
                            "phone",
                            "Phone",
                            details.phone,
                            false,
                            "tel"
                        )}

                        ${inputField(
                            "email",
                            "Email",
                            details.email,
                            false,
                            "email",
                            "registration-full-width"
                        )}

                    </div>

                    <p
                        id="contactRequirement"
                        class="registration-hint">
                        Phone or email is required.
                    </p>

                </section>


                <section class="registration-section">
                    <div class="registration-section-heading">
                        <h3>Additional Information</h3>
                        <p>Optional patient information.</p>
                    </div>

                    <div class="registration-grid">

                        ${selectField(
                            "blood_type",
                            "Blood Type",
                            details.blood_type,
                            [
                                ["", "Not specified"],
                                ["A+", "A+"],
                                ["A-", "A-"],
                                ["B+", "B+"],
                                ["B-", "B-"],
                                ["AB+", "AB+"],
                                ["AB-", "AB-"],
                                ["O+", "O+"],
                                ["O-", "O-"],
                            ]
                        )}

                        ${textareaField(
                            "allergies",
                            "Allergies",
                            details.allergies,
                            "registration-full-width"
                        )}

                    </div>
                </section>


                <div
                    id="registrationFormError"
                    class="registration-form-error"
                    role="alert"
                    aria-live="assertive"
                    hidden>
                </div>

            </form>
        </div>


        <footer class="registration-drawer-footer">

            <button
                type="button"
                class="registration-secondary-btn"
                id="registrationCancelBtn">
                Cancel
            </button>

            <button
                type="submit"
                form="registrationForm"
                class="registration-primary-btn"
                id="registrationSubmitBtn">
                Complete Registration
            </button>

        </footer>
    `;

    overlay.appendChild(drawer);
    document.body.appendChild(overlay);

    document.body.classList.add("registration-drawer-open");

    attachListeners();

    requestAnimationFrame(() => {
        drawer?.querySelector("#first_name")?.focus();
    });
}


/* ==========================================================================
   PATIENT CONTEXT
   ========================================================================== */

function renderPatientContext(details) {
    const token = getToken(patient);
    const patientLabel =
        getPatientName(patient) !== "Patient"
            ? getPatientName(patient)
            : "Patient registration";

    return `
        <section class="registration-patient-context">

            <div>
                <span>Patient</span>
                <strong>${escapeHtml(patientLabel)}</strong>
            </div>

            <div>
                <span>Token</span>
                <strong>${escapeHtml(token)}</strong>
            </div>

        </section>
    `;
}


/* ==========================================================================
   FIELD BUILDERS
   ========================================================================== */

function inputField(
    name,
    label,
    value = "",
    required = false,
    type = "text",
    extraClass = ""
) {
    return `
        <div class="registration-field ${extraClass}">
            <label for="${name}">
                ${escapeHtml(label)}
                ${required ? '<span class="required">*</span>' : ""}
            </label>

            <input
                id="${name}"
                name="${name}"
                type="${type}"
                value="${escapeHtml(value ?? "")}"
                ${required ? "required" : ""}
                autocomplete="off">

            <small
                class="field-error"
                data-error-for="${name}"
                hidden>
            </small>
        </div>
    `;
}


function selectField(
    name,
    label,
    value,
    options,
    required = false
) {
    return `
        <div class="registration-field">
            <label for="${name}">
                ${escapeHtml(label)}
                ${required ? '<span class="required">*</span>' : ""}
            </label>

            <select
                id="${name}"
                name="${name}"
                ${required ? "required" : ""}>

                ${options.map(([optionValue, optionLabel]) => `
                    <option
                        value="${escapeHtml(optionValue)}"
                        ${optionValue === value ? "selected" : ""}>
                        ${escapeHtml(optionLabel)}
                    </option>
                `).join("")}

            </select>

            <small
                class="field-error"
                data-error-for="${name}"
                hidden>
            </small>
        </div>
    `;
}


function textareaField(
    name,
    label,
    value = "",
    extraClass = ""
) {
    return `
        <div class="registration-field ${extraClass}">
            <label for="${name}">
                ${escapeHtml(label)}
            </label>

            <textarea
                id="${name}"
                name="${name}"
                rows="3">${escapeHtml(value ?? "")}</textarea>

            <small
                class="field-error"
                data-error-for="${name}"
                hidden>
            </small>
        </div>
    `;
}


/* ==========================================================================
   VISIBILITY
   ========================================================================== */

/**
 * Reveals the drawer. Split from render() so a CSS entrance transition
 * (drawer sliding in, overlay fading in) can key off these "visible"
 * classes rather than jumping straight to final state. If no such
 * transition is defined yet, this is still required — render() creates
 * the DOM, but nothing previously made it visible or focus-managed
 * before this call was added (open() called a show() that didn't
 * exist, so the drawer could never actually open).
 */
function show() {
    if (!overlay || !drawer) {
        return;
    }

    // Force layout so an initial (pre-transition) state, if defined in
    // CSS, is committed before the "visible" class kicks off a
    // transition rather than skipping straight to the end state.
    void drawer.offsetWidth;

    requestAnimationFrame(() => {
        overlay?.classList.add("registration-overlay-visible");
        drawer?.classList.add("registration-drawer-visible");
    });
}


/* ==========================================================================
   EVENTS
   ========================================================================== */

function attachListeners() {
    const closeBtn = drawer.querySelector("#registrationCloseBtn");
    const cancelBtn = drawer.querySelector("#registrationCancelBtn");
    const form = drawer.querySelector("#registrationForm");

    closeBtn?.addEventListener("click", () => close());
    cancelBtn?.addEventListener("click", () => close());

    overlay?.addEventListener("click", (event) => {
        if (event.target === overlay) {
            close();
        }
    });

    if (form) {
        // Remove existing listener to avoid duplicates if re-attached
        form.removeEventListener("submit", handleSubmit);
        form.addEventListener("submit", handleSubmit);

        form.addEventListener("input", () => {
            isDirty = true;
            clearFormError();
        });
    }

    // Single document-level escape key handler
    document.removeEventListener("keydown", handleEscape);
    document.addEventListener("keydown", handleEscape);
}

function handleEscape(event) {
    if (event.key === "Escape" && isOpen()) {
        close();
    }
}

/* ==========================================================================
   SUBMISSION
   ========================================================================== */

async function handleSubmit(event) {
    event.preventDefault();

    clearFieldErrors();
    clearFormError();

    const form = event.currentTarget;
    const payload = collectPayload(form);
    const validationErrors = validatePayload(payload);

    if (Object.keys(validationErrors).length > 0) {
        displayValidationErrors(validationErrors);
        return;
    }

    setSubmitting(true);

    try {
        if (typeof submitHandler !== "function") {
            throw new Error("Registration submit handler is not configured.");
        }

        // Execute callback
        await submitHandler(payload);

        isDirty = false;
        showSuccessState();

    } catch (error) {
        console.error(
            "[RegistrationDrawer] Registration failed:",
            error
        );

        showFormError(
            error?.message ||
            "Unable to complete registration. Please try again."
        );

        setSubmitting(false);
    }
}



/* ==========================================================================
   PAYLOAD
   ========================================================================== */

function collectPayload(form) {
    const formData = new FormData(form);

    return {
        first_name: clean(formData.get("first_name")),
        last_name: clean(formData.get("last_name")),
        date_of_birth: clean(formData.get("date_of_birth")),
        gender: clean(formData.get("gender")),

        national_id: cleanOrNull(formData.get("national_id")),
        phone: cleanOrNull(formData.get("phone")),
        email: cleanOrNull(formData.get("email")),

        blood_type: cleanOrNull(formData.get("blood_type")),
        allergies: cleanOrNull(formData.get("allergies")),
    };
}


/* ==========================================================================
   VALIDATION
   ========================================================================== */

function validatePayload(payload) {
    const errors = {};

    if (!payload.first_name) {
        errors.first_name = "First name is required.";
    }

    if (!payload.last_name) {
        errors.last_name = "Last name is required.";
    }

    if (!payload.date_of_birth) {
        errors.date_of_birth = "Date of birth is required.";
    }

    if (!payload.gender) {
        errors.gender = "Gender is required.";
    }

    if (!payload.phone && !payload.email) {
        errors.phone = "Phone or email is required.";
        errors.email = "Phone or email is required.";
    }

    if (
        payload.email &&
        !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(payload.email)
    ) {
        errors.email = "Enter a valid email address.";
    }

    return errors;
}


/* ==========================================================================
   UI STATE
   ========================================================================== */

function setSubmitting(submitting) {
    const button = drawer.querySelector(
        "#registrationSubmitBtn"
    );

    if (!button) {
        return;
    }

    button.disabled = submitting;

    button.innerHTML = submitting
        ? `<span class="registration-spinner"></span> Completing...`
        : "Complete Registration";
}


function showSuccessState() {
    const body = drawer.querySelector(
        ".registration-drawer-body"
    );

    const footer = drawer.querySelector(
        ".registration-drawer-footer"
    );

    if (!body || !footer) {
        return;
    }

    body.innerHTML = `
        <div class="registration-success">

            <div class="registration-success-icon">
                ✓
            </div>

            <h3>Registration Complete</h3>

            <p>
                Patient registration has been successfully completed.
            </p>

        </div>
    `;

    footer.innerHTML = `
        <button
            type="button"
            class="registration-primary-btn"
            id="registrationDoneBtn">
            Done
        </button>
    `;

    footer
        .querySelector("#registrationDoneBtn")
        ?.addEventListener("click", () => {
            close(true);
        });
}


function displayValidationErrors(errors) {
    Object.entries(errors).forEach(([field, message]) => {
        const input = drawer.querySelector(`#${field}`);
        const error = drawer.querySelector(
            `[data-error-for="${field}"]`
        );

        input?.classList.add("field-invalid");

        if (error) {
            error.textContent = message;
            error.hidden = false;
        }
    });
}


function clearFieldErrors() {
    drawer?.querySelectorAll(".field-invalid")
        .forEach((element) => {
            element.classList.remove("field-invalid");
        });

    drawer?.querySelectorAll(".field-error")
        .forEach((element) => {
            element.hidden = true;
            element.textContent = "";
        });
}


function showFormError(message) {
    const error = drawer?.querySelector(
        "#registrationFormError"
    );

    if (!error) {
        return;
    }

    error.textContent = message;
    error.hidden = false;
}


function clearFormError() {
    const error = drawer?.querySelector(
        "#registrationFormError"
    );

    if (error) {
        error.hidden = true;
        error.textContent = "";
    }
}


/* ==========================================================================
   DATA HELPERS
   ========================================================================== */

function getPatientDetails(data) {
    return (
        data?.visit?.patient ||
        data?.patient ||
        data ||
        {}
    );
}


function getToken(data) {
    return (
        data?.token_number ??
        data?.visit?.token_number ??
        data?.token ??
        "—"
    );
}


function getPatientName(data) {
    const details = getPatientDetails(data);

    const explicitName =
        data?.patient_name ??
        details?.patient_name;

    if (explicitName) {
        return explicitName;
    }

    const name = [
        details?.first_name,
        details?.last_name,
    ]
        .filter(Boolean)
        .join(" ")
        .trim();

    return name || "Patient";
}


/* ==========================================================================
   UTILITIES
   ========================================================================== */

function clean(value) {
    return String(value ?? "").trim();
}


function cleanOrNull(value) {
    const cleaned = clean(value);
    return cleaned || null;
}


function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}