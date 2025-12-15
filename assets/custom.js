// Auto-Scroll für Debug Console und Chat History
// Wird bei jedem UI-Update aufgerufen

console.log('🔧 custom.js loaded');

// Make all external links and HTML preview links open in new tab
function makeLinksOpenInNewTab() {
    // External links (http/https)
    const externalLinks = document.querySelectorAll('a[href^="http"]');
    externalLinks.forEach(link => {
        if (!link.hasAttribute('target')) {
            link.setAttribute('target', '_blank');
            link.setAttribute('rel', 'noopener noreferrer');
        }
    });

    // HTML Preview links (/html_preview/...)
    const previewLinks = document.querySelectorAll('a[href^="/html_preview/"]');
    previewLinks.forEach(link => {
        if (!link.hasAttribute('target')) {
            link.setAttribute('target', '_blank');
            link.setAttribute('rel', 'noopener noreferrer');
        }
    });
}

function isAutoScrollEnabled() {
    // Find the auto-scroll switch by looking for the switch near the "Auto-Scroll" text
    // The switch has data-state="checked" or "unchecked"
    const switches = document.querySelectorAll('[role="switch"]');
    for (let sw of switches) {
        // Check if this switch is the auto-scroll switch (near "Auto-Scroll" text)
        const parent = sw.closest('.rx-Flex');
        if (parent && parent.textContent.includes('Auto-Scroll')) {
            const isEnabled = sw.getAttribute('data-state') === 'checked';
            return isEnabled;
        }
    }
    return true; // Default to enabled if switch not found
}

function autoScrollElement(element) {
    if (element) {
        console.log('📜 Scrolling element:', element.id, 'scrollTop:', element.scrollTop, 'scrollHeight:', element.scrollHeight);
        element.scrollTop = element.scrollHeight;
    }
}

// Observer für Debug-Console und Chat-History Updates
// Renamed to avoid conflict with autoscroll_js inline script
let customObserverConfig = { childList: true, subtree: true };

const customCallback = function(mutationsList, observer) {
    const enabled = isAutoScrollEnabled();
    console.log('🔍 MutationObserver triggered, auto-scroll enabled:', enabled);

    // Make all links open in new tab (always, regardless of auto-scroll)
    makeLinksOpenInNewTab();

    // Only scroll if auto-scroll is enabled
    if (!enabled) {
        return;
    }

    // Auto-scroll Debug Console
    const debugBox = document.getElementById('debug-console-box');
    if (debugBox) {
        autoScrollElement(debugBox);
    }

    // Auto-scroll Chat History
    const chatBox = document.getElementById('chat-history-box');
    if (chatBox) {
        autoScrollElement(chatBox);
    }
};

function setupObservers() {
    console.log('🚀 Setting up observers...');

    const debugBox = document.getElementById('debug-console-box');
    if (debugBox) {
        console.log('✅ Found debug-console-box');
        const observer = new MutationObserver(customCallback);
        observer.observe(debugBox, customObserverConfig);
    } else {
        console.warn('❌ debug-console-box not found');
    }

    const chatBox = document.getElementById('chat-history-box');
    if (chatBox) {
        console.log('✅ Found chat-history-box');
        const observer = new MutationObserver(customCallback);
        observer.observe(chatBox, customObserverConfig);
    } else {
        console.warn('❌ chat-history-box not found');
    }
}

// ============================================================
// MEDIARECORDER IMPLEMENTATION FOR LIVE AUDIO RECORDING
// ============================================================

let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let audioStream = null;

// Audio feedback function - plays beep sounds
function playBeep(frequency = 800, duration = 100) {
    try {
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();

        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);

        oscillator.frequency.value = frequency;
        oscillator.type = 'sine';

        gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
        gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + duration / 1000);

        oscillator.start(audioContext.currentTime);
        oscillator.stop(audioContext.currentTime + duration / 1000);

        console.log(`🔊 Beep played: ${frequency}Hz, ${duration}ms`);
    } catch (error) {
        console.warn('⚠️ Could not play beep sound:', error);
    }
}

// Start recording
async function startAudioRecording() {
    try {
        console.log('🎤 Requesting microphone access...');
        const stream = await navigator.mediaDevices.getUserMedia({
            audio: {
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true
            }
        });

        audioStream = stream;
        mediaRecorder = new MediaRecorder(stream, {
            mimeType: 'audio/webm;codecs=opus'
        });
        audioChunks = [];

        mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
                console.log('📦 Audio chunk received:', event.data.size, 'bytes');
            }
        };

        mediaRecorder.onstop = async () => {
            console.log('⏹️ Recording stopped, processing audio...');
            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            console.log('🎵 Audio blob created:', audioBlob.size, 'bytes');

            // Upload audio blob to backend
            await uploadAudioBlob(audioBlob);

            // Stop all tracks to release microphone
            if (audioStream) {
                audioStream.getTracks().forEach(track => {
                    track.stop();
                    console.log('🛑 Stopped audio track');
                });
                audioStream = null;
            }
        };

        mediaRecorder.start();
        isRecording = true;
        updateRecordingButton(true);
        playBeep(1000, 150); // Higher pitch for START (1000Hz, 150ms)
        console.log('🔴 Recording started');

    } catch (error) {
        console.error('❌ MediaRecorder error:', error);
        alert('Mikrofon-Zugriff verweigert! Bitte erlauben Sie den Mikrofon-Zugriff in Ihren Browser-Einstellungen.');
        isRecording = false;
        updateRecordingButton(false);
    }
}

// Stop recording
function stopAudioRecording() {
    if (mediaRecorder && isRecording) {
        console.log('⏸️ Stopping recording...');
        playBeep(600, 200); // Lower pitch for STOP (600Hz, 200ms)
        mediaRecorder.stop();
        isRecording = false;
        updateRecordingButton(false);
    }
}

// Toggle recording
function toggleRecording() {
    console.log('🟢 toggleRecording() called, current state:', isRecording);
    if (isRecording) {
        stopAudioRecording();
    } else {
        startAudioRecording();
    }
}

// Make toggleRecording available globally for Reflex rx.call_script()
window.toggleRecording = toggleRecording;

// Upload blob to backend via hidden upload component
async function uploadAudioBlob(blob) {
    try {
        console.log('📤 Uploading audio blob to backend...');

        // Find the hidden upload input
        const uploadInput = document.querySelector('#audio-recording-upload input[type="file"]');

        if (!uploadInput) {
            console.error('❌ Upload input not found! Make sure #audio-recording-upload exists in the DOM.');
            return;
        }

        // Create File from Blob
        const file = new File([blob], 'recording.webm', { type: 'audio/webm' });

        // Use DataTransfer to set files property
        const dataTransfer = new DataTransfer();
        dataTransfer.items.add(file);
        uploadInput.files = dataTransfer.files;

        console.log('✅ File set on input:', uploadInput.files[0].name, uploadInput.files[0].size, 'bytes');

        // Trigger change event to notify Reflex
        const changeEvent = new Event('change', { bubbles: true });
        uploadInput.dispatchEvent(changeEvent);

        console.log('🚀 Change event dispatched to Reflex');

    } catch (error) {
        console.error('❌ Upload error:', error);
    }
}

// Update button UI state
function updateRecordingButton(recording) {
    const btn = document.querySelector('#recording-button');
    if (btn) {
        if (recording) {
            // Recording state - RED, show "Stop"
            btn.style.backgroundColor = '#dc2626'; // red-600
            btn.style.color = 'white';

            // Update button text (find the text element)
            const textElement = btn.querySelector('.rt-Text');
            if (textElement) {
                textElement.textContent = 'Stop';
            }

            console.log('🔴 Button updated to RECORDING state');
        } else {
            // Idle state - GREEN, show "Aufnahme"
            btn.style.backgroundColor = ''; // Reset to default (theme color)
            btn.style.color = '';

            // Update button text
            const textElement = btn.querySelector('.rt-Text');
            if (textElement) {
                textElement.textContent = 'Aufnahme';
            }

            console.log('🟢 Button updated to IDLE state');
        }
    } else {
        console.warn('⚠️ Recording button #recording-button not found');
    }
}

// ============================================================
// TTS AUTO-PLAY (Direct call from backend via rx.call_script)
// ============================================================

// Track currently playing audio to allow stopping
let currentTtsAudio = null;
let lastPlayedTtsUrl = '';

/**
 * Play TTS audio from URL - called directly from Python backend via rx.call_script()
 * This is much more reliable than DOM observers because:
 * 1. No race conditions with React DOM updates
 * 2. Backend knows exactly when file is ready
 * 3. Audio element is created fresh each time
 *
 * @param {string} audioUrl - URL path like '/tts_audio/audio_123.mp3'
 */
function playTtsFromUrl(audioUrl) {
    console.log('🔊 TTS: playTtsFromUrl called with', audioUrl);

    // Skip if same URL (avoid double-play)
    if (audioUrl === lastPlayedTtsUrl && currentTtsAudio && !currentTtsAudio.ended) {
        console.log('⚠️ TTS: Same audio already playing, skipping');
        return;
    }

    // Stop any currently playing audio
    if (currentTtsAudio) {
        console.log('⏹️ TTS: Stopping previous audio');
        currentTtsAudio.pause();
        currentTtsAudio.src = '';
        currentTtsAudio = null;
    }

    // Create new audio element (not attached to DOM - more reliable)
    const audio = new Audio();
    currentTtsAudio = audio;
    lastPlayedTtsUrl = audioUrl;

    // Set up event handlers
    audio.addEventListener('canplaythrough', () => {
        console.log('🔊 TTS: Audio ready, playing...');
        audio.play()
            .then(() => {
                console.log('✅ TTS: Playback started');
            })
            .catch(err => {
                console.warn('⚠️ TTS: Autoplay blocked:', err.message);
                // Update the visible player so user can click play manually
                updateVisiblePlayer(audioUrl);
            });
    });

    audio.addEventListener('ended', () => {
        console.log('✅ TTS: Playback finished');
        currentTtsAudio = null;
    });

    audio.addEventListener('error', (e) => {
        console.error('❌ TTS: Audio load error', e);
        console.error('❌ TTS: Error code:', audio.error?.code, 'message:', audio.error?.message);
        currentTtsAudio = null;
    });

    // Start loading
    audio.src = audioUrl;
    audio.load();
}

/**
 * Update the visible HTML5 audio player (fallback for manual playback)
 */
function updateVisiblePlayer(audioUrl) {
    const player = document.getElementById('tts-audio-player');
    if (player && player.src !== audioUrl) {
        player.src = audioUrl;
        player.load();
        console.log('🔊 TTS: Updated visible player for manual playback');
    }
}

/**
 * Stop TTS playback
 */
function stopTts() {
    if (currentTtsAudio) {
        currentTtsAudio.pause();
        currentTtsAudio.src = '';
        currentTtsAudio = null;
        console.log('⏹️ TTS: Stopped');
    }
}

// Legacy function for compatibility (DOM observer based)
function playTtsAudio() {
    const player = document.getElementById('tts-audio-player');
    if (player && player.src && player.src.includes('/tts_audio/')) {
        playTtsFromUrl(player.src);
    }
}

// Make available globally
window.playTtsFromUrl = playTtsFromUrl;
window.playTtsAudio = playTtsAudio;
window.stopTts = stopTts;

// ============================================================
// TTS AUDIO OBSERVER - Watch for NEW audio elements (React re-mounts)
// ============================================================

let lastObservedTtsSrc = '';
let ttsDocumentObserver = null;

/**
 * Setup a document-level observer that watches for newly added audio elements.
 * This is necessary because React re-mounts the audio element when the key changes,
 * destroying the old element and creating a new one.
 */
function setupTtsAudioObserver() {
    console.log('🔊 TTS Observer: Setting up document-level observer');

    // Disconnect existing observer if any
    if (ttsDocumentObserver) {
        ttsDocumentObserver.disconnect();
    }

    // Function to handle a found audio player
    const handleAudioPlayer = (player) => {
        if (!player || !player.src) return;

        const src = player.src;
        console.log('🔊 TTS Observer: Checking audio player, src =', src);

        // Only play if src contains tts_audio and is different from last played
        if (src.includes('/tts_audio/') && src !== lastObservedTtsSrc) {
            console.log('🔊 TTS Observer: NEW audio detected, will trigger playback after delay');
            lastObservedTtsSrc = src;
            // Longer delay (500ms) to ensure:
            // 1. Element is fully mounted in React
            // 2. File is completely written to disk by Edge TTS
            // 3. Server has time to serve the complete file
            setTimeout(() => {
                console.log('🔊 TTS Observer: Delay complete, triggering playback');
                playTtsFromUrl(src);
            }, 500);
        }
    };

    // Create document-level observer to watch for added nodes
    ttsDocumentObserver = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
            // Check added nodes for audio elements
            if (mutation.type === 'childList') {
                mutation.addedNodes.forEach(node => {
                    // Check if the added node IS an audio element
                    if (node.nodeName === 'AUDIO' && node.id === 'tts-audio-player') {
                        console.log('🔊 TTS Observer: Audio element ADDED to DOM');
                        handleAudioPlayer(node);
                    }
                    // Check if the added node CONTAINS an audio element
                    if (node.querySelector) {
                        const audio = node.querySelector('#tts-audio-player');
                        if (audio) {
                            console.log('🔊 TTS Observer: Audio element found in added subtree');
                            handleAudioPlayer(audio);
                        }
                    }
                });
            }
            // Also watch for attribute changes on audio elements
            if (mutation.type === 'attributes' && mutation.attributeName === 'src') {
                const target = mutation.target;
                if (target.nodeName === 'AUDIO' && target.id === 'tts-audio-player') {
                    console.log('🔊 TTS Observer: Audio src attribute changed');
                    handleAudioPlayer(target);
                }
            }
        }
    });

    // Observe the entire document for changes
    ttsDocumentObserver.observe(document.body, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ['src']
    });

    // Also check if audio element already exists
    const existingPlayer = document.getElementById('tts-audio-player');
    if (existingPlayer) {
        console.log('🔊 TTS Observer: Found existing audio player');
        handleAudioPlayer(existingPlayer);
    }

    console.log('🔊 TTS Observer: Document observer active');
}

// ============================================================
// INITIALIZATION
// ============================================================

function initializeAllObservers() {
    console.log('🚀 Initializing all observers...');

    // Make existing links open in new tab
    makeLinksOpenInNewTab();

    setupObservers();

    // Setup TTS audio observer
    setupTtsAudioObserver();

    // Retry after 500ms in case elements render later
    setTimeout(() => {
        setupObservers();
        makeLinksOpenInNewTab();
        setupTtsAudioObserver();
    }, 500);

    // Retry after 1000ms
    setTimeout(() => {
        setupObservers();
        makeLinksOpenInNewTab();
    }, 1000);
}

// Handle both cases: DOMContentLoaded not yet fired, or already fired
if (document.readyState === 'loading') {
    // DOM is still loading, wait for DOMContentLoaded
    document.addEventListener('DOMContentLoaded', function() {
        console.log('📄 DOMContentLoaded event fired');
        initializeAllObservers();
    });
} else {
    // DOM already loaded (script loaded after DOMContentLoaded)
    console.log('📄 DOM already ready, initializing immediately');
    initializeAllObservers();
}
