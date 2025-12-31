# Baseline-Analyse: qwen3:30b-a3b Q8 (3 Runs)

**Testzeitraum:** 2025-12-31, 12:11 - 12:53
**Konfiguration:**
- AIfred: qwen3:30b-a3b-instruct-2507-q8_0
- Sokrates: nemotron-3-nano:30b-a3b-q4_K_M
- Salomo: gpt-oss:120b

**Test-Query:** "Recherchiere, ob wir lieber zum Phantasialand oder in den Heidepark fahren sollen"

**Settings:**
- auto_consensus: true
- majority_threshold: 2/3
- max_debate_rounds: 2

---

## Messergebnisse

| Test | Dauer (s) | Dauer (min) | Browser-Latenz (s) | Messages | Polls |
|------|-----------|-------------|-------------------|----------|-------|
| 002  | 532       | 8:52        | ~153              | 6        | 92    |
| 003  | 465       | 7:45        | ~118              | 6        | 92    |
| 004  | 627       | 10:27       | ~177              | 6        | 124   |
| **Ø** | **541.3** | **9:01**    | **149.3**         | **6**    | **102.7** |

## Statistische Auswertung

### Dauer
- **Mittelwert:** 541.3s (9min 1s)
- **Minimum:** 465s (Test 003)
- **Maximum:** 627s (Test 004)
- **Standardabweichung:** 82.8s
- **Varianz:** ~15.3% (hohe Streuung!)

### Browser-Latenz (bis Message-Pickup)
- **Mittelwert:** 149.3s (~2min 29s)
- **Minimum:** ~118s (Test 003)
- **Maximum:** ~177s (Test 004)
- **Varianz:** ~20% (sehr hohe Streuung!)

## Beobachtungen

### ⚠️ Hohe Varianz
Die Schwankung von **162 Sekunden** (fast 3 Minuten!) zwischen schnellstem (465s) und langsamstem (627s) Run ist erheblich. Mögliche Ursachen:

1. **Browser-Polling-Latenz:** Sehr inkonsistent (118s - 177s)
2. **Systemlast:** GPU-Auslastung durch andere Prozesse?
3. **RAG-Performance:** Websuche-Antwortzeiten variabel?
4. **Modell-Caching:** Warmup-Effekte bei Ollama?

### ✅ Konsistenz
- Alle 3 Tests: **Exakt 6 Messages** (erwartetes Ergebnis)
- Keine Abstürze, keine Fehler
- Multi-Agent-Dialectic läuft stabil durch

### 🐌 Salomo (gpt-oss:120b) als Bottleneck?
- Alle Tests dauern >7 Minuten
- gpt-oss:120b ist mit Abstand das größte Modell
- Vermutlich der Hauptgrund für die lange Gesamtdauer

## Empfehlungen

1. **Phase 3c priorisieren:** Salomo-Modell optimieren (kleineres Modell testen)
2. **Browser-Latenz untersuchen:** Polling-Intervall anpassen? (aktuell 1000ms)
3. **Systemlast monitoren:** GPU-Auslastung während Tests tracken
4. **Mehr Runs:** 5-10 Runs für stabilere Statistik (aktuell zu hohe Varianz)

## Nächste Schritte

Gemäß Testplan:
- **Phase 3a:** AIfred-Modell-Optimierung (mistral-small3.2:24b testen)
- **Phase 3b:** Sokrates-Modell-Optimierung (höhere Quantisierung)
- **Phase 3c:** Salomo-Modell-Optimierung (kleinere Alternative zu 120B!)
