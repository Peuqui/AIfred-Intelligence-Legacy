# Dual-GPU Inter-KI Debate System - Implementation Plan

**Projekt**: AIfred Intelligence - Multi-Agent Debate Feature
**Hardware**: 2x Tesla P40 (24GB VRAM each)
**Ziel**: Visualisierte Inter-KI Diskussionen mit Reasoning-Synthesis

---

## Executive Summary

**Feature**: Zwei KI-Agents debattieren ambiguous questions, während User den Dialog in Echtzeit verfolgt. Finale Synthesis via Reasoning Model zeigt expliziten Denkprozess.

**Architektur**: Hybrid-Ansatz
- **Round 1-2**: Instruct Models (schnelle Argumentation)
- **Synthesis**: Reasoning Model (tiefe Analyse mit sichtbarem Denkprozess)

**Erwartete Performance**:
- Total Time: ~6-8 Minuten für vollständige Debate
- Token Usage: ~4500 tokens
- User Experience: Visually engaging, educational

---

## 1. Architektur-Optionen (Evaluiert)

### Option 1: 2x Reasoning Models ❌ NICHT EMPFOHLEN

**Setup**: QwQ-32B (GPU0) vs QwQ-32B (GPU1)

**Performance**:
```
Round 1: 2x 10K tokens @ 10 tok/s = 16+ Minuten
Total: 20+ Minuten für 2 Runden
```

**Probleme**:
- ❌ **Zu langsam**: 16+ Minuten pro Debate inakzeptabel
- ❌ **Token-Explosion**: 20K+ tokens pro Runde → Context Overflow
- ❌ **Redundanz**: Viel "Lass mich überlegen..." Rauschen
- ❌ **UX**: User verliert Geduld nach 5 Minuten

**Verdict**: Reasoning Models sind zu verbose für schnelle Debates.

---

### Option 2: 2x Instruct Models ✅ BASELINE

**Setup**: Qwen3-30B-Instruct (GPU0) vs Qwen2.5-14B-Instruct (GPU1)

**Performance**:
```
Round 1: Agent A (1000T @ 10 tok/s) = 100s
         Agent B (800T @ 20 tok/s) = 40s
         → Parallel: max(100s, 40s) = 100s

Round 2: Rebuttals (~600T each)
         → Parallel: ~60s

Total: ~160s (2.7 Minuten) für 2 Runden
```

**Vorteile**:
- ✅ **Schnell**: <3 Minuten für vollständige Debate
- ✅ **Fokussiert**: Direkt zum Punkt, keine Redundanz
- ✅ **Mehr Runden möglich**: 3-4 Runden in gleicher Zeit
- ✅ **Klare Argumente**: User sieht konkrete Perspektiven

**Nachteile**:
- ⚠️ **Kein expliziter Denkprozess**: Reasoning implizit, nicht sichtbar
- ⚠️ **Weniger Tiefe**: Keine Selbst-Reflexion wie bei Reasoning Models

**Verdict**: Solid Baseline, schnell und effektiv.

---

### Option 3: HYBRID - Instruct Debate + Reasoning Synthesis ✅✅ EMPFOHLEN

**Setup**:
- **Debate**: Qwen3-30B-Instruct (GPU0) vs Qwen2.5-14B-Instruct (GPU1)
- **Synthesis**: QwQ-32B-Preview (GPU0, nach Debate)

**Performance**:
```
Round 1 (Instruct Debate): 100s
Round 2 (Instruct Rebuttals): 60s
Synthesis (Reasoning QwQ): 200s (2000 tokens @ 10 tok/s)

Total: ~360s (6 Minuten)
```

**Vorteile**:
- ✅ **Schnelle Debate**: Instruct für Argumentation (2.7 Min)
- ✅ **Tiefe Synthesis**: Reasoning zeigt `<thinking>` Process (3.3 Min)
- ✅ **Visual Appeal**: Debate knackig, Synthesis deep
- ✅ **Educational**: User sieht WIE KI abwägt
- ✅ **Optimal Balance**: Speed + Depth

**Nachteile**:
- ⚠️ **Model Switch nötig**: Instruct → Reasoning (5-10s Ladezeit)
  - **Mitigation**: KoboldCPP kann 2 Modelle parallel laufen (2x Instance)

**Verdict**: ✅ **BESTE Option** - Kombiniert Speed + Reasoning Visibility

---

## 2. Empfohlene Architektur (Hybrid)

### Hardware-Konfiguration

```bash
# === Setup 1: Debate Phase (beide GPUs aktiv) ===

# GPU 0: Primary Agent (Pragmatic Perspective)
CUDA_VISIBLE_DEVICES=0 koboldcpp \
  ~/models/Qwen3-30B-A3B-Instruct-Q4_K_M.gguf \
  --port 5001 \
  --contextsize 16384 \
  --gpulayers -1 \
  --usecublas \
  --quantkv 2

# GPU 1: Secondary Agent (Idealistic Perspective)
CUDA_VISIBLE_DEVICES=1 koboldcpp \
  ~/models/Qwen2.5-14B-Instruct-Q4_K_M.gguf \
  --port 5002 \
  --contextsize 8192 \
  --gpulayers -1 \
  --usecublas \
  --quantkv 2


# === Setup 2: Synthesis Phase (GPU0 switched to Reasoning) ===

# Option A: Replace GPU0 Instruct with Reasoning (5-10s switch time)
CUDA_VISIBLE_DEVICES=0 koboldcpp \
  ~/models/QwQ-32B-Preview-Q4_K_M.gguf \
  --port 5003 \
  --contextsize 32768 \
  --gpulayers -1 \
  --usecublas \
  --quantkv 2

# Option B: Run Reasoning on GPU1 (if 14B model unloaded)
CUDA_VISIBLE_DEVICES=1 koboldcpp \
  ~/models/QwQ-32B-Preview-Q4_K_M.gguf \
  --port 5003 \
  --contextsize 32768 \
  --gpulayers -1
```

**Recommended**: Option A (GPU0 for Reasoning) - Faster inference, larger context window available.

---

### Workflow (Step-by-Step)

```
User Input: "Should I use PostgreSQL or MongoDB?"

┌─────────────────────────────────────────────────────────┐
│ Step 1: Detect Ambiguous Question (Automatik LLM)      │
│ → Classification: "Debate-worthy" (subjective choice)  │
│ → Trigger: Dual-GPU Debate Mode                        │
└─────────────────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────────────────┐
│ Step 2: Round 1 - Initial Arguments (PARALLEL)         │
│                                                         │
│ GPU0 (30B Instruct): Pragmatic Perspective             │
│   Prompt: "Argue for PostgreSQL from practical view"   │
│   Output: ~1000 tokens (100s)                          │
│                                                         │
│ GPU1 (14B Instruct): Idealistic Perspective            │
│   Prompt: "Argue for MongoDB from best-practice view"  │
│   Output: ~800 tokens (40s)                            │
│                                                         │
│ → Parallel Execution: max(100s, 40s) = 100s            │
└─────────────────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────────────────┐
│ Step 3: Round 2 - Rebuttals (PARALLEL)                 │
│                                                         │
│ GPU0 Rebuttal: Counter MongoDB arguments               │
│   Prompt: "Opponent says: [MongoDB args]. Counter:"    │
│   Output: ~600 tokens (60s)                            │
│                                                         │
│ GPU1 Rebuttal: Counter PostgreSQL arguments            │
│   Prompt: "Opponent says: [PostgreSQL args]. Counter:" │
│   Output: ~550 tokens (28s)                            │
│                                                         │
│ → Parallel Execution: max(60s, 28s) = 60s              │
└─────────────────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────────────────┐
│ Step 4: Model Switch (GPU0: Instruct → Reasoning)      │
│ → Unload Qwen3-30B-Instruct from GPU0                  │
│ → Load QwQ-32B-Preview on GPU0                         │
│ → Switch Time: ~5-10s                                   │
└─────────────────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────────────────┐
│ Step 5: Reasoning Synthesis (QwQ-32B, GPU0)            │
│                                                         │
│ Prompt Template:                                        │
│ """                                                     │
│ Question: Should I use PostgreSQL or MongoDB?          │
│                                                         │
│ Pragmatic Perspective (Agent A):                       │
│ [PostgreSQL arguments + rebuttal]                      │
│                                                         │
│ Idealistic Perspective (Agent B):                      │
│ [MongoDB arguments + rebuttal]                         │
│                                                         │
│ Think deeply about both perspectives.                  │
│ Show your reasoning process in <thinking> tags.        │
│ Provide a balanced recommendation.                     │
│ """                                                     │
│                                                         │
│ Output:                                                 │
│ <thinking>                                              │
│ Hmm, lass mich beide Argumente abwägen...              │
│ Agent A sagt PostgreSQL wegen ACID guarantees...       │
│ Agent B sagt MongoDB wegen Schema flexibility...       │
│ Der Schlüssel ist der Use Case...                      │
│ [1500 tokens internal reasoning]                       │
│ </thinking>                                             │
│                                                         │
│ **Finale Empfehlung:**                                  │
│ [500 tokens balanced answer]                           │
│                                                         │
│ → Total: ~2000 tokens (200s @ 10 tok/s)                │
└─────────────────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────────────────┐
│ Step 6: Display Results to User                        │
│ → Show full debate transcript (Round 1, 2, Synthesis)  │
│ → Highlight <thinking> tags visually                   │
│ → Total Time: ~6 minutes                               │
└─────────────────────────────────────────────────────────┘
```

---

## 3. UI/UX Design (Chat-Integration)

### Visual Mockup

```
┌─────────────────────────────────────────────────────────┐
│ 🎭 INTER-KI DEBATE MODUS AKTIVIERT                     │
│                                                         │
│ Frage: "Should I use PostgreSQL or MongoDB?"           │
│ Agents: 2x Instruct (Debate) + 1x Reasoning (Synthesis)│
│                                                         │
│ ⏱️ Geschätzte Dauer: ~6 Minuten                         │
└─────────────────────────────────────────────────────────┘

┌─ ROUND 1: Initial Arguments ────────────────────────────┐
│                                                          │
│ 🔵 AGENT A (Pragmatisch - Qwen3-30B, GPU0)              │
│ ┌────────────────────────────────────────────────────┐  │
│ │ PostgreSQL ist die richtige Wahl weil:             │  │
│ │                                                    │  │
│ │ ✅ ACID-Garantien: Transactions sind kritisch für │  │
│ │    Finanz-/E-Commerce-Daten                       │  │
│ │ ✅ SQL-Standard: 50+ Jahre bewährte Technologie   │  │
│ │ ✅ Joins & Complex Queries: Relational model      │  │
│ │    ist optimal für structured data                │  │
│ │ ✅ Mature Ecosystem: pgAdmin, extensions, etc.    │  │
│ │                                                    │  │
│ │ MongoDB ist nur sinnvoll wenn:                    │  │
│ │ - Schema unbekannt/variabel                       │  │
│ │ - Horizontal scaling absolut kritisch             │  │
│ │                                                    │  │
│ │ Für 90% der Use Cases: PostgreSQL > MongoDB       │  │
│ └────────────────────────────────────────────────────┘  │
│ ⏱️ 1m 40s | 📊 1000 tokens                              │
│                                                          │
│ 🟢 AGENT B (Idealistisch - Qwen2.5-14B, GPU1)           │
│ ┌────────────────────────────────────────────────────┐  │
│ │ MongoDB ist die Zukunft weil:                     │  │
│ │                                                    │  │
│ │ ✅ Schema Flexibility: Rapid iteration möglich    │  │
│ │ ✅ Horizontal Scaling: Sharding out-of-the-box    │  │
│ │ ✅ JSON-Native: Perfect für moderne APIs          │  │
│ │ ✅ Developer Productivity: Weniger Migrations     │  │
│ │                                                    │  │
│ │ PostgreSQL Probleme:                               │  │
│ │ - Schema migrations aufwendig                      │  │
│ │ - Vertical scaling limits                          │  │
│ │ - Impedance mismatch (ORM pain)                    │  │
│ │                                                    │  │
│ │ Moderne Apps brauchen: Flexibility > Rigidity     │  │
│ └────────────────────────────────────────────────────┘  │
│ ⏱️ 40s | 📊 800 tokens                                  │
└──────────────────────────────────────────────────────────┘

┌─ ROUND 2: Rebuttals ────────────────────────────────────┐
│                                                          │
│ 🔵 AGENT A - Gegenargument:                             │
│ ┌────────────────────────────────────────────────────┐  │
│ │ "Schema flexibility" klingt gut, aber:             │  │
│ │                                                    │  │
│ │ ❌ Keine Enforced Constraints → Data corruption   │  │
│ │ ❌ "Schemaless" = Schema in application code      │  │
│ │    → Jeder Microservice muss Validation duplizieren│ │
│ │ ❌ Migrations sind GUT: Force you to think about  │  │
│ │    data integrity                                  │  │
│ │                                                    │  │
│ │ PostgreSQL kann auch JSON (JSONB type) - best of  │  │
│ │ both worlds: Schema where needed, flexibility      │  │
│ │ where useful.                                      │  │
│ └────────────────────────────────────────────────────┘  │
│ ⏱️ 1m | 📊 600 tokens                                   │
│                                                          │
│ 🟢 AGENT B - Gegenargument:                             │
│ ┌────────────────────────────────────────────────────┐  │
│ │ "ACID guarantees" sind überschätzt für viele Apps:│  │
│ │                                                    │  │
│ │ ❌ Most web apps don't need strict consistency    │  │
│ │    → Eventual consistency ist OK (BASE > ACID)    │  │
│ │ ❌ Transactions = Performance bottleneck           │  │
│ │ ❌ PostgreSQL vertical scaling hits limits at     │  │
│ │    1-10M rows (need sharding = complex)            │  │
│ │                                                    │  │
│ │ MongoDB's atomic operations auf document-level    │  │
│ │ sind ausreichend für 95% der Fälle.               │  │
│ └────────────────────────────────────────────────────┘  │
│ ⏱️ 28s | 📊 550 tokens                                  │
└──────────────────────────────────────────────────────────┘

┌─ 🔄 MODEL SWITCH ───────────────────────────────────────┐
│ Lade Reasoning Model für Synthesis...                   │
│ ✅ QwQ-32B-Preview geladen (8.2s)                        │
└──────────────────────────────────────────────────────────┘

┌─ 🧠 REASONING SYNTHESIS (QwQ-32B, GPU0) ────────────────┐
│                                                          │
│ <thinking>                                               │
│ Hmm, ich habe jetzt zwei sehr unterschiedliche          │
│ Perspektiven gehört. Lass mich systematisch abwägen:    │
│                                                          │
│ **Agent A's Hauptargumente (PostgreSQL):**              │
│ 1. ACID guarantees → Data integrity                     │
│ 2. SQL-Standard → Proven, mature                        │
│ 3. Complex queries → Relational power                   │
│                                                          │
│ **Agent B's Hauptargumente (MongoDB):**                 │
│ 1. Schema flexibility → Fast iteration                  │
│ 2. Horizontal scaling → Cloud-native                    │
│ 3. JSON-native → Modern APIs                            │
│                                                          │
│ Moment... beide haben teilweise recht, aber für         │
│ UNTERSCHIEDLICHE Use Cases!                             │
│                                                          │
│ Lass mich die Entscheidungskriterien identifizieren:    │
│                                                          │
│ **Kritischer Faktor 1: Data Consistency Requirements**  │
│ - Financial data? → PostgreSQL (ACID kritisch)          │
│ - User profiles? → MongoDB OK (eventual consistency)    │
│                                                          │
│ **Kritischer Faktor 2: Query Complexity**               │
│ - Multi-table joins? → PostgreSQL (relational)          │
│ - Simple lookups? → MongoDB (document model)            │
│                                                          │
│ **Kritischer Faktor 3: Scale Strategy**                 │
│ - Vertical scaling OK (<10M rows)? → PostgreSQL         │
│ - Horizontal scaling needed (>100M docs)? → MongoDB     │
│                                                          │
│ **Kritischer Faktor 4: Team Expertise**                 │
│ - SQL experts? → PostgreSQL (leverage skills)           │
│ - NoSQL background? → MongoDB (faster onboarding)       │
│                                                          │
│ Ah! Die Antwort ist nicht binär - es hängt vom          │
│ spezifischen Use Case ab. Lass mich eine Decision       │
│ Matrix erstellen...                                      │
│ </thinking>                                              │
│                                                          │
│ ────────────────────────────────────────────────────────│
│                                                          │
│ **🎯 FINALE EMPFEHLUNG:**                                │
│                                                          │
│ Die Wahl zwischen PostgreSQL und MongoDB ist NICHT      │
│ "entweder-oder", sondern **kontextabhängig**:           │
│                                                          │
│ **✅ Wähle PostgreSQL wenn:**                            │
│ 1. **Data Integrity kritisch** (Finanzen, E-Commerce)   │
│    → ACID-Garantien unverzichtbar                       │
│ 2. **Complex Queries nötig** (Analytics, Reports)       │
│    → SQL Joins & Aggregations sind Standard             │
│ 3. **Structured Data** mit klarem Schema                │
│    → Relational model ist optimal                       │
│ 4. **Moderate Scale** (<10M rows)                       │
│    → Vertical scaling ausreichend                       │
│                                                          │
│ **✅ Wähle MongoDB wenn:**                               │
│ 1. **Rapid Iteration** wichtiger als Consistency        │
│    → Schema flexibility beschleunigt Development        │
│ 2. **Massive Scale** (>100M documents)                  │
│    → Horizontal sharding out-of-the-box                 │
│ 3. **Unstructured/Variable Data** (User-generated)      │
│    → Document model natürlicher als EAV-Tables          │
│ 4. **Simple Lookups** dominieren (Key-Value-like)       │
│    → MongoDB's B-tree indices sehr effizient            │
│                                                          │
│ **💡 Hybrid-Ansatz (BESTE Lösung für viele Apps):**     │
│ - **PostgreSQL** für transactional data (Orders, Users) │
│ - **MongoDB** für analytics/logs (Events, Metrics)      │
│ - Beide DBs via Microservices oder Data Sync           │
│                                                          │
│ **Meine konkrete Empfehlung für dich:**                 │
│ Wenn du noch unsicher bist → **Start with PostgreSQL**  │
│ Warum? Weil du SPÄTER zu MongoDB migrieren kannst       │
│ (export JSON), aber MongoDB → PostgreSQL ist schmerzhaft│
│ (schema reconstruction). PostgreSQL ist der "sichere"    │
│ Default für 80% der Apps.                               │
│                                                          │
│ **Nur wenn** du SICHER bist dass:                       │
│ - Schema ändert sich ständig                            │
│ - Du wirst >100M documents haben                        │
│ - Eventual consistency ist akzeptabel                   │
│ → DANN start with MongoDB.                              │
└──────────────────────────────────────────────────────────┘
│ ⏱️ 3m 20s | 📊 2000 tokens                              │
└──────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ ✅ DEBATE ABGESCHLOSSEN                                 │
│                                                         │
│ ⏱️ Gesamtzeit: 6m 8s                                    │
│ 📊 Gesamte Tokens: 4950                                │
│                                                         │
│ Agents beteiligt:                                       │
│ 🔵 Qwen3-30B (GPU0): Pragmatic perspective             │
│ 🟢 Qwen2.5-14B (GPU1): Idealistic perspective          │
│ 🧠 QwQ-32B (GPU0): Reasoning synthesis                 │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Implementation Details

### 4.1 Code Structure

```
aifred/
├── lib/
│   ├── dual_gpu_debate.py           # NEW: Debate orchestration
│   ├── reasoning_formatter.py       # NEW: <thinking> tag parsing & display
│   └── koboldcpp_manager.py         # EXTEND: Multi-instance management
├── state.py                          # EXTEND: debate_mode state
└── aifred.py                         # EXTEND: Debate UI components
```

---

### 4.2 Core Implementation (`dual_gpu_debate.py`)

```python
"""
Dual-GPU Inter-KI Debate System

Orchestrates multi-round debates between two KI agents with reasoning synthesis.
"""

import asyncio
import time
from typing import AsyncIterator, Dict, List, Tuple
from dataclasses import dataclass

from aifred.lib.koboldcpp_utils import KoboldCppClient


@dataclass
class DebateRound:
    """Represents one round of debate"""
    agent_a_response: str
    agent_a_tokens: int
    agent_a_time: float

    agent_b_response: str
    agent_b_tokens: int
    agent_b_time: float


@dataclass
class DebateResult:
    """Complete debate result with all rounds"""
    question: str
    rounds: List[DebateRound]
    synthesis: str
    synthesis_tokens: int
    synthesis_time: float
    total_time: float
    total_tokens: int


class DualGPUDebateOrchestrator:
    """
    Orchestrates debates between two KI agents on separate GPUs.

    Architecture:
    - Round 1-2: Instruct models (fast debate)
    - Synthesis: Reasoning model (deep analysis)
    """

    def __init__(
        self,
        agent_a_url: str = "http://localhost:5001",
        agent_b_url: str = "http://localhost:5002",
        reasoning_url: str = "http://localhost:5003"
    ):
        self.agent_a = KoboldCppClient(base_url=agent_a_url)
        self.agent_b = KoboldCppClient(base_url=agent_b_url)
        self.reasoning = KoboldCppClient(base_url=reasoning_url)

        # Agent personas
        self.agent_a_persona = "pragmatic"  # Real-world constraints
        self.agent_b_persona = "idealistic"  # Best practices, theory

    async def debate(
        self,
        question: str,
        rounds: int = 2,
        max_tokens_per_response: int = 1000
    ) -> AsyncIterator[Dict]:
        """
        Run complete debate with synthesis.

        Yields events:
        - {"type": "round_start", "round": 1}
        - {"type": "agent_a_thinking", "message": "..."}
        - {"type": "agent_a_response", "text": "...", "tokens": X, "time": Y}
        - {"type": "agent_b_response", ...}
        - {"type": "round_complete", "round": 1}
        - {"type": "synthesis_start"}
        - {"type": "synthesis_thinking", "text": "<thinking>..."}
        - {"type": "synthesis_response", "text": "...", "tokens": X}
        - {"type": "debate_complete", "result": DebateResult}
        """

        start_time = time.time()
        debate_rounds: List[DebateRound] = []

        # Track full context for synthesis
        debate_transcript = f"Question: {question}\n\n"

        # === ROUND 1: Initial Arguments ===
        yield {"type": "round_start", "round": 1, "phase": "Initial Arguments"}

        # Parallel execution of both agents
        round_1_a, round_1_b = await asyncio.gather(
            self._generate_argument(
                agent=self.agent_a,
                agent_name="Agent A (Pragmatisch)",
                question=question,
                perspective=self.agent_a_persona,
                max_tokens=max_tokens_per_response,
                event_prefix="agent_a"
            ),
            self._generate_argument(
                agent=self.agent_b,
                agent_name="Agent B (Idealistisch)",
                question=question,
                perspective=self.agent_b_persona,
                max_tokens=max_tokens_per_response,
                event_prefix="agent_b"
            )
        )

        # Yield responses
        for event in round_1_a['events']:
            yield event
        for event in round_1_b['events']:
            yield event

        # Store round
        round_1 = DebateRound(
            agent_a_response=round_1_a['text'],
            agent_a_tokens=round_1_a['tokens'],
            agent_a_time=round_1_a['time'],
            agent_b_response=round_1_b['text'],
            agent_b_tokens=round_1_b['tokens'],
            agent_b_time=round_1_b['time']
        )
        debate_rounds.append(round_1)

        debate_transcript += f"Agent A (Pragmatic):\n{round_1_a['text']}\n\n"
        debate_transcript += f"Agent B (Idealistic):\n{round_1_b['text']}\n\n"

        yield {"type": "round_complete", "round": 1}

        # === ROUND 2+: Rebuttals ===
        for round_num in range(2, rounds + 1):
            yield {"type": "round_start", "round": round_num, "phase": "Rebuttal"}

            # Each agent gets opponent's previous response
            rebuttal_a, rebuttal_b = await asyncio.gather(
                self._generate_rebuttal(
                    agent=self.agent_a,
                    agent_name="Agent A",
                    opponent_text=debate_rounds[-1].agent_b_response,
                    max_tokens=max_tokens_per_response // 2,
                    event_prefix="agent_a"
                ),
                self._generate_rebuttal(
                    agent=self.agent_b,
                    agent_name="Agent B",
                    opponent_text=debate_rounds[-1].agent_a_response,
                    max_tokens=max_tokens_per_response // 2,
                    event_prefix="agent_b"
                )
            )

            for event in rebuttal_a['events']:
                yield event
            for event in rebuttal_b['events']:
                yield event

            rebuttal_round = DebateRound(
                agent_a_response=rebuttal_a['text'],
                agent_a_tokens=rebuttal_a['tokens'],
                agent_a_time=rebuttal_a['time'],
                agent_b_response=rebuttal_b['text'],
                agent_b_tokens=rebuttal_b['tokens'],
                agent_b_time=rebuttal_b['time']
            )
            debate_rounds.append(rebuttal_round)

            debate_transcript += f"Agent A Rebuttal:\n{rebuttal_a['text']}\n\n"
            debate_transcript += f"Agent B Rebuttal:\n{rebuttal_b['text']}\n\n"

            yield {"type": "round_complete", "round": round_num}

        # === MODEL SWITCH NOTIFICATION ===
        yield {"type": "model_switch_start", "message": "Lade Reasoning Model..."}
        # (Assume reasoning model already loaded on port 5003)
        yield {"type": "model_switch_complete", "message": "QwQ-32B geladen"}

        # === SYNTHESIS: Reasoning Model Analyzes Full Debate ===
        yield {"type": "synthesis_start"}

        synthesis_prompt = f"""You are a wise judge analyzing a debate between two AI agents.

{debate_transcript}

Task: Think deeply about both perspectives. Show your reasoning process in <thinking> tags.
Then provide a balanced, comprehensive answer that:
1. Acknowledges strengths of both arguments
2. Identifies key decision factors
3. Gives concrete recommendation

Think step-by-step and be thorough."""

        synthesis_start = time.time()

        # Stream synthesis with <thinking> tag detection
        synthesis_text = ""
        synthesis_tokens = 0

        async for chunk in self.reasoning.generate_streaming(
            prompt=synthesis_prompt,
            max_tokens=2500,
            temperature=0.6
        ):
            synthesis_text += chunk['text']
            synthesis_tokens = chunk['tokens_generated']

            # Detect <thinking> tags and yield separately
            if '<thinking>' in synthesis_text and '</thinking>' not in synthesis_text:
                yield {
                    "type": "synthesis_thinking",
                    "text": chunk['text'],
                    "in_thinking": True
                }
            elif '</thinking>' in chunk['text']:
                yield {
                    "type": "synthesis_thinking_end",
                    "text": chunk['text']
                }
            else:
                yield {
                    "type": "synthesis_response",
                    "text": chunk['text']
                }

        synthesis_time = time.time() - synthesis_start
        total_time = time.time() - start_time

        # Calculate totals
        total_tokens = sum(
            r.agent_a_tokens + r.agent_b_tokens for r in debate_rounds
        ) + synthesis_tokens

        result = DebateResult(
            question=question,
            rounds=debate_rounds,
            synthesis=synthesis_text,
            synthesis_tokens=synthesis_tokens,
            synthesis_time=synthesis_time,
            total_time=total_time,
            total_tokens=total_tokens
        )

        yield {"type": "debate_complete", "result": result}

    async def _generate_argument(
        self,
        agent: KoboldCppClient,
        agent_name: str,
        question: str,
        perspective: str,
        max_tokens: int,
        event_prefix: str
    ) -> Dict:
        """Generate initial argument from one agent"""

        perspective_prompts = {
            "pragmatic": "from a PRAGMATIC perspective focusing on real-world constraints, practical benefits, and proven approaches",
            "idealistic": "from an IDEALISTIC perspective focusing on best practices, theoretical advantages, and long-term vision"
        }

        prompt = f"""{question}

Argue {perspective_prompts[perspective]}.

Provide concrete, specific arguments. Be persuasive but honest."""

        events = []
        events.append({
            "type": f"{event_prefix}_thinking",
            "message": f"{agent_name} überlegt..."
        })

        start = time.time()
        response = await agent.generate(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=0.7
        )
        elapsed = time.time() - start

        events.append({
            "type": f"{event_prefix}_response",
            "text": response['text'],
            "tokens": response['tokens_generated'],
            "time": elapsed
        })

        return {
            "text": response['text'],
            "tokens": response['tokens_generated'],
            "time": elapsed,
            "events": events
        }

    async def _generate_rebuttal(
        self,
        agent: KoboldCppClient,
        agent_name: str,
        opponent_text: str,
        max_tokens: int,
        event_prefix: str
    ) -> Dict:
        """Generate rebuttal to opponent's argument"""

        prompt = f"""Your opponent argues:

{opponent_text}

Provide a counter-argument addressing their main points. Be specific and cite weaknesses in their reasoning."""

        events = []
        events.append({
            "type": f"{event_prefix}_thinking",
            "message": f"{agent_name} formuliert Gegenargument..."
        })

        start = time.time()
        response = await agent.generate(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=0.7
        )
        elapsed = time.time() - start

        events.append({
            "type": f"{event_prefix}_response",
            "text": response['text'],
            "tokens": response['tokens_generated'],
            "time": elapsed
        })

        return {
            "text": response['text'],
            "tokens": response['tokens_generated'],
            "time": elapsed,
            "events": events
        }
```

---

### 4.3 UI Integration (`aifred.py`)

**New Component: Debate Display**

```python
def debate_message_component(debate_round: dict) -> rx.Component:
    """
    Displays one round of debate with agent responses side-by-side.
    """
    return rx.box(
        # Round header
        rx.heading(
            f"Round {debate_round['round']}: {debate_round['phase']}",
            size="4",
            margin_bottom="1em"
        ),

        # Two-column layout for parallel arguments
        rx.flex(
            # Agent A (left column)
            rx.box(
                rx.badge(
                    "🔵 Agent A (Pragmatisch)",
                    color_scheme="blue",
                    size="2",
                    margin_bottom="0.5em"
                ),
                rx.box(
                    rx.markdown(debate_round['agent_a_text']),
                    padding="1em",
                    background_color="#1e2936",
                    border_radius="8px",
                    border="1px solid #3b82f6"
                ),
                rx.text(
                    f"⏱️ {debate_round['agent_a_time']:.1f}s | 📊 {debate_round['agent_a_tokens']} tokens",
                    size="1",
                    color="gray",
                    margin_top="0.5em"
                ),
                flex="1",
                margin_right="1em"
            ),

            # Agent B (right column)
            rx.box(
                rx.badge(
                    "🟢 Agent B (Idealistisch)",
                    color_scheme="green",
                    size="2",
                    margin_bottom="0.5em"
                ),
                rx.box(
                    rx.markdown(debate_round['agent_b_text']),
                    padding="1em",
                    background_color="#1e2936",
                    border_radius="8px",
                    border="1px solid #22c55e"
                ),
                rx.text(
                    f"⏱️ {debate_round['agent_b_time']:.1f}s | 📊 {debate_round['agent_b_tokens']} tokens",
                    size="1",
                    color="gray",
                    margin_top="0.5em"
                ),
                flex="1"
            ),

            direction="row",
            width="100%"
        ),

        margin_bottom="2em",
        width="100%"
    )


def synthesis_component(synthesis_data: dict) -> rx.Component:
    """
    Displays reasoning synthesis with <thinking> tags highlighted.
    """
    return rx.box(
        rx.heading(
            "🧠 Reasoning Synthesis (QwQ-32B)",
            size="4",
            margin_bottom="1em"
        ),

        # <thinking> section (collapsible)
        rx.cond(
            synthesis_data['has_thinking'],
            rx.accordion.root(
                rx.accordion.item(
                    rx.accordion.trigger(
                        "💭 Denkprozess anzeigen",
                        color="gray"
                    ),
                    rx.accordion.content(
                        rx.box(
                            rx.markdown(synthesis_data['thinking_text']),
                            padding="1em",
                            background_color="#2d1810",
                            border_left="4px solid #f59e0b",
                            font_family="monospace",
                            font_size="0.9em",
                            color="#fbbf24"
                        )
                    ),
                    value="thinking"
                ),
                collapsible=True,
                width="100%"
            )
        ),

        # Final answer
        rx.box(
            rx.heading("🎯 Finale Empfehlung:", size="3", margin_bottom="0.5em"),
            rx.markdown(synthesis_data['final_answer']),
            padding="1em",
            background_color="#1e2936",
            border_radius="8px",
            border="2px solid #8b5cf6",
            margin_top="1em"
        ),

        # Metrics
        rx.text(
            f"⏱️ {synthesis_data['time']:.1f}s | 📊 {synthesis_data['tokens']} tokens",
            size="1",
            color="gray",
            margin_top="0.5em"
        ),

        margin_top="2em",
        width="100%"
    )
```

---

## 5. Testing & Validation

### Test Scenarios

#### Test 1: Technical Decision (PostgreSQL vs MongoDB)
**Expected Behavior**:
- Agent A: Argues for PostgreSQL (ACID, SQL, maturity)
- Agent B: Argues for MongoDB (flexibility, scaling, JSON-native)
- Synthesis: Context-dependent recommendation with decision matrix

**Success Criteria**:
- ✅ Both agents provide concrete arguments (not generic)
- ✅ Rebuttals address opponent's specific points
- ✅ Synthesis shows `<thinking>` tags with clear reasoning
- ✅ Final answer acknowledges both perspectives
- ✅ Total time <8 minutes

---

#### Test 2: Architectural Decision (Monolith vs Microservices)
**Expected Behavior**:
- Agent A: Pragmatic (start monolith, extract later)
- Agent B: Idealistic (microservices from day 1)
- Synthesis: Team-size-dependent recommendation

**Success Criteria**:
- ✅ Arguments reference real-world constraints (Conway's Law, team size)
- ✅ Synthesis identifies key decision factors
- ✅ Recommendation is actionable

---

#### Test 3: Programming Language (Python vs Rust)
**Expected Behavior**:
- Agent A: Python for productivity, ecosystem
- Agent B: Rust for performance, safety
- Synthesis: Use-case-dependent (web app vs systems programming)

**Success Criteria**:
- ✅ Both agents cite specific language features
- ✅ Synthesis maps use cases to language strengths

---

### Performance Benchmarks

| Metric | Target | Acceptable | Unacceptable |
|--------|--------|------------|--------------|
| **Total Time** | <6 min | <8 min | >10 min |
| **Round 1 Time** | <2 min | <3 min | >4 min |
| **Synthesis Time** | <4 min | <5 min | >6 min |
| **Total Tokens** | <5000 | <6000 | >7000 |
| **Agent A tok/s** | >9 | >7 | <5 |
| **Agent B tok/s** | >18 | >15 | <10 |
| **Reasoning tok/s** | >8 | >6 | <4 |

---

## 6. Rollout Plan

### Phase 1: MVP (1 Woche) ✅ START HERE

**Goal**: Proof-of-Concept mit basic UI

**Tasks**:
1. **Day 1-2**: Implement `DualGPUDebateOrchestrator` (core logic)
2. **Day 3**: UI components (debate display, synthesis formatting)
3. **Day 4**: Integration in AIfred state + event handling
4. **Day 5**: Testing with 3 scenarios (PostgreSQL, Microservices, Python)
5. **Day 6-7**: Bug fixes, UI polish

**Deliverables**:
- ✅ Working debate feature (opt-in)
- ✅ Visual transcript in chat
- ✅ `<thinking>` tags highlighted

**Success Metrics**:
- Debate completes in <8 min
- User can read both agent perspectives clearly
- Synthesis shows reasoning process

---

### Phase 2: Polish & Optimization (Optional, 1 Woche)

**Goal**: Production-ready quality

**Tasks**:
1. Parallel execution optimization (reduce latency)
2. Model auto-switching (detect when to use Reasoning vs Instruct)
3. Configurable debate parameters (rounds, max tokens)
4. Save debate transcripts (export as Markdown)
5. Performance metrics dashboard

**Deliverables**:
- ✅ <6 min average debate time
- ✅ Export feature
- ✅ Auto-detection of debate-worthy questions

---

### Phase 3: Advanced Features (Future)

**Ideas**:
- Multi-round voting (3+ agents, consensus algorithm)
- Domain-specific agents (Legal, Medical, Technical)
- User can pick agent personas
- Judge mode (user votes on best argument)

---

## 7. Risks & Mitigations

### Risk 1: Model Switch Latency (5-10s)

**Problem**: Switching GPU0 from Instruct to Reasoning takes time

**Mitigation 1**: Pre-load Reasoning on GPU1 (sacrifice 14B instance)
```bash
# Alternative: GPU1 always runs Reasoning (no 14B Instruct)
CUDA_VISIBLE_DEVICES=1 koboldcpp ~/models/QwQ-32B-Preview-Q4_K_M.gguf --port 5002
```
**Trade-off**: Lose parallel debate (sequential instead), but no model switch

**Mitigation 2**: 3-GPU setup (if available)
```bash
# GPU 0: 30B Instruct (Primary)
# GPU 1: 14B Instruct (Secondary)
# GPU 2: 32B Reasoning (Synthesis)
```
**Trade-off**: Requires 3rd GPU

---

### Risk 2: Reasoning Model Too Verbose (>3000 tokens)

**Problem**: QwQ can generate 10K+ tokens if not constrained

**Mitigation**:
- Set `max_tokens=2500` in synthesis prompt
- Add instruction: "Keep final answer under 500 words"
- Fallback to Instruct model if Reasoning OOMs

---

### Risk 3: User Boredom (6+ min wait)

**Problem**: User loses interest during long debates

**Mitigation**:
- Stream output in real-time (each agent's response visible immediately)
- Progress bar: "Round 1/2 abgeschlossen..."
- Estimated time remaining: "~3 Min verbleibend"
- Make debate visually engaging (animations, color-coding)

---

### Risk 4: Low-Quality Arguments (agents agree too quickly)

**Problem**: Both agents give similar answers, no real debate

**Mitigation**:
- Stronger persona prompts ("You MUST argue for X, even if you disagree")
- Devil's advocate mode (Agent B forced to take opposite view)
- Post-generation check: If similarity >80%, regenerate with stronger prompts

---

## 8. Next Steps

### Option A: Build MVP (1 Woche) ✅ RECOMMENDED

**Action Items**:
1. Clone `aifred/lib/dual_gpu_debate.py` template (from this doc)
2. Implement core orchestrator logic
3. Create UI components for debate display
4. Test with PostgreSQL scenario
5. Iterate based on output quality

**Commitment**: 1 Woche Development + Testing

---

### Option B: Manual Prototype (1-2 Tage)

**Action Items**:
1. Start 2x KoboldCPP manually (GPU0 + GPU1)
2. Test debate via curl:
   ```bash
   # Agent A
   curl http://localhost:5001/v1/completions -d '{
     "prompt": "Argue for PostgreSQL from pragmatic view...",
     "max_tokens": 1000
   }'

   # Agent B
   curl http://localhost:5002/v1/completions -d '{
     "prompt": "Argue for MongoDB from idealistic view...",
     "max_tokens": 1000
   }'
   ```
3. Manually combine outputs, read full "debate"
4. Decide: Is this interesting enough to build UI?

**Commitment**: 1-2 Tage Experimentation

---

### Option C: NICHT bauen (Focus auf andere Features)

**Reasoning**: If code review is rare, debate might be too niche

**Alternative Investment**:
- Improve Automatik decision quality
- Optimize RAG retrieval (re-ranking)
- Add more web scraping sources

---

## 9. Conclusion

**Summary**:
- **Hybrid Approach** (Instruct Debate + Reasoning Synthesis) ist optimal
- **Expected Performance**: ~6 Min, ~4500 Tokens
- **Visual Appeal**: Highly engaging, educational
- **Use Cases**: Ambiguous decisions, architecture choices, technical debates

**Recommendation**:
✅ **START with Manual Prototype** (Option B, 1-2 Tage)
→ Validiere ob Output wirklich interessant ist
→ DANN entscheide: MVP bauen (Option A) oder nicht (Option C)

**Frage an dich**:
Willst du **Option B** (Manual Prototype) starten? Ich kann dir:
1. Genaue curl-Commands geben für PostgreSQL Debate
2. Prompts für Agent A + B + Synthesis schreiben
3. Zeigen wie du Outputs kombinierst

**Oder direkt zu Option A** (MVP in 1 Woche)?

---

**Status**: Dokumentation abgeschlossen
**Nächster Schritt**: Deine Entscheidung - Option A, B, oder C?
