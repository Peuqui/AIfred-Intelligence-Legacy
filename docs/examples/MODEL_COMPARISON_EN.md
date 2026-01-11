# LLM Model Comparison: Performance and Quality Analysis

This comparison analyzes various local LLM models regarding inference performance, token efficiency, and linguistic quality in the AIfred Butler style.

## Test Environment

- **Hardware:** 2x Tesla P40 (48 GB VRAM total)
- **Backend:** Ollama
- **Test Question:** "Was ist Pervitin und warum heißt es so?" (What is Pervitin and why is it called that?)
- **Expected Style:** British butler, formal, polite, dry humor, English expressions sprinkled in

## Models Tested

| Model | Size | Thinking Mode |
|-------|------|---------------|
| qwen3:30b-instruct | 30B | No |
| qwen3:30b-thinking | 30B | Yes (native) |
| mannix/qwen2-57b | 57B | No |
| qwen3-next:80b | 80B | No |
| gpt-oss:120b | 120B | Yes (native) |

---

## Performance Comparison

### Web Research Mode

| Model | TTFT | Inference | tok/s | Total Tokens |
|-------|------|-----------|-------|--------------|
| qwen3:30b-instruct | 16.4s | 73.2s | 21.9 | ~1,602 |
| qwen3:30b-thinking | 37.9s | 99.2s | 25.9 | ~2,569 |
| mannix/qwen2-57b | 19.4s | 47.2s | 20.1 | ~960 |
| qwen3-next:80b | 61.3s | 218.1s | 8.1 | ~1,756 |
| gpt-oss:120b (T1) | 90.7s | 223.3s | 10.4 | ~2,320 |
| gpt-oss:120b (T2) | 179.9s | 315.6s | 9.0 | ~2,855 |

**Legend:**
- **TTFT:** Time to First Token (latency until first output)
- **Inference:** Total response time
- **tok/s:** Tokens per second
- **T1/T2:** Different test runs

---

## Token Efficiency Analysis

For models with thinking mode, a significant portion of generated tokens is dedicated to the internal reasoning process and does not appear in the visible response.

### Thinking vs. Useful Tokens

| Model | Thinking | Total tok | Think tok | Answer tok | Useful % | Eff. tok/s |
|-------|----------|-----------|-----------|------------|----------|------------|
| qwen3:30b-instruct | No | ~1,602 | 0 | ~455 | 100% | 6.2 |
| qwen3:30b-thinking | Yes | ~2,569 | ~1,240 | ~369 | 14% | 3.7 |
| mannix/qwen2-57b | No | ~960 | 0 | ~319 | 100% | 6.8 |
| qwen3-next:80b | No | ~1,756 | 0 | ~538 | 100% | 2.5 |
| gpt-oss:120b (T1) | Yes | ~2,320 | ~422 | ~352 | 15% | 1.6 |
| gpt-oss:120b (T2) | Yes | ~2,855 | ~406 | ~384 | 13% | 1.2 |

**Key Insights:**
- Thinking models generate 6-7x more tokens than visible in the answer
- Effective token rate (answer tokens only / time) is significantly lower for thinking models
- Non-thinking models are more efficient for equivalent answer lengths

---

## Quality Analysis

### Evaluation Criteria

| Criterion | Description |
|-----------|-------------|
| Butler Style | British-formal speech patterns |
| Address | Correct use of "Herr Peuqui" (user's name) |
| English | Sprinkled English expressions (indeed, rather, quite) |
| Humor | Dry, subtle British humor |
| Depth | Content completeness and accuracy |
| Sources | Citations and references |
| Elegance | Linguistic elegance and readability |
| Structure | Markdown formatting, tables, lists |

### Rating Overview

| Model | Butler | Address | English | Humor | Depth | Sources | Elegance | Structure | Total |
|-------|--------|---------|---------|-------|-------|---------|----------|-----------|-------|
| qwen3-next:80b | 3/3 | Yes | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | **24/24** |
| qwen3:30b-instruct | 3/3 | Yes | 2/3 | 2/3 | 3/3 | 3/3 | 3/3 | 3/3 | **22/24** |
| gpt-oss:120b | 2/3 | Yes | 2/3 | 2/3 | 3/3 | 3/3 | 2/3 | 3/3 | **20/24** |
| qwen3:30b-thinking | 2/3 | Yes | 1/3 | 1/3 | 3/3 | 3/3 | 2/3 | 3/3 | **18/24** |
| mannix/qwen2-57b | 1/3 | No | 0/3 | 0/3 | 2/3 | 2/3 | 1/3 | 1/3 | **8/24** |

---

## Detailed Analysis per Model

### qwen3-next:80b - Excellent

**Strengths:**
- Perfect butler style with natural English expressions
- Outstanding dry humor ("a rather spirited approach to pharmacology")
- First-class Markdown structure with tables and lists
- Comprehensive historical depth

**Example Quote:**
> "The Wehrmacht's pharmacological enthusiasm, one might observe, was rather spirited – a phrase that assumes new meaning when applied to methamphetamine distribution."

**Verdict:** Best linguistic quality of all tested models.

---

### qwen3:30b-instruct - Very Good

**Strengths:**
- Solid butler style
- Good balance between formality and readability
- Structured response with clear sections
- Fast inference

**Example Quote:**
> "Pervitin ist, indeed, ein bemerkenswertes Kapitel der Pharmaziegeschichte, das man durchaus als 'energetisch' bezeichnen könnte."

**Verdict:** Best balance between quality and speed.

---

### gpt-oss:120b - Good

**Strengths:**
- Excellent factual depth and historical details
- Good source integration
- Comprehensive tabular presentation

**Weaknesses:**
- Butler style somewhat stiff
- Humor more restrained
- Very slow inference

**Example Quote:**
> "Der Name leitet sich von dem lateinischen Wort 'pervīvus' ab, was so viel bedeutet wie ausdauernd – ein durchaus ambitioniertes Werbeversprechen, indeed."

**Verdict:** Maximum factual depth, but slow.

---

### qwen3:30b-thinking - Good

**Strengths:**
- Visible thinking process useful for debugging
- Factually correct

**Weaknesses:**
- Butler style less pronounced
- Less humor and elegance than non-thinking variant
- Token overhead from thinking block

**Verdict:** Useful when reasoning transparency matters.

---

### mannix/qwen2-57b - Poor

**Weaknesses:**
- Almost completely ignores butler style instructions
- No English expressions
- No humor
- Missing correct address
- Factually speculative in parts

**Example Quote:**
> "Die Bezeichnung 'Pervitin' ist eine Kombination aus den Wörtern 'per' und 'vitamin'."
> *(Unsourced and likely incorrect)*

**Verdict:** Not suitable for AIfred style.

---

## Overall Ranking

| Rank | Model | Style | Speed | Recommendation |
|------|-------|-------|-------|----------------|
| 1st | qwen3-next:80b | Excellent | Slow | Best quality when time is not a concern |
| 2nd | qwen3:30b-instruct | Very Good | Fast | **Best balance for everyday use** |
| 3rd | gpt-oss:120b | Good | Very Slow | Maximum factual depth for complex questions |
| 4th | qwen3:30b-thinking | Good | Medium | When reasoning transparency is important |
| 5th | mannix/qwen2-57b | Poor | Fast | Not recommended for butler style |

---

## Conclusion

For the AIfred butler style, we recommend:

1. **Standard Operation:** `qwen3:30b-instruct` - Best balance of quality and speed
2. **Maximum Quality:** `qwen3-next:80b` - When time is not a concern
3. **Complex Research:** `gpt-oss:120b` - For deep factual analyses

Thinking models offer transparent reasoning processes but significantly increase token consumption without proportional quality improvement in butler-style output.
