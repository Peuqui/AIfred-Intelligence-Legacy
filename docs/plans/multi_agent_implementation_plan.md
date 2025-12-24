# Multi-Agent Implementation Plan: AIfred + Sokrates

## Übersicht

**Ziel:** Multi-Agent Debate-System für AIfred implementieren
**KI-Namen:** AIfred (Hauptantwort) + Sokrates (Kritiker/Debattierer)
**Patterns:** Standard, User-as-Judge, Auto-Consensus, Devil's Advocate

**Wichtige Design-Entscheidungen:**
- Settings werden persistent in `settings.json` gespeichert (nicht bei Browser-Reload zurückgesetzt)
- Gleiches LLM-Modell wird für beide Agenten verwendet (unterschiedliche System-Prompts)
- User kann jederzeit Diskussionseinwürfe machen (Input-Feld bleibt permanent aktiv)
- User-Input wird gequeued während Inferenz läuft, dann bei nächster Runde injiziert
- `LGTM` als Konsens-Marker für Auto-Consensus Pattern

---

## Phase 1: UI-Grundlagen (Dropdown + State)

### 1.1 Neue State-Variablen in `aifred/state.py`

**Persistente Variablen** (werden in settings.json gespeichert):
```python
# Multi-Agent Settings - PERSISTENT (nach Zeile ~313)
multi_agent_mode: str = "standard"  # "standard", "user_judge", "auto_consensus", "devils_advocate"
max_debate_rounds: int = 3          # Maximum Runden (UI-konfigurierbarer Slider, 1-5)
```

**Runtime-Variablen** (werden bei Session-Start zurückgesetzt):
```python
# Multi-Agent Runtime State
sokrates_critique: str = ""         # Aktuelle Kritik/Gegenargumente von Sokrates
sokrates_pro_args: str = ""         # Pro-Argumente (für Devil's Advocate)
sokrates_contra_args: str = ""      # Contra-Argumente (für Devil's Advocate)
show_sokrates_panel: bool = False   # UI-Panel anzeigen?
debate_round: int = 0               # Aktuelle Debattenrunde (für Auto-Consensus)
debate_user_interjection: str = ""  # Gequeuter User-Einwurf während Debate
debate_in_progress: bool = False    # Signalisiert laufende Debate (für UI)
```

### 1.2 Neues Dropdown in `aifred/aifred.py` (Settings Panel)

Position: Im Settings-Panel nach "Forschungsmodus" (ca. Zeile 2050)

```python
# Multi-Agent Mode Dropdown
rx.text("Diskussionsmodus", font_weight="bold"),
rx.select.root(
    rx.select.trigger(placeholder="Modus wählen..."),
    rx.select.content(
        rx.select.item("Standard (nur AIfred)", value="standard"),
        rx.select.item("Kritische Prüfung (AIfred + Sokrates)", value="user_judge"),
        rx.select.item("Auto-Konsens (iterativ)", value="auto_consensus"),
        rx.select.item("Advocatus Diaboli (Pro & Contra)", value="devils_advocate"),
    ),
    value=AIState.multi_agent_mode,
    on_change=AIState.set_multi_agent_mode,
),

# Max Debate Rounds Slider (nur sichtbar wenn nicht "standard")
rx.cond(
    AIState.multi_agent_mode != "standard",
    rx.vstack(
        rx.text(f"Max. Debattenrunden: {AIState.max_debate_rounds}", font_size="0.9em"),
        rx.slider(
            min=1, max=5, step=1,
            value=[AIState.max_debate_rounds],
            on_change=AIState.set_max_debate_rounds,
        ),
        spacing="1",
    ),
),
```

### 1.3 Event Handler in `aifred/state.py`

```python
def set_multi_agent_mode(self, mode: str):
    """Set multi-agent discussion mode"""
    self.multi_agent_mode = mode
    self._save_settings()
    self.add_debug(f"🤖 Diskussionsmodus: {mode}")

def set_max_debate_rounds(self, value: list[int]):
    """Set maximum debate rounds (from slider)"""
    self.max_debate_rounds = value[0]
    self._save_settings()
    self.add_debug(f"🔄 Max. Debattenrunden: {self.max_debate_rounds}")

def queue_user_interjection(self, text: str):
    """Queue user input during active debate"""
    if self.debate_in_progress and text.strip():
        self.debate_user_interjection = text.strip()
        self.add_debug(f"💬 User-Einwurf gequeued: {text[:50]}...")
```

---

## Phase 2: Orchestrator-Modul erstellen

### 2.1 Neues Modul: `aifred/lib/multi_agent.py`

```python
"""
Multi-Agent Debate Orchestrator
AIfred (Main) + Sokrates (Critic)
"""
from dataclasses import dataclass
from typing import List, Dict, Optional, Callable, Awaitable
from .llm_client import LLMClient, LLMOptions

@dataclass
class DebateResult:
    alfred_answer: str           # AIfred's Antwort
    sokrates_critique: str = ""  # Sokrates' Kritik (User-as-Judge, Auto-Consensus)
    sokrates_pro: str = ""       # Pro-Argumente (Devil's Advocate)
    sokrates_contra: str = ""    # Contra-Argumente (Devil's Advocate)
    rounds_used: int = 1         # Anzahl Iterationen (Auto-Consensus)
    consensus_reached: bool = True  # LGTM erreicht?

@dataclass
class DebateContext:
    """Kontext für laufende Debate"""
    query: str
    history: list
    llm_client: LLMClient
    model: str
    options: LLMOptions
    max_rounds: int = 3
    get_user_interjection: Callable[[], str] = None  # Callback für User-Einwürfe

class MultiAgentOrchestrator:
    """Orchestriert AIfred + Sokrates Debate-Patterns"""

    SOKRATES_CRITIC_PROMPT = """Du bist Sokrates, ein scharfsinniger kritischer Denker.
Deine Aufgabe ist es, die Antwort von AIfred kritisch zu prüfen:

1. Identifiziere Schwachstellen, fehlende Aspekte oder Ungenauigkeiten
2. Stelle gezielte Fragen, die zur Verbesserung führen
3. Sei konstruktiv - zeige nicht nur Probleme auf, sondern schlage Verbesserungen vor
4. Wenn die Antwort gut ist, sage "LGTM" (Looks Good To Me)

Antworte prägnant und fokussiert auf die wichtigsten Punkte."""

    SOKRATES_DEVILS_ADVOCATE_PROMPT = """Du bist Sokrates als Advocatus Diaboli.
Deine Aufgabe ist es, eine ausgewogene Analyse zu liefern:

1. **Pro-Argumente**: Stärkste Argumente FÜR die Position/Lösung
2. **Contra-Argumente**: Stärkste Argumente GEGEN die Position/Lösung

Sei fair und gründlich bei beiden Seiten. Nutze dieses Format:

## Pro
- Argument 1
- Argument 2

## Contra
- Argument 1
- Argument 2"""

    async def user_as_judge(self, ctx: DebateContext) -> DebateResult:
        """Pattern A: AIfred antwortet, Sokrates kritisiert, User entscheidet"""

    async def auto_consensus(self, ctx: DebateContext) -> DebateResult:
        """Pattern B: Iteriert bis Konsens (LGTM) oder max Runden

        Prüft nach jeder Runde auf User-Interjection via ctx.get_user_interjection()
        und injiziert diese in die nächste Runde.
        """

    async def devils_advocate(self, ctx: DebateContext) -> DebateResult:
        """Pattern C: Pro + Contra Argumente"""
```

### 2.2 User-Interjection Mechanismus

Der User kann während einer laufenden Debate einen Kommentar einwerfen:

```python
# In state.py - während Debate-Loop:
async def auto_consensus_with_interjection(self, ctx: DebateContext):
    for round_num in range(1, ctx.max_rounds + 1):
        # AIfred antwortet
        alfred_response = await self._call_llm(ctx, role="alfred")

        # Prüfe auf User-Interjection
        user_input = ctx.get_user_interjection()
        if user_input:
            # Injiziere User-Kommentar in Kontext
            ctx.history.append({
                "role": "user",
                "content": f"[Einwurf vom User]: {user_input}"
            })

        # Sokrates kritisiert
        sokrates_response = await self._call_llm(ctx, role="sokrates")

        if "LGTM" in sokrates_response:
            return DebateResult(alfred_response, consensus_reached=True, rounds_used=round_num)

    return DebateResult(alfred_response, consensus_reached=False, rounds_used=ctx.max_rounds)
```

---

## Phase 3: Integration in Message-Flow

### 3.1 Anpassung in `aifred/state.py` - `send_message()`

In der `send_message()` Methode (ca. Zeile 2516) vor dem LLM-Aufruf:

```python
# Multi-Agent Routing
if self.multi_agent_mode != "standard":
    from .lib.multi_agent import MultiAgentOrchestrator
    orchestrator = MultiAgentOrchestrator()

    if self.multi_agent_mode == "user_judge":
        result = await orchestrator.user_as_judge(...)
        self.sokrates_critique = result.sokrates_critique
        self.show_sokrates_panel = True

    elif self.multi_agent_mode == "auto_consensus":
        result = await orchestrator.auto_consensus(...)
        # Final answer nach Konsens

    elif self.multi_agent_mode == "devils_advocate":
        result = await orchestrator.devils_advocate(...)
        self.sokrates_pro_args = result.sokrates_pro
        self.sokrates_contra_args = result.sokrates_contra
        self.show_sokrates_panel = True
else:
    # Standard single-agent flow (existing code)
```

---

## Phase 4: Sokrates UI-Panel

### 4.1 Neues UI-Element in `aifred/aifred.py`

Nach der Chat-Message-Bubble, conditionally anzeigen:

```python
def sokrates_panel() -> rx.Component:
    """Sokrates Kritik/Debate Panel"""
    return rx.cond(
        AIState.show_sokrates_panel,
        rx.box(
            rx.hstack(
                rx.icon("brain", size=20),
                rx.text("Sokrates", font_weight="bold"),
            ),
            rx.cond(
                AIState.multi_agent_mode == "devils_advocate",
                # Pro/Contra Layout
                rx.vstack(
                    rx.box(rx.text("Pro:"), rx.markdown(AIState.sokrates_pro_args)),
                    rx.box(rx.text("Contra:"), rx.markdown(AIState.sokrates_contra_args)),
                ),
                # Kritik Layout
                rx.markdown(AIState.sokrates_critique),
            ),
            # Action Buttons (für User-as-Judge)
            rx.cond(
                AIState.multi_agent_mode == "user_judge",
                rx.hstack(
                    rx.button("Akzeptieren", on_click=AIState.accept_answer),
                    rx.button("Verbessern", on_click=AIState.improve_answer),
                ),
            ),
            style={"background": "#1a1a2e", "border-radius": "8px", "padding": "12px"}
        )
    )
```

---

## Implementierungs-Reihenfolge

### Schritt 1: State + Dropdown (30 min)
- [ ] State-Variablen hinzufügen
- [ ] Event Handler erstellen
- [ ] Dropdown in Settings einbauen
- [ ] Settings-Persistenz

### Schritt 2: multi_agent.py Modul (45 min)
- [ ] Basis-Klassen (DebateResult, MultiAgentOrchestrator)
- [ ] user_as_judge() implementieren
- [ ] devils_advocate() implementieren
- [ ] auto_consensus() implementieren

### Schritt 3: Message-Flow Integration (30 min)
- [ ] Routing in send_message()
- [ ] Streaming-Support für Sokrates
- [ ] Debug-Logging

### Schritt 4: Sokrates UI-Panel (45 min)
- [ ] Panel-Komponente erstellen
- [ ] Styling (passend zum Dark Theme)
- [ ] Action-Buttons (User-as-Judge)
- [ ] Pro/Contra Layout (Devil's Advocate)

### Schritt 5: Testing + Polish (30 min)
- [ ] Alle 4 Modi testen
- [ ] Edge Cases (leere Antworten, Fehler)
- [ ] Debug-Messages verfeinern

---

## Betroffene Dateien

| Datei | Änderungen |
|-------|------------|
| `aifred/state.py` | State-Variablen (persistent + runtime), Event Handler, send_message() Routing |
| `aifred/aifred.py` | Dropdown, Slider, Sokrates-Panel UI |
| `aifred/lib/multi_agent.py` | **NEU** - Orchestrator-Modul |
| `aifred/lib/settings.py` | multi_agent_mode + max_debate_rounds in Save/Load |

---

## Settings-Persistenz (aifred/lib/settings.py)

Neue Felder in `save_settings()` und `load_settings()`:

```python
# In SETTINGS_KEYS oder entsprechender Stelle:
"multi_agent_mode": "standard",    # Default: Standard (nur AIfred)
"max_debate_rounds": 3,            # Default: 3 Runden
```

---

## Rollback-Punkt

Tag: `v0.5.0-pre-multiagent`
```bash
git reset --hard v0.5.0-pre-multiagent
```

---

## Erstellt

Datum: 2024-12-24
Referenz: `docs/research/multi_agent_research_technical.md`
