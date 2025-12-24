# Ollama Auto-Context Calibration Plan

**Status:** Geplant
**Priorität:** Sehr Hoch
**Erstellt:** 2025-12-24

## Ziel
Automatische Ermittlung des maximalen Context-Windows ohne CPU-Offloading für Ollama-Modelle.
Nutzt die volle VRAM-Kapazität (2x P40 oder RTX 3090).

---

## Kernkonzept

### `/api/ps` Response enthält die Schlüsselinformation:
```json
{
  "models": [{
    "name": "qwen3:8b",
    "size": 4700000000,        // Total memory (kann CPU+GPU sein)
    "size_vram": 4700000000,   // NUR GPU memory
    "context_length": 32768    // Aktuell geladener Context
  }]
}
```

**Regel:** `size == size_vram` → Modell komplett in VRAM, kein CPU-Offload

---

## Algorithmus: Binäre Suche

```
Input: model_name, native_context (z.B. 128k)
Output: max_context_gpu_only

1. low = 4096, high = native_context
2. Lade Modell mit num_ctx = high
3. Query /api/ps → size vs size_vram
4. IF size == size_vram:
     result = high
     low = high
     high = min(high * 1.5, native_context)  # Versuche mehr
   ELSE:
     high = (low + high) // 2  # CPU-Offload → halbieren
5. REPEAT bis |high - low| < 1024
6. Speichere result in model_vram_cache.json
```

---

## Implementierung

### Schritt 1: `model_vram_cache.py` - Neue Funktionen

```python
def add_ollama_calibration(
    model_name: str,
    max_context_gpu_only: int,
    free_vram_mb: int,
    native_context: int,
    gpu_model: str = None
) -> None:
    """Speichert kalibriertes Context-Maximum für Ollama"""

def get_ollama_calibrated_max_context(
    model_name: str
) -> Optional[int]:
    """Holt kalibriertes Maximum (existiert bereits, aber leer)"""
```

**Cache-Struktur erweitern:**
```json
{
  "qwen3:8b": {
    "backend": "ollama",
    "native_context": 131072,
    "ollama_calibrations": [{
      "max_context_gpu_only": 52000,
      "free_vram_mb": 22000,
      "gpu_model": "NVIDIA GeForce RTX 3090 Ti",
      "measured_at": "2025-12-24T14:00:00"
    }]
  }
}
```

### Schritt 2: `ollama.py` - Kalibrierungslogik

```python
async def calibrate_max_context(
    self,
    model: str,
    progress_callback: Optional[Callable[[str], None]] = None
) -> int:
    """
    Binäre Suche für maximalen Context ohne CPU-Offload.

    Args:
        model: Modellname (z.B. "qwen3:8b")
        progress_callback: Optional callback für UI-Updates

    Returns:
        max_context_gpu_only: Kalibriertes Maximum
    """
    # 1. Hole native_context via /api/show
    native_ctx, model_size = await self.get_model_context_limit(model)

    # 2. Binäre Suche
    low, high = 4096, native_ctx
    result = low

    while high - low > 1024:
        mid = (low + high) // 2
        if progress_callback:
            progress_callback(f"Testing {mid // 1024}k...")

        # Lade mit mid context
        await self.preload_model(model, num_ctx=mid)

        # Check CPU-Offload
        if await self._is_fully_in_vram(model):
            result = mid
            low = mid
        else:
            high = mid

    # 3. Speichern
    add_ollama_calibration(model, result, ...)
    return result

async def _is_fully_in_vram(self, model: str) -> bool:
    """Prüft ob Modell komplett in VRAM (size == size_vram)"""
    ps_data = await self._query_ps()
    for m in ps_data.get("models", []):
        if m["name"] == model or model in m["name"]:
            return m["size"] == m["size_vram"]
    return False
```

### Schritt 3: `state.py` - UI Integration

```python
async def calibrate_model_context(self):
    """Event Handler für Kalibrierungs-Button"""
    if not self.selected_model_id:
        return

    self.add_debug(f"🔧 Starte Kalibrierung für {self.selected_model_id}...")
    self.calibration_in_progress = True
    yield

    backend = self._get_backend()

    def progress(msg: str):
        self.add_debug(f"📊 {msg}")

    try:
        max_ctx = await backend.calibrate_max_context(
            self.selected_model_id,
            progress_callback=progress
        )
        self.add_debug(f"✅ Kalibriert: {max_ctx // 1024}k Context")
    finally:
        self.calibration_in_progress = False

    yield
```

### Schritt 4: `aifred.py` - Button in Settings

```python
# Nach Model-Dropdown, nur wenn Ollama Backend
rx.cond(
    AIState.backend_id == "ollama",
    rx.button(
        rx.cond(
            AIState.calibration_in_progress,
            rx.hstack(rx.spinner(size="1"), "Kalibriere..."),
            rx.hstack(rx.icon("gauge"), "Context kalibrieren")
        ),
        on_click=AIState.calibrate_model_context,
        disabled=AIState.calibration_in_progress,
        size="1",
        variant="outline",
    )
)
```

---

## Betroffene Dateien

| Datei | Änderungen |
|-------|------------|
| `aifred/lib/model_vram_cache.py` | `add_ollama_calibration()`, Cache-Struktur |
| `aifred/backends/ollama.py` | `calibrate_max_context()`, `_is_fully_in_vram()` |
| `aifred/state.py` | `calibrate_model_context()`, `calibration_in_progress` |
| `aifred/aifred.py` | Kalibrierungs-Button in Settings |

---

## Entscheidungen

1. **Kalibrierung:** Beides - Manueller Button + Toggle für Auto-Kalibrierung beim ersten Load
2. **Progress-Anzeige:** Debug-Konsole (einfach, keine neue UI-Komponente)
3. **Multi-GPU:** Ollama handled das intern - wir prüfen nur size vs size_vram

---

## Nächste Schritte

1. [ ] `add_ollama_calibration()` in model_vram_cache.py implementieren
2. [ ] `calibrate_max_context()` in ollama.py implementieren
3. [ ] State-Variable + Event Handler
4. [ ] UI-Button
5. [ ] Testen mit verschiedenen Modellen
