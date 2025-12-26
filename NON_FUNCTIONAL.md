# Non-Functional Branches

This file documents branches that contain experimental or non-functional code.

## feature/preload-thinking-mode

**Status:** Non-functional / Experimental

**Description:**
Alternative implementation approach for the thinking mode preload bug fix. This branch threads the `enable_thinking` parameter through the entire stack (LLMClient → Backend → Ollama) to explicitly disable thinking mode during preload.

**Why non-functional:**
The bug was ultimately fixed with a simpler solution: just removing `num_predict=1` from the preload request in `aifred/backends/ollama.py`. This minimal fix proved to be sufficient and is now in the main branch (v2.10.7).

**Purpose:**
Kept for reference and documentation of the investigation process. May be useful if future issues with thinking mode arise.

**Do not merge** - Use only for reference.
