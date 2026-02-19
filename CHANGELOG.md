# Changelog

All notable changes to AIfred Intelligence will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.41.0] - 2026-02-19 🛡️ VMM-sichere VRAM-Kalibration

### Changed

- **Kalibration: pynvml statt Breakdown für VRAM-Messung** - `_test_context_physical()` misst jetzt GPU-weiten freien VRAM via pynvml (nvidia-smi) statt llama.cpp-internem Breakdown (`free` dort ist immer 0)
  - Sofortige Messung nach Server-Start (kein Settle-Delay nötig — Delta <15 MB verifiziert)
  - Breakdown wird nur noch als Diagnose-Info geloggt (self + unaccounted)
- **Plattform-abhängige VRAM Safety Margin** - Neue Konstante `LLAMACPP_VRAM_SAFETY_MARGIN` ersetzt `VRAM_SAFETY_MARGIN` in der llama.cpp-Kalibration
  - WSL2/Windows (WDDM): 1536 MB — WDDM swappt VRAM still ins System-RAM (7x Slowdown)
  - Natives Linux: 512 MB — `cudaMalloc` gibt OOM zurück, kein stilles Swapping
  - Automatische Erkennung via `platform.release()` (WSL2) und `os.name` (Windows)
  - Gemessen auf WSL2 RTX 3090 Ti: 512 MB → 70 tok/s, 1024 MB → marginal, 1536 MB → 137 tok/s
- **Plattform-Logging beim Start** - OS/Kernel und WDDM-Status werden in Debug-Log und Konsole geloggt

### Fixed

- **VMM Overallocation Detection** - `_check_vram_physical_fit()` prüft jetzt `free < margin` statt `self > total` — erkennt Fälle wo "unaccounted" VRAM (~4 GB für CUDA-Runtime, Display, Treiber) via VMM verdrängt wird

---

## [2.40.0] - 2026-02-19 🚀 Projektionsbasierte Kalibration & Settings-Guard

### Changed

- **Kalibration: llama-fit-params Projektion statt Heuristik** - VRAM-Projektion via `llama-fit-params` Binary (0,3s pro Aufruf, kein Model-Loading) berechnet exakte MiB/Token-Rate aus zwei Datenpunkten
  - Ersetzt die alte hardcodierte 0,08 MiB/tok Heuristik durch modell-spezifische Berechnung
  - Zwei-Punkt-Interpolation: `rate = (P_high - P_low) / (ctx_high - ctx_low)` für exakte lineare VRAM-Projektion
  - `_get_fit_params_binary()`, `_build_fit_params_cmd()`, `_get_vram_projection()`, `_calculate_max_context()`: Neue Funktionen für die Projektionsberechnung
  - `_estimate_upper_bound()` entfernt (obsolet durch Projektion)
- **Kalibration: Binary Search in beide Richtungen** - Nach der initialen Projektion wird der tatsächliche maximale Context per Binary Search mit 512-Token-Granularität gesucht
  - Projektion passt → Binary Search aufwärts [calculated_max, native_context]
  - Projektion zu optimistisch → Binary Search abwärts [MIN_CONTEXT, calculated_max]
  - Ergebnis: typisch +21.000 Tokens mehr als die konservative Projektion allein (getestet: 261.801 vs 240.211 bei Qwen3-4B Q8_0)

### Fixed

- **Settings: Cross-Backend-Korruption verhindert** - `_save_settings()` validiert jetzt Model-IDs gegen `available_models_dict` bevor `backend_models` geschrieben wird
  - Verhindert, dass llamacpp-Model-IDs unter dem Ollama-Backend gespeichert werden (und umgekehrt) bei Race Conditions während Backend-Switches
  - Bestehendes `backend_models` bleibt erhalten wenn die Validierung fehlschlägt (kein Datenverlust)

---

## [2.39.0] - 2026-02-18 🎥 VL-Modell-Support & llamacpp Restart-Fix

### Added

- **Autoscan: Vision-Language-Modell-Unterstützung (mmproj)** - Autoscan erkennt jetzt `mmproj-*.gguf`-Dateien und verknüpft sie automatisch mit dem passenden Haupt-Modell
  - `_strip_quant_suffix()` und `_find_mmproj()`: Quantisierungs-Suffix wird entfernt (z.B. `Q4_K_M`, `Q8_0`, `F16`) und Basis-Namen verglichen (case-insensitive)
  - VL-Modelle erhalten `--mmproj <pfad>` im llama-swap YAML-Eintrag
  - Ausgabe zeigt VL-Modelle mit Projector: `◆ Qwen3VL-8B-Instruct-Q4_K_M + mmproj-Qwen3VL-8B-Instruct-F16.gguf`
  - `test_model_compatibility()` nimmt `mmproj_path: Optional[Path]` entgegen und testet VL-Modelle korrekt
- **Autoscan: Erkennung fehlender GGUF-Metadaten** - Neuer Fehlertyp `"key not found in model"` wird jetzt abgefangen (z.B. `qwen3vl.rope.dimension_sections` bei Ollama-Blobs)
  - Bei Ollama-Blob-Symlinks: Hinweis `— Ollama blob missing llama.cpp metadata; download official GGUF from HuggingFace`
  - Modell landet in der Skip-Liste mit erklärendem Grund

### Fixed

- **llamacpp Backend Restart ohne Funktion** - `restart_backend()` hatte keinen `llamacpp`-Branch → Klick auf Restart tat nichts
  - Führt jetzt `systemctl --user restart llama-swap` aus (mit `XDG_RUNTIME_DIR`/`DBUS_SESSION_BUS_ADDRESS` für Service-Kontext)
  - Wartet bis llama-swap bereit ist: Pollt `/v1/models` mit bis zu 20 Versuchen (0.5s Intervall, max 10s)
  - Debug-Anzeige: `✅ llama-swap ready after 3.5s` bzw. Fehlermeldung bei Timeout

### Changed

- **VRAM-Cache bereinigt** - 6 verwaiste/unbrauchbare Einträge entfernt:
  - `Qwen3-VL-8B-Q4_K_M` (Ollama-Blob fehlt MRoPE-Metadaten, fundamental inkompatibel)
  - `Qwen3-14B-Q4_K_M`, `Qwen3-VL-30B-A3B-Instruct-Q4_K_M` (Dateien existieren nicht mehr)
  - `Smollm2-135m-F16` (8192 Token Kontext — zu klein für AIfred-Systemprompt)
  - `Qwen3-1.7B-Q4_K_M`, `Qwen3-4B-Instruct-2507-Q4_K_M` (entfernt)

---

## [2.38.0] - 2026-02-18 🛡️ Autoscan Kompatibilitätsprüfung & Kalibrierungs-Fixes

### Added

- **Autoscan: Kompatibilitätsprüfung für neue Modelle** - Startet llama-server kurz für jedes neu entdeckte Modell (6s Timeout) und erkennt unsupportete Architekturen (z.B. `deepseekocr`) bevor sie in die Config kommen
  - Inkompatible Modelle werden mit Grund übersprungen: `✗ Deepseek-OCR-3B-F16: unsupported architecture 'deepseekocr'`
  - Kompatible Architekturen: Timeout = Server läuft = alles gut → wird normal eingetragen
- **Autoscan: Skip-Liste** (`~/.config/llama-swap/autoscan-skip.json`) - Einmal geprüfte inkompatible Modelle werden persistent gespeichert, kein erneuter Test bei jedem llama-swap-Start
  - Eintrag manuell löschen um nach llama.cpp-Update neu zu testen
- **Kalibrierung: flash-attn Auto-Detection** (`update_llamaswap_flash_attn()`) - Wenn ein Modell nicht startet und `--flash-attn on` im Cmd ist: automatischer Retry ohne flash-attn
  - Bei Erfolg: llama-swap Config wird automatisch auf `--flash-attn off` umgestellt
  - Greift im Sonderfall für kleine Modelle (native_context ≤ 8192)
- **Kalibrierung: Sonderfall für kleine Modelle** - Modelle mit `native_context ≤ CALIBRATION_MIN_CONTEXT` (8192 Token) werden direkt getestet ohne Binary-Search (die ohnehin keinen Sinn ergibt)
- **Kalibrierung: Startup-Fehler sichtbar** - `stderr=subprocess.STDOUT` in Popen: llama-server-Output (stdout+stderr kombiniert) wird bei Fehlschlag vollständig ins Log geschrieben

### Fixed

- **Kalibrierung: Falsche Daten bei Startup-Fehler** - `any_test_succeeded` Guard verhindert dass ein nicht-VRAM-bedingter Startfehler (z.B. unbekannte Architektur) fälschlicherweise als `max_context=8192` in den VRAM-Cache geschrieben wird
- **Kalibrierung: `config_path` nicht übergeben** - `aifred/backends/llamacpp.py` übergibt jetzt `config_path=LLAMASWAP_CONFIG_PATH` an `calibrate_llamacpp_model()` damit YAML-Updates (flash-attn, context, ngl) tatsächlich in die Config geschrieben werden

---

## [2.37.1] - 2026-02-18 🔧 Bugfixes & Code-Vereinfachung

### Fixed

- **Cold-Start-Bug bei Speed-Modus + expliziter Automatik-LLM** - `_effective_automatik_id` erkennt jetzt, wenn Automatik-LLM explizit auf AIfred's Base-Modell gesetzt ist und AIfred im Speed-Modus läuft → folgt automatisch der Speed-Variante statt llama-swap-Swap auszulösen (~80s Delay pro Automatik-Aufruf)
- **Automatik-LLM Preload beim Start entfernt** - Verhinderte 60-80s Startup-Delay bei großen Modellen; erster Request lädt das Modell bei Bedarf

### Changed

- **Title-Generierung vereinfacht** - `_generate_session_title` nutzt jetzt direkt `_effective_automatik_id` wie alle anderen Automatik-Aufrufe (Intent-Erkennung, History-Kompression etc.); interner `model_id`-Parameter entfernt

---

## [2.37.0] - 2026-02-18 🔍 llama-swap Autoscan & Automatik-LLM Vereinheitlichung

### Added

- **llama-swap Autoscan** (`scripts/llama-swap-autoscan.py`) - Automatische Modell-Erkennung beim Service-Start
  - Scannt Ollama-Manifests und erstellt beschreibende Symlinks in `~/models/` (z.B. `sha256-6335adf...` → `Qwen3-14B-Q8_0.gguf`)
  - Inline-Deduplizierung: Bei mehreren Ollama-Tags zum selben Blob wird der längste/beschreibendste Name gewählt
  - Blob-Target-Guard in `create_symlinks()`: Verhindert Duplikate durch manuelle Symlinks die denselben Blob abdecken
  - Erkennt neue GGUFs und ergänzt llama-swap Config mit Einträgen für optimale Default-Parameter
  - Erstellt vorläufige VRAM-Cache-Einträge (Kalibrierung über UI)
  - Läuft als `ExecStartPre` im systemd-Service → kein manuelles Setup für neue Modelle nötig
  - Embedding-Modelle (BERT, nomic, etc.) werden automatisch übersprungen
- **„(wie AIfred-LLM)" Option für Automatik-LLM** - Konsistenz mit Sokrates/Salomo-Dropdowns
  - Automatik-LLM-Dropdown zeigt jetzt „(wie AIfred-LLM)" als erste Option (intern als Leerstring gespeichert)
  - Auflösung über `_effective_automatik_id`-Property: `""` → `aifred_model_id` an allen funktionalen Stellen (Intent-Erkennung, Chat-Calls, Session-Titel, RoPE-Factor, Preload)
  - Restore/Validierung: Leerstring wird korrekt als „wie AIfred" akzeptiert (kein Fallback auf config.py-Default)
  - Debug-Anzeige: Zeigt `(= AIfred)` wenn Automatik-LLM dem Haupt-Modell folgt
  - vLLM/TabbyAPI (Single-Model-Backends): Automatik wird automatisch auf `""` gesetzt statt explizit auf AIfred-ID

### Changed

- **llama-swap Config-Pfad** verschoben zu `~/.config/llama-swap/config.yaml` (XDG-Standard, weg von `~/llama-swap-config.yaml`)
- **llama-swap Port** von 8080 → **11435** (direkt neben Ollama 11434, weniger Konflikt-Risiko)
- `LLAMACPP_URL`-Default in `config.py` auf `http://localhost:11435/v1` aktualisiert
- Systemd-Service nutzt `--listen :11435` und neuen Config-Pfad

---

## [2.36.0] - 2026-02-18 ⚡ Speed-Kalibrierung für Multi-GPU llama.cpp

### Added

- **Speed-Kalibrierung für Multi-GPU-Setups** - Dreiphasiger Algorithmus optimiert automatisch die GPU-Lastverteilung für maximale Inferenz-Geschwindigkeit
  - **Phase 1** (GPU-only): Native Kontext-Kalibrierung mit `ngl=99`, Binary Search auf `-c`
  - **Phase 2** (Speed-Variante): Bei Multi-GPU-Setup → Binary Search auf `--tensor-split N:1` bei 32K Kontext (CUDA_DEVICE_ORDER=FASTEST_FIRST)
    - Findet maximale Tensor-Split-Ratio: GPU0 bekommt N Teile, GPU1 bekommt 1 Teil
    - Aggressivere GPU-Lastverteilung → höherer Durchsatz (z.B. 11:1 bei 72GB Dual-GPU)
    - Erstellt separaten `model_id-speed` YAML-Eintrag in llama-swap Config
  - **Phase 3** (Hybrid-Fallback): Wenn Phase 1 < 16K Kontext → Hybrid-Modus (NGL-Reduzierung)
  - `speed_split`-Wert in `data/model_vram_cache.json` gespeichert
- **Ctx/Speed-Schalter in der UI** - Toggle zwischen zwei vorkalibrierten Modell-Varianten
  - Erscheint bei AIfred, Sokrates und Salomo (nur bei Modellen mit kalibrierter Speed-Variante)
  - **Ctx** (grün): Maximaler Kontext, ausgewogene GPU-Lastverteilung
  - **⚡ Speed** (orange): 32K Kontext, aggressive GPU-Lastverteilung (schneller)
  - Mit Tooltip (i18n, DE/EN)
- **„(wie AIfred-LLM)" als wählbare erste Option** in Sokrates- und Salomo-Dropdowns
  - Intern als Leerstring gespeichert (verwendet dasselbe Modell wie AIfred)
  - Vollständig i18n-fähig (DE: „(wie AIfred-LLM)", EN: „(same as AIfred-LLM)")

### Fixed

- **Prozess-Leak in `_start_and_verify`** - Bei abgebrochenem Kalibrierungs-Generator (z.B. Doppelklick auf Kalibrieren) wurde der llama-server-Prozess nicht beendet
  - `except BaseException: _kill_process(process); raise` fängt `GeneratorExit` und `CancelledError` ab
- **`has_speed_variant` beim Neustart nicht gesetzt** - Nach Neustart von AIfred wurde der Speed-Toggle nicht angezeigt, obwohl die Kalibrierung erfolgreich war
  - Startup-Block liest jetzt `speed_split` aus Cache und setzt `{agent}_has_speed_variant` korrekt

### Changed

- **Phase-Benennung in der Kalibrierung** - Phase-Nummerierung logisch umstrukturiert:
  - Phase 1 (GPU-only, Basis) → Phase 2 (Speed-Optimierung, Erfolgspfad) → Phase 3 (Hybrid-Fallback)
  - Vorher: Phase 2 = Hybrid-Fallback, Phase 3 = Speed — was den Kontrollfluss verschleiert hat

---

## [2.35.0] - 2026-02-18 🐛 Backend-Wechsel & Kalibrierungs-Fixes

### Fixed

- **llama-swap Stop/Start beim Backend-Wechsel** - `systemctl --user` schlug im Kontext des AIfred System-Service (User=mp) lautlos fehl, weil `XDG_RUNTIME_DIR` und `DBUS_SESSION_BUS_ADDRESS` fehlten
  - `_cleanup_old_backend()`: llama-swap wird beim Wechsel weg von llamacpp jetzt korrekt gestoppt
  - `initialize_backend()`: Auto-Start von llama-swap beim Wechsel zu llamacpp jetzt korrekt
  - Beide Stellen verwenden jetzt `Path.exists()` zur Service-Erkennung (statt `systemctl cat`) und setzen die D-Bus Session-Env explizit — konsistent mit dem bestehenden Kalibrierungs-Code
- **Doppelte Kalibrierungseinträge im VRAM-Cache** - `save_ollama_calibration()` hängte bei jeder Neukalibrierung einen weiteren Eintrag an statt den vorhandenen zu überschreiben
  - Für denselben RoPE-Faktor wird jetzt der bestehende Eintrag ersetzt
  - Betraf 20 Modelle im Cache (je 2 Duplikate) — alle bereinigt
  - Kritisch bei `gpt-oss:120b`: Alter Eintrag hatte `is_hybrid: true` mit 41.529 ctx, neuer hat `is_hybrid: false` mit 262.144 ctx — Code las fälschlicherweise den alten, was zu unnötigem Modell-Reload und Session-Titel-Timeout führte
- **`is_hybrid` Flag für qwen3-next:80b** - Nach Hardware-Upgrade passt das Modell komplett in VRAM — Cache-Eintrag manuell auf `is_hybrid: false` korrigiert

## [2.34.0] - 2026-02-17 🔧 llama.cpp Hybrid-Kalibrierung (NGL + Context)

### Added

- **Hybrid-Kalibrierung für übergroße Modelle** - Zweiphasiger Algorithmus findet den Sweet Spot zwischen GPU-Layer-Offloading (`-ngl`) und Kontextgröße (`-c`)
  - **Phase 1** (bestehend): GPU-only mit `ngl=99`, Binary Search auf `-c`
  - **Phase 2** (NEU): Wenn Phase 1 < 16K Context liefert → Hybrid-Modus
    - Reduziert `-ngl` um VRAM für KV-Cache freizumachen
    - Probiert Context-Targets absteigend: native → 128K → 64K → 32K → 16K
    - NGL-Schätzung per VRAM-Formel + empirische Verifikation
    - Binary Search für optimales NGL + Context-Paar
    - RAM+Swap-Monitoring verhindert System-Thrashing
  - Ergebnis: Modelle wie Qwen3-Next-80B (48GB VRAM) bekommen statt 4K Context jetzt 32-64K+
- **`_estimate_ngl_for_context()`** - VRAM-basierte NGL-Schätzung: `ngl = (free_vram - ctx×mb_per_token - safety) / vram_per_layer`
- **`update_llamaswap_ngl()`** - Schreibt optimierten `-ngl` Wert in llama-swap YAML Config
- **`get_llamacpp_calibration_info()`** - Neuer Cache-Getter liefert vollständige Kalibrierungs-Info (ngl, mode, max_context)
- **VRAM-Cache erweitert** - Speichert jetzt `ngl` und `mode` (gpu/hybrid) pro Kalibrierung

### Fixed

- **`get_gguf_layer_count()` Bugfix** - Hardcodierte Architektur-Keys durch generisches `endswith('.block_count')` Pattern ersetzt (funktioniert jetzt mit allen GGUF-Architekturen)

## [2.33.0] - 2026-02-17 🧹 KoboldCPP Backend entfernt

### Removed

- **KoboldCPP Backend komplett entfernt** - Das gesamte KoboldCPP-Backend wurde aus der Codebase entfernt
  - llama.cpp via llama-swap ersetzt KoboldCPP vollständig (bessere Performance, einfachere Architektur)
  - **Gelöschte Dateien:**
    - `aifred/backends/koboldcpp.py` - Backend-Adapter (556 Zeilen)
    - `aifred/lib/koboldcpp_manager.py` - Prozess-Management mit RoPE-Scaling, OOM-Retry, GPU-Config (979 Zeilen)
    - `aifred/lib/koboldcpp_utils.py` - Error-Parsing Utilities (156 Zeilen)
    - `scripts/install_koboldcpp.sh` - Installations-Script (206 Zeilen)
  - **Bereinigt in 24 Dateien:**
    - `state.py`: 8 State-Variablen, 6 Methoden (~380 Zeilen), ~15 elif-Branches entfernt
    - `aifred.py`: UI-Elemente (Auto-Restart, Spinner, Backend-Dropdown-Eintrag)
    - `config.py`: Alle `KOBOLDCPP_*` Konstanten (RoPE, QuantKV, Inactivity, Safety Margins)
    - `backends/__init__.py`: Import, Registry-Eintrag, `__all__`
    - 14 Library-Dateien: Tote Code-Branches, Kommentare, Docstrings
    - READMEs, TODO, CLAUDE.md, systemd-Service, Install-Script
  - **Gesamtbilanz:** -3.052 Zeilen, +75 Zeilen (Kommentar-Updates "KoboldCPP" → "llama.cpp")
  - CHANGELOG-Historie bleibt erhalten (KoboldCPP-Einträge dokumentieren die Entwicklung)

## [2.32.0] - 2026-02-17 ⚡ Performance: Ollama Reload Fix & llama.cpp Thinking Control

### Fixed

- **Ollama num_ctx Mismatch** - Eliminated 2 unnecessary model reloads (~26s wasted) when Automatik = Main LLM
  - Root cause: `num_ctx` was omitted for Automatik calls when same model as Main LLM
  - Ollama uses MODEL DEFAULT (not currently loaded context) when `num_ctx` is omitted
  - This caused Ollama to reload with default context, then reload AGAIN for main inference with calibrated context
  - Fix: Always send `aifred_max_context` as `num_ctx` when Automatik model = Main LLM model
  - Result: Ollama TTFT improved from 14.4s → 1.5s (9.6x faster), Intent from 15.3s → 0.7s (21x faster)
- **Model parameters not reloaded during backend switch** - `supports_thinking`, `max_context`, `is_hybrid`, `rope_factor` now correctly loaded from VRAM cache when switching backends
  - Previously, values from the old backend persisted (e.g., `supports_thinking=True` from llama.cpp carried over to Ollama)
  - This caused unnecessary `think=True` → 400 error → retry cycles on backends that don't support native thinking for the model
  - Fix: Added parameter loading block in `initialize_backend()` slow path for both Ollama and llama.cpp
- **Debug yields now logged to file** - `log_message()` calls added to debug yield statements in `state.py` routing, ensuring debug output appears in both UI console and `aifred_debug.log`
- **5s gap removed** - `get_model_context_limit()` API call replaced with local VRAM cache read, eliminating a blocking HTTP request during model info retrieval

### Added

- **llama.cpp Thinking Control** - Per-request `enable_thinking` support via `chat_template_kwargs` (llama-server PR #13196)
  - Passes `{"enable_thinking": true/false}` to Jinja chat template via `extra_body`
  - Works for both `chat()` and `chat_stream()` methods in `llamacpp.py`
  - Enables/disables `<think>` block generation for Qwen3 models on llama.cpp backend

### Changed

- **Ollama Automatik num_ctx** - Corrected v2.31.0 behavior: now sends explicit `num_ctx` matching the preloaded context instead of omitting it
- **llama.cpp context parity** - Qwen3-30B-A3B calibrated to 222,960 tokens (matching Ollama calibration for same hardware)

### Performance Benchmarks

Qwen3-30B-A3B Q8_0 on 2× Tesla P40 (48 GB VRAM):

| Metric | Ollama (Before v2.32) | Ollama (After v2.32) | llama.cpp |
|--------|:---------------------:|:--------------------:|:---------:|
| Intent Detection | 15.3s | 0.7s | 0.8s |
| TTFT (Time to First Token) | 14.4s | 1.5s | 1.1s |
| Generation Speed | 12.3 tok/s | 27.4 tok/s | 39.3 tok/s |
| Prompt Processing | 877 tok/s | 862 tok/s | 1,116 tok/s |

llama.cpp advantage over Ollama (both optimized): **+43% generation speed**, **+30% prompt processing**, **-27% TTFT**

## [2.31.0] - 2026-02-16 🦙 llama.cpp Calibration & Automatik Context Optimization

### Added

- **llama.cpp VRAM Calibration** - Binary Search calibration for llama.cpp models via direct llama-server testing
  - Stops llama-swap service, starts llama-server with test context on temp port (9999)
  - Binary Search with 512-token precision until max VRAM-fitting context found
  - Results cached in `data/model_vram_cache.json` (unified cache for all backends)
  - Updates llama-swap YAML config with calibrated `-c` value
  - Restarts llama-swap service after calibration
  - New module: `aifred/lib/llamacpp_calibration.py`
- **GGUF Metadata Reader** - Read native context and quantization from GGUF files without loading models
  - Parses GGUF header for `context_length` and quantization level
  - New module: `aifred/lib/gguf_utils.py`
- **LLM-based URL Ranking** - Rank search result URLs by relevance before scraping (Phase 2.5)
  - Automatik-LLM ranks URLs using title/snippet metadata
  - Scrapes most relevant URLs first (top 3 quick / top 7 deep)
  - New module: `aifred/lib/research/url_ranker.py`
- **llama.cpp Backend** - Full backend integration via llama-swap proxy
  - Model discovery from llama-swap YAML config
  - Vision model detection (Qwen3-VL support)
  - Calibrated context display in debug console
  - New config: `LLAMASWAP_CONFIG_PATH`, `LLAMACPP_HEALTH_TIMEOUT`, `LLAMACPP_CALIBRATION_PORT`

### Changed

- **Automatik-LLM Context Optimization** - Optimized context handling for Automatik calls
  - When different model: `num_ctx` set to `AUTOMATIK_LLM_NUM_CTX` (12288, was 4096)
  - When same model: `num_ctx` omitted (intended to keep loaded context, but caused reloads - fixed in v2.32.0)
  - Threaded `automatik_num_ctx` parameter through all 6 Automatik call sites:
    `detect_research_decision()`, `generate_search_queries()`, `build_rag_context()`,
    `perform_agent_research()` → `handle_cache_hit()`, `rank_urls_by_relevance()`
  - Warning shown when effective context < `AUTOMATIK_LLM_NUM_CTX`
- **Backend-aware calibration display** - Debug console shows calibrated context for all backends
  - `format_model_with_ctx()` now checks `get_llamacpp_calibration()` for llama.cpp backend
  - Automatik model now also shows calibrated context (was missing `format_model_with_ctx()`)
  - `context_limits` calculation loops updated for llama.cpp
- **AUTOMATIK_LLM_NUM_CTX increased** from 4096 to 12288 (12K) for better Automatik task reliability
- **Backend dropdown order** - llama.cpp moved to first position (recommended for performance)
- **Data directory consolidation** - All runtime data now in `data/` (settings, sessions, caches, logs)
  - Settings path updated: `data/settings.json` (was `~/.config/aifred/settings.json`)
  - Documentation updated to reflect correct paths

### Removed

- **Legacy vLLM cache migration** - Removed `_migrate_old_vllm_cache()` and `OLD_VLLM_CACHE` from `model_vram_cache.py`
  - Migration from `~/.config/aifred/vllm_context_cache.json` no longer needed
- **Unused `generate_cache_metadata()` function** - Removed from `cache_manager.py` (was never called)
- **Backend dropdown decorations** - Removed `BACKEND_DROPDOWN_ITEMS` and `BACKEND_NON_SELECTABLE` (unused)
- **`~/.config/aifred/` directory** - Legacy data directory deleted (all data lives in `data/`)

## [2.30.0] - 2026-02-16 🔊 TTS Dropdown & Documentation

### Changed

- **TTS UI: Single dropdown replaces toggle + engine dropdown** - "Aus"/"Off" as first option disables TTS, selecting an engine enables it
  - Combined `set_tts_engine_or_off()` handler merges toggle + engine switch logic
  - `tts_engine_or_off` computed var drives dropdown value
  - Two-row layout: Label + AutoPlay + Streaming on top, engine dropdown below
  - XTTS GPU toggle appears next to dropdown when XTTS active
  - Per-engine voice/toggle settings saved on disable, restored on enable
- **TTS i18n: Engine dropdown labels translated per UI language** - Engine names stored as keys ("xtts", "edge", etc.) with translated display labels in DE/EN. `tts_label_to_key()` searches all languages for reliable reverse mapping. Settings migration auto-converts old display-string format.
- **TTS debug logging: show actual agent voices** - `_restore_agent_voices_for_engine()` now logs per-agent voice names (e.g., "Aifred=Deutsch (Katja), Sokrates=Deutsch (Conrad)"). Removed misleading fallback voice transition log from `_switch_tts_voice_for_language()`.
- **Debug console messages: all German → English** - Consistent English debug output for TTS container lifecycle, streaming mode, etc.
- **DashScope Qwen3-TTS: realtime WebSocket → sentence-level streaming** - Better intonation per sentence, same architecture as XTTS/Edge/Piper. WebSocket code commented out (not deleted) with instructions to re-enable.
- **Audio playback: double-buffered → visible widget with blob-URL prefetching** - Single visible `<audio>` widget replaces hidden double-buffer. Next 2 chunks pre-fetched as in-memory blob URLs for near-instant src switching.
- **TTS sentence ordering** - Sentences generated in parallel but pushed to playback queue in sequence order. Prevents out-of-order playback when cloud APIs (DashScope) return faster for later sentences.
- **Mobile-responsive media buttons** - Button texts hidden on mobile, flexible widths, flex-wrap for narrow screens. Drag & drop tooltip moved from separate info icon to Camera/Upload buttons. Audio button icon unified (single mic icon).

### Removed

- **Dead TTS handlers** - `set_tts_engine()` removed (superseded by `set_tts_engine_or_off()`)

### Added

- **README TTS Engine documentation** (EN + DE) - Comparison table of all 6 TTS engines with streaming behavior, quality, latency, resources, and rationale for each engine choice

## [2.29.0] - 2026-02-15 🎤 DashScope Qwen3-TTS Cloud Streaming & Gapless Audio

### Added

- **DashScope Qwen3-TTS als neue TTS-Engine** - Cloud-basiertes Realtime-Streaming via WebSocket
  - 0 GB VRAM - läuft vollständig in der Cloud (DashScope API)
  - WebSocket Realtime-Streaming: Audio wird **während** der LLM-Inferenz generiert und abgespielt
  - Voice Cloning: Geklonte Stimmen für AIfred, Sokrates und Salomo (★-Voices im Dropdown)
  - 22+ Built-in Voices (Cherry, Serena, Ethan, Chelsie, etc.) plus 3 geklonte Stimmen
  - Satzgrenzen-aligniertes Batching: Audio-Chunks werden an natürlichen Sprechpausen geschnitten
  - Konfigurierbarer Volume-Gain (`DASHSCOPE_TTS_GAIN`) für Lautstärke-Anpassung
  - Neue Klasse `DashScopeRealtimeTTS` in `audio_processing.py` mit WebSocket-Lifecycle-Management
  - Separates Voice-Enrollment für Batch- und Realtime-Modelle

- **Nahtlose Audio-Wiedergabe** - Double-buffered HTML5 Gapless Playback für alle TTS-Engines
  - Zwei `<audio>`-Elemente wechseln sich ab: während eines spielt, wird das nächste vorgeladen
  - `preservesPitch: true` für Geschwindigkeitsanpassung ohne Chipmunk-Effekt
  - Entfernt künstliche 300ms Satzpause (war für XTTS/MOSS, im Audio selbst bereits enthalten)
  - Profitiert alle Engines: DashScope (kritisch bei 3s-Schnitten), XTTS, MOSS-TTS, Edge TTS

### Changed

- **TTS-Queue Architektur** - SSE bleibt persistent ab Browser-Session-Start
  - WebSocket-Connect läuft im Background-Thread (blockiert nicht den Reflex Event-Loop)
  - `_finishing`-Flag: Nach LLM-Ende pusht Callback alle 3s-Batches sofort statt auf Satzgrenzen zu warten
  - Module-Level Storage für WebSocket-Instanzen (vermeidet Reflex State Serialization Error mit SSLSocket)
  - Debug-Output in UI-Console für TTS-Aktivität (Init, Finalize)

## [2.28.4] - 2026-02-14 🧹 Centralize ★ Prefix Stripping

### Changed

- **TTS Voice Name Cleanup zentralisiert** - ★-Prefix wird jetzt einmal in `generate_tts()` entfernt statt in jeder Engine einzeln
  - Entfernt: Duplizierter Strip-Code in `generate_speech_xtts()` und `generate_speech_moss()`
  - Neue Engines müssen sich nicht mehr um UI-Prefixe kümmern

## [2.28.3] - 2026-02-14 🎤 Voice Sorting & Cleanup

### Fixed

- **Custom Voice Sortierung** - ★-Stimmen (AIfred, Sokrates, Salomo) erscheinen jetzt ganz oben im TTS-Dropdown
  - Vorher: Alphabetisch sortiert → ★-Voices am Ende (Unicode-Sortierung)
  - Nachher: ★ Custom Voices zuerst, dann Built-in Voices alphabetisch
  - Neue Hilfsfunktion `sort_voices_custom_first()` in `config.py`

### Removed

- **F5-TTS Docker Container** - Entfernt wegen schlechter Qualität (Gestammel, unverständlich)
- **MOSS-TTS-Realtime Docker-Dateien** - Museum-Code endgültig gelöscht (war bereits aus AIfred entfernt)

### Tested (nicht integriert)

- **Qwen3-TTS** evaluiert als Streaming-TTS-Kandidat
  - Funktioniert mit Voice Cloning (bfloat16), 24kHz, ~7s pro Satz
  - float16 produziert Müll (zu kleiner Exponent-Bereich)
  - Tesla P40 (Compute 6.1): Kein bfloat16 → float32 nötig (~10 GB VRAM)
  - Offizielles `qwen-tts` Package unterstützt kein Streaming
  - Streaming nur über vLLM-Omni möglich → Evaluierung wenn RTX 8000 verfügbar
  - Container nicht beibehalten (kein Mehrwert gegenüber MOSS-TTS ohne Streaming)

## [2.28.2] - 2026-02-12 🗑️ MOSS-TTS-Realtime Removal

### Removed

- **MOSS-TTS-Realtime** - Vollständige Entfernung aus AIfred-Code aufgrund unzureichender Performance
  - Probleme: 24GB VRAM-Verbrauch (gesamte RTX 3090 Ti), schlechte Latenz, übersprungene/vertauschte Sätze
  - Qualität war schlechter als XTTS und MOSS-TTS (Batch)
  - Nicht echtzeitfähig trotz "Realtime" im Namen
  - Docker-Container und Code bleiben als Museum-Code in `docker/moss-tts-realtime/` erhalten
- Alle MOSS-TTS-Realtime Container-Management-Funktionen aus `process_utils.py`
- Engine-Routing-Logik für Realtime-Variante aus `audio_processing.py` und `state.py`

### Changed

- **Dynamische TTS-Engine-Liste** - Kein Hardcoding mehr in `aifred.py`
  - Neue `@rx.var tts_engines()` Property in `state.py` nutzt `config.TTS_ENGINES`
  - Erleichtert zukünftige TTS-Engine-Ergänzungen
- **Alphabetische Voice-Sortierung** - Alle TTS-Engine Voice-Listen werden alphabetisch sortiert
  - Betrifft XTTS, MOSS-TTS, Piper, eSpeak und Edge TTS
  - Verbessert Übersichtlichkeit in Voice-Dropdowns

### Note

- **MOSS-TTS (Batch)** bleibt voll funktionsfähig für hochqualitative Offline-Audiogenerierung

---

## [2.28.1] - 2026-02-12 🔧 ChromaDB Healthcheck & MOSS-TTS P40 Fix

### Fixed

- **ChromaDB Healthcheck kaputt** - Container war seit Start als `unhealthy` markiert (FailingStreak: 7.698!)
  - `curl` existiert nicht im ChromaDB Docker-Image
  - Healthcheck nutzte deprecated `/api/v1/heartbeat`
  - Fix: Bash TCP-Check (`/dev/tcp/localhost/8000`) statt curl
- **MOSS-TTS transformers 5.x Kompatibilitaet** - `DynamicCache` erwartet `num_hidden_layers` auf Decoder-Config
  - `MossTTSDelayConfig` hat nur `local_num_layers` (4), nicht die Language-Model Layers (28)
  - Patch liest `num_hidden_layers` aus Qwen3 Sub-Config

### Changed

- **docker-compose.yml** - Veraltetes `version: '3.8'` entfernt (Docker Compose V2 braucht das nicht mehr)

---

## [2.28.0] - 2026-02-12 🔊 MOSS-TTS Voice Cloning & Bug Fixes

### Added

- **MOSS-TTS Voice Cloning** - State-of-the-Art Zero-Shot Voice Cloning (1.7B, 20 Sprachen, BF16)
  - Docker-Container (`docker/moss-tts/`) mit Flask/Gunicorn API (Port 5055)
  - Zero-Shot: Referenz-Audio reicht, keine Transkription noetig
  - Hervorragende Sprachqualitaet (EN SIM 73.42%, ZH SIM 78.82%)
  - Smart Device Selection (GPU/CPU basierend auf VRAM)
  - Auto-Shutdown nach Inaktivitaet (KEEP_ALIVE)
  - Web-UI zum Testen auf Port 5055
- **MOSS-TTS Container-Management** - Automatischer Start/Stop wie XTTS
- **MOSS-TTS VRAM-Reservation** - ~11.5 GB VRAM-Reservation im Context-Manager
  - Neues Device-Tracking (`moss_tts_device` State-Variable)
  - `context_utils.py` und `context_manager.py` beruecksichtigen MOSS-TTS GPU-Nutzung

### Fixed

- **Login-Dialog**: Blockiert jetzt UI bis zur Authentifizierung (Default `login_dialog_open=True`)
  - Behebt Race Condition bei `rx.call_script()` Callback nach Server-Restart
- **TTS Engine-Wechsel UX**: `yield` fuer sofortiges UI-Feedback, No-Op Guard gegen doppelten `on_change`
- **TTS Voice Logging**: Nur noch bei tatsaechlicher Aenderung (kein "Katja -> Katja" mehr)
- **SSE TTS Streaming**: Race Condition bei Reconnect gefixt (Identity-Check im `finally`-Block)
- **MOSS-TTS VRAM Bug**: `context_utils.py` behandelte MOSS-TTS faelschlicherweise als "No VRAM impact"

### Changed

- **`ensure_moss_ready()`** gibt jetzt 3-Tuple `(success, msg, device)` zurueck
- **TTS Engine Dropdown** aktualisiert sich sofort beim Wechsel (vor Container-Operationen)

### Known Limitations

- **MOSS-TTS nicht fuer Streaming geeignet**: ~18-22s pro Satz (vs. ~1-2s bei XTTS)
- **Hoher VRAM-Verbrauch**: ~11.5 GB in BF16 (bestaetigt durch MOSS-Entwickler: 14-15 GB erwartet)
- Empfohlen fuer hochqualitative Offline-Audiogenerierung

---

## [2.27.7] - 2026-02-09 🔊 XTTS Voice Cloning & UI Polish

### Added

- **Salomo Voice Clone** - Custom XTTS voice from audiobook reference audio
- **Custom Voices in Fallback** - ★ AIfred, ★ Salomo, ★ Sokrates in XTTS_VOICES_FALLBACK
- **GPU Toggle Tooltip** - Hover-Hinweis "Container-Neustart dauert einige Sekunden"

### Changed

- **GPU Toggle invertiert** - ON = GPU (schneller), OFF = CPU (langsamer)
- **GPU Toggle sofort reaktiv** - yield-basiertes UI-Feedback, Toggle flippt sofort
- **Klarere Debug-Meldungen** - "XTTS Container neu gestartet (Modell lädt...)" statt irreführendem "switched to mode"

### Fixed

- **CODE-OVERRIDE Research-Pfad** - Nutzt jetzt `generate_search_queries` statt `detect_research_decision`, verhindert falsche `web=false` bei expliziten Keywords
- **Research Decision Prompt** - Neue "Kritische Regel 1" für explizite Research-Keywords (recherchiere, google, etc.)
- **Salomo Voice Echo** - Embeddings neu generiert, behebt Silben-Wiederholung bei Streaming TTS

---

## [2.27.6] - 2026-01-27 ⚖️ Tribunal Mode: Adversarial Debate System

### Added

- **Tribunal-specific Prompts** - Separate prompts for true adversarial debate:
  - `prompts/de/sokrates/tribunal.txt` - Sokrates as prosecutor, not coach
  - `prompts/de/aifred/defense.txt` - AIfred can choose [VERTEIDIGUNG] or [ÜBERARBEITUNG]
  - `prompts/en/sokrates/tribunal.txt` - English version
  - `prompts/en/aifred/defense.txt` - English version

- **Anti-Repetition Rule** for Tribunal mode:
  - Sokrates must bring NEW arguments in Round 2+
  - No recycling of previous critiques
  - Forces deeper exploration of counterarguments

- **New Loader Functions** ([prompt_loader.py](aifred/lib/prompt_loader.py)):
  - `get_sokrates_tribunal_prompt()` - Adversarial prosecutor prompt
  - `get_aifred_defense_prompt()` - Defense/Revision choice prompt

### Changed

- **Tribunal vs Auto-Consensus now truly different**:
  - Auto-Consensus: Sokrates as coach, AIfred must acknowledge critique
  - Tribunal: Sokrates as opponent, AIfred can defend or revise
  - Salomo judges at the end (no [LGTM] voting in Tribunal)

- **Tribunal Workflow** ([multi_agent.py](aifred/lib/multi_agent.py)):
  - Uses `sokrates/tribunal` instead of `sokrates/critic`
  - Uses `aifred/defense` instead of `aifred/refinement`
  - AIfred chooses `[VERTEIDIGUNG]` (defend) or `[ÜBERARBEITUNG]` (revise)

### Impact

- **More balanced debates**: AIfred no longer structurally loses every Tribunal
- **Higher quality discourse**: Anti-repetition forces new perspectives each round
- **Clearer role separation**: Coach mode vs. Adversary mode now distinct

---

## [2.27.5] - 2026-01-24 🚀 XTTS Eager Loading & Startup-Kontrolle

### Added

- **XTTS Eager Loading** ([docker/xtts/server.py](docker/xtts/server.py)):
  - `XTTS_EAGER_LOAD` environment variable - Model lädt beim Container-Start
  - Kein Lazy-Loading mehr - Model ist sofort bereit nach Container-Start
  - Health-Endpoint `/health` zeigt `model_loaded: true` erst wenn fertig

- **XTTS Startup in AIfred** ([aifred/state.py](aifred/state.py)):
  - Bei TTS=ON + Engine=XTTS: Container startet VOR Ollama-Model-Discovery
  - Synchrones Polling auf `model_loaded: true` (max 60s)
  - XTTS reserviert VRAM bevor Ollama lädt

- **start_xtts_container()** ([aifred/lib/process_utils.py](aifred/lib/process_utils.py)):
  - Neue Funktion zum Starten des XTTS-Containers

### Changed

- **Docker Restart-Policy** ([docker/xtts/docker-compose.yml](docker/xtts/docker-compose.yml)):
  - `restart: "no"` statt `unless-stopped`
  - AIfred kontrolliert Container-Lifecycle vollständig
  - Kein Auto-Start bei System-Reboot

---

## [2.27.4] - 2026-01-24 🔊 XTTS CPU-Mode & VRAM Management

### Added

- **OLLAMA_NUM_PARALLEL=1 Optimization Guide** ([README.md](README.md), [README.de.md](README.de.md)):
  - Documented critical performance optimization for single-user Ollama setups
  - Default PARALLEL=2 doubles KV-cache allocation for unused parallel slot
  - Setting PARALLEL=1 doubles available context (111K → 222K for 30B models)
  - Step-by-step systemd override instructions included

- **AIfred Typo Correction** ([personality.txt](prompts/de/aifred/personality.txt), [personality.txt](prompts/en/aifred/personality.txt)):
  - AIfred now corrects user spelling errors in responses instead of copying them
  - Examples: "Mamellade" → "Marmelade", "Gurken Sandwich" → "Gurkensandwich"
  - Instruction added to both German and English personality prompts

- **XTTS CPU-Mode Toggle** ([aifred.py](aifred/aifred.py), [state.py](aifred/state.py)):
  - New GPU/CPU toggle in TTS settings (only visible when XTTS selected)
  - CPU mode: Slower TTS but saves ~2 GB GPU VRAM for larger LLM context
  - GPU mode (default): Faster TTS, VRAM reserved for XTTS
  - Toggle automatically restarts XTTS Docker container with new setting

- **XTTS VRAM Reservation** ([context_manager.py](aifred/lib/context_manager.py), [config.py](aifred/lib/config.py)):
  - When XTTS runs on GPU: ~2.1 GB VRAM reserved (14,000 tokens)
  - Automatic context window reduction to prevent GPU memory overflow
  - No reservation when CPU mode enabled or TTS disabled

- **TTS Container Management** ([process_utils.py](aifred/lib/process_utils.py)):
  - TTS toggle now starts/stops XTTS Docker container
  - TTS OFF: Container stopped, VRAM fully freed
  - TTS ON: Container started with current CPU/GPU setting
  - New functions: `restart_docker_container()`, `set_xtts_cpu_mode()`, `stop_xtts_container()`

### Changed

- **TTS UI Improvements** ([aifred.py](aifred/aifred.py)):
  - Removed XTTS unload button (replaced by CPU-mode toggle)
  - All TTS toggle labels now in consistent gold color (#d4a14a)
  - Improved toggle grouping for better visual clarity
  - Debug console height increased by 80px

- **Docker Compose** ([docker/xtts/docker-compose.yml](docker/xtts/docker-compose.yml)):
  - `XTTS_FORCE_CPU` now read from `.env` file for runtime configuration
  - Supports dynamic GPU/CPU switching without manual file edits

### Fixed

- **XTTS VRAM Reservation Not Applied** ([context_utils.py](aifred/lib/research/context_utils.py), [multi_agent.py](aifred/lib/multi_agent.py)):
  - XTTS GPU VRAM reservation (~14K tokens) was never subtracted from context window
  - Moved XTTS logic to `get_agent_num_ctx()` - the single source of truth for num_ctx
  - Sokrates/Salomo agents now also use centralized `get_agent_num_ctx()` function
  - Added comprehensive TTS debug output for all TTS engines (XTTS GPU/CPU, Edge TTS, etc.)

---

## [2.27.3] - 2026-01-22 🔊 TTS Regeneration & Multi-Device Support

### Added

- **TTS Regeneration Buttons** ([aifred.py](aifred/aifred.py), [state.py](aifred/state.py), [i18n.py](aifred/lib/i18n.py), [custom.js](assets/custom.js)):
  - Per-Bubble Regenerate Button (🔄) next to speaker icon for individual audio regeneration
  - Global "Alles neu generieren" button to regenerate all bubble audio at once
  - Complete bubble regeneration (not concatenated sentences) for better audio quality
  - Automatic button visibility management based on audio existence

- **Multi-Device TTS Support** ([custom.js](assets/custom.js)):
  - Page Visibility API (`document.hidden`) prevents simultaneous audio playback on multiple devices
  - Only visible/focused browser tab plays TTS audio automatically
  - Other tabs/devices receive audio URLs but don't autoplay

### Changed

- **Touch-Friendly Audio UI** ([aifred.py](aifred/aifred.py)):
  - Increased audio button size: icons 14px → 18px, padding 2px 4px → 6px 8px
  - Better mobile/tablet usability for audio controls

- **SSE Reconnect on Session Refresh** ([state.py](aifred/state.py)):
  - Session refresh button now reconnects TTS SSE stream automatically
  - Elegant "Last Writer Wins" device switching without F5 reload

### Fixed

- **XTTS Ordinal Number Splitting** ([docker/xtts/server.py](docker/xtts/server.py)):
  - Date formats like "Donnerstag, den 22. Januar" no longer split after ordinal numbers
  - Detects 1-3 digit numbers before periods followed by uppercase words and keeps them together
  - Prevents audio cutoff in the middle of dates and structured text

- **XTTS Colon Processing** ([docker/xtts/server.py](docker/xtts/server.py)):
  - Re-enabled colon-to-period replacement for better speech pauses in flowing text
  - Protects time formats (19:20) and URLs (https://) from replacement via negative lookahead/lookbehind
  - Regex: `(?<!\d):(?!\d|//)` ensures colons between digits remain unchanged

---

## [2.27.2] - 2026-01-22 🔧 Multi-Agent Prompt Fixes & Export Improvements

### Fixed

- **Multi-Agent Round Number Injection** ([prompts/de/aifred/refinement.txt](prompts/de/aifred/refinement.txt), [prompts/en/aifred/refinement.txt](prompts/en/aifred/refinement.txt), [prompt_loader.py](aifred/lib/prompt_loader.py)):
  - AIfred refinement prompt now receives `{round_num}` like Sokrates and Salomo
  - Ensures AIfred knows which round of debate it's responding to

- **Sokrates R1 Salomo Reference Bug** ([prompts/de/sokrates/critic.txt](prompts/de/sokrates/critic.txt), [prompts/en/sokrates/critic.txt](prompts/en/sokrates/critic.txt)):
  - Added explicit warning: "Salomo has NOT spoken yet - do NOT reference him!"
  - Prevents Sokrates from referencing Salomo in Round 1 before Salomo has responded

- **Multi-Agent Label Duplication** ([state.py](aifred/state.py)):
  - Fixed "[Critical Review: Critical Review R1]" appearing in message markers
  - Mode prefix now skipped when mode equals multi_agent_mode

- **UI Legacy Label Cleanup** ([aifred.py](aifred/aifred.py)):
  - Removed legacy "ctx" label under Vision context input field

### Changed

- **HTML Export Filenames** ([formatting.py](aifred/lib/formatting.py), [state.py](aifred/state.py)):
  - Export files now use chat title instead of UUID (e.g., `🎩 AIfred - Hund_oder_Katze.html`)
  - HTML `<title>` tag uses session title for better browser tab identification

### Added

- **Showcase Documentation** ([docs/examples/README.md](docs/examples/README.md)):
  - Added "Hund oder Katze" multi-agent debate showcase with analysis
  - Links to full HTML export and markdown analyses (DE/EN)

---

## [2.27.1] - 2026-01-21 🔊 TTS Text Processing & SSE Streaming Fixes

### Changed

- **TTS Text Normalization Architecture** ([audio_processing.py](aifred/lib/audio_processing.py), [docker/xtts/server.py](docker/xtts/server.py)):
  - Klare Trennung der Verantwortlichkeiten zwischen AIfred und XTTS Docker
  - **AIfred** (`clean_text_for_tts`): Content-Filterung (Markdown, Code-Blöcke, Tabellen, `<think>` Tags, HTML, LaTeX)
  - **XTTS Docker** (`normalize_text_for_tts`): XTTS-spezifische Normalisierung (Emojis, Sonderzeichen, Interpunktion)
  - Lach-Emojis (😂🤣😆😄😅😁🙂😊) werden zu "hahaha" konvertiert (klingt natürlich)
  - Andere Emojis werden entfernt (unaussprechbar)
  - Sonderzeichen die "Quirzel"-Sounds verursachen werden gefiltert
  - Doppelpunkte → Punkte (verhindert "rushed speech" in XTTS)

- **TTS SSE Stream Handling** ([api.py](aifred/lib/api.py), [state.py](aifred/state.py), [custom.js](assets/custom.js)):
  - Race-Condition behoben: Bereits generierte Audio-URLs werden sofort beim SSE-Connect gesendet
  - SSE-Stream wird vor TTS-Generierung gestartet (garantiert Browser ist bereit)
  - Auto-Start des TTS-Streams beim Page-Load
  - Periodischer Reconnect-Check alle 5 Sekunden (Tab-Sleep, Netzwerk-Unterbrechungen)

### Fixed

- **TTS Text Cleaning** ([audio_processing.py](aifred/lib/audio_processing.py)):
  - HTML-Tags (`<br>`, `<span>`, etc.) werden jetzt korrekt entfernt
  - Markdown-Links `[text](url)` → behält "text", entfernt URL
  - Markdown-Bilder `![alt](url)` → komplett entfernt
  - Blockquotes (`> text`) → Text bleibt, Marker wird entfernt
  - Listen-Marker (`- `, `* `, `1. `) → entfernt, Text bleibt
  - Tabellen-Trennzeilen (`|---|---|`) werden gefiltert

- **XTTS Hallucination Prevention** ([docker/xtts/server.py](docker/xtts/server.py)):
  - Zeilen ohne Satzzeichen bekommen automatisch einen Punkt
  - Verhindert XTTS-Halluzinationen bei Überschriften, Listen, etc.

## [2.27.0] - 2026-01-20 🎤 XTTS v2 Voice Cloning & Multi-Agent TTS Queue

### Added

- **XTTS v2 Voice Cloning Integration** ([docker/xtts/](docker/xtts/)):
  - Neuer Docker-Service für Coqui XTTS v2 mit Voice Cloning
  - 58 eingebaute Stimmen + eigene Stimmklonung aus 6-10s Referenz-Audio
  - Mehrsprachige Unterstützung (16 Sprachen) mit automatischem Code-Switching (DE/EN gemischt)
  - Web UI unter `http://localhost:5051` für Tests und Voice Cloning

- **Smart GPU/CPU Device Selection** ([docker/xtts/server.py](docker/xtts/server.py)):
  - Automatische VRAM-Erkennung via `nvidia-smi`
  - GPU-Modus wenn freies VRAM >= Threshold (Standard: 2.0 GB)
  - Automatischer CPU-Fallback bei VRAM-Knappheit (konkurriert nicht mit Ollama)
  - Konfigurierbar via `XTTS_VRAM_THRESHOLD` und `XTTS_FORCE_CPU` Umgebungsvariablen

- **XTTS Status Endpoints** ([docker/xtts/server.py](docker/xtts/server.py)):
  - `/status` - Detaillierte VRAM/Device-Info
  - `/health` - Zeigt aktuelles Device (GPU/CPU)
  - `/voices` - Liste aller verfügbaren Stimmen (custom + builtin)

- **Per-Agent Voice Settings UI** ([aifred.py](aifred/aifred.py), [state.py](aifred/state.py)):
  - Agentenstimmen-Sektion in TTS Settings mit Voice, Pitch und Speed pro Agent
  - AIfred, Sokrates, Salomo können verschiedene Stimmen, Tonhöhen und Geschwindigkeiten haben
  - Per-Engine Speicherung: Stimmen-Einstellungen werden pro TTS-Engine gespeichert
  - Speed wird bei Playback auf Browser-Seite angewendet (data-playback-rate Attribut)
  - Pitch wird via ffmpeg nachbearbeitet (asetrate + aresample)

- **Custom Voice Embeddings** ([docker/xtts/voices/](docker/xtts/voices/)):
  - `aifred.wav` und `sokrates.wav` als Referenz-Audio
  - Automatische Embedding-Generierung beim Container-Start
  - Persistente Speicherung in Docker-Volume

- **TTS Audio Queue für Multi-Agent** ([state.py](aifred/state.py), [custom.js](assets/custom.js)):
  - Sequentielle Wiedergabe von Multi-Agent Responses (AIfred → Sokrates → Salomo)
  - JavaScript Queue mit Version-Tracking für Backend-Sync
  - `clearTtsQueue()` und `skipTtsQueueItem()` Funktionen im Browser
  - MutationObserver für `#tts-queue-data` Element

- **Async TTS Generation** ([state.py](aifred/state.py)):
  - TTS läuft als Hintergrund-Task (`asyncio.create_task`)
  - Nächste LLM-Inferenz kann parallel starten
  - Keine Blockierung mehr durch TTS-Generierung

- **TTS Player Visibility** ([aifred.py](aifred/aifred.py), [state.py](aifred/state.py)):
  - Player erscheint automatisch wenn Audio in Queue oder generiert
  - `tts_player_visible` computed var für UI-Steuerung

### Changed

- **TTS Engine Dropdown** ([aifred.py](aifred/aifred.py)):
  - XTTS v2 als neue TTS-Engine Option hinzugefügt
  - Dynamische Voice-Liste aus XTTS Docker-Service

- **Audio Processing** ([audio_processing.py](aifred/lib/audio_processing.py)):
  - `generate_speech_xtts()` Funktion für XTTS API-Aufrufe
  - Dispatcher unterstützt XTTS Engine

- **Agent Voice Defaults** ([config.py](aifred/lib/config.py), [state.py](aifred/state.py)):
  - Alle Agenten auf Speed 1.0x und Pitch 1.0 normalisiert
  - XTTS Custom Voices mit `★` Prefix (★ AIfred, ★ Sokrates)

### Fixed

- **TTS Audio Playback** ([aifred.py](aifred/aifred.py)):
  - React Hook Order Error behoben (rx.cond → CSS display:none)
  - Audio-Element wird immer gerendert, nur CSS-visibility wechselt

- **TTS Response Time** ([state.py](aifred/state.py)):
  - TTS-Generierung vor Session-Title für schnelleres Audio-Feedback

- **TTS Text Source** ([state.py](aifred/state.py)):
  - TTS verwendet jetzt `llm_history` statt `chat_history` (kein HTML)
  - Agent-Label (`[AIFRED]:`, `[SOKRATES]:`, `[SALOMO]:`) wird vor TTS gestrippt
  - Re-Synthesize erkennt den Agenten und verwendet dessen Stimm-Einstellungen

- **Multi-Agent HTML in TTS** ([audio_processing.py](aifred/lib/audio_processing.py)):
  - `clean_text_for_tts()` vereinfacht - HTML-Stripping entfernt (nicht mehr nötig)

- **XTTS Voice Validation** ([state.py](aifred/state.py)):
  - Ungültige gespeicherte Stimmen werden auf Defaults zurückgesetzt
  - Verhindert Fehler wenn Custom Voice nicht mehr existiert

- **Gender Toggle Styling** ([custom.css](assets/custom.css)):
  - Bessere Sichtbarkeit der ausgewählten Option (heller orange Hintergrund)

### Documentation

- **XTTS README** ([docker/xtts/README.md](docker/xtts/README.md)):
  - Vollständige Dokumentation für XTTS Docker-Service
  - API Endpoints, Voice Cloning, Troubleshooting

## [2.26.0] - 2026-01-19 🎯 Cloud API Vision Support

### Added

- **Cloud API Vision Support** ([conversation_handler.py](aifred/lib/conversation_handler.py), [llm_client.py](aifred/lib/llm_client.py)):
  - Vision-Pipeline funktioniert jetzt mit Cloud APIs (Qwen DashScope, etc.)
  - `qwen-vl-max` und andere Cloud-VL-Modelle nutzbar für OCR
  - ~48 tok/s bei Cloud vs ~22 tok/s lokal - deutlich schneller!

### Fixed

- **Cloud API Backend URL Bug** ([conversation_handler.py](aifred/lib/conversation_handler.py)):
  - Vision-Pipeline setzte fälschlicherweise Ollama-URL wenn `backend_url` leer war
  - Cloud APIs nutzen Provider-Config für URL - darf nicht überschrieben werden
  - Fix: URL-Fallback nur für nicht-Cloud-Backends

- **Provider-Parameter fehlte in Vision-Pipeline** ([llm_client.py](aifred/lib/llm_client.py), [conversation_handler.py](aifred/lib/conversation_handler.py), [state.py](aifred/state.py)):
  - `LLMClient` akzeptiert jetzt `provider` Parameter für Cloud APIs
  - `chat_with_vision_pipeline` reicht Provider durch
  - `_process_single_image_vision` erhält Provider für korrekten API-Aufruf

- **get_vision_model_capabilities für Cloud API** ([conversation_handler.py](aifred/lib/conversation_handler.py)):
  - Ollama-spezifischer `/api/show` Endpoint verursachte 404 bei Cloud APIs
  - Cloud APIs nutzen jetzt sensible Defaults (chat support, 128K context)

## [2.25.1] - 2026-01-19

### Changed

- **Zahlenfelder: Speichern erst bei Blur** ([aifred.py](aifred/aifred.py)):
  - Alle num_ctx Felder (AIfred, Sokrates, Salomo, Vision) und YARN-Factor nutzen jetzt `on_blur` statt `on_change`
  - Werte werden erst übernommen wenn das Feld verlassen wird (Tab, Enter, Klick)
  - Behebt nerviges Überschreiben während des Tippens

### Removed

- **vision_num_predict komplett entfernt** ([state.py](aifred/state.py), [aifred.py](aifred/aifred.py), [conversation_handler.py](aifred/lib/conversation_handler.py)):
  - Ollama ignoriert `num_predict` bei Thinking-Modellen komplett
  - Für OCR würde es die Ausgabe vorzeitig abschneiden
  - UI-Feld, State-Variable, Handler und Settings-Eintrag entfernt
  - Nur `num_ctx` (Context-Window) bleibt erhalten - das funktioniert

### Fixed

- **CSS: Number Input Spinner-Buttons entfernt** ([custom.css](assets/custom.css)):
  - Spinner-Buttons bei Zahlenfeldern in LLM-Parameters ausgeblendet
  - Firefox: `-moz-appearance: textfield`
  - Chrome/Safari/Edge: `::-webkit-outer-spin-button` hidden
  - Kompaktere Darstellung im Accordion

## [2.25.0] - 2026-01-19

### Added

- **Collapsible Thinking Output für Vision-Modelle** ([conversation_handler.py](aifred/lib/conversation_handler.py)):
  - Thinking-Modelle (Qwen3-VL, etc.) zeigen `<think>`-Blöcke jetzt in einklappbaren Sections
  - "🧠 Reasoning" als Titel, standardmäßig eingeklappt
  - Konsistent mit Chat-Thinking-Output

### Changed

- **Vision num_ctx: Calibrated statt Hardcoded** ([conversation_handler.py](aifred/lib/conversation_handler.py), [config.py](aifred/lib/config.py)):
  - Entfernt: `VISION_RESPONSE_RESERVE` (12.500) und `VISION_MINIMUM_CONTEXT` (4.096)
  - Vision-Pipeline nutzt jetzt direkt den kalibrierten `max_context` aus VRAM-Cache
  - Ermöglicht 160K+ Context für MoE-Modelle (statt hardcoded 15K Limit)
  - Kalibrierte Werte sind experimentell gemessen = zuverlässig

- **OCR-Prompts für Multi-Column-Layouts verbessert** ([vision_ocr.txt](prompts/de/vision/vision_ocr.txt), [vision_templateless_ocr.txt](prompts/de/vision/vision_templateless_ocr.txt)):
  - Explizite Anweisungen für Spalten-Reihenfolge (erst links komplett, dann rechts)
  - "VERBOTEN"-Section mit Beispielen was NICHT erlaubt ist (Zusammenfassungen)
  - Tabellen-Format-Beispiel für vollständige Extraktion
  - DE + EN Versionen synchron aktualisiert

- **Vision Prompt-Konsolidierung** ([prompt_loader.py](aifred/lib/prompt_loader.py)):
  - `vision_templateless_default.txt` gelöscht (DE + EN)
  - Logik vereinfacht: OCR-Prompt wird für alle faktischen Anfragen verwendet
  - Weniger Dateien, klarere Struktur

### Fixed

- **Session-Löschung bereinigt Bilder** ([session_storage.py](aifred/lib/session_storage.py), [state.py](aifred/state.py)):
  - Beim Löschen einer Session werden zugehörige Bilder aus `data/images/{session_id}/` entfernt
  - Verhindert Speicher-Akkumulation durch verwaiste Bild-Dateien
  - Session-ID wird jetzt in State getrackt für Image-Cleanup

- **Hot-Reload während Vision-Inferenz** ([aifred-intelligence.service](systemd/aifred-intelligence.service)):
  - `REFLEX_HOT_RELOAD_EXCLUDE_PATHS=data:prompts` verhindert Reloads bei Datei-Änderungen
  - Behebt Abbrüche wenn Bilder in `data/images/` geschrieben werden

## [2.24.3] - 2026-01-19

### Fixed

- **Hybrid-Model Reload-Optimierung** ([ollama.py](aifred/backends/ollama.py)):
  - Bei Multi-Agent-Anfragen mit gleichem Modell wurde das Modell bei jedem Agent-Wechsel neu geladen (~60-70s pro Reload)
  - Neue Logik prüft via `/api/ps` ob das Modell bereits geladen ist, bevor ein Unload ausgelöst wird
  - TTFT-Verbesserung bei Folge-Agents: **~100s → ~30s** (75-85s schneller)
  - Gesamtersparnis bei 5-Agent-Pipeline: **~4 Minuten** pro Anfrage
  - Erster Agent-Call weiterhin ~78s (initiales Laden nötig)

## [2.24.2] - 2026-01-18

### Changed

- **Intent Detection Prompt - Semantic Understanding** ([intent_detection.txt](prompts/en/automatik/intent_detection.txt)):
  - Radikal vereinfacht: 59 → 39 Zeilen (34% kürzer)
  - Entfernt: Alle Beispiele, WRONG EXAMPLES, redundante Format-Hinweise
  - Fokus auf semantische Intention statt Syntax: "Ignore grammar, spelling, or punctuation - focus on semantic intent"
  - Robuster für umgangssprachliche User-Eingaben (schnelles Tippen, fehlende Kommas, Tippfehler)
  - Striktes Output-Schema mit klaren Regeln für Parser-Kompatibilität
  - Verbessert Addressee-Erkennung bei Patterns wie "was hältst du aifred von..." (ohne perfekte Komma-Platzierung)
  - Backup des alten Prompts erstellt: `intent_detection.txt.backup`

## [2.24.1] - 2026-01-18

### Fixed

- **Ollama Hybrid-Model Race Condition** ([ollama.py](aifred/backends/ollama.py), [model_vram_cache.py](aifred/lib/model_vram_cache.py)):
  - Große Hybrid-Modelle (CPU+GPU Offload) verursachten gelegentlich CUDA OOM Fehler
  - Root cause: CUDA-Deallocation ist asynchron, nächstes Modell lud bevor VRAM freigegeben war
  - `preload_model()` erkennt jetzt automatisch Hybrid-Modelle aus Kalibrierungs-Cache
  - Hybrid-Modelle: Explizites Unload + VRAM-Stabilisierungs-Wait (1-3s auf P40 GPUs)
  - VRAM-only Modelle: Weiterhin Ollama LRU (schnell, keine Änderung)
  - Verhindert 500 Errors bei parallelen Requests (AIfred + Sokrates)

## [2.24.0] - 2026-01-17

### Added

- **Web-Quellen Nummerierung** ([formatting.py](aifred/lib/formatting.py)):
  - Quellen im Collapsible haben jetzt Nummern (1., 2., 3.)
  - Passt zu LLM-Referenzen "Quelle 1, Quelle 2" im Antworttext
  - Verbesserte Lesbarkeit und Zuordnung

- **BACKEND_URL Environment-Variable** ([config.py](aifred/lib/config.py)):
  - Neue Konfiguration für statische Dateien (HTML-Preview, Bilder)
  - Ermöglicht Entwicklung ohne NGINX-Proxy (WSL, lokale Dev-Umgebung)
  - Mit NGINX: Leer lassen (NGINX routet `/_upload/` ans Backend)

### Changed

- **Web-Quellen Sortierung nur noch per LLM-Relevanz** ([context_builder.py](aifred/lib/tools/context_builder.py)):
  - Legacy `prioritize_source()` Heuristik entfernt
  - Sortierung erfolgt jetzt ausschließlich nach `rank_index` (LLM-Ranking)
  - Einfacherer, konsistenter Code

- **Prompts: Keine URL-Liste am Ende** ([system_rag.txt](prompts/de/aifred/system_rag.txt)):
  - LLM gibt keine redundante Quellenliste mehr aus
  - URLs sind bereits im Web-Quellen Collapsible sichtbar
  - Betrifft DE + EN Prompts für RAG und Cache-Hit

- **HTML-Export Verbesserungen** ([state.py](aifred/state.py)):
  - URL-Farben auf Cyan-Türkis angepasst (`#56d4dd`)
  - max-width von 900px auf 1000px erhöht
  - Konsistentes Design mit der Haupt-UI

### Fixed

- **HTML-Export: Doppeltes Collapsible** ([state.py](aifred/state.py)):
  - Export zeigte zwei Web-Quellen Collapsibles (aus Content + aus Metadata)
  - Jetzt wird geprüft ob Content bereits ein Collapsible enthält
  - Verhindert Duplikate im Export

- **HTML-Preview 404 in Dev-Umgebung** ([formatting.py](aifred/lib/formatting.py)):
  - StaticFiles sind auf Backend-Port gemountet
  - Mit `BACKEND_URL` werden absolute URLs generiert
  - Funktioniert jetzt ohne NGINX-Proxy

## [2.23.0] - 2026-01-17

### Added

- **Timer-Utility Migration** ([timer.py](aifred/lib/timer.py)):
  - Neue zentrale `Timer`-Klasse mit `time.monotonic()` für zuverlässige Zeitmessung
  - Ersetzt fehleranfällige `time.time()` Start/Stop Muster im gesamten Codebase
  - Monotone Uhr ist immun gegen Systemzeit-Änderungen (NTP-Sync, Zeitumstellung)
  - Methoden: `reset()`, `elapsed()` - einfaches Interface, keine Fehlerquellen

- **Scrollbar Gutter Stability** ([aifred.py](aifred/aifred.py)):
  - Session-Liste verwendet `scrollbarGutter: stable` CSS-Property
  - Verhindert UI-"Springen" wenn Scrollbar erscheint/verschwindet beim Löschen von Sessions
  - Icons und Texte bleiben jetzt positionsstabil

### Changed

- **Per-Agent Reasoning Toggles steuern beide Systeme** ([state.py](aifred/state.py), [multi_agent.py](aifred/lib/multi_agent.py)):
  - Die Per-Agent Reasoning-Toggles (`aifred_reasoning`, `sokrates_reasoning`, `salomo_reasoning`) kontrollieren jetzt BEIDE:
    1. **Reasoning Prompt**: Chain-of-Thought Anweisungen im System-Prompt (funktioniert für alle Modelle)
    2. **enable_thinking Flag**: Spezifisches Flag für Thinking-Modelle (Qwen3, QwQ, etc.)
  - Design-Entscheidung: Instruct-Modelle (ohne native `<think>`-Tags) profitieren vom CoT-Prompt
  - Thinking-Modelle erhalten beides: CoT-Prompt + technisches Flag für `<think>`-Block-Generierung
  - 5 Stellen in `state.py` und 5 Stellen in `multi_agent.py` aktualisiert

- **Globaler "Reasoning Mode" Toggle entfernt** ([aifred.py](aifred/aifred.py)):
  - Der globale "Thinking Mode" Toggle wurde aus dem UI entfernt
  - Reasoning wird jetzt ausschließlich per-Agent gesteuert in den LLM-Einstellungen
  - Verhindert Verwirrung zwischen globalem und per-Agent Toggle

### Fixed

- **"Chat cleared" Meldung bei Startup/Logout** ([state.py](aifred/state.py)):
  - `new_session()` und `do_logout()` zeigen nicht mehr irreführende "🗑️ Chat cleared" Debug-Meldung
  - Neuer `silent=True` Parameter für `_clear_chat_internal()` (interne Methode)
  - `clear_chat()` bleibt als UI-Event-Handler ohne Parameter (Reflex-Anforderung)

### Design Notes

**Per-Agent Reasoning Design-Entscheidung:**

Die Reasoning-Toggles pro Agent steuern jetzt einheitlich beide Mechanismen:

| Toggle Status | Reasoning Prompt | enable_thinking | Effekt |
|---------------|------------------|-----------------|--------|
| **ON** | ✅ Injiziert | ✅ True | Voller CoT mit `<think>`-Blocks (Thinking-Modelle) |
| **ON** | ✅ Injiziert | ✅ True | CoT-Anweisungen befolgt (Instruct-Modelle, kein `<think>`) |
| **OFF** | ❌ Nicht injiziert | ❌ False | Direkte Antworten, kein Reasoning |

Diese Vereinheitlichung ermöglicht konsistentes Verhalten unabhängig vom Modelltyp.

---

## [2.22.0] - 2026-01-16

### Added

- **Bildrotation im Crop-Dialog** ([state.py](aifred/state.py), [aifred.py](aifred/aifred.py)):
  - Zwei neue Buttons: 90° links drehen, 90° rechts drehen
  - Behebt Problem mit PNG-Fotos von Handy-Kameras (kein EXIF-Support)
  - Thumbnail wird nach Rotation automatisch aktualisiert (Cache-Busting)

- **Session-Titel für Vision-Only Uploads** ([state.py](aifred/state.py)):
  - Bilder ohne User-Text generieren jetzt auch einen Session-Titel
  - Verwendet "📷 [Bildanalyse]" als Platzhalter für Titel-Generierung

### Fixed

- **Echtzeit Debug-Feedback bei Titel-Generierung** ([state.py](aifred/state.py)):
  - `_generate_session_title()` zu async Generator konvertiert
  - "🏷️ Generating session title..." erscheint sofort, nicht erst nach Fertigstellung
  - Beide Call-Sites aktualisiert (regulärer Flow und Vision-Only)

---

## [2.21.0] - 2026-01-16

### Fixed

- **EXIF-Rotation für Handy-Fotos** ([vision_utils.py](aifred/lib/vision_utils.py)):
  - Querformat-Fotos vom Handy werden jetzt korrekt gedreht angezeigt
  - Bug: Nach `ImageOps.exif_transpose()` waren EXIF-Daten leer → falscher Check
  - Fix: Prüft jetzt ob sich Bildgröße geändert hat (100x200 → 200x100 = rotiert)
  - Behebt: Bilder erschienen um 90° gedreht in UI und Vision-LLM Analyse

- **Doppelte User-Message im Vision-Flow** ([state.py](aifred/state.py)):
  - User-Anfrage erschien zweimal in der Chat-History bei Bild+Text
  - Entfernt: Redundantes `chat_history.append()` in Phase 2 (AIfred nach Vision)
  - User-Message wird bereits am Anfang von `send_message()` hinzugefügt
  - Betrifft nur Vision+Text Flow, andere Flows unverändert

---

## [2.20.0] - 2026-01-16

### Changed

- **Rename: device_id → session_id** ([state.py](aifred/state.py), [aifred.py](aifred/aifred.py), [session_storage.py](aifred/lib/session_storage.py), [api.py](aifred/lib/api.py), [browser_storage.py](aifred/lib/browser_storage.py)):
  - Durchgängige Umbenennung von `device_id` zu `session_id` für bessere Semantik
  - Alte Session-Dateien bleiben kompatibel (Feld wird beim Laden gemappt)
  - Cookie-Name bleibt `aifred_session_id` (war bereits korrekt)

- **API URL Konfiguration vereinfacht** ([rxconfig.py](rxconfig.py)):
  - Entfernt: `_get_local_ip()` Funktion und `AIFRED_API_URL` Umgebungsvariable
  - Neu: Feste `api_url="http://0.0.0.0:8002"` - Reflex's Frontend-JS ersetzt `0.0.0.0` automatisch mit `window.location.hostname`
  - Vorteil: Gleiche Konfiguration funktioniert auf allen Zugangswegen (Port 8443, 443, lokal)

### Fixed

- **Session-Wechsel überschrieb Daten** ([state.py](aifred/state.py)):
  - Entfernt: Unnötiger `_save_current_session()` Aufruf in `switch_session()` und `new_session()`
  - Problem: Wenn Tab A leer war und Session wechselte, wurde die Session-Datei mit leeren Daten überschrieben
  - Sessions werden bereits nach jeder Inferenz automatisch gespeichert - kein zusätzliches Speichern beim Wechsel nötig

- **Session-Reload bei leerer History** ([state.py](aifred/state.py)):
  - `switch_session()` lädt Session neu, wenn `session_id` gleich aber `chat_history` leer ist
  - Behebt: Klick auf aktuelle Session in der Liste hat nichts getan, obwohl History nicht geladen war

- **Multi-Port CORS für Image-Upload** (nginx):
  - nginx `sub_filter` schreibt `env.json` URLs basierend auf eingehendem Port um
  - Port 8443 → `https://narnia.spdns.de:8443`, Port 443 → `https://narnia.spdns.de`
  - Behebt: Image-Paste auf Port 8443 scheiterte wegen CORS (Reflex JS entfernt Port bei HTTPS)

---

## [2.19.3] - 2026-01-16

### Added

- **Session List Refresh Button** ([aifred.py](aifred/aifred.py)):
  - Neuer Refresh-Button neben "Neuer Chat" in der Session-Liste
  - Ermöglicht manuelles Aktualisieren der Session-Liste ohne App-Neustart
  - Rötliches Styling zur visuellen Unterscheidung vom New-Chat-Button

- **Image Upload Feedback** ([state.py](aifred/state.py)):
  - Debug-Nachricht beim Start des Bild-Uploads ("📤 Uploading X image(s) from source...")
  - Verbesserte Nutzer-Feedback bei langsamen Mobilfunk-Verbindungen

### Changed

- **Vision Response Reserve konfigurierbar** ([config.py](aifred/lib/config.py), [conversation_handler.py](aifred/lib/conversation_handler.py)):
  - Neue Konstante `VISION_RESPONSE_RESERVE = 12500` (vorher hardcoded 8192)
  - Größerer Token-Puffer erlaubt längere OCR-Ausgaben (große Tabellen, lange Texte)
  - Berechnung: 2K Bild-Tokens + 0.5K System-Prompt + 12.5K Response = 15K total

### Fixed

- **Korrekte Bildgrößen-Anzeige** ([conversation_handler.py](aifred/lib/conversation_handler.py)):
  - Zeigt echte Dateigröße in KB (aus `size_kb` Metadaten beim Upload)
  - Vorher: Berechnete fälschlicherweise die Base64-Länge (33% größer als Originaldatei)

- **Port-unabhängige URLs für Uploads** ([vision_utils.py](aifred/lib/vision_utils.py), [formatting.py](aifred/lib/formatting.py), [audio_processing.py](aifred/lib/audio_processing.py), [state.py](aifred/state.py)):
  - Alle Upload-URLs (Bilder, TTS Audio, HTML Preview) verwenden jetzt relative Pfade
  - Browser verwendet automatisch den aktuellen Host/Port
  - Problem behoben: Bilder über Port 443 aufgerufen → versuchte Port 8443 zu laden
  - Entfernt: `BACKEND_API_URL` nicht mehr benötigt (war hardcoded in config.py)
  - **Neu: URL-Normalisierung beim Session-Restore** (`_normalize_upload_urls()`):
    - Alte Sessions mit absoluten URLs werden beim Laden automatisch normalisiert
    - Konvertiert `http(s)://host:port/_upload/...` → `/_upload/...`
    - Betrifft sowohl HTML-Content als auch metadata.images URLs

---

## [2.19.2] - 2026-01-16

### Improved

- **Vision OCR Prompt: Vollständigkeitspflicht** ([vision_ocr.txt](prompts/de/vision/vision_ocr.txt), [vision_ocr.txt](prompts/en/vision/vision_ocr.txt)):
  - Neue explizite Verbote: Keine Zusammenfassungen, keine "...", keine "Example Entries"
  - Neue Vollständigkeitspflicht: ALLE erkannten Daten müssen in der JSON-Ausgabe erscheinen
  - Problem behoben: Vision-LLM extrahierte Tabellen korrekt im Thinking, gab aber nur Zusammenfassungen aus
  - Beispiel-Kommentare ergänzt um klarzustellen dass ALLE Zeilen ausgegeben werden müssen

### Added

- **Chat Export: Klickbare URLs** ([state.py](aifred/state.py)):
  - URLs in exportierten Chats sind jetzt klickbar und öffnen in neuem Tab
  - Verwendet mistune's eingebautes `url` Plugin für URL-Erkennung
  - Neue Hilfsfunktion `_add_target_blank_to_links()` für `target="_blank"`
  - Betrifft: Quellenangaben vom LLM, failed sources collapsible, alle Links im Export

### Fixed

- **Fehlende Dependency** ([requirements.txt](requirements.txt)):
  - `mistune>=3.0.0` zu requirements.txt hinzugefügt (war bereits verwendet aber nicht deklariert)

---

## [2.19.1] - 2026-01-15

### Fixed

- **Critical: User Message Disappearing from Chat History** ([state.py](aifred/state.py)):

  **Problem:** Nach Abschluss der LLM-Inferenz (und Titel-Generierung) verschwand die User-Message aus der Chat-History. Die User-Bubble war nicht mehr sichtbar.

  **Ursache:** An 3 Stellen in `state.py` wurde `self.chat_history[:-1]` an die Handler-Funktionen übergeben:
  - Zeile 3315 (Vision Pipeline Phase 2)
  - Zeile 3413 (Automatik Mode)
  - Zeile 3672 (Research Mode)

  Das `[:-1]` sollte ursprünglich einen "temporary entry" ausschließen, der nicht mehr existiert. Stattdessen wurde die **User-Message** (das letzte Element) ausgeschlossen.

  **Ablauf des Bugs:**
  1. User sendet Nachricht → User-Message wird zu `self.chat_history` hinzugefügt (Zeile 3055-3066)
  2. Handler-Funktion wird mit `self.chat_history[:-1]` aufgerufen → User-Message fehlt!
  3. Handler fügt nur AI-Antwort zur History hinzu (nicht User-Message, siehe Kommentar in `conversation_handler.py:1588`)
  4. `self.chat_history = result_data["history"]` überschreibt die komplette History
  5. User-Message ist verschwunden

  **Hinweis:** Die `llm_history` war nicht betroffen, weil dort die User-Message im Handler wieder hinzugefügt wird (`own_knowledge_handler.py:271`).

  **Fix:** `[:-1]` entfernt an allen 3 Stellen:
  ```python
  # Vorher (falsch):
  history=self.chat_history[:-1],  # Exclude current temporary entry

  # Nachher (korrekt):
  history=self.chat_history,  # User message already included
  ```

---

## [2.19.0] - 2026-01-13

### Added

- **Username + Password Authentication** ([session_storage.py](aifred/lib/session_storage.py), [state.py](aifred/state.py), [aifred.py](aifred/aifred.py)):
  - Login dialog with username and password fields
  - Password hashing with SHA-256 (stored as `sha256:...` hash)
  - Auto-login via browser cookie (username persisted, not password)
  - Login/Register mode toggle in dialog
  - Enter key support for form submission

- **Whitelist-Based Registration** ([session_storage.py](aifred/lib/session_storage.py)):
  - Only usernames on whitelist (`~/.config/aifred/allowed_users.json`) can register
  - Admin controls who can create accounts
  - Case-insensitive username handling

- **Session Ownership** ([session_storage.py](aifred/lib/session_storage.py)):
  - Sessions now have `owner` field linking to username
  - Users only see their own sessions in the chat list
  - New sessions automatically assigned to logged-in user

- **AIfred Admin CLI** ([aifred-admin](aifred-admin)):
  - Standalone command-line tool for user management
  - `aifred-admin users` - List whitelist
  - `aifred-admin add <username>` - Add to whitelist
  - `aifred-admin remove <username>` - Remove from whitelist
  - `aifred-admin accounts` - List registered accounts with session counts
  - `aifred-admin delete <username> [--sessions]` - Delete account (optionally with sessions)

- **Username Cookie** ([browser_storage.py](aifred/lib/browser_storage.py)):
  - `get_username_script()` - Read username from cookie
  - `set_username_script()` - Store username in cookie (1 year expiry)
  - `clear_username_script()` - Delete cookie on logout

### Changed

- **Session Initialization** ([state.py](aifred/state.py)):
  - Login now creates a new session if user has none
  - Registration always creates a new session for the new account
  - Prevents orphan sessions without owner

### Removed

- **Device-ID Only Sessions**: Sessions now require authentication; anonymous device-based sessions no longer supported

---

## [2.18.0] - 2026-01-13

### Added

- **Session Management UI** ([aifred.py](aifred/aifred.py), [state.py](aifred/state.py)):
  - Chat list sidebar showing all sessions with titles
  - Click to switch between sessions
  - Delete sessions with confirmation dialog
  - Sessions sorted by last activity (newest first)
  - Collapsible sidebar with toggle button

- **LLM-Generated Chat Titles** ([state.py](aifred/state.py), [session_storage.py](aifred/lib/session_storage.py)):
  - Auto-generate descriptive title after first Q&A pair
  - Uses small Automatik model (stays warm, no model switching)
  - Thinking mode disabled for fast response
  - Topic-based prompts in DE/EN (`prompts/*/utility/chat_title.txt`)
  - Title displayed in session list and header

### Changed

- **Session Sorting Stability** ([session_storage.py](aifred/lib/session_storage.py)):
  - `load_session()` no longer updates `last_seen` timestamp
  - Only `save_session()` updates `last_seen` (when new content added)
  - Session list remains stable when just viewing sessions

### Fixed

- **Metadata Display** ([own_knowledge_handler.py](aifred/lib/own_knowledge_handler.py)):
  - TTFT, inference time, and tok/s now visible in chat messages
  - Added missing `format_metadata` import and usage

- **llm_history Updates** ([own_knowledge_handler.py](aifred/lib/own_knowledge_handler.py)):
  - User message now properly added to `llm_history`
  - Fixed title generation which requires complete history

- **Double Bubble Rendering** ([state.py](aifred/state.py)):
  - `current_ai_response` cleared immediately after history update
  - Prevents duplicate message display during title generation

---

## [2.17.0] - 2026-01-13

### Changed

- **Unified Result-Dict Format** ([context_builder.py](aifred/lib/research/context_builder.py), [cache_handler.py](aifred/lib/research/cache_handler.py), [conversation_handler.py](aifred/lib/conversation_handler.py), [own_knowledge_handler.py](aifred/lib/own_knowledge_handler.py), [state.py](aifred/state.py)):
  - All `{"type": "result", "data": ...}` yields now use consistent Dict format
  - Removed mixed Tuple/Dict handling - single format across all LLM pipelines
  - Standardized fields: `response_clean`, `response_html`, `history`, `inference_time`, `tokens_per_sec`, `ttft`, `model_choice`, `failed_sources`
  - `own_knowledge_handler` now accepts `history` parameter and returns updated history in result
  - Simplified result processing in `state.py` - removed isinstance checks and legacy Tuple handling

- **Share Chat Function Rewritten** ([state.py](aifred/state.py)):
  - Updated to work with Dict-based `chat_history` format
  - Proper handling of `role`, `content`, `agent`, `mode`, `metadata` fields
  - Fixed `ValueError: too many values to unpack` error

- **HTML Export Image Preservation** ([state.py](aifred/state.py)):
  - `_convert_markdown_preserve_html()` now preserves `<a>` and `<img>` tags
  - Added special regex handling for self-closing tags like `<img>`
  - Images in exported HTML now render properly and are clickable

### Removed

- **Legacy Tuple Result Format**: All Tuple-based result handling code removed
- **Hybrid Result Processing**: No more isinstance checks for Dict vs Tuple formats

---

## [2.16.0] - 2026-01-11

### Added

- **Inline Image Thumbnails in Chat History** ([state.py](aifred/state.py), [aifred.py](aifred/aifred.py)):
  - Uploaded images now display as 50x50px clickable thumbnails in user messages
  - Click on thumbnail opens full-size image in new browser tab
  - Images embedded as HTML `<a><img></a>` tags in message content
  - Works with `rx.markdown` component rendering

- **Device-ID Based Image Storage** ([vision_utils.py](aifred/lib/vision_utils.py)):
  - Images stored in `uploaded_files/images/{device_id}/` instead of `{session_id}/`
  - Device-ID is persistent across browser sessions (32-char hex identifier)
  - Images survive Reflex session reconnects

- **External Links in New Tab** ([aifred.py](aifred/aifred.py)):
  - All markdown links in AI responses open in new tab (`target="_blank"`)
  - Custom `MARKDOWN_COMPONENT_MAP` with `rx.link(is_external=True)`
  - Applied to all 14 `rx.markdown` instances

### Changed

- **Image Cleanup in Message Builder** ([message_builder.py](aifred/lib/message_builder.py)):
  - `_clean_content()` now removes HTML image tags for LLM context
  - Handles both legacy `[IMG:...]` markers and new `<a><img></a>` format
  - Prevents image HTML from polluting LLM conversation history

- **HTML Export with Embedded Images** ([state.py](aifred/state.py)):
  - `share_chat()` converts image URLs to Base64 data URIs
  - Exported HTML files are self-contained and portable
  - Pattern changed from `[IMG:url]` to `<img src="url">` detection

---

## [2.15.37] - 2026-01-11

### Changed

- **Vision Refactoring: File-Based Image Storage** ([vision_utils.py](aifred/lib/vision_utils.py), [state.py](aifred/state.py), [conversation_handler.py](aifred/lib/conversation_handler.py)):
  - **Critical Bug Fixed**: Base64 images were stored in `chat_history`, causing session files to grow 2+ MB and browser unresponsiveness
  - **New Storage**: Images saved as JPEG files in `uploaded_files/images/{session_id}/`
  - **On-Demand Loading**: Base64 now generated only when sending to Vision-LLM
  - **Session Cleanup**: Images automatically deleted with `clear_chat()`
  - **New Functions** in `vision_utils.py`:
    - `save_image_to_file()` - Save image bytes as JPEG
    - `get_image_url()` - Convert path to HTTP URL for UI
    - `load_image_as_base64()` - Load from file when needed
    - `cleanup_session_images()` - Delete session images
  - **Breaking**: Old sessions with Base64 images won't display images (intentional - no fallback)

- **Prompt Token Estimate Rename** ([prompt_loader.py](aifred/lib/prompt_loader.py)):
  - Renamed misleading "Prompt cache" log message to "Prompt token estimate"
  - More accurately describes the function (token counting, not caching)

---

## [2.15.36] - 2026-01-11

### Changed

- **Raw Error Messages** ([scraper_tool.py](aifred/lib/tools/scraper_tool.py)):
  - Removed `_classify_error()` function - was misclassifying errors (e.g., "timeout=15000" matched as "500 Server Error")
  - Now using raw exception messages directly for honest, debuggable error output
  - Playwright timeout increased from 10s to 15s for slower sites

### Removed

- **Error Classification Logic**: Deleted ~40 lines of buggy error classification code that:
  - Falsely matched "500" in timeout values like "15000"
  - Hid actual exception messages behind generic labels
  - Made debugging harder instead of easier

---

## [2.15.35] - 2026-01-11

### Fixed

- **Playwright Error Logging** ([scraper_tool.py](aifred/lib/tools/scraper_tool.py)):
  - Playwright errors now logged to UI debug console via `log_message()`
  - Previously only visible in systemd journal, not in AIfred's debug log
  - Helps diagnose JavaScript-heavy page scraping issues

### Changed

- **Documentation Updates**:
  - Added trafilatura + Playwright fallback strategy documentation to both READMEs
  - Fixed dependencies table in README.de.md (removed beautifulsoup4, added numpy)
  - Added API message injection and systemctl documentation to CLAUDE.md

---

## [2.15.34] - 2026-01-11

### Added

- **500 Error Retry Logic for Multi-Agent Streaming** ([multi_agent.py](aifred/lib/multi_agent.py)):
  - **New**: `_chat_stream_with_retry()` - Central wrapper function for LLM streaming with retry logic
  - On 500 Internal Server Error: Logs error, waits 2 seconds, retries once
  - If retry fails: Error is re-raised (visible in console and debug logs)
  - Applied to all three streaming functions:
    - `_stream_sokrates_to_history()`
    - `_stream_alfred_refinement()`
    - `_stream_salomo_to_history()`
  - **Problem solved**: Occasional 500 errors during rapid model switches in Multi-Agent mode (e.g., 80B Hybrid models)
  - **Log output**: `⚠️ Sokrates: 500 Error - retrying in 2.0s...`

---

## [2.15.33] - 2026-01-10

### Changed

- **Hybrid Mode Calibration Refactoring** ([ollama.py](aifred/backends/ollama.py), [gpu_utils.py](aifred/lib/gpu_utils.py)):
  - **New**: `calculate_context_from_memory()` - Universal function for VRAM and RAM context calculation
  - **New**: `get_swap_used_mb()` - Query current swap usage via psutil
  - **Fix**: All Hybrid calibration paths now calculate RAM-based upper bound BEFORE binary search
  - **Fix**: Binary search now monitors **swap increase** during each test iteration
    - Problem: Linux keeps RAM "available" by swapping, hiding system overload
    - Solution: If swap increases > 512 MB during test → context too large → reduce
  - **Problem solved**: System freeze at 135k tokens due to excessive swapping
  - **Three Hybrid paths refactored**:
    1. `force_hybrid` (RoPE calibration after 1.0x was hybrid)
    2. `model > VRAM` (model larger than available VRAM)
    3. `VRAM-only < 16k` (VRAM-only yields too little context)
  - **Formula**: `max_tokens = (available_mb - reserve_mb) / ratio_mb_per_token`
  - **Constants**: `MIN_FREE_RAM_MB = 3072`, `MIN_USEFUL_CONTEXT_TOKENS = 16384`, `MAX_SWAP_INCREASE_MB = 512`

---

## [2.15.32] - 2026-01-10

### Fixed

- **Language Consistency Bug** ([#milestone](https://github.com/marpete/AIfred-Intelligence)):
  - Fixed agents (Sokrates, Salomo) answering in wrong language
  - **Root Cause**: Reminder was injected with UI-Language instead of detected_language, overriding system prompt language
  - **Fix 1 - Reminder Injection** ([message_builder.py](aifred/lib/message_builder.py)):
    - Added `detected_language` parameter to `build_messages_from_llm_history()`
    - Reminder now uses detected_language with fallback to UI-Language
  - **Fix 2 - Intent Detection Parser** ([intent_detector.py](aifred/lib/intent_detector.py)):
    - Parser now handles "(empty)" marker from LLM robustly
    - Changed all fallbacks from hardcoded `"en"` to `get_language()` (UI-Language)
  - **Fix 3 - Intent Detection Prompt** ([intent_detection.txt](prompts/en/automatik/intent_detection.txt)):
    - Added explicit instruction: "DO NOT write '(empty)' or 'none' - just leave it blank!"
  - **Fix 4 - Multi-Agent Defaults** ([multi_agent.py](aifred/lib/multi_agent.py)):
    - Changed 4 function signatures from `detected_lang: str = "en"` to `Optional[str] = None`
    - Functions: `run_sokrates_direct_response`, `run_salomo_direct_response`, `run_sokrates_analysis`, `run_tribunal`
    - All now fallback to UI-Language instead of hardcoded "en"
  - **Fix 5 - Salomo Mediator Prompt** ([mediator.txt](prompts/en/salomo/mediator.txt)):
    - Enhanced to match German version's detail level

- **Language Logic** (Consistent across all code paths):
  - If Intent Detection provides language → Use that for ALL prompts and reminder
  - If Intent Detection provides NO language → Fallback to UI-Language (not "en")
  - Works across: AIfred, Sokrates, Salomo, all modes (Auto-Consensus, Tribunal, Critical Review)

---

## [2.15.31] - 2026-01-09

### Added

- **LLM History for Automatik-LLM** ([conversation_handler.py](aifred/lib/conversation_handler.py), [state.py](aifred/state.py)):
  - `detect_research_decision` now receives `llm_history` parameter
  - Enables pronoun resolution in follow-up questions ("dieser Film" → "Der Tiger 2025")
  - Token-based history limiting: 2/3 of context for history, 1/3 for prompt+output
  - Uses local Qwen3 tokenizer for accurate token counting

- **Local Qwen3 Tokenizer** ([context_manager.py](aifred/lib/context_manager.py)):
  - Replaced HuggingFace transformers with lightweight `tokenizers` library (~5MB vs ~500MB)
  - Fully offline: reads from `~/.cache/huggingface/` - no network calls
  - No fallback: errors surface immediately for debugging

- **Centralized RAW Message Logging** ([logging_utils.py](aifred/lib/logging_utils.py)):
  - New `log_raw_messages(agent_name, messages, token_counter)` function
  - Full message content logged to debug.log (not just preview)
  - Token count per message when token_counter provided
  - Used by: Automatik-LLM, Sokrates, Salomo, AIfred, Compression LLM

### Changed

- **Research Decision Prompt v2** ([research_decision.txt](prompts/de/automatik/research_decision.txt), [research_decision.txt](prompts/en/automatik/research_decision.txt)):
  - **NEW: "KRITISCHE REGEL" section at top** - forces model to check EXACT answer presence first
  - Added explicit "STOPP!" instruction with 3-step checklist
  - Concrete example: Film info in chat but no filming locations → web=true
  - "NIEMALS erfinden! Lieber recherchieren als halluzinieren!" warning
  - Reordered rules: Follow-up questions now first priority for web=true
  - web=false now explicitly requires "NUR wenn die EXAKTE Antwort bereits im Chat steht"

### Fixed

- **Hallucination Prevention**:
  - Automatik-LLM now checks if specific information is in history before deciding `web=false`
  - Prevents AIfred from inventing plausible-sounding but false details
  - Example: "Der Tiger" filming locations were hallucinated before this fix

---

## [2.15.30] - 2026-01-09

### Added

- **Non-Scrapable Domain Filter** ([url_utils.py](aifred/lib/tools/url_utils.py)):
  - Filters out video platforms (YouTube, Vimeo, TikTok, Twitch, etc.) before URL ranking
  - Filters out social media with login walls (Twitter/X, Facebook, Instagram, LinkedIn)
  - Prevents wasted scraping attempts on sites that cannot be scraped effectively
  - Logged in debug.log: `🚫 Blocked: https://youtube.com/...`
  - Summary log: `🚫 Filtered 6 non-scrapable URLs (video/social platforms)`

- **External Blocked Domains Configuration** ([blocked_domains.txt](data/blocked_domains.txt)):
  - Moved blocked domains from hardcoded Python set to external text file
  - Easy to maintain: One domain per line, `#` for comments
  - Automatic subdomain matching (e.g., `youtube.com` also blocks `m.youtube.com`)
  - Lazy loading with caching (loaded once at first use)

- **Consistent Source Numbering** ([context_builder.py](aifred/lib/research/context_builder.py)):
  - Sources now sorted identically in logging and LLM context
  - Sorting rule: News articles first (short), Wikipedia last (long)
  - Debug log now shows sources in same order as they appear in context

### Changed

- **Automatik-LLM Context Increased** ([config.py](aifred/lib/config.py)):
  - `AUTOMATIK_LLM_NUM_CTX` increased from 4K to 12K tokens
  - Supports URL ranking with 30+ URLs (each ~70 tokens)
  - Note: num_ctx only affects max context size, not processing speed
  - Removed separate `AUTOMATIK_LLM_NUM_CTX_URL_RANKING` constant (single value for all tasks)

### Fixed

- **RAW Response Logging** ([formatting.py](aifred/lib/formatting.py)):
  - RAW AI response now logged only once (was duplicated before)
  - Central logging in `format_thinking_process()` only

---

## [2.15.29] - 2026-01-09

### Changed

- **Query Language Rules** ([research_decision.txt](prompts/de/automatik/research_decision.txt), [research_decision.txt](prompts/en/automatik/research_decision.txt)):
  - Query 1: ALWAYS in English (for international sources, more results)
  - Query 2-3: In the language of the question
  - Simpler rule than "include English for technical topics" (LLM-agnostic)
  - Results in better search coverage across languages

### Added

- **English RAG Relevance Check Prompt** ([rag_relevance_check.txt](prompts/en/automatik/rag_relevance_check.txt)):
  - Added missing English version of RAG relevance check prompt
  - Fixes crash when English-language users trigger RAG context flow
  - Matches German version structure with examples

### Fixed

- **Fallback Removal in context_builder.py** ([context_builder.py](aifred/lib/research/context_builder.py)):
  - Removed silent fallback to German when `detected_language` is None
  - Now raises `ValueError` instead of defaulting silently
  - Ensures language detection bugs surface immediately

### Documentation

- **README Phase 4 Documentation** ([README.de.md](README.de.md), [README.md](README.md)):
  - Updated Automatik Decision section to document combined LLM call
  - Added Query Rules subsection explaining English-first query strategy
  - Reflects actual code behavior after v2.15.18 consolidation

---

## [2.15.28] - 2026-01-07

### Changed

- **Critical Review Mode Enhanced** ([prompts/de/sokrates/critic.txt](prompts/de/sokrates/critic.txt), [prompts/en/sokrates/critic.txt](prompts/en/sokrates/critic.txt)):
  - Added mandatory Pro/Contra section at the end of Sokrates' critique
  - Sokrates now delivers: Critique → Alternative Solution → Pro/Contra overview
  - Helps users see both sides of AIfred's position at a glance

### Removed

- **Advocatus Diaboli Mode Disabled** ([state.py](aifred/state.py)):
  - Mode removed from dropdown (code preserved for potential reactivation)
  - Functionality merged into Critical Review mode (Pro/Contra section)
  - Reason: Too similar to Critical Review, consolidation improves UX

### Added

- **TODO.md Vision Items**:
  - Configurable Multi-Agent System: User-defined agents with custom prompts
  - RAG-Agent "Bibliothekar": Local document search with vector indexing

---

## [2.15.18] - 2026-01-05

### Added

- **Consolidated Research Decision** ([conversation_handler.py](aifred/lib/conversation_handler.py), [prompt_loader.py](aifred/lib/prompt_loader.py)):
  - New `detect_research_decision()` function combines Decision-Making + Query-Optimization
  - Reduces 2 LLM calls → 1 LLM call in Automatik-Modus (saves ~1-2s latency)
  - New prompts: `research_decision.txt` (DE + EN) with JSON output format
  - Pre-generated queries passed to `perform_agent_research()` to skip Query-Opt call
  - Decision output: `{"web": true/false, "queries": ["q1", "q2", "q3"]}`

- **Centralized Content Cleaning** ([message_builder.py](aifred/lib/message_builder.py)):
  - New `TIMING_PATTERNS` module-level constant (Single Source of Truth)
  - New `_clean_content()` internal function for all content stripping
  - Consolidated duplicate cleaning logic from `build_messages_from_history()` and `clean_content_for_llm()`
  - Added `*( TTFT:` pattern to prevent TTFT metadata leaking into LLM context

- **i18n Pluralization Support** ([i18n.py](aifred/lib/i18n.py)):
  - New `count` parameter in `t()` function for automatic singular/plural selection
  - Usage: `t("sources_unavailable", count=3)` → uses `key_plural` if count > 1
  - New keys: `sources_unavailable`, `sources_unavailable_plural`

### Changed

- **LLM Call Optimization** ([state.py](aifred/state.py), [conversation_handler.py](aifred/lib/conversation_handler.py)):
  - Automatik-Modus now uses consolidated research decision (1 call instead of 2)
  - Query-Optimization skipped when pre-generated queries are available
  - Debug console shows: `⚡ Using pre-generated queries (skip Query-Opt LLM)`

### Fixed

- **TTFT Pattern Leakage** ([message_builder.py](aifred/lib/message_builder.py)):
  - Added `*( TTFT:` to timing patterns list
  - Prevents LLMs from imitating TTFT metadata in responses

---

## [2.15.17] - 2026-01-03

### Added

- **Cloud API Integration** ([cloud_api.py](aifred/backends/cloud_api.py), [config.py](aifred/lib/config.py)):
  - New backend type `cloud_api` for cloud LLM providers
  - Supported providers: **Qwen/DashScope**, **DeepSeek**, **Claude (Anthropic)**, **Kimi (Moonshot)**
  - Dynamic model fetching from `/models` endpoint (no hardcoded model lists)
  - Provider-specific base URLs and API key environment variables
  - Vision model filtering (excludes `-vl` models from main LLM dropdown)
  - Token usage display in debug console (prompt/completion tokens)
  - OpenAI-compatible API implementation for all providers

- **User Salutation System** ([prompt_loader.py](aifred/lib/prompt_loader.py), [system_minimal.txt](prompts/de/aifred/system_minimal.txt)):
  - New `{user_salutation}` placeholder in prompts
  - Gender-aware addressing (Herr/Frau + Name)
  - Only in user-facing prompts (not internal agent communication)
  - Natural variations allowed (e.g., "Mein lieber Herr Müller")
  - Prevents generic double-forms ("Herr/Frau", "Dear Sir/Madam")

### Changed

- **Backend Selection UI** ([aifred.py](aifred/aifred.py)):
  - Cloud API providers shown as separate options in backend dropdown
  - Labels: "☁️ Qwen (DashScope)", "☁️ DeepSeek", "☁️ Claude (Anthropic)"
  - Per-provider model memory (each cloud provider remembers its last used model)

---

## [2.15.16] - 2026-01-03

### Added

- **TTS Pitch Control** ([audio_processing.py](aifred/lib/audio_processing.py), [aifred.py](aifred/aifred.py)):
  - New pitch slider in TTS settings (0.8 to 1.2)
  - Pitch adjustment via ffmpeg post-processing (asetrate/aresample)
  - Persisted in user settings

- **Piper TTS German Voices** ([config.py](aifred/lib/config.py)):
  - Added Karlsson, Kerstin, Eva K, MLS voices
  - Removed English voices (Alba, Alan) - focus on German TTS
  - Removed Pavoque (had persistent "Höh" artifact)

- **Date/Time in Agent Prompts** ([system_minimal.txt](prompts/de/aifred/system_minimal.txt)):
  - All agents (AIfred, Sokrates, Salomo) now receive current date/time
  - Consistent across DE and EN prompts

### Fixed

- **German Language Enforcement** ([personality.txt](prompts/de/aifred/personality.txt)):
  - Restructured prompt with language instruction at END (LLMs follow last instruction most strongly)
  - Added FALSCH/RICHTIG examples to prevent English output
  - Fixes issue where Qwen3-4B Thinking model drifted to English during long reasoning

- **Piper TTS Artifacts** ([audio_processing.py](aifred/lib/audio_processing.py)):
  - Fixed "PFFT/HÖH" sound at end of audio by ensuring proper trailing punctuation
  - Added timing metadata filter (STT, TTFT, Inference, tok/s, etc.)
  - Added zero-width Unicode character removal
  - Decorative separator lines (═══, ───) now replaced with pause

- **Intent Detection Visibility** ([state.py](aifred/state.py)):
  - Language detection now logged to UI debug console (was file-only)
  - Shows: `🎯 Intent: FAKTISCH, Addressee: –, Lang: DE`

---

## [2.15.15] - 2026-01-02

### Added

- **Personality Reminder System** ([message_builder.py](aifred/lib/message_builder.py), [prompt_loader.py](aifred/lib/prompt_loader.py)):
  - New `reminder.txt` files for each agent (AIfred, Sokrates, Salomo)
  - Short personality reminder automatically prefixed to user messages
  - Reinforces agent speech style in long conversations where system prompt is far from current question
  - New `load_personality_reminder()` function in prompt_loader

- **TTS Smart Filtering** ([audio_processing.py](aifred/lib/audio_processing.py)):
  - Code blocks (``` ... ```) excluded from speech output
  - Markdown tables (| ... |) excluded from speech output
  - LaTeX formulas ($...$ and $$...$$) excluded from speech output
  - Inline code (`...`) excluded from speech output

- **Dynamic Year Placeholder** ([prompt_loader.py](aifred/lib/prompt_loader.py)):
  - New `{current_year}` placeholder available in all prompts
  - Automatically injected via kwargs in `load_prompt()`

### Fixed

- **Query Optimization Year Bug** ([query_optimization.txt](prompts/de/query_optimization.txt), [prompts/en/query_optimization.txt](prompts/en/query_optimization.txt)):
  - Replaced hardcoded "2025" with dynamic `{current_year}` placeholder
  - Search queries now use correct current year

### Changed

- **Personality Prompts Simplified** ([personality.txt](prompts/de/aifred/personality.txt), [prompts/de/sokrates/personality.txt](prompts/de/sokrates/personality.txt)):
  - Removed redundant style criticism prohibition (already in identity.txt)
  - Cleaner separation between identity (who) and personality (how)

---

## [2.15.14] - 2026-01-02

### Changed

- **LLM-based Language Detection** ([intent_detector.py](aifred/lib/intent_detector.py), [state.py](aifred/state.py)):
  - Language detection now uses LLM instead of Regex patterns
  - Intent Detection returns 4 values: `(intent, addressee, detected_language, raw_response)`
  - Format: `INTENT|ADDRESSEE|LANGUAGE` (e.g., `FACTUAL|sokrates|DE`, `CREATIVE||EN`)
  - Single English prompt for intent detection (handles all languages universally)
  - Deleted `prompts/de/intent_detection.txt` (no longer needed)

- **Removed "auto" Language Mode** ([prompt_loader.py](aifred/lib/prompt_loader.py), [config.py](aifred/lib/config.py)):
  - Removed Regex-based `detect_language()` function completely
  - `DEFAULT_LANGUAGE` changed from "auto" to "de"
  - `set_language()` now only accepts "de" or "en" (no "auto")
  - All "auto" fallback logic removed from prompt loader

- **Intent Detection Moved Earlier** ([state.py](aifred/state.py)):
  - Intent Detection now runs BEFORE Pre-Compression-Check
  - `detected_language` passed through entire call chain to all functions
  - Vision Pipeline fallback: uses `ui_language` when no text present

- **Multi-Agent Language Support** ([multi_agent.py](aifred/lib/multi_agent.py)):
  - All agent functions now receive `detected_lang` parameter
  - Sokrates, Salomo direct responses use LLM-detected language
  - Tribunal and Analysis modes use consistent language detection

### Fixed

- **Consistent Response Language**: AIfred now responds in the language of the user's current question, not based on Regex patterns that could fail on short queries

---

## [2.15.13] - 2026-01-02

### Added

- **Production Mode for External HTTPS Access** ([rxconfig.py](rxconfig.py), [systemd/aifred-intelligence.service](systemd/aifred-intelligence.service)):
  - Added `--env prod` flag to systemd service for production mode
  - Disables Vite Hot Module Replacement (HMR) WebSocket that caused connection errors
  - External HTTPS access now works correctly via nginx reverse proxy
  - Added dotenv loading in `rxconfig.py` for `.env` configuration

- **Environment Configuration via .env** ([README.md](README.md), [README.de.md](README.de.md)):
  - New `AIFRED_API_URL` variable for external domain configuration
  - Documentation for production deployment with reverse proxy
  - `.env` file is gitignored (machine-specific configuration)

### Changed

- **Systemd Service Improvements** ([systemd/aifred-intelligence.service](systemd/aifred-intelligence.service)):
  - Added `KillMode=control-group` for proper process termination
  - Added `ExecStopPost` to cleanup koboldcpp processes on stop
  - Environment variables now read from `.env` instead of service file

- **Hide "Built with Reflex" Badge** ([rxconfig.py](rxconfig.py)):
  - Added `show_built_with_reflex=False` for cleaner UI

---

## [2.15.12] - 2026-01-01

### Changed

- **Share Chat: Portable HTML Export** ([state.py](aifred/state.py), [formatting.py](aifred/lib/formatting.py)):
  - KaTeX CSS, JS and all fonts now embedded inline as Base64 (single-file export)
  - Exports work completely offline without any external dependencies
  - New `get_katex_inline_assets()` function with caching for efficient embedding
  - Removed `examples/` folder, exports now go to `uploaded_files/exports/`

### Fixed

- **AIfred Metadata Spacing** ([state.py](aifred/state.py)):
  - Added missing blank line between AIfred's response and metadata footer
  - Now consistent with other agents (Vision, Sokrates, Salomo)

- **HTML Export CSS** ([state.py](aifred/state.py)):
  - Removed `white-space: pre-wrap` which caused excessive spacing
  - Improved margins for paragraphs, headings, lists, tables

### Removed

- **rxconfig.py**: Removed invalid `reload_excludes` option (not supported by Reflex)

---

## [2.15.11] - 2026-01-01

### Added

- **Share Chat: HTML Export** ([state.py](aifred/state.py)):
  - Chat export now opens as styled HTML in new browser tab (instead of clipboard copy)
  - Dark theme matching AIfred UI with agent-specific colors (🎩 AIfred, 🏛️ Sokrates, 👑 Salomo)
  - Working `<details>` collapsibles for thinking processes in exported HTML
  - Files saved to `uploaded_files/html_preview/` with LRU cache (max 50 files)

- **i18n: Collapsible Labels** ([i18n.py](aifred/lib/i18n.py), [config.py](aifred/lib/config.py), [formatting.py](aifred/lib/formatting.py)):
  - All collapsible labels now translatable (Thinking Process, Structured Data, Summary, etc.)
  - `get_xml_tag_config(lang)` replaces static `XML_TAG_CONFIG` dict
  - Labels respect UI language setting (DE: "Denkprozess", EN: "Thinking Process")

---

## [2.15.10] - 2026-01-01

### Documentation

- **Major docs cleanup: README.md as single source of truth**
  - Deleted 55+ documentation files that duplicated README content
  - Deleted 16 obsolete scripts (download scripts, test scripts, etc.)
  - Moved `AGENT_PIPELINE_USAGE.md` to `.claude/` (internal docs)
  - Kept only `docs/vllm/` for GPU-specific vLLM documentation
  - Kept `docs/plans/HYBRID_MODE_CALIBRATION_DISCUSSION.md` as referenced roadmap item

- **Translated all German documentation to English**
  - `docker/README.md` - Docker services documentation
  - `systemd/README.md` - Systemd service installation and monitoring
  - `prompts/README.md` - **Completely rewritten** to reflect current i18n prompt structure
  - `docker/searxng/README.md` - SearXNG setup guide
  - `TODO.md` - Roadmap and planned features
  - `docs/plans/HYBRID_MODE_CALIBRATION_DISCUSSION.md` - Hybrid mode planning document

- **Fixed broken links**
  - `docs/vllm/README.md` - Removed reference to deleted `GPU_COMPATIBILITY.md`
  - `prompts/README.md` - Removed outdated reference to `lib/agent_core.py`

- **Scripts cleanup**
  - Added Playwright installation to `scripts/setup-python.sh`
  - Kept essential scripts: `install-all.sh`, `install-services.sh`, `install_koboldcpp.sh`, `setup-python.sh`, `chroma_maintenance.py`

---

## [2.15.9] - 2025-12-30

### Refactoring

- **API: Browser Remote Control Architektur** ([api.py](aifred/lib/api.py), [session_storage.py](aifred/lib/session_storage.py), [state.py](aifred/state.py)):
  - API führt keine eigene LLM-Inferenz mehr aus - stattdessen werden Messages in Browser-Sessions injiziert
  - Neuer Endpoint `POST /api/chat/inject` ersetzt `/api/chat/send`
  - Neuer Endpoint `GET /api/chat/status` für Inferenz-Status-Polling
  - Browser pollt pending_messages und führt volle Pipeline aus (Intent Detection, Multi-Agent, Research...)
  - **Vorteile:** Ein Code-Pfad, alle Features funktionieren, ~120 Zeilen LLM-Code entfernt, User sieht Streaming live

### Fixed

- **Diskussionsmodus-Dropdown zeigte keinen Wert** ([aifred.py](aifred/aifred.py)):
  - `rx.select.trigger(placeholder="...")` überschrieb die Wertanzeige
  - Fix: Leerer Trigger wie bei anderen funktionierenden Dropdowns

---

## [2.15.8] - 2025-12-30

### Fixed

- **API: `<think>` Tags werden jetzt als Collapsibles formatiert** ([api.py](aifred/lib/api.py)):
  - API-Responses nutzen jetzt `format_thinking_process()` für UI-Anzeige
  - `<think>` Tags werden zu klickbaren "Denkprozess" Collapsibles
  - Vorher: Rohe `<think>` Tags wurden ungefiltert angezeigt

---

## [2.15.7] - 2025-12-30

### Refactoring

- **Centralize DEFAULT_OLLAMA_URL constant** ([config.py](aifred/config.py)):
  - URL-Konstante zentral in config.py definiert
  - Vermeidet Hardcodierungen in mehreren Dateien

---

## [2.15.6] - 2025-12-30

### Refactoring

- **Extract model discovery to reusable module** ([model_discovery.py](aifred/lib/model_discovery.py)):
  - Backend-agnostische Model-Discovery aus state.py extrahiert
  - Unterstützt Ollama, vLLM, TabbyAPI, KoboldCPP

---

## [2.15.5] - 2025-12-30

### Refactoring

- **Consolidate GPU queries and cleanup functions** ([gpu_utils.py](aifred/lib/gpu_utils.py)):
  - GPU-Abfragen in eigenes Modul konsolidiert
  - Cleanup-Funktionen zentralisiert

---

## [2.15.4] - 2025-12-30

### Refactoring

- **Cleanup redundant code in state.py**:
  - Entfernung von ungenutztem Code
  - Vereinfachung der State-Logik

---

## [2.15.3] - 2025-12-30

### Refactoring

- **Misc code quality improvements**:
  - Kleinere Verbesserungen und Aufräumarbeiten

---

## [2.15.2] - 2025-12-30

### Refactoring

- **Code-Cleanup und Keep-It-Simple Verbesserungen** ([state.py](aifred/state.py)):
  - Entfernung von 233 Zeilen totem Code
  - Zentralisierung von URL-Konstanten in `config.py`
  - Nutzung von `model_discovery.py` für Backend-Model-Discovery

---

## [2.15.1] - 2025-12-30

### 🔧 API Fixes & Improvements

#### Fixed

- **`<think>` Tag Handling** ([api.py](aifred/lib/api.py)):
  - `chat_history` (UI) enthält jetzt korrekt die vollständige Antwort MIT `<think>` Tags
  - `llm_history` (LLM) enthält die bereinigte Antwort OHNE `<think>` Tags
  - Vorher war es vertauscht - führte zu LLM-Wiederholungen

- **Session Clear via API** ([state.py](aifred/state.py)):
  - `_restore_session()` setzt jetzt auch leere Listen korrekt
  - Vorher: Leere `chat_history=[]` wurde ignoriert, alte History blieb erhalten

#### Added

- **API-Inferenz Logging** ([api.py](aifred/lib/api.py)):
  - Auffällige Start/Ende-Markierungen in Debug-Console und Log-Datei
  - `⚠️ API-INFERENZ GESTARTET` / `✅ API-INFERENZ ABGESCHLOSSEN`
  - Nutzt standardisierte `CONSOLE_SEPARATOR` Länge

---

## [2.15.0] - 2025-12-30

### 🌐 REST API für Remote-Steuerung

**Vollständige REST-API für programmatische Steuerung von AIfred - ermöglicht Fernsteuerung via Cloud, Automatisierung und Drittanbieter-Integration.**

#### Added

- **REST API** ([api.py](aifred/lib/api.py)):
  - FastAPI-basierte REST-Schnittstelle auf Port 8002
  - OpenAPI/Swagger-Dokumentation unter `/docs`
  - CORS-Unterstützung für Cross-Origin-Requests

- **API Endpoints**:
  - `GET /api/health` - Health-Check mit Backend-Status
  - `GET /api/settings` - Alle Einstellungen abrufen
  - `PATCH /api/settings` - Einstellungen ändern (partielles Update)
  - `GET /api/models` - Verfügbare Modelle auflisten
  - `POST /api/chat/send` - Nachricht senden und Antwort erhalten
  - `GET /api/chat/history` - Chat-Verlauf abrufen
  - `DELETE /api/chat/clear` - Chat-Verlauf löschen
  - `GET /api/sessions` - Alle Browser-Sessions auflisten
  - `POST /api/system/restart` - AIfred neustarten (Systemd)

- **Browser-Synchronisation** ([session_storage.py](aifred/lib/session_storage.py), [state.py](aifred/state.py)):
  - **Chat-Sync**: API-Änderungen erscheinen automatisch im Browser (per-session Flag)
  - **Settings-Sync**: Einstellungsänderungen via API werden live im Browser aktualisiert (globales Flag)
  - Flag-File-Polling alle 2 Sekunden via `refresh_debug_console()`
  - Keine manuelle Browser-Aktualisierung nötig

- **Session-Discovery** ([session_storage.py](aifred/lib/session_storage.py)):
  - `list_sessions()` - Alle verfügbaren Sessions mit device_id, last_seen, message_count
  - `get_latest_session_file()` - Zuletzt aktive Session für API-Zugriff

- **Settings Update Flags** ([session_storage.py](aifred/lib/session_storage.py)):
  - `set_settings_update_flag()` - Globales Flag für alle Browser
  - `check_and_clear_settings_update_flag()` - Flag-Prüfung und Löschung
  - Separate Flags für Chat (per-session) und Settings (global)

- **State Reload** ([state.py](aifred/state.py)):
  - `_reload_settings_from_file()` - Lädt alle Settings aus settings.json neu
  - Aktualisiert Model-IDs, RoPE-Faktoren, Temperature, Multi-Agent-Mode, TTS, etc.
  - Integration in `refresh_debug_console()` für automatische Updates

#### Use Cases

- **Cloud-Steuerung**: AIfred von überall steuern via HTTPS/API
- **Home-Automation**: Integration mit Home Assistant, Node-RED, etc.
- **Voice Assistants**: Alexa/Google Home können AIfred-Anfragen senden
- **Batch-Processing**: Automatisierte Abfragen via Scripts
- **Mobile Apps**: Custom-Apps können die API nutzen

#### API Beispiele

```bash
# Einstellungen abrufen
curl http://localhost:8002/api/settings

# Model ändern
curl -X PATCH http://localhost:8002/api/settings \
  -H "Content-Type: application/json" \
  -d '{"aifred_model": "qwen3:14b", "sokrates_rope_factor": 2.0}'

# Nachricht senden (mit Browser-Sync)
curl -X POST http://localhost:8002/api/chat/send \
  -H "Content-Type: application/json" \
  -d '{"message": "Was ist Python?", "device_id": "abc123..."}'

# Alle Sessions auflisten
curl http://localhost:8002/api/sessions
```

## [2.14.6] - 2025-12-29

### 🔧 Multi-Agent Compression & Debugging

**Agent-spezifische Kompression und verbessertes RAW Message Debugging.**

#### Fixed

- **Agent-spezifische Compression** ([multi_agent.py](aifred/lib/multi_agent.py)):
  - Compression verwendet jetzt das Context-Limit des NÄCHSTEN Agenten statt `min_ctx`
  - PRE-SOKRATES: Verwendet `sokrates_num_ctx`
  - PRE-SALOMO: Verwendet `salomo_num_ctx`
  - PRE-AIFRED: Verwendet `main_llm_ctx`
  - Verhindert Context-Overflow bei Agenten mit unterschiedlichen Limits

- **Direct Response Perspektiven** ([multi_agent.py](aifred/lib/multi_agent.py)):
  - `run_sokrates_direct_response()` verwendet jetzt `perspective="sokrates"`
  - `run_salomo_direct_response()` verwendet jetzt `perspective="salomo"`
  - Korrekte Rollenzuweisung auch bei direkter Ansprache

#### Added

- **RAW Message Logging** ([multi_agent.py](aifred/lib/multi_agent.py)):
  - Neue Funktion `_log_raw_messages()` für Debug-Logging
  - Zeigt alle Messages die an LLMs gesendet werden
  - Kontrolliert durch `DEBUG_LOG_RAW_MESSAGES` in config.py
  - Hilft bei Debugging von Prompt-Injection und Agent-Confusion

- **Salomo Context Cache** ([multi_agent.py](aifred/lib/multi_agent.py)):
  - `_last_vram_limit_cache["salomo_limit"]` speichert Salomo's Context-Limit
  - Konsistente 3-Agent-Konfiguration mit separaten Limits

#### Changed

- **Refinement Prompts** ([prompts/de/aifred/refinement.txt](prompts/de/aifred/refinement.txt)):
  - Vereinfacht und fokussiert auf Kernaufgabe
  - Entfernt überflüssige Formatierungsanweisungen
  - Konsistente Struktur für DE und EN

- **History Summarization** ([prompts/de/history_summarization.txt](prompts/de/history_summarization.txt)):
  - Klarere FORMAT A/B Unterscheidung
  - Explizite Regel: NUR tatsächliche Runden dokumentieren
  - Keine erfundenen Runden mehr

## [2.14.5] - 2025-12-29

### 🔀 Hybrid-Mode RoPE Calibration

**Inkrementelle RoPE-Kalibrierung mit Hybrid-Mode-Kontinuität für erweiterte Kontextfenster.**

#### Added

- **force_hybrid Parameter** ([ollama.py](aifred/backends/ollama.py)):
  - Neuer Parameter `force_hybrid=True` überspringt GPU-only Erkennung
  - Wenn 1.0x Hybrid war, starten 1.5x/2.0x direkt im Hybrid-Mode
  - Vermeidet unnötige Binary-Search von 8K

- **min_context Parameter** ([ollama.py](aifred/backends/ollama.py)):
  - Neuer Parameter `min_context` setzt untere Grenze für Binary Search
  - RoPE 1.5x startet beim 1.0x Ergebnis (nicht bei 8K)
  - RoPE 2.0x startet beim 1.5x Ergebnis (inkrementell)

- **Inkrementeller RoPE-Loop** ([state.py](aifred/state.py)):
  - `prev_ctx` Variable speichert vorheriges Ergebnis
  - Jeder RoPE-Faktor startet beim Ergebnis des vorherigen
  - Beispiel: 40K → 61K → 81K statt 8K → 8K → 8K

- **Hybrid-Mode Kontinuität** ([state.py](aifred/state.py)):
  - `is_hybrid_mode` Flag wird aus 1.0x Ergebnis extrahiert
  - Wird an alle RoPE-Kalibrierungen weitergegeben
  - Cache speichert `is_hybrid: true/false` pro Kalibrierung

#### Changed

- **__RESULT__ Protokoll** ([ollama.py](aifred/backends/ollama.py)):
  - Neues Format: `__RESULT__:{ctx}:{mode}` (vorher: `__RESULT__:{ctx}`)
  - `mode` ist `gpu`, `hybrid`, oder `error`
  - Ermöglicht Hybrid-Mode-Erkennung im Caller

- **Skip-Logik bei Memory-Limit** ([state.py](aifred/state.py)):
  - RoPE wird nur übersprungen wenn `calibrated_ctx < native_ctx`
  - Hybrid-Mode mit vollem Native-Context testet weiterhin RoPE
  - RAM könnte mehr Headroom haben als VRAM

#### Documentation

- **Neues Flussdiagramm** ([OLLAMA_CONTEXT_CALIBRATION.md](docs/plans/OLLAMA_CONTEXT_CALIBRATION.md)):
  - ASCII-Flowchart mit kompletter Entscheidungslogik
  - Tabellen für Nach-1.0x-Entscheidungen
  - Beispiel-Log von erfolgreicher Kalibrierung

- **README.de.md**: Kalibrierungs-Sektion gekürzt mit Link zur Detail-Dokumentation

## [2.14.4] - 2025-12-29

### 📐 Smart RoPE Calibration & VRAM Optimization

**Intelligente Kalibrierung aller RoPE-Faktoren mit automatischer VRAM-Limit-Erkennung.**

#### Added

- **Full RoPE Calibration** ([state.py](aifred/state.py)):
  - Kalibriert jetzt alle drei RoPE-Faktoren (1.0x, 1.5x, 2.0x) sequenziell
  - Jeder Faktor wird einzeln getestet und im Cache gespeichert
  - Separator-Linien zwischen Kalibrierungen für bessere Lesbarkeit

- **VRAM-Limited Auto-Detection** ([state.py](aifred/state.py)):
  - Erkennt automatisch wenn VRAM der Flaschenhals ist (calibrated < native)
  - Bei VRAM-Limit: RoPE-Scaling bringt keinen Vorteil
  - Setzt 1.5x und 2.0x automatisch auf den 1.0x-Wert
  - Überspringt unnötige Kalibrierungs-Tests → schnellerer Startup
  - Markiert auto-gesetzte Werte mit "(auto)" im Summary

- **Dynamic VRAM Stabilization** ([ollama.py](aifred/backends/ollama.py)):
  - Neue Funktion `wait_for_vram_stable()` ersetzt fixen 2s Sleep
  - Pollt VRAM bis es stabil ist (2 konsekutive Messungen < 100MB Änderung)
  - Funktioniert mit langsamen GPUs wie Tesla P40
  - Timeout nach 10 Sekunden mit Fallback

#### Changed

- **Disabled Manual Model Unload** ([ollama.py](aifred/backends/ollama.py)):
  - `unload_all_models()` vor Kalibrierung deaktiviert
  - Ollama verwaltet VRAM automatisch via LRU
  - Unnötige Unloads verursachten Wartezeiten ohne Nutzen

- **Removed Auto-Set RoPE 2x Logic** ([ollama.py](aifred/backends/ollama.py)):
  - Alte Logik setzte automatisch RoPE 2x wenn 1x kalibriert wurde
  - Redundant mit neuer sequenzieller Kalibrierung
  - Entfernt um doppelte Console-Ausgaben zu vermeiden

#### Fixed

- **Debug Console Formatting**:
  - Separator-Linie nach "Desktop device detected" für klaren Startup-Abschluss
  - Leerzeile vor Summary entfernt
  - Abschließende Separator-Linie nach Kalibrierungs-Summary

## [2.14.3] - 2025-12-28

### 🎯 Intent Detection Improvements & Performance Optimizations

**Kombinierte Intent + Addressee Detection in einem LLM-Call, verbesserte Direktansprache-Erkennung und VRAM-Optimierung.**

#### Added

- **Combined Intent + Addressee Detection** ([intent_detector.py](aifred/lib/intent_detector.py)):
  - Neue Funktion `detect_query_intent_and_addressee()` kombiniert beide in einem Call
  - Gibt Tuple zurück: `(intent, addressee, raw_response)`
  - Raw Response wird in Debug-Konsole angezeigt für Transparenz
  - Eliminiert doppelte Intent-Detection (war vorher Bug)

- **Temperature Offsets in Config** ([config.py](aifred/lib/config.py)):
  - `SOKRATES_TEMPERATURE_OFFSET = 0.2` - Sokrates ist etwas kreativer
  - `SALOMO_TEMPERATURE_OFFSET = 0.3` - Salomo ist am kreativsten
  - Offsets werden auf AIfred's Temperature addiert

- **Salomo Direct Address Prompts** ([prompts/de/salomo/direct.txt](prompts/de/salomo/direct.txt), [prompts/en/salomo/direct.txt](prompts/en/salomo/direct.txt)):
  - Neue Prompts für direkte Ansprache an Salomo
  - Klare Regeln: Antwortet dem USER, nicht AIfred/Sokrates
  - Hebräische Weisheits-Einsprengsel (Nu, Emet, Davka)

#### Fixed

- **AIfred responded in English despite German UI** ([system_minimal.txt](prompts/de/aifred/system_minimal.txt)):
  - Problem: Britische Einsprengsel (Quite so, Indeed) ließen LLM auf Englisch antworten
  - Fix: Explizite Anweisung "KRITISCH: Antworte IMMER auf DEUTSCH!"
  - Nur Einsprengsel dürfen englisch sein, Rest muss deutsch sein

- **Wrong Addressee Detection** ([intent_detection.txt](prompts/de/intent_detection.txt)):
  - Problem: "Lieber Sokrates, was sagst du zu Salomo?" erkannte Salomo statt Sokrates
  - Fix: Explizite Beispiele für Addressee vs. Topic Unterscheidung
  - "Wer wird ANGESPROCHEN" vs. "Wer ist nur THEMA"

- **Duplicate Intent Detection** ([state.py](aifred/state.py)):
  - Problem: Intent wurde zweimal detected mit unterschiedlichen Ergebnissen
  - Fix: Einmaliger Call, `detected_intent` wird wiederverwendet

#### Changed

- **KREATIV Temperature** ([config.py](aifred/lib/config.py)):
  - Reduziert von 1.1 auf 1.0 (war inkonsistent mit Sokrates/Salomo Cap)

- **Debug Output auf Englisch** ([state.py](aifred/state.py)):
  - Intent Detection Debug: "🎯 Intent: ... → Addressee: ..."
  - Temperature Debug: "🌡️ Temperature: X.X (auto, creative)"
  - Zahlen mit `format_number()` formatiert

#### Performance

- **VRAM Unload deaktiviert** ([ollama.py](aifred/backends/ollama.py)):
  - `unload_all_models()` in `calculate_practical_context()` auskommentiert
  - Ollama managt VRAM automatisch mit LRU-Strategie
  - Spart ~2s Latenz pro Request (kein Warten auf VRAM-Release)
  - Für kalibrierte Modelle war der Unload sowieso unnötig (früher Return aus Cache)

#### Technical Details

```
Intent Detection Output Format:
  "FAKTISCH|sokrates" → intent=FAKTISCH, addressee=sokrates
  "KREATIV|"          → intent=KREATIV, addressee=None
  "GEMISCHT|aifred"   → intent=GEMISCHT, addressee=aifred

Temperature Calculation (Multi-Agent):
  AIfred:   base_temp (from intent or manual)
  Sokrates: base_temp + 0.2 (capped at 1.0)
  Salomo:   base_temp + 0.3 (capped at 1.0)

VRAM Flow (kalibrierte Modelle):
  calculate_practical_context()
    → calculate_vram_based_context()
      → Cache-Lookup (calibrated max_context)
      → EARLY RETURN (kein VRAM-Messung, kein Unload!)
```

#### Files Changed

- [aifred/backends/ollama.py](aifred/backends/ollama.py): Unload disabled
- [aifred/lib/config.py](aifred/lib/config.py): Temperature offsets, KREATIV=1.0
- [aifred/lib/intent_detector.py](aifred/lib/intent_detector.py): Combined detection
- [aifred/lib/multi_agent.py](aifred/lib/multi_agent.py): Use config offsets
- [aifred/state.py](aifred/state.py): Single intent call, debug output
- [prompts/de/aifred/system_minimal.txt](prompts/de/aifred/system_minimal.txt): German enforcement
- [prompts/de/intent_detection.txt](prompts/de/intent_detection.txt): Addressee examples
- [prompts/en/intent_detection.txt](prompts/en/intent_detection.txt): Addressee examples
- [prompts/de/salomo/direct.txt](prompts/de/salomo/direct.txt): New
- [prompts/en/salomo/direct.txt](prompts/en/salomo/direct.txt): New

---

## [2.14.2] - 2025-12-27

### 📋 Inline Summary Placement & UI Improvements

**Summaries erscheinen jetzt inline im Chat an der Stelle wo komprimiert wurde, nicht mehr am Anfang.**

#### Added

- **Inline Summary Collapsibles** ([aifred.py](aifred/aifred.py)):
  - `render_inline_summary()` - Rendert Summaries inline als Collapsibles
  - Neue Optik: 📋 Zusammenfassung #N (X Messages) - Timestamp
  - i18n: "Zusammenfassung" (DE) / "Summary" (EN)

- **FIFO-Separation** ([context_manager.py](aifred/lib/context_manager.py)):
  - `chat_history` (UI): Behält ALLE Summaries für vollständige Anzeige
  - `llm_history` (LLM): Wendet FIFO an (nur neueste Summary bleibt)
  - User sieht immer die komplette History

#### Fixed

- **Summary-Nummerierung** ([context_manager.py](aifred/lib/context_manager.py)):
  - Bug: Beide Summaries hatten #1 statt #1 und #2
  - Ursache: `len(preserved_summaries)` fand nur Summaries am ANFANG
  - Fix: `count_summaries(history)` zählt ALLE Summaries in der History

#### Removed

- **Toter Code bereinigt**:
  - `render_unified_summaries()` - nicht mehr benötigt
  - `render_single_summary_box()` - nicht mehr benötigt
  - `all_summaries` property - nicht mehr benötigt
  - `chat_history_without_summaries` property - nicht mehr benötigt
  - `total_summary_tokens` property - nicht mehr benötigt

#### Technical Details

```
Vorher (oben, gruppiert):          Nachher (inline, wo komprimiert):
┌── Summaries ──────────────┐      [User Message 1]
│ [#1] [#2] [#3]           │      [AI Response 1]
└───────────────────────────┘      ┌── 📋 Zusammenfassung #1 ──┐
[User Message 1]                   └───────────────────────────┘
[AI Response 1]                    [User Message 3]
[User Message 2]                   [AI Response 3]
...                                ┌── 📋 Zusammenfassung #2 ──┐
                                   └───────────────────────────┘
```

---

## [2.14.0] - 2025-12-27

### 🗳️ 3-Agent Consensus Voting System

**Alle drei Agenten stimmen jetzt mit [LGTM]/[WEITER] Tags ab. Konfigurierbarer Konsens-Typ: Majority (2/3) oder Unanimous (3/3).**

#### Added

- **3-Agent Voting** ([multi_agent.py](aifred/lib/multi_agent.py)):
  - `count_lgtm_votes()` - Zählt Votes von AIfred, Sokrates, Salomo
  - `check_consensus()` - Prüft ob Konsens erreicht (majority/unanimous)
  - `format_votes_debug()` - Formatiert Vote-Status für Debug-Ausgabe
  - `[WEITER]` überschreibt `[LGTM]` für Negations-Fälle

- **Consensus Type Setting** ([state.py](aifred/state.py)):
  - `consensus_type: str = "majority"` - Wählbar in UI
  - Majority: 2/3 Agents müssen `[LGTM]` sagen
  - Unanimous: Alle 3 Agents müssen `[LGTM]` sagen

- **UI Toggle** ([aifred.py](aifred/aifred.py)):
  - Segment-Control für Konsens-Typ (nur im Auto-Consensus Modus sichtbar)
  - i18n Labels für DE/EN

- **Updated Prompts** ([prompts/](prompts/)):
  - Alle Agenten-Prompts (AIfred, Sokrates, Salomo) mit Voting-Instructions
  - DE + EN Varianten

#### Changed

- **Trialog Workflow** erweitert:
  - Nach jeder Runde: Votes von allen 3 Agenten gezählt
  - Bei Konsens: Debatte beendet
  - Debug-Log zeigt Vote-Status pro Runde

#### Technical Details

```
┌─────────────┐     ┌─────────────────┐     ┌─────────────────────┐
│   User      │────▶│   🎩 AIfred     │────▶│   🏛️ Sokrates       │
│   Query     │     │   + [LGTM/WEITER]│     │   + [LGTM/WEITER]  │
└─────────────┘     └─────────────────┘     └──────────┬──────────┘
                                                       │
                              ┌─────────────────────────┘
                              ▼
                    ┌─────────────────────┐
                    │   👑 Salomo         │
                    │   + [LGTM/WEITER]   │
                    └──────────┬──────────┘
                               │
               ┌───────────────┴───────────────┐
               ▼                               ▼
     ┌────────────────┐              ┌─────────────────┐
     │ 2/3 or 3/3     │              │ Not enough votes│
     │ = Consensus!   │              │ = Next Round    │
     └────────────────┘              └─────────────────┘
```

---

## [2.13.0] - 2025-12-27

### 📚 Dual Chat-History Architecture

**Zwei parallele Datenstrukturen: chat_history (UI, vollständig) und llm_history (LLM, komprimiert). User verliert nie Kontext, auch bei kleinen Modellen.**

#### Added

- **`llm_history`** ([state.py](aifred/state.py)):
  - Neue State-Variable: `llm_history: List[Dict[str, str]] = []`
  - Ready-to-use Format für LLM-Aufrufe: `{"role": "user/assistant/system", "content": "..."}`
  - Parallel zu `chat_history` geführt

- **Dual-Sync bei neuen Messages** ([state.py](aifred/state.py)):
  - User-Message: Append zu beiden Histories
  - AI-Response: Update `chat_history`, Append zu `llm_history`
  - Agent-Responses als System-Messages mit Speaker-Label `[SOKRATES]:`, `[SALOMO]:`, `[AIFRED]:`

- **Session-Speicherung erweitert** ([state.py](aifred/state.py)):
  - Beide Histories werden in Session gespeichert
  - Keine Rekonstruktion beim Laden nötig

- **`clean_content_for_llm()`** ([message_builder.py](aifred/lib/message_builder.py)):
  - Entfernt HTML-Tags, Metadaten, Timing-Patterns
  - Bereinigt Content für LLM-History

#### Changed

- **Multi-Agent llm_history Sync** ([multi_agent.py](aifred/lib/multi_agent.py)):
  - `_stream_sokrates_to_history()` synct zu llm_history
  - `_stream_alfred_refinement()` synct zu llm_history
  - `_stream_salomo_to_history()` synct zu llm_history
  - `run_sokrates_direct_response()` synct zu llm_history

- **Kompression arbeitet auf llm_history** ([context_manager.py](aifred/lib/context_manager.py)):
  - `chat_history`: Summary-Eintrag eingefügt (Original-Messages bleiben!)
  - `llm_history`: Alte Messages durch Summary ersetzt

#### Removed

- **`_reconstruct_llm_history()`** - Keine Fallback-Migration (alte Sessions starten leer)

#### Technical Details

```python
# Parallele Datenstrukturen
chat_history = [
    ("Wetter?", "15°C sonnig"),                              # Original bleibt
    ("", "[📊 Summary #1|2 Msgs|14:30]\n• Wetter"),           # Summary eingefügt
    ("Aktuell", "Aktuelle Antwort"),
]

llm_history = [
    {"role": "system", "content": "[Summary]\n• Wetter"},     # Summary ersetzt
    {"role": "user", "content": "Aktuell"},
    {"role": "assistant", "content": "Aktuelle Antwort"},
]
```

---

## [2.12.0] - 2025-12-27

### 📊 Unified Summary Collapsible & PRE-MESSAGE Compression

**History-Kompression wurde komplett überarbeitet: PRE-MESSAGE statt POST-RESPONSE, dynamisches max_summaries basierend auf Context-Größe, und ein einheitliches Collapsible für alle Summaries.**

#### Added

- **Unified Summary Collapsible** ([aifred.py](aifred/aifred.py)):
  - Alle Summaries in einem einzigen aufklappbaren Container
  - Jede Summary als separate Box mit Header (Nummer, Message-Count, Timestamp)
  - Token-Übersicht im Collapsible-Header (~X tok)
  - Collapsed by default, FIFO-Reihenfolge (älteste zuerst)

- **Dynamisches max_summaries** ([context_manager.py](aifred/lib/context_manager.py)):
  - `calculate_max_summaries(context_limit)` - berechnet basierend auf 20% Context-Budget
  - 4K Context → max 1-2 Summaries
  - 8K Context → max 3 Summaries
  - 32K+ Context → max 10 Summaries (gedeckelt)
  - Neue Config: `HISTORY_SUMMARY_MAX_RATIO = 0.2`

- **Neues Summary-Format**:
  - Alt: `[📊 Compressed: N Messages]`
  - Neu: `[📊 Summary #N|X Messages|DD.MM.YYYY HH:MM]`
  - Abwärtskompatibel: Erkennt beide Formate

- **State-Variablen für UI** ([state.py](aifred/state.py)):
  - `all_summaries` - Extrahiert alle Summaries für Unified Collapsible
  - `chat_history_without_summaries` - Chat ohne Summaries für normale Anzeige
  - `total_summary_tokens` - Geschätzte Token-Anzahl aller Summaries
  - `ChatMessageParsed` erweitert um Summary-Felder

- **Helper-Funktionen** ([context_manager.py](aifred/lib/context_manager.py)):
  - `is_summary_entry()` - Erkennt alte und neue Summary-Formate
  - `count_summaries()` - Zählt Summaries in History

#### Changed

- **PRE-MESSAGE statt POST-RESPONSE Compression** ([multi_agent.py](aifred/lib/multi_agent.py)):
  - Kompression VOR jedem LLM-Aufruf (nicht danach)
  - Löst Session-Restore Problem: Modell-Wechsel → Kein Overflow mehr
  - Multi-Agent: PRE-CHECK vor Sokrates, Salomo, AIfred-Revision
  - `_check_compression_if_needed()` als zentrale Funktion

- **FIFO aggressiver bei kleinem Context**:
  - Bei max_summaries=1: Älteste Summary wird gelöscht vor neuer
  - Garantiert: Nie mehr Summaries als Context erlaubt
  - Debug-Log zeigt FIFO-Aktionen

- **Chat-Rendering separiert** ([aifred.py](aifred/aifred.py)):
  - `render_unified_summaries()` oben im Chat
  - `chat_history_without_summaries` für normale Messages
  - Alte inline-Summary-Darstellung entfernt

- **Share-Chat erweitert** ([state.py](aifred/state.py)):
  - Erkennt neues Summary-Format beim Export
  - Salomo-Messages werden korrekt erkannt

#### Technical Details

**Dynamisches max_summaries:**
```python
# 20% des Context für Summaries reserviert
max_summary_budget = context_limit * 0.2
max_summaries = max(1, max_summary_budget // 500)
# Gedeckelt bei HISTORY_MAX_SUMMARIES (10)
```

**PRE-MESSAGE Check:**
```python
# VOR dem Hinzufügen einer neuen Nachricht
async for _ in _check_compression_if_needed(state, llm_client, min_ctx):
    yield
# Jetzt erst die neue Nachricht hinzufügen
self.chat_history.append((user_msg, ""))
```

---

## [2.11.0] - 2025-12-26

### 👑 Salomo - The Wise Judge (NEW AGENT)

**Neuer dritter Agent für Multi-Agent-Diskussionen: Salomo als weiser Vermittler und Richter.**

#### Added

- **Salomo Agent** - Dritter Agent im Multi-Agent-System:
  - 👑 König Salomo - bekannt für weise Urteile
  - Ruhiger, abwägender Sprachstil (nicht religiös-salbungsvoll)
  - Zwei Rollen: Vermittler (Auto-Konsens) und Richter (Tribunal)

- **Tribunal Mode** (NEW):
  - AIfred und Sokrates debattieren für X Runden
  - Salomo fällt am Ende ein finales Urteil
  - Wägt beide Standpunkte ab und entscheidet

- **Trialog-Workflow** (Auto-Konsens erweitert):
  - AIfred → Sokrates → Salomo (pro Runde)
  - Salomo synthetisiert und entscheidet ob LGTM
  - Sokrates kritisiert nur noch - sagt nie mehr LGTM

- **Salomo-Prompts** ([prompts/de/salomo/](prompts/de/salomo/), [prompts/en/salomo/](prompts/en/salomo/)):
  - `system_minimal.txt` - Basis-Persönlichkeit
  - `mediator.txt` - Für Auto-Konsens (Synthese)
  - `judge.txt` - Für Tribunal (Urteil)

- **Help Modal für Diskussionsmodi** ([aifred.py](aifred/aifred.py)):
  - 💡 Glühbirnen-Icon öffnet Übersicht aller Modi
  - Tabelle mit Ablauf und "Wer entscheidet?"
  - Agenten-Beschreibungen mit Emojis
  - Desktop + Mobile kompatibel

- **Multi-Agent-Modi Dokumentation** ([docs/multi-agent-modes.md](docs/multi-agent-modes.md)):
  - Vollständige Übersicht aller 5 Modi
  - Ablauf-Diagramme für Trialog und Tribunal

#### Changed

- **Sokrates-Prompts vereinfacht** ([prompts/de/sokrates/critic.txt](prompts/de/sokrates/critic.txt)):
  - LGTM-Logik komplett entfernt
  - Sokrates kritisiert nur - Salomo entscheidet
  - Klarere Rollenverteilung

- **AIfred-Prompts präzisiert** ([prompts/de/aifred/system_minimal.txt](prompts/de/aifred/system_minimal.txt)):
  - "NIEMALS archaisch-philosophisch sprechen"
  - Keine sokratischen rhetorischen Fragen
  - Butler-Charakter verstärkt

- **State erweitert** ([state.py](aifred/state.py)):
  - `salomo_model`, `salomo_temperature` etc.
  - `multi_agent_help_open` für Help-Modal
  - `ChatMessageParsed` um `salomo_mode`, `salomo_content`

- **i18n Labels** ([i18n.py](aifred/lib/i18n.py)):
  - 20+ neue Übersetzungsschlüssel für Salomo und Help-Modal
  - DE + EN vollständig

---

## [2.10.6] - 2025-12-26

### 🔧 Hybrid Mode for Large Models

**Intelligente Kalibrierung für Modelle größer als VRAM mit CPU-Offloading.**

#### Added

- **Hybrid Mode Detection** ([ollama.py](aifred/backends/ollama.py)):
  - Automatische Erkennung wenn Modell > VRAM
  - Direktberechnung statt iterativer 2K-Schritte (1-3 statt 15+ Lade-Versuche)
  - MoE vs Dense Erkennung (0.10 vs 0.15 MB/Token Ratio)
  - Fine-Tuning nach initialem Laden (±25% Anpassungen)

- **Dynamic RAM Reserve** ([gpu_utils.py](aifred/lib/gpu_utils.py)):
  - 32+ GB frei → 8 GB Reserve
  - 16-32 GB frei → 6 GB Reserve
  - 8-16 GB frei → 4 GB Reserve
  - 4-8 GB frei → 3 GB Reserve
  - <4 GB frei → 2 GB Reserve (Minimum)

- **Neue Konstanten** ([config.py](aifred/lib/config.py)):
  - `RAM_RESERVE_MIN = 2048` (Minimum-Reserve)
  - `RAM_RESERVE_COMFORT = 8192` (Maximum-Reserve für große Systeme)

#### Changed

- **Model Size via /api/tags** ([ollama.py](aifred/backends/ollama.py)):
  - Modellgröße direkt von Ollama API statt Blob-Pfad-Parsing
  - Zuverlässiger und weniger fehleranfällig

- **README Dokumentation** ([README.md](README.md), [README.de.md](README.de.md)):
  - Ablauf-Schema für Hybrid-Mode hinzugefügt
  - Feature-Beschreibung erweitert

#### Tested

- Erfolgreich getestet mit 30+ GB Modell auf System mit begrenztem VRAM

---

## [2.10.5] - 2025-12-26

### 🎨 UI/UX Improvements

**UI-Optimierungen: Kompakteres Layout, Info-Tooltips, User-Name in Einstellungen verschoben.**

#### Added

- **Info-Tooltips mit Hover-Cards** ([aifred.py](aifred/aifred.py)):
  - Erklärungstexte durch Info-Icons (ℹ️) ersetzt
  - Hover zeigt Hilfetext im Dark-Mode Stil
  - Auf Mobile ausgeblendet (kein Hover möglich)
  - Betrifft: Bild-Upload Hint, Recherche-Modus, Diskussionsmodus

- **Separate Context Window für Sokrates** ([state.py](aifred/state.py), [multi_agent.py](aifred/lib/multi_agent.py)):
  - Neues Feld `num_ctx_manual_sokrates` im Manual-Modus
  - Zwei Input-Felder nebeneinander im LLM-Parameter Accordion
  - Sokrates kann anderen Context als AIfred haben

#### Changed

- **User-Name Input verschoben** ([aifred.py](aifred/aifred.py)):
  - Von Button-Zeile in Einstellungen verschoben
  - Jetzt neben UI-Sprache Dropdown
  - Behält orangenes Styling

- **LLM-Parameter Accordion kompakter** ([aifred.py](aifred/aifred.py)):
  - Neben Diskussionsmodus-Dropdown positioniert
  - Höhe reduziert, Select-ähnliches Styling

- **Diskussionsmodus-Info verbessert** ([i18n.py](aifred/lib/i18n.py)):
  - Auto-Konsens Text erweitert: "LGTM (Looks Good To Me)"
  - Icon von 🤝 auf 💬 geändert (bessere Darstellung)

- **Settings-Bereich aufgeräumt** ([aifred.py](aifred/aifred.py), [i18n.py](aifred/lib/i18n.py)):
  - Selbsterklärende Hinweistexte entfernt (F5/Browser, Button/Grundeinstellungen)
  - Neustart-Infos vereinfacht mit 💡 Icon
  - Backend: "Entlädt Models aus VRAM"
  - AIfred: "Debug-Logs werden geleert, Sessions bleiben erhalten"

---

## [2.10.4] - 2025-12-25

### 🌡️ Temperature Control Refactoring

**Temperature-Steuerung für Multi-Agent Modus vollständig refaktoriert - keine hardcodierten Werte mehr.**

#### Added

- **Temperature Auto/Manual Mode** ([state.py](aifred/state.py)):
  - `temperature_mode`: "auto" (Intent-Detection) oder "manual" (User-Slider)
  - Auto-Modus: Intent-Detection bestimmt Basis-Temperatur (FAKTISCH=0.2, GEMISCHT=0.5, KREATIV=1.1)
  - Manual-Modus: Separate Slider für AIfred und Sokrates

- **Sokrates Temperature Offset** ([state.py](aifred/state.py), [aifred.py](aifred/aifred.py)):
  - Konfigurierbarer Offset für Auto-Modus (Standard: +0.2)
  - Slider in UI: 0.0 bis 0.5 in 0.1er-Schritten
  - Sokrates = Intent-Temp + Offset (gedeckelt bei 1.0)

- **Temperature UI in LLM-Parameter** ([aifred.py](aifred/aifred.py)):
  - Temperature-Kontrolle aus Hauptbereich in "LLM-Parameter (Erweitert)" verschoben
  - Radio-Buttons für Auto/Manual Modus
  - Konditionale Slider je nach Modus

#### Changed

- **Multi-Agent Temperatures state-basiert** ([multi_agent.py](aifred/lib/multi_agent.py)):
  - Entfernt: Hardcodierte Temperaturen (0.3, 0.4, 0.5)
  - Neu: `state.temperature`, `state.sokrates_temperature`, `state.sokrates_temperature_offset`
  - Debug-Log zeigt verwendete Temperaturen

- **Intent-Detection schreibt in State** ([state.py](aifred/state.py)):
  - `self.temperature = final_temperature` nach Intent-Detection
  - Multi-Agent Modus liest jetzt korrekt die intent-basierte Temperatur

#### Technical Details

**Temperature-Berechnung:**
```python
# Auto-Modus
alfred_temp = state.temperature  # Von Intent-Detection
sokrates_temp = min(1.0, alfred_temp + state.sokrates_temperature_offset)

# Manual-Modus
alfred_temp = state.temperature  # User-Slider
sokrates_temp = state.sokrates_temperature  # Separater Slider
```

**Neue State-Variablen:**
```python
temperature: float = 0.3  # Default: niedrig für faktische Antworten
temperature_mode: str = "auto"
sokrates_temperature: float = 0.5  # Nur im Manual-Modus
sokrates_temperature_offset: float = 0.2  # Nur im Auto-Modus
```

---

## [2.10.3] - 2025-12-25

### 🏗️ Multi-Agent Architecture Refactoring

**Große Refaktorisierung: Multi-Agent Logik ausgelagert, Perspective-System implementiert, Sokrates-Prompts mit strukturiertem Format verstärkt.**

#### Added

- **Perspective-System für Multi-Agent Dialog** ([message_builder.py](aifred/lib/message_builder.py)):
  - Neuer `perspective` Parameter in `build_messages_from_history()`
  - `perspective="sokrates"`: Sokrates sieht AIfred als `[AIFRED]:` (user role)
  - `perspective="aifred"`: AIfred sieht Sokrates als `[SOKRATES]:` (user role)
  - Eigene frühere Antworten bleiben `assistant` role
  - Verhindert Identitätsverwechslung zwischen Agenten

- **Rundennummer-Platzhalter** ([prompts/*/sokrates/critic.txt](prompts/de/sokrates/critic.txt)):
  - `{round_num}` Platzhalter am Prompt-Anfang
  - Sokrates weiß jetzt explizit welche Runde es ist
  - Keine Hardcodierung mehr im Python-Code

- **DIMINISHING RETURNS Sektion** ([prompts/*/sokrates/critic.txt](prompts/de/sokrates/critic.txt)):
  - Neue Prompt-Sektion ab Runde 2
  - "Gut genug" Schwelle definiert
  - Perfektionismus verhindert Abschluss - LGTM früher möglich

- **Strukturiertes Prompt-Format**:
  - Visuelle Sektions-Trenner mit `═══════════════`
  - Checkbox-Style LGTM-Checkliste
  - Klare IF/THEN Runden-Logik
  - LGTM-Regeln: Stilistische Präferenzen sind KEINE validen Kritikgründe

- **AIfred Refinement Prompt** ([prompts/*/aifred/refinement.txt](prompts/de/aifred/refinement.txt)):
  - Neuer dedizierter Prompt für Synthese-Phase
  - Anleitung für echte Synthese statt Patchwork
  - 4-Schritte Vorgehen: Anerkennen → Behalten → Neu formulieren → Eigener Aspekt

#### Changed

- **Multi-Agent Logik ausgelagert** ([multi_agent.py](aifred/lib/multi_agent.py)):
  - ~600 Zeilen aus state.py nach multi_agent.py verschoben
  - Klare Trennung: State-Management vs. Agent-Logik
  - state.py: -633 Zeilen, multi_agent.py: +906 Zeilen
  - Bessere Wartbarkeit und Testbarkeit

- **Sokrates Critic Prompt komplett überarbeitet**:
  - Von ~30 auf ~100 Zeilen erweitert
  - Explizite Runden-Logik (Runde 1 vs. Runde 2+)
  - MAXIMAL 1-2 Kritikpunkte pro Runde
  - Pflicht-Sektion "ALTERNATIVE LÖSUNG"

- **Prompt-Loader erweitert** ([prompt_loader.py](aifred/lib/prompt_loader.py)):
  - `get_sokrates_critic_prompt(round_num)` akzeptiert jetzt Rundennummer
  - `{round_num}` Platzhalter wird automatisch ersetzt

#### Removed

- **Hardcodierte Round-Injection** ([multi_agent.py](aifred/lib/multi_agent.py)):
  - Entfernt: `round_context = f"AKTUELLE RUNDE: {round_num}..."`
  - Ersetzt durch Platzhalter im Prompt-Template

- **Sokrates Refinement Prompt** ([prompts/*/sokrates/refinement.txt](prompts/)):
  - Gelöscht - Refinement ist AIfred's Aufgabe, nicht Sokrates'

#### Technical Details

**Perspective-System Beispiel:**
```python
# Sokrates-Aufruf
messages = build_messages_from_history(
    state.chat_history,
    perspective="sokrates"  # AIfred → [AIFRED]: prefix
)

# AIfred-Refinement-Aufruf
messages = build_messages_from_history(
    state.chat_history,
    perspective="aifred"    # Sokrates → [SOKRATES]: prefix
)
```

**Strukturiertes Prompt-Format:**
```
AKTUELLE RUNDE: {round_num}

═══════════════════════════════════════════════════════════════
RUNDEN-LOGIK (STRIKT BEFOLGEN!)
═══════════════════════════════════════════════════════════════

WENN {round_num} = 1:
→ Überspringe "FORTSCHRITT" komplett
→ Beginne direkt mit "NEUE KRITIK"
```

**Affected Files:**
- `aifred/state.py` - Auslagerung der Multi-Agent Logik (-633 Zeilen)
- `aifred/lib/multi_agent.py` - Neue zentrale Agent-Logik (+906 Zeilen)
- `aifred/lib/message_builder.py` - Perspective-System
- `aifred/lib/prompt_loader.py` - Round-Platzhalter Support
- `prompts/de/sokrates/critic.txt` - Strukturiertes Format
- `prompts/en/sokrates/critic.txt` - Same in English
- `prompts/de/aifred/refinement.txt` - Neuer Synthese-Prompt
- `prompts/en/aifred/refinement.txt` - Same in English

---

## [2.10.2] - 2025-12-25

### 🎭 Multi-Agent Dialog Improvements

**Verbesserte Multi-Agent Konversationen: Klarere Rollenverteilung, besseres Context-Handling, erweiterte Dialog-Patterns.**

#### Added

- **Dialog Routing: Erweiterte Patterns** ([intent_detector.py:247-248, 284-285](aifred/lib/intent_detector.py)):
  - Neue Patterns für Namen nach Satzende: "...motiviert. Sokrates." / "...machen. Alfred."
  - Regex: `[.!?]\s*sokrates\s*[.!?]?\s*$` und `[.!?]\s*(?:ai\s*fred|aifred|alfred|eifred)\s*[.!?]?\s*$`
  - Ermöglicht natürlichere Adressierung am Satzende

- **Automatische Timestamp-Injektion** ([prompt_loader.py:131-158](aifred/lib/prompt_loader.py)):
  - Alle Prompts erhalten automatisch aktuelles Datum und Uhrzeit
  - DE: "AKTUELLES DATUM UND UHRZEIT: Mittwoch, 25.12.2025, 14:30:00 Uhr"
  - EN: "CURRENT DATE AND TIME: Wednesday, 2025-12-25, 14:30:00"
  - LLM kennt immer den aktuellen Zeitpunkt für zeitbezogene Fragen

- **Debug-Console Separatoren** ([state.py](aifred/state.py)):
  - Separator nach `_run_sokrates_direct_response()` hinzugefügt
  - Separator nach `_run_sokrates_analysis()` hinzugefügt
  - Konsistente visuelle Trennung aller Dialog-Phasen

- **TTFT Debug-Logging** ([state.py:3120-3144](aifred/state.py)):
  - Zusätzliche Timestamps zur Diagnose negativer TTFT-Werte
  - Logs: inference_start, first token time, calculated TTFT

#### Changed

- **Multi-Agent Messages als System Role** ([message_builder.py:121-131](aifred/lib/message_builder.py)):
  - Sokrates/AIfred Nachrichten jetzt mit `role: system` statt `role: assistant`
  - Prefix `[MULTI-AGENT CONTEXT]` für klare Trennung
  - Verhindert, dass LLM eigene Antworten mit Agent-Nachrichten verwechselt
  - Speaker-Labels: `[SOKRATES]:` und `[AIFRED]:` erhalten

- **AIfred Direct Prompt verstärkt** ([prompts/de/aifred/direct.txt](prompts/de/aifred/direct.txt), [prompts/en/aifred/direct.txt](prompts/en/aifred/direct.txt)):
  - Explizite Regel: "NIEMALS mit 'Was hältst du davon, Sokrates?' enden"
  - Klarstellung: "Sokrates ist NICHT im Gespräch - er ist nur Hintergrund-Kontext"
  - Verhindert, dass AIfred Sokrates direkt anspricht statt den User

- **Sokrates Direct Prompt: Context-Verständnis** ([prompts/de/sokrates/direct.txt](prompts/de/sokrates/direct.txt), [prompts/en/sokrates/direct.txt](prompts/en/sokrates/direct.txt)):
  - Neue Sektion: "KRITISCH - Kontext richtig verstehen"
  - Wenn User "die Antwort" lobt → bezieht sich meist auf AIfred's Antwort
  - Sokrates hat die Frage NICHT beantwortet, nur kritisiert
  - Verhindert falsches "Danke für dein Lob" wenn AIfred gemeint war

#### Fixed

- **Doppelte Separator-Linien in Debug-Console**:
  - Problem: Nach Multi-Agent Dialog erschienen zwei Separatoren
  - Ursache: Separator nach Main-LLM UND finaler Separator beide aktiv
  - Lösung: Finaler Separator nur bei `multi_agent_mode == "standard"`

#### Technical Details

**Multi-Agent Message Format:**
```python
# Vorher: role: assistant (verwirrte LLM)
{'role': 'assistant', 'content': '🏛️[Kritik] Deine Antwort...'}

# Nachher: role: system mit klarem Label
{'role': 'system', 'content': '[MULTI-AGENT CONTEXT]\n[SOKRATES]: Deine Antwort...'}
```

**Neue Dialog-Patterns:**
```
"Toll erklärt. Sokrates."     → detect_dialog_addressing() = ("sokrates", "Toll erklärt.")
"Prima gemacht. Alfred!"      → detect_dialog_addressing() = ("alfred", "Prima gemacht.")
```

**Affected Files:**
- `aifred/lib/intent_detector.py` - Erweiterte Adressierungs-Patterns
- `aifred/lib/message_builder.py` - Multi-Agent als System-Messages
- `aifred/lib/prompt_loader.py` - Timestamp-Injektion
- `aifred/state.py` - Separatoren, TTFT-Debug
- `prompts/de/aifred/direct.txt` - Verstärkte User-Fokussierung
- `prompts/en/aifred/direct.txt` - Same in English
- `prompts/de/sokrates/direct.txt` - Context-Verständnis
- `prompts/en/sokrates/direct.txt` - Same in English

---

## [2.10.1] - 2025-12-24

### 🎭 Dialog Routing & Calibration Improvements

**Direkte Adressierung von Sokrates oder AIfred, entfernte num_predict Limitierung, Kalibrierungs-Info bei Modellwechsel.**

#### Added

- **Dialog Routing: Direkte Agenten-Ansprache** ([intent_detector.py](aifred/lib/intent_detector.py), [state.py](aifred/state.py)):
  - Neue `detect_dialog_addressing()` Funktion erkennt direkte Anrede
  - **Sokrates direkt**: "Sokrates, warum denkst du...", "@sokrates", "Hey Sokrates"
  - **AIfred direkt**: "AIfred, erkläre...", "@alfred", "Eifred" (STT-Varianten)
  - Sokrates-Adressierung → Sokrates antwortet direkt mit sokratischer Methode
  - AIfred-Adressierung → AIfred antwortet ohne Sokrates-Analyse
  - Marker: "🏛️[Direkte Antwort]" / "🏛️[Direct Response]"

- **Kalibrierungs-Info bei Modellwechsel** ([state.py:4350-4368](aifred/state.py#L4350-L4368)):
  - Zeigt kalibrierten Kontext bei Modellauswahl an (Native und/oder RoPE 2x)
  - Warnung wenn Modell noch nicht kalibriert wurde
  - Debug-Ausgabe: "🎯 Calibrated: Native: 110K, RoPE 2x: 220K"

#### Changed

- **num_predict für Ollama entfernt** ([ollama.py:117-118, 305-306](aifred/backends/ollama.py)):
  - Problem: Safety Margin Berechnung limitierte DeepSeek auf 512 Tokens Output
  - Ollama generiert natürlich bis EOS oder Context voll - keine künstliche Begrenzung nötig
  - Betrifft sowohl Streaming als auch Non-Streaming Aufrufe

- **Binary Search Präzision erhöht** ([ollama.py](aifred/backends/ollama.py)):
  - Minimaler Schritt: 2048 → 512 Tokens
  - Feinere Granularität: 1024 bei <16k, 512 bei <8k Differenz
  - Genauere Kalibrierungswerte für maximale VRAM-Nutzung

#### Fixed

- **History-Kompression ignorierte manuellen num_ctx** ([state.py:4804-4809](aifred/state.py#L4804-L4809)):
  - Problem: Zeigte "Context limit: 40.960" obwohl manual auf 1.472 gesetzt
  - Lösung: Prüft jetzt `num_ctx_mode == "manual"` und verwendet `num_ctx_manual`
  - Fallback von 40k auf 32k reduziert (kleinster üblicher Context)

- **num_ctx Eingabe zu restriktiv** ([state.py](aifred/state.py)):
  - Problem: Werte wie 1472 wurden als "ungültiger Wert" abgelehnt
  - Minimum von 2048 auf 1 gesenkt
  - Locale-Formatierung wird akzeptiert (Punkte, Kommas, Leerzeichen als Tausendertrennzeichen)
  - `NUM_CTX_MANUAL_MAX` nach config.py verschoben (2M Tokens)

- **System-Instabilität bei RAM-Erschöpfung** ([ollama.py](aifred/backends/ollama.py)):
  - Problem: Nemotron 1M Context führte zu RAM-Erschöpfung und System-Freeze
  - Erkennung: 3 aufeinanderfolgende Fails <2s → System-Instabilität
  - Recovery: 5s Pause, Ollama Health-Check, Neustart mit 256k Ceiling
  - `RECOVERY_THRESHOLD = 262144`

#### Technical Details

**Dialog Routing Workflow:**
```
User: "Sokrates, was denkst du über KI?"
    ↓
detect_dialog_addressing() → ("sokrates", "was denkst du über KI?")
    ↓
_run_sokrates_direct_response()
    ↓
Sokrates antwortet mit sokratischer Methode
    ↓
Marker: 🏛️[Direkte Antwort]
```

**Affected Files:**
- `aifred/lib/intent_detector.py` - `detect_dialog_addressing()` function
- `aifred/state.py` - Dialog routing, `_run_sokrates_direct_response()`, compression fix
- `aifred/backends/ollama.py` - num_predict removal, precision increase, stability detection
- `aifred/lib/config.py` - `NUM_CTX_MANUAL_MAX` constant

---

## [2.10.0] - 2025-12-24

### 🎯 Ollama Context Calibration with RoPE 2x Support

**Per-model context calibration with optional RoPE 2x extended context window.**

#### Added

- **Context Calibration Button** ([aifred.py](aifred/aifred.py), [state.py](aifred/state.py)):
  - New "Context kalibrieren" button in LLM Parameters section
  - Binary search algorithm finds maximum context fitting entirely in VRAM
  - Uses Ollama `/api/ps` endpoint: `size == size_vram` → no CPU offload
  - Progress displayed in debug console during calibration

- **RoPE 2x Extended Mode** ([state.py:4155](aifred/state.py#L4155)):
  - Toggle "RoPE bis 2x" enables extended context calibration
  - Calibrates up to 2x native context limit via RoPE scaling
  - Per-model setting stored in `model_vram_cache.json`
  - Toggle state automatically loads when switching models

- **Dual Calibration System** ([model_vram_cache.py](aifred/lib/model_vram_cache.py)):
  - `max_context_gpu_only`: Native calibration (up to model limit)
  - `max_context_extended`: RoPE 2x calibration (up to 2x model limit)
  - `use_extended`: Per-model toggle stored in cache
  - `get_use_extended_for_model()` / `set_use_extended_for_model()` functions

- **Automatic Toggle Sync** ([state.py:919-945](aifred/state.py#L919-L945)):
  - On app start: Load toggle from cache for selected model
  - On model switch: Load toggle from cache for new model
  - UI toggle reflects actual cache state

- **Calibration Warnings** ([state.py:4166-4176](aifred/state.py#L4166-L4176)):
  - Warning if RoPE 2x toggle enabled but no extended calibration exists
  - Warning if native toggle but no native calibration exists
  - Prompts user to calibrate before using

#### Changed

- **Simplified num_ctx_mode** ([context_manager.py](aifred/lib/context_manager.py)):
  - Reduced from 3 modes (`auto_vram`, `auto_extended`, `manual`) to 2 modes (`auto`, `manual`)
  - RoPE extension now controlled by per-model toggle, not dropdown
  - Cleaner UI with just "Auto" and "Manual" radio buttons

- **Removed use_extended_calibration Parameter**:
  - No longer passed through function call chain
  - `gpu_utils.py` reads toggle directly from cache via `get_use_extended_for_model()`
  - Simpler code, less parameter threading

- **i18n for Calibration UI** ([i18n.py](aifred/lib/i18n.py)):
  - Added translations: `calibrate_context`, `calibrating`, `up_to_2x`
  - German: "Context kalibrieren", "Kalibriere...", "RoPE bis 2x"
  - English: "Calibrate context", "Calibrating...", "RoPE up to 2x"

#### Fixed

- **Toggle not affecting inference** ([gpu_utils.py:338-359](aifred/lib/gpu_utils.py#L338-L359)):
  - Problem: RoPE 2x was calibrated but inference used native context
  - Solution: Read `use_extended` from cache at inference time, not just calibration

- **Toggle state not persisted on app restart**:
  - Problem: Toggle reset to OFF on every restart
  - Solution: Load from `model_vram_cache.json` during `on_load()`

#### Technical Details

**Calibration Flow:**
```
User clicks "Context kalibrieren"
    ↓
Check toggle: Native or RoPE 2x?
    ↓
Set target: native_limit or 2x native_limit
    ↓
Binary search with /api/ps check
    ↓
Save to model_vram_cache.json
    ↓
Next inference uses calibrated value
```

**Cache Structure:**
```json
{
  "qwen3:14b": {
    "backend": "ollama",
    "native_context": 40960,
    "gpu_model": "NVIDIA GeForce RTX 3090 Ti",
    "use_extended": true,
    "ollama_calibrations": [
      {"max_context_gpu_only": 40960, "measured_at": "..."},
      {"max_context_extended": 81920, "measured_at": "..."}
    ]
  }
}
```

**Affected Files:**
- `aifred/aifred.py` - Calibration button + RoPE toggle UI
- `aifred/state.py` - `calibrate_context()`, `set_calibrate_extended()`, toggle sync
- `aifred/lib/model_vram_cache.py` - Per-model toggle functions
- `aifred/lib/gpu_utils.py` - Read toggle from cache at inference
- `aifred/lib/context_manager.py` - Simplified to 2 modes
- `aifred/lib/i18n.py` - Calibration UI translations
- `aifred/backends/ollama.py` - `calibrate_max_context()`, `_is_fully_in_vram()`
- `docs/plans/OLLAMA_CONTEXT_CALIBRATION.md` - Updated documentation
- `docs/architecture/ollama-context-calculation.md` - Updated flow diagram

---

## [2.9.0] - 2025-12-24

### 🤖 Multi-Agent Debate System: AIfred + Sokrates

**Neues Multi-Agent System mit zweitem LLM (Sokrates) als kritischem Diskussionspartner.**

#### Added

- **Multi-Agent Diskussionsmodi** ([state.py:4489-4820](aifred/state.py#L4489-L4820)):
  - **Standard**: Nur AIfred (klassisches Verhalten)
  - **Kritische Prüfung** (`user_judge`): AIfred antwortet, Sokrates kritisiert, User entscheidet
  - **Auto-Konsens** (`auto_consensus`): Iterative Verbesserung bis LGTM oder max Runden (1-3)
  - **Advocatus Diaboli** (`devils_advocate`): Pro & Contra Argumente für ausgewogene Analyse

- **Sokrates-LLM Auswahl** ([aifred.py](aifred/aifred.py)):
  - Separates Dropdown für Sokrates-Modell im Settings-Panel
  - Kann anderes Modell als AIfred verwenden
  - Einstellung wird in `settings.json` persistiert

- **Debate-Orchestrierung** ([state.py:4489](aifred/state.py#L4489)):
  - `_run_sokrates_analysis()`: Hauptlogik für Multi-Agent Debate
  - `_stream_llm_with_ui()`: Generic Streaming Helper für alle Agenten
  - `_stream_alfred_refinement()`: AIfred Überarbeitung nach Sokrates-Kritik
  - Max. Debattenrunden konfigurierbar (1-5, Standard: 3)

- **Sokrates Prompts** ([prompts/de/sokrates/](prompts/de/sokrates/), [prompts/en/sokrates/](prompts/en/sokrates/)):
  - `critic.txt`: Kritik-Prompt mit LGTM-Option
  - `refinement.txt`: AIfred Überarbeitungs-Prompt
  - `devils_advocate.txt`: Pro/Contra Analyse-Prompt
  - Zweisprachig (DE/EN) mit automatischer Spracherkennung

- **Thinking-Support für alle Agenten**:
  - `<think>`-Blöcke werden als Collapsible formatiert
  - LGTM-Erkennung strippt `<think>`-Tags vor Prüfung
  - Konsistente Darstellung für AIfred, Sokrates und Refinement

#### Fixed

- **LGTM-Erkennung bei Thinking-Models** ([state.py:4735](aifred/state.py#L4735)):
  - Problem: LGTM wurde nicht erkannt wenn in `<think>`-Block verpackt
  - Lösung: `strip_thinking_blocks()` vor LGTM-Check

- **Thinking-Header ohne Modellgröße** ([state.py:2978](aifred/state.py#L2978)):
  - Problem: Collapsible-Header zeigte "qwen3:8b (4.9 GB)" statt nur "qwen3:8b"
  - Lösung: `selected_model_id` statt `selected_model` verwenden

- **ollama Python-Paket fehlte** ([requirements.txt](requirements.txt)):
  - War in requirements definiert aber nicht installiert
  - Benötigt für ChromaDB Ollama Embedding Function

- **Whisper-Modell Dropdown bei Sprachwechsel** ([state.py](aifred/state.py)):
  - Problem: STT-Modell wurde als Display-Name gespeichert (z.B. "small (466MB...)")
  - Bei UI-Sprachwechsel konnte Dropdown den Wert nicht mehr matchen
  - Lösung: `whisper_model_key` speichert nur den Key ("small", "tiny", etc.)
  - Computed Property `whisper_model_display` generiert lokalisierten Display-Namen

- **Mobile Diskussionsmodus-Dropdown** ([aifred.py](aifred/aifred.py)):
  - Problem: Multi-Agent Dropdown sah auf Mobile anders aus als andere Dropdowns
  - Lösung: `native_select_generic()` Helper für konsistentes Mobile-Styling
  - `rx.cond(AIState.is_mobile, ...)` für responsive Darstellung

- **Type-Safety Fixes** (ruff/mypy compliance):
  - `i18n.py`: Research-Mode-Maps als separate Klassenattribute (nested dict type fix)
  - `prompt_loader.py`: `Optional[str]` statt implizites `str = None`
  - `llm_client.py`: `MessageType` TypeAlias nach Imports verschoben
  - `multi_agent.py`: `_to_messages()` Helper mit `cast()` für type-safe chat calls

- **Reflex Computed Var Warnings** ([state.py](aifred/state.py)):
  - Problem: Warnings über fehlende Dependencies bei computed vars
  - Lösung: Explizite `deps=["...", "ui_language"]` und `auto_deps=False`

#### Technical Details

**Workflow (Auto-Konsens):**
```
User Query → AIfred R1 → Sokrates Kritik
                              ↓
                         LGTM? ──YES──→ Fertig
                              ↓ NO
                    AIfred Überarbeitung R2
                              ↓
                    Sokrates Kritik R2
                              ↓
                         LGTM? ──YES──→ Fertig
                              ↓ NO
                    ... (bis max Runden)
```

**Betroffene Dateien:**
- `aifred/state.py` - Debate-Orchestrierung, Streaming Helper
- `aifred/aifred.py` - UI für Sokrates-LLM Auswahl, Diskussionsmodus
- `aifred/lib/multi_agent.py` - Orchestrator-Klassen (DebateResult, DebateContext)
- `prompts/*/sokrates/` - Sokrates-Prompts (critic, refinement, devils_advocate)

---

## [2.8.3] - 2025-12-23

### 🎯 Automatik-LLM: Fehlende num_ctx Parameter

**Query Optimizer und Intent Detector verwenden jetzt konsistent AUTOMATIK_LLM_NUM_CTX.**

#### Fixed

- **Query Optimizer ohne num_ctx** ([query_optimizer.py:87](aifred/lib/query_optimizer.py#L87)):
  - **Problem**: `num_ctx` fehlte komplett in den Options
  - **Symptom**: Bei Websuche verwendete Qwen3:4B seinen 262K Default-Context
  - **Solution**: `num_ctx: AUTOMATIK_LLM_NUM_CTX` hinzugefügt
  - **Impact**: Websuche-Modus lädt Automatik-LLM jetzt mit 4K statt 262K Context

- **Intent Detector mit hardcoded 4096** ([intent_detector.py:74,135](aifred/lib/intent_detector.py#L74)):
  - **Problem**: Hardcoded `4096` statt Config-Konstante
  - **Symptom**: Inkonsistenz - wenn Konstante geändert wird, bleibt Intent Detector bei 4096
  - **Solution**: Beide Stellen verwenden jetzt `AUTOMATIK_LLM_NUM_CTX`
  - **Impact**: Zentrale Steuerung über config.py für alle Automatik-Tasks

#### Technical Details

**Alle Automatik-LLM Aufrufe verwenden jetzt die Konstante:**
```python
# config.py
AUTOMATIK_LLM_NUM_CTX = 4096

# Verwendet in:
# - query_optimizer.py (NEU GEFIXT)
# - intent_detector.py (NEU GEFIXT: detect_query_intent + detect_cache_followup_intent)
# - conversation_handler.py ✓
# - cache_manager.py ✓
# - rag_context_builder.py ✓
# - context_manager.py (prepare_automatik_llm) ✓
```

---

## [2.8.2] - 2025-12-23

### 🌐 HTML Preview: Robusterer Regex

#### Fixed

- **HTML Code-Block Detection** ([formatting.py:319-321](aifred/lib/formatting.py#L319-L321)):
  - **Problem**: HTML-Blöcke wurden nicht erkannt wenn kein Newline nach ` ```html ` folgte
  - **Symptom**: Roher HTML-Code statt Collapsible mit Preview-Button
  - **Solution**: Regex von `r'```html\s*\n(...)```'` zu `r'```html\s*(...)```'` geändert
  - **Impact**: Erkennt jetzt alle Varianten: `\n`, Leerzeichen, oder direkter Content nach `html`

---

## [2.8.1] - 2025-12-23

### 🎯 Automatik-LLM: Context-Limiting bei Preload

**Automatik-LLM wird jetzt mit kleinem Context (4K) vorgeladen statt mit 262K Default.**

#### Fixed

- **Automatik-LLM VRAM-Explosion** ([state.py:1249-1264](aifred/state.py#L1249-L1264), [context_manager.py:670-727](aifred/lib/context_manager.py#L670-L727)):
  - **Problem**: Qwen3:4B hat 262K Default-Context - Ollama allokierte riesigen KV-Cache auf beiden GPUs
  - **Symptom**: Vor Main-LLM Preload wurde Automatik-LLM mit vollem 262K Context geladen (2x15 GB auf P4s)
  - **Root Cause**: Ollama verwendet Model-Default wenn kein `num_ctx` explizit gesetzt
  - **Solution**: Neue Funktion `prepare_automatik_llm()` preloaded mit `AUTOMATIK_LLM_NUM_CTX = 4096`
  - **Impact**: Automatik-LLM braucht jetzt nur ~500 MB statt mehrere GB VRAM

#### Added

- **`prepare_automatik_llm()`** ([context_manager.py:670-720](aifred/lib/context_manager.py#L670-L720)):
  - Separate Funktion für Automatik-LLM Preloading
  - Verwendet `AUTOMATIK_LLM_NUM_CTX` aus config.py
  - Wird bei Backend-Init aufgerufen (state.py `initialize_backend()`)

- **`AUTOMATIK_LLM_NUM_CTX`** ([config.py:397](aifred/lib/config.py#L397)):
  - Zentrale Konstante für alle Automatik-LLM Tasks (4096 tokens)
  - Verwendet in: conversation_handler, cache_manager, rag_context_builder, context_manager

#### Technical Details

**Problemanalyse:**
```bash
# Qwen3:4B hat enormen Default-Context:
curl -s localhost:11434/api/show -d '{"name":"qwen3:4b-instruct"}' | jq '.model_info["qwen3.context_length"]'
# → 262144  (262K tokens!)
```

**Lösung:**
```python
# config.py - Zentrale Konstante
AUTOMATIK_LLM_NUM_CTX = 4096  # 4K für alle Automatik-Tasks

# context_manager.py - Preload mit explizitem num_ctx
async def prepare_automatik_llm(backend, model_name, backend_type):
    if backend_type == "ollama":
        await backend.preload_model(model_name, num_ctx=AUTOMATIK_LLM_NUM_CTX)
```

---

## [2.8.0] - 2025-12-23

### 🧠 Vector Cache: Multilingual Embeddings mit Ollama

**ChromaDB nutzt jetzt nomic-embed-text-v2-moe für bessere deutsche semantische Suche.**

#### Changed

- **Ollama Embedding Integration** ([vector_cache.py:50-86](aifred/lib/vector_cache.py#L50-L86)):
  - Wechsel von internem `all-MiniLM-L6-v2` (nur Englisch) zu `nomic-embed-text-v2-moe`
  - MoE-Architektur: 305M aktive Parameter, ~100 Sprachen unterstützt
  - MIRACL Score 65.80 (multilingual retrieval benchmark)
  - Neue Collection `research_cache_v2` für saubere Trennung

- **CPU-only Embedding** ([vector_cache.py:50-86](aifred/lib/vector_cache.py#L50-L86)):
  - Eigene `OllamaCPUEmbeddingFunction` Klasse mit `num_gpu=0`
  - Embedding läuft auf CPU, VRAM bleibt 100% frei für LLM-Inferenz
  - Ollama-Server kann parallel zu vLLM/KoboldCPP laufen

#### Added

- **ollama Python-Paket** ([requirements.txt:24](requirements.txt#L24)):
  - Neue Abhängigkeit für ChromaDB OllamaEmbeddingFunction

#### Removed

- **Lokales ONNX-Embedding-Modell**: `~/.cache/chroma/onnx_models/` (167 MB) nicht mehr benötigt
- **nomic-embed-text v1**: Altes Ollama-Modell (274 MB) durch v2-moe ersetzt

#### Benefits

- ✅ Deutsche Anfragen werden semantisch korrekt erkannt
- ✅ "Wie wird das Wetter?" ≈ "Wettervorhersage" (Synonyme)
- ✅ Bessere Cache-Hit-Rate für nicht-englische Anfragen

---

## [2.7.10] - 2025-12-23

### 🧪 Chemistry Formula Support & HTML Preview Stability

**Added KaTeX mhchem extension for chemistry formulas and fixed HTML Preview hot-reload crash.**

#### Added

- **Chemistry Formula Support** ([custom.js:40-60](assets/custom.js#L40-L60), [katex/mhchem.min.js](assets/katex/mhchem.min.js)):
  - KaTeX mhchem extension for chemical equations and formulas
  - Supports `\ce{H2O}`, `\ce{Fe + S -> FeS}`, `\ce{CH3CH2OH}` notation
  - Locally hosted (no CDN dependency) for privacy and offline use
  - Dynamic loading: Extension loaded only when needed

- **Structure Formula Generation** (via HTML Preview):
  - AI can generate SVG structure formulas for organic molecules
  - Benzol ring, molecular structures rendered as scalable vector graphics
  - Opens in new browser tab via HTML Preview system

#### Fixed

- **HTML Preview Hot-Reload Crash** ([formatting.py:82-88](aifred/lib/formatting.py#L82-L88), [state.py:cleanup](aifred/state.py)):
  - Previously: Creating HTML preview in `assets/html_preview/` triggered Reflex hot-reload crash
  - Root cause: Reflex file watcher monitors `assets/` directory for changes
  - Solution: Moved HTML previews to `uploaded_files/html_preview/` (not watched)
  - URL changed to use `BACKEND_API_URL/_upload/html_preview/{filename}`

- **Double Log Messages in debug.log** ([context_manager.py](aifred/lib/context_manager.py), [scraper_orchestrator.py](aifred/lib/research/scraper_orchestrator.py)):
  - Previously: "✅ Main LLM preloaded" appeared twice in debug.log
  - Root cause: Both `yield {"type": "debug"}` AND direct `log_message()` were called
  - The yield handler `add_debug()` already calls `log_message()` internally
  - Solution: Removed redundant direct `log_message()` calls after yield statements

#### Technical Details

**mhchem Extension Loading:**
```javascript
function loadMhchemExtension() {
    if (mhchemLoaded) return Promise.resolve();
    return new Promise((resolve) => {
        const script = document.createElement('script');
        script.src = '/katex/mhchem.min.js';
        script.onload = () => {
            console.log('🧪 KaTeX mhchem extension loaded');
            mhchemLoaded = true;
            resolve();
        };
        document.head.appendChild(script);
    });
}
```

**HTML Preview Path Change:**
```python
# OLD: assets/html_preview/ (triggers hot-reload!)
# NEW: uploaded_files/html_preview/ (served via /_upload/)
_HTML_PREVIEW_DIR = PROJECT_ROOT / "uploaded_files" / "html_preview"
return f"{BACKEND_API_URL}/_upload/html_preview/{filename}"
```

---

## [2.7.9] - 2025-12-15

### 🔊 TTS: Audio Overlap Fix & Regenerate Button

**Fixed audio overlap bug when using "Neu generieren" and improved TTS controls.**

#### Added

- **TTS Regenerate Button** ([aifred.py:2942-2949](aifred/aifred.py#L2942-L2949)):
  - New "Neu generieren" button to re-synthesize TTS for the last AI response
  - Works with current voice/speed/engine settings without re-running LLM
  - Stops any currently playing audio before generating new audio

- **Persistent Playback Rate** ([state.py:4190-4197](aifred/state.py#L4190-L4197)):
  - Browser playback speed (0.5x - 2x) now saved to settings.json
  - Dropdown selector replaces browser's native 3-dot menu
  - Rate persists across page reloads and app restarts

- **TTS Widget Always Visible** ([aifred.py:2935](aifred/aifred.py#L2935)):
  - TTS widget shows when chat history exists (not just when audio exists)
  - Allows using "Neu generieren" after app restart to hear last response

#### Fixed

- **Audio Overlap Bug** ([custom.js:299-351](assets/custom.js#L299-L351), [custom.js:458-493](assets/custom.js#L458-L493)):
  - Previously: Clicking pause after "Neu generieren" started a second audio overlapping with the first
  - Root cause: Two separate audio elements (hidden `new Audio()` + visible HTML5 player) were not synchronized
  - Solution: All playback now uses only the visible HTML5 player - no hidden audio element
  - Pause/Play/Volume/Mute controls now work correctly

- **stopTts() Before Regenerate** ([state.py:4211-4212](aifred/state.py#L4211-L4212)):
  - `resynthesize_tts()` now calls `stopTts()` before generating new audio
  - Prevents overlap when clicking "Neu generieren" while audio is playing

---

## [2.7.8] - 2025-12-13

### 🎯 Context Management: Kalibrierte VRAM-Limits & Erhöhte Output-Reserve

**Ollama nutzt jetzt kalibrierte max_context-Werte aus Cache und Output-Reserve erhöht auf 32K.**

#### Added

- **Kalibrierte Context-Limits für Ollama** ([gpu_utils.py:252-262](aifred/lib/gpu_utils.py#L252-L262), [model_vram_cache.py:264-288](aifred/lib/model_vram_cache.py#L264-L288)):
  - Neue Funktion `get_ollama_calibrated_max_context()` liest experimentell gemessene Werte
  - Kalibrierte Werte haben Priorität vor dynamischer VRAM-Berechnung
  - Verhindert fehlerhafte Context-Größen (z.B. 143K statt korrekter 108K)
  - Nicht-kalibrierte Modelle nutzen weiterhin dynamische Berechnung mit `[uncalibrated]` Marker

- **Kalibrierungsdaten in model_vram_cache.json**:
  - Qwen3 30B A3B Q8_0: max 110592 tokens (108K) ohne CPU-Offloading
  - Struktur: `ollama_calibrations[].max_context_gpu_only`

#### Changed

- **Output-Reserve erhöht** ([context_manager.py:142-148](aifred/lib/context_manager.py#L142-L148)):
  - `OUTPUT_RESERVE_PREFERRED`: 8K → **32K** (für 108K+ Context Windows)
  - `OUTPUT_RESERVE_REDUCED`: 6K (unverändert, Fallback bei knappem VRAM)
  - `OUTPUT_RESERVE_MINIMUM`: 4K (unverändert, Notfall-Minimum)
  - Ermöglicht deutlich längere LLM-Antworten ohne Truncation

- **Context-Berechnung vereinfacht** ([context_manager.py:331-337](aifred/lib/context_manager.py#L331-L337)):
  - Für Ollama: Nutze vollen kalibrierten/berechneten Wert
  - Alte Logik "Input + 8K Reserve" entfernt
  - VRAM-Reservierung kostet keine Geschwindigkeit, nur die Füllung

#### Technical Details

**Kalibrierungs-Priorität:**
```python
# PRIORITY 1: Check for calibrated max_context (most accurate!)
calibrated_max = get_ollama_calibrated_max_context(model_name)
if calibrated_max is not None:
    return calibrated_max, debug_msgs  # Skip dynamic calculation
```

**Neue Reserve-Stufen:**
```python
OUTPUT_RESERVE_PREFERRED = 32768  # 32K für ausführliche Antworten
OUTPUT_RESERVE_REDUCED = 6144     # 6K Fallback
OUTPUT_RESERVE_MINIMUM = 4096     # 4K Minimum
```

---

## [2.7.7] - 2025-12-13

### 📄 RAG Prompt: Flexible User-Anfragen (Übersetzen, Zitieren, Analysieren)

**RAG System-Prompt respektiert jetzt User-Intent statt immer zusammenzufassen.**

#### Changed

- **RAG System-Prompt überarbeitet** ([prompts/de/system_rag.txt](prompts/de/system_rag.txt), [prompts/en/system_rag.txt](prompts/en/system_rag.txt)):
  - **Vorher**: Prompt erzwang immer "Fasse die Recherche-Ergebnisse zusammen"
  - **Jetzt**: Prompt erkennt User-Intent und passt Verhalten an:
    - `"übersetze"` → Vollständige Übersetzung Absatz für Absatz
    - `"zitiere"` → Wörtliches Zitieren aus den Quellen
    - `"analysiere"` → Detaillierte Analyse
    - Allgemeine Fragen → Zusammenfassung (wie bisher)

- **Übersetzungs-Modus mit strikten Regeln**:
  - Keine Meta-Kommentare ("Hier ist die Übersetzung...")
  - Keine Einleitungen ("Laut meiner Recherche...")
  - Direkter Start mit übersetztem Titel/Text
  - Vollständige Übersetzung aller Abschnitte
  - Original-Struktur beibehalten
  - Nur Quellen-Liste am Ende

- **Single-Source Word Limit erhöht** ([config.py:193-197](aifred/lib/config.py#L193-L197), [context_builder.py:70-73](aifred/lib/tools/context_builder.py#L70-L73)):
  - Neuer Konstante `MAX_WORDS_SINGLE_SOURCE = 12000`
  - Bei Direct URL Research (nur 1 Quelle) → höheres Limit
  - Ermöglicht vollständige PDF/Paper-Analyse ohne Kürzung
  - Multi-Source bleibt bei `MAX_WORDS_PER_SOURCE = 2000`

#### Technical Details

**Dynamisches Word-Limit in context_builder.py:**
```python
is_single_source = len(successful_results) == 1
word_limit = MAX_WORDS_SINGLE_SOURCE if is_single_source else MAX_WORDS_PER_SOURCE
```

**Neuer Prompt-Abschnitt für Übersetzungen:**
```
⚠️ BEI ÜBERSETZUNGEN:
- Gib NUR den übersetzten Text aus - KEINE Meta-Kommentare!
- ❌ KEINE Einleitung wie "Hier ist die Übersetzung..."
- ✅ Beginne DIREKT mit dem übersetzten Text (Titel/erste Überschrift)
- ✅ Übersetze JEDEN Abschnitt vollständig
```

---

## [2.7.6] - 2025-12-13

### 📄 PDF-Scraping & Failed Sources Cache

**PDF-Extraktion verbessert und Failed Sources werden jetzt im Vector Cache gespeichert.**

#### Added

- **Failed Sources im Vector Cache** ([conversation_handler.py:985-989](aifred/lib/conversation_handler.py#L985-L989)):
  - Bei Cache-Hits werden jetzt auch gespeicherte Failed Sources angezeigt
  - URLs die beim ursprünglichen Scraping fehlschlugen erscheinen wieder im Collapsible
  - Vollständige Transparenz über Quellenverfügbarkeit auch bei gecachten Antworten

#### Fixed

- **PDF-Scraping mit Hotlink-Protection** ([scraper_tool.py:377-387](aifred/lib/tools/scraper_tool.py#L377-L387)):
  - Browser User-Agent statt Bot-UA (`Mozilla/5.0 Chrome/120...`)
  - Referer-Header automatisch aus Domain generiert
  - Behebt 403 Forbidden bei PDFs mit Hotlink-Schutz (z.B. jvsmedicscorner.com)

#### Changed

- **requirements.txt**: `pymupdf>=1.26.0` hinzugefügt für PDF-Support

---

## [2.7.5] - 2025-12-13

### 🔧 Automatik-Tasks: Thinking immer deaktiviert

**User-Toggle für Thinking gilt nur noch für Haupt-LLM, nicht für Automatik-Tasks.**

#### Fixed

- **Automatik-Tasks ignorieren jetzt User-Toggle** ([query_optimizer.py:89-91](aifred/lib/query_optimizer.py#L89-L91), [intent_detector.py:78-79](aifred/lib/intent_detector.py#L78-L79), [conversation_handler.py:1454-1455](aifred/lib/conversation_handler.py#L1454-L1455)):
  - Query-Optimierung, Intent-Detection und Automatik-Entscheidungen laufen immer mit `enable_thinking: False`
  - Vorher: User-Toggle überschrieb Default, was zu unnötig langen Antwortzeiten führte
  - Jetzt: Automatik-Tasks sind konsistent schnell, unabhängig von User-Einstellung
  - Haupt-LLM respektiert weiterhin den User-Toggle

#### Betroffene Dateien

- `aifred/lib/query_optimizer.py` - Zeilen 89-91
- `aifred/lib/intent_detector.py` - Zeilen 78-79, 139-140
- `aifred/lib/conversation_handler.py` - Zeilen 1454-1455

---

## [2.7.4] - 2025-12-13

### 🔧 Multi-Session Deadlock Fix (QuantKV + Native Queue)

**Stabiles Multi-Session ohne Python asyncio.Lock.** Root Cause für Deadlocks identifiziert und behoben.

#### Changed

- **Python asyncio.Lock entfernt** ([koboldcpp.py:32-40](aifred/backends/koboldcpp.py#L32-L40)):
  - asyncio.Lock verursachte Deadlocks wenn async generators nicht vollständig konsumiert wurden
  - KoboldCPP's natives `--multiuser 5` Queuing übernimmt jetzt allein die Request-Serialisierung
  - Getestet mit 5 parallelen Requests - alle erfolgreich ohne Hänger

- **GPU Inactivity Monitor nutzt native API** ([state.py:1284-1307](aifred/state.py#L1284-L1307), [state.py:1328-1349](aifred/state.py#L1328-L1349)):
  - Statt Python Lock-Status wird jetzt `/api/extra/perf` abgefragt
  - `queue > 0` oder `idle == 0` = Requests aktiv
  - Robuster als Python-Lock-Check

- **QuantKV Default auf Q8 (quantkv=1)** ([config.py:349](aifred/lib/config.py#L349), [gpu_utils.py:582](aifred/lib/gpu_utils.py#L582)):
  - `quantkv=2` (Q4) hat Deadlock-Bug auf Multi-GPU mit FlashAttention
  - `quantkv=1` (Q8) stabil auf 2x Tesla P40 mit 262k Context
  - Dokumentiert in config.py mit Hinweis auf den Hardware-Bug

#### Fixed

- **Multi-GPU Deadlock bei parallelen Requests**:
  - **Root Cause 1**: `quantkv=2` + FlashAttention + Multi-GPU = Deadlock nach 2-3 großen Requests
  - **Root Cause 2**: Python asyncio.Lock + nicht-konsumierte async generators = Lock nie freigegeben
  - **Lösung**: QuantKV=1 (Hardware-Bug umgehen) + Native Queue (robuster als Python Lock)

#### Technical Details

**Warum asyncio.Lock problematisch war:**
```python
# PROBLEM: Wenn async generator nicht vollständig konsumiert wird
async with _koboldcpp_request_lock:  # Lock acquired
    async for chunk in stream:
        yield chunk  # Generator suspended here
        # Wenn Caller abbricht → Lock bleibt für immer gehalten!
```

**Jetzt mit nativem KoboldCPP Queue:**
```
Request 1 → KoboldCPP Queue (verarbeitet)
Request 2 → KoboldCPP Queue (wartet)
Request 3 → KoboldCPP Queue (wartet)
           └─ Kein Python Lock, keine Generator-Lifecycle-Probleme
```

**QuantKV Hardware-Bug:**
- `quantkv=2` (Q4) + `--flashattention` + Multi-GPU = Deadlock
- Manifestiert sich nach 2-3 großen Requests (~40k+ tokens)
- GPUs zeigen 0% Auslastung obwohl Queue voll
- Mit `quantkv=1` (Q8) läuft 262k Context stabil

---

## [2.7.3] - 2025-12-13

### 🔒 Multi-User Request Lock (Reverted in 2.7.4)

**Hinweis: Dieser Ansatz wurde in v2.7.4 durch natives KoboldCPP-Queuing ersetzt.**

Python asyncio.Lock wurde hinzugefügt, verursachte aber selbst Deadlocks bei nicht-konsumierten async generators.

---

## [2.7.2] - 2025-12-12

### 👥 Multi-User Support + Package Updates

**Multi-User Concurrent Requests werden jetzt korrekt in eine Queue gestellt.** Python-Dependencies auf aktuelle Versionen aktualisiert.

#### Added

- **KoboldCPP Multi-User Mode** ([koboldcpp_manager.py:265-268](aifred/lib/koboldcpp_manager.py#L265-L268)):
  - `--multiuser 5` Parameter für Request-Queuing
  - Bis zu 5 gleichzeitige Clients werden in Queue gestellt
  - Verarbeitung bleibt sequentiell (KoboldCPP Limitation: `n_seq_max = 1`)
  - Verhindert Timeout/Hänger wenn zweiter Request während Verarbeitung kommt

#### Changed

- **Python Package Updates**:
  - `reflex`: 0.8.21 → 0.8.22
  - `openai`: 2.6.1 → 2.11.0
  - `chromadb`: 1.3.4 → 1.3.7
  - `fastapi`: 0.121.1 → 0.124.4
  - `granian`: 2.5.6 → 2.6.0
  - `pydantic`: 2.12.3 → 2.12.5
  - `transformers`: 4.57.1 → 4.57.3
  - `starlette`: 0.46.4 → 0.47.0
  - `SQLAlchemy`: 2.0.36 → 2.0.40
  - `beautifulsoup4`: 4.12.3 → 4.13.4
  - `certifi`: 2025.4.26 → 2025.6.15
  - Diverse weitere Updates (urllib3, soupsieve, etc.)

- **ChromaDB Docker**: Auf latest Image aktualisiert

#### Fixed

- **huggingface-hub Versionskonflikt**: transformers erforderte `<1.0`, aber `1.2.3` war installiert
  - Upgrade auf transformers 4.57.3 löste den Konflikt (huggingface-hub automatisch auf 0.36.0 angepasst)

- **Mobile Device Stuck**: Bei gleichzeitiger Desktop- und Mobile-Nutzung blieb der zweite Request hängen
  - Multi-User Mode stellt Requests jetzt in Queue

- **GGUF Model Not Found bei Service-Start** ([state.py:1609-1615](aifred/state.py#L1609-L1615), [koboldcpp.py:99-105](aifred/backends/koboldcpp.py#L99-L105)):
  - `gguf_models` Dictionary war bei Service-Neustart noch nicht geladen
  - Auto-Scan der GGUF-Modelle wenn Dictionary leer ist
  - Behebt "GGUF model 'X' not found" Fehler beim Senden der ersten Nachricht

#### Technical Details

**KoboldCPP Multi-User Verhalten:**
```
Request 1 (Desktop): Wird verarbeitet
Request 2 (Mobile):  Wird in Queue gestellt (max 5)
Request 1 fertig:    Request 2 startet automatisch
```

**Ohne `--multiuser`:**
- Zweiter Request während Verarbeitung → Timeout oder Endlosschleife
- `n_seq_max = 1` bedeutet nur eine Sequenz im KV-Cache

**Mit `--multiuser 5`:**
- Requests werden in interne Queue gestellt
- Sequentielle Verarbeitung mit korrektem Queuing

---

## [2.7.1] - 2025-12-11

### 🌐 HTML Preview Button

**AI-generierter HTML-Code kann jetzt direkt im Browser geöffnet werden.**

#### Added

- **HTML Preview Button** ([formatting.py:186-239](aifred/lib/formatting.py#L186-L239)):
  - `\`\`\`html` Code-Blöcke erhalten automatisch einen "🌐 Im Browser öffnen" Link
  - HTML wird nach `assets/html_preview/` gespeichert und statisch serviert
  - Link öffnet im neuen Browser-Tab (AIfred bleibt erhalten)

- **Cleanup-Funktion** ([formatting.py:152-183](aifred/lib/formatting.py#L152-L183)):
  - `cleanup_old_html_previews()` löscht Dateien älter als 24h
  - Verhindert Ansammlung temporärer HTML-Dateien

#### Changed

- **custom.js erweitert** ([custom.js:17-24](assets/custom.js#L17-L24)):
  - `/html_preview/` Links werden automatisch mit `target="_blank"` versehen

---

## [2.6.3] - 2025-12-11

### 🎯 VRAM-Messung optimiert für Automatik-Modus

**Korrekte VRAM-Messung für optimale Context-Window Berechnung.**

#### Changed

- **VRAM-Messung verschoben** ([ollama.py:729-783](aifred/backends/ollama.py#L729-L783)):
  - Entladen aller Modelle erfolgt jetzt in `calculate_practical_context()` statt in `set_selected_model()`
  - Sichert korrekte VRAM-Messung auch wenn Automatik-LLM vorher lief
  - 2 Sekunden Wartezeit für vollständige VRAM-Freigabe durch GPU-Treiber

- **Proaktives Entladen entfernt** ([state.py:3360-3363](aifred/state.py#L3360-L3363)):
  - Beim Modellwechsel wird nicht mehr sofort entladen
  - Vermeidet unnötige Wartezeit bei Modellauswahl

#### Fixed

- **Falsches Context-Window nach Automatik-LLM**: VRAM wurde gemessen während Automatik-LLM noch geladen war → zu kleines Context-Window für Haupt-LLM
- **Race Condition mit externen Prozessen**: Gecachte VRAM-Werte konnten durch andere GPU-Nutzer veraltet sein → jetzt Just-in-Time Messung

#### Technical Details

**Neuer Flow für Automatik-Modus:**
```
1. User sendet Nachricht
2. Automatik-LLM läuft (Entscheidung: Web/RAG/Eigenes Wissen)
3. calculate_practical_context() wird aufgerufen:
   → Entlade ALLE Modelle (inkl. Automatik-LLM)
   → 2s warten (VRAM-Freigabe)
   → VRAM messen (jetzt komplett frei!)
4. Haupt-LLM laden mit optimalem Context-Window
```

**Vorheriger (fehlerhafter) Flow:**
```
1. User wählt Modell → Entlade + 2s warten (zu früh!)
2. Automatik-LLM läuft → VRAM belegt
3. VRAM messen → FALSCH (Automatik-LLM noch geladen)
```

---

## [2.6.2] - 2025-12-08

### 🔧 Vision-Prompts Overhaul + Think-Tag Fix

**Massive Verbesserung der Vision-LLM Prompts und Fix für fehlende Think-Tags bei Qwen3.**

#### Added

- **Template-less Vision-Prompts** ([prompts/*/vision_templateless_*.txt](prompts/de/)):
  - Neue Dateien für OCR-Modelle ohne Chat-Template (DeepSeek-OCR, etc.)
  - `vision_templateless_ocr.txt`: Minimaler OCR-Prompt ohne Timestamp
  - `vision_templateless_default.txt`: Für Nicht-OCR template-less Modelle
  - Kein Timestamp-Injection (verwirrt manche Modelle)

- **Think-Tag Reparatur** ([formatting.py:136-168](aifred/lib/formatting.py#L136-L168)):
  - Neue Funktion `fix_orphan_closing_think_tag()`
  - Repariert verwaiste `</think>` Tags (ohne öffnenden `<think>`)
  - Löst Problem: Qwen3 mit `enable_thinking=false` gibt trotzdem Denkprozess aus, aber ohne öffnenden Tag
  - Log-Meldung: "🔧 Fehlender <think> Tag repariert"

#### Changed

- **Vision-OCR Prompts verschärft** ([prompts/*/vision_ocr.txt](prompts/de/vision_ocr.txt)):
  - Kontextabhängige Ausgabe: JSON nur bei strukturierten Daten
  - Neue VERBOTEN-Sektion gegen Interpretationen
  - Keine Erklärungen wie "b.B. steht für..."
  - Tabellen-spezifische Regeln für korrekte Spaltenzuordnung
  - Multi-Image Abschnitt entfernt (sequentielle Verarbeitung)
  - Singular-Formulierung (ein Bild pro Call)

- **prompt_loader.py** ([prompt_loader.py:307-336](aifred/lib/prompt_loader.py#L307-L336)):
  - Neue Funktionen: `get_vision_templateless_ocr_prompt()`, `get_vision_templateless_default_prompt()`
  - Direkte Datei-Lese-Funktionen ohne Timestamp-Injection

- **conversation_handler.py** ([conversation_handler.py:95-102](aifred/lib/conversation_handler.py#L95-L102)):
  - Hardcodierte template-less Prompts durch Datei-basierte Loader ersetzt

- **formatting.py**:
  - `format_thinking_process()` und `build_debug_accordion()` rufen `fix_orphan_closing_think_tag()` auf

#### Fixed

- **DeepSeek-OCR leere Antworten**: Timestamp-Injection hat das Modell verwirrt → jetzt minimaler Prompt ohne Timestamp
- **Qwen3-VL Markdown statt JSON**: Verschärfte Prompts erzwingen JSON bei strukturierten Daten
- **Qwen3 fehlende Think-Tags**: Denkprozess wurde nicht in Collapsible angezeigt → automatische Tag-Reparatur
- **Vision-LLM Spalten-Verwechslungen**: Neue Regeln für korrektes Spalten-Mapping bei Tabellen

#### Technical Details

**Think-Tag Reparatur Logik:**
```python
# Wenn nur </think> vorhanden (ohne <think>):
# → Alles davor wird als Denkprozess behandelt
if '</think>' in text and '<think>' not in text:
    text = '<think>' + text  # Öffnenden Tag am Anfang einfügen
```

**Template-less Prompt-Logik:**
```python
# OCR-Modelle (DeepSeek-OCR): Minimaler Prompt
if "ocr" in model_lower:
    prompt = get_vision_templateless_ocr_prompt(lang)  # "Extrahiere den Text aus dem Bild."

# Andere template-less Modelle: Bildbeschreibung + Text
else:
    prompt = get_vision_templateless_default_prompt(lang)  # "Beschreibe das Bild..."
```

---

## [2.6.1] - 2025-12-07

### 🧠 VRAM-Aware Context Building

**Intelligentes RAG-Budgeting:** Context wird jetzt BEVOR er gebaut wird auf verfügbares VRAM geprüft. Keine "Eingabe zu groß" Fehler mehr bei großem Web-Scraping.

#### Added

- **VRAM-Aware Context Building** ([context_manager.py:151-215](aifred/lib/context_manager.py#L151-L215)):
  - Neue Funktion `get_max_available_context()` ermittelt VRAM-Limit VOR dem Context-Building
  - Neue Funktion `calculate_adaptive_reserve()` mit stufenweiser Reserve-Anpassung
  - RAG-Context wird dynamisch auf verfügbares Budget begrenzt
  - Verhindert "Eingabe zu groß" Fehler bei großem Web-Scraping

- **Adaptive Reserve-Stufen** (8K → 6K → 4K):
  - **8K Reserve** (Standard): Ideal für ausführliche Antworten
  - **6K Reserve**: Wenn RAG-Content unter 80% vom Ziel fällt
  - **4K Reserve** (Minimum): Nur wenn VRAM sehr knapp
  - Erst wenn Reserve auf 4K, wird RAG-Content gekürzt

#### Changed

- **research/context_builder.py** ([context_builder.py:87-128](aifred/lib/research/context_builder.py#L87-L128)):
  - VRAM-Limit wird vor `build_context()` abgefragt
  - `max_context_tokens` Parameter wird jetzt dynamisch übergeben
  - Overhead (System-Prompt, History, User) wird vorab geschätzt

- **research/cache_handler.py** ([cache_handler.py:77-115](aifred/lib/research/cache_handler.py#L77-L115)):
  - Gleiche VRAM-aware Logik wie context_builder.py
  - Cache-Hits nutzen ebenfalls adaptive Reserve

- **context_manager.py**:
  - Reserve vereinfacht auf konstante 8K (statt dynamisch 8K/12K/16K)
  - `OUTPUT_RESERVE_PREFERRED/REDUCED/MINIMUM` Konstanten

#### Technical Details

**Adaptive Reserve Logik:**
```python
# Priorität: Maximiere RAG-Content, reduziere Reserve stufenweise
available = VRAM_limit  # z.B. 32K
base = System_Prompt + History + User  # z.B. 4K

# Stufe 1: 8K Reserve → RAG = available - base - 8K
# Stufe 2: Falls RAG < 80% Ziel → 6K Reserve
# Stufe 3: Falls RAG < 80% Ziel → 4K Reserve
# Stufe 4: Falls RAG < 80% Ziel → Kürze RAG-Content
```

**Beispiel-Szenarien:**
| VRAM | Base | Reserve | RAG |
|------|------|---------|-----|
| 40K | 4K | 8K | 20K (voll) |
| 30K | 4K | 8K | 17.8K (leicht reduziert) |
| 28K | 4K | 6K | 17.8K (Reserve reduziert) |
| 18K | 4K | 4K | 9.9K (RAG gekürzt) |

---

## [2.6.0] - 2025-12-07

### 📷 Sequentielle Bildverarbeitung + Session Persistenz

**Stabilere Vision-Ergebnisse:** Multi-Image wird jetzt sequentiell verarbeitet. Mobile Sessions bleiben erhalten.

#### Added

- **Sequentielle Bildverarbeitung** ([conversation_handler.py:676-851](aifred/lib/conversation_handler.py#L676-L851)):
  - Bilder werden nacheinander verarbeitet statt gleichzeitig
  - Auch große Vision-Modelle produzieren konsistentere Ergebnisse
  - Kleinere Modelle (z.B. deepseek-ocr:3b) werden nicht mehr überlastet
  - Debug-Output zeigt Fortschritt: `[1/3] Verarbeite: image.jpg`
  - Ergebnisse werden im `multi_image` JSON-Format kombiniert

- **Session Persistenz** (Cookie + Server-Side Storage):
  - **Neue Datei:** [browser_storage.py](aifred/lib/browser_storage.py) - JavaScript Cookie-Helfer
  - **Neue Datei:** [session_storage.py](aifred/lib/session_storage.py) - Server-seitige Session-Speicherung
  - Mobile Browser behalten Chat-History nach Background/Neustart
  - Sessions in `~/.config/aifred/sessions/{device_id}.json`
  - 128-bit Device-ID via Cookie (1 Jahr gültig)
  - Auto-Cleanup: Sessions > 30 Tage werden gelöscht
  - PIN-Funktionen vorbereitet für Cross-Device-Zugriff (Phase 2)

#### Fixed

- **Fast Path Settings Override Bug** ([state.py:895-932](aifred/state.py#L895-L932)):
  - **Problem:** Nach Backend-Wechsel (vLLM → Ollama) wurde falsches Modell geladen
  - **Ursache:** Fast Path überschrieb settings.json mit altem Global State
  - **Fix:** Fast Path respektiert jetzt settings.json Modell-Auswahl

#### Technical Details

**Sequentielle Verarbeitung:**
```python
# Bei 1 Bild: Direkte Verarbeitung (wie bisher)
# Bei N Bildern: Sequentiell, dann kombinieren
for i, img in enumerate(images):
    result = await _process_single_image_vision(img, i, ...)
    all_results.append(result)

# Ergebnisse kombinieren
corrected_json = {
    "type": "multi_image",
    "processing_mode": "sequential",
    "images": combined_images
}
```

**Session-Persistenz Flow:**
```
1. on_load() → rx.call_script(get_device_id_script())
2. Callback → handle_device_id_loaded()
   - "NEW" → generate_device_id() + set cookie
   - existing → load_session(device_id)
3. Nach jeder Chat-Nachricht → _save_current_session()
```

---

## [2.5.3] - 2025-12-07

### 🎯 Dynamische Vision-Kontext-Berechnung

**Optimierte VRAM-Nutzung:** Vision-Kontext wird jetzt dynamisch berechnet wie beim Haupt-LLM - basierend auf tatsächlich benötigten Tokens, VRAM-Kapazität und Model-Limits.

#### Added

- **Dynamische Vision-Kontext-Berechnung** ([conversation_handler.py:1892-1920](aifred/lib/conversation_handler.py#L1892-L1920)):
  - Vision-Kontext wird jetzt wie Haupt-LLM berechnet: `min(benötigt, VRAM-max, Model-max)`
  - Nutzt `calculate_vram_based_context()` für VRAM-basierte Berechnung
  - Fallback auf feste Werte wenn VRAM-Berechnung fehlschlägt

#### Fixed

- **Vision-Kontext nutzt jetzt Minimum statt Maximum**:
  - **Problem:** Vision-Kontext war statisch auf 16384 Tokens gesetzt
  - **Fix:** Berechnet jetzt `min(benötigte_tokens, vram_max, model_limit)`
  - Spart VRAM bei kürzeren Anfragen

- **Doppelte Log-Zeilen entfernt** ([gpu_utils.py](aifred/lib/gpu_utils.py)):
  - **Problem:** Debug-Meldungen wurden doppelt geloggt (direkt + via add_debug)
  - **Fix:** `log_message()` Aufrufe aus `calculate_vram_based_context()` entfernt
  - Nachrichten werden nur noch via `debug_msgs` gesammelt und einmal geloggt

- **Mypy Type-Fehler behoben** ([gpu_utils.py:337,342,444](aifred/lib/gpu_utils.py#L337)):
  - Fixed: `None - int` Operation durch early return
  - Fixed: `format_number(None)` durch early return
  - Fixed: `return Any` durch explizite Type-Annotation

#### Removed

- **Toter Code entfernt**:
  - `VISION_CONTEXT_LIMIT` aus config.py entfernt (ungenutzt)
  - Doppelte `detect_gpu_vendor()` Funktion aus gpu_utils.py entfernt

#### Technical Details

**Vision-Kontext-Berechnung:**
```python
# Dynamische Berechnung wie Haupt-LLM
vram_num_ctx = calculate_vram_based_context(model_name, ...)
model_limit = get_model_context_limit(model_name)
needed_tokens = len(prompt_tokens) + expected_output

# Minimum aller drei Werte
num_ctx = min(needed_tokens, vram_num_ctx, model_limit)
```

---

## [2.5.2] - 2025-12-07

### 📷 Multi-Image Vision Pipeline Improvements

**Enhanced multi-image analysis:** Fixed JSON-to-readable conversion for multi-image output, improved log formatting, and better Markdown rendering.

#### Added

- **Multi-Image Handler** ([conversation_handler.py:276-304](aifred/lib/conversation_handler.py#L276-L304)):
  - New `multi_image` type handler in `_json_to_readable()` function
  - Recursively processes each image's content (document, text, table, etc.)
  - Generates formatted output with `📷 **Bild N**: Description` headers

- **Collapsible JSON Formatting** ([custom.css:164-171](assets/custom.css#L164-L171)):
  - Added `white-space: pre-wrap` for proper JSON indentation display
  - Added `font-family: monospace` for better readability
  - JSON in "Strukturierte Daten" collapsible now properly formatted

#### Fixed

- **Markdown Line Breaks** ([conversation_handler.py:255-262](aifred/lib/conversation_handler.py#L255-L262)):
  - **Problem:** Single `\n` in text content was ignored by Markdown, causing text to run together
  - **Fix:** Convert single `\n` to `  \n` (two spaces + newline) for hard line breaks
  - Text now displays with proper line breaks without extra paragraph spacing

- **Log Alignment** ([state.py:2005-2007](aifred/state.py#L2005-L2007)):
  - **Problem:** Bullet points in image list not aligned with "Vision-LLM" text
  - **Fix:** Changed indent from 3 spaces to 2 spaces for proper alignment

#### Changed

- **Vision Context Limit**: Increased from 8192 to 16384 tokens for multi-image analysis

#### Technical Details

**Markdown Line Break Fix:**
```python
# Single \n → Markdown hard line break (two spaces + newline)
content = re.sub(r'(?<!\n)\n(?!\n)', '  \n', content)
```

**Multi-Image JSON Format:**
```json
{
  "type": "multi_image",
  "images": [
    {"image_index": 1, "description": "...", "content": {...}},
    {"image_index": 2, "description": "...", "content": {...}}
  ]
}
```

---

## [2.5.1] - 2025-12-07

### 📱 Mobile UX Improvements - Crop Modal & Image Upload

**Enhanced mobile experience:** Fullscreen crop modal, improved thumbnail layout, and smarter image naming.

#### Fixed

- **Crop Modal Positioning** ([aifred.py:409-590](aifred/aifred.py#L409-L590)):
  - **Problem:** Crop modal appeared at bottom-right on mobile devices, often off-screen when page was scrolled
  - **Fix:** Replaced `rx.dialog` with fullscreen overlay using `position: fixed`
  - Added JavaScript to scroll page to top and block body scroll when modal opens
  - Restored scroll on modal close

- **Touch Interaction Issues** ([custom.css:238-395](assets/custom.css#L238-L395)):
  - **Problem:** "Snap-to-grid" behavior on mobile made crop box hard to control
  - **Fix:** Added `touch-action: none` on all crop elements (container, overlay, box, handles)
  - Disabled webkit touch callout and user-select

- **Backend Dropdown Empty on Mobile** ([aifred.py](aifred/aifred.py)):
  - **Problem:** Backend dropdown showed nothing in closed state on mobile
  - **Root Cause:** CSS layout issue - badge next to dropdown consumed all space
  - **Fix:** Added `min_width: 120px` and `flex: 1` to native select

#### Changed

- **Image Upload Layout** ([aifred.py:348-407](aifred/aifred.py#L348-L407)):
  - Buttons and hint text now left-aligned (not centered)
  - Thumbnails display below buttons (not beside them)
  - Thumbnail size increased: 60px → 80px
  - Crop/delete buttons enlarged for better touch targets (size="2")

- **Image Name Shortening** ([state.py:2743-2752](aifred/state.py#L2743-L2752)):
  - Camera images with long names (>20 chars) like `2025-12-07_11.36.123456789.jpg` now display as `Bild_001.jpg`
  - Original filename preserved internally

- **Crop Completion Messages** ([state.py:2916-2920](aifred/state.py#L2916-L2920)):
  - Simplified from: `✂️ Bild zugeschnitten: image.png (1920 x 1080 → 91% x 47% → 1747 x 508 px)`
  - To: `✂️ Bild zugeschnitten: 91% x 47% → 1747 x 508 px`
  - Filename already shown in previous message

#### Technical Details

**Scroll Fix JavaScript:**
```javascript
// When modal opens:
document.body.style.overflow = 'hidden';
document.documentElement.style.overflow = 'hidden';
window.scrollTo(0, 0);

// When modal closes:
document.body.style.overflow = '';
document.documentElement.style.overflow = '';
```

---

## [2.5.0] - 2025-12-07

### ✂️ Image Crop & 4K Auto-Resize

**New feature:** Crop images before sending to Vision-LLM, with automatic 4K resolution limit.

#### Added

- **Interactive Crop Modal** ([aifred.py:409-590](aifred/aifred.py#L409-L590)):
  - Full-screen modal with dark semi-transparent overlay
  - Image displayed with `object-fit: contain` for proper aspect ratio
  - Draggable crop box with visual selection area
  - "Zuschneiden" (Crop) and "Abbrechen" (Cancel) buttons

- **8-Point Drag Handles** ([custom.css:234-381](assets/custom.css#L234-L381)):
  - 4 corner handles (nw, ne, sw, se) - diagonal resizing
  - 4 edge handles (n, s, e, w) - single-axis resizing
  - Touch-friendly: 24px hit area, 12px visible circle
  - Visual feedback with `cursor` styles and hover effects

- **Crop Button per Image** ([aifred.py:348-407](aifred/aifred.py#L348-L407)):
  - Green crop icon button on each image thumbnail
  - Position: top-left corner of preview
  - Opens crop modal for that specific image

- **Crop State Variables** ([state.py:282-291](aifred/state.py#L282-L291)):
  - `crop_modal_open`: Modal visibility toggle
  - `crop_image_index`: Which image is being cropped
  - `crop_image_url`: Data-URL for crop preview
  - `crop_box`: {x, y, width, height} in percent (0-100)

- **Crop Handler** ([state.py:2858-2937](aifred/state.py#L2858-L2937)):
  - `open_crop_modal(index)`: Opens modal with selected image
  - `apply_crop()`: Applies crop and replaces image in pending_images
  - `cancel_crop()`: Closes modal without changes
  - Detailed logging: `✂️ Bild zugeschnitten: image.png (1920 x 1080 → 91% x 47% → 1747 x 508 px)`

- **crop_and_resize_image() Function** ([vision_utils.py:377-453](aifred/lib/vision_utils.py#L377-L453)):
  - Crop image based on percentage box `{x, y, width, height}`
  - EXIF rotation fix with `ImageOps.exif_transpose()`
  - Automatic resize to max dimension (4K)
  - RGBA→RGB conversion for PNG transparency (white background)

#### Changed

- **4K Resolution Limit** ([config.py:358](aifred/lib/config.py#L358)):
  - `VISION_MAX_IMAGE_DIMENSION`: 2048 → 3840 (4K UHD)
  - Better quality for detailed documents and images

- **EXIF Rotation Handling** ([vision_utils.py:392-395](aifred/lib/vision_utils.py#L392-L395)):
  - Mobile photos now correctly oriented before cropping
  - Uses `PIL.ImageOps.exif_transpose()` to auto-rotate

- **RGBA to RGB Conversion** ([vision_utils.py:428-441](aifred/lib/vision_utils.py#L428-L441)):
  - PNG screenshots with transparency now work correctly
  - Transparent areas filled with white background
  - Supports RGBA, LA, and P (palette) modes

#### Technical Details

**Crop Flow:**
```
User clicks crop button on thumbnail
    ↓
open_crop_modal(index) → Shows modal with image
    ↓
User drags corners/edges to adjust crop box
    ↓
JavaScript updates crop_box state via on_change
    ↓
User clicks "Zuschneiden"
    ↓
apply_crop() → crop_and_resize_image(original_bytes, crop_box)
    ↓
Cropped image replaces original in pending_images
    ↓
Modal closes, thumbnail updates
```

**Crop Box Calculation:**
```python
# crop_box = {x: 10, y: 20, width: 60, height: 50} (percent)
# Image size = 1920 x 1080 pixels

x_px = 1920 * 10 / 100 = 192
y_px = 1080 * 20 / 100 = 216
w_px = 1920 * 60 / 100 = 1152
h_px = 1080 * 50 / 100 = 540

cropped = img.crop((192, 216, 192+1152, 216+540))
```

#### Files Modified

1. [aifred/aifred.py](aifred/aifred.py) - Crop button + modal UI
2. [aifred/lib/config.py](aifred/lib/config.py) - 4K resolution limit
3. [aifred/lib/vision_utils.py](aifred/lib/vision_utils.py) - crop_and_resize_image(), EXIF fix, RGBA→RGB
4. [aifred/state.py](aifred/state.py) - Crop state variables + handlers
5. [assets/custom.css](assets/custom.css) - Crop modal styling with drag handles

---

## [2.4.2] - 2025-12-06

### 🔧 Model-Sync Fix & Universelle Vision-Erkennung

**Kritische Bugfixes:** Model-IDs werden jetzt korrekt synchronisiert wenn User im Dropdown wechselt. Vision-LLM unterstützt jetzt beliebige Dokumenttypen ohne Fehlermeldungen.

#### Fixed

- **Model-ID Sync beim Dropdown-Wechsel** ([state.py:3207-3209](aifred/state.py#L3207-L3209), [state.py:3414-3415](aifred/state.py#L3414-L3415), [state.py:3431](aifred/state.py#L3431)):
  - **Problem:** Vision-LLM zeigte falsches Modell (UI: qwen3-vl:8b, tatsächlich: deepseek-ocr:3b)
  - **Root Cause:** `set_selected_model()`, `set_automatik_model()`, `set_vision_model()` setzten nur Display-Variable, nicht die `*_model_id`
  - **Fix:** Alle drei Handler synchronisieren jetzt die ID via `extract_model_name()`
  - Model-Änderungen werden jetzt auch korrekt gespeichert

- **Model-Settings nicht gespeichert bei Ollama** ([state.py:3210-3211](aifred/state.py#L3210-L3211)):
  - **Problem:** `_save_settings()` wurde bei Ollama-Backend nicht aufgerufen (nur bei vLLM/TabbyAPI/KoboldCPP)
  - **Fix:** `_save_settings()` wird jetzt VOR dem Backend-spezifischen Code aufgerufen

#### Added

- **Universeller Vision-Dokumenttyp-Handler** ([conversation_handler.py:289-333](aifred/lib/conversation_handler.py#L289-L333)):
  - **Vorher:** Unbekannte Typen wie `image_description` zeigten Fehlermeldung
  - **Nachher:** Dynamischer Fallback extrahiert Inhalt aus bekannten Feldern (`content`, `description`, `text`, `items`, `sections`)
  - Vision-LLM kann jetzt beliebige Typen zurückgeben (`photo`, `scene`, `diagram`, etc.)
  - Keine Hardcodierung neuer Typen mehr nötig

---

## [2.4.1] - 2025-12-06

### 🔧 Generic XML-Tag Processing & Vision Collapsible Bugfix

**Major refactor:** Replaced hardcoded XML-tag handling with generic, config-driven processing. Fixed critical double-collapsible bug in Vision-LLM responses.

#### Fixed

- **Double Collapsible Bug in Vision-LLM** ([conversation_handler.py:494-502](aifred/lib/conversation_handler.py#L494-L502), [state.py:1799-1907](aifred/state.py#L1799-L1907)):
  - **Problem:** Vision-LLM with `<think>` tags (qwen3-vl:30b) showed thinking process TWICE
  - **Root Cause:** `<think>` content extracted in conversation_handler.py, rebuilt in state.py, then extracted AGAIN by format_thinking_process()
  - **Fix:** Removed `<think>` extraction from conversation_handler.py; let format_thinking_process() handle it once
  - Vision-LLM responses now show single collapsible as expected

- **Nested XML-Tag Stripping** ([formatting.py:195-201](aifred/lib/formatting.py#L195-L201), [formatting.py:267-272](aifred/lib/formatting.py#L267-L272)):
  - **Problem:** Nested tags like `<code><function>...</function></code>` lost inner tags
  - **Root Cause:** Global regex `re.sub(r'<(\w+)>.*?</\1>', '', ...)` removed ALL tags
  - **Fix:** Only remove extracted top-level tags; preserve nested tags in collapsible content

#### Added

- **Generic XML-Tag Detection** ([formatting.py:94-111](aifred/lib/formatting.py#L94-L111)):
  - New `extract_xml_tags()` helper function with regex `r'<(\w+)>(.*?)</\1>'`
  - Detects ANY XML-style tags automatically (not just hardcoded `<think>`, `<data>`)
  - Returns list of `(tag_name, content)` tuples for processing

- **XML Tag Configuration Dictionary** ([config.py:340-347](aifred/lib/config.py#L340-L347)):
  - `XML_TAG_CONFIG` dict defines icon, label, CSS class per tag
  - Known tags: `think` (💭), `data` (📊), `python` (🐍), `code` (💻), `sql` (🗃️), `json` (📋)
  - **Unknown tags get auto-fallback:** "📄 Tagname" (capitalized)
  - Config-driven: Add new tags without code changes!

- **Auto-Formatting for Unknown XML Tags** ([formatting.py:164-172](aifred/lib/formatting.py#L164-L172)):
  - Any XML tag not in `XML_TAG_CONFIG` gets automatic collapsible with "📄" icon
  - Log info: `ℹ️ Auto-formatiere unbekanntes XML-Tag: <tagname> → 📄 Tagname`
  - Example: LLM generates `<peitenfunktion>code</peitenfunktion>` → "📄 Peitenfunktion" collapsible

#### Changed

- **Refactored format_thinking_process()** ([formatting.py:128-206](aifred/lib/formatting.py#L128-L206)):
  - **Before:** Hardcoded pattern matching for `<think>` and `<data>` tags only
  - **After:** Generic loop over all detected XML tags with config lookup
  - Supports unlimited tag types via `XML_TAG_CONFIG`
  - Inference time shown only for `<think>` tags (reasoning)

- **Refactored build_debug_accordion()** ([formatting.py:209-277](aifred/lib/formatting.py#L209-L277)):
  - Now uses `extract_xml_tags()` instead of hardcoded patterns
  - Consistent behavior with main formatter

- **Simplified Vision Response Reconstruction** ([state.py:1867-1889](aifred/state.py#L1867-L1889)):
  - Removed `vision_think_content` variable (no longer needed)
  - `vision_readable_text` may contain `<think>` tags - handled by format_thinking_process()
  - Only `<data>` block explicitly constructed for JSON responses

#### Technical Details

**Before (Buggy Flow):**
```
conversation_handler → Extracts <think> → yields {"type": "thinking"}
                                          ↓
state.py → Collects think_content → Rebuilds <think> tags
                                          ↓
format_thinking_process() → Extracts <think> AGAIN → DOUBLE COLLAPSIBLE!
```

**After (Fixed Flow):**
```
conversation_handler → Leaves <think> tags in vision_readable_text
                                          ↓
state.py → Passes vision_readable_text unchanged
                                          ↓
format_thinking_process() → Extracts <think> ONCE → Single collapsible!
```

**Generic XML Processing:**
```python
# Old (hardcoded):
if '<think>' in response: ...  # Only 2 tags supported
if '<data>' in response: ...

# New (generic):
xml_tags = extract_xml_tags(response)  # ANY tag detected!
for tag_name, content in xml_tags:
    config = XML_TAG_CONFIG.get(tag_name, fallback)
```

#### Files Modified

1. [aifred/lib/conversation_handler.py](aifred/lib/conversation_handler.py) - Removed <think> extraction
2. [aifred/state.py](aifred/state.py) - Simplified Vision response handling
3. [aifred/lib/formatting.py](aifred/lib/formatting.py) - Generic XML processing, nested tag fix
4. [aifred/lib/config.py](aifred/lib/config.py) - Added XML_TAG_CONFIG dictionary

---

### 🎨 Metadata Formatting & HTML Tag Blacklist (2025-12-06)

**UI refinement:** Improved metadata display and added HTML tag blacklist for XML processing.

#### Added

- **HTML Tag Blacklist** ([html_tags.py](aifred/lib/html_tags.py)):
  - New file with 96 HTML5 tags excluded from XML-Tag processing
  - Prevents HTML elements like `<span>`, `<div>`, `<details>` from becoming collapsibles
  - Categories: inline, block, table, form, media, interactive, meta elements
  - `extract_xml_tags()` now checks against `HTML_TAG_BLACKLIST`

#### Changed

- **Metadata Formatting** ([formatting.py:47-76](aifred/lib/formatting.py#L47-L76)):
  - Changed from HTML `<span style="...">` to Markdown `*...*` (italic)
  - **Why:** `rx.markdown()` escapes inline HTML by default
  - CSS styling in [custom.css](assets/custom.css) makes `<em>` tags gray (#888)
  - Metadata now appears on its own line (Markdown line break: `"  \n"`)

- **Metadata Line Breaks** ([conversation_handler.py](aifred/lib/conversation_handler.py), [state.py](aifred/state.py), [context_builder.py](aifred/lib/research/context_builder.py)):
  - Changed from `\n\n` (paragraph) to `  \n` (Markdown line break)
  - Removes extra blank line between content and metadata
  - Metadata displays directly below content on its own line

#### Files Modified

5. [aifred/lib/html_tags.py](aifred/lib/html_tags.py) - **NEW:** HTML tag blacklist (96 tags)
6. [aifred/lib/formatting.py](aifred/lib/formatting.py) - Markdown metadata formatting
7. [assets/custom.css](assets/custom.css) - CSS for gray italic `<em>` tags
8. [aifred/lib/conversation_handler.py](aifred/lib/conversation_handler.py) - Metadata line breaks
9. [aifred/state.py](aifred/state.py) - Metadata line breaks
10. [aifred/lib/research/context_builder.py](aifred/lib/research/context_builder.py) - Metadata line breaks

## [2.4.0] - 2025-12-04

### 🔗 Vision + Research Integration

**Game Changer:** Intelligent image data extraction flows seamlessly into web research and AI analysis.

#### Added (2025-12-04 03:00)

- **Camera Button for Mobile Devices** ([aifred.py:195-217](aifred/aifred.py#L195-L217), [state.py:228](aifred/state.py#L228), [state.py:2552-2558](aifred/state.py#L2552-L2558)):
  - Browser-based camera detection via JavaScript (`navigator.mediaDevices.enumerateDevices()`)
  - Camera button only visible if browser supports camera access
  - Desktop without camera: Button hidden (no confusing file requestor)
  - Mobile/Tablet with camera: Button visible, opens camera for photo capture
  - Uses `rx.call_script` with callback to set `camera_available` state
  - Positioned left of "Bild hochladen" button

#### Key Feature: Vision JSON Context Propagation

Enable complex queries like: *"Recherchiere die Nebenwirkungen des ersten Medikaments auf der Liste"* (Research side effects of the first medication on the list) - where the medication name is extracted from an uploaded image.

**Example Flow:**
1. Upload medication plan image → Vision-LLM extracts table with 8 medications
2. User asks: *"Recherchiere die Nebenwirkungen des ersten Medikaments"*
3. Query Optimizer receives Vision JSON → Resolves "erstes Medikament" → "Acetylsalicylsäure"
4. Web research: "Acetylsalicylsäure Nebenwirkungen 2025"
5. Main-LLM generates comprehensive answer with sources

#### Added

- **Vision JSON Context Propagation** ([7 files modified]()):
  - Vision JSON automatically passed through entire research pipeline
  - Query Optimizer receives structured data for reference resolution
  - Main-LLM gets Vision JSON as system context for interpretation

- **Two-Phase Vision Architecture** ([state.py:1788-1982](aifred/state.py#L1788-L1982)):
  - **Phase 1:** Vision-LLM extraction (processes ONLY vision items: thinking, response, done, vision_complete)
  - **Phase 2:** Automatik/Research flow (if user text present)
  - Clean separation: Vision loop → Break → Automatik call
  - No race conditions, no duplicate messages

- **Enhanced Query Optimization Prompts**:
  - [prompts/de/query_optimization.txt](prompts/de/query_optimization.txt#L10-L11): Vision JSON awareness
  - [prompts/en/query_optimization.txt](prompts/en/query_optimization.txt#L10-L11): Vision JSON awareness
  - Example: "Recherchiere Nebenwirkungen des ersten Medikaments" + JSON → "Acetylsalicylsäure Nebenwirkungen 2025"

- **Enhanced Automatik Decision Prompts**:
  - [prompts/de/decision_making.txt](prompts/de/decision_making.txt#L1): `{vision_json_context}` placeholder
  - [prompts/en/decision_making.txt](prompts/en/decision_making.txt#L1): `{vision_json_context}` placeholder
  - Automatik-LLM sees Vision JSON for informed research decisions

#### Changed

- **Vision Pipeline Simplification** ([conversation_handler.py:487-500](aifred/lib/conversation_handler.py#L487-L500)):
  - Removed `chat_interactive_mode` call from Vision pipeline
  - Now only yields `vision_complete` signal with `has_user_text` flag
  - state.py handles routing decision (cleaner architecture)

- **Query Optimizer Function Signature** ([query_optimizer.py:22-55](aifred/lib/query_optimizer.py#L22-L55)):
  - Added `vision_json_context: Optional[Dict] = None` parameter
  - Passes Vision JSON to prompt builder

- **Research Query Processor** ([query_processor.py:142-167](aifred/lib/research/query_processor.py#L142-L167)):
  - `process_query_and_search()` accepts `vision_json_context` parameter
  - Forwards Vision JSON to Query Optimizer in all modes (Direct, Hybrid, Normal)

- **Prompt Loader** ([prompt_loader.py:198-219](aifred/lib/prompt_loader.py#L198-L219)):
  - `get_decision_making_prompt()` accepts `vision_json` parameter
  - `get_query_optimization_prompt()` accepts `vision_json` parameter
  - Injects Vision JSON into prompts when available

#### Fixed

- **Race Condition in Vision + Research Flow**:
  - **Problem:** conversation_handler.py called `chat_interactive_mode(history=state.chat_history)` BEFORE state.py processed `vision_complete` signal
  - **Result:** Research pipeline didn't see Vision-Entry in history
  - **Fix:** conversation_handler.py no longer calls chat_interactive_mode; state.py calls it AFTER vision_complete

- **Triple Message Duplication**:
  - **Problem:** Vision-Loop, Research Pipeline, and state.py all created separate history entries
  - **Fix:** Research Pipeline receives `history[:-1]` (excludes temp entry), creates single final entry

- **Missing Progress Updates in UI** ([state.py:1954-1955](aifred/state.py#L1954-L1955)):
  - Added `yield` after progress handler (was missing)
  - Scraping status messages now displayed in UI

#### Technical Implementation

**Files Modified:**
1. [aifred/state.py](aifred/state.py#L1788-L1982) - Two-phase Vision → Automatik flow
2. [aifred/lib/conversation_handler.py](aifred/lib/conversation_handler.py#L487-L500) - Vision pipeline simplification
3. [aifred/lib/query_optimizer.py](aifred/lib/query_optimizer.py#L22-L55) - Vision JSON parameter
4. [aifred/lib/research/query_processor.py](aifred/lib/research/query_processor.py#L142-L167) - Vision JSON propagation
5. [aifred/lib/prompt_loader.py](aifred/lib/prompt_loader.py#L198-L219) - Prompt builders
6. [prompts/de/query_optimization.txt](prompts/de/query_optimization.txt) - Vision JSON awareness
7. [prompts/en/query_optimization.txt](prompts/en/query_optimization.txt) - Vision JSON awareness
8. [prompts/de/decision_making.txt](prompts/de/decision_making.txt) - Vision JSON context
9. [prompts/en/decision_making.txt](prompts/en/decision_making.txt) - Vision JSON context

**Architecture:**
```
User uploads image + asks question
    ↓
PHASE 1: Vision-LLM (Pure OCR)
├─ Input: Image + System Prompt ONLY
├─ User text: STORED (not sent to Vision-LLM)
└─ Output: Structured JSON → vision_complete signal
    ↓
PHASE 2: Automatik-LLM (Decision with Vision Context)
├─ Input: User text + Vision JSON
├─ Decision: <search>yes/no</search>
└─ Example: "Recherchiere Nebenwirkungen von Aspirin" + JSON {"rows": [["Aspirin",...]]}
   → Recognizes medication from JSON → <search>yes</search>
    ↓
PHASE 3: Query Optimization (with Vision JSON)
├─ Input: User text + Vision JSON
├─ Resolves: "erstes Medikament" → "Acetylsalicylsäure" (from JSON row 0)
└─ Output: "Acetylsalicylsäure Nebenwirkungen 2025"
    ↓
PHASE 4: Web Research → Main-LLM (with Vision JSON)
├─ Input: Vision JSON + Research results + User text
└─ Output: Comprehensive answer with sources
```

**Performance:**
- Vision extraction: ~10s (104 tok/s, Ministral-3:8b)
- Query optimization: ~2s (Vision JSON context added)
- Web research: ~5s (6/7 URLs scraped)
- Main-LLM inference: ~23s (14.3k tokens context)
- **Total:** ~40s for complete Vision + Research flow

## [2.3.1] - 2025-12-04

### 🔍 Vision Model Intelligence (2025-12-04)

#### Added
- **Chat Template Detection** ([vision_utils.py](aifred/lib/vision_utils.py)):
  - `get_vision_model_capabilities()`: Single API call for template + context detection
  - Detects `{{ .Prompt }}` (simple) vs. `[SYSTEM_PROMPT]` (full chat support)
  - Auto-detects chat markers: `SYSTEM`, `INST`, `<|im_start|>`, etc.
  - Returns tuple: `(supports_chat_template, context_window_size)`

- **Smart Model Handling** ([conversation_handler.py](aifred/lib/conversation_handler.py)):
  - **Models WITH chat template** (Ministral, Qwen2): Use JSON extraction system prompt
  - **Models WITHOUT chat template** (DeepSeek-OCR, Qwen3-Coder): Skip system prompt + add default text
  - Default prompt for template-less models: "Extrahiere den Text." (DE) / "Extract the text." (EN)
  - Prevents empty inference (DeepSeek-OCR needs text to work)

- **Intrinsic Context Windows**:
  - Vision models now use full model context size (8K-32K)
  - No more 4K Ollama default truncation
  - Reads from model metadata: `deepseekocr.context_length`, `llama.context_length`, etc.

#### Changed
- **Corrected JSON in Collapsibles**:
  - `_json_to_readable()` now returns `tuple[str, dict]` (readable_text, corrected_json)
  - Collapsibles display **auto-corrected JSON**, not raw malformed output
  - Consistent with what's actually processed and sent to Main-LLM

- **Enhanced Error Correction** ([conversation_handler.py:165-185](aifred/lib/conversation_handler.py#L165-L185)):
  - **Nested Array Fix**: `{"columns": [["A", "B"]]}` → `{"columns": ["A", "B"]}`
  - **Header+Data Mix Fix**: `{"columns": [["H"], ["R1"], ["R2"]], "rows": []}` → Split correctly
  - **Ministral-3:3b Compatibility**: Handles malformed JSON with 9-element nested columns
  - **Ministral-3:8b**: Generates perfect JSON, no correction needed

- **Separator Line Positioning** ([state.py:1880-1884](aifred/state.py#L1880-L1884)):
  - Moved separator to AFTER history save (was before)
  - Now shows after "💾 History gespeichert" message
  - Consistent with Main-LLM flow

#### Fixed
- **TypeError Prevention** ([state.py:1820-1827](aifred/state.py#L1820-L1827)):
  - Type-safety check for `item["content"]` (was causing crashes)
  - Gracefully handles dict-typed content with warning log
  - Fallback to `str(content)` if type mismatch detected

- **Vision Model Persistence**:
  - Fixed validation logic to search entire model list (not just first element)
  - Vision model selection now correctly saved and restored across sessions

- **Separator Display**:
  - Separator now always shown (even for HTML fallback models like DeepSeek-OCR)
  - Was missing when `vision_json_response` was empty

#### Performance
- **Single API Call Optimization**:
  - Combined chat template + context window detection (was 2 separate calls)
  - Faster model capability detection (~50% reduction in API overhead)

#### Technical Details

**Model Compatibility Matrix:**

| Model | Template | System Prompt | Auto-Text | Context | JSON Quality |
|-------|----------|---------------|-----------|---------|--------------|
| Ministral-3:8b | `[SYSTEM_PROMPT]` | ✅ Yes | ❌ No | 32768 | ⭐⭐⭐⭐⭐ Perfect |
| Ministral-3:3b | `[SYSTEM_PROMPT]` | ✅ Yes | ❌ No | 32768 | ⚠️ Nested arrays |
| Qwen2-57b | `<\|im_start\|>` | ✅ Yes | ❌ No | 32768 | ⭐⭐⭐⭐⭐ Perfect |
| DeepSeek-OCR:3b | `{{ .Prompt }}` | ❌ No | ✅ Yes | 8192 | ❌ HTML output |
| Qwen3-Coder:30b | `{{ .Prompt }}` | ❌ No | ✅ Yes | 32768 | ❓ Untested |

**Performance Impact:**
- Ministral-3:8b: 9.3s (105.6 tok/s) - Perfect JSON, no corrections needed
- Ministral-3:3b: 3.8s (185.0 tok/s) - Fast but needs auto-correction
- DeepSeek-OCR:3b: 2.3s (312.4 tok/s) - Fastest, but HTML output (fallback works)

## [2.3.0] - 2025-12-03

### 📸 Vision/OCR Support (2025-12-03)

#### Added
- **Vision/OCR Integration** - Complete multimodal image analysis pipeline:
  - **3-Model Architecture**: Vision-LLM (OCR) → Main-LLM (interpretation) → Automatik-LLM (decisions)
  - **Drag & Drop Upload**: Images can be uploaded directly into chat via drag-and-drop or file picker
  - **Auto-Detection**: Automatically detects vision-capable models via backend metadata queries
    - Ollama: Checks `.vision.*` and `.sam.*` keys in model_info
    - vLLM/TabbyAPI: Reads `architectures` from HuggingFace config.json
    - KoboldCPP: Reads `general.architecture` from GGUF metadata
  - **Supported Models**: DeepSeek-OCR, Qwen3-VL, Ministral-3 (3B/8B/14B variants)
  - **Structured Output**: JSON extraction with 5 types (table, list, form, text, mixed)
  - **Smart Formatting**:
    - Collapsible JSON display: `📊 Strukturierte Daten (model-name)`
    - Automatic Markdown conversion (tables, lists, forms)
    - Metadata footer: `( Vision: 3.7s (192.4 tok/s) )`
  - **Performance**: 3-15s inference (85% faster prompts: 119 lines → 18 lines)
  - **Robust Parsing**: Auto-correction for malformed Vision-LLM output
    - Detects nested columns array and auto-splits into columns + rows
    - HTML-to-Markdown fallback for models that ignore system prompts
  - **Image Processing**: Auto-resize to 2048px, JPEG optimization (quality 85)
  - **History Management**: Stores formatted HTML for UI, preserves JSON for follow-up questions

- **Vision Model Selector** - Dedicated dropdown in UI for Vision-LLM selection
  - Shows only vision-capable models (metadata-based filtering)
  - Selection persisted per backend in settings.json
  - Independent from Main-LLM selection

- **New System Prompts**:
  - `prompts/de/vision_ocr.txt`: German OCR prompt (18 lines, optimized)
  - `prompts/en/vision_ocr.txt`: English OCR prompt (18 lines, optimized)

- **Documentation**:
  - `docs/VISION_OCR.md`: Comprehensive Vision/OCR documentation (600+ lines)
    - Architecture diagrams
    - Model benchmarks (performance testing with 7 models)
    - Usage examples
    - Troubleshooting guide
    - JSON format specifications
  - `docs/development/VISION_IMAGE_SUPPORT_PLAN.md`: Implementation plan (archived)

#### Changed
- **README.md**: Updated with Vision/OCR features
  - Added Vision-LLM to Core Features
  - Model recommendations for Vision-LLM (Ministral-3 series)
  - Updated version to 2.3.0

- **Context Manager** (`aifred/lib/context_manager.py`):
  - Modified `strip_thinking_blocks()` to only remove `<think>` tags
  - Preserves `<data>` tags (Vision JSON) during history compression

- **Formatting** (`aifred/lib/formatting.py`):
  - Added `<data>` block rendering (similar to `<think>` but with 📊 icon)
  - Removed inference time from Collapsible headers (now only in metadata footer)
  - Consistent formatting for `<think>` and `<data>` blocks

- **State Management** (`aifred/state.py`):
  - Added `vision_model` field with per-backend persistence
  - Fixed vision model selection bug (was always resetting to first available)
  - Vision pipeline now formats response after stream completion (like Main-LLM)
  - Metrics capture: tokens/s, inference time from backend `done` signal
  - Debug logging: Separator line + timing info after Vision-LLM completion

#### Fixed
- **Vision Model Persistence** - Vision model selection now correctly saved and restored
  - Bug: Validation logic always overwrote selection with first model in list
  - Fix: Search entire list for matching model, not just first element
  - Now correctly handles different model orders across backends

- **Collapsible Display** - Vision JSON now properly rendered in collapsible HTML
  - Bug: Chat history stored raw JSON, causing unformatted display
  - Fix: Store formatted response (Collapsible + Markdown + Metadata) in history
  - Metadata footer now appears below table: `( Vision: 3.7s (192.4 tok/s) )`

- **Malformed JSON Handling** - Auto-correction for common Vision-LLM errors
  - Bug: Some models nest entire table data in `columns` array
  - Fix: Detect `columns[0]` as array → split into proper columns + rows structure
  - Graceful fallback to raw output if all parsing fails

- **HTML Output Handling** - Fallback for models that ignore system prompts
  - Bug: DeepSeek-OCR outputs HTML tables instead of JSON
  - Fix: HTML parser converts `<table>` to Markdown automatically
  - Still displays formatted table despite wrong output format

#### Performance Benchmarks
Model performance on medication plan image (465 KB, Ollama, RTX 4090):

| Model | Inference | Tokens | tok/s | Quality |
|-------|-----------|--------|-------|---------|
| Ministral-3:3b | 9.8s | 313 | 192 | ⭐⭐⭐⭐ |
| Ministral-3:8b | 14.4s | 421 | 184 | ⭐⭐⭐⭐⭐ |
| Ministral-3:14b | 59.9s | 349 | 98 | ⭐⭐⭐⭐⭐ |
| DeepSeek-OCR:3b | 4.3s | 0* | - | ❌ HTML |
| Qwen3-VL:8b | 56.6s | 0 | - | ❌ Empty |

\* Outputs HTML instead of JSON

#### Technical Details
- **Multimodal Messages**: Support for mixed text + image content arrays
- **Base64 Encoding**: Images converted to data URLs for API compatibility
- **Backend Integration**: Works with Ollama (tested), vLLM, TabbyAPI, KoboldCPP
- **Error Correction**: Robust JSON parsing with multiple fallback strategies
- **Streaming**: Non-streaming for Vision-LLM (prevents fragment display)

#### Files Modified
- `aifred/state.py`: Vision pipeline, model persistence, metrics capture
- `aifred/lib/conversation_handler.py`: Vision extraction, JSON parsing, HTML fallback
- `aifred/lib/formatting.py`: `<data>` block rendering, header time removal
- `aifred/lib/context_manager.py`: `<data>` tag preservation
- `aifred/lib/vision_utils.py`: Vision model detection (new file)
- `prompts/de/vision_ocr.txt`: Optimized OCR prompt (85% shorter)
- `prompts/en/vision_ocr.txt`: Optimized OCR prompt (85% shorter)
- `README.md`: Vision/OCR features documentation
- `docs/VISION_OCR.md`: Comprehensive technical documentation (new file)

---

## [2.2.0] - 2025-12-02

### 📚 Documentation & Configuration (2025-12-02)

#### Changed
- **Documentation Refactoring** - Complete restructuring for better maintainability:
  - **READMEs Cleaned Up**: Removed detailed changelog sections from README.md and README.de.md
  - Replaced with concise "What's New" section linking to CHANGELOG.md
  - README now focuses purely on project description and features
  - **Session Changelogs Archived**: Moved to `docs/archive/session-changelogs/`
    - CHANGELOG_2025-11-01.md, CHANGELOG_2025-11-02.md, CHANGELOG_2025-11-02_Session4.md
    - CHANGELOG_tokens_per_sec_uniformity.md
  - **PDF Duplicates Removed** (118KB freed):
    - Deleted vllm_pascal_patches.pdf and multi_agent_research_technical.pdf
    - Markdown versions remain as source of truth in `docs/research/`
  - **docs/INDEX.md Updated**: New archive/ directory structure documented

- **GPU Display Enhancements**:
  - Multi-GPU support: "2x Tesla P40 (Compute 6.1, 48 GB total)"
  - Single GPU format: "Tesla P40 (Compute 6.1, 24 GB)"
  - **Nominal VRAM Values**: Shows marketing specs (48 GB) instead of actual available (45 GB)
  - GPU info now displayed in Settings UI, startup log, and debug console
  - Added `gpu_count`, `gpu_vram_gb`, and `gpu_display_text` computed property

- **Ollama Configuration Documented** ([aifred/lib/config.py](aifred/lib/config.py)):
  - Comprehensive documentation of Ollama systemd environment variables
  - Explains current setup: 2x Tesla P40 with `OLLAMA_MAX_LOADED_MODELS=2`
  - Notes that MAX_LOADED_MODELS=2 is perfect for future Dual-LLM Debate System
  - Instructions for modifying `/etc/systemd/system/ollama.service.d/override.conf`

#### Fixed
- **Model Display Bug** ([aifred/lib/conversation_handler.py](aifred/lib/conversation_handler.py), [aifred/lib/research/query_processor.py](aifred/lib/research/query_processor.py)):
  - Fixed Ollama 500 Internal Server Error when passing model names with size suffix
  - Added `extract_model_name()` helper to remove " (X.X GB)" before backend API calls
  - Model names with sizes (e.g., "qwen3:4b (2.3 GB)") now correctly converted to pure names

#### Files Modified (2025-12-02)
- README.md, README.de.md: Changelog sections removed (-66 lines)
- docs/INDEX.md: Updated structure with archive directory
- aifred/state.py: GPU display fields and computed properties
- aifred/lib/gpu_detection.py: Multi-GPU detection with total VRAM
- aifred/aifred.py: GPU display in Settings UI
- aifred/lib/config.py: Ollama systemd configuration documentation
- aifred/lib/conversation_handler.py: Model name extraction
- aifred/lib/research/query_processor.py: Model name extraction

---

### ⚡ KoboldCPP Auto-Shutdown: Rolling Window Monitoring (2025-11-30)

#### Changed
- **Rolling Window Inactivity Monitoring** ([aifred/state.py:966-1086](aifred/state.py#L966-L1086)):
  - **Simplified Logic**: Replaced complex "Simple Reset" approach with clean Rolling Window pattern
  - **Continuous Checking**: GPU checks every 60s (was: 10s) from start to finish
  - **Responsive Timer Reset**: Any GPU activity resets counter with debug message
  - **"Bedenkzeit" Use Case**: User has full timeout duration after inference to start new query
  - **Example**: 5min timeout = 5 consecutive idle checks à 60s
    - Inferenz finishes at 16:22 → idle checks at 16:23, 16:24, 16:25, 16:26, 16:27 → shutdown at 16:27
    - New inference at 16:25 → counter reset (was 3/5) → new 5min timer starts after inference

- **Updated Configuration** ([aifred/lib/config.py:234-248](aifred/lib/config.py#L234-L248)):
  - `KOBOLDCPP_INACTIVITY_TIMEOUT = 300` (5 minutes for testing, was: 30s)
  - `KOBOLDCPP_INACTIVITY_CHECK_INTERVAL = 60` (1 minute, was: 10s)
  - Added Rolling Window documentation to config comments

#### Technical Details
- **Before (Complex)**:
  - Wait period (timeout - 30s) with activity detection
  - Final 30s with separate check loop
  - Nested loops, activity detection during wait
  - ~130 lines of code
- **After (Simple)**:
  - Single while loop with 60s sleep
  - Continuous checks with consecutive idle counter
  - GPU activity → reset counter + debug message
  - ~100 lines of code (-23% reduction)
- **Debug Message**: `🔄 GPU activity detected - idle timer reset (was at X/5 checks)`

#### Impact
- **Simpler Code**: Single loop instead of nested wait + check loops
- **More Efficient**: 60s intervals (6x less CPU/GPU queries than 10s)
- **Better UX**: User sees timer reset messages when new inference starts
- **Accurate Timeout**: Integer division ensures exact timeout (300s = 5 × 60s)

#### Files Modified
- [aifred/state.py](aifred/state.py): Lines 966-1086 (complete function rewrite)
- [aifred/lib/config.py](aifred/lib/config.py): Lines 234-248 (updated config + docs)

---

## [Unreleased] - 2025-11-29

### 🔔 KoboldCPP Auto-Shutdown: Debug Console Messages (Fixed)

#### Changed
- **Unified Logging System for Auto-Shutdown** ([aifred/lib/inactivity_monitor.py:31-32, 60-76, 240-252](aifred/lib/inactivity_monitor.py#L60-L76)):
  - **Fixed**: Shutdown messages now correctly appear in Debug Console UI
  - **Removed**: Custom `debug_callback` parameter (was bypassing queue system)
  - **Solution**: Direct use of `log_message()` from `logging_utils`
  - `log_message()` automatically writes to BOTH:
    - `/logs/aifred_debug.log` (file logging)
    - `_message_queue` (UI Debug Console via queue polling)
  - **Removed**: GPU statistics message (user request)
  - **Example Messages** (now visible in Debug Console):
    - `🛑 KoboldCPP wird wegen Inaktivität heruntergefahren (GPUs waren 30s idle, Timeout: 30s)`
    - `✅ KoboldCPP erfolgreich heruntergefahren`

#### Technical Details
- **Root Cause**: Custom callback was bypassing the `_message_queue` used by UI polling
- **Fix**: Use existing `log_message()` function that writes to queue when `CONSOLE_DEBUG_ENABLED=True`
- **Pattern**: Follows same approach as all other logging throughout the codebase
- **Removed Code**:
  - `Callable` import (no longer needed)
  - `debug_callback` parameter from `__init__`
  - Conditional callback logic in shutdown messages
  - GPU statistics line: `GPU-Statistik: X aktiv / Y idle Checks`

#### Impact
- **Before**: Messages appeared in log file but NOT in Debug Console UI
- **After**: Real-time shutdown notifications in BOTH log file AND Debug Console UI
- **Simpler**: No custom callbacks - uses unified logging system
- **Cleaner**: Removed unnecessary GPU statistics message

#### Files Modified
- [aifred/lib/inactivity_monitor.py](aifred/lib/inactivity_monitor.py): Lines 31-32, 60-76, 240-252
- [aifred/state.py](aifred/state.py): Line 1174-1178 (removed `debug_callback` parameter)

---

## [Unreleased] - 2025-11-25

### 🧠 Automatik-LLM: Thinking Model Compatibility & Robust Fallbacks

#### Added
- **Query Optimization Fallback** ([aifred/lib/query_optimizer.py:118-124](aifred/lib/query_optimizer.py#L118-L124)):
  - Empty query detection when Thinking Models fail to produce keywords
  - Falls back to original user query instead of empty search
  - Preserves full question with temporal context (e.g., "Wie wird das Wetter morgen?" → adds "2025")
  - Ensures web search always works, even with suboptimal models

- **`enable_thinking` Toggle Propagation** ([aifred/lib/conversation_handler.py:631-636](aifred/lib/conversation_handler.py#L631-L636), [aifred/lib/intent_detector.py:77-82](aifred/lib/intent_detector.py#L77-L82), [aifred/lib/query_optimizer.py:81-86](aifred/lib/query_optimizer.py#L81-L86)):
  - User's thinking toggle now propagates to all Automatik-LLM tasks
  - Explicit logging shows when toggle is active vs. default
  - Default: `enable_thinking: False` (fast mode without reasoning)
  - Allows debugging Thinking Model behavior when needed

#### Changed
- **Optimized `num_predict` Values** for Automatik-LLM tasks:
  - Decision-Making: 256 → **64 tokens** (`<search>yes</search>` = ~20 tokens, 3x buffer)
  - Intent Detection: 256 → **32 tokens** (`FAKTISCH`/`KREATIV` = ~10 tokens, 3x buffer)
  - Query Optimization: 512 → **128 tokens** (keywords = ~30 tokens, 4x buffer)
  - Minimizes generation time while maintaining sufficient headroom
  - Reduces VRAM waste for short, structured outputs

- **Removed Redundant Log** ([aifred/backends/koboldcpp.py:383-384](aifred/backends/koboldcpp.py#L383-L384)):
  - Removed "💾 KoboldCPP Context: X tokens (from global state)" message
  - Context is already logged during server startup
  - Reduces console clutter on every request

#### Known Issues
- **Thinking Models Incompatible with Automatik-LLM**:
  - Thinking Models (e.g., QwQ-32B, DeepSeek-R1) ignore `enable_thinking: False`
  - Always output `<think>` tags and verbose reasoning
  - Exceed `num_predict` limits before reaching expected output
  - **Impact**: Query-Opt produces empty string (fallback works), Decision-Making may fail
  - **Recommendation**: Use Instruct models for Automatik-LLM, Thinking models for main LLM only
  - **Technical Details**:
    - With `num_predict: 64`, Decision-Making works if `enable_thinking: True` (compact reasoning)
    - With `num_predict: 128`, Query-Opt always fails (reasoning too verbose)
    - Models trained to reason cannot be suppressed by flags or prompts

### 🎯 KoboldCPP Dynamic RoPE Scaling & VRAM Optimization

#### Added
- **KoboldCPP Backend Support** ([aifred/backends/koboldcpp.py](aifred/backends/koboldcpp.py)):
  - Full KoboldCPP integration as fourth backend (alongside Ollama, vLLM, TabbyAPI)
  - Auto-start functionality with intelligent VRAM-based context calculation
  - Dynamic RoPE (Rotary Position Embedding) scaling for context extension
  - Single-pass optimization: calculates optimal context + RoPE factor before first start
  - OOM retry strategy with automatic MB/token adjustment

- **Intelligent Context + RoPE Calculation** ([aifred/lib/koboldcpp_manager.py:443-534](aifred/lib/koboldcpp_manager.py#L443-L534)):
  - New `calculate_optimal_context_and_rope()` method for VRAM-based optimization
  - Automatically determines if RoPE scaling is beneficial or if context is VRAM-limited
  - **Logic**:
    - If `max_tokens > native_context`: Apply RoPE scaling (extend context beyond native)
    - If `max_tokens ≤ native_context`: Use available VRAM without RoPE (VRAM-limited)
  - Caps RoPE factor at configurable maximum (default: 2.0x)
  - Caps context at KoboldCPP hard limit (262,144 tokens)

- **GGUF Metadata Utilities** ([aifred/lib/gguf_utils.py](aifred/lib/gguf_utils.py), [aifred/lib/gguf_utils_vision.py](aifred/lib/gguf_utils_vision.py)):
  - Extract native context from GGUF files (avoids hardcoded values)
  - Detect architecture (Qwen2, Llama, etc.) for accurate KV cache calculation
  - Extract quantization level from filename (Q4_K_M, Q8_0, etc.)
  - Calculate MB/token for KV cache based on architecture + quantization
  - Vision model support: VL models use same KV cache as text models (no multiplier)

- **Configuration Options** ([aifred/lib/config.py:228-259](aifred/lib/config.py#L228-L259)):
  ```python
  KOBOLDCPP_TARGET_FREE_VRAM_MB = 600        # Target free VRAM after start
  KOBOLDCPP_SAFETY_MARGIN_MB = 150           # CUDA scratch buffer (fixed)
  KOBOLDCPP_MAX_ROPE_FACTOR = 2.0            # Maximum RoPE scaling factor
  KOBOLDCPP_OOM_RETRY_MB_PER_TOKEN_ADJUSTMENT = 0.10  # 10% more conservative per retry
  KOBOLDCPP_MAX_OOM_RETRIES = 3              # Maximum retry attempts
  ```

#### Changed
- **Removed vLLM/TabbyAPI/KoboldCPP Automatik-LLM Messages** ([aifred/state.py:561,730,2130](aifred/state.py)):
  - Removed verbose "🔄 Automatik-LLM angepasst..." debug messages
  - These backends can only load one model - adjustment happens silently
  - Reduces console clutter and prevents horizontal scrolling

#### Fixed
- **KoboldCPP RoPE Calculation Bugs** (3 critical fixes):
  - **Bug #1**: Added KoboldCPP maximum context cap (262,144 tokens) - prevented exceeding hard limit
  - **Bug #2**: Removed incorrect `--overridenativecontext` parameter - was using wrong value
  - **Bug #3**: Fixed scope error with `log_feedback()` - replaced with `logger.info()` in calculation method

#### Technical Details

**RoPE Scaling Strategy:**
- **Small Models** (32k native context): Benefit from RoPE extension
  - Example: Qwen3-14B (32k native) → 65k with RoPE 2.0x @ RTX 3090 Ti
- **Large Models** (262k native context): Already at maximum
  - Example: Qwen3-VL-8B (262k native) → No RoPE needed, at KoboldCPP limit

**VRAM Calculation:**
```python
usable_vram = total_vram - model_size - safety_margin - target_free_vram
max_tokens = usable_vram / mb_per_token

if max_tokens > native_context:
    rope_factor = max_tokens / native_context  # Extend beyond native
    context = min(max_tokens, 262144)          # Cap at KoboldCPP max
else:
    rope_factor = 1.0                          # No RoPE, VRAM-limited
    context = max_tokens
```

**OOM Retry Strategy:**
If initial calculation is too optimistic:
1. Attempt 1: Optimal calculation with measured MB/token
2. Attempt 2: +10% more conservative MB/token → recalculate
3. Attempt 3: +10% again → recalculate
4. Fail after 3 attempts

**KV Cache Optimization:**
- Q4 quantization: 0.05 MB/token (75% savings vs FP16)
- Vision models: Same KV cache as text (vision encoder separate)
- Architecture-aware: Dense vs MoE models handled correctly

#### Files Modified
- [aifred/backends/koboldcpp.py](aifred/backends/koboldcpp.py): Complete backend implementation
- [aifred/lib/koboldcpp_manager.py](aifred/lib/koboldcpp_manager.py): Process management + optimization
- [aifred/lib/gguf_utils.py](aifred/lib/gguf_utils.py): GGUF metadata extraction
- [aifred/lib/gguf_utils_vision.py](aifred/lib/gguf_utils_vision.py): Architecture detection + KV cache calculation
- [aifred/lib/config.py](aifred/lib/config.py): KoboldCPP configuration constants
- [aifred/state.py](aifred/state.py): Removed verbose Automatik-LLM sync messages (3 locations)

#### Performance Results
**RTX 3090 Ti (24GB VRAM):**
- Qwen3-VL-8B (8.5 GB): 262,144 tokens (maximum, no RoPE needed)
- Qwen3-14B (8 GB): 65,536 tokens (32k native × 2.0 RoPE)
- Target free VRAM: ~600 MB (optimal for stability)

---

## [2.1.0] - 2025-11-22

### 🚀 Major Features

#### Unified VRAM Cache System
- **Created**: `aifred/lib/model_vram_cache.py` - Unified cache combining vLLM calibrations and VRAM ratio measurements
- **Backend-Aware Structure**: Single cache file with per-backend model tracking (Ollama/vLLM/TabbyAPI)
- **Automatic Migration**: Old `vllm_context_cache.json` automatically migrated to new unified format on first load
- **Universal VRAM Ratio Tracking**: Measures MB/token for ALL backends (Ollama active, vLLM/TabbyAPI for validation)
- **Architecture Detection**: Separate ratios for MoE vs Dense models (0.10 vs 0.15 MB/token)

### Added

#### Model VRAM Cache Functions
- **`load_cache()`**: Loads unified cache with automatic migration from old vLLM cache
- **`add_vram_measurement()`**: Records VRAM ratio measurements for any backend (with backend parameter)
- **`get_calibrated_ratio()`**: Returns measured MB/token ratio or default fallback
- **`add_vllm_calibration()`**: Stores vLLM-specific context calibration points
- **`interpolate_vllm_context()`**: Linear interpolation for vLLM context limits at different VRAM levels
- **`get_measurement_count()`**: Returns number of VRAM measurements for a model

#### Cache File Structure
```json
{
  "model_name": {
    "backend": "ollama|vllm|tabbyapi",
    "architecture": "moe|dense",
    "native_context": 262144,
    "gpu_model": "NVIDIA GeForce RTX 3090 Ti",
    "vram_ratio": {
      "measurements": [
        {
          "context_tokens": 20720,
          "measured_mb_per_token": 0.0872,
          "measured_at": "2025-11-22T02:30:00"
        }
      ],
      "avg_mb_per_token": 0.0872
    },
    "vllm_calibrations": [
      {
        "free_vram_mb": 22968,
        "max_context": 21608,
        "measured_at": "2025-11-21T23:31:17"
      }
    ]
  }
}
```

- **Dynamic Context Window Optimization** ([aifred/lib/context_manager.py:184-187](aifred/lib/context_manager.py#L184-L187)):
  - Removed fixed context size rounding (2K, 4K, 8K, etc.)
  - Now uses exact calculated `num_ctx` values for maximum efficiency
  - Automatically utilizes full VRAM-based limit for large contexts
  - **Example**: 42K needed → Uses 42K directly (instead of rounding to 64K or capping at 40K)
  - **Benefit**: ~7-10% more context available for long conversations without wasting RAM

- **Ollama: Loaded Model Context Detection** ([aifred/backends/ollama.py:610-640](aifred/backends/ollama.py#L610-L640)):
  - New `get_loaded_model_context()` method queries `/api/ps` for actual context length
  - Returns the exact `num_ctx` value a loaded model is using
  - Used for accurate history compression limits

### Changed

#### Updated All VRAM Cache Imports (6 Files Modified)
- **`aifred/lib/gpu_utils.py`** (Line 243):
  - Changed: `from .vram_ratio_cache import ...` → `from .model_vram_cache import ...`
  - Functions: `get_calibrated_ratio`, `get_measurement_count`

- **`aifred/lib/conversation_handler.py`** (Lines 498-513):
  - Changed: `from aifred.lib.vram_ratio_cache import add_measurement` → `from aifred.lib.model_vram_cache import add_vram_measurement`
  - **NEW Parameter**: Added `backend=backend_type` to measurement calls
  - Impact: VRAM measurements now backend-aware for Ollama/vLLM/TabbyAPI

- **`aifred/lib/vllm_manager.py`** (5 locations - lines 503, 557, 603, 780, 831):
  - Changed: `from aifred.lib.vllm_context_cache import ...` → `from aifred.lib.model_vram_cache import ...`
  - Function renames:
    - `interpolate_context` → `interpolate_vllm_context as interpolate_context`
    - `add_calibration_point` → `add_vllm_calibration as add_calibration_point`

- **`aifred/lib/vllm_utils.py`** (Lines 48, 75):
  - Changed: `from .vllm_context_cache import ...` → `from .model_vram_cache import ...`
  - Function renames:
    - `get_calibrations` → `get_vllm_calibrations as get_calibrations`
    - `interpolate_context` → `interpolate_vllm_context as interpolate_context`

### Removed

- **Deleted Old Cache Modules** (No backward compatibility per user requirement):
  - `aifred/lib/vram_ratio_cache.py` - Replaced by unified cache
  - `aifred/lib/vllm_context_cache.py` - Replaced by unified cache
  - `~/.config/aifred/vllm_context_cache.json` - Automatically migrated to `model_vram_cache.json`

### Fixed

#### Critical Web Research Crash - ValueError in Scraper Orchestrator
- **Problem**: `ValueError: too many values to unpack (expected 2)` during web research
- **Location**: [aifred/lib/research/scraper_orchestrator.py:158](aifred/lib/research/scraper_orchestrator.py#L158)
- **Root Cause**:
  - Line 84 `unload_and_preload()` returns 3 values: `(success, load_time, models)`
  - Line 128 correctly unpacks 3 values in the first code path
  - Line 158 **incorrectly** only unpacked 2 values: `success, load_time = await preload_task`
- **Impact**: Web research would crash when Main-LLM preload finished after scraping completed
- **Fix Applied**:
  ```python
  # Before (Line 158)
  success, load_time = await preload_task

  # After (Line 158-162)
  success, load_time, unloaded_models = await preload_task
  if unloaded_models:
      models_str = ", ".join(unloaded_models)
      log_message(f"🗑️ Entladene Modelle: {models_str}")
      yield {"type": "debug", "message": f"🗑️ Entladene Modelle: {models_str}"}
  ```
- **Additional Enhancement**: Now properly logs unloaded models in both code paths (lines 126-135, 158-169)
- **Testing**: Syntax validated with `python3 -m py_compile`

### Technical Details

#### Files Modified (7 total)
1. **Created**: [aifred/lib/model_vram_cache.py](aifred/lib/model_vram_cache.py) (420 lines)
   - Unified cache management with automatic migration
   - VRAM ratio tracking for all backends
   - vLLM calibration with linear interpolation

2. **Modified**: [aifred/lib/gpu_utils.py](aifred/lib/gpu_utils.py) (Line 243)
   - Updated imports from old `vram_ratio_cache` to `model_vram_cache`

3. **Modified**: [aifred/lib/conversation_handler.py](aifred/lib/conversation_handler.py) (Lines 498-513)
   - Added `backend` parameter to VRAM measurement calls
   - Backend-aware measurement storage

4. **Modified**: [aifred/lib/vllm_manager.py](aifred/lib/vllm_manager.py) (5 locations)
   - Updated all vLLM cache function imports
   - Function alias mapping for compatibility

5. **Modified**: [aifred/lib/vllm_utils.py](aifred/lib/vllm_utils.py) (2 locations)
   - Updated vLLM utility imports

6. **Modified**: [aifred/lib/research/scraper_orchestrator.py](aifred/lib/research/scraper_orchestrator.py) (Lines 158-169)
   - **CRITICAL FIX**: Corrected async task unpacking
   - Added unloaded models logging

7. **Deleted**: `aifred/lib/vram_ratio_cache.py` - Functionality moved to unified cache
8. **Deleted**: `aifred/lib/vllm_context_cache.py` - Functionality moved to unified cache
9. **Deleted**: `~/.config/aifred/vllm_context_cache.json` - Auto-migrated to `model_vram_cache.json`

#### Cache Migration Details
- **Automatic**: No user intervention required
- **One-Time**: Migration runs on first `load_cache()` call
- **Data Preservation**: All vLLM calibrations preserved
- **Format**: 5 models migrated (Qwen3-8B-AWQ, Qwen3-4B, Qwen2.5-3B, Qwen3-4B-AWQ, Qwen3-30B-A3B-AWQ)
- **Location**: `~/.config/aifred/model_vram_cache.json`

#### Performance Impact
- **VRAM Optimization**: More accurate context limits with calibrated ratios
- **Bug Fix Impact**: Web research stability improved (no more mid-research crashes)
- **Cache Efficiency**: Single cache file instead of two separate files
- **Future-Ready**: Extensible for new backends (e.g., LM Studio, LocalAI)

#### GPU Performance Observations
- **MoE Models** (Qwen3-30B-A3B): 17-21% → 59-60% GPU utilization (prefill → generation)
  - Speed: 61.4 tok/s
  - Power: 117-221W
  - VRAM: 22.8 GB
  - **Reason**: Sparse activation (10-20% active parameters), memory-bound operation

- **Dense Models** (Qwen3-32B): 14-37% → 83-95% GPU utilization (prefill → generation)
  - Speed: 31.9 tok/s (50% slower)
  - Power: 118-446W (2x power consumption)
  - VRAM: 23.9 GB
  - **Reason**: All parameters active, compute-bound operation

- **Conclusion**: MoE ~60% GPU utilization at double the speed is expected and optimal behavior

### Changed (History Compression)
- **History Compression Context Limit** ([aifred/state.py:1404-1444](aifred/state.py#L1404-L1444)):
  - **Ollama**: Now uses `/api/ps` to get actual loaded model context (e.g., 40960 or 44051)
  - **vLLM/TabbyAPI**: Uses `calculate_dynamic_num_ctx()` for consistent limit calculation
  - **Result**: History percentage now shows accurate utilization
  - **Before**: "2,169 / 7,505 tok (28%)" ❌ (wrong VRAM calculation)
  - **After**: "2,169 / 40,960 tok (5%)" ✅ (actual model context)

### Fixed
- **vLLM Context Calibration Safety Buffer** ([aifred/lib/vllm_manager.py:537-544, 666-673](aifred/lib/vllm_manager.py#L537-L544)):
  - Changed from fixed 150 token buffer to 2% percentage-based safety margin
  - Applied iteratively at each calibration attempt
  - **Before**: 3 attempts needed, 150 tokens wasted regardless of context size
  - **After**: 2 attempts, scales with context (e.g., 440 tokens at 22K context)
  - **Result**: More efficient calibration with better success rate

- **vLLM: Automatik-LLM Synchronization** ([aifred/state.py:460-466, 566-571, 1786-1822](aifred/state.py#L1786-L1822)):
  - vLLM can only load ONE model at a time (unlike Ollama)
  - Now automatically syncs Automatik-LLM to match Main-LLM for vLLM backend
  - Applied at three points: model change, backend init (slow path), backend init (fast path)
  - **Before**: 404 errors when Automatik-LLM differed from Main-LLM
  - **After**: Automatic sync with debug message explaining why

- **YaRN Factor Reset on Model Change** ([aifred/state.py:1786-1822](aifred/state.py#L1786-L1822)):
  - YaRN factor now automatically resets to 1.0 when changing models
  - Prevents crashes from trying to load new model with old YaRN extension
  - Resets all YaRN state: factor, input, max_factor, max_tested
  - Shows loading spinner during model change (40-70 seconds for vLLM)

## [Unreleased] - 2025-11-18

### Changed
- **UI Layout Optimization** ([aifred/aifred.py:1486-1506](aifred/aifred.py#L1486-L1506)):
  - Improved usability by reordering main UI components
  - **New order**: Chat History → Input Controls → Debug Console & Settings
  - **Benefit**: After reading conversation, text input is directly accessible without scrolling
  - Debug console moved to bottom for quick access when needed

- **Query Optimization: URL Handling** ([prompts/de/query_optimization.txt](prompts/de/query_optimization.txt), [prompts/en/query_optimization.txt](prompts/en/query_optimization.txt)):
  - Enhanced query optimization to preserve URLs completely
  - **New rule**: URLs and web addresses (https://, www., domain.com, github.com/...) are returned UNFILTERED
  - **Examples added**: github.com/user/repo, example.com/blog/article
  - **Benefit**: Web search modes (quick/detailed) can now handle URL-based queries correctly without breaking them into keywords

### Fixed
- **Model Preload Order** ([aifred/backends/ollama.py](aifred/backends/ollama.py), [aifred/lib/conversation_handler.py](aifred/lib/conversation_handler.py), [aifred/lib/research/scraper_orchestrator.py](aifred/lib/research/scraper_orchestrator.py), [aifred/state.py:1066-1086](aifred/state.py#L1066-L1086)):
  - Fixed unnecessary model unload/reload during preload phase
  - **Problem**: `preload_model()` internally called `unload_all_models()`, which unloaded ALL models including the target model if already loaded
  - **Symptom**: Debug showed `🗑️ Entladene Modelle: qwen3:4b, qwen3:14b` (14B shouldn't be there!)
  - **Root Cause**: Sequence was Automatik-LLM decision → preload → unload ALL → reload target
  - **Solution**: Removed `unload_all_models()` from `preload_model()` internals, added explicit calls before preload in callers
  - **Impact**: Eliminates unnecessary model reload, clearer debug output, proper VRAM management
  - Changed return signature: `tuple[bool, float, list[str]]` → `tuple[bool, float]`
  - Correct order now: Automatik decision → explicit unload → load Haupt-LLM

---

### 🧠 VRAM-Based Dynamic Context Window Calculation

#### Added
- **Automatic VRAM-Based Context Calculation** ([aifred/lib/gpu_utils.py](aifred/lib/gpu_utils.py)):
  - Dynamically calculates maximum practical `num_ctx` based on available GPU memory
  - Prevents CPU offloading by staying within VRAM limits
  - Two-scenario detection: Model loaded vs not loaded (via `/api/ps` endpoint)
  - Reads model size from blob filesystem (no hardcoded values)
  - Safety margin: 512 MB (optimized from initial 1024 MB)
  - KV-cache ratio: 0.097 MB/token (empirically measured for Qwen3 MoE models)
  - **VRAM Stabilization Polling** ([aifred/lib/gpu_utils.py:138-169](aifred/lib/gpu_utils.py#L138-L169)):
    - Waits for VRAM to stabilize after model preload (prevents premature measurement)
    - Polls every 200ms, requires 2 consecutive stable readings (< 50 MB difference)
    - Maximum wait time: 3 seconds
    - Ensures accurate context calculation after Ollama finishes loading model into VRAM

- **Model Load Detection** ([aifred/lib/gpu_utils.py:22-56](aifred/lib/gpu_utils.py#L22-L56)):
  - `is_model_loaded()` checks Ollama `/api/ps` endpoint
  - Prevents double-subtraction of model size from free VRAM
  - Scenario 1 (model NOT loaded): `vram_for_context = free_vram - model_size - margin`
  - Scenario 2 (model IS loaded): `vram_for_context = free_vram - margin`

- **Model Size Extraction** ([aifred/backends/ollama.py:430-520](aifred/backends/ollama.py#L430-L520)):
  - Enhanced `get_model_context_limit()` to return `(context_limit, model_size_bytes)`
  - Extracts blob path from modelfile (`FROM /path/to/blobs/sha256-...`)
  - Reads actual file size from filesystem (e.g., 17.28 GB for qwen3:30b)
  - Falls back gracefully if blob not found (no VRAM calculation)

- **Automatic Model Unloading** ([aifred/backends/ollama.py:349-454](aifred/backends/ollama.py#L349-L454)):
  - **Problem**: Multiple models loaded simultaneously (e.g., Automatik 3B + Main 30B) consumed VRAM
  - **Solution**: `preload_model()` now unloads ALL other models before loading requested model
  - Uses `/api/ps` to detect loaded models, then sends `keep_alive=0` to unload each
  - Returns list of unloaded models for debug output
  - **Impact**: Ensures maximum VRAM available for context calculation (23GB → 35K tokens instead of 730MB → 7K tokens)
  - **UI Feedback**: Shows `🗑️ Entladene Modelle: qwen2.5:3b` in debug console
  - **Bug Fix**: Added required `prompt` field to `/api/generate` unload request (prevents preload failure with 0.0s time)

- **UI Integration** ([aifred/aifred.py:1151-1188](aifred/aifred.py#L1151-L1188)):
  - Manual context override option (numeric input field)
  - Checkbox: "Setze Context-Fenster auf Basis von VRAM"
  - Warning message when manual override active
  - Real-time VRAM debug messages in UI console

- **Debug Logging** ([aifred/lib/gpu_utils.py:196-236](aifred/lib/gpu_utils.py#L196-L236)):
  - Detailed VRAM calculation messages collected as list
  - Yielded to UI console for real-time visibility
  - Shows: Free VRAM, model size, safety margin, calculated context, architectural limit
  - German number formatting (35.010 T instead of 35,010T)
  - **Improved Readability**: Spaces between numbers and units (e.g., `3853 MB` instead of `3853MB`, `0.097 MB/T` instead of `0.097MB/T`)

#### Configuration
- **Optimized Constants** ([aifred/lib/config.py](aifred/lib/config.py)):
  - `VRAM_SAFETY_MARGIN = 512` (MB) - reduced from 1024 MB
  - `VRAM_CONTEXT_RATIO = 0.097` (MB/token) - empirically measured
  - `ENABLE_VRAM_CONTEXT_CALCULATION = True` - feature flag

#### Performance Results (RTX 3090 Ti, 24GB VRAM)
- **qwen3:30b-a3b-instruct-2507-q4_K_M** (17.28 GB):
  - Free VRAM: 3908 MB
  - Context for KV-cache: 3396 MB (after 512 MB safety margin)
  - **Calculated Context**: 35,010 tokens (3396 MB / 0.097 MB/T)
  - Model architectural limit: 262,144 tokens
  - **Practical limit**: 35,010 tokens (VRAM-constrained, prevents CPU offloading)

- **qwen3:32b-q4_K_M** (18.81 GB, older generation):
  - Free VRAM: 1780 MB (with Whisper loaded)
  - Context for KV-cache: 1268 MB
  - **Calculated Context**: 13,072 tokens
  - Model architectural limit: 40,960 tokens (only!)
  - **Problem**: Input 16K tokens → exceeds 13K limit → CPU offloading (17.6 t/s instead of 80+ t/s)
  - **Recommendation**: Use qwen3:30b-a3b instead (newer, larger context, smaller size)

#### Impact
- **Before**: Hardcoded context windows → frequent CPU offloading on large inputs
- **After**: Automatic adaptation to available VRAM → maximizes usable context
- **User Benefit**: No more manual tuning, system automatically prevents CPU offloading

#### Technical Details
- **VRAM Query**: Uses `nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits`
- **Model Load Detection**: HTTP GET to `http://localhost:11434/api/ps`
- **Fallback**: If VRAM calculation fails → use model's architectural limit
- **Validation**: Minimum 100 MB VRAM required, otherwise fallback to 2048 tokens

#### Files Modified
- [aifred/lib/gpu_utils.py](aifred/lib/gpu_utils.py): Lines 22-238 (VRAM calculation, stabilization polling, model load detection, improved debug formatting)
- [aifred/backends/ollama.py](aifred/backends/ollama.py): Lines 349-520 (automatic model unloading, model size extraction)
- [aifred/backends/base.py](aifred/backends/base.py): Lines 159-173 (preload_model signature updated)
- [aifred/backends/vllm.py](aifred/backends/vllm.py): Lines 221-239 (preload_model signature updated)
- [aifred/backends/tabbyapi.py](aifred/backends/tabbyapi.py): Lines 212-230 (preload_model signature updated)
- [aifred/lib/llm_client.py](aifred/lib/llm_client.py): Lines 183-198 (preload_model signature updated)
- [aifred/state.py](aifred/state.py): Lines 92, 556-603, 1017-1035, 1348-1372 (state management, preload with unload feedback, settings persistence)
- [aifred/lib/conversation_handler.py](aifred/lib/conversation_handler.py): Lines 419-437 (Automatik mode with unload feedback)
- [aifred/lib/config.py](aifred/lib/config.py): Lines 168-171 (VRAM constants)
- [aifred/aifred.py](aifred/aifred.py): Lines 1151-1188 (UI integration)

---

### ✂️ Token Optimization: Redundant Date Line Removed

#### Changed
- **Prompt Timestamp Format** ([aifred/lib/prompt_loader.py:137-147](aifred/lib/prompt_loader.py#L137-L147)):
  - Removed redundant `- Jahr: {now.year}` line from German timestamp
  - Removed redundant `- Year: {now.year}` line from English timestamp
  - Date already contains full year (`16.11.2025` or `2025-11-16`)
  - Separate year line was wasting tokens without adding information

#### Impact
- **Token Savings**: ~15 tokens saved per prompt (affects ALL prompts across all modes)
- **Information Loss**: None - full date already shows year
- **User Experience**: Cleaner prompt headers, more efficient token usage

#### Files Modified
- [aifred/lib/prompt_loader.py](aifred/lib/prompt_loader.py): Lines 137-147 (timestamp generation)

---

## [Unreleased] - 2025-11-15

### 🔍 Enhanced Debug Logging & Query Visibility

#### Added
- **Consistent Debug Logging Across All Modes** ([aifred/state.py:1014-1030](aifred/state.py#L1014-L1030), [aifred/lib/conversation_handler.py:395-414](aifred/lib/conversation_handler.py#L395-L414)):
  - "Eigenes Wissen" mode now shows comprehensive debug messages matching Automatik mode style
  - LLM preloading messages with precise timing: `🚀 Haupt-LLM wird vorgeladen...` → `✅ Haupt-LLM vorgeladen (X.Xs)`
  - System prompt creation confirmation
  - Token statistics: `📊 Haupt-LLM: input / num_ctx Tokens (max: limit)`
  - Temperature settings display
  - TTFT (Time To First Token) measurement
  - Final completion stats with tokens/s

- **Precise Preload Time Measurement** ([aifred/state.py:1019-1030](aifred/state.py#L1019-L1030)):
  - Ollama backend: Actual model loading time via `backend.preload_model()` (1-5 seconds)
  - vLLM/TabbyAPI: Preparation time only (models stay in VRAM, 0.1-0.5 seconds)
  - Backend-aware timing ensures accurate performance metrics

- **Optimized Query Display in Debug Console** ([aifred/lib/research/query_processor.py:61](aifred/lib/research/query_processor.py#L61)):
  - Shows the LLM-optimized search query after query optimization completes
  - Enables quality assessment of web research queries
  - Visible in all web research modes (Automatik, Websuche schnell, Websuche ausführlich)
  - Format: `🔎 Optimierte Query: [optimized search terms]`

#### Enhanced
- **Web Research Modes Debug Output** ([aifred/lib/research/query_processor.py:43-61](aifred/lib/research/query_processor.py#L43-L61)):
  - Query optimization progress: `🔍 Query-Optimierung läuft...`
  - Completion with timing: `✅ Query-Optimierung fertig (X.Xs)`
  - Optimized query display for quality assessment

#### Impact
- **Before**: Debug output varied significantly between modes, making performance comparison difficult
- **After**: All modes show consistent, detailed debug information for easier troubleshooting and optimization
- **User Benefit**: Better visibility into AIfred's internal processes, easier quality assessment of web searches

#### Files Modified
- [aifred/state.py](aifred/state.py): Lines 982-1030, 1036-1093 (Eigenes Wissen mode logging)
- [aifred/lib/conversation_handler.py](aifred/lib/conversation_handler.py): Lines 356-417 (Automatik mode logging)
- [aifred/lib/research/query_processor.py](aifred/lib/research/query_processor.py): Line 61 (optimized query display)

---

## [Unreleased] - 2025-11-14

### Fix: Research Mode Persistence

#### Fixed
- **Research Mode not persisted** ([aifred/state.py:1314](aifred/state.py#L1314)):
  - `set_research_mode_display()` changed the variable but didn't call `_save_settings()`
  - Settings infrastructure was complete (load + save to dict), only the trigger was missing
  - Inconsistent with other setters like `set_automatik_model()` which correctly save
  - Now calls `_save_settings()` after mode change to persist immediately

#### How it works
1. **Startup**: Loads `research_mode` from `settings.json` (Line 219) or falls back to `"automatik"` from `config.py`
2. **User changes mode**: UI calls `set_research_mode_display()` → `_save_settings()` → `settings.json` updated
3. **Next startup**: Saved mode is restored correctly

#### Impact
- **Before**: Research mode reset to default on every restart
- **After**: Research mode persists across sessions like all other settings

#### Files Modified
- [aifred/state.py](aifred/state.py): Line 1314 (added `_save_settings()` call)

---

### 🎯 Progress UI System Complete - MILESTONE

#### Added
- **Complete Progress Event Handling** ([aifred/state.py:942-960](aifred/state.py#L942-L960)):
  - Quick/Deep research modes now handle all progress events (`progress`, `history_update`, `thinking_warning`)
  - Identical event routing logic as Automatik mode
  - Shows Web-Scraping progress (1/3, 2/3, 3/3) and LLM generation phase
  - Visual feedback for all research pipeline stages

- **Pulsing Animation for All Modes** ([aifred/aifred.py:526,539,543](aifred/aifred.py#L526)):
  - Animation triggers on `progress_active | is_generating` (previously only `progress_active`)
  - "Generiere Antwort" now pulses in "none" mode (Eigenes Wissen) during LLM inference
  - Consistent visual feedback across all 4 research modes
  - Bold text weight during active phases

- **Dynamic Status Text** ([aifred/aifred.py:449-464](aifred/aifred.py#L449-L464)):
  - Status text shows "Generiere Antwort" when `is_generating=True` even if `progress_active=False`
  - Fixes idle state in "none" mode where status stayed on "Warte auf Eingabe"
  - Properly reflects system activity in all modes

#### Fixed
- **Progress Bar Visibility** ([assets/custom.css:90](assets/custom.css#L90)):
  - Removed `.rt-Box` from dark theme CSS selector
  - Orange progress bar fill (#e67700) was hidden by `!important` background override
  - Progress bar now visible in all research modes
  - Root cause: Commit d8e4d55 ("Force dark theme") introduced CSS specificity conflict

- **Missing Progress Events in Quick/Deep Modes**:
  - Quick/Deep modes had no progress event handling (only debug, content, result)
  - Web-Scraping and LLM phases were invisible to user
  - Now shows full pipeline: "Web-Scraping 1/7" → "Generiere Antwort"

#### Testing Results
- ✅ **Automatik Mode**: Progress bar + phases (Automatik → Scraping → LLM)
- ✅ **Quick Mode**: Progress bar + phases (Scraping 1/3 → LLM)
- ✅ **Deep Mode**: Progress bar + phases (Scraping 1/7 → LLM)
- ✅ **None Mode**: Pulsing "Generiere Antwort" during LLM

#### Technical Details
- Progress event flow: `scraper_orchestrator.py` → `orchestrator.py` → `state.py` → `aifred.py`
- Event types: `progress` (scraping, llm, compress), `debug`, `content`, `result`, `history_update`
- State variables: `progress_active`, `progress_phase`, `progress_current`, `progress_total`, `is_generating`
- Reflex reactive rendering: `rx.cond()` for conditional UI updates

#### Impact
- **Before**: Inconsistent progress feedback, Quick/Deep modes had no visual pipeline status
- **After**: Professional, consistent UI feedback across all modes. User always knows system status.
- **UX Improvement**: No more confusion about "is it working?" - clear visual feedback at every stage

#### Files Modified
- [assets/custom.css](assets/custom.css): Line 90 (removed `.rt-Box`)
- [aifred/state.py](aifred/state.py): Lines 942-960 (progress event handling)
- [aifred/aifred.py](aifred/aifred.py): Lines 449-464, 526, 539, 543 (status text, pulsing animation)
- [TODO.md](TODO.md): Comprehensive milestone documentation

---

### 🏷️ Source Label Consistency & Double Metadata Bug Fix

#### Fixed
- **Double Source Metadata Bug** ([aifred/lib/message_builder.py](aifred/lib/message_builder.py), [aifred/lib/conversation_handler.py](aifred/lib/conversation_handler.py)):
  - Fixed issue where responses showed duplicate source labels (e.g., `( Inferenz: 62.3s, Quelle: Web-Recherche ) ( Inferenz: 53.2s, Quelle: LLM-Trainingsdaten )`)
  - Root cause: HTML metadata (`<span>` tags) and thinking collapsibles (`<details>` tags) were NOT removed from chat history before passing to LLM
  - LLM sometimes copied old metadata into new responses, resulting in duplicate sources
  - Solution: Enhanced `build_messages_from_history()` to strip ALL HTML tags and metadata using regex patterns

#### Changed
- **Message History Cleaning** ([aifred/lib/message_builder.py:86-100](aifred/lib/message_builder.py#L86-L100)):
  - Added `import re` for regex-based HTML tag removal
  - Four-step cleaning process for AI messages:
    1. Remove thinking collapsibles: `<details>...</details>`
    2. Remove metadata spans: `<span style="...">( Inferenz: ... )</span>`
    3. Fallback: Remove text-based metadata patterns
    4. Cleanup: Remove multiple newlines and excess whitespace
  - Prevents LLM from seeing or copying old metadata from history

- **Source Label Consistency** ([aifred/lib/conversation_handler.py:480-486](aifred/lib/conversation_handler.py#L480-L486)):
  - Replaced ambiguous `"LLM-Trainingsdaten"` label with context-aware labels:
    - `"Cache+LLM (RAG)"` - RAG context from Vector Cache
    - `"LLM (mit History)"` - Chat history available as context (NEW)
    - `"LLM"` - Pure LLM without additional context (NEW)
  - Consistent with existing labels: `"Vector Cache"` (direct hit), `"Web-Recherche"` (agent research)

#### Impact
- **Before**: Confusing duplicate source labels, inconsistent terminology
- **After**: Clean, single source label per response with clear context indication
- **User Experience**: Users can now clearly see where each response comes from:
  - First message: `( Inferenz: 2.5s, Quelle: LLM )`
  - Follow-up with history: `( Inferenz: 3.2s, Quelle: LLM (mit History) )`
  - RAG context: `( Inferenz: 4.1s, Quelle: Cache+LLM (RAG) )`
  - Web research: `( Inferenz: 62.3s, 35.2 tok/s, Quelle: Web-Recherche )`

#### Files Modified
- [aifred/lib/message_builder.py](aifred/lib/message_builder.py): Lines 11 (import re), 84-100 (HTML cleaning)
- [aifred/lib/conversation_handler.py](aifred/lib/conversation_handler.py): Lines 480-486 (source labels)

---

### 🧹 Debug Console Separator Structure

#### Fixed
- **Separator Placement Logic** ([aifred/lib/research/context_builder.py](aifred/lib/research/context_builder.py), [aifred/state.py](aifred/state.py)):
  - Separators now appear AFTER each logical processing unit (not before)
  - Implemented "separator marks end of unit" principle across all code paths
  - Eliminated double separators after LLM completion
  - Three logical units with proper separation:
    1. LLM Response Generation → Separator
    2. Vector Cache Decision (web research only) → Separator
    3. History Compression Check → Separator

#### Changed
- **Web Research Path** ([aifred/lib/research/context_builder.py:204-207](aifred/lib/research/context_builder.py#L204-L207)):
  - Added separator after "✅ Haupt-LLM fertig" message
  - Added separator after Cache-Decision block (lines 329-332)
- **Normal Chat Path** ([aifred/state.py:866-869](aifred/state.py#L866-L869)):
  - Removed redundant separator (conversation_handler already emits one)
- **Compression Check** ([aifred/state.py:997-1016](aifred/state.py#L997-L1016)):
  - Separator now appears after compression completion message

#### Impact
- **Debug Console Output**: Clean, predictable structure with logical block boundaries
- **Before**: Inconsistent separator placement, double separators in some paths
- **After**: Each processing unit ends with exactly one separator line

#### Files Modified
- [aifred/lib/research/context_builder.py](aifred/lib/research/context_builder.py): Lines 204-207, 329-332
- [aifred/state.py](aifred/state.py): Lines 866-869 (commented), 997-1016

---

### 🔄 Auto-Reload Model List on Backend Restart

#### Added
- **Model List Auto-Refresh on Ollama Restart** ([aifred/state.py:1044-1092](aifred/state.py#L1044-L1092)):
  - After Ollama service restart via UI, automatically reload model list from `/api/tags`
  - Update both session state (`self.available_models`) and global state (`_global_backend_state`)
  - No need to restart AIfred just to see newly downloaded models
  - Shows immediate feedback: "🔄 Reloading model list..." and "✅ Model list updated: N models found"

#### Changed
- **`restart_backend()` Method Enhancement**:
  - Added automatic model list refresh after Ollama restart
  - Uses same curl-based API call as initial backend initialization
  - Preserves existing vLLM/TabbyAPI restart logic unchanged

#### Impact
- **User Experience**: Download new models → Restart Ollama → Models instantly available in dropdown
- **Before**: Had to restart entire AIfred service to refresh model list
- **After**: Just click "Restart Ollama" button in system control panel

#### Files Modified
- [aifred/state.py](aifred/state.py): Lines 1044-1092

---

### 🌍 Language Detection for All Prompts

#### Fixed
- **Language Not Passed to Prompt Loading Functions** (8 locations across 7 files):
  - Language was detected but not passed as `lang=` parameter to prompt functions
  - German user queries were receiving English prompts despite correct detection
  - Root cause: Missing `detected_user_language` parameter in function calls

#### Changed
- **Intent Detection** ([aifred/lib/intent_detector.py](aifred/lib/intent_detector.py)):
  - Line 62: Added `lang=detected_user_language` to `get_intent_detection_prompt()`
  - Lines 110-113: Added language detection for followup intent classification
- **Query Optimization** ([aifred/lib/query_optimizer.py:47](aifred/lib/query_optimizer.py#L47)):
  - Added `lang=detected_user_language` to `get_query_optimization_prompt()`
- **Decision Making** ([aifred/lib/conversation_handler.py:268](aifred/lib/conversation_handler.py#L268)):
  - Added `lang=detected_user_language` to `get_decision_making_prompt()`
- **Cache Hit Prompt** ([aifred/lib/research/cache_handler.py:77](aifred/lib/research/cache_handler.py#L77)):
  - Added `lang=detected_user_language` to `load_prompt('system_rag_cache_hit')`
- **System RAG Prompt** ([aifred/lib/research/context_builder.py:99](aifred/lib/research/context_builder.py#L99)):
  - Added `lang=detected_user_language` and `user_text` parameter
- **Cache Decision** ([aifred/lib/research/context_builder.py:241](aifred/lib/research/context_builder.py#L241)):
  - Added `lang=detected_user_language` to `load_prompt('cache_decision')`
- **RAG Relevance Check** ([aifred/lib/rag_context_builder.py:89](aifred/lib/rag_context_builder.py#L89)):
  - Added `lang=detected_user_language` to `load_prompt('rag_relevance_check')`
- **History Summarization** ([aifred/lib/context_manager.py:290](aifred/lib/context_manager.py#L290)):
  - Special case: Detects language from first user message in conversation history
  - Fallback to "de" if no messages available

#### Impact
- **User Experience**: German queries now receive German prompts, English queries receive English prompts
- **All Subsystems Affected**: Intent detection, query optimization, research mode, cache decisions, history compression
- **Consistent i18n**: All 8 prompt loading locations now respect detected language

#### Files Modified
- [aifred/lib/intent_detector.py](aifred/lib/intent_detector.py): Lines 62, 110-113
- [aifred/lib/query_optimizer.py](aifred/lib/query_optimizer.py): Line 47
- [aifred/lib/conversation_handler.py](aifred/lib/conversation_handler.py): Lines 268-270
- [aifred/lib/research/cache_handler.py](aifred/lib/research/cache_handler.py): Lines 76-89
- [aifred/lib/research/context_builder.py](aifred/lib/research/context_builder.py): Lines 98-110, 244-251
- [aifred/lib/rag_context_builder.py](aifred/lib/rag_context_builder.py): Lines 86-100
- [aifred/lib/context_manager.py](aifred/lib/context_manager.py): Lines 289-301

---

### 🧠 Thinking Mode Support for Ollama and vLLM Backends

#### Added
- **Ollama Thinking Mode Implementation** ([aifred/backends/ollama.py](aifred/backends/ollama.py)):
  - Added `"think": true` API parameter support in `chat()` and `chat_stream()` methods
  - Parse separate `thinking` and `content` fields from Ollama response
  - Wrap thinking output in `<think>...</think>` tags for unified formatting
  - Streaming support: Properly handle thinking chunks before content chunks
- **vLLM Thinking Mode Enhancement** ([aifred/backends/vllm.py](aifred/backends/vllm.py)):
  - Improved type safety: Replaced `# type: ignore` with proper `Dict[str, Any]` annotations
  - Use `chat_template_kwargs: {"enable_thinking": bool}` in `extra_body` for Qwen3 models
  - Consistent implementation across `chat()` and `chat_stream()` methods
- **Unified Thinking Process Formatting** ([aifred/lib/formatting.py](aifred/lib/formatting.py)):
  - Created `format_metadata()` function for metadata display (color: `#bbb`, font-size: `0.85em`)
  - Enhanced `format_thinking_process()` with model name and inference time in collapsible header
  - Added line break reduction regex (`r'\n\n+'`) to reduce excessive blank lines while preserving paragraphs
  - Fallback logic for malformed `<think>` tags (missing opening tag)
  - Updated `build_debug_accordion()` with same improvements for agent research mode
- **UI Styling** ([aifred/theme.py](aifred/theme.py)):
  - Added `.thinking-compact` CSS class for proper paragraph spacing (`0.75em` margins)
  - Text color matches collapsible header (`#aaa`)
  - Compact spacing for first/last child elements
- **User Message HTML Rendering** ([aifred/aifred.py](aifred/aifred.py#L725)):
  - Changed from `rx.text()` to `rx.markdown()` to properly render HTML metadata spans
- **Settings Update** ([aifred/lib/settings.py](aifred/lib/settings.py#L74)):
  - Default `enable_thinking` set to `True` for optimal user experience

#### Changed
- **Type Safety Improvements**:
  - Import `Any` from typing in vLLM backend
  - Declare `extra_body: Dict[str, Any] = {}` instead of untyped dict with `# type: ignore`
  - Removed all type ignore comments in vLLM backend
- **Metadata Color**: Adjusted from `#999` → `#aaa` → `#bbb` for better readability
- **Collapsible Styling**: Removed complex inline div styling in favor of CSS class approach

#### Fixed
- **HTML Rendering in User Messages**: Metadata now properly displays as styled HTML instead of raw tags
- **Type Safety**: MyPy passes without warnings for vLLM `extra_body` dictionary assignments
- **Line Break Handling**: Regex correctly reduces 2+ consecutive newlines to exactly 2 (one blank line)
- **Paragraph Spacing**: Thinking process collapsibles now have proper spacing (not too cramped, not too spaced)

#### Technical Details
- **Ollama API**: Uses `"think": true` payload parameter (not `enable_thinking` in options)
- **Ollama Response Structure**: Provides separate `thinking` and `content` fields in message dict
- **vLLM API**: Uses `extra_body["chat_template_kwargs"] = {"enable_thinking": bool}`
- **Unified Format**: Both backends output `<think>...</think>` wrapped content for consistent parsing
- **Automatik-LLM**: Thinking mode intentionally DISABLED for all automatik tasks (8x faster decisions)

#### Files Modified
- [aifred/backends/ollama.py](aifred/backends/ollama.py): Lines 93-95, 116-125, 199-236
- [aifred/backends/vllm.py](aifred/backends/vllm.py): Lines 9, 79, 88-90, 163, 172-174
- [aifred/lib/formatting.py](aifred/lib/formatting.py): Lines 13-37, 64-152, 155-235
- [aifred/theme.py](aifred/theme.py): Lines 125-142
- [aifred/lib/settings.py](aifred/lib/settings.py): Line 74
- [aifred/aifred.py](aifred/aifred.py): Line 725
- [aifred/lib/conversation_handler.py](aifred/lib/conversation_handler.py): Lines 467-478

---

### 📱 Mobile Dropdown Optimization

#### Problem Solved
- **Fixed**: Select dropdowns disappeared below viewport on mobile devices
- **Impact**: Users couldn't select models/backends when list was too long or positioned at bottom
- **Root Cause**: Default "item-aligned" positioning opens downward without viewport awareness
- **Solution**: Intelligent positioning + scrollable dropdowns with max-height

#### Implementation
- **Intelligent Positioning**: Added `position="popper"` to all select dropdowns
  - Backend select, Model select, Automatik-Model select
  - Adapts to available viewport space (opens upward if no space below)
- **Scrollable Dropdowns**: CSS max-height with internal scroll
  - Max height: 300px or available viewport height (whichever is smaller)
  - Internal scrollbar when list exceeds height
  - Dropdown stays open while scrolling (no accidental close)
- **Mobile-Friendly**: Touch scroll works correctly inside dropdown

#### Files Modified
- [aifred/aifred.py](aifred/aifred.py): Added `position="popper"` to 3 select components
- [aifred/theme.py](aifred/theme.py): CSS for `.rt-SelectContent` and `.rt-SelectViewport`

---

### 🛡️ GPU Compatibility Backend Filter

#### Problem Solved
- **Fixed**: Incompatible backends (vLLM, TabbyAPI) were selectable on Pascal GPUs (P40, GTX 10 series)
- **Impact**: vLLM would crash with Triton compiler errors or be extremely slow (FP16 1:64 ratio)
- **Root Cause**: Backend selection showed all backends regardless of GPU capabilities
- **Solution**: Automatic backend filtering based on GPU detection

#### Implementation
- **GPU Detection**: Existing `GPUDetector` now filters UI backend options
  - Detects GPU compute capability and FP16 performance
  - Tesla P40 (Compute 6.1) → Only shows "ollama" backend
  - RTX 3060+ (Compute 8.6) → Shows "ollama", "vllm", "tabbyapi"
- **Auto-Switch**: If saved backend is incompatible, auto-switch to first available backend
- **UI Updates**:
  - Backend select dropdown shows only compatible backends
  - GPU info badge shows detected GPU and compute capability
  - Removed redundant GPU warning box (no longer needed)
- **Backend Requirements**:
  - **Ollama**: Works on ALL GPUs (Compute 3.5+, INT8/Q4/Q8 quantization)
  - **vLLM**: Requires Compute 7.0+, fast FP16 performance (Volta or newer)
  - **TabbyAPI**: Same as vLLM (Compute 7.0+, fast FP16)

#### GPU Compatibility Matrix
| GPU | Compute Cap | Available Backends | Reason |
|-----|-------------|-------------------|--------|
| Tesla P40 | 6.1 | ollama only | FP16 ratio 1:64 (extremely slow) |
| Tesla P100 | 6.0 | ollama only | Compute < 7.0 (Triton unsupported) |
| GTX 1080 Ti | 6.1 | ollama only | Pascal architecture (slow FP16) |
| RTX 2080 | 7.5 | ollama, vllm, tabbyapi | Turing (fast FP16, Tensor Cores) |
| RTX 3060 | 8.6 | ollama, vllm, tabbyapi | Ampere (fast FP16, AWQ Marlin) |
| RTX 4090 | 8.9 | ollama, vllm, tabbyapi | Ada Lovelace (excellent) |

#### Files Modified
- [aifred/state.py](aifred/state.py#L146): Added `available_backends` state field
- [aifred/state.py](aifred/state.py#L240-L251): Backend filtering logic on session load
- [aifred/aifred.py](aifred/aifred.py#L994): Dynamic backend select with `AIState.available_backends`
- [aifred/aifred.py](aifred/aifred.py#L1013-L1028): GPU info badge
- [aifred/lib/gpu_detection.py](aifred/lib/gpu_detection.py): Existing GPU detection (no changes)

---

### 📐 vLLM Context Auto-Detection (40K-128K+ Support)

#### Problem Solved
- **Fixed**: vLLM context limit was only 16K tokens
- **Impact**: Responses were cut off mid-sentence, chat history was severely limited
- **Root Cause**: Hardcoded context limits didn't match actual model capabilities
- **Solution**: Automatic detection from model's config.json

#### Implementation
- **Auto-Detection**: `get_model_max_position_embeddings()` reads `max_position_embeddings` from HuggingFace cache
  - Searches `~/.cache/huggingface/hub/models--{vendor}--{model}/snapshots/*/config.json`
  - Returns native context limit (e.g., 40,960 for Qwen3-8B-AWQ, 131,072 for Qwen2.5-Instruct)
  - No more hardcoded values - works with any model!
- **Enhanced**: `vLLMProcessManager.start()` uses auto-detected context
  - `max_model_len=None` triggers auto-detection
  - Falls back to vLLM default if config not found
- **YaRN Support**: Optional RoPE scaling for extending context beyond training limits
  - Accepts YaRN config dict: `{"rope_type": "yarn", "factor": 2.0, "original_max_position_embeddings": 40960}`
  - Can extend context (e.g., 40K → 80K with factor=2.0)
  - Not used by default - native context is sufficient
- **Error Diagnostics**: Improved vLLM startup error logging (captures stderr)
- **Memory Fix**: Increase GPU memory utilization to 95% (40K context needs ~5.6 GiB KV cache)
- **Compatibility**: Use vLLM v0.11.0 defaults (v1 engine with multiprocessing)

#### Context Limits
- **Before**: 16K tokens (hardcoded, responses cut off!)
- **After**: Hardware-constrained maximum:
  - **RTX 3060 (12GB, Ampere 8.6)**: **26,608 tokens** @ 90% GPU memory ✅ Tested
  - Native model support: 40,960 tokens (requires ~5.6 GiB KV cache)
- **Note**: Context size limited by VRAM + GPU architecture, not model capability
- **VRAM Usage**: ~12 GB (97.7% utilization) at 26K context - GPU fully utilized but stable
- **Future**: Can use YaRN for extension when more VRAM available (e.g., RTX 3090, A100, H100)

#### Files Modified
- [aifred/lib/vllm_manager.py](aifred/lib/vllm_manager.py#L19-L64): Added `get_model_max_position_embeddings()`
- [aifred/lib/vllm_manager.py](aifred/lib/vllm_manager.py#L134-L158): Auto-detect in `start()` method
- [aifred/state.py](aifred/state.py#L569-L580): Removed hardcoded values, use auto-detection

---

### ⚡ Backend Pre-Initialization (Page Reload Performance)

#### Problem Solved
- **Fixed**: Backend re-initialization on every page reload (F5)
- **Impact**: Eliminated 30-120s wait time on page refresh
- **Behavior**: Backend now initializes ONCE at server start, persists across page reloads

#### Implementation
- **Added**: Module-level `_global_backend_state` dict for persistent backend state
- **Added**: `_global_backend_initialized` flag to prevent redundant initialization
- **Refactored**: `on_load()` method with two-phase initialization:
  - **Global Phase** (runs once at server start):
    - Debug log initialization
    - Language settings
    - Vector Cache connection
    - GPU detection
  - **Session Phase** (runs per user/tab/reload):
    - Load user settings
    - Generate session ID
    - Restore backend state from global cache
- **Optimized**: `initialize_backend()` with fast/slow paths:
  - **Fast Path**: Backend already initialized → Restore from global state (instant!)
  - **Slow Path**: First initialization or backend switch → Full model loading
- **Optimized**: vLLM Process Manager persistence:
  - `_vllm_manager` stored in global state
  - vLLM server survives page reloads
  - Prevents unnecessary vLLM restarts (saves 70-120s)

#### State Persistence
- **Preserved on page reload**:
  - Chat history
  - Debug console messages
  - Backend configuration
  - Loaded models
  - vLLM server process
  - GPU detection results

#### Restart Buttons
- **Enhanced**: `restart_backend()` method:
  - Ollama: Restarts systemd service
  - vLLM: Stops and restarts vLLM server process
  - TabbyAPI: Shows info message (manual restart)
- **Preserved**: "AIfred Neustarten" button behavior:
  - Clears chat history, debug console, caches
  - Does NOT restart backend or vLLM
  - Soft restart for development (hot-reload mode)
  - Hard restart via systemd for production

#### Code Quality
- **Passed**: ruff linter checks (no errors)
- **Fixed**: Unused variable `research_result` in generate loop
- **Added**: Type annotations for `_global_backend_state: dict[str, Any]`
- **Tested**: Backend switching, page reload, restart buttons

---

### 🔍 GPU Detection & Compatibility Checking

#### GPU Detection System
- **Added**: `aifred/lib/gpu_detection.py` - Automatic GPU capability detection
- **Features**:
  - Detects GPU compute capability via nvidia-smi
  - Identifies compatible/incompatible backends per GPU
  - Warns about known GPU limitations (Tesla P40 FP16 issues, etc.)
- **State Integration**:
  - GPU info stored in AIState (gpu_name, gpu_compute_cap, gpu_warnings)
  - Detection runs on startup via `on_load()`
  - Debug console shows GPU capabilities and warnings

#### UI Warnings
- **Added**: Visual warning in Settings when vLLM selected on incompatible GPU
- **Shows**:
  - GPU name and compute capability
  - Backend requirements (Compute Cap 7.5+ for vLLM/AWQ)
  - Recommendation to switch to Ollama for better performance
- **Styling**: Red warning box with icon, auto-shows when vLLM + Pascal GPU

#### Download Scripts Enhanced
- **Enhanced**: `download_vllm_models.sh` with GPU compatibility check
- **Features**:
  - Automatic GPU detection before download
  - Detailed warning for incompatible GPUs (P40, GTX 10 series)
  - Explains why vLLM/AWQ won't work (Triton, FP16 ratio, Compute Cap)
  - Offers exit with recommendation to use Ollama
  - User can override with explicit confirmation

#### Documentation
- **Added**: `docs/GPU_COMPATIBILITY.md` - Comprehensive GPU compatibility guide
- **Covers**:
  - GPU compatibility matrix (Pascal, Turing, Ampere, Ada, Hopper)
  - Backend comparison (Ollama GGUF vs vLLM AWQ vs TabbyAPI EXL2)
  - Technical explanation of Pascal limitations
  - Performance benchmarks (P40 vs RTX 4090)
  - Recommendations by use case
  - Troubleshooting guide

#### Backend Compatibility Summary
- **Ollama (GGUF)**: ✅ Works on all GPUs (Compute Cap 3.5+)
- **vLLM (AWQ)**: ⚠️ Requires Compute Cap 7.5+ (Turing+), fast FP16
- **TabbyAPI (EXL2)**: ⚠️ Requires Compute Cap 7.0+ (Volta+), fast FP16

#### Known GPU Issues Documented
- **Tesla P40**: FP16 ratio 1:64 → vLLM/ExLlama ~1-5 tok/s (unusable)
- **Tesla P100**: FP16 ratio 1:2 → vLLM possible but slower than Ollama
- **GTX 10 Series**: Compute Cap 6.1 → vLLM not supported
- **Recommendation**: Use Ollama (GGUF) on Pascal GPUs for best performance

### 🚀 Performance - 8x Faster Automatik, 7s Saved per Web Research

#### vLLM Preloading Optimization
- **Skip unnecessary preloading** for vLLM/TabbyAPI (models stay in VRAM)
- **Result**: 7s faster web research, UI shows "ℹ️ Haupt-LLM bereits geladen"
- **Files**: `aifred/backends/vllm.py`, `aifred/backends/tabbyapi.py`, `aifred/lib/research/scraper_orchestrator.py`

#### Thinking Mode Disabled for Automatik Tasks
- **Problem**: Qwen3 Thinking Mode slowed decisions from 1-2s to 7-13s
- **Solution**: `enable_thinking=False` for all automatik tasks (decisions, intent, RAG)
- **Result**: 8x faster total flow (3s instead of 24s)
  - Automatik decision: 8.7s → 2.1s (4x faster)
  - Intent detection: 13.0s → 0.3s (43x faster)
- **Files**: Fixed parameter passing in `llm_client.py`, vLLM `chat_template_kwargs` structure, 9 LLM call sites

### 🎯 Context Window Improvements

#### Real Tokenizer instead of Estimation
- **Problem**: Token estimation (3.5 chars/token) was 25% too low → context overflow
- **Solution**: HuggingFace AutoTokenizer with local cache
- **Fallback**: 2.5 chars/token (conservative) when tokenizer unavailable
- **Files**: `aifred/lib/context_manager.py` + 5 call sites

#### vLLM Context Auto-Detection (16K → 40K for Qwen3)
- **Problem**: vLLM hardcoded to 16K despite Qwen3-8B supporting 40K
- **Solution**: Remove `--max-model-len` → auto-detect from model config
- **Benefits**:
  - Qwen3-8B: 40K context (matches Ollama)
  - Qwen2.5-32B: 128K context automatically
  - No hardcoding, each model uses native limit
- **Files**: `vllm_startup.py`, `aifred/lib/vllm_manager.py`

### 🐛 Bug Fixes

- **Backend switching**: Fixed AttributeError and wrong model selection
- **Dead code**: Removed 83 lines (77 unreachable + 6 unused variables)
- **UI**: Debug console limit 100 → 500 messages

### 🔄 Portability

- ✅ No absolute paths
- ✅ No system-specific dependencies
- ✅ HuggingFace tokenizer: offline-capable (local cache)
- ✅ vLLM auto-detection: works on any system
- ✅ Systemd services: Template-based with sed substitution
- ✅ **Fully portable to MiniPC**

### 📦 Model Configuration

#### Restructured Download Scripts with YaRN Support
- **Added**: Separate download scripts for better organization
  - `download_ollama_models.sh` - Ollama (GGUF) models
  - `download_vllm_models.sh` - vLLM (AWQ) models with YaRN docs
  - `download_all_models.sh` - Master script for both backends
- **Archived**: Old scripts renamed to `.old` (preserved for reference)

#### Qwen3 AWQ Models (Primary Recommendation)
- **Added**: Qwen3 AWQ series with YaRN context extension support
  - Qwen3-4B-AWQ (~2.5GB, 40K native, YaRN→128K)
  - Qwen3-8B-AWQ (~5GB, 40K native, YaRN→128K)
  - Qwen3-14B-AWQ (~8GB, 32K native, YaRN→128K)
- **Features**:
  - Optional Thinking Mode (enable_thinking parameter)
  - Newest generation (2025)
  - Flexible context: Native 32-40K, YaRN extendable to 64K/128K

#### Qwen2.5 Instruct-AWQ Models (Alternative)
- **Available**: As alternative option with native 128K context
  - Qwen2.5-7B-Instruct-AWQ (~4GB, 128K native)
  - Qwen2.5-14B-Instruct-AWQ (~8GB, 128K native)
  - Qwen2.5-32B-Instruct-AWQ (~18GB, 128K native)
- **Benefits**: No YaRN needed, older generation but proven stable

#### YaRN Context Extension Support
- **Documentation**: Added comprehensive YaRN configuration examples
- **Flexible Factors**:
  - factor=2.0 → 64K context (recommended for chat history)
  - factor=4.0 → 128K context (for long documents)
- **Implementation**: Command-line and Python examples in download scripts
- **Trade-offs**: Documented perplexity loss vs context gain

## [1.0.0] - 2025-11-10

### 🎉 Milestone: Vector Cache Production Ready

#### Added
- **ChromaDB Vector Cache**: Thread-safe semantic caching for web research results
  - Docker-based ChromaDB server mode (port 8000)
  - Automatic duplicate detection with configurable distance thresholds
  - Time-based cache invalidation (5-minute threshold for explicit research keywords)
  - Query-only embeddings for improved similarity matching (distance 0.000 for exact matches)
  - Auto-learning from web research results
- **Configurable Distance Thresholds** (`aifred/lib/config.py`):
  - `CACHE_DISTANCE_HIGH = 0.5` - High confidence cache hits
  - `CACHE_DISTANCE_MEDIUM = 0.85` - Medium confidence cache hits
  - `CACHE_DISTANCE_DUPLICATE = 0.3` - Duplicate detection for explicit keywords
  - `CACHE_TIME_THRESHOLD = 300` - 5 minutes for time-based invalidation
- **Enhanced Cache Logging**: Distance and confidence displayed for all cache operations (hits, misses, duplicates)
- **Docker Compose Consolidation**: Unified `docker/docker-compose.yml` with ChromaDB + optional SearXNG
- **Docker Documentation**: New `docker/README.md` with service management instructions

#### Changed
- **Vector Cache Architecture**: Migrated from PersistentClient to HttpClient (Docker server mode)
  - Fixes: File lock issues and deadlocks in async operations
  - Improvement: Thread-safe by design, no worker threads needed
- **Cache Query Strategy**: Implemented `query_newest()` method
  - Returns most recent match instead of best similarity match
  - Prevents outdated cache entries from being returned
- **Context Window Management**: Generous reserve strategy (8K-16K tokens) to prevent answer truncation
- **Project Structure**:
  - Moved `docker-compose.yml` from root to `docker/` directory
  - Consolidated separate ChromaDB and SearXNG compose files
- **Duplicate Detection**: Time-aware duplicate prevention
  - Skip save if similar entry exists and is < 5 minutes old
  - Allow new entry if existing entry is > 5 minutes old (allows updates)

#### Removed
- **Obsolete Implementations**: Deleted `archive/vector_cache_old/` directory
  - Old PersistentClient implementation (vector_cache.py)
  - Old worker thread implementation (vector_cache_v2.py)
  - Still available in git history if needed

#### Fixed
- **KeyError 'data'**: Fixed cache hit result format for explicit research keywords
- **Missing user_with_time**: Added timestamp generation for history entries
- **Cache Miss on Recent Entries**: Fixed `query_newest()` to find most recent duplicate
- **Duplicate Log Messages**: Proper distinction between saved entries and skipped duplicates
- **Distance Logging**: Distance now displayed for all cache operations (hits and misses)

#### Technical Details
- **ChromaDB Version**: Using latest ChromaDB Docker image
- **API Version**: ChromaDB v2 API (v1 deprecated)
- **Collection Management**:
  - Collection name: `research_cache`
  - Persistent storage: `./aifred_vector_cache/` (Docker volume)
  - Health checks: Automatic with 30s interval
- **Cache Statistics**: Available via `get_cache().get_stats()`

#### Migration Notes
- **Docker Commands Updated**: All docker-compose commands now require `-f docker/docker-compose.yml` or working from `docker/` directory
- **ChromaDB Reset**: Two methods documented in README
  - Option 1: Full restart (stop container, delete data, restart)
  - Option 2: API-based collection deletion (faster, no container restart)
- **Configuration**: All cache thresholds centralized in `aifred/lib/config.py`

---

## [1.1.0] - 2025-11-10

### 🧠 Intelligent Cache Decision System

#### Added
- **LLM-Based Cache Decision**: Automatic cache filtering with AI-powered override capability
  - Two-stage filter: Volatile keywords → LLM decision
  - Override logic: Concept questions (e.g., "Was ist Wetter?") are cached despite volatile keywords
  - Automatik-LLM makes decision (fast, deterministic with temperature=0.1)
- **Volatile Keywords List** (`aifred/lib/config.py`):
  - `CACHE_EXCLUDE_VOLATILE` - 40+ keywords for volatile data detection
  - Weather, finance, live sports, breaking news, time-specific queries
  - Triggers LLM decision for smart caching
- **Cache Decision Prompt** (`prompts/de/cache_decision.txt`):
  - Clear rules: Cache facts/concepts, don't cache live data
  - Examples for both cacheable and non-cacheable queries
  - Override examples for ambiguous cases
- **Source Attribution**: Transparent source labeling in chat history
  - "Quelle: LLM-Trainingsdaten" - Answer from model's training data
  - "Quelle: Vector Cache" - Answer from semantic cache
  - "Quelle: Session Cache" - Answer from session-based cache
  - "Quelle: Web-Recherche" - Answer from fresh web research
- **Cache Inspection Scripts**:
  - `scripts/list_cache.py` - List all cached entries with timestamps
  - `scripts/search_cache.py` - Semantic similarity search in cache

#### Changed
- **Cache Distance Thresholds**: Stricter matching for better quality
  - `CACHE_DISTANCE_MEDIUM` lowered from 0.85 to 0.5
  - Preparation for RAG mode (0.5-1.2 range)
- **Cache Auto-Learning Logic** (`context_builder.py`):
  - Intelligent filtering before saving to cache
  - LLM evaluates if content is timeless or volatile
  - Debug messages for cache decision transparency
- **Volatile Keywords**: Moved to external file for easier maintenance
  - Now loaded from `prompts/cache_volatile_keywords.txt`
  - Multilingual file (German + English keywords)
  - Easy to edit without code changes
  - 68 keywords covering weather, finance, sports, news, time references

#### Fixed
- **UnboundLocalError**: Fixed duplicate `load_prompt` import causing variable shadowing
  - Removed local imports at lines 231 and 261 in `context_builder.py`
  - Now uses module-level import correctly
- **Deadlock in Cache Decision**: Fixed LLM client resource conflict
  - Was creating new LLMClient instances for cache decision
  - Now uses existing `automatik_llm_client` parameter
  - Prevents deadlock when Haupt-LLM just finished generating
  - Removed unnecessary `from ..llm_client import LLMClient` import

#### Technical Details
- **Cache Decision Flow**:
  1. Check user query for volatile keywords
  2. If keyword found → Ask LLM (can override to "cacheable")
  3. If no keyword → Ask LLM (default decision)
  4. Save to cache only if LLM approves
- **Source Display Format**:
  - Appears at end of AI answer (not user question)
  - Format: `(Inferenz: 2.5s, Quelle: <source>)`
  - Consistent across all answer types

---

## [1.3.0] - 2025-11-11

### 🚀 Pure Semantic Deduplication + Smart Cache for Explicit Research

#### Added
- **Smart Cache-Check for Explicit Research Keywords** (`conversation_handler.py`):
  - Cache check BEFORE web research for keywords like "recherchiere", "google", "suche im internet"
  - Distance < 0.05 (practically identical) → Use cache (0.15s instead of 100s)
  - Distance ≥ 0.05 → Perform fresh research
  - Transparent display: Shows cache age (e.g., "Cache-Hit (681s old, d=0.0000)")
  - User can still force fresh research via UI mode selection (Web-Suche schnell/tief)
- **ChromaDB Maintenance Tool** (`chroma_maintenance.py`):
  - Display cache statistics (entries, age, size)
  - Find duplicates (text similarity-based)
  - Remove duplicates (keeps newest entry)
  - Delete old entries (by age threshold)
  - Clear entire database
  - Dry-run mode for safe testing

#### Changed
- **Pure Semantic Deduplication** (No Time Dependencies):
  - Removed: `CACHE_TIME_THRESHOLD` (5-minute logic)
  - New: Always update semantic duplicates (distance < 0.3) regardless of age
  - Benefit: Consistent behavior, no race conditions, latest data guaranteed
  - Affected files: `vector_cache.py`, `config.py`, `conversation_handler.py`
- **Automatik-LLM Default Model**:
  - Changed from `qwen3:8b` to `qwen2.5:3b`
  - Performance: 2.7x faster decisions (0.3s instead of 0.8s)
  - VRAM: ~63% reduction (~3GB instead of ~8GB)
  - Main LLM remains `qwen3:8b` for final answers

#### Fixed
- **LLMResponse AttributeError** (`context_builder.py`):
  - Fixed: `response.get('message', {}).get('content', '')` → `response.text`
  - Issue: LLMResponse is dataclass with `.text` attribute, not a dict
  - Affected: Cache decision logic (2 locations)
- **10x Python Duplicates**:
  - Root cause: Time-based logic allowed duplicates after 5 minutes
  - Fix: Pure semantic deduplication always updates duplicates
  - Result: No more duplicate cache entries

#### Performance
- **Identical Research Query**: ~667x faster (0.15s instead of 100s) ✅
- **Automatik Decision**: 2.7x faster (0.3s instead of 0.8s) ✅
- **VRAM Savings**: ~63% less for Automatik-LLM ✅

#### Breaking Changes
None - Fully backwards compatible

---

## [Unreleased]

### Planned Features
- RAG mode improvements: Better relevance detection
- Cache statistics dashboard in UI
- Export/import cache entries
- Multi-language support for cache queries
- Background cache cleanup scheduler

---

**Note**: This is the first formal release with changelog tracking. Previous development history is available in git commit history.
