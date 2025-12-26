# Adaptive Temperature System

**Version:** 2.10.4+
**Status:** Production
**Module:** `aifred/lib/intent_detector.py`

---

## Overview

AIfred uses an adaptive temperature system that automatically selects the optimal temperature based on query intent. This improves answer quality by using:
- **Low temperature** (0.2) for factual queries → Accurate, deterministic
- **Medium temperature** (0.5) for mixed queries → Balanced
- **High temperature** (0.7) for creative queries → Diverse, imaginative

**Modes:**
- **Auto Mode** (default): AI detects intent and sets temperature automatically
- **Manual Mode**: User controls temperature via slider

---

## Architecture

```
User Query
    ↓
┌─────────────────────────────────────────────┐
│ Temperature Mode Check                      │
│ - Manual: Use user slider value             │
│ - Auto: Continue to intent detection        │
└─────────────────────────────────────────────┘
    ↓ (Auto Mode)
┌─────────────────────────────────────────────┐
│ Intent Detection (Automatik-LLM)            │
│ - Query: "What is 2+2?"                     │
│ - LLM analyzes intent                       │
│ - Response: "FAKTISCH"                      │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│ Temperature Mapping                         │
│ - FAKTISCH → 0.2                            │
│ - GEMISCHT → 0.5                            │
│ - KREATIV → 0.7                             │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│ Main LLM Inference                          │
│ - Model: qwen3:8b                           │
│ - Temperature: 0.2 (factual)                │
│ - Response: "2+2 = 4"                       │
└─────────────────────────────────────────────┘
```

---

## Intent Categories

### FAKTISCH (Factual)
**Temperature: 0.2**

**Characteristics:**
- Queries with definite answers
- Math, science, technical questions
- Historical facts, dates, names
- "What is...?", "How does...work?"

**Examples:**
```
"What is the capital of France?"
→ Intent: FAKTISCH (0.2)
→ Answer: "Paris"

"Calculate the square root of 144"
→ Intent: FAKTISCH (0.2)
→ Answer: "12"

"When was Python created?"
→ Intent: FAKTISCH (0.2)
→ Answer: "1991 by Guido van Rossum"
```

**Why low temperature:**
- Factual questions need accurate, consistent answers
- No creativity required
- Deterministic output preferred

---

### KREATIV (Creative)
**Temperature: 0.7**

**Characteristics:**
- Open-ended questions
- Creative writing, brainstorming
- Opinion-based queries
- "Write a story...", "Generate ideas..."

**Examples:**
```
"Write a short poem about winter"
→ Intent: KREATIV (0.7)
→ Answer: <diverse creative poem>

"Generate 10 startup ideas for AI"
→ Intent: KREATIV (0.7)
→ Answer: <varied innovative suggestions>

"Describe a futuristic city"
→ Intent: KREATIV (0.7)
→ Answer: <imaginative description>
```

**Why high temperature:**
- Creativity benefits from randomness
- Multiple valid answers possible
- Diversity in output desired

---

### GEMISCHT (Mixed)
**Temperature: 0.5**

**Characteristics:**
- Queries combining factual and creative elements
- Explanations requiring examples
- Analysis with interpretation
- "Explain... with examples"

**Examples:**
```
"Explain quantum physics simply"
→ Intent: GEMISCHT (0.5)
→ Answer: <factual concepts + creative analogies>

"Pros and cons of electric cars"
→ Intent: GEMISCHT (0.5)
→ Answer: <factual data + subjective analysis>

"How to learn programming?"
→ Intent: GEMISCHT (0.5)
→ Answer: <factual steps + personalized tips>
```

**Why medium temperature:**
- Balances accuracy and flexibility
- Allows some creativity in explanations
- Not too rigid, not too random

---

## Implementation

### Intent Detection Process

**Step 1: Language Detection**
```python
detected_lang = detect_language(user_query)
# "What is 2+2?" → "EN"
# "Was ist 2+2?" → "DE"
```

**Step 2: Intent Prompt Creation**
```python
prompt = get_intent_detection_prompt(
    user_query=user_query,
    lang=detected_lang
)
# Loads prompt from prompts/de/intent_detection.txt or prompts/en/intent_detection.txt
```

**Step 3: Automatik-LLM Classification**
```python
intent_options = {
    'temperature': 0.2,      # Low temp for consistent classification
    'num_predict': 32,        # Short response ("FAKTISCH" = ~10 tokens)
    'enable_thinking': False  # Fast classification without reasoning
}

response = await llm_client.chat(
    model=automatik_model,  # Small, fast LLM (e.g., qwen3:4b)
    messages=[{'role': 'user', 'content': prompt}],
    options=intent_options
)

intent_raw = response.text  # "FAKTISCH" or "KREATIV" or "GEMISCHT"
```

**Step 4: Intent Parsing**
```python
def parse_intent_from_response(intent_raw: str) -> str:
    """
    Extract intent even if LLM writes extra text
    """
    intent_upper = intent_raw.strip().upper()

    if "FAKTISCH" in intent_upper:
        return "FAKTISCH"
    elif "KREATIV" in intent_upper:
        return "KREATIV"
    elif "GEMISCHT" in intent_upper:
        return "GEMISCHT"
    else:
        # Fallback to safe default
        return "FAKTISCH"
```

**Step 5: Temperature Mapping**
```python
temp_map = {
    "FAKTISCH": 0.2,
    "GEMISCHT": 0.5,
    "KREATIV": 0.7
}

temperature = temp_map[intent]
```

### Mode Selection

**Auto Mode:**
```python
if temperature_mode == "auto":
    # Detect intent
    intent = await detect_query_intent(user_query, automatik_model, llm_client)
    temperature = temp_map[intent]
    log_message(f"🌡️ Temperature: {temperature} (auto, {intent.lower()}, {elapsed}s)")
```

**Manual Mode:**
```python
elif temperature_mode == "manual":
    # Use slider value
    temperature = user_slider_value  # 0.0 - 1.0
    log_message(f"🌡️ Temperature: {temperature} (manual)")
```

---

## Configuration

### Temperature Mapping

**Defined in:** `aifred/state.py`

```python
TEMPERATURE_PRESETS = {
    "FAKTISCH": 0.2,  # Factual queries
    "GEMISCHT": 0.5,  # Mixed queries
    "KREATIV": 0.7    # Creative queries
}
```

**Customization:**
```python
# To change defaults, edit the constants:
FAKTISCH_TEMP = 0.15  # Even more deterministic
GEMISCHT_TEMP = 0.6   # Slightly more creative
KREATIV_TEMP = 0.8    # More randomness
```

### Automatik-LLM Settings

**Model:** Small, fast LLM (e.g., `qwen3:4b`, `gemma3:1b`)

**Purpose:** Intent classification only (not main inference)

**Context:** 4096 tokens (small, fixed)

**Temperature:** 0.2 (consistent classification)

---

## User Interface

### Settings Panel

```
┌─────────────────────────────────────────────┐
│ Temperature Control                         │
│ ┌─────────────────────────────────────────┐ │
│ │ ● Auto (Intent-based)                   │ │
│ │ ○ Manual (Slider)                       │ │
│ └─────────────────────────────────────────┘ │
│                                             │
│ Manual Temperature: [====    ] 0.7          │
│ (Only active in Manual mode)                │
└─────────────────────────────────────────────┘
```

### Debug Output

**Auto Mode:**
```
🎯 Intent detection running...
🌐 Language detection: User input is probably 'DE' (for prompt selection)
🎯 Intent detection for query: Was ist 2+2?...
🧠 Intent enable_thinking: False (Automatik-Task)
✅ Intent detected: FAKTISCH
🌡️ Temperature: 0.2 (auto, factual, 0.4s)
```

**Manual Mode:**
```
🌡️ Temperature: 0.6 (manual)
```

---

## Performance

### Intent Detection Speed

**Typical latency:**
```
Automatik-LLM: qwen3:4b-instruct-2507-q4_K_M
Hardware: 2x Tesla P40
Response time: 0.3-0.5s
```

**Token usage:**
```
Prompt: ~150 tokens (intent detection template)
Response: ~10 tokens ("FAKTISCH" or similar)
Total: ~160 tokens per classification
```

### Overhead

**Auto Mode:**
- Extra inference: 1x Automatik-LLM call
- Time: +0.3-0.5s per query
- Benefit: Optimized temperature for better quality

**Manual Mode:**
- Extra inference: None
- Time: No overhead
- Benefit: User control, faster

**Tradeoff:**
```
Auto Mode: +0.5s overhead → Better answer quality
Manual Mode: No overhead → Faster, but suboptimal temperature
```

---

## Examples

### Example 1: Factual Query

**Input:**
```
User: "What is the speed of light?"
Mode: Auto
```

**Process:**
```
1. Intent detection (0.4s)
   → Language: EN
   → Intent: FAKTISCH
   → Temperature: 0.2

2. Main inference (3.2s)
   → Model: qwen3:8b
   → Temp: 0.2 (factual)
   → Response: "The speed of light in vacuum is approximately
                299,792,458 meters per second (299,792 km/s)."
```

**Result:** Precise, consistent answer ✅

---

### Example 2: Creative Query

**Input:**
```
User: "Write a haiku about coding"
Mode: Auto
```

**Process:**
```
1. Intent detection (0.3s)
   → Language: EN
   → Intent: KREATIV
   → Temperature: 0.7

2. Main inference (4.1s)
   → Model: qwen3:8b
   → Temp: 0.7 (creative)
   → Response: "Code flows like water,
                Bugs dance in moonlit screens,
                Compile, then release."
```

**Result:** Diverse, creative poem ✅

---

### Example 3: Mixed Query

**Input:**
```
User: "Explain recursion with a real-world example"
Mode: Auto
```

**Process:**
```
1. Intent detection (0.4s)
   → Language: EN
   → Intent: GEMISCHT
   → Temperature: 0.5

2. Main inference (8.3s)
   → Model: qwen3:8b
   → Temp: 0.5 (balanced)
   → Response: "Recursion is when a function calls itself.
                Imagine Russian nesting dolls: each doll contains
                a smaller version until you reach the tiniest one..."
```

**Result:** Factual explanation + creative analogy ✅

---

### Example 4: Manual Override

**Input:**
```
User: "Explain quantum physics"
Mode: Manual (temp=0.9)
```

**Process:**
```
1. Intent detection: SKIPPED (manual mode)

2. Main inference (7.5s)
   → Model: qwen3:8b
   → Temp: 0.9 (user-defined, high)
   → Response: <very creative, diverse explanation with unusual analogies>
```

**Result:** User-controlled creativity ✅

---

## Limitations

1. **Intent Misclassification**
   - Automatik-LLM can misinterpret ambiguous queries
   - Fallback: FAKTISCH (safe default)
   - Example: "Tell me about AI" could be FAKTISCH or GEMISCHT

2. **Latency Overhead**
   - Auto mode adds 0.3-0.5s per query
   - Not significant for most use cases
   - Can be disabled via Manual mode

3. **Fixed Temperature Presets**
   - Only 3 temperature values (0.2, 0.5, 0.7)
   - No fine-grained auto-tuning
   - Manual mode required for custom temperatures

4. **No Context-Aware Adaptation**
   - Intent detection only looks at current query
   - Doesn't consider conversation history
   - Follow-up questions may get wrong temperature

---

## Best Practices

### When to use Auto Mode

**Use Auto if:**
- ✅ You have diverse query types
- ✅ You want optimal quality without manual tuning
- ✅ Latency overhead (+0.5s) is acceptable
- ✅ You trust AI to classify correctly

**Example scenarios:**
- General assistant usage
- Educational queries
- Mixed factual/creative workflows

### When to use Manual Mode

**Use Manual if:**
- ✅ You know the optimal temperature for your task
- ✅ You need faster responses (no intent detection)
- ✅ All queries are same type (e.g., all creative)
- ✅ You're doing performance benchmarks

**Example scenarios:**
- Creative writing sessions (temp=0.7)
- Factual research (temp=0.2)
- Code generation (temp=0.3-0.4)

---

## Troubleshooting

### Wrong temperature selected

**Symptom:**
```
Query: "Write a creative story"
Intent: FAKTISCH (wrong!)
Temperature: 0.2
→ Boring, repetitive story
```

**Fix:**
1. Check intent detection prompt (may need improvement)
2. Use Manual mode for that session
3. Report misclassification (helps improve prompts)

### Intent detection too slow

**Symptom:**
```
Intent detection: 2.0s (too long)
```

**Cause:**
- Large Automatik-LLM model
- Slow hardware
- High num_predict setting

**Fix:**
```python
# Use smaller Automatik model
automatik_model = "gemma3:1b"  # Instead of qwen3:4b

# Reduce num_predict
num_predict = 16  # Instead of 32
```

---

## Related Documentation

- [LLM_PARAMETERS.md](LLM_PARAMETERS.md) - All LLM parameters explained
- [../development/PRE_COMMIT_CHECKLIST.md](../development/PRE_COMMIT_CHECKLIST.md) - Testing temperature system
- [../architecture/ARCHITECTURE.md](../architecture/ARCHITECTURE.md) - Overall system architecture

---

## Changelog

**v2.10.4** (Dec 2025)
- Refactored temperature system
- Separated into Auto/Manual modes
- Improved intent detection prompts

**v2.10.0** (Nov 2025)
- Initial adaptive temperature implementation

---

**Last Updated:** 2025-12-26
**Maintainer:** AIfred Intelligence Team
