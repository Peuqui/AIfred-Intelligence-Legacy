# Docker Services for AIfred Intelligence

This directory contains all Docker services required by AIfred Intelligence.

## Services

### 1. ChromaDB (Essential)
Vector database for semantic caching of web research results.

**Start:**
```bash
docker compose up -d chromadb
```

**Stop:**
```bash
docker compose stop chromadb
```

**Check status:**
```bash
docker compose ps
```

### 2. SearXNG (Optional)
Local meta-search engine for web research.

**Start (with ChromaDB):**
```bash
docker compose --profile full up -d
```

**Access:** http://localhost:8888

## Management

### Start all services
```bash
# ChromaDB only (default)
docker compose up -d chromadb

# ChromaDB + SearXNG
docker compose --profile full up -d
```

### Stop all services
```bash
docker compose down
```

### View logs
```bash
# All services
docker compose logs -f

# ChromaDB only
docker compose logs -f chromadb

# SearXNG only
docker compose logs -f searxng
```

### Reset ChromaDB cache
```bash
# Option 1: Restart container + delete data
docker compose stop chromadb
cd ..
rm -rf aifred_vector_cache/
cd docker
docker compose up -d chromadb

# Option 2: Delete collection only (see main README)
```

## Network

All services run in the shared `aifred-network`, allowing inter-service communication.

- ChromaDB: `http://localhost:8000`
- SearXNG: `http://localhost:8888` (only with `--profile full`)

## Volumes

- `../aifred_vector_cache/` - Persistent storage for ChromaDB
- `./searxng/settings.yml` - SearXNG configuration
