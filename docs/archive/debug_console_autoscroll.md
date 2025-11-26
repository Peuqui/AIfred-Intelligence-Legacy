# Debug Console Auto-Scroll

## Überblick

Die Debug Console in AIfred verwendet ein JavaScript-basiertes Auto-Scroll-System, das zuverlässig während schnellen State-Updates funktioniert (Intent Detection, LLM-Generierung).

## Problem mit Reflex's `rx.auto_scroll()`

Reflex's eingebautes `rx.auto_scroll()` bricht bei schnellen State-Updates zusammen:
- Stoppt nach ~0.3 Sekunden (TTFT - Time To First Token)
- Funktioniert nicht bei nachfolgenden Anfragen
- Springt zum Anfang wenn Toggle deaktiviert wird

## Lösung: MutationObserver-basiertes JavaScript

### Architektur

```
User Request
    ↓
Debug Message Update (State.debug_messages)
    ↓
DOM Mutation (neue <p> Tags)
    ↓
MutationObserver Callback
    ↓
isAutoScrollEnabled() prüft Toggle
    ↓
autoScrollElement() scrollt zum Ende
```

### Implementierung

**Inline JavaScript** ([aifred.py:1620-1737](../aifred/aifred.py#L1620-L1737)):
```javascript
const observerConfig = { childList: true, subtree: true };

const callback = function(mutationsList, observer) {
    const enabled = isAutoScrollEnabled();

    if (!enabled) {
        return;  // Preserve scroll position
    }

    const debugBox = document.getElementById('debug-console-box');
    if (debugBox) {
        debugBox.scrollTop = debugBox.scrollHeight;
    }
};

const observer = new MutationObserver(callback);
observer.observe(debugBox, observerConfig);
```

**Debug Console ohne `rx.auto_scroll()`** ([aifred.py:996-1024](../aifred/aifred.py#L996-L1024)):
```python
debug_content = rx.box(
    rx.foreach(
        AIState.debug_messages,
        lambda msg: rx.text(msg, ...),
    ),
    id="debug-console-box",  # Für JavaScript-Zugriff
    width="100%",
    height="500px",
    overflow_y="auto",
    style={"scroll-behavior": "smooth"},
)
```

### Toggle-Integration

Der Auto-Scroll-Toggle wird via `data-state` Attribut ausgelesen:

```javascript
function isAutoScrollEnabled() {
    const switches = document.querySelectorAll('[role="switch"]');
    for (let sw of switches) {
        const parent = sw.closest('.rx-Flex');
        if (parent && parent.textContent.includes('Auto-Scroll')) {
            return sw.getAttribute('data-state') === 'checked';
        }
    }
    return true;  // Default: enabled
}
```

## Features

✅ **Funktioniert bei:**
- Intent Detection (schnelle State-Updates)
- LLM-Generierung (Streaming-Tokens)
- Nachfolgenden Anfragen
- Manueller Scroll + neue Anfrage

✅ **Toggle-Verhalten:**
- **Aktiviert**: Scrollt automatisch zum Ende
- **Deaktiviert**: Scroll-Position bleibt erhalten (kein Sprung zum Anfang!)

✅ **Performance:**
- MutationObserver: ~0ms Overhead (Browser-nativ)
- Smooth Scrolling via CSS `scroll-behavior`

## Dateien

| Datei | Zweck | Zeilen |
|-------|-------|--------|
| `aifred/aifred.py` | Inline JavaScript | 1620-1737 |
| `aifred/aifred.py` | Debug Console Box | 996-1024 |
| `assets/custom.js` | *(Legacy, nicht verwendet)* | - |

**Hinweis**: Das JavaScript ist **inline eingebettet**, nicht als externes File. Grund: Reflex's Asset-Loading-System hat Timing-Probleme.

## Warum Inline JavaScript?

Externe JavaScript-Files (`/assets/custom.js`) werden von Reflex inkonsistent geladen:
- `rx.script(src="/custom.js")` → Wird nicht ausgeführt
- `head_components=[rx.script(...)]` → Timing-Probleme mit React Helmet

**Lösung**: JavaScript direkt in `rx.script(autoscroll_js)` einbetten.

## Debugging

### Console-Logs

Das JavaScript enthält Debug-Logs (optional entfernbar):

```javascript
console.log('🔧 Autoscroll script loaded');
console.log('📄 Initializing autoscroll...');
console.log('🚀 Setting up observers...');
console.log('✅ Found debug-console-box');
console.log('🔍 MutationObserver triggered, auto-scroll enabled:', enabled);
console.log('📜 Scrolling element:', element.id, 'scrollTop:', element.scrollTop);
```

### Häufige Probleme

**Problem**: JavaScript-Logs erscheinen nicht in Console
- **Ursache**: React Helmet lädt Scripts verzögert
- **Lösung**: Nicht kritisch, solange Autoscroll funktioniert

**Problem**: Autoscroll stoppt nach einigen Sekunden
- **Ursache**: MutationObserver nicht richtig initialisiert
- **Lösung**: `document.readyState` Check hinzufügen (bereits implementiert)

**Problem**: Toggle funktioniert nicht
- **Ursache**: Switch-Element nicht gefunden
- **Lösung**: `parent.textContent.includes('Auto-Scroll')` prüft deutschen Text

## Zukünftige Erweiterungen

- [ ] Console-Logs optional über Config-Flag
- [ ] Scroll-Geschwindigkeit konfigurierbar
- [ ] Auto-Scroll für Chat History (bereits implementiert, aber ID fehlt)
- [ ] "Scroll to Bottom" Button bei manueller Scroll-Position

## Alternative Ansätze (verworfen)

### 1. Reflex's `rx.auto_scroll()` ❌
```python
# Funktioniert NICHT bei schnellen State-Updates
rx.cond(
    AIState.auto_scroll_enabled,
    rx.auto_scroll(debug_content, ...),
    debug_content,
)
```
**Problem**: Bricht nach TTFT (~0.3s)

### 2. Externes JavaScript via Asset-System ❌
```python
rx.script(src="/custom.js")
```
**Problem**: Wird nicht geladen oder zu spät ausgeführt

### 3. `useEffect` Hook in React ❌
```python
rx.script("useEffect(() => { scrollToBottom(); }, [messages])")
```
**Problem**: Reflex unterstützt keine React Hooks direkt

## Verwandte Dokumentation

- [VRAM Detection](vllm_vram_detection.md) - Ähnliches Problem mit State-Updates
- [Context Management](../aifred/lib/config.py) - Konfiguration für Auto-Scroll (zukünftig)

---

**Dokumentation erstellt**: 2025-11-21
**Letzte Aktualisierung**: 2025-11-21
**AIfred Version**: 3.0+
