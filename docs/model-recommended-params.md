# Empfohlene Parameter pro Modell (llama-server)

Stand: 2026-02-21 — Recherche via Aragon

## GPT-OSS-120B

| Parameter | Wert | Wichtig |
|-----------|------|---------|
| --jinja | ja, Pflicht | Harmony-Template |
| --reasoning-format | none | NICHT deepseek! |
| --chat-template-kwargs | '{"reasoning_effort": "medium"}' | low/medium/high moeglich |
| --temp | 1.0 | |
| --top-p | 1.0 | |
| --top-k | 0 (offiziell) oder 100 (Speed-Trick) | |
| --min-p | 0.0 | |
| --repeat-penalty | NICHT setzen! | Explizit verboten |
| -ctk / -ctv | NICHT setzen! | KV-Quant killt Performance (84% langsamer PP, 58% langsamer TG) |
| -fa | on | |
| -b / -ub | 2048 / 2048 | |

## GLM-4.7-REAP-218B

| Parameter | Wert | Wichtig |
|-----------|------|---------|
| --jinja | ja, Pflicht | |
| --reasoning-format | deepseek | |
| --chat-template-kwargs | '{"enable_thinking": false}' | Zum Abschalten |
| --temp | 0.7 (Coding) / 1.0 (allgemein) | |
| --top-p | 1.0 (Coding) / 0.95 (allgemein) | |
| --min-p | 0.01 | llama.cpp Default 0.1 ist zu hoch |
| --repeat-penalty | 1.0 (= disabled, KRITISCH!) | Jeder andere Wert zerstoert Output |
| -ctk / -ctv | q8_0 / q8_0 | OK, spart VRAM |
| -fa | on | |
| -b / -ub | 2048 / 512 | |

## MiniMax-M2.5

| Parameter | Wert | Wichtig |
|-----------|------|---------|
| --jinja | ja, Pflicht | Sonst Endlos-Loops |
| --reasoning-format | none | NICHT deepseek! MiniMax-Format ist anders |
| --temp | 1.0 | |
| --top-p | 0.95 | |
| --top-k | 40 | |
| --min-p | 0.01 | |
| --repeat-penalty | 1.0 | |
| -ctk / -ctv | q4_0 / q4_0 | OK bei Q2_K_XL Modell |
| -fa | on | |
| -b / -ub | 4096 / 4096 | MoE profitiert von grossen Batches |

## Qwen3 — Instruct-Varianten (4B, 14B, 30B-A3B, 235B-A22B)

| Parameter | Wert | Wichtig |
|-----------|------|---------|
| --jinja | ja | |
| --reasoning-format | nicht noetig | Instruct = kein Thinking |
| --temp | 0.7 | |
| --top-p | 0.8 | |
| --top-k | 20 | |
| --min-p | 0 | |
| --presence-penalty | 1.5 (bei Wiederholungen) | |
| -ctk / -ctv | q8_0 / q8_0 | OK |
| -fa | on | |
| --no-context-shift | ja | Pflicht bei KV-Quant |

## Qwen3-Next-80B (Thinking + Instruct)

| Parameter | Wert | Wichtig |
|-----------|------|---------|
| --jinja | ja | |
| --reasoning-format | deepseek (Thinking) / nicht noetig (Instruct) | |
| --temp | 0.6 (Thinking) / 0.7 (Instruct) | |
| --top-p | 0.95 (Thinking) / 0.8 (Instruct) | |
| --top-k | 20 | |
| -ub | max 512! | Hoeher = Crash |
| -ctk / -ctv | q4_1 / q4_1 | |
| KV-Cache-Reuse | kaputt | Hybrid-Architektur |

## Wichtigste Erkenntnisse

- **GPT-OSS**: Kein KV-Cache-Quant! (-ctk/-ctv killt Performance massiv)
- **GPT-OSS**: --reasoning-format none, nicht deepseek (Harmony-Format ist inkompatibel)
- **GLM-REAP**: --repeat-penalty muss 1.0 sein (alles andere = Endlos-Wiederholungen)
- **MiniMax**: --reasoning-format none (kein deepseek)
- **Qwen3-Next**: -ub max 512 (hoeher crasht wegen Hybrid-Architektur)
- **--jinja ist bei ALLEN Modellen Pflicht**
- **--no-context-shift** ist Pflicht bei Qwen3 + KV-Quant
