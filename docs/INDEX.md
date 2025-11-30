# AIfred Intelligence - Dokumentations-Index

**Letzte Aktualisierung:** 2025-11-30

---

## 📚 Dokumentationsstruktur

```
docs/
├── INDEX.md (diese Datei)
├── api/                       # API-Konfiguration
├── architecture/              # System-Architektur
├── development/               # Entwicklungs-Guides & Archive
├── hardware/                  # Hardware-Erkennung
├── infrastructure/            # Infrastruktur (Ollama, ROCm)
├── llm/                       # LLM-Konfiguration & Vergleiche
├── vllm/                      # vLLM-spezifische Dokumentation
│   ├── VLLM_RTX3060_CONFIG.md     # RTX 3060 Optimierung
│   ├── VLLM_FIX_SUMMARY.md        # Crash-Fix Zusammenfassung
│   └── VLLM_CHANGES_ANALYSIS.md   # Commit-History-Analyse
├── GPU_COMPATIBILITY.md       # GPU Kompatibilitäts-Matrix
└── TODO.md                    # Projekt-Aufgabenliste
```

---

## 🚀 Schnellstart

### Ollama GPU-Beschleunigung (AMD Radeon 780M)

✅ **Status:** Erfolgreich implementiert (18.10.2025)

**Kurzanleitung:**
1. BIOS: iGPU VRAM auf 8 GB setzen
2. Ollama Service Override konfigurieren:
   ```bash
   # /etc/systemd/system/ollama.service.d/override.conf
   [Service]
   Environment="HSA_OVERRIDE_GFX_VERSION=11.0.2"
   ```
3. Performance: **4-6x schneller** als CPU-Mode!

📖 **Details:** [infrastructure/OLLAMA_ROCM_GPU_STATUS.md](infrastructure/OLLAMA_ROCM_GPU_STATUS.md)

---

## 📁 Dokumentation nach Kategorie

### 🏗️ Infrastruktur & System

| Dokument | Beschreibung | Status |
|----------|--------------|--------|
| [GPU_COMPATIBILITY.md](GPU_COMPATIBILITY.md) | GPU Kompatibilitäts-Matrix (Ollama/vLLM/TabbyAPI) | ✅ Aktiv |
| [vllm/VLLM_RTX3060_CONFIG.md](vllm/VLLM_RTX3060_CONFIG.md) | RTX 3060 Optimierung (26K context @ 90% GPU) | ✅ Aktiv |
| [vllm/VLLM_FIX_SUMMARY.md](vllm/VLLM_FIX_SUMMARY.md) | vLLM Crash-Fix Zusammenfassung | ✅ Referenz |
| [infrastructure/OLLAMA_ROCM_GPU_STATUS.md](infrastructure/OLLAMA_ROCM_GPU_STATUS.md) | Ollama GPU-Beschleunigung mit AMD Radeon 780M | ✅ Aktiv |
| [infrastructure/OLLAMA_0.12.6_ROCM_RADEON780M_RESEARCH.md](infrastructure/OLLAMA_0.12.6_ROCM_RADEON780M_RESEARCH.md) | Web-Recherche: Community-Lösungen für gfx1103 | ✅ Referenz |
| [hardware/HARDWARE_DETECTION.md](hardware/HARDWARE_DETECTION.md) | Automatische Hardware-Erkennung (CPU/GPU/RAM) | ✅ Aktiv |

### 🤖 LLM-Konfiguration & Modelle

| Dokument | Beschreibung | Status |
|----------|--------------|--------|
| [llm/OLLAMA_VRAM_OPTIMIZATION.md](llm/OLLAMA_VRAM_OPTIMIZATION.md) | Ollama VRAM-Optimierung für 48GB Setup (55% schneller) | ✅ Aktiv |
| [llm/LLM_PARAMETERS.md](llm/LLM_PARAMETERS.md) | Parameter-Tuning (temperature, top_p, etc.) | ✅ Aktiv |
| [llm/MEMORY_MANAGEMENT.md](llm/MEMORY_MANAGEMENT.md) | Memory-Management für Ollama | ✅ Aktiv |
| [llm/LLM_COMPARISON.md](llm/LLM_COMPARISON.md) | Vergleich verschiedener LLMs | ✅ Referenz |
| [llm/MODEL_COMPARISON_DETAILED.md](llm/MODEL_COMPARISON_DETAILED.md) | Detaillierter Model-Vergleich | ✅ Referenz |

###🏛️ Architektur & Features

| Dokument | Beschreibung | Status |
|----------|--------------|--------|
| [architecture/CACHE_SYSTEM.md](architecture/CACHE_SYSTEM.md) | Intelligentes Cache-System mit Metadata | ✅ Aktiv |
| [architecture/architecture-agentic-features.md](architecture/architecture-agentic-features.md) | Agent-Features & Web-Recherche | ✅ Aktiv |
| [architecture/LLM_HELP_UI.md](architecture/LLM_HELP_UI.md) | UI-Hilfe & Tooltips | ✅ Aktiv |

### 💻 Entwicklung

| Dokument | Beschreibung | Status |
|----------|--------------|--------|
| [development/PRE_COMMIT_CHECKLIST.md](development/PRE_COMMIT_CHECKLIST.md) | Pre-Commit Workflow (ruff, mypy, pytest) | ✅ Aktiv |
| [development/REFACTORING_REPORT.md](development/REFACTORING_REPORT.md) | Code-Refactoring Report | ✅ Referenz |
| [development/debug-output-reference.md](development/debug-output-reference.md) | Debug-Output Referenz | ✅ Aktiv |

### 🔌 API & Integration

| Dokument | Beschreibung | Status |
|----------|--------------|--------|
| [api/API_SETUP.md](api/API_SETUP.md) | API-Keys Setup (SearXNG, Brave, etc.) | ✅ Aktiv |

---

## 📊 Performance-Übersicht

### CPU vs. GPU-Mode (Radeon 780M)

| Metrik | CPU-Mode | GPU-Mode | Speedup |
|--------|----------|----------|---------|
| **Prompt Eval** | 28 tokens/s | **171.72 tokens/s** | **6.1x** ⚡ |
| **Generation** | 12 tokens/s | **47.63 tokens/s** | **4.0x** ⚡ |
| **Agent-Test (142s)** | 142s | **~50-70s** (geschätzt) | **2-3x** ⚡ |

---

## 🛠️ System-Konfiguration

### Hardware
- **CPU:** AMD Ryzen 9 7940HS
- **GPU:** AMD Radeon 780M (gfx1103, RDNA 3 iGPU)
- **RAM:** 32 GB
- **VRAM:** 8 GB (BIOS-Allocation)

### Software
- **OS:** Ubuntu 22.04 LTS
- **Ollama:** 0.12.6 (official)
- **ROCm:** 6.2.4
- **Python:** 3.10+
- **HSA_OVERRIDE:** 11.0.2 (gfx1103 → gfx1102 emulation)

---

## 🔗 Wichtige Links

- **GitHub Repository:** https://github.com/Peuqui/AIfred-Intelligence
- **Ollama Docs:** https://docs.ollama.com
- **ROCm Docs:** https://rocm.docs.amd.com
- **Community Build (gfx1103):** https://github.com/likelovewant/ollama-for-amd

---

## 📝 Changelog

### 2025-11-30
- ✅ Ollama VRAM-Optimierung für 48GB Setup (2x Tesla P40)
- ✅ Manuelle Unload/Reload-Zyklen entfernt (Ollama LRU aktiv)
- ✅ VRAM-Stabilisierung entfernt (3s Overhead gespart)
- ✅ Performance: Eigenes Wissen 55% schneller (3.9s vs 8.7s)
- ✅ [OLLAMA_VRAM_OPTIMIZATION.md](llm/OLLAMA_VRAM_OPTIMIZATION.md) erstellt

### 2025-11-01
- ✅ Intelligentes Cache-System implementiert (Metadata-basiert, ~60% Token-Einsparung)
- ✅ Synchrone Metadata-Generierung (100 Wörter, nach Haupt-LLM)
- ✅ Smart Context-Building: Alte Metadata + aktuelle volle Quellen
- ✅ Logging konsolidiert: Zentrale console_separator() Funktion
- ✅ System-Prompt optimiert: URLs-im-Text Problem behoben
- ✅ Dokumentation reorganisiert: Alle Docs in docs/ Unterordner
- ✅ [CACHE_SYSTEM.md](architecture/CACHE_SYSTEM.md) erstellt

### 2025-10-18
- ✅ GPU-Beschleunigung erfolgreich implementiert (HSA_OVERRIDE=11.0.2)
- ✅ Dokumentation reorganisiert (Unterordner-Struktur)
- ✅ Web-Recherche zu gfx1103-Support dokumentiert
- ✅ Custom-Builds bereinigt (~10 GB frei)
- ✅ Temperature-Parameter optimiert (0.2-0.3 für Agent-Funktionen)

### 2025-10-17
- Code-Refactoring Phase 1 (Threading-Locks, Agent CPU-Mode)
- Hardware-Detection-Dokumentation aktualisiert

### 2025-10-15
- LLM-Vergleich & Model-Comparison erstellt
- Memory-Management dokumentiert

---

**Autor:** AIfred Intelligence Team
**Maintainer:** AI Assistant + mp
**Lizenz:** Siehe Repository
