**🌍 Sprachen:** [English](README.md) | [Deutsch](README.de.md)

---

# 🎩 AIfred Intelligence - Fortschrittlicher KI-Assistent

**KI-Assistent mit Multi-LLM-Unterstützung, Web-Recherche & Sprachschnittstelle**

AIfred Intelligence ist ein fortschrittlicher KI-Assistent mit automatischer Web-Recherche, Multi-Model-Support und History-Kompression für unbegrenzte Konversationen.

Für Versionshistorie und aktuelle Änderungen siehe [CHANGELOG.md](CHANGELOG.md).

**📺 [Beispiel-Showcases ansehen](https://peuqui.github.io/AIfred-Intelligence/)** - Exportierte Chats (via Share-Chat-Button): Multi-Agent-Debatten, Chemie, Mathe, Coding und Web-Recherche.

---

## ✨ Features

### 🎯 Kern-Features
- **Multi-Backend-Unterstützung**: Ollama (GGUF), vLLM (AWQ), TabbyAPI (EXL2), KoboldCPP (GGUF mit erweitertem Kontext)
- **Vision/OCR-Unterstützung**: Bildanalyse mit multimodalen LLMs (DeepSeek-OCR, Qwen3-VL, Ministral-3)
- **Bild-Zuschnitt-Tool**: Interaktiver Crop vor OCR/Analyse (8-Punkt-Handles, 4K Auto-Resize)
- **3-Modell-Architektur**: Spezialisiertes Vision-LLM für OCR, Haupt-LLM für Interpretation
- **Denkmodus**: Chain-of-Thought-Reasoning für komplexe Aufgaben (Qwen3, NemoTron, QwQ - Ollama + vLLM)
- **Automatische Web-Recherche**: KI entscheidet selbst, wann Recherche nötig ist
- **History-Kompression**: Intelligente Kompression bei 70% Context-Auslastung
- **Automatische Kontext-Kalibrierung**: VRAM-bewusste Kontextgröße mit RoPE-Skalierung (1.0x, 1.5x, 2.0x), Hybrid-Modus für übergroße Modelle (CPU-Offload)
- **Sprachschnittstelle**: Konfigurierbare STT (Whisper) und TTS (Edge TTS, Piper, espeak) mit verschiedenen Stimmen, Tonhöhen-Kontrolle, intelligente Filterung (Code-Blöcke, Tabellen, LaTeX-Formeln werden nicht vorgelesen)
- **Vector-Cache**: ChromaDB-basierter semantischer Cache für Web-Recherchen (Docker)
- **Backend-spezifische Einstellungen**: Jedes Backend merkt sich seine bevorzugten Modelle (inkl. Vision-LLM)
- **Session-Persistenz**: Mobile Chat-History überlebt Browser-Hintergrund/Neustart (Cookie-basiert)
- **Chat teilen**: Export als portable HTML-Datei in neuem Browser-Tab (KaTeX-Fonts inline eingebettet, funktioniert offline)
- **HTML-Vorschau**: KI-generierter HTML-Code öffnet direkt im Browser (neuer Tab)
- **LaTeX & Chemie**: KaTeX für Mathe-Formeln, mhchem-Erweiterung für Chemie (`\ce{H2O}`, Reaktionen, Strukturformeln)
- **Multi-Agent Debate System**: AIfred + Sokrates als kritischer Diskussionspartner für verbesserte Antwortqualität

### 🎩 Multi-Agent Diskussionsmodi

AIfred unterstützt verschiedene Diskussionsmodi mit Sokrates (Kritiker) und Salomo (Richter):

| Modus | Ablauf | Wer entscheidet? |
|-------|--------|------------------|
| **Standard** | AIfred antwortet | — |
| **Kritische Prüfung** | AIfred → Sokrates → STOP | User |
| **Auto-Konsens** | AIfred → Sokrates → Salomo (X Runden) | Salomo |
| **Advocatus Diaboli** | AIfred → Sokrates (Pro/Contra) | User |
| **Tribunal** | AIfred ↔ Sokrates (X Runden) → Salomo | Salomo (Urteil) |

**Agenten:**
- 🎩 **AIfred** - Butler & Gelehrter - beantwortet Fragen (britischer Butler-Stil mit dezenter Noblesse)
- 🏛️ **Sokrates** - Kritischer Philosoph - hinterfragt & liefert Alternativen mit sokratischer Methode
- 👑 **Salomo** - Weiser Richter - synthetisiert Argumente und fällt finale Entscheidungen

**Anpassbare Persönlichkeiten:**
- Alle Agenten-Prompts sind Textdateien in `prompts/de/` und `prompts/en/`
- Persönlichkeit kann in den UI-Einstellungen ein-/ausgeschaltet werden (behält Identität, entfernt Stil)
- 3-Schichten Prompt-System: Identität (wer) + Persönlichkeit (wie, optional) + Aufgabe (was)
- Eigene Agenten erstellen oder bestehende Persönlichkeiten anpassen
- **Mehrsprachig**: Agenten antworten in der Sprache des Users (deutsche Prompts für Deutsch, englische Prompts für alle anderen Sprachen)

**Direkte Agenten-Ansprache** (NEU in v2.10):
- Sokrates direkt ansprechen: "Sokrates, was denkst du über...?" → Sokrates antwortet mit sokratischer Methode
- AIfred direkt ansprechen: "AIfred, erkläre..." → AIfred antwortet ohne Sokrates-Analyse
- Unterstützt STT-Transkriptionsvarianten: "Alfred", "Eifred", "AI Fred"
- Funktioniert auch am Satzende: "Gut erklärt. Sokrates." / "Prima gemacht. Alfred!"

**Intelligentes Context-Handling** (v2.10.2):
- Multi-Agent-Nachrichten verwenden `role: system` mit `[MULTI-AGENT CONTEXT]` Prefix
- Speaker-Labels `[SOKRATES]:` und `[AIFRED]:` bleiben für LLM-Kontext erhalten
- Verhindert, dass LLM Agenten-Austausch mit eigenen Antworten verwechselt
- Alle Prompts erhalten automatisch aktuelles Datum/Uhrzeit für zeitbezogene Fragen

**Perspektiven-System** (v2.10.3):
- Jeder Agent sieht die Konversation aus seiner eigenen Perspektive
- Sokrates sieht AIfred's Antworten als `[AIFRED]:` (user role), seine eigenen als `assistant`
- AIfred sieht Sokrates' Kritik als `[SOKRATES]:` (user role), seine eigene als `assistant`
- Verhindert Identitätsverwechslung zwischen Agenten bei mehrrundigen Debatten

**Strukturierte Kritik-Prompts** (v2.10.3):
- Rundennummer-Platzhalter `{round_num}` - Sokrates weiß welche Runde es ist
- Maximal 1-2 Kritikpunkte pro Runde
- Sokrates kritisiert nur - entscheidet nie über Konsens (das ist Salomos Aufgabe)

**Trialog-Workflow (Auto-Konsens mit Salomo):**
```
┌─────────────┐     ┌─────────────────┐     ┌─────────────────────┐
│   User      │────▶│   🎩 AIfred     │────▶│   🏛️ Sokrates       │
│   Frage     │     │   THESE         │     │   ANTITHESE         │
└─────────────┘     │   (Antwort)     │     │   (Kritik)          │
                    └─────────────────┘     └──────────┬──────────┘
                                                       │
                              ┌─────────────────────────┘
                              ▼
                    ┌─────────────────────┐
                    │   👑 Salomo         │
                    │   SYNTHESE          │
                    │   (Vermittlung)     │
                    └──────────┬──────────┘
                               │
               ┌───────────────┴───────────────┐
               ▼                               ▼
          ┌────────┐                     ┌────────┐
          │  LGTM  │                     │ Weiter │
          │ Fertig │                     │ Runde  │
          └────────┘                     └────────┘
```

**Tribunal-Workflow:**
```
┌─────────────┐     ┌─────────────────────────────────────┐
│   User      │────▶│   🎩 AIfred ↔ 🏛️ Sokrates          │
│   Frage     │     │   Debatte für X Runden              │
└─────────────┘     └──────────────────┬──────────────────┘
                                       │
                                       ▼
                    ┌─────────────────────────────────────┐
                    │   👑 Salomo - Finales Urteil        │
                    │   Wägt beide Seiten, entscheidet    │
                    └─────────────────────────────────────┘
```

**Prompt-Dateien pro Modus:**
| Modus | Verwendete Prompts |
|-------|-------------------|
| **Standard** | `aifred/system_rag` oder `aifred/system_minimal` |
| **Direkt AIfred** | `aifred/direct` |
| **Direkt Sokrates** | `sokrates/direct` |
| **Kritische Prüfung** | `aifred/*` → `sokrates/critic` |
| **Auto-Konsens** | `aifred/*` → `sokrates/critic` → `salomo/mediator` (Schleife) |
| **Advocatus Diaboli** | `aifred/*` → `sokrates/devils_advocate` |
| **Tribunal** | `aifred/*` ↔ `sokrates/critic` (X Runden) → `salomo/judge` |

**UI-Einstellungen:**
- Sokrates-LLM und Salomo-LLM separat wählbar (können verschiedene Modelle sein)
- Max. Debattenrunden (1-10, Standard: 3)
- Diskussionsmodus im Settings-Panel
- 💡 Hilfe-Icon öffnet Modal mit Übersicht aller Modi

**Thinking-Support:**
- Alle Agenten (AIfred, Sokrates, Salomo) unterstützen Thinking-Mode
- `<think>`-Blöcke werden als Collapsible formatiert

### 🔧 Technische Highlights
- **Reflex-Framework**: React-Frontend aus Python generiert
- **WebSocket-Streaming**: Echtzeit-Updates ohne Polling
- **Adaptive Temperatur**: KI wählt Temperatur basierend auf Fragetyp
- **Token-Management**: Dynamische Context-Window-Berechnung
- **VRAM-bewusster Kontext**: Automatische Kontext-Größe basierend auf verfügbarem GPU-Speicher
- **Debug-Konsole**: Umfangreiches Logging und Monitoring
- **ChromaDB-Server-Modus**: Thread-sichere Vector-DB via Docker (0.0 Distance für exakte Matches)
- **GPU-Erkennung**: Automatische Erkennung und Warnung bei inkompatiblen Backend-GPU-Kombinationen ([docs/GPU_COMPATIBILITY.md](docs/GPU_COMPATIBILITY.md))
- **Ollama Context-Kalibrierung**: 3-Stufen-Kalibrierung (Native, RoPE 1.5x, RoPE 2.0x) mit automatischer Hybrid-Mode-Erkennung für CPU-Offload → [Details](docs/plans/OLLAMA_CONTEXT_CALIBRATION.md)
- **KoboldCPP Dynamic RoPE**: Intelligente VRAM-basierte Kontext-Optimierung mit automatischem RoPE-Scaling
- **Multi-User-Queue**: KoboldCPP Request-Queuing für gleichzeitige Benutzer (bis zu 5 Clients)
- **Parallele Web-Suche**: 2-3 optimierte Queries parallel auf APIs verteilt (Tavily, Brave, SearXNG), automatische URL-Deduplizierung, optionales self-hosted SearXNG
- **Paralleles Scraping**: ThreadPoolExecutor scrapt 3-7 URLs gleichzeitig, erste erfolgreiche Ergebnisse werden verwendet
- **Nicht-verfügbare Quellen**: Zeigt nicht scrapbare URLs mit Fehlergrund an (Cloudflare, 404, Timeout) - im Vector Cache gespeichert für Cache-Hits
- **PDF-Unterstützung**: Direkte Extraktion aus PDF-Dokumenten (AWMF-Leitlinien, PubMed PDFs) via PyMuPDF mit Browser-User-Agent

### ⚠️ Modell-Empfehlungen
- **Automatik-LLM** (Intent-Erkennung, Query-Optimierung): Kleine Instruct-Modelle funktionieren am besten
  - **Empfohlen**: `qwen3:4b-instruct-2507` (Q4 oder Q8 Quantisierung)
  - Dieses Modell folgt Instruktionen präzise - kritisch für Format-Erkennung (INTENT|ADDRESSEE|LANGUAGE)
  - Thinking-Modelle dauern zu lange für diese einfachen Entscheidungen
- **Haupt-LLM**: Größere Modelle (14B+, idealerweise 30B+) für besseres Kontextverständnis und Prompt-Following
  - Sowohl Instruct- als auch Thinking-Modelle funktionieren gut
  - "Denkmodus" für Chain-of-Thought-Reasoning bei komplexen Aufgaben aktivieren
  - **Sprach-Hinweis**: Kleine Modelle (4B-14B) antworten möglicherweise auf Englisch, wenn der RAG-Kontext überwiegend englische Web-Inhalte enthält - auch bei deutschen Prompts. Modelle ab 30B+ befolgen Sprachanweisungen zuverlässig, unabhängig von der Kontext-Sprache.

---

## 🔄 Research Mode Workflows

AIfred bietet 4 verschiedene Research-Modi, die je nach Anforderung unterschiedliche Strategien verwenden. Hier ist der detaillierte Ablauf jedes Modus:

### 📊 LLM Calls Übersicht

| Modus | Min LLM Calls | Max LLM Calls | Typische Dauer |
|-------|---------------|---------------|----------------|
| **Eigenes Wissen** | 1 | 1 | 5-30s |
| **Automatik** (Cache Hit) | 0 | 0 | <1s |
| **Automatik** (Direct Answer) | 2 | 3 | 5-35s |
| **Automatik** (Web Research) | 4 | 5 | 15-60s |
| **Websuche Schnell** | 3 | 4 | 10-40s |
| **Websuche Ausführlich** | 3 | 4 | 15-60s |

---

### 🔄 Pre-Processing (alle Modi)

**Gemeinsamer erster Schritt** für alle Research-Modi:

```
Intent + Addressee Detection
├─ LLM Call (Automatik-LLM) - kombiniert in einem Call
├─ Prompt: intent_detection
├─ Response: "FAKTISCH|sokrates" | "KREATIV|" | "GEMISCHT|aifred"
├─ Temperature-Nutzung:
│  ├─ Auto-Mode: FAKTISCH=0.2, GEMISCHT=0.5, KREATIV=1.0
│  └─ Manual-Mode: Intent ignoriert, manueller Wert verwendet
└─ Addressee: Direkte Agenten-Ansprache (sokrates/aifred/salomo)
```

Bei direkter Agenten-Ansprache wird der entsprechende Agent sofort aktiviert, unabhängig vom gewählten Research-Modus oder Temperature-Setting.

---

### 1️⃣ Eigenes Wissen Mode (Direct LLM)

**Einfachster Modus**: Direkter LLM-Aufruf ohne Web-Recherche oder KI-Entscheidung.

**Workflow:**
```
1. Message Building
   └─ Build from chat history
   └─ Inject system_minimal prompt (mit Timestamp)

2. Model Preloading (Ollama only)
   └─ backend.preload_model() - misst echte Ladezeit
   └─ vLLM/TabbyAPI: Skip (bereits in VRAM)

3. Token Management
   └─ estimate_tokens(messages, model_name)
   └─ calculate_dynamic_num_ctx()

4. LLM Call - Main Response
   ├─ Model: Haupt-LLM (z.B. Qwen2.5-32B)
   ├─ Temperature: Manual (User-Einstellung)
   ├─ Streaming: Ja (Echtzeit-Updates)
   └─ TTFT + Tokens/s Messung

5. Format & Save
   └─ format_thinking_process() für <think> Tags
   └─ Update chat history

6. History Compression (PRE-MESSAGE Check - VOR jedem LLM-Aufruf)
   ├─ Trigger: 70% Auslastung des kleinsten Context-Fensters
   │  └─ Multi-Agent: min_ctx aller Agenten wird verwendet
   ├─ Dual History: chat_history (UI) + llm_history (LLM, FIFO)
   └─ Summaries erscheinen inline im Chat wo komprimiert wurde
```

**LLM Calls:** 1 Haupt-LLM + optional 1 Compression-LLM (bei >70% Context)
**Async Tasks:** Keine
**Code:** `aifred/state.py` Lines 974-1117

---

### 2️⃣ Automatik Mode (AI Decision System)

**Intelligentester Modus**: KI entscheidet selbst, ob Web-Recherche nötig ist.

#### Phase 1: Vector Cache Check
```
1. Query ChromaDB für ähnliche Fragen
   └─ Distance < 0.5: HIGH Confidence → Cache Hit
   └─ Distance ≥ 0.5: CACHE_MISS → Weiter

2. IF CACHE HIT:
   └─ Antwort direkt aus Cache
   └─ RETURN (0 LLM Calls!)
```

#### Phase 2: RAG Context Check
```
1. Query cache für RAG candidates (distance 0.5-1.2)

2. FOR EACH candidate:
   ├─ LLM Relevance Check (Automatik-LLM)
   │  └─ Prompt: rag_relevance_check
   │  └─ Options: temp=0.1, num_ctx=2048
   └─ Keep if relevant

3. Build formatted context from relevant entries
```

#### Phase 3: Keyword Override Check
```
1. Check für explicit research keywords:
   └─ "recherchiere", "suche im internet", "google", etc.

2. IF keyword found:
   └─ Trigger fresh web research (mode='deep')
   └─ BYPASS Automatik decision
```

#### Phase 4: Automatik Decision (Kombiniert)
```
1. LLM Call - Research-Entscheidung + Query-Generierung (Kombiniert)
   ├─ Model: Automatik-LLM (z.B. Qwen3:4B, konfigurierbar, 4K Kontext)
   ├─ Prompt: prompts/{lang}/automatik/research_decision.txt
   │  ├─ Enthält: Aktuelles Datum/Jahr-Injektion
   │  ├─ Vision-Kontext bei angehängten Bildern
   │  └─ Strukturierte Ausgabe: JSON {"web": bool, "queries": [str]}
   ├─ Messages: ❌ KEINE History (fokussierte, unvoreingenommene Entscheidung)
   ├─ Options:
   │  ├─ temperature: 0.2 (konsistente Entscheidungen)
   │  ├─ num_ctx: 4096 (AUTOMATIK_LLM_NUM_CTX Konstante)
   │  ├─ num_predict: 256 (genug für Entscheidung + 3 Queries)
   │  └─ enable_thinking: False (schnell)
   └─ Response: {"web": true, "queries": ["q1", "q2", "q3"]}
                ODER {"web": false}

2. JSON-Response parsen:
   ├─ Web-Entscheidung extrahieren (true/false)
   ├─ Vorgenerierte Queries extrahieren (falls web=true)
   ├─ Validieren: falls web=true aber keine Queries → setze web=false
   └─ Bei Fehlern: raise ValueError (keine stillen Fallbacks)

3. Route basierend auf Entscheidung:
   ├─ IF web=true:  → Web-Recherche mit vorgenerierten Queries
   └─ IF web=false: → Direkte LLM-Antwort (Phase 5)
```

**Warum kombinierte Entscheidung + Query-Generierung?**
- **Ein LLM-Call** statt zwei separater Calls (Entscheidung → Query-Optimierung)
- **Schneller**: Spart ~0,5-1s pro Research-Anfrage
- **Konsistenter**: Entscheidung und Queries werden mit gleichem Kontext generiert
- **Einfacherer Code**: Keine Fallback-Logik nötig

**Warum keine History für Decision-Making?**
- Verhindert Bias aus vorherigem Gesprächskontext
- Entscheidung basiert rein auf aktueller Frage + Vision-Daten
- Garantiert konsistente, objektive Web-Research-Auslösung

**Automatik-LLM System-Architektur:**

Das Automatik-LLM ist ein kleines, schnelles Modell (typisch 3-4B Parameter), das für leichtgewichtige Entscheidungsaufgaben genutzt wird, die nicht die vollen Fähigkeiten des Haupt-LLMs benötigen. Es läuft mit einem fixen 4K Kontextfenster um VRAM-Nutzung zu minimieren.

**Aktive Prompts** (`prompts/{lang}/automatik/`):
| Datei | Zweck | Wann verwendet | Ausgabe |
|-------|-------|----------------|---------|
| `research_decision.txt` | Kombiniert: Web-Entscheidung + 3 Query-Generierung | Jede User-Message im Automatik-Modus | JSON: `{"web": bool, "queries": [str]}` |
| `intent_detection.txt` | Erkennt Intent/Adressat/Sprache | Jede User-Message (alle Modi) | `INTENT\|ADRESSAT\|SPRACHE` |
| `followup_intent_detection.txt` | Cache-Followup: Neues Thema vs. Vertiefungsfrage | Bei Cache-Hit mit anderer Query | `NEW_TOPIC` oder `FOLLOW_UP` |
| `rag_relevance_check.txt` | Prüft ob gecachter Inhalt relevant ist | Vor Nutzung von Cache-Hit-Inhalt | `relevant` oder `not_relevant` |

**Konfiguration** (`aifred/lib/config.py`):
```python
# Fixer 4K Kontext für alle Automatik-Aufgaben (verhindert VRAM-Bloat)
AUTOMATIK_LLM_NUM_CTX = 4096

# Warum 4K?
# - Qwen3:4B Standard ist 262K → würde riesigen KV-Cache allokieren
# - 4K ist ausreichend für alle Automatik-Prompts + Antworten
# - Hält VRAM-Nutzung minimal über Multi-GPU-Setups hinweg
```

**Code-Ablauf** (`aifred/lib/conversation_handler.py:detect_research_decision()`):
1. Lade `research_decision.txt` Prompt mit aktuellem Datum/Jahr
2. Rufe Automatik-LLM auf (keine History, temp=0.2, 4K Kontext)
3. Parse JSON-Response mit Reparatur-Logik für häufige LLM-Fehler
4. Validiere Queries falls web=true
5. Gebe Entscheidung + Queries an Orchestrator zurück

**Modell-Anforderungen:**
- **Minimum**: 3B Parameter (z.B. Qwen2.5-3B)
- **Empfohlen**: Qwen3:4B oder ähnliche instruction-tuned Modelle
- **JSON-Ausgabe**: Modell muss strukturierte JSON-Generierung unterstützen
- **Geschwindigkeit**: Sollte in <0,5s fertig sein für responsive UX

#### Phase 5: Direct LLM Answer (if decision = no)
```
1. Model Preloading (Ollama only)

2. Build Messages
   ├─ From chat history
   ├─ Inject system_minimal prompt
   └─ Optional: Inject RAG context (if found in Phase 2)

3. LLM Call - Main Response
   ├─ Model: Haupt-LLM
   ├─ Temperature: From Pre-Processing or manual
   ├─ Streaming: Ja
   └─ TTFT + Tokens/s Messung

4. Format & Update History
   └─ Metadata: "Cache+LLM (RAG)" or "LLM"

5. History Compression Check (wie in Eigenes Wissen Mode)
   └─ Automatische Kompression bei >70% Context-Auslastung
```

**LLM Calls:**
- Cache Hit: 0 + optional 1 Compression
- RAG Context: 2-6 + optional 1 Compression
- Web Research: 4-5 + optional 1 Compression
- Direct Answer: 2-3 + optional 1 Compression

**Code:** `aifred/lib/conversation_handler.py`

---

### 3️⃣ Websuche Schnell Mode (Quick Research)

**Schnellster Web-Research Modus**: Top 3 URLs, optimiert für Speed.

#### Phase 1: Session Cache Check
```
1. Check session-based cache
   └─ IF cache hit: Use cached sources → Skip to Phase 4
   └─ IF miss: Continue to Phase 2
```

#### Phase 2: Query Optimization + Web Search
```
1. LLM Call - Query Optimization
   ├─ Model: Automatik-LLM
   ├─ Prompt: query_optimization
   ├─ Messages: Last 3 history turns (for follow-up context)
   ├─ Options:
   │  ├─ temperature: 0.3 (balanced for keywords)
   │  ├─ num_ctx: min(8192, automatik_limit)
   │  └─ enable_thinking: False
   ├─ Post-processing:
   │  ├─ Extract <think> tags (reasoning)
   │  ├─ Clean query (remove quotes)
   │  └─ Add temporal context (current year)
   └─ Output: optimized_query, query_reasoning

2. Web Search (Multi-API with Fallback)
   ├─ Try: Brave API
   ├─ Fallback: Tavily
   ├─ Fallback: SearXNG (local)
   └─ Deduplication across APIs
```

#### Phase 3: Parallel Web Scraping
```
PARALLEL EXECUTION:
├─ ThreadPoolExecutor (max 5 workers)
│  └─ Scrape Top 3 URLs simultaneously
│     └─ Extract text content + word count
│
└─ Async Task: Main LLM Preload (Ollama only)
   └─ llm_client.preload_model(model)
   └─ Runs parallel to scraping
   └─ vLLM/TabbyAPI: Skip (already loaded)

Progress Updates:
└─ Yield after each URL completion
```

#### Phase 4: Context Building + LLM Response
```
1. Build Context
   ├─ Filter successful scrapes (word_count > 0)
   ├─ build_context() - smart token limit aware
   └─ Build system_rag prompt (with context + timestamp)

2. LLM Call - Final Response
   ├─ Model: Haupt-LLM
   ├─ Temperature: From Pre-Processing or manual
   ├─ Context: ~3 sources, 5K-10K tokens
   ├─ Streaming: Ja
   └─ TTFT + Tokens/s Messung

3. Cache Decision (NUR bei Web-Recherche)
   ├─ Check for volatile keywords (z.B. "heute", "aktuell", "jetzt")
   │  └─ IF volatile: Skip caching (zeitkritische Info)
   ├─ LLM Call (Automatik-LLM) - Cacheability Check
   │  ├─ Prompt: cache_decision
   │  ├─ Input: User-Query + LLM-Antwort
   │  ├─ Entscheidung basiert auf:
   │  │  ├─ Zeitlose Fakten? (z.B. "Was ist Python?") → cacheable
   │  │  ├─ Zeitgebundene Events? (z.B. "aktuelle News") → not_cacheable
   │  │  ├─ Persönliche Präferenzen? (z.B. "bestes Restaurant") → not_cacheable
   │  │  └─ Volatile Daten? (z.B. Wetter, Aktienkurse) → not_cacheable
   │  └─ Response: 'cacheable' | 'not_cacheable'
   ├─ IF cacheable:
   │  ├─ Semantic Duplicate Check (distance < 0.3 zu existierenden Einträgen)
   │  │  └─ IF duplicate: Lösche alten Eintrag (garantiert neueste Daten)
   │  ├─ cache.add(query, answer, sources, metadata)
   │  └─ Debug: "💾 Antwort gecacht" oder "🔄 Cache-Eintrag aktualisiert"
   └─ ELSE: Debug: "⏭️ Antwort nicht gecacht (volatil/zeitgebunden)"

4. Format & Update History
   └─ Metadata: "(Agent: quick, {n} Quellen)"

5. History Compression Check (wie in Eigenes Wissen Mode)
   └─ Automatische Kompression bei >70% Context-Auslastung
```

**LLM Calls:**
- With Cache: 1-2 + optional 1 Compression
- Without Cache: 3-4 + optional 1 Compression

**Async Tasks:**
- Parallel URL scraping (3 URLs)
- Background LLM preload (Ollama only)

**Code:** `aifred/lib/research/orchestrator.py` + Submodules

---

### 4️⃣ Websuche Ausführlich Mode (Deep Research)

**Gründlichster Modus**: Top 7 URLs für maximale Informationstiefe.

**Workflow:** Identisch zu Websuche Schnell, mit folgenden Unterschieden:

#### Scraping Strategy
```
Quick Mode:  3 URLs → ~3 successful sources
Deep Mode:   7 URLs → ~5-7 successful sources

Parallel Execution:
├─ ThreadPoolExecutor (max 5 workers)
│  └─ Scrape Top 7 URLs simultaneously
│  └─ Continue until 5 successful OR all tried
│
└─ Async: Main LLM Preload (parallel)
```

#### Context Size
```
Quick: ~5K-10K tokens context
Deep:  ~10K-20K tokens context

→ Mehr Quellen = reicherer Kontext
→ Längere LLM Inference (10-40s vs 5-30s)
```

**LLM Calls:** Identisch zu Quick (3-4 + optional 1 Compression)
**Async Tasks:** Mehr URLs parallel (7 vs 3)
**Trade-off:** Höhere Qualität vs längere Dauer
**History Compression:** Wie alle Modi - automatisch bei >70% Context

---

### 🔀 Decision Flow Diagram

```
USER INPUT
    │
    ▼
┌─────────────────────┐
│ Research Mode?      │
└─────────────────────┘
    │
    ├── "none" ────────────────────────┐
    │                                   │
    ├── "automatik" ──────────────┐   │
    │                              │   │
    ├── "quick" ──────────────┐  │   │
    │                          │  │   │
    └── "deep" ────────────┐  │  │   │
                           │  │  │   │
                           ▼  ▼  ▼   ▼
                      ╔═══════════════════╗
                      ║ MODE HANDLER      ║
                      ╚═══════════════════╝
                               │
     ┌─────────────────────────┼──────────────────────┐
     │                         │                      │
     ▼                         ▼                      ▼
┌──────────┐         ┌──────────────┐       ┌─────────────┐
│ EIGENES  │         │ AUTOMATIK    │       │ WEB         │
│ WISSEN   │         │ (AI Decides) │       │ RESEARCH    │
└──────────┘         └──────────────┘       │ (quick/deep)│
     │                       │               └─────────────┘
     │                       ▼                      │
     │              ┌────────────────┐              │
     │              │ Vector Cache   │              │
     │              │ Check          │              │
     │              └────────────────┘              │
     │                       │                      │
     │          ┌────────────┼─────────────┐        │
     │          │            │             │        │
     │          ▼            ▼             ▼        │
     │     ┌────────┐  ┌─────────┐  ┌─────────┐   │
     │     │ CACHE  │  │ RAG     │  │ CACHE   │   │
     │     │ HIT    │  │ CONTEXT │  │ MISS    │   │
     │     │ RETURN │  │ FOUND   │  │         │   │
     │     └────────┘  └─────────┘  └─────────┘   │
     │                       │            │         │
     │                       │            ▼         │
     │                       │    ┌──────────────┐ │
     │                       │    │ Keyword      │ │
     │                       │    │ Override?    │ │
     │                       │    └──────────────┘ │
     │                       │         │     │      │
     │                       │         NO   YES     │
     │                       │         │     │      │
     │                       │         │     └──────┤
     │                       │         ▼            │
     │                       │   ┌──────────────┐  │
     │                       │   │ LLM Decision │  │
     │                       │   │ (yes/no)     │  │
     │                       │   └──────────────┘  │
     │                       │         │     │      │
     │                       │         NO   YES     │
     │                       │         │     │      │
     │                       │         │     └──────┤
     ▼                       ▼         ▼            ▼
╔══════════════════════════════════════════════════════╗
║         DIRECT LLM INFERENCE                         ║
║  1. Build Messages (with/without RAG)                ║
║  2. Intent Detection (auto mode)                     ║
║  3. Main LLM Call (streaming)                        ║
║  4. Format & Update History                          ║
╚══════════════════════════════════════════════════════╝
                           │
                           ▼
                    ┌──────────┐
                    │ RESPONSE │
                    └──────────┘

         WEB RESEARCH PIPELINE
         ═════════════════════
                    │
                    ▼
        ┌───────────────────┐
        │ Session Cache?    │
        └───────────────────┘
                    │
        ┌───────────┴────────────┐
        │                        │
        ▼                        ▼
   ┌────────┐          ┌─────────────────┐
   │ CACHE  │          │ Query           │
   │ HIT    │          │ Optimization    │
   └────────┘          │ (Automatik-LLM) │
                       └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ Web Search      │
                       │ (Multi-API)     │
                       └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ PARALLEL TASKS  │
                       ├─────────────────┤
                       │ • Scraping      │
                       │   (3 or 7 URLs) │
                       │ • LLM Preload   │
                       │   (async)       │
                       └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ Context Build   │
                       └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ Main LLM        │
                       │ (streaming)     │
                       └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ Cache Decision  │
                       │ (Automatik-LLM) │
                       └─────────────────┘
                                │
                                ▼
                       ┌─────────────────┐
                       │ RESPONSE        │
                       └─────────────────┘
```

### 📁 Code Structure Reference

**Core Entry Points:**
- `aifred/state.py` - Main state management, send_message()

**Automatik Mode:**
- `aifred/lib/conversation_handler.py` - Decision logic, RAG context

**Web Research Pipeline:**
- `aifred/lib/research/orchestrator.py` - Top-level orchestration
- `aifred/lib/research/cache_handler.py` - Session cache
- `aifred/lib/research/query_processor.py` - Query optimization + search
- `aifred/lib/research/scraper_orchestrator.py` - Parallel scraping
- `aifred/lib/research/context_builder.py` - Context building + LLM

**Supporting Modules:**
- `aifred/lib/vector_cache.py` - ChromaDB semantic cache
- `aifred/lib/rag_context_builder.py` - RAG context from cache
- `aifred/lib/query_optimizer.py` - Search query optimization
- `aifred/lib/intent_detector.py` - Temperature selection
- `aifred/lib/agent_tools.py` - Web search, scraping, context building

---

## 🌐 REST API (Fernsteuerung)

AIfred bietet eine vollständige REST-API für programmatische Steuerung - ermöglicht Fernbedienung via Cloud, Automatisierungs-Systeme und Drittanbieter-Integrationen.

### Hauptmerkmale

- **Vollständige Fernsteuerung**: AIfred von überall via HTTPS steuern
- **Live Browser-Sync**: API-Änderungen erscheinen automatisch im Browser (kein Refresh nötig)
- **Session-Management**: Zugriff und Verwaltung mehrerer Browser-Sessions
- **OpenAPI Dokumentation**: Interaktive Swagger UI unter `/docs`

### API Endpoints

Die API ermöglicht **reine Fernsteuerung** - Messages werden in Browser-Sessions injiziert, der Browser führt die vollständige Verarbeitung durch (Intent Detection, Multi-Agent, Research, etc.). So sieht der User alles live im Browser.

| Endpoint | Methode | Beschreibung |
|----------|---------|--------------|
| `/api/health` | GET | Health-Check mit Backend-Status |
| `/api/settings` | GET | Alle Einstellungen abrufen |
| `/api/settings` | PATCH | Einstellungen ändern (partielles Update) |
| `/api/models` | GET | Verfügbare Modelle auflisten |
| `/api/chat/inject` | POST | Nachricht in Browser-Session injizieren |
| `/api/chat/status` | GET | Inferenz-Status abfragen (is_generating, message_count) |
| `/api/chat/history` | GET | Chat-Verlauf abrufen |
| `/api/chat/clear` | POST | Chat-Verlauf löschen |
| `/api/sessions` | GET | Alle Browser-Sessions auflisten |
| `/api/system/restart-ollama` | POST | Ollama neustarten |
| `/api/system/restart-aifred` | POST | AIfred neustarten |
| `/api/calibrate` | POST | Kontext-Kalibrierung starten |

### Browser-Synchronisation

Wenn du Einstellungen änderst oder Nachrichten via API sendest, aktualisiert sich das Browser-UI automatisch:

- **Chat-Sync**: Via API gesendete Nachrichten erscheinen im Browser innerhalb von 2 Sekunden
- **Settings-Sync**: Model-Änderungen, RoPE-Faktoren, Temperatur etc. werden live im UI aktualisiert

Dies ermöglicht echte Fernsteuerung - ändere AIfred's Konfiguration von einem anderen Gerät und sieh die Änderungen sofort in jedem verbundenen Browser.

### Beispiel-Verwendung

```bash
# Aktuelle Einstellungen abrufen
curl http://localhost:8002/api/settings

# Model und RoPE-Faktor ändern
curl -X PATCH http://localhost:8002/api/settings \
  -H "Content-Type: application/json" \
  -d '{"aifred_model": "qwen3:14b", "sokrates_rope_factor": 2.0}'

# Nachricht injizieren (Browser verarbeitet und zeigt live)
curl -X POST http://localhost:8002/api/chat/inject \
  -H "Content-Type: application/json" \
  -d '{"message": "Was ist Python?", "device_id": "abc123..."}'

# Inferenz-Status abfragen
curl "http://localhost:8002/api/chat/status?device_id=abc123..."

# Alle Browser-Sessions auflisten
curl http://localhost:8002/api/sessions
```

### Anwendungsfälle

- **Cloud-Steuerung**: AIfred von überall via HTTPS/API bedienen
- **Home-Automation**: Integration mit Home Assistant, Node-RED, etc.
- **Sprachassistenten**: Alexa/Google Home können AIfred-Anfragen senden
- **Batch-Verarbeitung**: Automatisierte Abfragen via Scripts
- **Mobile Apps**: Custom-Apps können die API nutzen

---

## 🚀 Installation

### Voraussetzungen
- Python 3.10+
- **LLM Backend** (wähle eins):
  - **Ollama** (einfach, GGUF-Modelle) - empfohlen für Start
  - **vLLM** (schnell, AWQ-Modelle) - beste Performance (requires Compute Capability 7.5+)
  - **TabbyAPI** (ExLlamaV2/V3, EXL2-Modelle) - experimentell
- 8GB+ RAM (12GB+ empfohlen für größere Modelle)
- Docker (für ChromaDB Vector Cache)
- **GPU**: NVIDIA GPU empfohlen (siehe [GPU Compatibility Guide](docs/GPU_COMPATIBILITY.md))

### Setup

1. **Repository klonen**:
```bash
git clone https://github.com/yourusername/AIfred-Intelligence.git
cd AIfred-Intelligence
```

2. **Virtual Environment erstellen**:
```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# oder
venv\Scripts\activate     # Windows
```

3. **Dependencies installieren**:
```bash
pip install -r requirements.txt
# Playwright Browser installieren (für JS-heavy Seiten)
playwright install chromium
```

**Haupt-Dependencies** (siehe `requirements.txt`):
| Kategorie | Packages |
|-----------|----------|
| Framework | reflex, fastapi, pydantic |
| LLM Backends | httpx, openai, pynvml, psutil |
| Web Research | beautifulsoup4, trafilatura, playwright, pymupdf |
| Vector Cache | chromadb, ollama |
| Audio (STT/TTS) | edge-tts, openai-whisper |

4. **Umgebungsvariablen** (.env):
```env
# API Keys für Web-Recherche
BRAVE_API_KEY=your_key_here
TAVILY_API_KEY=your_key_here

# Ollama Konfiguration
OLLAMA_BASE_URL=http://localhost:11434
```

5. **LLM Models installieren**:

**Option A: Alle Models (Empfohlen)**
```bash
# Master-Script für beide Backends
./scripts/download_all_models.sh
```

**Option B: Nur Ollama (GGUF) - Einfachste Installation**
```bash
# Ollama Models (GGUF Q4/Q8)
./scripts/download_ollama_models.sh

# Empfohlene Core-Modelle:
# - qwen3:30b-instruct (18GB) - Haupt-LLM, 256K context
# - qwen3:8b (5.2GB) - Automatik, optional thinking
# - qwen2.5:3b (1.9GB) - Ultra-schnelle Automatik
```

**Option C: Nur vLLM (AWQ) - Beste Performance**
```bash
# vLLM installieren (falls noch nicht geschehen)
pip install vllm

# vLLM Models (AWQ Quantization)
./scripts/download_vllm_models.sh

# Empfohlene Modelle:
# - Qwen3-8B-AWQ (~5GB, 40K→128K mit YaRN)
# - Qwen3-14B-AWQ (~8GB, 32K→128K mit YaRN)
# - Qwen2.5-14B-Instruct-AWQ (~8GB, 128K native)

# vLLM Server starten mit YaRN (64K context)
./venv/bin/vllm serve Qwen/Qwen3-14B-AWQ \
  --quantization awq_marlin \
  --port 8001 \
  --rope-scaling '{"rope_type":"yarn","factor":2.0,"original_max_position_embeddings":32768}' \
  --max-model-len 65536 \
  --gpu-memory-utilization 0.85

# Systemd Service einrichten: siehe docs/infrastructure/
```

**Option D: TabbyAPI (EXL2) - Experimentell**
```bash
# Noch nicht vollständig implementiert
# Siehe: https://github.com/theroyallab/tabbyAPI
```

6. **ChromaDB Vector Cache starten** (Docker):
```bash
cd docker
docker compose up -d chromadb
cd ..
```

**Optional: SearXNG auch starten** (lokale Suchmaschine):
```bash
cd docker
docker compose --profile full up -d
cd ..
```

**ChromaDB Cache zurücksetzen** (bei Bedarf):

*Option 1: Kompletter Neustart (löscht alle Daten)*
```bash
cd docker
docker compose stop chromadb
cd ..
rm -rf docker/aifred_vector_cache/
cd docker
docker compose up -d chromadb
cd ..
```

*Option 2: Nur Collection löschen (während Container läuft)*
```bash
./venv/bin/python -c "
import chromadb
from chromadb.config import Settings

client = chromadb.HttpClient(
    host='localhost',
    port=8000,
    settings=Settings(anonymized_telemetry=False)
)

try:
    client.delete_collection('research_cache')
    print('✅ Collection gelöscht')
except Exception as e:
    print(f'⚠️ Fehler: {e}')
"
```

7. **Starten**:
```bash
reflex run
```

Die App läuft dann unter: http://localhost:3002

---

## ⚙️ Backend-Wechsel & Settings

### Multi-Backend Support

AIfred unterstützt verschiedene LLM-Backends, die in der UI dynamisch gewechselt werden können:

- **Ollama**: GGUF-Modelle (Q4/Q8), einfachste Installation
- **vLLM**: AWQ-Modelle (4-bit), beste Performance mit AWQ Marlin Kernel
- **KoboldCPP**: GGUF-Modelle mit dynamischem RoPE-Scaling und VRAM-Optimierung
- **TabbyAPI**: EXL2-Modelle (ExLlamaV2/V3) - experimentell, nur Basis-Unterstützung

### GPU Compatibility Detection

AIfred erkennt automatisch beim Start deine GPU und warnt vor inkompatiblen Backend-Konfigurationen:

- **Tesla P40 / GTX 10 Series** (Pascal): Nutze Ollama (GGUF) - vLLM/AWQ wird nicht unterstützt
- **RTX 20+ Series** (Turing/Ampere/Ada): vLLM (AWQ) empfohlen für beste Performance

Detaillierte Informationen: [GPU_COMPATIBILITY.md](docs/GPU_COMPATIBILITY.md)

### Settings-Persistenz

Settings werden in `~/.config/aifred/settings.json` gespeichert:

**Per-Backend Modell-Speicherung:**
- Jedes Backend merkt sich seine zuletzt verwendeten Modelle
- Beim Backend-Wechsel werden automatisch die richtigen Modelle wiederhergestellt
- Beim ersten Start werden Defaults aus `aifred/lib/config.py` verwendet

**Beispiel Settings-Struktur:**
```json
{
  "backend_type": "vllm",
  "enable_thinking": true,
  "backend_models": {
    "ollama": {
      "selected_model": "qwen3:8b",
      "automatik_model": "qwen2.5:3b"
    },
    "vllm": {
      "selected_model": "Qwen/Qwen3-8B-AWQ",
      "automatik_model": "Qwen/Qwen3-4B-AWQ"
    }
  }
}
```

### Thinking Mode (Chain-of-Thought)

AIfred unterstützt Thinking Mode für Modelle mit `<think>` Tag-Unterstützung (Qwen3, QwQ, NemoTron, etc.):

- **Thinking Mode ON**: Generiert `<think>...</think>` Blocks mit Denkprozess
- **Thinking Mode OFF**: Direkte Antworten ohne Chain-of-Thought
- **Temperature**: Unabhängig - nutzt Intent Detection (auto) oder manuellen Slider
- **Formatierung**: Denkprozess als ausklappbares Collapsible mit Modellname und Inferenzzeit
- **Automatik-LLM**: Thinking Mode für Automatik-Entscheidungen DEAKTIVIERT (8x schneller)

---

## 🏗️ Architektur

### Directory Structure
```
AIfred-Intelligence/
├── aifred/
│   ├── backends/          # LLM Backend Adapters
│   │   ├── base.py           # Abstract Base Class
│   │   ├── ollama.py         # Ollama Backend (GGUF)
│   │   ├── vllm.py           # vLLM Backend (AWQ)
│   │   ├── tabbyapi.py       # TabbyAPI Backend (EXL2)
│   │   └── koboldcpp.py      # KoboldCPP Backend (GGUF)
│   ├── lib/               # Core Libraries
│   │   ├── multi_agent.py       # Multi-Agent System (AIfred, Sokrates, Salomo)
│   │   ├── context_manager.py   # History-Kompression
│   │   ├── conversation_handler.py # Automatik-Modus, RAG-Kontext
│   │   ├── config.py            # Default Settings
│   │   ├── vector_cache.py      # ChromaDB Vector Cache
│   │   ├── research/            # Web-Research Module
│   │   │   ├── orchestrator.py      # Research Orchestrierung
│   │   │   └── query_processor.py   # Query Processing
│   │   └── tools/               # Tool-Implementierungen
│   │       ├── search_tools.py      # Parallele Websuche
│   │       └── scraper_tool.py      # Paralleles Web-Scraping
│   ├── aifred.py          # Hauptanwendung / UI
│   └── state.py           # Reflex State Management
├── prompts/               # System Prompts (de/en)
├── scripts/               # Utility Scripts
├── docs/                  # Dokumentation
│   ├── infrastructure/          # Service-Setup Anleitungen
│   ├── architecture/            # Architektur-Docs
│   └── GPU_COMPATIBILITY.md     # GPU-Kompatibilitätsmatrix
├── docker/                # Docker-Konfigurationen
│   └── aifred_vector_cache/     # ChromaDB Docker Setup
└── CHANGELOG.md           # Projekt-Changelog
```

### History Compression System

Bei 70% Context-Auslastung werden automatisch ältere Konversationen komprimiert mit **PRE-MESSAGE Checks** (v2.12.0):

| Parameter | Wert | Beschreibung |
|-----------|------|--------------|
| `HISTORY_COMPRESSION_TRIGGER` | 0.7 (70%) | Bei dieser Context-Auslastung wird komprimiert |
| `HISTORY_COMPRESSION_TARGET` | 0.3 (30%) | Ziel nach Kompression (Platz für ~2 Roundtrips) |
| `HISTORY_SUMMARY_RATIO` | 0.25 (4:1) | Summary = 25% des zu komprimierenden Inhalts |
| `HISTORY_SUMMARY_MIN_TOKENS` | 500 | Minimum für sinnvolle Zusammenfassungen |
| `HISTORY_SUMMARY_TOLERANCE` | 0.5 (50%) | Erlaubte Überschreitung, darüber wird gekürzt |
| `HISTORY_SUMMARY_MAX_RATIO` | 0.2 (20%) | Max Context-Anteil für Summaries (NEU) |

**Ablauf (PRE-MESSAGE):**
1. **PRE-CHECK** vor jedem LLM-Aufruf (nicht danach!)
2. **Trigger** bei 70% Context-Auslastung
3. **Dynamisches max_summaries** basierend auf Context-Größe (20% Budget / 500 tok)
4. **FIFO cleanup**: Falls zu viele Summaries, älteste wird zuerst gelöscht
5. **Sammle** älteste Messages bis remaining < 30%
6. **Komprimiere** gesammelte Messages zu Summary (4:1 Ratio)
7. **Neue History** = [Summaries] + [verbleibende Messages]

**Dynamische Summary-Limits:**
| Context | Max Summaries | Berechnung |
|---------|---------------|------------|
| 4K | 1-2 | 4096 × 0.2 / 500 = 1,6 |
| 8K | 3 | 8192 × 0.2 / 500 = 3,3 |
| 32K | 10 | 32768 × 0.2 / 500 = 13 → gedeckelt bei 10 |

**Token-Estimation:** Ignoriert `<details>`, `<span>`, `<think>` Tags (gehen nicht ans LLM)

**Beispiele nach Context-Größe:**
| Context | Trigger | Ziel | Komprimiert | Summary |
|---------|---------|------|-------------|---------|
| 7K | 4.900 tok | 2.100 tok | ~2.800 tok | ~700 tok |
| 40K | 28.000 tok | 12.000 tok | ~16.000 tok | ~4.000 tok |
| 200K | 140.000 tok | 60.000 tok | ~80.000 tok | ~20.000 tok |

**Inline Summaries (UI, v2.14.2+):**
- Summaries erscheinen inline wo die Kompression stattfand
- Jede Summary als Collapsible mit Header (Nummer, Message-Count)
- FIFO gilt nur für `llm_history` (LLM sieht 1 Summary)
- `chat_history` behält ALLE Summaries (User sieht vollständige History)

### Vector Cache & RAG System

AIfred nutzt ein mehrstufiges Cache-System basierend auf **semantischer Ähnlichkeit** (Cosine Distance) mit rein semantischer Deduplizierung und intelligenter Cache-Nutzung bei expliziten Recherche-Keywords.

#### Cache-Entscheidungs-Logik

**Phase 0: Explizite Recherche-Keywords**
```
User Query: "recherchiere Python" / "google Python" / "suche im internet Python"
└─ Explizites Keyword erkannt → Cache-Check ZUERST
   ├─ Distance < 0.05 (praktisch identisch)
   │  └─ ✅ Cache-Hit (0.15s statt 100s) - Zeigt Alter transparent an
   └─ Distance ≥ 0.05 (nicht identisch)
      └─ Neue Web-Recherche (User will neue Daten)
```

**Phase 1a: Direct Cache Hit Check**
```
User Query → ChromaDB Similarity Search
├─ Distance < 0.5 (HIGH Confidence)
│  └─ ✅ Use Cached Answer (sofort, keine Zeit-Checks mehr!)
├─ Distance 0.5-1.2 (MEDIUM Confidence) → Continue to Phase 1b (RAG)
└─ Distance > 1.2 (LOW Confidence) → Continue to Phase 2 (Research Decision)
```

**Phase 1b: RAG Context Check**
```
Cache Miss (d ≥ 0.5) → Query for RAG Candidates (0.5 ≤ d < 1.2)
├─ Found RAG Candidates?
│  ├─ YES → Automatik-LLM checks relevance for each candidate
│  │   ├─ Relevant (semantic match) → Inject as System Message Context
│  │   │   Example: "Python" → "FastAPI" ✅ (FastAPI is Python framework)
│  │   └─ Not Relevant → Skip
│  │       Example: "Python" → "Weather" ❌ (no connection)
│  └─ NO → Continue to Phase 2
└─ LLM Answer with RAG Context (Source: "Cache+LLM (RAG)")
```

**Phase 2: Research Decision**
```
No Direct Cache Hit & No RAG Context
└─ Automatik-LLM decides: Web Research needed?
   ├─ YES → Web Research + Cache Result
   └─ NO  → Pure LLM Answer (Source: "LLM-Trainingsdaten")
```

#### Semantic Deduplication

**Beim Speichern in Vector Cache:**
```
New Research Result → Check for Semantic Duplicates
└─ Distance < 0.3 (semantisch ähnlich)
   └─ ✅ IMMER Update
      - Löscht alten Eintrag
      - Speichert neuen Eintrag
      - Garantiert: Neueste Daten werden verwendet
```

Rein semantische Deduplizierung ohne Zeit-Checks → Konsistentes Verhalten.

#### Cache Distance Thresholds

| Distance | Confidence | Behavior | Example |
|----------|-----------|----------|---------|
| `0.0 - 0.05` | EXACT | Explizite Recherche nutzt Cache | Identische Query |
| `0.05 - 0.5` | HIGH | Direct cache hit | "Python tutorial" vs "Python Anleitung" |
| `0.5 - 1.2` | MEDIUM | RAG candidate (relevance check via LLM) | "Python" vs "FastAPI" |
| `1.2+` | LOW | Cache miss → Research decision | "Python" vs "Weather" |

#### ChromaDB Maintenance Tool

Wartungstool für Vector Cache:
```bash
# Stats anzeigen
python3 chroma_maintenance.py --stats

# Duplikate finden
python3 chroma_maintenance.py --find-duplicates

# Duplikate entfernen (Dry-Run)
python3 chroma_maintenance.py --remove-duplicates

# Duplikate entfernen (Execute)
python3 chroma_maintenance.py --remove-duplicates --execute

# Alte Einträge löschen (> 30 Tage)
python3 chroma_maintenance.py --remove-old 30 --execute
```

#### RAG (Retrieval-Augmented Generation) Mode

**How it works**:
1. Query finds related cache entries (distance 0.5-1.2)
2. Automatik-LLM checks if cached content is relevant to current question
3. Relevant entries are injected as system message: "Previous research shows..."
4. Main LLM combines cached context + training knowledge for enhanced answer

**Example Flow**:
```
User: "Was ist Python?" → Web Research → Cache Entry 1 (d=0.0)
User: "Was ist FastAPI?" → RAG finds Entry 1 (d=0.7)
  → LLM checks: "Python" relevant for "FastAPI"? YES (FastAPI uses Python)
  → Inject Entry 1 as context → Enhanced LLM answer
  → Source: "Cache+LLM (RAG)"
```

**Benefits**:
- Leverages related past research without exact cache hits
- Avoids false context (LLM filters irrelevant entries)
- Multi-level context awareness (cache + conversation history)

#### TTL-Based Cache System (Volatility)

Das Main LLM bestimmt die Cache-Lebensdauer via `<volatility>` Tag in der Antwort:

| Volatility | TTL | Anwendungsfall |
|------------|-----|----------------|
| `DAILY` | 24h | News, aktuelle Ereignisse, "neueste Entwicklungen" |
| `WEEKLY` | 7 Tage | Politische Updates, semi-aktuelle Themen |
| `MONTHLY` | 30 Tage | Statistiken, Reports, weniger volatile Daten |
| `PERMANENT` | ∞ | Zeitlose Fakten ("Was ist Python?") |

**Automatisches Cleanup**: Hintergrund-Task läuft alle 12 Stunden, löscht abgelaufene Einträge.

#### Configuration

Cache-Verhalten in `aifred/lib/config.py`:

```python
# Cache Distance Thresholds
CACHE_DISTANCE_HIGH = 0.5        # < 0.5 = HIGH confidence cache hit
CACHE_DISTANCE_DUPLICATE = 0.3   # < 0.3 = semantic duplicate (wird immer gemerged)
CACHE_DISTANCE_RAG = 1.2         # < 1.2 = ähnlich genug für RAG-Kontext

# TTL (Time-To-Live)
TTL_HOURS = {
    'DAILY': 24,
    'WEEKLY': 168,
    'MONTHLY': 720,
    'PERMANENT': None
}
```

**RAG Relevance Check**: Nutzt Automatik-LLM mit dediziertem Prompt (`prompts/de/rag_relevance_check.txt`)

---

## 🔧 Konfiguration

Alle wichtigen Parameter in `aifred/lib/config.py`:

```python
# History Compression (dynamisch, prozentual)
HISTORY_COMPRESSION_TRIGGER = 0.7    # 70% - Wann komprimieren?
HISTORY_COMPRESSION_TARGET = 0.3     # 30% - Wohin komprimieren?
HISTORY_SUMMARY_RATIO = 0.25         # 25% = 4:1 Kompression
HISTORY_SUMMARY_MIN_TOKENS = 500     # Minimum für Summaries
HISTORY_SUMMARY_TOLERANCE = 0.5      # 50% Überschreitung erlaubt

# Intent-basierte Temperatur
INTENT_TEMPERATURE_FAKTISCH = 0.2    # Faktische Anfragen
INTENT_TEMPERATURE_GEMISCHT = 0.5    # Gemischte Anfragen
INTENT_TEMPERATURE_KREATIV = 1.0     # Kreative Anfragen

# Backend-spezifische Default Models (in BACKEND_DEFAULT_MODELS)
# Ollama: qwen3:4b-instruct-2507-q4_K_M (Automatik), qwen3-vl:8b (Vision)
# vLLM: cpatonn/Qwen3-4B-Instruct-2507-AWQ-4bit, etc.
```

### HTTP Timeout Konfiguration

In `aifred/backends/ollama.py`:
- **HTTP Client Timeout**: 300 Sekunden (5 Minuten)
- Erhöht von 60s für große Research-Anfragen mit 30KB+ Context
- Verhindert Timeout-Fehler bei erster Token-Generation

### Restart-Button Verhalten

Der AIfred Restart-Button startet den systemd-Service neu:
- Führt `systemctl restart aifred-intelligence` aus
- Browser lädt automatisch nach kurzer Verzögerung neu
- Debug-Logs werden geleert, Sessions bleiben erhalten

---

## 📦 Deployment

### Systemd Service

Für produktiven Betrieb als Service sind vorkonfigurierte Service-Dateien im `systemd/` Verzeichnis verfügbar.

**⚠️ WICHTIG**: Die Umgebungsvariable `AIFRED_ENV=prod` **MUSS** gesetzt sein, damit AIfred auf dem MiniPC läuft und nicht auf den Entwicklungsrechner weiterleitet!

#### Schnellinstallation

```bash
# 1. Service-Dateien kopieren
sudo cp systemd/aifred-chromadb.service /etc/systemd/system/
sudo cp systemd/aifred-intelligence.service /etc/systemd/system/

# 2. Services aktivieren und starten
sudo systemctl daemon-reload
sudo systemctl enable aifred-chromadb.service aifred-intelligence.service
sudo systemctl start aifred-chromadb.service aifred-intelligence.service

# 3. Status prüfen
systemctl status aifred-chromadb.service
systemctl status aifred-intelligence.service
```

Siehe [systemd/README.md](systemd/README.md) für Details, Troubleshooting und Monitoring.

#### Service-Dateien (Referenz)

**1. ChromaDB Service** (`systemd/aifred-chromadb.service`):
```ini
[Unit]
Description=AIfred ChromaDB Vector Cache (Docker)
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/mp/Projekte/AIfred-Intelligence/docker
ExecStart=/usr/bin/docker compose up -d chromadb
ExecStop=/usr/bin/docker compose stop chromadb
```

**2. AIfred Intelligence Service** (`systemd/aifred-intelligence.service`):
```ini
[Unit]
Description=AIfred Intelligence Voice Assistant (Reflex Version)
After=network.target ollama.service aifred-chromadb.service
Wants=ollama.service
Requires=aifred-chromadb.service

[Service]
Type=simple
User=__USER__
Group=__USER__
WorkingDirectory=__PROJECT_DIR__
Environment="PATH=__PROJECT_DIR__/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PYTHONUNBUFFERED=1"
ExecStart=__PROJECT_DIR__/venv/bin/python -m reflex run --env prod --frontend-port 3002 --backend-port 8002 --backend-host 0.0.0.0
Restart=always
KillMode=control-group
ExecStopPost=/usr/bin/pkill -f koboldcpp || true
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**⚠️ Wichtig: Ersetze die Platzhalter** `__USER__` und `__PROJECT_DIR__` mit deinen tatsächlichen Werten!

#### Umgebungskonfiguration (.env)

Für Produktions-/Externen Zugriff erstelle eine `.env` Datei im Projektverzeichnis (diese Datei ist in .gitignore und wird NICHT ins Repository gepusht):

```bash
# Umgebungsmodus (erforderlich für Produktion)
AIFRED_ENV=prod

# Backend API URL für externen Zugriff via nginx Reverse Proxy
# Setze dies auf deine externe Domain/IP für HTTPS-Zugriff
AIFRED_API_URL=https://deine-domain.de:8443

# API Keys für Web-Recherche (optional)
BRAVE_API_KEY=dein_brave_api_key
TAVILY_API_KEY=dein_tavily_api_key

# Ollama Konfiguration
OLLAMA_BASE_URL=http://localhost:11434
```

**Warum wird `AIFRED_API_URL` benötigt?**

Das Reflex-Frontend muss wissen, wo das Backend erreichbar ist. Ohne diese Einstellung:
- Das Frontend erkennt automatisch die lokale IP (z.B. `http://192.168.0.252:8002`)
- Das funktioniert für lokalen Netzwerkzugriff, aber scheitert bei externem HTTPS-Zugriff
- Externe Nutzer würden WebSocket-Verbindungsfehler zu `localhost` sehen

Mit `AIFRED_API_URL=https://deine-domain.de:8443`:
- Alle API/WebSocket-Verbindungen gehen über deinen nginx Reverse Proxy
- HTTPS funktioniert korrekt für externen Zugriff
- Lokaler HTTP-Zugriff funktioniert weiterhin

**Warum `--env prod`?**

Das `--env prod` Flag im ExecStart:
- Deaktiviert Vite Hot Module Replacement (HMR) WebSocket
- Verhindert "failed to connect to websocket localhost:3002" Fehler
- Reduziert Ressourcenverbrauch (kein Dev-Server Overhead)
- Kompiliert trotzdem bei Neustart wenn sich Code geändert hat

2. Service aktivieren:
```bash
sudo systemctl daemon-reload
sudo systemctl enable aifred-intelligence
sudo systemctl start aifred-intelligence
```

3. **Optional: Polkit-Regel für Restart ohne sudo**

Für den Restart-Button in der Web-UI ohne Passwort-Abfrage:

`/etc/polkit-1/rules.d/50-aifred-restart.rules`:
```javascript
polkit.addRule(function(action, subject) {
    if ((action.id == "org.freedesktop.systemd1.manage-units") &&
        (action.lookup("unit") == "aifred-intelligence.service" ||
         action.lookup("unit") == "ollama.service") &&
        (action.lookup("verb") == "restart") &&
        (subject.user == "mp")) {
        return polkit.Result.YES;
    }
});
```

---

## 🛠️ Development

### Debug Logs
```bash
tail -f logs/aifred_debug.log
```

### Code-Qualitätsprüfung
```bash
# Syntax-Check
python3 -m py_compile aifred/DATEI.py

# Linting mit Ruff
source venv/bin/activate && ruff check aifred/

# Type-Checking mit mypy
source venv/bin/activate && mypy aifred/ --ignore-missing-imports
```

## 🔨 Troubleshooting

### Häufige Probleme

#### HTTP ReadTimeout bei Research-Anfragen
**Problem**: `httpx.ReadTimeout` nach 60 Sekunden bei großen Recherchen
**Lösung**: Timeout ist bereits auf 300s erhöht in `aifred/backends/ollama.py`
**Falls weiterhin Probleme**: Ollama Service neustarten mit `systemctl restart ollama`

#### Service startet nicht
**Problem**: AIfred Service startet nicht oder stoppt sofort
**Lösung**:
```bash
# Logs prüfen
journalctl -u aifred-intelligence -n 50
# Ollama Status prüfen
systemctl status ollama
```

#### Restart-Button funktioniert nicht
**Problem**: Restart-Button in Web-UI ohne Funktion
**Lösung**: Polkit-Regel prüfen in `/etc/polkit-1/rules.d/50-aifred-restart.rules`

---

## 📚 Dokumentation

Weitere Dokumentation im `docs/` Verzeichnis:
- [Architecture Overview](docs/architecture/)
- [API Documentation](docs/api/)
- [Migration Guide](docs/infrastructure/MIGRATION.md)

---

## 🤝 Contributing

Pull Requests sind willkommen! Für größere Änderungen bitte erst ein Issue öffnen.

---

## 📄 License

MIT License - siehe [LICENSE](LICENSE) file