# Hybrid-Modus Kalibrierung: Diskussion und Optionen

**Datum:** 2025-12-29
**Status:** Diskussion / Noch nicht implementiert

## Hintergrund

Die aktuelle Kalibrierung funktioniert so:
1. **GPU-only zuerst**: Versucht, maximalen Kontext rein im VRAM zu finden
2. **Automatischer Hybrid-Fallback**: Wenn das Modell gar nicht ins VRAM passt (120B, 70B), wechselt es automatisch in den Hybrid-Modus
3. **Kein optionaler Hybrid**: Modelle die *gerade so* ins VRAM passen (z.B. 32B mit 40K Kontext) bekommen keinen Hybrid-Modus angeboten

## Das Problem

Beispiel: `qwen3:32b`
- Passt komplett ins VRAM (18.8 GB)
- Kalibriert auf ~40.960 Token (GPU-only)
- Könnte mit Hybrid-Modus vielleicht 80-100K Token erreichen
- **Aber**: Der User hat keine Möglichkeit, das zu wählen

Größere Modelle mit kleinem GPU-only Kontext könnten von Hybrid profitieren, aber der User weiß das nicht und hat keine Option es zu aktivieren.

## Mögliche Lösungsansätze

### Option A: "Erweiterte Kalibrierung" Button

```
[Kalibrieren] [Hybrid kalibrieren]
```

- Separater Button für Hybrid-Kalibrierung
- User entscheidet bewusst: "Ich will mehr Kontext, akzeptiere langsamere Performance"

| Pro | Contra |
|-----|--------|
| Explizite User-Kontrolle | UI-Komplexität erhöht |
| Einfach zu verstehen | Zwei Buttons für ähnliche Funktion |

---

### Option B: Automatische Hybrid-Empfehlung

Nach GPU-only Kalibrierung:
```
✅ GPU-only: 40.960 tok
💡 Mit Hybrid-Modus wären ~95.000 tok möglich
   [Hybrid kalibrieren?]
```

- System berechnet, ob Hybrid sich lohnen würde
- Zeigt potentiellen Gewinn an

| Pro | Contra |
|-----|--------|
| Informiert User über Möglichkeiten | Mehr Logik nötig |
| Unaufdringlich | Schätzung könnte ungenau sein |
| Nur wenn relevant |  |

---

### Option C: Memory-Modus Dropdown (analog zu RoPE)

```
Memory-Modus: [GPU-only ▼]
              [GPU-only]
              [Hybrid (CPU+GPU)]
```

- Analog zum RoPE-Dropdown
- Per-Model Einstellung
- Kalibrierte Werte für jeden Modus separat gespeichert

| Pro | Contra |
|-----|--------|
| Konsistente UI (wie RoPE) | Noch mehr Dropdowns in Settings |
| Flexible Kontrolle pro Modell | Kann User überfordern |
| Transparenz | Komplexere State-Logik |

**Implementation:**
- Neues State-Feld `aifred_memory_mode: str = "gpu"` (gpu/hybrid)
- VRAM-Cache speichert beide Werte: `max_context_gpu_only` und `max_context_hybrid`
- UI zeigt Dropdown unter dem Model-Select (wie RoPE)
- Bei Wechsel wird der entsprechende kalibrierte Wert verwendet

---

### Option D: Intelligente Auto-Entscheidung

- System entscheidet basierend auf:
  - Verfügbarem RAM
  - Gewinn durch Hybrid (>50% mehr Kontext?)
  - Performance-Tradeoff

| Pro | Contra |
|-----|--------|
| "Es funktioniert einfach" | Weniger User-Kontrolle |
| Keine UI-Änderungen nötig | Schwer vorhersagbar |
|  | Magic behaviour (unerwünscht) |

---

## Empfehlung

**Option C (Memory-Modus Dropdown)** erscheint am sinnvollsten:

1. **Konsistenz**: Passt zum RoPE-Dropdown-Pattern das bereits existiert
2. **Transparenz**: User sieht explizit, welchen Modus er nutzt
3. **Flexibilität**: Kann pro Modell unterschiedlich sein
4. **Kalibrierung**: Jeder Modus hat seinen eigenen kalibrierten Wert

**Alternative**: Option B (Empfehlung nach Kalibrierung) als Mittelweg - zeigt die Option, ohne die UI zu überladen.

## Offene Fragen

1. Soll Hybrid-Modus pro Agent einstellbar sein (AIfred, Sokrates, Salomo)?
2. Wie kommunizieren wir den Performance-Tradeoff dem User?
3. Brauchen wir eine "Reset to GPU-only" Option wenn Hybrid zu langsam ist?
4. Soll die Kalibrierung beide Modi gleichzeitig ermitteln oder sequenziell?

## Betroffene Dateien (geschätzt)

- `aifred/state.py` - Neue State-Felder, Memory-Mode Handling
- `aifred/aifred.py` - UI für Memory-Mode Dropdown
- `aifred/backends/ollama.py` - Kalibrierungslogik erweitern
- `aifred/lib/model_vram_cache.py` - Neues Feld für Hybrid-Kontext
- `aifred/lib/gpu_utils.py` - calculate_vram_based_context anpassen

## Verwandte Dokumentation

- [OLLAMA_CONTEXT_CALIBRATION.md](./OLLAMA_CONTEXT_CALIBRATION.md)
- [HYBRID_MODE_GUIDE.md](../llm/HYBRID_MODE_GUIDE.md)
