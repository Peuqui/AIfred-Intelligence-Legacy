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

(weitere TODOs hier einfügen)
