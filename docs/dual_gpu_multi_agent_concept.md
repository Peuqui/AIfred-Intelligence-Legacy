# Dual-GPU KI Agents - Multi-Agent System mit 2x Tesla P40

## Konzept

Zwei separate KoboldCpp Instanzen, jede auf einer eigenen GPU, die zusammenarbeiten um Probleme zu lösen.

```
GPU 0 (Tesla P40 #1): KoboldCpp Instance 1 (Port 5001) → Agent A
GPU 1 (Tesla P40 #2): KoboldCpp Instance 2 (Port 5002) → Agent B
        ↓                                    ↓
              Orchestrator (Python)
        (koordiniert Zusammenarbeit)
```

## Vorteile

- ✅ Beide GPUs voll genutzt (keine verschwendete Hardware)
- ✅ Keine langsame Inter-GPU Kommunikation über Oculink/USB4
- ✅ "Zwei Köpfe denken besser als einer" - Agents diskutieren & reviewen
- ✅ Parallel Processing: Beide können gleichzeitig an Teilproblemen arbeiten
- ✅ Spezialisierung möglich (z.B. Agent A = Coder, Agent B = Reviewer)

## Nachteile

- ❌ Kleinere Modelle pro GPU (z.B. 2x 14B statt 1x 30B)
- ❌ Orchestrator-Komplexität
- ❌ Context-Duplikation (beide Agents brauchen gleiche Historie)
- ❌ Mehr VRAM für Context (2x statt 1x)

## Mögliche Konfigurationen

### Option 1: Gleiche Modelle (Redundanz & Diskussion)
```
GPU 0: Qwen2.5-14B-Instruct (Agent A)
GPU 1: Qwen2.5-14B-Instruct (Agent B)
```
- Use Case: Beide analysieren gleiche Problem, diskutieren Lösungen
- Vorteil: Demokratischer Ansatz, gegenseitige Prüfung

### Option 2: Spezialisierte Rollen
```
GPU 0: Qwen3-Coder-30B (Agent "Coder")
GPU 1: Qwen2.5-7B-Instruct (Agent "Reviewer")
```
- Use Case: Coder schreibt Code, Reviewer prüft & testet
- Vorteil: Arbeitsteilung nach Stärken

### Option 3: Größe vs. Geschwindigkeit
```
GPU 0: Qwen2.5-14B (Agent "Deep Thinker")
GPU 1: Qwen2.5-3B (Agent "Fast Responder")
```
- Use Case: Deep für komplexe Analyse, Fast für schnelle Checks
- Vorteil: Optimal für verschiedene Task-Typen

## Implementierung

### Phase 1: KoboldCpp Multi-Instance Support

**Änderungen in AIfred:**

1. **koboldcpp_manager.py erweitern:**
   - Statt singleton: Multi-instance Manager
   - GPU-Pinning: `CUDA_VISIBLE_DEVICES=0` bzw `=1`
   - Port-Management: 5001, 5002, ...

2. **Konfiguration:**
```python
{
    "agents": [
        {
            "name": "agent_a",
            "gpu_id": 0,
            "port": 5001,
            "model": "Qwen2.5-14B-Instruct",
            "role": "coder"
        },
        {
            "name": "agent_b",
            "gpu_id": 1,
            "port": 5002,
            "model": "Qwen2.5-14B-Instruct",
            "role": "reviewer"
        }
    ]
}
```

3. **Start-Logik:**
```bash
# Agent A
CUDA_VISIBLE_DEVICES=0 koboldcpp model_a.gguf 5001 --contextsize 16384 --gpulayers -1

# Agent B
CUDA_VISIBLE_DEVICES=1 koboldcpp model_b.gguf 5002 --contextsize 16384 --gpulayers -1
```

### Phase 2: Orchestrator

**Neues Modul: `aifred/lib/multi_agent_orchestrator.py`**

```python
class MultiAgentOrchestrator:
    """
    Koordiniert Zusammenarbeit zwischen mehreren KI Agents
    """

    async def parallel_generate(self, prompt: str):
        """Beide Agents generieren parallel"""
        responses = await asyncio.gather(
            agent_a.generate(prompt),
            agent_b.generate(prompt)
        )
        return responses

    async def debate(self, topic: str, rounds: int = 2):
        """Agents diskutieren ein Thema"""
        for round in range(rounds):
            response_a = await agent_a.generate(...)
            response_b = await agent_b.generate(f"Agent A sagt: {response_a}")
            # ...

    async def code_review_workflow(self, task: str):
        """Coder schreibt, Reviewer prüft"""
        code = await coder_agent.generate(f"Write code: {task}")
        review = await reviewer_agent.generate(f"Review this code: {code}")
        # ...
```

### Phase 3: Use Cases

**1. Code Review Workflow:**
```
User Request → Agent A (Coder) schreibt Code
            → Agent B (Reviewer) analysiert Code
            → Agent B gibt Feedback
            → Agent A verbessert Code
            → Finale Lösung
```

**2. Parallel Problem Solving:**
```
Complex Problem
    ├─→ Agent A: Ansatz 1
    └─→ Agent B: Ansatz 2
         ↓
    Orchestrator vergleicht & wählt besten aus
```

**3. Debate & Consensus:**
```
Ambiguous Question
    → Round 1: Beide geben Meinung
    → Round 2: Beide kommentieren andere Meinung
    → Round 3: Konsens oder "agree to disagree"
```

## Nächste Schritte

### TODO Phase 1 - Basic Multi-Instance
- [ ] KoboldCpp Manager Multi-Instance fähig machen
- [ ] GPU Pinning implementieren (CUDA_VISIBLE_DEVICES)
- [ ] Port-Management für mehrere Instanzen
- [ ] Beide KoboldCpp Prozesse starten können
- [ ] Health Check für beide Instances

### TODO Phase 2 - Orchestrator
- [ ] `multi_agent_orchestrator.py` erstellen
- [ ] Basis-Methoden: parallel_generate(), sequential_generate()
- [ ] Debate-Logik implementieren
- [ ] Code-Review Workflow
- [ ] Context-Synchronisation zwischen Agents

### TODO Phase 3 - Integration in AIfred UI
- [ ] Multi-Agent Mode in UI auswählbar
- [ ] Agent-Rollen konfigurierbar
- [ ] Workflow-Auswahl (Review, Debate, Parallel, ...)
- [ ] Agent-Konversation visualisieren
- [ ] Performance-Metriken (Tokens/s pro Agent)

### TODO Phase 4 - Advanced Features
- [ ] Agent-Spezialisierung (Coder vs Reviewer vs Tester)
- [ ] Dynamische Aufgabenverteilung
- [ ] Konfliktauflösung wenn Agents nicht übereinstimmen
- [ ] Voting-System bei >2 Agents
- [ ] Load Balancing basierend auf Task-Typ

## Offene Fragen

1. **Context Sharing:**
   - Wie teilen beide Agents die Konversationshistorie?
   - Separate Contexts oder unified?

2. **Performance:**
   - Overhead durch Orchestrator messbar?
   - Lohnt sich der Multi-Agent Ansatz vs. 1x großes Modell?

3. **Error Handling:**
   - Was wenn ein Agent crashed?
   - Fallback auf Single-Agent Mode?

4. **Resource Management:**
   - Context-Size Balance zwischen beiden
   - VRAM Monitoring für beide GPUs

## Referenzen

- KoboldCpp GPU Pinning: CUDA_VISIBLE_DEVICES
- Multi-Agent Frameworks: AutoGen, LangGraph
- AIfred Architektur: state.py, koboldcpp_manager.py
