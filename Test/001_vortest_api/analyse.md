# Test 001: Vortest API-Workflow

## Konfiguration
- **Datum**: 2025-12-31 11:12
- **Modelle**:
  - AIfred: qwen3:30b-a3b-instruct-2507-q8_0
  - Sokrates: nemotron-3-nano:30b-a3b-q4_K_M
  - Salomo: gpt-oss:120b
- **Multi-Agent**: auto_consensus, majority (2/3), max 2 rounds
- **Test-Query**: "Recherchiere, ob wir lieber zum Phantasialand oder in den Heidepark fahren sollen"
- **Session-ID**: c2385b757f4a68e087d1ed920cbce0db

## Zielsetzung
Validierung des API-Workflows:
1. Message-Injektion via `/api/chat/inject`
2. Status-Polling via `/api/chat/status`
3. Completion-Detection

## Durchführung

### Schritt 1: Session vorbereiten
```bash
# Chat-Historie löschen für saubere Bedingungen
curl -X POST http://localhost:8002/api/chat/clear \
  -H "Content-Type: application/json" \
  -d '{"device_id": "c2385b757f4a68e087d1ed920cbce0db"}'

# Response: {"success":true,"message":"Chat session c2385b75... cleared"}
```

### Schritt 2: Nachricht injizieren
```bash
# Startzeitpunkt: 2025-12-31 11:12:38
curl -X POST http://localhost:8002/api/chat/inject \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Recherchiere, ob wir lieber zum Phantasialand oder in den Heidepark fahren sollen",
    "device_id": "c2385b757f4a68e087d1ed920cbce0db"
  }'

# Response:
{
    "success": true,
    "message": "Message queued for browser processing",
    "session_id": "c2385b757f4a68e087d1ed920cbce0db",
    "queued": true
}
```

✅ **Erfolg**: Nachricht wurde erfolgreich in Queue eingestellt

### Schritt 3: Status pollen
```bash
# Poll #1 (0s nach Injection)
curl "http://localhost:8002/api/chat/status?device_id=c2385b757f4a68e087d1ed920cbce0db"

# Response:
{
    "is_generating": false,
    "message_count": 0,
    "session_id": "c2385b757f4a68e087d1ed920cbce0db"
}
```

### Schritt 4: Session-Datei prüfen
```json
{
    "data": {
        "pending_message": null,
        "chat_history": [],
        "llm_history": [],
        "debug_messages": [],
        "is_generating": false
    },
    "created_at": "2025-12-30T19:04:35.677658",
    "last_seen": "2025-12-31T11:12:38.009808",
    "device_id": "c2385b757f4a68e087d1ed920cbce0db"
}
```

## Beobachtungen

### Problem: Nachricht nicht verarbeitet
- `pending_message` ist `null` (nicht mehr in Queue)
- `chat_history` ist leer (keine Verarbeitung erfolgt)
- `is_generating` ist `false`
- **Hypothese**: Kein aktiver Browser mit dieser Session

### API-Mechanismus (aus Codebase-Analyse)
1. `/api/chat/inject` setzt `pending_message` in Session-JSON
2. Setzt `.pending` Flag-Datei
3. Browser pollt (1s-Timer via `rx.moment(interval=1000)`)
4. Browser liest `pending_message` aus
5. Browser startet Pipeline
6. `pending_message` wird auf `null` gesetzt

**Aktueller Status**: Nachricht wurde in Queue gesetzt, aber nicht vom Browser abgeholt

## Nächste Schritte

🔍 **Zu klären**:
1. Ist ein Browser mit Session `c2385b757f4a68e087d1ed920cbce0db` offen?
2. Falls ja: Warum wird `pending_message` nicht abgeholt?
3. Falls nein: Muss Browser aktiv sein für API-Tests?

📋 **Alternative Ansätze**:
1. Browser öffnen und Session laden
2. Neue Session erstellen durch Browser-Aufruf
3. Mechanismus anders testen (direkt Session-File manipulieren)

## Status-Update (11:15)

✅ **Nachricht vom Browser abgeholt**
✅ **Inferenz gestartet**
- `is_generating: true`
- `message_count: 2` (User + erste Response)
- Monitoring läuft im Hintergrund

⏳ **Wartend auf Completion** (Multi-Agent-Dialektik läuft)
