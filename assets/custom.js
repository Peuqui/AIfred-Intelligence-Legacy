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
    const handleAudioPlayer = (player) => {
        if (!player || !player.src) return;

        const src = player.src;
        console.log('🔊 TTS Observer: Detected audio player, src =', src);

        // Only process TTS audio URLs
        if (!src.includes('/tts_audio/')) return;

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
    console.log('🚀 Initializing TTS observer...');

    // Setup TTS audio observer
    setupTtsAudioObserver();

    // Retry after 500ms in case elements render later
    setTimeout(() => {
        setupTtsAudioObserver();
    }, 500);
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
