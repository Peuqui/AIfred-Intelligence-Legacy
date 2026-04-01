# Sandbox Plugin

**File:** `aifred/plugins/tools/sandbox.py`

Isolated Python code execution in a sandboxed subprocess.

## Tools

| Tool | Description | Tier |
|------|------------|------|
| `execute_code` | Execute Python code and return result | WRITE_DATA |

## Features

- **Available libraries:** numpy, pandas, matplotlib, plotly, sympy, scipy
- **HTML/JS visualizations:** Generated charts are rendered as inline HTML
- **Timeout protection:** Automatic termination on excessive runtime
- **Isolated subprocess:** Code runs in its own process, no access to AIfred internals
