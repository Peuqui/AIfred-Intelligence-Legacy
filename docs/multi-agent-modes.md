# Multi-Agent Modi

## Übersicht

| Modus | Ablauf | Wer entscheidet? |
|-------|--------|------------------|
| **Standard** | AIfred antwortet | - |
| **Kritische Prüfung** | AIfred → Sokrates | User |
| **Auto-Konsens** | AIfred → Sokrates → Salomo (Loop) | Salomo |
| **Advocatus Diaboli** | AIfred → Sokrates (Pro/Contra) | User |
| **Tribunal** | AIfred ↔ Sokrates (X Runden) → Salomo | Salomo |

---

## 1. Standard

```
User → AIfred antwortet
```

Kein Multi-Agent. AIfred beantwortet die Frage direkt.

---

## 2. Kritische Prüfung (`user_judge`)

```
User → AIfred antwortet → Sokrates kritisiert → STOP
```

- **1 Runde** - kein Loop
- Sokrates liefert Kritik + Alternative
- **User entscheidet** selbst, was er mit dem Feedback macht

---

## 3. Auto-Konsens (`auto_consensus`)

```
Runde 1: User → AIfred → Sokrates → Salomo
Runde 2: AIfred (verbessert) → Sokrates → Salomo
...
Runde N: Salomo sagt "LGTM" → STOP
```

- **Trialog** mit max. X Runden (einstellbar)
- Salomo synthetisiert nach jeder Runde
- **Salomo entscheidet** via LGTM
- AIfred verbessert basierend auf Salomos Feedback

---

## 4. Advocatus Diaboli (`devils_advocate`)

```
User → AIfred antwortet → Sokrates liefert Pro/Contra → STOP
```

- **1 Runde** - kein Loop
- Sokrates analysiert die Frage aus beiden Blickwinkeln
- Eigener Prompt (`devils_advocate.txt`)
- **User entscheidet** selbst

---

## 5. Tribunal (`tribunal`)

```
Runde 1: AIfred → Sokrates kritisiert
Runde 2: AIfred verteidigt → Sokrates kritisiert
...
Runde N: AIfred → Sokrates → Salomo fällt Urteil → STOP
```

- **Debatte** mit max. X Runden (einstellbar)
- Salomo spricht **nur am Ende** (finales Urteil)
- **Salomo urteilt** - keine LGTM-Prüfung, sondern Richterspruch

---

## Prompts pro Modus

| Agent | Standard | Krit. Prüfung | Auto-Konsens | Advocatus | Tribunal |
|-------|----------|---------------|--------------|-----------|----------|
| **AIfred** | `system_minimal` | `system_minimal` | `system_minimal` | `system_minimal` | `system_minimal` |
| **Sokrates** | - | `critic.txt` | `critic.txt` | `devils_advocate.txt` | `critic.txt` |
| **Salomo** | - | - | `mediator.txt` | - | `judge.txt` |

---

## Agenten-Rollen

### AIfred 🎩
- **Rolle:** Butler & Gelehrter
- **Aufgabe:** Beantwortet Fragen, verteidigt/verbessert bei Kritik
- **Prompt:** `prompts/{lang}/aifred/system_minimal.txt`

### Sokrates 🏛️
- **Rolle:** Kritischer Philosoph
- **Aufgabe:** Kritisiert, hinterfragt, liefert Alternativen
- **Prompts:**
  - `prompts/{lang}/sokrates/system_minimal.txt` (Basis-Persönlichkeit)
  - `prompts/{lang}/sokrates/critic.txt` (Kritik-Modus)
  - `prompts/{lang}/sokrates/devils_advocate.txt` (Pro/Contra)

### Salomo 👑
- **Rolle:** Weiser Richter
- **Aufgabe:** Synthetisiert, vermittelt, urteilt
- **Prompts:**
  - `prompts/{lang}/salomo/system_minimal.txt` (Basis-Persönlichkeit)
  - `prompts/{lang}/salomo/mediator.txt` (Auto-Konsens: Synthese)
  - `prompts/{lang}/salomo/judge.txt` (Tribunal: Urteil)
