import { kioskCheckIn } from "./kiosk-api.js";



(function(){
  "use strict";

  /* -----------------------------------------------------------
     STATE
  ----------------------------------------------------------- */
  var state = {
    idMethod: "national_id",   // national_id | phone | temp_id
    idValue: "",
    visitType: null,           // WALK_IN | APPOINTMENT | REFERRAL | EMERGENCY
    submitting: false,
    step: 1                    // 1, 2, 3
  };

  var TOTAL_STEPS = 3;

  var IDLE_RESET_MS = 90 * 1000;      // reset form if idle this long on check-in screen
  var SUCCESS_AUTO_RESET_MS = 30 * 1000;

  var idleTimer = null;
  var successTimer = null;
  var successCountdownInterval = null;

  // Maps each identification method to the translation keys that describe it.
  // Replaces the old English-only LABELS object so the step 2 copy follows
  // both the selected method AND the active language.
  var ID_METHOD_KEYS = {
    national_id: { title: "nationalIdTitle", subtitle: "patientRecord", label: "nationalIdLabel", placeholder: "nationalIdPlaceholder" },
    phone:       { title: "phoneTitle",      subtitle: "patientRecord", label: "phoneLabel",      placeholder: "phonePlaceholder" }
  };

  /* -----------------------------------------------------------
     ELEMENTS
  ----------------------------------------------------------- */
  var screenCheckin  = document.getElementById("screen-checkin");
  var screenSuccess  = document.getElementById("screen-success");
  var screenNotFound = document.getElementById("screen-notfound");
  var screenError    = document.getElementById("screen-error");

  var progressFill   = document.getElementById("progress-fill");
  var progressSteps  = document.getElementById("progress-steps");

  var formSteps = [
    document.getElementById("form-step-1"),
    document.getElementById("form-step-2"),
    document.getElementById("form-step-3")
  ];

  var idMethodGroup  = document.getElementById("id-method-group");
  var idInput        = document.getElementById("id-input");
  var idInputTitle    = document.getElementById("id-input-title");
  var idInputSubtitle = document.getElementById("id-input-subtitle");
  var idInputLabel    = document.getElementById("id-input-label");
  var idInputError   = document.getElementById("id-input-error");

  var visitTypeGroup = document.getElementById("visit-type-group");
  var visitTypeError = document.getElementById("visit-type-error");

  var step1Next = document.getElementById("step1-next");
  var step2Back = document.getElementById("step2-back");
  var step2Next = document.getElementById("step2-next");
  var step3Back = document.getElementById("step3-back");

  var checkinBtn      = document.getElementById("checkin-btn");
  var checkinBtnLabel = document.getElementById("checkin-btn-label");

  var successGreeting = document.getElementById("success-greeting");
  var tokenValue       = document.getElementById("token-value");
  var deptValue        = document.getElementById("dept-value");
  var deptValueIsDefault = true; // tracks whether dept-value still shows the translated fallback, vs a real API value
  var autoResetNote    = document.getElementById("auto-reset-note");
  var doneBtn           = document.getElementById("done-btn");

  var notfoundRetryBtn = document.getElementById("notfound-retry-btn");
  var errorRetryBtn    = document.getElementById("error-retry-btn");



  const translations = {
  en: {
    welcome: "Welcome",
    welcomeTitle: "Welcome to<br>Horizon General Hospital",
    welcomeMessage: "Please use this kiosk to check in for your visit.",
    privacyNote: "Your privacy matters to us. Please make sure you have your identification information ready.",

    identify: "Identify",
    yourDetails: "Your details",
    visitType: "Visit type",

    identificationQuestion: "How would you like to identify yourself?",
    chooseOption: "Choose one option to continue.",

    nationalId: "National ID",
    phoneNumber: "Phone Number",

    next: "NEXT",
    back: "BACK",

    nationalIdTitle: "Enter your National ID",
    phoneTitle: "Enter your Phone Number",

    patientRecord: "We use this to find your patient record.",

    nationalIdLabel: "National ID number",
    phoneLabel: "Phone Number",

    nationalIdPlaceholder: "Enter your National ID",
    phonePlaceholder: "Enter your Phone Number",

    identificationError:
      "Please enter your identification number to continue.",

    visitQuestion: "What type of visit are you making?",
    visitSubtitle: "Select the option that best describes your visit.",

    walkIn: "Walk-in",
    appointment: "Appointment",
    referral: "Referral",
    emergency: "Emergency",

    visitTypeError:
      "Please select a visit type to continue.",

    checkIn: "CHECK IN",
    checkingIn: "Checking you in\u2026",

    checkInComplete: "Check-in complete",
    checkInSuccessTitle: "Check-In Successful!",
    welcomeShort: "Welcome",
    allSet: "You're all set. Please note your details below.",

    queueToken: "Your queue token is",
    proceedTo: "Please proceed to",
    reception: "RECEPTION",

    tokenHelper:
      "A staff member will call your token when it is your turn.",

    done: "DONE",

    autoReset:
      "This screen will reset automatically in 30s.",
    autoResetTemplate:
      "This screen will reset automatically in {s}s.",

    patientNotFound: "Patient not found",

    patientNotFoundMessage:
      "We couldn't find a patient record using the information provided. Please check your information and try again.",

    patientNotFoundHelper:
      "If this is your first visit, please continue and our reception team will help complete your registration.",

    tryAgain: "TRY AGAIN",

    somethingWentWrong: "Something went wrong",

    errorMessage:
      "We couldn't complete your check-in. Please try again.",

    secureInformation:
      "Your information is handled securely",

    needHelp:
      "Need help? Ask a staff member"
  },

  sw: {
    welcome: "Karibu",

    welcomeTitle:
      "Karibu katika<br>Hospitali Kuu ya Horizon",

    welcomeMessage:
      "Tafadhali tumia kifaa hiki kujisajili kwa ziara yako.",

    privacyNote:
      "Faragha yako ni muhimu kwetu. Tafadhali hakikisha una taarifa zako za utambulisho.",

    identify: "Utambulisho",
    yourDetails: "Taarifa zako",
    visitType: "Aina ya ziara",

    identificationQuestion:
      "Ungependa kujitambulisha kwa njia gani?",

    chooseOption:
      "Chagua chaguo moja ili kuendelea.",

    nationalId: "Kitambulisho cha Taifa",
    phoneNumber: "Nambari ya Simu",

    next: "ENDELEA",
    back: "RUDI",

    nationalIdTitle:
      "Weka nambari yako ya Kitambulisho cha Taifa",

    phoneTitle:
      "Weka Nambari yako ya Simu",

    patientRecord:
      "Tunatumia taarifa hii kupata rekodi yako ya mgonjwa.",

    nationalIdLabel:
      "Nambari ya Kitambulisho cha Taifa",

    phoneLabel:
      "Nambari ya Simu",

    nationalIdPlaceholder:
      "Weka nambari yako ya Kitambulisho cha Taifa",

    phonePlaceholder:
      "Weka Nambari yako ya Simu",

    identificationError:
      "Tafadhali weka nambari yako ya utambulisho ili kuendelea.",

    visitQuestion:
      "Unakuja kwa aina gani ya ziara?",

    visitSubtitle:
      "Chagua chaguo linaloelezea vizuri sababu ya ziara yako.",

    walkIn: "Bila miadi",
    appointment: "Miadi",
    referral: "Rufaa",
    emergency: "Dharura",

    visitTypeError:
      "Tafadhali chagua aina ya ziara ili kuendelea.",

    checkIn: "JISAJILI",
    checkingIn: "Inakusajili\u2026",

    checkInComplete:
      "Usajili umekamilika",
    checkInSuccessTitle: "Usajili Umefaulu!",

    welcomeShort: "Karibu",

    allSet:
      "Uko tayari. Tafadhali zingatia taarifa zako hapa chini.",

    queueToken:
      "Nambari yako ya foleni ni",

    proceedTo:
      "Tafadhali elekea",

    reception:
      "MAPOKEZI",

    tokenHelper:
      "Mfanyakazi ataita nambari yako ya foleni wakati wako ukifika.",

    done: "IMEKAMILIKA",

    autoReset:
      "Ukurasa huu utajirekebisha baada ya sekunde 30.",
    autoResetTemplate:
      "Ukurasa huu utajirekebisha baada ya sekunde {s}.",

    patientNotFound:
      "Mgonjwa hakupatikana",

    patientNotFoundMessage:
      "Hatukuweza kupata rekodi ya mgonjwa kwa kutumia taarifa ulizoweka. Tafadhali hakikisha taarifa zako ni sahihi na ujaribu tena.",

    patientNotFoundHelper:
      "Ikiwa hii ni ziara yako ya kwanza, tafadhali endelea na timu yetu ya mapokezi itakusaidia kukamilisha usajili wako.",

    tryAgain:
      "JARIBU TENA",

    somethingWentWrong:
      "Kuna tatizo limetokea",

    errorMessage:
      "Hatukuweza kukamilisha usajili wako. Tafadhali jaribu tena.",

    secureInformation:
      "Taarifa zako zinashughulikiwa kwa usalama",

    needHelp:
      "Unahitaji msaada? Muulize mfanyakazi"
  }
};

  let currentLanguage = "en";

  /* -----------------------------------------------------------
     HELPERS
  ----------------------------------------------------------- */
  function t(key){
    var strings = translations[currentLanguage] || translations.en;
    return strings[key] !== undefined ? strings[key] : translations.en[key];
  }

  function showScreen(name){
    screenCheckin.classList.toggle("hidden", name !== "checkin");
    screenSuccess.classList.toggle("hidden", name !== "success");
    screenNotFound.classList.toggle("hidden", name !== "notfound");
    screenError.classList.toggle("hidden", name !== "error");
  }

  function goToStep(stepNum){
    state.step = stepNum;

    formSteps.forEach(function(el, i){
      el.classList.toggle("active", (i + 1) === stepNum);
    });

    var pct = (stepNum / TOTAL_STEPS) * 100;
    progressFill.style.width = pct + "%";

    Array.prototype.forEach.call(progressSteps.querySelectorAll(".progress-step"), function(el){
      var n = parseInt(el.dataset.step, 10);
      el.classList.toggle("done", n < stepNum);
      el.classList.toggle("active", n === stepNum);
    });

    // Scroll form area back to top on each step change
    var scrollArea = document.querySelector(".form-scroll");
    if (scrollArea) scrollArea.scrollTop = 0;

    resetIdleTimer();
  }

  function resetIdleTimer(){
    if (idleTimer) clearTimeout(idleTimer);
    idleTimer = setTimeout(function(){
      resetForm();
    }, IDLE_RESET_MS);
  }

  function resetForm(){
    state.idMethod = "national_id";
    state.idValue = "";
    state.visitType = null;
    state.submitting = false;

    // reset identification segmented control
    Array.prototype.forEach.call(idMethodGroup.querySelectorAll(".seg-btn"), function(btn){
      btn.classList.toggle("selected", btn.dataset.method === "national_id");
    });
    applyIdMethodLabels("national_id");
    idInput.value = "";
    idInputError.classList.remove("show");

    // reset visit type
    Array.prototype.forEach.call(visitTypeGroup.querySelectorAll(".visit-card"), function(card){
      card.classList.remove("selected");
    });
    visitTypeError.classList.remove("show");

    setSubmitting(false);
    showScreen("checkin");
    goToStep(1);
  }

  function setSubmitting(isSubmitting){
    state.submitting = isSubmitting;
    checkinBtn.disabled = isSubmitting;
    if (isSubmitting){
      checkinBtn.innerHTML = '<span class="spinner"></span><span>' + t("checkingIn") + '</span>';
    } else {
      checkinBtn.innerHTML = '<span id="checkin-btn-label" data-i18n="checkIn">' + t("checkIn") + '</span>';
      checkinBtnLabel = document.getElementById("checkin-btn-label");
    }
  }

  function applyIdMethodLabels(method){
    var keys = ID_METHOD_KEYS[method] || ID_METHOD_KEYS.national_id;
    idInputTitle.textContent = t(keys.title);
    idInputSubtitle.textContent = t(keys.subtitle);
    idInputLabel.textContent = t(keys.label);
    idInput.placeholder = t(keys.placeholder);
  }

  /* -----------------------------------------------------------
     IDENTIFICATION METHOD (STEP 1)
  ----------------------------------------------------------- */
  idMethodGroup.addEventListener("click", function(e){
    var btn = e.target.closest(".seg-btn");
    if (!btn) return;
    resetIdleTimer();

    Array.prototype.forEach.call(idMethodGroup.querySelectorAll(".seg-btn"), function(b){
      b.classList.remove("selected");
    });
    btn.classList.add("selected");

    state.idMethod = btn.dataset.method;
    applyIdMethodLabels(state.idMethod);
    idInput.value = "";
    idInputError.classList.remove("show");
  });

  step1Next.addEventListener("click", function(){
    goToStep(2);
    setTimeout(function(){ idInput.focus(); }, 50);
  });

  /* -----------------------------------------------------------
     IDENTIFIER INPUT (STEP 2)
  ----------------------------------------------------------- */
  idInput.addEventListener("input", function(){
    resetIdleTimer();
    if (idInput.value.trim().length > 0){
      idInputError.classList.remove("show");
    }
  });

  step2Back.addEventListener("click", function(){
    goToStep(1);
  });

  step2Next.addEventListener("click", function(){
    var idVal = idInput.value.trim();
    if (idVal.length === 0){
      idInputError.classList.add("show");
      resetIdleTimer();
      return;
    }
    idInputError.classList.remove("show");
    state.idValue = idVal;
    goToStep(3);
  });

  idInput.addEventListener("keydown", function(e){
    if (e.key === "Enter"){
      step2Next.click();
    }
  });

  /* -----------------------------------------------------------
     VISIT TYPE (STEP 3)
  ----------------------------------------------------------- */
  visitTypeGroup.addEventListener("click", function(e){
    var card = e.target.closest(".visit-card");
    if (!card) return;
    resetIdleTimer();

    Array.prototype.forEach.call(visitTypeGroup.querySelectorAll(".visit-card"), function(c){
      c.classList.remove("selected");
    });
    card.classList.add("selected");
    state.visitType = card.dataset.visit;
    visitTypeError.classList.remove("show");
  });

  step3Back.addEventListener("click", function(){
    goToStep(2);
    setTimeout(function(){ idInput.focus(); }, 50);
  });

 /* ==========================================================================
   THE UNIFIED SUBMISSION HANDLER
   ========================================================================== */

checkinBtn.addEventListener("click", async function() {
    if (state.submitting) return;
    resetIdleTimer();

    if (!state.visitType) {
        visitTypeError.classList.add("show");
        return;
    }

    await handleFormSubmit();
});

async function handleFormSubmit() {
    setSubmitting(true);

    try {
        // Since state contains: idMethod, idValue, and visitType,
        // we can pass it directly into the network translation layer!
        const response = await kioskCheckIn(state);

        setSubmitting(false);

        // Success: Forward the exact flat Pydantic schema parameters to the UI
        renderSuccess({
            queue_token: response.token_number || "—",
            department: response.department_name || null
        });

    } catch (error) {
        setSubmitting(false);
        console.error("Kiosk transaction breakdown:", error);

        const errorDetail = String(error.body?.detail || error.message || "").toLowerCase();
        if (error.status === 404 && errorDetail.includes("patient")) {
            showScreen("notfound");
        } else {
            showScreen("error");
        }
    }
}

function renderSuccess(kioskData) {
    kioskData = kioskData || {};

    successGreeting.textContent = t("checkInSuccessTitle");
    tokenValue.textContent = kioskData.queue_token || "—";

    if (kioskData.department) {
        deptValue.textContent = kioskData.department;
        deptValue.removeAttribute("data-i18n");
        deptValueIsDefault = false;
    } else {
        deptValue.textContent = t("reception");
        deptValue.setAttribute("data-i18n", "reception");
        deptValueIsDefault = true;
    }

    showScreen("success");
    startSuccessCountdown();
}



  function startSuccessCountdown(){
    var remaining = Math.ceil(SUCCESS_AUTO_RESET_MS / 1000);
    autoResetNote.textContent = t("autoResetTemplate").replace("{s}", remaining);

    if (successCountdownInterval) clearInterval(successCountdownInterval);
    successCountdownInterval = setInterval(function(){
      remaining -= 1;
      if (remaining <= 0){
        clearInterval(successCountdownInterval);
        return;
      }
      autoResetNote.textContent = t("autoResetTemplate").replace("{s}", remaining);
    }, 1000);

    if (successTimer) clearTimeout(successTimer);
    successTimer = setTimeout(function(){
      resetForm();
    }, SUCCESS_AUTO_RESET_MS);
  }

  doneBtn.addEventListener("click", function(){
    if (successTimer) clearTimeout(successTimer);
    if (successCountdownInterval) clearInterval(successCountdownInterval);
    resetForm();
  });

  /* -----------------------------------------------------------
     RETRY BUTTONS
  ----------------------------------------------------------- */
  notfoundRetryBtn.addEventListener("click", function(){
    showScreen("checkin");
    goToStep(2);
    idInput.value = "";
    idInput.focus();
  });

  errorRetryBtn.addEventListener("click", function(){
    showScreen("checkin");
    goToStep(3);
  });

  /* -----------------------------------------------------------
     LANGUAGE TOGGLE
  ----------------------------------------------------------- */
  document.querySelector(".lang-toggle").addEventListener("click", function(e) {
    var btn = e.target.closest("button[data-lang]");
    if (!btn) return;

    var lang = btn.dataset.lang;

    Array.prototype.forEach.call(
      document.querySelectorAll(".lang-toggle button"),
      function(b) {
        b.classList.remove("active");
      }
    );

    btn.classList.add("active");

    setLanguage(lang);

    resetIdleTimer();
  });

  function setLanguage(lang) {
    if (!translations[lang]) return;
    currentLanguage = lang;

    var strings = translations[lang];

    document.querySelectorAll("[data-i18n]").forEach(function(element) {
      var key = element.dataset.i18n;
      if (strings[key] !== undefined) {
        element.innerHTML = strings[key];
      }
    });

    document.querySelectorAll("[data-i18n-placeholder]").forEach(function(element) {
      var key = element.dataset.i18nPlaceholder;
      if (strings[key] !== undefined) {
        element.placeholder = strings[key];
      }
    });

    document.documentElement.lang = lang;

    // Re-render strings that are set dynamically in JS rather than through
    // static [data-i18n] attributes, so a language switch mid-flow stays consistent.
    applyIdMethodLabels(state.idMethod);

    if (!state.submitting) {
      checkinBtn.innerHTML = '<span id="checkin-btn-label" data-i18n="checkIn">' + t("checkIn") + '</span>';
      checkinBtnLabel = document.getElementById("checkin-btn-label");
    } else {
      checkinBtn.innerHTML = '<span class="spinner"></span><span>' + t("checkingIn") + '</span>';
    }

    if (!screenSuccess.classList.contains("hidden")) {
      successGreeting.textContent = t("checkInSuccessTitle");
      if (deptValueIsDefault) {
        deptValue.textContent = t("reception");
      }
      if (successCountdownInterval || successTimer) {
        // leave the exact remaining count alone; just re-translate the template
        var currentText = autoResetNote.textContent;
        var match = currentText.match(/(\d+)/);
        var remaining = match ? match[1] : Math.ceil(SUCCESS_AUTO_RESET_MS / 1000);
        autoResetNote.textContent = t("autoResetTemplate").replace("{s}", remaining);
      }
    }
  }



  /* -----------------------------------------------------------
     GLOBAL IDLE ACTIVITY LISTENER
  ----------------------------------------------------------- */
  ["click", "touchstart", "keydown"].forEach(function(evt){
    document.addEventListener(evt, function(){
      if (!screenCheckin.classList.contains("hidden")){
        resetIdleTimer();
      }
    }, { passive: true });
  });

  /* -----------------------------------------------------------
     INIT
  ----------------------------------------------------------- */
  setLanguage("en");
  showScreen("checkin");
  goToStep(1);

})();