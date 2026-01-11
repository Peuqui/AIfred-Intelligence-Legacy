# AIfred TODO

## KRITISCH (Höchste Priorität)

### Base64-Bilder in LLM-History
- **Problem:** Bilder werden als Base64 in `llm_history` gespeichert und in Session-Dateien persistiert
- **Auswirkung:** Session-Dateien werden riesig (2+ MB), Browser wird unresponsive
- **Lösung:**
  - Base64-Bilder NICHT in `llm_history` speichern
  - Stattdessen: Referenz/Marker speichern (z.B. `[IMG:uploaded_123.jpg]`)
  - Oder: Bilder separat speichern und nur Pfad referenzieren
- **Betroffene Dateien:**
  - `aifred/lib/conversation_handler.py` (Multimodal-Pfad)
  - `aifred/lib/message_builder.py`
  - Session-Storage

---

## Offen

### KoboldCPP Support - Evaluierung

**Frage:** Sollen wir KoboldCPP weiterhin unterstützen?

**Recherche-Ergebnis (Januar 2026):**

| Aspekt | Ollama | KoboldCPP |
|--------|--------|-----------|
| **Setup** | Einfach (1-Befehl) | Technischer |
| **Performance** | Gut | ~27% schneller (llama.cpp Basis) |
| **Sampling Options** | Begrenzt | Mehr Optionen (DRY, etc.) |
| **Large Context** | Probleme bei 64-80K | Besser optimiert |
| **Community** | 144k GitHub Stars | Kleiner, spezialisiert |
| **Multi-GPU** | Basis | Besser |
| **Use Case** | Allgemein, API-first | Storytelling, Roleplay |

**Pro KoboldCPP behalten:**
- Bessere Performance bei großen Kontexten
- Mehr Sampling-Optionen
- Einige User haben es bereits konfiguriert

**Contra KoboldCPP behalten:**
- Wartungsaufwand für zwei Backends
- Ollama deckt 95% der Use-Cases ab
- KoboldCPP primär für Storytelling/Roleplay (nicht AIfred's Fokus)

**Entscheidung:** Erstmal behalten, später eigene Benchmarks machen

**Nächste Schritte:**
- [ ] Eigener Vergleich: Gleiches Modell + Quant auf beiden Backends
- [ ] Messen: TTFT, tok/s, Model Loading Zeit
- [ ] Besonders interessant bei Multi-Agent (häufiges Model Loading)

---

### Vision-LLM Pfad verbessern

**Problem:** Der Vision-LLM Pfad funktioniert nicht zuverlässig
- Base64-Bilder in History (siehe oben)
- Inkonsistente JSON-Ausgabe
- Komplexe 3-Model-Architektur

**Mögliche Lösungen:**
- [ ] Vereinfachung der Pipeline
- [ ] Bessere Error-Handling
- [ ] Alternative: Direkte Multimodal-Antwort ohne JSON-Extraktion

---

### Direkter llama.cpp Zugang - Evaluierung

**Frage:** Sollten wir llama-server oder llama-cpp-python direkt nutzen statt Ollama/KoboldCPP?

**Hintergrund:**
- Ollama und KoboldCPP sind Wrapper um llama.cpp
- Jeder Wrapper hat Overhead (API-Layer, zusätzliche Abstraktion)
- Bei großen Modellen mit CPU-Offloading zählt jedes Quäntchen Geschwindigkeit
- Multi-Agent = häufiges Model-Loading → Overhead multipliziert sich

**Optionen:**

| Variante | Typ | Vorteil | Nachteil |
|----------|-----|---------|----------|
| **llama-server** | HTTP API (C++) | Minimaler Overhead, direkt von llama.cpp | Weniger Features als Ollama |
| **llama-cpp-python** | Python Bindings | Kein HTTP-Overhead, direkter Speicherzugriff | Mehr Setup, Python GIL |

**Nächste Schritte:**
- [ ] Benchmark: Ollama vs llama-server vs llama-cpp-python
- [ ] Messen: TTFT, tok/s, Prompt Processing, Model Loading
- [ ] Besonders bei CPU-Offloading testen (dort ist Overhead am spürbarsten)
- [ ] Prüfen: Wie schwer wäre ein neues Backend zu implementieren?

---

### Dual-Backend für parallele Agenten (Brainstorm)

**Idee:** WSL (RTX 3090 Ti) + MiniPC (2x P40) parallel nutzen

**Mögliche Agenten:**
- Research-Agent (3090 Ti) - schnelle Web-Recherche parallel zu AIfred
- Validator-Agent (3090 Ti) - Faktencheck parallel zu Sokrates
- Code-Executor (3090 Ti) - Linting/Tests parallel

**Status:** Brainstorm-Phase, noch nicht priorisiert
