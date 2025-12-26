# Multi-Agent Debate System

**Version:** 2.10+
**Status:** Production
**Module:** `aifred/lib/multi_agent.py`

---

## Overview

AIfred Intelligence implements a multi-agent debate system featuring two LLM agents:
- **AIfred**: Primary agent providing answers
- **Sokrates**: Critical thinker providing analysis, critique, and refinement

This system improves answer quality through dialectical discussion, enabling critical evaluation and iterative refinement.

---

## Architecture

### Core Components

```
User Input
    ↓
┌─────────────────────────────────────────────┐
│ Intent Detection & Mode Selection          │
│ - Direct addressing detection               │
│ - Mode selection (Standard/Review/etc.)     │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│ AIfred (Primary Agent)                      │
│ - Main LLM with system prompt               │
│ - Full context + history                    │
│ - Thinking mode support (Qwen3)             │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│ Sokrates (Critic Agent)                     │
│ - Same or different LLM                     │
│ - Critical system prompt                    │
│ - Receives AIfred's answer + context        │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│ Synthesis & Presentation                    │
│ - LGTM detection (Auto-Consensus)           │
│ - Pro/Contra parsing (Devil's Advocate)     │
│ - Round management                          │
└─────────────────────────────────────────────┘
```

### Model Assignment

**AIfred:**
- Uses `main_model` from settings
- Can be any LLM (Qwen3, Gemma3, Llama, etc.)
- Supports thinking mode if model capable

**Sokrates:**
- Uses `sokrates_model` from settings (optional)
- Defaults to `main_model` if not specified
- Typically uses same model with different temperature (0.4 vs 0.2)

---

## Discussion Modes

### 1. Standard Mode
**Default behavior** - No multi-agent discussion

```
User → AIfred → User
```

**Use case:** Quick queries, simple answers, when critique is not needed

---

### 2. Critical Review Mode
**AIfred answers, Sokrates critiques, User decides**

```
User → AIfred → Sokrates (critique) → User (judges)
```

**Sokrates receives:**
- User's original question
- AIfred's complete answer
- Context: "Provide critical analysis"

**Sokrates provides:**
- Strengths and weaknesses
- Factual accuracy check
- Missing perspectives
- Recommendations for improvement

**Output:**
- AIfred's answer displayed first
- Sokrates' critique in collapsible section
- User manually decides whether to iterate

**Use case:** Important decisions, fact-checking, balanced perspective

---

### 3. Auto-Consensus Mode
**Iterative refinement until agreement or max rounds**

```
Round 1: User → AIfred → Sokrates (critique) → AIfred (synthesis)
Round 2: Sokrates (critique) → AIfred (synthesis)
...
Until: Sokrates says "LGTM" or max_rounds reached
```

**LGTM Detection:**
- Sokrates analyzes AIfred's synthesis
- If satisfied, includes "LGTM" (case-insensitive) in response
- Triggers immediate consensus and ends debate

**Round Limit:**
- Configurable via `max_debate_rounds` (default: 2)
- Range: 1-3 rounds
- Prevents infinite loops

**Synthesis Process:**
1. AIfred receives:
   - Previous answer
   - Sokrates' critique (Antithesis)
   - Task: Create improved synthesis
2. AIfred produces refined answer
3. Loop continues until consensus

**Use case:** Complex questions requiring refinement, philosophical discussions

---

### 4. Devil's Advocate Mode
**Balanced Pro & Contra arguments**

```
User → AIfred → Sokrates (Pro/Contra) → User
```

**Sokrates provides:**
- **Pro arguments:** Supporting AIfred's position
- **Contra arguments:** Challenging AIfred's position

**UI Presentation:**
- AIfred's answer
- Collapsible "Pro Arguments" section (green)
- Collapsible "Contra Arguments" section (red)

**Parsing Logic:**
```python
# Sokrates must structure response with markers:
## Pro
<arguments supporting AIfred>

## Contra
<arguments challenging AIfred>
```

**Use case:** Controversial topics, balanced analysis, decision-making

---

## Direct Agent Addressing

**Feature:** Users can directly address specific agents

### Detection Patterns

**Start of sentence:**
```
"Sokrates, what do you think about quantum computing?"
"AIfred, explain the multiverse theory."
```

**End of sentence:**
```
"What is the meaning of life? Sokrates."
"Explain this code. Alfred."
```

**STT Variants** (Speech-to-Text tolerance):
- "Alfred" / "Eifred" / "AI Fred" → AIfred
- "Sokrates" / "Socrates" → Sokrates

### Behavior

**When Sokrates is addressed:**
- Bypass AIfred entirely
- Sokrates answers directly using Socratic method
- Prompt: `get_sokrates_direct_prompt()`
- No multi-agent discussion
- Uses critical questioning approach

**When AIfred is addressed:**
- Bypass Sokrates
- AIfred answers in Standard mode
- No critique/analysis
- Single-turn response

**When neither is addressed:**
- Respect selected `multi_agent_mode` setting
- Default behavior based on mode

---

## Implementation Details

### State Variables

**Persistent (saved in settings.json):**
```python
multi_agent_mode: str = "standard"  # "standard" | "user_judge" | "auto_consensus" | "devils_advocate"
max_debate_rounds: int = 2          # 1-3 rounds for Auto-Consensus
sokrates_model: str = ""            # Optional, defaults to main_model if empty
```

**Runtime (reset per session):**
```python
debate_in_progress: bool = False    # Prevents concurrent debates
sokrates_temp: float = 0.4          # Higher than AIfred (0.2) for diversity
```

### Message History Structure

**AIfred's message:**
```python
{
    "role": "assistant",
    "content": "<aifred>...</aifred>",
    "thinking": "..." (if thinking mode enabled)
}
```

**Sokrates' message:**
```python
{
    "role": "assistant",
    "content": "<sokrates_critique>...</sokrates_critique>",  # Critical Review
    # OR
    "content": "<sokrates_pro>...</sokrates_pro><sokrates_contra>...</sokrates_contra>"  # Devil's Advocate
}
```

**Synthesis (Auto-Consensus):**
```python
{
    "role": "assistant",
    "content": "<aifred_synthesis>...</aifred_synthesis>"
}
```

### Context Management

**Sokrates receives:**
- User's original question
- AIfred's complete response (stripped of `<think>` tags)
- Mode-specific prompt
- Shared history context

**Context limits:**
- AIfred and Sokrates can have different `num_ctx` values
- Calculated independently based on model and VRAM
- Compression applies to both agents' contexts

---

## System Prompts

Located in `prompts/de/` and `prompts/en/`:

**AIfred:**
- `systemPrompt.txt` - General assistant
- `systemPrompt_factual.txt` - Factual queries
- `systemPrompt_creative.txt` - Creative tasks

**Sokrates:**
- `sokrates_system_minimal.txt` - Base system prompt
- `sokrates_direct_prompt.txt` - Direct addressing
- `sokrates_critic_prompt.txt` - Critical Review mode
- `sokrates_devils_advocate_prompt.txt` - Devil's Advocate mode
- `sokrates_refinement_prompt.txt` - Auto-Consensus synthesis request

---

## UI Components

### Settings Panel

```
┌─────────────────────────────────────────────┐
│ Multi-Agent Discussion Mode                │
│ ┌─────────────────────────────────────────┐ │
│ │ ○ Standard (AIfred only)                │ │
│ │ ○ Critical Review (Sokrates critiques)  │ │
│ │ ○ Auto-Consensus (iterative until LGTM) │ │
│ │ ○ Devil's Advocate (Pro & Contra)       │ │
│ └─────────────────────────────────────────┘ │
│                                             │
│ Max Debate Rounds: [2] (1-3)                │
│                                             │
│ Sokrates Model: [Use Main Model ▾]         │
└─────────────────────────────────────────────┘
```

### Output Rendering

**Critical Review:**
```
┌─────────────────────────────────────────────┐
│ 🤖 AIfred                                   │
│ <answer>                                    │
└─────────────────────────────────────────────┘
┌─────────────────────────────────────────────┐
│ 🏛️ Sokrates - Critical Analysis ▾          │
│ <critique>                                  │
└─────────────────────────────────────────────┘
```

**Auto-Consensus:**
```
┌─────────────────────────────────────────────┐
│ 🤖 AIfred (Round 1)                         │
│ <initial answer>                            │
└─────────────────────────────────────────────┘
┌─────────────────────────────────────────────┐
│ 🏛️ Sokrates (Round 1) ▾                     │
│ <critique>                                  │
└─────────────────────────────────────────────┘
┌─────────────────────────────────────────────┐
│ 🤖 AIfred - Synthesis (Round 2)             │
│ <improved answer>                           │
└─────────────────────────────────────────────┘
┌─────────────────────────────────────────────┐
│ 🏛️ Sokrates (Round 2) ▾                     │
│ LGTM - Consensus reached ✅                 │
└─────────────────────────────────────────────┘
```

**Devil's Advocate:**
```
┌─────────────────────────────────────────────┐
│ 🤖 AIfred                                   │
│ <answer>                                    │
└─────────────────────────────────────────────┘
┌─────────────────────────────────────────────┐
│ ✅ Pro Arguments ▾                          │
│ <supporting arguments>                      │
└─────────────────────────────────────────────┘
┌─────────────────────────────────────────────┐
│ ❌ Contra Arguments ▾                       │
│ <challenging arguments>                     │
└─────────────────────────────────────────────┘
```

---

## Performance Considerations

### VRAM Usage

**Standard Mode:**
- 1x model loaded (AIfred)

**Multi-Agent Modes:**
- 2x model loads if different models
- 1x model if same model (shared VRAM)
- Context switching incurs latency (~2s per switch on Ollama)

### Latency

**Typical Response Times** (2x Tesla P40, Qwen3:8B):
- Standard: 5-10s
- Critical Review: 15-20s (2 inferences)
- Auto-Consensus (2 rounds): 30-45s (4 inferences)
- Devil's Advocate: 15-20s (2 inferences)

### Token Usage

**Per round:**
- AIfred: ~500-2000 tokens (depending on complexity)
- Sokrates: ~300-800 tokens (critique is typically shorter)
- Synthesis: ~800-3000 tokens (combines both perspectives)

**Context overhead:**
- Each round adds previous messages to context
- Compression triggers at 70% of num_ctx
- Auto-Consensus can accumulate significant history

---

## Configuration Examples

### Example 1: Fast Critical Review
```python
# settings.json
{
    "multi_agent_mode": "user_judge",
    "main_model": "qwen3:8b",
    "sokrates_model": "",  # Use same model
    "max_debate_rounds": 1
}
```
**Result:** Quick 2-turn dialogue (AIfred + Sokrates)

### Example 2: Deep Philosophical Analysis
```python
{
    "multi_agent_mode": "auto_consensus",
    "main_model": "qwen3:32b",
    "sokrates_model": "qwen3:32b",
    "max_debate_rounds": 3
}
```
**Result:** Up to 6 inferences for thorough refinement

### Example 3: Lightweight Debate
```python
{
    "multi_agent_mode": "devils_advocate",
    "main_model": "gemma3:1b",  # Fast, lightweight
    "sokrates_model": "gemma3:1b",
    "max_debate_rounds": 1
}
```
**Result:** Quick balanced analysis on low-end hardware

---

## Debug Output

**Log markers:**
```
🤖 Multi-Agent: <mode>
🏛️ Sokrates-LLM: <model> (<size>)
📊 Context limits: AIfred=<N>, Sokrates=<N>
🌡️ Temps: AIfred=0.2, Sokrates=0.4
✅ Consensus reached in round <N> (LGTM)
⚠️ Debate finished: max <N> rounds without consensus
```

**Example log:**
```
17:05:14.044 | 🏛️ Sokrates-LLM: gemma3:1b (0.8 GB)
17:05:16.226 | 📊 Context limits: AIfred=32.768, Sokrates=32.768, Compression=32.768
17:05:16.226 | 🌡️ Temps: AIfred=0.2, Sokrates=0.4
17:05:21.765 | ✅ Consensus reached in round 1 (LGTM)
17:05:21.765 | 🎯 Debate finished: consensus after 1 rounds
```

---

## Best Practices

### When to use each mode:

**Standard:**
- Quick queries
- Factual lookups
- When you trust AIfred's judgment

**Critical Review:**
- Important decisions
- Fact-checking needed
- Second opinion desired
- Educational contexts (seeing critique process)

**Auto-Consensus:**
- Complex philosophical questions
- Nuanced topics requiring refinement
- When initial answer may be incomplete
- Iterative improvement desired

**Devil's Advocate:**
- Controversial topics
- Balanced perspective needed
- Decision-making with trade-offs
- Exploring both sides of an argument

### Direct Addressing:

**Use "Sokrates, ..."** when:
- You want Socratic questioning
- Probing deeper understanding
- Challenging your assumptions
- No initial answer needed

**Use "AIfred, ..."** when:
- Bypassing debate for speed
- Simple informational query
- Multi-agent mode enabled but not desired for this query

---

## Limitations

1. **No cross-backend debate:** AIfred and Sokrates must use same backend (can't mix Ollama + vLLM)
2. **Sequential execution:** Inferences run one after another, no true parallelism
3. **Context accumulation:** Long debates can hit context limits quickly
4. **LGTM brittleness:** Sokrates must explicitly write "LGTM" - paraphrases won't trigger consensus
5. **No backtracking:** Once a round completes, can't go back to revise

---

## Future Enhancements

**Planned:**
- [ ] Separate Sokrates backend (Ollama for AIfred, vLLM for Sokrates)
- [ ] Voice differentiation for TTS (different voices for agents)
- [ ] Debate history visualization (tree view of refinements)
- [ ] Custom agent personalities (beyond AIfred/Sokrates)
- [ ] Multi-agent memory (agents remember past debates)

**Under consideration:**
- [ ] 3+ agent debates (Thesis, Antithesis, Synthesis, Synthesis2)
- [ ] Parallel agent execution (if models fit in VRAM)
- [ ] Agent voting (multiple Sokrates instances vote on best answer)
- [ ] Human-in-the-loop during debate (user can inject feedback mid-debate)

---

## Related Documentation

- [ARCHITECTURE.md](../ARCHITECTURE.md) - Overall system architecture
- [CACHE_SYSTEM.md](CACHE_SYSTEM.md) - History compression and context management
- [ollama-context-calculation.md](ollama-context-calculation.md) - Context window optimization
- [../llm/LLM_PARAMETERS.md](../llm/LLM_PARAMETERS.md) - Temperature and generation parameters
- [../development/PRE_COMMIT_CHECKLIST.md](../development/PRE_COMMIT_CHECKLIST.md) - Testing multi-agent features

---

## Changelog

**v2.10.6** (Dec 2025)
- Fixed LGTM consensus detection in Auto-Consensus mode
- Added collapsible UI for Sokrates responses

**v2.10.0** (Nov 2025)
- Initial Multi-Agent implementation
- Extracted from state.py to separate module
- Added direct agent addressing
- Implemented all 4 modes

---

**Last Updated:** 2025-12-26
**Maintainer:** AIfred Intelligence Team
