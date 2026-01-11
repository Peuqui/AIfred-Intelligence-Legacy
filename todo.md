# AIfred TODO

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

---

## Erledigt

### ~~Base64-Bilder in LLM-History~~ ✅
- Bilder werden jetzt als `[IMG:filename]` Marker gespeichert statt Base64
- Session-Dateien bleiben klein

### ~~Einheitliche History-Aufbereitung~~ ✅
- Zentrale Funktion `build_messages_from_llm_history()` in message_builder.py
- Alle Pfade (RAG Bypass, Own Knowledge, Multi-Agent) nutzen dieselbe Funktion
- Labels bleiben erhalten, Rollen werden korrekt zugewiesen
- RAW Logging für alle Pfade implementiert

### ~~Vision-LLM Pfad~~ ✅
- Pipeline vereinfacht
- Base64-Problem gelöst (siehe oben)
