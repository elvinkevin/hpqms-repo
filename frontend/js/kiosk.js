// =============================================
// HPQMS - Patient Check-In Kiosk
// Prototype Version (Local Storage)
// =============================================

const form = document.getElementById("kioskForm");
const input = document.getElementById("patientIdentifier");
const errorMsg = document.getElementById("errorMsg");
const ticketCard = document.getElementById("ticketModal");
const tokenDisplay = document.getElementById("generatedToken");
const issueTimeDisplay = document.getElementById("issueTime");
const issueDateDisplay = document.getElementById("issueDate");
const maskedIdentifierDisplay = document.getElementById("maskedIdentifier");
const submitButton = form.querySelector("button");

// ---------------------------------------------
// Validation
// ---------------------------------------------

function validateIdentifier(identifier) {
    // Kenyan Phone Number
    const phoneRegex = /^(07\d{8}|01\d{8}|2547\d{8}|2541\d{8})$/;

    // Kenyan National ID (6–10 digits)
    const idRegex = /^\d{6,10}$/;

    return phoneRegex.test(identifier) || idRegex.test(identifier);
}

// ---------------------------------------------
// Token Generator (Prototype)
// Backend will eventually replace this.
// ---------------------------------------------

function generateToken() {

    let sequence =
        parseInt(localStorage.getItem("hpqms_daily_sequence") || "0") + 1;

    localStorage.setItem("hpqms_daily_sequence", sequence);

    return `R${String(sequence).padStart(3, "0")}`;
}

// ---------------------------------------------
// Mask identifier for ticket display
// ---------------------------------------------

function maskIdentifier(identifier) {
    const cleaned = String(identifier).trim();

    if (cleaned.length <= 4) {
        return "*".repeat(cleaned.length);
    }

    const visible = cleaned.slice(-4);
    const masked = "*".repeat(cleaned.length - 4);

    return `${masked}${visible}`;
}

// ---------------------------------------------
// Save Check-In
// ---------------------------------------------

function saveCheckIn(identifier, token) {

    const queue =
        JSON.parse(localStorage.getItem("hpqms_queue") || "[]");

    const record = {

        check_in_id: crypto.randomUUID(),

        token,

        identifier,

        status: "CHECKED_IN",

        checked_in_at: new Date().toISOString()

    };

    queue.push(record);

    localStorage.setItem(
        "hpqms_queue",
        JSON.stringify(queue)
    );

    return record;
}

// ---------------------------------------------
// Display Ticket
// ---------------------------------------------

function displayTicket(record) {

    const issuedTime =
        new Date(record.checked_in_at).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit"
        });

    const issuedDate =
        new Date(record.checked_in_at).toLocaleDateString("en-GB", {
            day: "2-digit",
            month: "short",
            year: "numeric"
        });

    tokenDisplay.textContent = record.token;
    maskedIdentifierDisplay.textContent = maskIdentifier(record.identifier);
    issueTimeDisplay.textContent = issuedTime;
    issueDateDisplay.textContent = issuedDate;

    form.style.display = "none";
    ticketCard.style.display = "flex";
}

// ---------------------------------------------
// Reset Kiosk
// ---------------------------------------------

function resetKiosk() {

    ticketCard.style.display = "none";

    form.style.display = "block";

    input.value = "";

    submitButton.disabled = false;

    input.focus();
}

// ---------------------------------------------
// Simulated Printer
// Replace with thermal printer later
// ---------------------------------------------

function printTicket(record) {

    console.group("HPQMS Ticket");

    console.log("Token:", record.token);

    console.log("Identifier:", record.identifier);

    console.log("Status:", record.status);

    console.log("Checked In:", record.checked_in_at);

    console.groupEnd();

    // Future
    // window.print();
}

// ---------------------------------------------
// Main Event
// ---------------------------------------------

form.addEventListener("submit", (event) => {

    event.preventDefault();

    const identifier = input.value.trim();

    if (!validateIdentifier(identifier)) {

        errorMsg.style.display = "block";

        input.focus();

        return;
    }

    errorMsg.style.display = "none";

    submitButton.disabled = true;

    try {

        const token = generateToken();

        const record = saveCheckIn(identifier, token);

        displayTicket(record);

        printTicket(record);

        setTimeout(resetKiosk, 5000);

    } catch (error) {

        console.error(error);

        alert("Unable to generate ticket. Please contact reception.");

        submitButton.disabled = false;
    }

});