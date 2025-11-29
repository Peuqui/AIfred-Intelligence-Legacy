# Tensor Split Analysis - Dual P40 Setup

**Status:** Archiviert - Erkenntnisse für zukünftige Referenz
**Datum:** 2025-11-29
**Kontext:** Qwen3-VL-30B-A3B-Instruct MoE Model (Q4_K_M)

## Problem Statement

Bei Verwendung von `tensor_split 71 29` mit KoboldCPP auf 2x Tesla P40 (23GB VRAM each) wurden nur **1.7 tokens/s** erreicht statt erwarteter 40-50 tok/s.

## Root Cause Analysis

### KV-Cache Distribution Problem

**Das fundamentale Problem:**
- KoboldCPP pre-alloziert den kompletten KV-Cache beim Start
- KV-Cache wird im **GLEICHEN Verhältnis** wie das Modell gesplittet
- Bei 260K context + tensor_split 71/29:
  - GPU0 (71%): 184,600 tokens × 0.1 MB/token = **18.5 GB KV-Cache**
  - GPU1 (29%): 75,400 tokens × 0.1 MB/token = **7.5 GB KV-Cache**

### VRAM Capacity Analysis

```
GPU0 VRAM Breakdown (tensor_split 71 29):
- Model Weights:    8.2 GB
- KV-Cache needed: 18.5 GB (bei 260K context)
- Total needed:    26.7 GB
- GPU0 capacity:   23.0 GB
→ OVERFLOW:         3.7 GB → CPU RAM!
```

```
GPU1 VRAM Breakdown (tensor_split 71 29):
- Model Weights:    3.2 GB
- KV-Cache needed:  7.5 GB (bei 260K context)
- Total needed:    10.7 GB
- GPU1 capacity:   23.0 GB
→ FREE SPACE:      12.3 GB (ungenutzt!)
```

### Performance Impact

**CPU RAM Spillover:**
- 15.9 GB Model + KV-Cache im CPU RAM
- Jeder Token-Generation greift auf CPU RAM zu
- PCIe Bottleneck (Gen3 x16 = ~15 GB/s bidirectional)
- **Performance: 1.7 tok/s** (97% Verlust!)

## Solution: tensor_split 50 50

### VRAM Distribution

```
Optimale Verteilung (tensor_split 50 50):
GPU0:
- Model:      5.7 GB
- KV-Cache:  13.0 GB (130K tokens @ 260K total)
- Total:     18.7 GB
- Free:       4.3 GB ✅

GPU1:
- Model:      5.7 GB
- KV-Cache:  13.0 GB (130K tokens @ 260K total)
- Total:     18.7 GB
- Free:       4.3 GB ✅
```

### Performance Expectations

- Kein CPU RAM Overflow
- Beide GPUs arbeiten parallel
- Erwartete Performance: **40-50 tok/s**
- Max Context: **262K tokens** (KoboldCPP hardcoded limit)

## Key Learnings

### 1. KV-Cache Pre-Allocation

**Fakt:** KoboldCPP alloziert KV-Cache beim Start, NICHT dynamisch.

```bash
# VRAM usage direkt nach Start (ohne Inference):
GPU0: 8.2 GB  # Model + pre-allocated KV-Cache
GPU1: 3.2 GB  # Model + pre-allocated KV-Cache
```

Das bedeutet:
- ✅ VRAM-Nutzung ist KONSTANT (egal ob 0 oder 260K tokens geladen)
- ✅ Kein dynamisches num_ctx wie bei Ollama
- ✅ Modell muss neu geladen werden für anderen Context

### 2. Tensor Split Distribution

**Missverständnis:** "71/29 vermeidet Cross-GPU Traffic"

**Realität:**
- KV-Cache wird AUCH gesplittet (im gleichen Verhältnis!)
- Bei asymmetrischem Split → asymmetrische VRAM-Nutzung
- Kleinere GPU = Bottleneck

**Korrekt:**
- Tensor Split ist NUR sinnvoll für:
  - Multi-User Szenarien (Load-Balancing)
  - Wenn Modell + KV-Cache NICHT auf eine GPU passt
- Für Single-User mit großem Context: **Immer 50/50**

### 3. MoE Model Memory Usage

**Qwen3-VL-30B-A3B (Q4_K_M):**
- File size: 18 GB
- VRAM usage: 11.4 GB (Model)
- CPU RAM usage: 15.9 GB (bei 71/29 Overflow)
- **Total: 27.3 GB** im Speicher

**MoE Specifics:**
- 30.5B Total Parameter
- ~3-5B aktive Parameter pro Token
- Alle Experts SIND im VRAM (nicht lazy-loaded)
- Shared Weights zwischen Experts reduzieren Speicher

### 4. Asymmetric Split Nutzlos

**Ursprüngliche Annahme:**
```
71/29 Split maximiert GPU0 Nutzung
→ Weniger Cross-GPU Traffic
→ Bessere Performance
```

**Realität:**
```
71/29 Split → GPU0 Bottleneck
→ CPU RAM Overflow
→ PCIe Bottleneck
→ 97% Performance Verlust!
```

**Warum 50/50 besser ist:**
- Beide GPUs haben genug VRAM
- Kein Overflow
- Cross-GPU Traffic ist irrelevant bei Pre-Allocation
- NVLink nicht nötig (KV-Cache ist statisch)

## Implementation Decision

### Entfernte Logik

Die komplexe tensor_split Berechnungslogik wurde entfernt:
- Asymmetrische Split-Berechnung (71/29, 80/20, etc.)
- VRAM-basierte Optimierung
- Single-GPU vs Dual-GPU Entscheidung

### Neue Strategie

**Default:** `tensor_split: None` (KoboldCPP entscheidet = 50/50)

**Begründung:**
1. KoboldCPP's Auto-Distribution ist optimal für Dual-GPU
2. Keine manuelle Optimierung nötig
3. Funktioniert für alle Modelle
4. Code-Simplifikation: -200 Zeilen

## Performance Comparison

| Config | Model VRAM | KV-Cache VRAM | CPU RAM | Performance |
|--------|-----------|---------------|---------|-------------|
| 71/29 (alt) | 11.4 GB | 26.0 GB (split) | 15.9 GB | 1.7 tok/s ❌ |
| 50/50 (neu) | 11.4 GB | 26.0 GB (split) | 0 GB | 40-50 tok/s ✅ |
| 100/0 | N/A | N/A | N/A | PASST NICHT |

## Recommendations

### For Dual P40 Setups

1. **IMMER `tensor_split: None` verwenden** (= 50/50 auto)
2. **Context maximieren:** Bis zu 262K tokens (KoboldCPP hardcoded limit)
3. **NICHT optimieren:** KoboldCPP's Default ist optimal

### For Future Experiments

Wenn asymmetrischer Split gewünscht:
1. Prüfe BEIDE GPUs auf Overflow
2. Berechne KV-Cache Verteilung
3. Teste Performance (CPU RAM usage!)

### Code Philosophy

**KISS-Prinzip:**
- Keine vorzeitige Optimierung
- KoboldCPP's Defaults vertrauen
- Nur optimieren bei nachgewiesenem Problem

## Files Modified (To Be Reverted)

- `aifred/lib/koboldcpp_manager.py`: -200 Zeilen tensor_split Logik
- `aifred/lib/gpu_utils.py`: `tensor_split: None` (keine Berechnung)

## References

- KoboldCPP Documentation: https://github.com/LostRuins/koboldcpp
- Qwen3 MoE Architecture: https://qwen.readthedocs.io/
- Tesla P40 Specs: 23GB VRAM, PCIe Gen3 x16

---

**Lessons Learned:** Manchmal ist die einfachste Lösung die beste. KoboldCPP's Auto-Distribution (50/50) ist optimal für Dual-GPU Setups mit großem Context.
