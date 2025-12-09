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
const observerConfig = { childList: true, subtree: true };

const callback = function(mutationsList, observer) {
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
        const observer = new MutationObserver(callback);
        observer.observe(debugBox, observerConfig);
    } else {
        console.warn('❌ debug-console-box not found');
    }

    const chatBox = document.getElementById('chat-history-box');
    if (chatBox) {
        console.log('✅ Found chat-history-box');
        const observer = new MutationObserver(callback);
        observer.observe(chatBox, observerConfig);
    } else {
        console.warn('❌ chat-history-box not found');
    }
}

// Try multiple times to setup observers (Reflex might render async)
document.addEventListener('DOMContentLoaded', function() {
    console.log('📄 DOMContentLoaded event fired');

    // Make existing links open in new tab
    makeLinksOpenInNewTab();

    setupObservers();

    // Retry after 500ms in case elements render later
    setTimeout(() => {
        setupObservers();
        makeLinksOpenInNewTab();
    }, 500);

    // Retry after 1000ms
    setTimeout(() => {
        setupObservers();
        makeLinksOpenInNewTab();
    }, 1000);
});
