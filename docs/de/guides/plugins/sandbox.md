# Sandbox Plugin

**Datei:** `aifred/plugins/tools/sandbox.py`

Isolierte Python-Code-Ausführung in einem abgesicherten Subprocess.

## Tools

| Tool | Beschreibung | Tier |
|------|-------------|------|
| `execute_code` | Python-Code ausführen und Ergebnis zurückgeben | WRITE_DATA |

## Features

- **Verfügbare Libraries:** numpy, pandas, matplotlib, plotly, sympy, scipy
- **HTML/JS-Visualisierungen:** Generierte Charts werden als HTML inline dargestellt
- **Timeout-Schutz:** Automatischer Abbruch bei zu langer Laufzeit
- **Isolierter Subprocess:** Code läuft in eigenem Prozess, kein Zugriff auf AIfred-Internals
