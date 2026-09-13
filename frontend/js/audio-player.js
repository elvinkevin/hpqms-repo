/**
 * ============================================================================
 * HPQMS Public Patient Display Board
 * js/audio-player.js — Audio Chime & Token Announcement Module
 * ============================================================================
 *
 * Responsibilities:
 *   - Generate and play a chime sound using the Web Audio API
 *   - Speak the token number aloud using SpeechSynthesis (TTS)
 *   - Handle browser autoplay-policy unlocking via user gesture
 *   - Expose a simple playTokenChime(alert) entry point
 *
 * The alert object passed from the alert-manager contains:
 *   token_number  — e.g. "P-014"
 *   priority      — "NORMAL" | "HIGH" | "CRITICAL"
 *   department_name — e.g. "Pharmacy"
 *   service_point — e.g. "Counter 2"
 *
 * No external audio files are required — the chime is synthesized
 * in real time with the Web Audio API oscillator nodes.
 * ============================================================================
 */


/* ==========================================================================
   Constants
   ========================================================================== */

const CHIME_NOTES = [
    { frequency: 659.25, durationMs: 180 },  // E5
    { frequency: 783.99, durationMs: 180 },  // G5
    { frequency: 880.00, durationMs: 180 },  // A5
    { frequency: 987.77, durationMs: 320 },  // B5 (held)
];

const CRITICAL_CHIME_NOTES = [
    { frequency: 880.00, durationMs: 120 },  // A5
    { frequency: 783.99, durationMs: 120 },  // G5
    { frequency: 880.00, durationMs: 300 },  // A5 (held)
];

const DEFAULT_OPTIONS = {
    enabled: true,
    speakTokenNumber: true,
    chimeVolume: 1.0,
    speechRate: 1.0,
    speechPitch: 1.0,
    speechVolume: 1.0,
    criticalChime: true,
};


/* ==========================================================================
   Internal State
   ========================================================================== */

let audioContext = null;

let gainNode = null;

let options = { ...DEFAULT_OPTIONS };

let initialized = false;

let unlocked = false;

let currentSpeech = null;


/* ==========================================================================
   Audio Context Management
   ========================================================================== */

/**
 * Lazily create the AudioContext.
 *
 * Browsers create AudioContexts in a "suspended" state until a user
 * gesture unlocks them. We create it on first use and attempt to resume
 * it, which succeeds after a user gesture.
 */
function ensureAudioContext() {
    if (audioContext) {
        return audioContext;
    }

    const AudioCtx =
        window.AudioContext ||
        window.webkitAudioContext;

    if (!AudioCtx) {
        return null;
    }

    audioContext = new AudioCtx();

    gainNode = audioContext.createGain();
    gainNode.connect(audioContext.destination);

    return audioContext;
}


/**
 * Resume the AudioContext after a user gesture.
 *
 * Call this from a click/tap/keydown handler on the document.
 */
function unlockAudio() {
    if (unlocked) {
        return Promise.resolve();
    }

    const ctx = ensureAudioContext();

    if (!ctx) {
        return Promise.resolve();
    }

    if (ctx.state === "suspended") {
        return ctx.resume().then(() => {
            unlocked = ctx.state === "running";
            return;
        });
    }

    unlocked = ctx.state === "running";

    return Promise.resolve();
}


/**
 * Return whether the AudioContext has been unlocked by a user gesture.
 */
function isUnlocked() {
    return unlocked;
}


/* ==========================================================================
   Chime Synthesis
   ========================================================================== */

/**
 * Play a chime sound using a sequence of ascending oscillator tones.
 *
 * @param {string} priority  — alert priority, affects chime style
 */
function playChime(priority) {
    const ctx = ensureAudioContext();

    if (!ctx || !gainNode) {
        return Promise.resolve();
    }

    const isCritical =
        priority === "CRITICAL" &&
        options.criticalChime;

    const notes =
        isCritical
            ? CRITICAL_CHIME_NOTES
            : CHIME_NOTES;

    const volume = Math.min(
        1,
        Math.max(0, options.chimeVolume)
    );

    const now = ctx.currentTime;
    let cursor = 0;

    return new Promise((resolve) => {
        let noteIndex = 0;

        function playNextNote() {
            if (noteIndex >= notes.length) {
                gainNode.gain.setValueAtTime(
                    0,
                    now + cursor
                );
                resolve();
                return;
            }

            const note = notes[noteIndex];
            const startTime = now + cursor;
            const endTime =
                startTime + note.durationMs / 1000;

            const oscillator =
                ctx.createOscillator();

            oscillator.type = "sine";

            oscillator.frequency.setValueAtTime(
                note.frequency,
                startTime
            );

            gainNode.gain.setValueAtTime(
                volume,
                startTime
            );

            /*
             * Exponential fade-out to avoid clicks.
             */
            gainNode.gain.exponentialRampToValueAtTime(
                0.001,
                endTime
            );

            oscillator.connect(gainNode);

            oscillator.start(startTime);

            oscillator.stop(endTime);

            cursor += note.durationMs / 1000;
            noteIndex += 1;

            setTimeout(
                playNextNote,
                note.durationMs
            );
        }

        playNextNote();
    });
}


/* ==========================================================================
   Speech Synthesis (Token Number Announcement)
   ========================================================================== */

/**
 * Convert a token number like "P-014" into a spoken-friendly string.
 *
 * The token prefix (letters) is spoken as individual characters
 * or words, and the numeric portion is spoken digit-by-digit for
 * clarity. When a service point is provided, the announcement
 * includes a "please proceed to" instruction.
 */
function formatTokenForSpeech(tokenNumber, servicePoint) {
    if (!tokenNumber) {
        return "Token";
    }

    const str = String(tokenNumber);

    const parts = str.split(/[-_\s]/);

    const spoken = parts.map((part) => {
        if (/^\d+$/.test(part)) {
            return part;
        }

        return part;
    });

    let result = `Token ${spoken.join(" ")}`;

    if (servicePoint) {
        result += ` please proceed to ${servicePoint}`;
    }

    return result;
}


/**
 * Speak the token number aloud using SpeechSynthesis.
 *
 * This is best-effort: if the API is unavailable or already
 * speaking, the existing speech is cancelled and replaced.
 *
 * When servicePoint is provided, the announcement includes
 * a "please proceed to" instruction for the counter/window.
 */
function speakToken(tokenNumber, servicePoint) {
    if (!("speechSynthesis" in window)) {
        return Promise.resolve();
    }

    return new Promise((resolve) => {
        if (currentSpeech) {
            try {
                speechSynthesis.cancel();
            } catch {
                /* ignore */
            }
        }

        const text = formatTokenForSpeech(tokenNumber, servicePoint);

        const utterance = new SpeechSynthesisUtterance(text);

        utterance.rate = options.speechRate;
        utterance.pitch = options.speechPitch;
        utterance.volume = options.speechVolume;

        utterance.onend = () => {
            currentSpeech = null;
            resolve();
        };

        utterance.onerror = () => {
            currentSpeech = null;
            resolve();
        };

        currentSpeech = utterance;

        try {
            speechSynthesis.speak(utterance);
        } catch (error) {
            currentSpeech = null;
            resolve();
        }
    });
}


/* ==========================================================================
   Public API
   ========================================================================== */

/**
 * Initialize the audio player with configuration options.
 */
function initialize(customOptions = {}) {
    options = {
        ...DEFAULT_OPTIONS,
        ...customOptions,
    };

    ensureAudioContext();

    /*
     * Register a one-time user-gesture unlock.
     *
     * The display page is full-screen with no explicit controls,
     * so we listen for any interaction to satisfy autoplay policies.
     */
    if (!unlocked) {
        const handleGesture = () => {
            unlockAudio();
            document.removeEventListener(
                "click",
                handleGesture
            );
            document.removeEventListener(
                "keydown",
                handleGesture
            );
            document.removeEventListener(
                "touchstart",
                handleGesture
            );
        };

        document.addEventListener(
            "click",
            handleGesture,
            { once: true }
        );
        document.addEventListener(
            "keydown",
            handleGesture,
            { once: true }
        );
        document.addEventListener(
            "touchstart",
            handleGesture,
            { once: true }
        );
    }

    initialized = true;

    return {
        initialized: true,
        unlocked,
        audioContextState: audioContext
            ? audioContext.state
            : "unavailable",
    };
}


/**
 * Play the token-called chime and announce the token number.
 *
 * @param {object} alert  — normalized alert object from alert-manager
 * @returns {Promise<void>}
 */
async function playTokenChime(alert) {
    if (!initialized || !options.enabled) {
        return;
    }

    /*
     * Attempt to resume the AudioContext on every call.
     * After the first user gesture this is a no-op but
     * harmless, and it satisfies browsers that suspend
     * the context after a period of inactivity.
     */
    if (audioContext && audioContext.state === "suspended") {
        try {
            await audioContext.resume();
        } catch {
            /* ignore — audio may simply not play */
        }
    }

    const priority =
        alert?.priority ?? "NORMAL";

    if (options.chimeVolume > 0) {
        try {
            await playChime(priority);
        } catch {
            /* ignore playback errors */
        }
    }

    if (
        options.speakTokenNumber &&
        alert?.token_number
    ) {
        try {
            await speakToken(
                alert.token_number,
                alert.service_point,
            );
        } catch {
            /* ignore speech errors */
        }
    }
}


/**
 * Enable or disable audio at runtime.
 */
function setEnabled(enabled) {
    options.enabled =
        typeof enabled === "boolean"
            ? enabled
            : Boolean(enabled);
}


/**
 * Update audio player configuration at runtime.
 */
function updateOptions(newOptions) {
    options = {
        ...options,
        ...newOptions,
    };
}


/**
 * Stop any in-progress speech and release resources.
 */
function reset() {
    if (currentSpeech) {
        try {
            speechSynthesis.cancel();
        } catch {
            /* ignore */
        }
        currentSpeech = null;
    }

    if (audioContext) {
        try {
            audioContext.close();
        } catch {
            /* ignore */
        }
        audioContext = null;
        gainNode = null;
    }

    unlocked = false;
    initialized = false;
}


export {
    initialize,
    playTokenChime,
    setEnabled,
    updateOptions,
    reset,
    unlockAudio,
    ensureAudioContext,
    isUnlocked,
};
