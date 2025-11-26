# ChromaDB v2 API Migration

**Datum:** 2025-11-25
**Version:** ChromaDB 1.3.5 (Client) + chromadb/chroma:latest (Server)

## 🎯 Übersicht

AIfred Intelligence nutzt nun die **ChromaDB API v2** für alle Vektor-Cache-Operationen. Dies stellt sicher, dass der Health-Check mit aktuellen ChromaDB-Versionen kompatibel ist.

## 📋 Änderungen

### 1. Custom Docker Image mit curl

**Neu:** `docker/Dockerfile.chromadb`
```dockerfile
FROM chromadb/chroma:latest

# Install curl for healthcheck
USER root
RUN apt-get update && \
    apt-get install -y curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
```

**Grund:** Das offizielle ChromaDB-Image enthält weder `curl` noch `wget` für Health-Checks.

### 2. Health-Check auf API v2 umgestellt

**Vorher (deprecated):**
```yaml
test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/heartbeat"]
```

**Nachher (aktuell):**
```yaml
test: ["CMD", "curl", "-f", "http://localhost:8000/api/v2/heartbeat"]
```

### 3. Docker Compose v2 Syntax

**docker-compose.yml Änderungen:**
- ✅ `version: '3.8'` entfernt (obsolet in Compose v2)
- ✅ Build-Context für custom Image hinzugefügt
- ✅ Health-Check nutzt curl + API v2

### 4. ChromaDB Client Library aktualisiert

```bash
# Vorher
chromadb==1.3.4

# Nachher
chromadb==1.3.5
```

**Update-Befehl:**
```bash
source venv/bin/activate
pip install --upgrade chromadb
```

## 🚀 Migration Guide

### Schritt 1: Docker Compose v2 installieren

```bash
# Docker Compose Plugin installieren
sudo apt-get update
sudo apt-get install docker-compose-plugin

# Version prüfen
docker compose version  # sollte v2.x.x zeigen
```

### Schritt 2: Container neu bauen und starten

```bash
# Alten Container stoppen
docker rm -f aifred-chromadb

# Neues Image bauen (mit curl)
cd docker
docker compose build chromadb

# Container starten
docker compose up -d chromadb
```

### Schritt 3: Health-Status prüfen

```bash
# Container Status
docker ps | grep chroma
# Erwartet: (healthy) im Status nach ~30 Sekunden

# API v2 testen
curl http://localhost:8000/api/v2/heartbeat
# Erwartet: {"nanosecond heartbeat": 1764058061599536091}
```

### Schritt 4: ChromaDB Client aktualisieren

```bash
source venv/bin/activate
pip install --upgrade chromadb
python -c "import chromadb; print(chromadb.__version__)"
# Erwartet: 1.3.5
```

## 🔧 Troubleshooting

### Problem: "curl: command not found"

**Symptom:** Health-Check zeigt "unhealthy"

**Lösung:** Custom Image neu bauen:
```bash
cd docker
docker compose build --no-cache chromadb
docker compose up -d chromadb
```

### Problem: "unknown command: docker compose"

**Symptom:** `docker compose` funktioniert nicht

**Lösung:** Docker Compose Plugin installieren (siehe Schritt 1)

**Alternative:** Altes `docker-compose` (mit Bindestrich) funktioniert auch:
```bash
sudo apt-get install docker-compose
docker-compose up -d chromadb
```

### Problem: "The v1 API is deprecated"

**Symptom:** Logs zeigen API v1 Warnungen

**Lösung:** Health-Check nutzt bereits API v2. Die Python Client Library handhabt die API-Version automatisch. Ignorieren oder auf ChromaDB Client 1.3.5+ updaten.

## 📊 Vorteile der Migration

- ✅ **Zukunftssicher:** API v2 ist die aktuelle ChromaDB-API
- ✅ **Bessere Health-Checks:** curl-basiert, funktioniert zuverlässig
- ✅ **Keine "unhealthy" Container mehr:** Korrekter Health-Check verhindert false positives
- ✅ **Moderne Syntax:** Docker Compose v2 ist schneller und besser integriert

## 📝 Technische Details

### API v1 vs v2 Unterschiede

**v1 (deprecated):**
```bash
GET /api/v1/heartbeat
# Response: 200 OK (leer)
```

**v2 (aktuell):**
```bash
GET /api/v2/heartbeat
# Response: {"nanosecond heartbeat": 1764058061599536091}
```

### Health-Check Intervalle

```yaml
healthcheck:
  interval: 30s      # Prüfung alle 30 Sekunden
  timeout: 10s       # Timeout nach 10 Sekunden
  retries: 3         # 3 Fehlversuche bis "unhealthy"
  start_period: 10s  # 10 Sekunden Anlaufzeit beim Start
```

**Ergebnis:** Container wird nach 3 fehlgeschlagenen Checks als "unhealthy" markiert.

## 🔗 Weiterführende Links

- [ChromaDB Documentation](https://docs.trychroma.com/)
- [Docker Compose v2](https://docs.docker.com/compose/migrate/)
- [AIfred Docker README](../docker/README.md)

---

**Letzte Aktualisierung:** 2025-11-25
**Autor:** Claude Code
**Status:** ✅ Produktiv
