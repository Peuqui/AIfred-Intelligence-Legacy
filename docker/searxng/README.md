# SearXNG Docker Setup

Self-hosted meta-search engine for AIfred Intelligence.

## Quick Start

```bash
# Start SearXNG
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f

# Stop SearXNG
docker compose down
```

## Access

- **Web Interface**: http://localhost:8888
- **JSON API**: http://localhost:8888/search?q=test&format=json&language=de

## Configuration

- `compose.yml` - Docker Compose configuration
- `settings.yml` - SearXNG settings (search engines, timeout, etc.)

After changing `settings.yml`:
```bash
docker compose restart
```

## Details

- **Port**: 8888 (Host) → 8080 (Container)
- **Auto-restart**: Container starts automatically on reboot
- **Logs**: Max 10MB × 3 files (rotation)
- **Default Language**: German (de)
- **Enabled Engines**: Google, Bing, DuckDuckGo, Wikipedia, News
- **Disabled**: Reddit, Twitter, YouTube (for faster responses)

## Troubleshooting

**Port already in use?**
```bash
# Change port in compose.yml:
ports:
  - "8889:8080"  # instead of 8888
```

**Container not running?**
```bash
docker compose logs searxng
```

**Change secret key?**
```bash
# Generate new secret:
openssl rand -hex 32

# Add to settings.yml:
server:
  secret_key: "your_new_secret_here"
```
