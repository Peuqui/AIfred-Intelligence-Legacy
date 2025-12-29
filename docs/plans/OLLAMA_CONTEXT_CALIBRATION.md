# Ollama Context Calibration System

**Status:** Implementiert
**Version:** 3.0 (mit Hybrid-Mode + RoPE-Skalierung)
**Erstellt:** 2025-12-24
**Aktualisiert:** 2025-12-29

---

## Überblick

Automatische Bestimmung des maximalen Context-Windows für Ollama-Modelle mit intelligenter Hybrid-Mode-Erkennung und RoPE-Skalierung.

### Features

- **3-Stufen RoPE-Kalibrierung**: Native (1.0x), RoPE 1.5x, RoPE 2.0x
- **Hybrid-Mode-Erkennung**: Automatischer CPU-Offload für große Modelle
- **Inkrementeller Binary Search**: Jeder RoPE-Faktor startet beim vorherigen Ergebnis
- **is_hybrid Flag**: Cache speichert ob Hybrid-Mode aktiv ist

---

## Flussdiagramm

```
                    ┌─────────────────────────────┐
                    │     Kalibrierung starten    │
                    │      (Model auswählen)      │
                    └─────────────┬───────────────┘
                                  │
                                  ▼
                    ┌─────────────────────────────┐
                    │  STEP 1: Native (1.0x)      │
                    │  Binary Search: 8K → native │
                    └─────────────┬───────────────┘
                                  │
                                  ▼
                    ┌─────────────────────────────┐
                    │   Ergebnis auswerten        │
                    └─────────────┬───────────────┘
                                  │
           ┌──────────────────────┼──────────────────────┐
           │                      │                      │
           ▼                      ▼                      ▼
    ┌─────────────┐      ┌──────────────┐      ┌──────────────┐
    │   ERROR     │      │ ctx < native │      │ ctx = native │
    │   (ctx=0)   │      │ (Memory-Limit)│     │ (passt voll) │
    └──────┬──────┘      └──────┬───────┘      └──────┬───────┘
           │                    │                     │
           ▼                    ▼                     │
    ┌─────────────┐      ┌──────────────┐            │
    │  ABBRUCH    │      │ Auto-Set     │            │
    │ (zu groß)   │      │ 1.5x = 2.0x  │            │
    └─────────────┘      │ = 1.0x Wert  │            │
                         └──────────────┘            │
                                                     ▼
                                        ┌────────────────────────┐
                                        │  War 1.0x Hybrid-Mode? │
                                        └───────────┬────────────┘
                                                    │
                              ┌─────────────────────┴─────────────────────┐
                              │                                           │
                              ▼                                           ▼
                    ┌─────────────────┐                        ┌─────────────────┐
                    │   GPU-only      │                        │   Hybrid-Mode   │
                    │ Normal Binary   │                        │ force_hybrid=   │
                    │    Search       │                        │     True        │
                    └────────┬────────┘                        └────────┬────────┘
                             │                                          │
                             └────────────────┬─────────────────────────┘
                                              │
                                              ▼
                              ┌───────────────────────────────┐
                              │  STEP 2: RoPE 1.5x            │
                              │  min_context = 1.0x Ergebnis  │
                              │  target = native × 1.5        │
                              └───────────────┬───────────────┘
                                              │
                                              ▼
                              ┌───────────────────────────────┐
                              │  Teste direkt max (1.5x)      │
                              │  Passt? → Fertig!             │
                              │  Sonst: Binary Search         │
                              │  zwischen 1.0x und 1.5x       │
                              └───────────────┬───────────────┘
                                              │
                                              ▼
                              ┌───────────────────────────────┐
                              │  STEP 3: RoPE 2.0x            │
                              │  min_context = 1.5x Ergebnis  │
                              │  target = native × 2.0        │
                              └───────────────┬───────────────┘
                                              │
                                              ▼
                              ┌───────────────────────────────┐
                              │  Teste direkt max (2.0x)      │
                              │  Passt? → Fertig!             │
                              │  Sonst: Binary Search         │
                              │  zwischen 1.5x und 2.0x       │
                              └───────────────┬───────────────┘
                                              │
                                              ▼
                              ┌───────────────────────────────┐
                              │  Speichere alle 3 Werte       │
                              │  in model_vram_cache.json     │
                              └───────────────────────────────┘
```

---

## Entscheidungslogik

### Nach 1.0x Kalibrierung

| Ergebnis | `calibrated_ctx` | Vergleich | Aktion |
|----------|------------------|-----------|--------|
| **Error** | 0 | - | Abbruch, nichts speichern |
| **GPU-only** | < native | VRAM-Limit | Skip RoPE, auto-set 1.5x/2.0x |
| **Hybrid** | < native | RAM-Limit | Skip RoPE, auto-set 1.5x/2.0x |
| **GPU-only** | = native | Passt voll | Kalibriere RoPE 1.5x/2.0x |
| **Hybrid** | >= native | Native passt | Kalibriere RoPE 1.5x/2.0x |

### RoPE-Kalibrierung (wenn nicht übersprungen)

| Schritt | min_context | target | Modus |
|---------|-------------|--------|-------|
| 1.5x | 1.0x Ergebnis | native × 1.5 | GPU oder Hybrid (von 1.0x) |
| 2.0x | 1.5x Ergebnis | native × 2.0 | GPU oder Hybrid (von 1.0x) |

---

## Cache-Struktur

```json
{
  "qwen3:32b-q4_K_M": {
    "backend": "ollama",
    "native_context": 40960,
    "gpu_model": "NVIDIA GeForce RTX 3090 Ti",
    "ollama_calibrations": [
      {
        "max_context_1.0x": 40960,
        "is_hybrid": true,
        "measured_at": "2025-12-29T13:51:59.481799"
      },
      {
        "max_context_1.5x": 61440,
        "is_hybrid": true,
        "measured_at": "2025-12-29T13:52:31.176256"
      },
      {
        "max_context_2.0x": 81920,
        "is_hybrid": true,
        "measured_at": "2025-12-29T13:53:02.668284"
      }
    ]
  }
}
```

---

## Beispiel: qwen3:32b-q4_K_M (18.8 GB Model, 24 GB VRAM)

```
13:49:06 | 📐 Calibrating Native (1.0x)...
13:49:08 | 📊 Model: 18,8 GB | VRAM: 20,3 GB | RAM: 43,5 GB
13:49:08 | 📊 [1] Testing 40.960...
13:49:36 | 📊 ✗ 40.960 too large, starting binary search...
13:49:36 | 📊 Binary search range: 8.192 → 40.960 tok

         ... Binary Search: 24K, 16K, 12K, 10K, 9K, 8K → alle CPU offload ...

13:51:29 | 📊 ⚠️ GPU-only context (8.192) <= minimum (8.192)
13:51:29 | 📊 → Switching to Hybrid mode for usable context...
13:51:29 | 📊 → Hybrid calculation: 40.960 tokens
13:51:59 | 📊 ✅ Hybrid mode: 40.960 tokens
13:51:59 | ────────────────────────────────────────
13:51:59 | 🔀 Hybrid mode: 40.960 (native fits)
13:51:59 |    → Testing if RoPE scaling can extend context further...
13:51:59 | ────────────────────────────────────────
13:51:59 | 📐 Calibrating RoPE 1.5x...
13:52:01 | 📊 🔀 Hybrid mode (continuing from 1.0x calibration)
13:52:01 | 📊 → Binary search range: 40.960 → 61.440 tok
13:52:01 | 📊 [1] Testing 61.440...
13:52:31 | 📊 ✅ 61.440 fits in RAM
13:52:31 | ────────────────────────────────────────
13:52:31 | 📐 Calibrating RoPE 2.0x...
13:52:32 | 📊 🔀 Hybrid mode (continuing from 1.0x calibration)
13:52:32 | 📊 → Binary search range: 61.440 → 81.920 tok
13:52:32 | 📊 [1] Testing 81.920...
13:53:02 | 📊 ✅ 81.920 fits in RAM
13:53:02 | ════════════════════════════════════════
13:53:02 | ✅ Calibration complete for qwen3:32b-q4_K_M (Hybrid):
13:53:02 |    Native: 40.960 tok
13:53:02 |    RoPE 1.5x: 61.440 tok
13:53:02 |    RoPE 2.0x: 81.920 tok
```

**Ergebnis:** 32B Model nutzt 81.920 Tokens Context im Hybrid-Modus!

---

## Implementierung

### Key Files

| Datei | Funktion |
|-------|----------|
| `aifred/backends/ollama.py` | `calibrate_max_context_generator()` mit `force_hybrid` und `min_context` |
| `aifred/state.py` | Kalibrierungs-Orchestrierung, RoPE-Loop mit `prev_ctx` |
| `aifred/lib/model_vram_cache.py` | `add_ollama_calibration()` mit `is_hybrid` Flag |
| `aifred/lib/gpu_utils.py` | `calculate_vram_based_context()` liest Kalibrierung |

### Neue Parameter in `calibrate_max_context_generator()`

```python
async def calibrate_max_context_generator(
    self,
    model: str,
    rope_factor: float = 1.0,
    min_context: int | None = None,    # Unteres Binary Search Limit
    force_hybrid: bool = False          # Direkt in Hybrid-Mode starten
):
```

### RoPE-Loop in `state.py`

```python
# Start from 1.0x result, then use previous RoPE result as new minimum
prev_ctx = calibration_results.get(1.0, CALIBRATION_MIN_CONTEXT)

for rope_factor in [1.5, 2.0]:
    async for progress_msg in backend.calibrate_max_context_generator(
        self.aifred_model_id,
        rope_factor=rope_factor,
        min_context=prev_ctx,       # Start from previous result
        force_hybrid=is_hybrid_mode # Continue in hybrid if 1.0x was hybrid
    ):
        if progress_msg.startswith("__RESULT__:"):
            parts = progress_msg.split(":")
            rope_calibrated_ctx = int(parts[1])
            prev_ctx = rope_calibrated_ctx  # Update for next iteration
```

---

## Vorteile des neuen Systems

1. **Schnellere Kalibrierung**: RoPE 1.5x/2.0x testen nur noch den Bereich über dem vorherigen Ergebnis
2. **Hybrid-Kontinuität**: Wenn 1.0x Hybrid ist, bleiben 1.5x/2.0x auch im Hybrid-Modus
3. **Kein Neustart**: Bei Memory-Limit werden RoPE-Faktoren automatisch auf 1.0x-Wert gesetzt
4. **is_hybrid Flag**: Cache weiß ob CPU-Offload aktiv ist

---

## Konfiguration

```python
# aifred/lib/config.py
CALIBRATION_MIN_CONTEXT = 8192  # 8K minimum für nutzbare Kontexte
```

---

## Verwandte Dokumentation

- [MEMORY_MANAGEMENT.md](../llm/MEMORY_MANAGEMENT.md) - Smart Model Loading
- [HYBRID_MODE_GUIDE.md](../llm/HYBRID_MODE_GUIDE.md) - CPU-Offload Details
- [LLM_PARAMETERS.md](../llm/LLM_PARAMETERS.md) - num_ctx Parameter

---

**Letzte Aktualisierung:** 2025-12-29
**Version:** 3.0 - Hybrid-Mode + RoPE-Skalierung
