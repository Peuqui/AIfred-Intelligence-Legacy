// custom.js - Zusätzliche Frontend-Funktionen
// Auto-Scroll wird in aifred.py inline JS gehandhabt (mit ID-basiertem Switch-Check)

console.log('🔧 custom.js loaded');

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
        // Fixed width for both Aufnahme and Stop states
        btn.style.width = '160px';

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
 * Play TTS audio from URL - uses the VISIBLE HTML5 player for full user control
 *
 * The visible player (`#tts-audio-player`) is the single source of truth.
 * This allows the user to control playback with native HTML5 controls (pause, seek, volume).
 *
 * @param {string} audioUrl - URL path like '/tts_audio/audio_123.mp3'
 */
function playTtsFromUrl(audioUrl) {
    console.log('🔊 TTS: playTtsFromUrl called with', audioUrl);

    // Stop any old hidden audio (cleanup from previous implementation)
    if (currentTtsAudio) {
        console.log('⏹️ TTS: Stopping old hidden audio');
        currentTtsAudio.pause();
        currentTtsAudio.src = '';
        currentTtsAudio = null;
    }

    // Skip if same URL already playing on visible player
    const player = document.getElementById('tts-audio-player');
    if (player) {
        // Check if same audio already playing
        if (player.src === audioUrl || player.src.endsWith(audioUrl.split('/').pop())) {
            if (!player.paused && !player.ended) {
                console.log('⚠️ TTS: Same audio already playing on visible player, skipping');
                return;
            }
        }

        // Apply playback rate from data attribute (set by agent settings) or global default
        const dataRate = player.dataset.playbackRate;
        if (dataRate) {
            const rate = parseFloat(dataRate.replace('x', ''));
            if (!isNaN(rate) && rate > 0) {
                ttsPlaybackRate = rate;
            }
        }
        player.playbackRate = ttsPlaybackRate;
        console.log('🔊 TTS: Applied playback rate', ttsPlaybackRate);

        // Set source if different
        if (!player.src.endsWith(audioUrl.split('/').pop())) {
            player.src = audioUrl;
            player.load();
        }

        // Play the visible player
        player.play()
            .then(() => {
                console.log('✅ TTS: Playback started on visible player');
            })
            .catch(err => {
                console.warn('⚠️ TTS: Autoplay blocked:', err.message);
                console.log('ℹ️ TTS: User can click play on the visible player');
            });
    } else {
        console.warn('⚠️ TTS: Visible player not found, creating fallback audio');
        // Fallback: Create hidden audio only if visible player doesn't exist
        const audio = new Audio();
        currentTtsAudio = audio;
        audio.playbackRate = ttsPlaybackRate;
        audio.src = audioUrl;
        audio.play().catch(err => console.warn('⚠️ TTS fallback autoplay blocked:', err.message));
    }

    lastPlayedTtsUrl = audioUrl;
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
 * Stop TTS playback - stops both visible player and any hidden fallback audio
 */
function stopTts() {
    // Stop visible player
    const player = document.getElementById('tts-audio-player');
    if (player) {
        player.pause();
        player.currentTime = 0;
        console.log('⏹️ TTS: Stopped visible player');
    }

    // Stop hidden fallback audio (if any)
    if (currentTtsAudio) {
        currentTtsAudio.pause();
        currentTtsAudio.src = '';
        currentTtsAudio = null;
        console.log('⏹️ TTS: Stopped hidden fallback audio');
    }
}

// Legacy function for compatibility (DOM observer based)
function playTtsAudio() {
    const player = document.getElementById('tts-audio-player');
    if (player && player.src && player.src.includes('/tts_audio/')) {
        playTtsFromUrl(player.src);
    }
}

// ============================================================
// TTS PLAYBACK RATE (Persistent browser-side speed setting)
// ============================================================

// Store current playback rate (persisted via backend)
let ttsPlaybackRate = 1.0;  // Default (speed via Agent Settings)

/**
 * Set TTS playback rate - called from Python backend via rx.call_script()
 * Also applies to any currently playing audio
 * @param {number} rate - Playback rate (0.5, 0.75, 1, 1.25, 1.5, 2)
 */
function setTtsPlaybackRate(rate) {
    ttsPlaybackRate = parseFloat(rate);
    console.log('🔊 TTS: Playback rate set to', ttsPlaybackRate);

    // Apply to currently playing audio
    if (currentTtsAudio) {
        currentTtsAudio.playbackRate = ttsPlaybackRate;
        console.log('🔊 TTS: Applied rate to current audio');
    }

    // Apply to visible HTML5 player
    const player = document.getElementById('tts-audio-player');
    if (player) {
        player.playbackRate = ttsPlaybackRate;
        console.log('🔊 TTS: Applied rate to visible player');
    }
}

/**
 * Get current playback rate
 * @returns {number} Current playback rate
 */
function getTtsPlaybackRate() {
    return ttsPlaybackRate;
}

// Make available globally
window.playTtsFromUrl = playTtsFromUrl;
window.playTtsAudio = playTtsAudio;
window.stopTts = stopTts;
window.setTtsPlaybackRate = setTtsPlaybackRate;
window.getTtsPlaybackRate = getTtsPlaybackRate;

// ============================================================
// BUBBLE AUDIO PLAYBACK - Replay audio from chat bubbles
// ============================================================

/**
 * Play audio from a chat bubble button
 * Extracts audio_urls from the button's data attribute and plays the last one
 * @param {HTMLElement} button - The button element clicked
 */
function playBubbleAudioFromButton(button) {
    if (!button) {
        console.warn('playBubbleAudioFromButton: No button provided');
        return;
    }

    // audio_urls_json is a proper JSON array string
    const audioUrlsJson = button.dataset.audioUrls;
    if (!audioUrlsJson) {
        console.warn('playBubbleAudioFromButton: No audio URLs in data attribute');
        return;
    }

    try {
        const audioUrls = JSON.parse(audioUrlsJson);

        if (!Array.isArray(audioUrls) || audioUrls.length === 0) {
            console.log('🔊 Bubble Audio: Empty audio URLs array');
            return;
        }

        // Play the last audio URL (most complete chunk)
        const audioUrl = audioUrls[audioUrls.length - 1];
        console.log('🔊 Bubble Audio: Playing', audioUrl);
        playBubbleAudio(audioUrl);
    } catch (e) {
        console.warn('playBubbleAudioFromButton: Failed to parse JSON:', e, audioUrlsJson);
    }
}

// Bubble audio playback state
let bubbleAudioUrls = [];
let bubbleAudioIndex = 0;
let bubbleAudioPlaying = false;

/**
 * Play all audio URLs from a bubble sequentially
 * @param {string[]} audioUrls - Array of audio URLs to play
 */
function playBubbleAudioAll(audioUrls) {
    if (!audioUrls || !Array.isArray(audioUrls) || audioUrls.length === 0) {
        console.warn('playBubbleAudioAll: No audio URLs provided');
        return;
    }

    console.log(`🔊 Bubble Audio: Playing ${audioUrls.length} chunks sequentially`);

    // Stop any current playback
    const player = document.getElementById('tts-audio-player');
    if (player) {
        player.pause();
        player.onended = null;
    }

    // Stop TTS queue if playing
    if (ttsQueuePlaying) {
        console.log('🔊 Bubble Audio: Stopping TTS queue playback');
        ttsQueuePlaying = false;
    }

    // Setup bubble playback state
    bubbleAudioUrls = audioUrls;
    bubbleAudioIndex = 0;
    bubbleAudioPlaying = true;

    // Start playing
    playNextBubbleChunk();
}

/**
 * Play the next chunk in the bubble audio sequence
 */
function playNextBubbleChunk() {
    if (bubbleAudioIndex >= bubbleAudioUrls.length || !bubbleAudioPlaying) {
        bubbleAudioPlaying = false;
        console.log('🔊 Bubble Audio: Playback complete');
        return;
    }

    const audioUrl = bubbleAudioUrls[bubbleAudioIndex];
    console.log(`🔊 Bubble Audio: Playing chunk ${bubbleAudioIndex + 1}/${bubbleAudioUrls.length}`);

    const player = document.getElementById('tts-audio-player');
    if (player) {
        player.src = audioUrl;
        player.playbackRate = ttsPlaybackRate || 1.0;

        // Play next chunk when current finishes
        player.onended = () => {
            bubbleAudioIndex++;
            // Small pause between chunks for natural rhythm
            setTimeout(playNextBubbleChunk, 150);
        };

        player.play()
            .then(() => console.log(`✅ Bubble Audio: Chunk ${bubbleAudioIndex + 1} started`))
            .catch(err => {
                console.warn('⚠️ Bubble Audio: Autoplay blocked:', err.message);
                bubbleAudioPlaying = false;
            });
    } else {
        // Fallback: Create temporary audio element
        const audio = new Audio(audioUrl);
        audio.playbackRate = ttsPlaybackRate || 1.0;
        audio.onended = () => {
            bubbleAudioIndex++;
            setTimeout(playNextBubbleChunk, 150);
        };
        audio.play()
            .catch(err => {
                console.warn('⚠️ Bubble Audio: Autoplay blocked:', err.message);
                bubbleAudioPlaying = false;
            });
    }
}

/**
 * Stop bubble audio playback
 */
function stopBubbleAudio() {
    bubbleAudioPlaying = false;
    bubbleAudioUrls = [];
    bubbleAudioIndex = 0;
    const player = document.getElementById('tts-audio-player');
    if (player) {
        player.pause();
        player.onended = null;
    }
    console.log('🔊 Bubble Audio: Stopped');
}

/**
 * Play audio from a URL (single URL - legacy compatibility)
 * @param {string} audioUrl - The URL of the audio file to play
 */
function playBubbleAudio(audioUrl) {
    if (!audioUrl) {
        console.warn('playBubbleAudio: No audio URL provided');
        return;
    }
    // Delegate to playBubbleAudioAll with single-item array
    playBubbleAudioAll([audioUrl]);
}

/**
 * Initialize bubble audio buttons - hide those without audio URLs
 * Called after DOM updates to manage button visibility
 */
function initBubbleAudioButtons() {
    const buttons = document.querySelectorAll('.bubble-audio-btn');
    console.log(`🔊 initBubbleAudioButtons: Found ${buttons.length} buttons`);
    buttons.forEach((button, idx) => {
        const audioUrlsJson = button.dataset.audioUrls;
        console.log(`🔊 Button[${idx}] data-audio-urls:`, audioUrlsJson);
        if (!audioUrlsJson) {
            console.log(`🔊 Button[${idx}] → HIDE (no data attribute)`);
            button.style.display = 'none';
            return;
        }
        try {
            const audioUrls = JSON.parse(audioUrlsJson);
            if (!Array.isArray(audioUrls) || audioUrls.length === 0) {
                console.log(`🔊 Button[${idx}] → HIDE (empty array)`);
                button.style.display = 'none';
            } else {
                console.log(`🔊 Button[${idx}] → SHOW (${audioUrls.length} URLs)`);
                button.style.display = 'inline-flex';
                // Attach click handler via JS (Reflex doesn't support native onclick strings)
                if (!button.dataset.clickAttached) {
                    button.addEventListener('click', () => {
                        console.log(`🔊 Button clicked, playing all ${audioUrls.length} URLs`);
                        playBubbleAudioAll(audioUrls);
                    });
                    button.dataset.clickAttached = 'true';
                }
            }
        } catch (e) {
            console.log(`🔊 Button[${idx}] → HIDE (parse error)`, e);
            button.style.display = 'none';
        }
    });
}

/**
 * Play bubble audio from click event (called from Reflex with event object)
 * @param {Event} event - The click event
 */
function playBubbleAudioFromEvent(event) {
    if (!event || !event.currentTarget) {
        console.warn('playBubbleAudioFromEvent: No event or currentTarget');
        return;
    }

    const button = event.currentTarget;
    const audioUrlsJson = button.dataset.audioUrls;

    if (!audioUrlsJson) {
        console.warn('playBubbleAudioFromEvent: No audio URLs in data attribute');
        return;
    }

    try {
        const audioUrls = JSON.parse(audioUrlsJson);

        if (!Array.isArray(audioUrls) || audioUrls.length === 0) {
            console.log('🔊 Bubble Audio: Empty audio URLs array');
            return;
        }

        // Play all audio URLs sequentially
        console.log(`🔊 Bubble Audio Event: Playing all ${audioUrls.length} URLs`);
        playBubbleAudioAll(audioUrls);
    } catch (e) {
        console.warn('playBubbleAudioFromEvent: Failed to parse JSON:', e, audioUrlsJson);
    }
}

window.playBubbleAudioFromButton = playBubbleAudioFromButton;
window.playBubbleAudio = playBubbleAudio;
window.playBubbleAudioAll = playBubbleAudioAll;
window.stopBubbleAudio = stopBubbleAudio;
window.playBubbleAudioFromEvent = playBubbleAudioFromEvent;
window.initBubbleAudioButtons = initBubbleAudioButtons;

// ============================================================
// TTS AUDIO QUEUE - Sequential playback of multiple audio files
// ============================================================

// Queue state
let ttsQueue = [];  // Array of audio URLs to play
let ttsQueuePlaying = false;  // Is queue currently playing?
let ttsQueueCurrentIndex = 0;  // Current position in queue
let ttsQueueVersion = 0;  // Track version to detect updates from backend

/**
 * Update the TTS queue from backend state
 * Called when tts_audio_queue or tts_queue_version changes in Python
 * @param {string[]} queue - Array of audio URLs
 * @param {number} version - Queue version number
 */
function updateTtsQueue(queue, version) {
    // Check if this is a new version
    if (version <= ttsQueueVersion && queue.length === ttsQueue.length) {
        return;
    }

    console.log(`🔊 TTS Queue: Update received - version ${ttsQueueVersion} → ${version}, items ${ttsQueue.length} → ${queue.length}`);

    // Detect queue reset - this happens when:
    // 1. Queue becomes shorter or empty (user clears chat)
    // 2. Version goes DOWN (new inference started, server reset version to 1)
    const versionReset = version < ttsQueueVersion && ttsQueueVersion > 0;
    const queueShrunk = queue.length < ttsQueue.length || queue.length === 0;

    if (queueShrunk || versionReset) {
        console.log(`🔊 TTS Queue: Queue was reset (versionReset=${versionReset}, queueShrunk=${queueShrunk}), resetting index and state`);
        ttsQueueCurrentIndex = 0;
        ttsQueuePlaying = false;
        ttsQueue = [];  // Clear local queue so new items are treated as fresh
        // Stop current playback if any
        const player = document.getElementById('tts-audio-player');
        if (player) {
            player.pause();
            player.onended = null;
        }
    }

    ttsQueueVersion = version;

    // Find new items (items not yet in our local queue)
    // Only calculate new items if queue grew (not if it was reset)
    const newItems = queue.length > ttsQueue.length ? queue.slice(ttsQueue.length) : queue;
    ttsQueue = [...queue];  // Sync local queue with backend

    // If we have new items and not currently playing, start playback
    // But ONLY if AutoPlay is enabled (check data-autoplay attribute)
    const queueElement = document.getElementById('tts-queue-data');
    const autoplayEnabled = queueElement?.dataset?.autoplay === 'true';

    if (newItems.length > 0 && !ttsQueuePlaying && autoplayEnabled) {
        console.log(`🔊 TTS Queue: Starting playback of ${newItems.length} new items (with 50ms delay for DOM sync)`);
        setTimeout(() => {
            playNextInQueue();
        }, 50);
    } else if (newItems.length > 0 && !autoplayEnabled) {
        console.log('🔊 TTS Queue: New items received but AutoPlay is OFF - not playing');
    }
}

/**
 * Play the next item in the queue
 */
function playNextInQueue() {
    if (ttsQueueCurrentIndex >= ttsQueue.length) {
        ttsQueuePlaying = false;
        console.log('🔊 TTS Queue: Playback complete (no more items)');
        return;
    }

    ttsQueuePlaying = true;
    const audioUrl = ttsQueue[ttsQueueCurrentIndex];
    console.log(`🔊 TTS Queue: Playing item ${ttsQueueCurrentIndex + 1}/${ttsQueue.length}: ${audioUrl}`);

    const player = document.getElementById('tts-audio-player');
    if (player) {
        // Read playback rate from data attribute (set by Python backend)
        const dataRate = player.dataset.playbackRate;
        if (dataRate) {
            const rate = parseFloat(dataRate.replace('x', ''));
            if (!isNaN(rate) && rate > 0) {
                ttsPlaybackRate = rate;
                console.log(`🔊 TTS Queue: Using playback rate ${rate}x from data attribute`);
            }
        }

        // Set source first
        player.src = audioUrl;

        // Set playback rate AFTER setting src but BEFORE load
        // Also set it again on canplay event (browsers sometimes reset it)
        player.playbackRate = ttsPlaybackRate;

        // Handler to ensure playbackRate is applied after audio is ready
        const applyPlaybackRate = () => {
            if (player.playbackRate !== ttsPlaybackRate) {
                console.log(`🔊 TTS Queue: Re-applying playback rate ${ttsPlaybackRate}x on canplay`);
                player.playbackRate = ttsPlaybackRate;
            }
        };
        player.oncanplay = applyPlaybackRate;
        player.onloadeddata = applyPlaybackRate;

        player.load();

        // Apply rate again after load (belt and suspenders)
        player.playbackRate = ttsPlaybackRate;

        // Remove old ended handler and add new one
        // Add a small pause between sentences for natural speech rhythm
        player.onended = () => {
            console.log('🔊 TTS Queue: Item finished, adding sentence pause before next');
            ttsQueueCurrentIndex++;
            // 300ms pause between sentences for natural rhythm
            setTimeout(() => {
                playNextInQueue();
            }, 300);
        };

        player.play()
            .then(() => {
                // Apply rate one more time after play starts
                player.playbackRate = ttsPlaybackRate;
                console.log(`✅ TTS Queue: Playback started at ${player.playbackRate}x`);
            })
            .catch(err => {
                console.warn('⚠️ TTS Queue: Autoplay blocked:', err.message);
                // Still move to next after a delay if autoplay blocked
                setTimeout(() => {
                    ttsQueueCurrentIndex++;
                    playNextInQueue();
                }, 1000);
            });
    } else {
        console.warn('⚠️ TTS Queue: Player not found');
        ttsQueuePlaying = false;
    }
}

/**
 * Clear the TTS queue and stop playback
 */
function clearTtsQueue() {
    console.log('🔊 TTS Queue: Clearing');
    ttsQueue = [];
    ttsQueueCurrentIndex = 0;
    ttsQueuePlaying = false;

    // Stop current playback
    const player = document.getElementById('tts-audio-player');
    if (player) {
        player.pause();
        player.onended = null;
    }
}

/**
 * Skip to next item in queue
 */
function skipTtsQueueItem() {
    console.log('🔊 TTS Queue: Skipping current item');
    const player = document.getElementById('tts-audio-player');
    if (player) {
        player.pause();
    }
    ttsQueueCurrentIndex++;
    playNextInQueue();
}

// Make queue functions available globally
window.updateTtsQueue = updateTtsQueue;
window.clearTtsQueue = clearTtsQueue;
window.skipTtsQueueItem = skipTtsQueueItem;

// ============================================================
// TTS SSE STREAM - Server-Sent Events for immediate audio playback
// ============================================================

let ttsStreamActive = false;
let ttsEventSource = null;
let ttsStreamSessionId = null;

/**
 * Get session ID from cookie
 */
function getSessionIdFromCookie() {
    const name = 'aifred_session_id=';
    const decodedCookie = decodeURIComponent(document.cookie);
    const cookies = decodedCookie.split(';');
    for (let cookie of cookies) {
        cookie = cookie.trim();
        if (cookie.indexOf(name) === 0) {
            return cookie.substring(name.length);
        }
    }
    return null;
}

/**
 * Start SSE stream for TTS audio
 * Called when user starts a message (is_generating becomes true)
 * Server pushes audio URLs immediately as they're generated
 * @param {string} sessionIdParam - Optional session ID (if not provided, read from cookie)
 */
function startTtsStream(sessionIdParam) {
    const sessionId = sessionIdParam || getSessionIdFromCookie();
    if (!sessionId) {
        console.warn('🔊 TTS SSE: No session ID found');
        return;
    }

    // Check if already connected AND connection is still open
    if (ttsStreamActive && ttsStreamSessionId === sessionId && ttsEventSource) {
        // EventSource.OPEN = 1, CONNECTING = 0, CLOSED = 2
        if (ttsEventSource.readyState === EventSource.OPEN || ttsEventSource.readyState === EventSource.CONNECTING) {
            console.log('🔊 TTS SSE: Already connected for this session');
            return;
        } else {
            // Connection was closed, need to reconnect
            console.log('🔊 TTS SSE: Previous connection closed, reconnecting...');
        }
    }

    // Close existing connection if any
    if (ttsEventSource) {
        ttsEventSource.close();
        ttsEventSource = null;
    }

    ttsStreamSessionId = sessionId;
    ttsStreamActive = true;
    console.log(`🔊 TTS SSE: Connecting for session ${sessionId.substring(0, 8)}...`);

    // Build SSE URL - use backend port (8002) instead of frontend port
    // The backend API is mounted at /api, so full path is :8002/api/tts/stream/...
    const backendPort = 8002;
    const sseUrl = `${window.location.protocol}//${window.location.hostname}:${backendPort}/api/tts/stream/${sessionId}`;
    console.log(`🔊 TTS SSE: URL = ${sseUrl}`);

    // Create EventSource connection to SSE endpoint
    ttsEventSource = new EventSource(sseUrl);

    ttsEventSource.onopen = () => {
        console.log('🔊 TTS SSE: Connection opened');
    };

    ttsEventSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            console.log(`🔊 TTS SSE: Received audio URL, version ${data.version}`);

            // Add to queue and play immediately
            if (data.audio_url) {
                // Check for version reset BEFORE building queue
                // Version reset means new inference started - clear old queue first
                const versionReset = data.version < ttsQueueVersion && ttsQueueVersion > 0;
                if (versionReset) {
                    console.log(`🔊 TTS SSE: Version reset detected (${ttsQueueVersion} → ${data.version}), clearing local queue`);
                    ttsQueue = [];
                    ttsQueueVersion = 0;
                    ttsQueueCurrentIndex = 0;
                    ttsQueuePlaying = false;
                }

                // Build queue incrementally (now with potentially cleared queue)
                const newQueue = [...ttsQueue, data.audio_url];
                updateTtsQueue(newQueue, data.version);

                // Update playback rate from SSE data
                if (data.playback_rate) {
                    const rate = parseFloat(data.playback_rate.replace('x', ''));
                    if (!isNaN(rate) && rate > 0) {
                        ttsPlaybackRate = rate;
                    }
                }
            }
        } catch (e) {
            console.warn('🔊 TTS SSE: Failed to parse event data:', e);
        }
    };

    ttsEventSource.onerror = (event) => {
        if (ttsEventSource.readyState === EventSource.CLOSED) {
            console.log('🔊 TTS SSE: Connection closed by server');
            // Reset state and attempt reconnect after delay
            ttsStreamActive = false;
            ttsEventSource = null;
            console.log('🔊 TTS SSE: Will attempt reconnect in 2 seconds...');
            setTimeout(() => {
                if (!ttsStreamActive && ttsStreamSessionId) {
                    console.log('🔊 TTS SSE: Attempting reconnect...');
                    startTtsStream(ttsStreamSessionId);
                }
            }, 2000);
        } else {
            console.warn('🔊 TTS SSE: Connection error, EventSource will auto-retry...');
        }
    };
}

/**
 * Stop TTS SSE stream
 * Called when generation completes (is_generating becomes false)
 */
function stopTtsStream() {
    if (ttsEventSource) {
        ttsEventSource.close();
        ttsEventSource = null;
    }
    ttsStreamActive = false;
    console.log('🔊 TTS SSE: Stopped');
}

// Legacy aliases for compatibility with existing MutationObserver code
function startTtsPolling() { startTtsStream(); }
function stopTtsPolling() { stopTtsStream(); }

// Make SSE functions available globally
window.startTtsStream = startTtsStream;
window.stopTtsStream = stopTtsStream;
window.startTtsPolling = startTtsPolling;  // Legacy alias
window.stopTtsPolling = stopTtsPolling;    // Legacy alias

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
    // When a NEW audio element is detected (React re-mounts with new key), we:
    // 1. Apply the playback rate from data attribute (agent-specific speed)
    // 2. Trigger play() on the VISIBLE player after a short delay
    // The HTML5 player has autoPlay=True, but browsers may block it. This is a backup.
    // NOTE: If queue is playing, the queue controls playback - observer should not interfere
    const handleAudioPlayer = (player) => {
        if (!player || !player.src) return;

        const src = player.src;
        console.log('🔊 TTS Observer: Detected audio player, src =', src);

        // Only process TTS audio URLs
        if (!src.includes('/tts_audio/')) return;

        // If queue is actively playing, don't interfere - queue controls playback
        if (ttsQueuePlaying) {
            console.log('🔊 TTS Observer: Queue is playing, skipping observer play trigger');
            return;
        }

        // Read playback rate from data attribute (set by backend per agent)
        const dataRate = player.dataset.playbackRate;
        if (dataRate) {
            const rate = parseFloat(dataRate.replace('x', ''));
            if (!isNaN(rate) && rate > 0) {
                ttsPlaybackRate = rate;
                console.log('🔊 TTS Observer: Agent speed from data-playback-rate =', rate);
            }
        }

        // Apply playback rate immediately
        player.playbackRate = ttsPlaybackRate;
        console.log('🔊 TTS Observer: Applied playback rate', ttsPlaybackRate);

        // Check if this is a NEW audio (different from last observed)
        if (src === lastObservedTtsSrc) {
            console.log('🔊 TTS Observer: Same audio URL, skipping play trigger');
            return;
        }

        // NEW audio detected - this is a fresh player (React re-mounted it)
        lastObservedTtsSrc = src;
        console.log('🔊 TTS Observer: NEW audio detected');

        // Small delay to ensure audio is fully loaded, then ensure it plays
        // The autoPlay attribute should work, but this is a backup in case browser blocks it
        setTimeout(() => {
            // Double-check queue isn't playing (might have started during delay)
            if (ttsQueuePlaying) {
                console.log('🔊 TTS Observer: Queue started playing during delay, skipping');
                return;
            }
            if (player.paused && player.readyState >= 2) {
                console.log('🔊 TTS Observer: AutoPlay may have been blocked, triggering play()');
                player.play()
                    .then(() => console.log('✅ TTS Observer: Playback started via backup'))
                    .catch(err => console.warn('⚠️ TTS Observer: Play blocked:', err.message));
            } else if (!player.paused) {
                console.log('🔊 TTS Observer: Already playing (autoPlay worked)');
            }
        }, 200);
    };

    // Function to handle TTS queue data updates
    const handleQueueDataUpdate = (element) => {
        if (!element) return;

        const queueJson = element.dataset.queue;
        const version = parseInt(element.dataset.version || '0', 10);

        if (!queueJson) return;

        try {
            const queue = JSON.parse(queueJson);
            if (Array.isArray(queue)) {
                updateTtsQueue(queue, version);
            }
        } catch (e) {
            console.warn('⚠️ TTS Queue: Failed to parse queue JSON', e);
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
                        // Check for queue data element
                        const queueData = node.querySelector('#tts-queue-data');
                        if (queueData) {
                            handleQueueDataUpdate(queueData);
                        }
                    }
                    // Check if the added node IS the queue data element
                    if (node.id === 'tts-queue-data') {
                        handleQueueDataUpdate(node);
                    }
                });
            }
            // Watch for attribute changes
            if (mutation.type === 'attributes') {
                const target = mutation.target;
                // Audio src changes
                if (mutation.attributeName === 'src' && target.nodeName === 'AUDIO' && target.id === 'tts-audio-player') {
                    console.log('🔊 TTS Observer: Audio src attribute changed');
                    handleAudioPlayer(target);
                }
                // Playback rate changes (from dropdown) - apply IMMEDIATELY to playing audio
                if (mutation.attributeName === 'data-playback-rate' && target.nodeName === 'AUDIO' && target.id === 'tts-audio-player') {
                    const newRate = target.dataset.playbackRate;
                    if (newRate) {
                        const rate = parseFloat(newRate.replace('x', ''));
                        if (!isNaN(rate) && rate > 0) {
                            ttsPlaybackRate = rate;
                            target.playbackRate = rate;
                            console.log(`🔊 TTS Observer: Playback rate changed to ${rate}x (applied immediately)`);
                        }
                    }
                }
                // Queue data changes (data-queue or data-version)
                if ((mutation.attributeName === 'data-queue' || mutation.attributeName === 'data-version') && target.id === 'tts-queue-data') {
                    console.log('🔊 TTS Observer: Queue data attribute changed');
                    handleQueueDataUpdate(target);
                }
                // NOTE: SSE stream is started once on login via rx.call_script("startTtsStream('...')")
                // and stays open for the entire session. We no longer stop it based on data-polling.
                // The stream handles idle periods automatically (SSE keeps connection open).
                //
                // Old behavior (removed): stopTtsStream() when data-polling becomes false
                // This caused the stream to close after each inference, requiring restart.
            }
        }
    });

    // Observe the entire document for changes
    ttsDocumentObserver.observe(document.body, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ['src', 'data-queue', 'data-version', 'data-playback-rate', 'data-polling']
    });

    // Also check if audio element already exists
    const existingPlayer = document.getElementById('tts-audio-player');
    if (existingPlayer) {
        console.log('🔊 TTS Observer: Found existing audio player');
        handleAudioPlayer(existingPlayer);
    }

    // Check if queue data element already exists
    const existingQueueData = document.getElementById('tts-queue-data');
    if (existingQueueData) {
        console.log('🔊 TTS Observer: Found existing queue data element');
        handleQueueDataUpdate(existingQueueData);

        // Also check if SSE should be started (data-polling might already be true)
        const shouldStream = existingQueueData.dataset.polling === 'true';
        console.log(`🔊 TTS Observer: Initial polling state = ${shouldStream}`);
        if (shouldStream && !ttsStreamActive) {
            console.log('🔊 TTS Observer: Starting SSE stream on init');
            startTtsStream();
        }
    }

    console.log('🔊 TTS Observer: Document observer active');
}

// ============================================================
// INITIALIZATION
// ============================================================

function initializeAllObservers() {
    console.log('🚀 Initializing TTS observer...');

    // Setup TTS audio observer
    setupTtsAudioObserver();

    // Initialize bubble audio buttons (hide those without audio)
    initBubbleAudioButtons();

    // NOTE: TTS SSE stream is started by Reflex via rx.call_script("startTtsStream('...')")
    // when session is loaded (_load_session_by_id) or created (new_session).
    // No cookie polling needed.

    // Retry after 500ms in case elements render later
    setTimeout(() => {
        setupTtsAudioObserver();
        initBubbleAudioButtons();
    }, 500);

    // Setup a MutationObserver to initialize new bubble audio buttons as they're added
    const chatObserver = new MutationObserver((mutations) => {
        let hasNewButtons = false;
        for (const mutation of mutations) {
            if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
                for (const node of mutation.addedNodes) {
                    if (node.querySelector && node.querySelector('.bubble-audio-btn')) {
                        hasNewButtons = true;
                        break;
                    }
                    if (node.classList && node.classList.contains('bubble-audio-btn')) {
                        hasNewButtons = true;
                        break;
                    }
                }
            }
            if (hasNewButtons) break;
        }
        if (hasNewButtons) {
            // Debounce initialization
            setTimeout(initBubbleAudioButtons, 50);
        }
    });

    // Observe the document body for new chat bubbles
    chatObserver.observe(document.body, {
        childList: true,
        subtree: true
    });
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

// ============================================================
// KaTeX LaTeX Rendering
// ============================================================
// Renders LaTeX formulas in chat messages using KaTeX
// Supports: $...$ (inline), $$...$$ (block), and \ce{} (chemistry via mhchem)

let katexLoaded = false;
let mhchemLoaded = false;

function loadKatexScript() {
    if (katexLoaded || window.katex) {
        katexLoaded = true;
        // Also load mhchem if KaTeX already loaded
        return loadMhchemExtension();
    }

    return new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = '/katex/katex.min.js';
        script.onload = () => {
            console.log('📐 KaTeX script loaded');
            katexLoaded = true;
            // Load mhchem extension after KaTeX
            loadMhchemExtension().then(resolve).catch(resolve); // Don't fail if mhchem fails
        };
        script.onerror = () => {
            console.error('❌ Failed to load KaTeX');
            reject(new Error('KaTeX load failed'));
        };
        document.head.appendChild(script);
    });
}

function loadMhchemExtension() {
    if (mhchemLoaded) {
        return Promise.resolve();
    }

    return new Promise((resolve) => {
        const script = document.createElement('script');
        script.src = '/katex/mhchem.min.js';
        script.onload = () => {
            console.log('🧪 KaTeX mhchem extension loaded (chemistry support)');
            mhchemLoaded = true;
            resolve();
        };
        script.onerror = () => {
            console.warn('⚠️ mhchem extension not loaded (chemistry formulas disabled)');
            resolve(); // Don't fail, just continue without chemistry
        };
        document.head.appendChild(script);
    });
}

function renderLatexInElement(element) {
    if (!window.katex) return;

    const walker = document.createTreeWalker(
        element,
        NodeFilter.SHOW_TEXT,
        null,
        false
    );

    const textNodes = [];
    let node;
    while (node = walker.nextNode()) {
        // Skip if already processed or inside code/pre blocks
        if (node.parentElement.closest('code, pre, .katex')) continue;
        // Check for $ delimiter (server converts \[...\] and \(...\) to $...$)
        if (node.textContent.includes('$')) {
            textNodes.push(node);
        }
    }

    textNodes.forEach(textNode => {
        const text = textNode.textContent;
        let combined = text;
        let hasMatch = false;

        // 1. Block math: $$...$$ (server converts \[...\] to this format)
        combined = combined.replace(/\$\$([^$]+)\$\$/g, (match, formula) => {
            hasMatch = true;
            try {
                return '<span class="katex-block">' +
                    window.katex.renderToString(formula.trim(), {
                        displayMode: true,
                        throwOnError: false
                    }) + '</span>';
            } catch (e) {
                console.warn('KaTeX block $$ error:', e);
                return match;
            }
        });

        // 2. Inline math: $...$ (server converts \(...\) to this format)
        // Note: \[...\], \(...\), and \text{} are handled server-side in formatting.py
        combined = combined.replace(/(?<!\$)\$([^$\n]+)\$(?!\$)/g, (match, formula) => {
            hasMatch = true;
            try {
                return window.katex.renderToString(formula.trim(), {
                    displayMode: false,
                    throwOnError: false
                });
            } catch (e) {
                console.warn('KaTeX inline $ error:', e);
                return match;
            }
        });

        if (hasMatch) {
            const span = document.createElement('span');
            span.innerHTML = combined;
            textNode.parentNode.replaceChild(span, textNode);
        }
    });
}

function renderLatexInChat() {
    loadKatexScript().then(() => {
        // Find the chat history container
        const chatBox = document.getElementById('chat-history-box');
        if (!chatBox) {
            console.log('📐 KaTeX: chat-history-box not found');
            return;
        }

        // Find all text containers in chat that might contain LaTeX
        // Reflex markdown generates nested divs, so we look for any element containing LaTeX patterns
        const allElements = chatBox.querySelectorAll('div, p, span');
        let processedCount = 0;
        allElements.forEach(el => {
            // Skip if already processed or is a KaTeX element
            if (el.dataset.katexProcessed || el.classList.contains('katex') || el.closest('.katex')) {
                return;
            }
            // Skip code blocks
            if (el.closest('code') || el.closest('pre')) {
                return;
            }
            // Check if element contains any LaTeX pattern
            const text = el.textContent || '';

            // Check for LaTeX indicators: $...$ or $$...$$
            // Note: Server-side (formatting.py) converts \[...\], \(...\), and \text{} to $...$
            // So we only need to check for $ here
            const hasDollar = text.includes('$');

            if (hasDollar) {
                renderLatexInElement(el);
                el.dataset.katexProcessed = 'true';
                processedCount++;
            }
        });
        if (processedCount > 0) {
            console.log('📐 KaTeX: Processed', processedCount, 'elements');
        }
    }).catch(err => {
        console.warn('KaTeX not available:', err);
    });
}

// Setup KaTeX observer
let katexObserver = null;

function setupKatexObserver() {
    if (katexObserver) return;

    katexObserver = new MutationObserver((mutations) => {
        let shouldRender = false;
        for (const mutation of mutations) {
            if (mutation.addedNodes.length > 0) {
                shouldRender = true;
                break;
            }
        }
        if (shouldRender) {
            // Debounce rendering
            clearTimeout(window.katexRenderTimeout);
            window.katexRenderTimeout = setTimeout(renderLatexInChat, 100);
        }
    });

    katexObserver.observe(document.body, {
        childList: true,
        subtree: true
    });

    // Initial render
    renderLatexInChat();
    console.log('📐 KaTeX observer active');
}

// Initialize KaTeX after DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupKatexObserver);
} else {
    setTimeout(setupKatexObserver, 500);
}
