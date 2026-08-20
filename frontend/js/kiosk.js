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

  var LABELS = {
    national_id: { title: "Enter your National ID", subtitle: "We use this to find your patient record.", label: "National ID number", placeholder: "Enter your National ID" },
    phone:       { title: "Enter your phone number", subtitle: "We use this to find your patient record.", label: "Phone number", placeholder: "Enter your phone number" },
    
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
  var autoResetNote    = document.getElementById("auto-reset-note");
  var doneBtn           = document.getElementById("done-btn");

  var notfoundRetryBtn = document.getElementById("notfound-retry-btn");
  var errorRetryBtn    = document.getElementById("error-retry-btn");

  /* -----------------------------------------------------------
     HELPERS
  ----------------------------------------------------------- */
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
      checkinBtn.innerHTML = '<span class="spinner"></span><span>Checking you in&hellip;</span>';
    } else {
      checkinBtn.innerHTML = '<span id="checkin-btn-label">CHECK IN</span>';
    }
  }

  function applyIdMethodLabels(method){
    var cfg = LABELS[method];
    idInputTitle.textContent = cfg.title;
    idInputSubtitle.textContent = cfg.subtitle;
    idInputLabel.textContent = cfg.label;
    idInput.placeholder = cfg.placeholder;
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
            department: response.department_name || "RECEPTION"
        });

    } catch (error) {
        setSubmitting(false);
        console.error("Kiosk transaction breakdown:", error);
        
        if (error.status === 404) {
            showScreen("notfound");
        } else {
            showScreen("error");
        }
    }
}

function renderSuccess(kioskData) {
    kioskData = kioskData || {};
    
    successGreeting.textContent = "Check-In Successful!"; 
    tokenValue.textContent = kioskData.queue_token || "—";
    deptValue.textContent = kioskData.department || "RECEPTION";
    
    showScreen("success");
    startSuccessCountdown();
}


  function startSuccessCountdown(){
    var remaining = Math.ceil(SUCCESS_AUTO_RESET_MS / 1000);
    autoResetNote.textContent = "This screen will reset automatically in " + remaining + "s.";

    if (successCountdownInterval) clearInterval(successCountdownInterval);
    successCountdownInterval = setInterval(function(){
      remaining -= 1;
      if (remaining <= 0){
        clearInterval(successCountdownInterval);
        return;
      }
      autoResetNote.textContent = "This screen will reset automatically in " + remaining + "s.";
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
     LANGUAGE TOGGLE (placeholder — wire to i18n strings as needed)
  ----------------------------------------------------------- */
  document.querySelector(".lang-toggle").addEventListener("click", function(e){
    var btn = e.target.closest("button[data-lang]");
    if (!btn) return;
    Array.prototype.forEach.call(document.querySelectorAll(".lang-toggle button"), function(b){
      b.classList.remove("active");
    });
    btn.classList.add("active");
    resetIdleTimer();
    // Hook point: swap text content here based on btn.dataset.lang
  });

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
  applyIdMethodLabels("national_id");
  showScreen("checkin");
  goToStep(1);

})();