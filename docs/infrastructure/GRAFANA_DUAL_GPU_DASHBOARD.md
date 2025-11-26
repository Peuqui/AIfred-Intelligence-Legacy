# Grafana Dual-GPU Dashboard Update

## Datum: 2025-11-26

## Zusammenfassung

System Monitoring Dashboard wurde aktualisiert um beide NVIDIA Tesla P40 GPUs separat anzuzeigen statt nur GPU 0.

---

## Änderungen

### 1. Gauge Panels → Bar Gauges mit beiden GPUs

**Vorher:**
- Kreisförmige Gauges (Doughnut-Style)
- Nur GPU 0 angezeigt
- Keine Information über GPU 1

**Nachher:**
- Horizontale Bar Gauges
- Beide GPUs übereinander in jedem Panel
- GPU 0 = Grün, GPU 1 = Blau
- Klarere Übersicht bei Dual-GPU Setup

### 2. Time-Series Panels mit beiden GPUs

**Betroffene Panels:**
- 📈 P40 Power Over Time
- 📈 P40 Temp Over Time
- 📈 P40 GPU % Over Time
- 📈 P40 VRAM Over Time

**Änderung:**
- Jedes Panel zeigt jetzt 2 Linien (eine pro GPU)
- GPU 0 = Grün
- GPU 1 = Blau
- Gleiche Y-Achse für direkten Vergleich

---

## Visuelle Darstellung

### Bar Gauges (Neue Ansicht)

```
┌─────────────────────────────────────────┐
│ 🎮 VRAM                                 │
├─────────────────────────────────────────┤
│ GPU 0  ████████████░░░░░░░░  14.0 GB   │
│ GPU 1  ████████████░░░░░░░░  14.2 GB   │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ ⚡ Power                                │
├─────────────────────────────────────────┤
│ GPU 0  ███░░░░░░░░░░░░░░░░░  50.6 W    │
│ GPU 1  ███░░░░░░░░░░░░░░░░░  51.0 W    │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ 🌡️ Temp                                │
├─────────────────────────────────────────┤
│ GPU 0  ████░░░░░░░░░░░░░░░░  39°C      │
│ GPU 1  █████░░░░░░░░░░░░░░░  42°C      │
└─────────────────────────────────────────┘
```

### Time-Series Graphs (Neue Ansicht)

```
📈 P40 VRAM Over Time
┌─────────────────────────────────────────┐
│ 20 GB ┤                                 │
│       │     ┌────────────────────────┐  │
│ 15 GB ┤─────┤ GPU 0 (grün)           │  │
│       │     └──────────────┬─────────┘  │
│ 10 GB ┤                    │            │
│       │         ┌──────────┴─────────┐  │
│  5 GB ┤─────────┤ GPU 1 (blau)       │  │
│       │         └────────────────────┘  │
│  0 GB ┤                                 │
└─────────────────────────────────────────┘
```

---

## Technische Details

### Prometheus Queries

**Bar Gauges** - Zwei separate Queries pro Panel:

```promql
# Query A - GPU 0
nvidia_gpu_memory_used_bytes{gpu="0_Tesla_P40"}

# Query B - GPU 1
nvidia_gpu_memory_used_bytes{gpu="1_Tesla_P40"}
```

**Time-Series** - Gleicher Ansatz:

```promql
# Query A
nvidia_gpu_utilization_percent{gpu="0_Tesla_P40"}

# Query B
nvidia_gpu_utilization_percent{gpu="1_Tesla_P40"}
```

### Farbkodierung

Konsistente Farben über alle Panels:

```json
{
  "fieldConfig": {
    "overrides": [
      {
        "matcher": {"id": "byName", "options": "GPU 0"},
        "properties": [
          {"id": "color", "value": {"fixedColor": "green", "mode": "fixed"}}
        ]
      },
      {
        "matcher": {"id": "byName", "options": "GPU 1"},
        "properties": [
          {"id": "color", "value": {"fixedColor": "blue", "mode": "fixed"}}
        ]
      }
    ]
  }
}
```

---

## Geänderte Panels

### NVIDIA Tesla P40 Section

| Panel | Typ | GPU 0 | GPU 1 | Änderung |
|-------|-----|-------|-------|----------|
| 🎮 VRAM | Bar Gauge | ✅ Grün | ✅ Blau | gauge → bargauge |
| ⚡ Power | Bar Gauge | ✅ Grün | ✅ Blau | gauge → bargauge |
| 🌡️ Temp | Bar Gauge | ✅ Grün | ✅ Blau | gauge → bargauge |
| 📊 GPU % | Bar Gauge | ✅ Grün | ✅ Blau | gauge → bargauge |
| ⚙️ GPU Clock | Bar Gauge | ✅ Grün | ✅ Blau | gauge → bargauge |
| 💾 Mem Clock | Bar Gauge | ✅ Grün | ✅ Blau | gauge → bargauge |
| 🎯 P-State | Bar Gauge | ✅ Grün | ✅ Blau | gauge → bargauge |

### GPU Details (Over Time)

| Panel | Linien | Änderung |
|-------|--------|----------|
| 📈 P40 Power Over Time | GPU 0 (grün) + GPU 1 (blau) | +1 Serie |
| 📈 P40 Temp Over Time | GPU 0 (grün) + GPU 1 (blau) | +1 Serie |
| 📈 P40 GPU % Over Time | GPU 0 (grün) + GPU 1 (blau) | +1 Serie |
| 📈 P40 VRAM Over Time | GPU 0 (grün) + GPU 1 (blau) | +1 Serie |

---

## Implementierung

### Script 1: Time-Series Panels (Dual-GPU Linien)

```python
def add_gpu1_series(panel):
    """Add GPU 1 as second series to time-series panels"""
    if panel.get('type') != 'timeseries':
        return False

    targets = panel.get('targets', [])
    if not targets:
        return False

    # Clone first target for GPU 1
    first_target = targets[0].copy()
    expr = first_target.get('expr', '')

    # Replace GPU 0 with GPU 1
    gpu1_expr = expr.replace('gpu="0_Tesla_P40"', 'gpu="1_Tesla_P40"')

    gpu1_target = first_target.copy()
    gpu1_target['expr'] = gpu1_expr
    gpu1_target['legendFormat'] = 'GPU 1'
    gpu1_target['refId'] = 'B'

    # Add color overrides
    panel['fieldConfig']['overrides'] = [
        {
            "matcher": {"id": "byName", "options": "GPU 0"},
            "properties": [{"id": "color", "value": {"fixedColor": "green", "mode": "fixed"}}]
        },
        {
            "matcher": {"id": "byName", "options": "GPU 1"},
            "properties": [{"id": "color", "value": {"fixedColor": "blue", "mode": "fixed"}}]
        }
    ]

    targets.append(gpu1_target)
    return True
```

### Script 2: Gauge → Bar Gauge Conversion

```python
def convert_to_bar_gauge(panel):
    """Convert circular gauge to horizontal bar gauge with both GPUs"""
    if panel.get('type') != 'gauge':
        return False

    # Get existing query
    targets = panel.get('targets', [])
    first_target = targets[0]
    expr = first_target.get('expr', '')

    # Create queries for both GPUs
    gpu0_expr = expr.replace('gpu=~".*Tesla.*"', 'gpu="0_Tesla_P40"')
    gpu1_expr = gpu0_expr.replace('gpu="0_Tesla_P40"', 'gpu="1_Tesla_P40"')

    # Convert to bar gauge
    panel['type'] = 'bargauge'

    panel['targets'] = [
        {**first_target, 'expr': gpu0_expr, 'legendFormat': 'GPU 0', 'refId': 'A'},
        {**first_target, 'expr': gpu1_expr, 'legendFormat': 'GPU 1', 'refId': 'B'}
    ]

    # Configure horizontal bars
    panel['options'] = {
        'orientation': 'horizontal',
        'displayMode': 'gradient',
        'showUnfilled': True,
        'namePlacement': 'left'
    }

    return True
```

---

## Deployment

### Manuelle Schritte

1. **Dashboard exportieren:**
```bash
docker exec grafana cat /var/lib/grafana/dashboards/node-exporter.json > backup.json
```

2. **Modifikationen anwenden:**
```bash
python3 modify_dashboard.py
```

3. **Dashboard zurückkopieren:**
```bash
docker cp node-exporter-modified.json grafana:/var/lib/grafana/dashboards/node-exporter.json
docker restart grafana
```

### Automatisiertes Update

Siehe Python Scripts in `/tmp/`:
- `/tmp/node-exporter-original.json` - Original Backup
- `/tmp/node-exporter-modified.json` - Mit Dual-GPU Time-Series
- `/tmp/node-exporter-bargauge.json` - Final mit Bar Gauges

---

## Testing

### Verifizierung

**1. Bar Gauges:**
- [x] Beide GPUs angezeigt (GPU 0 + GPU 1)
- [x] Horizontale Balken statt Kreise
- [x] GPU 0 = Grün, GPU 1 = Blau
- [x] Werte korrekt (z.B. VRAM ~14 GB pro GPU)

**2. Time-Series:**
- [x] Zwei Linien pro Graph
- [x] GPU 0 = Grüne Linie
- [x] GPU 1 = Blaue Linie
- [x] Legenden korrekt beschriftet

**3. Metriken:**
```bash
# Test: Beide GPUs exportieren Metriken
curl -s http://localhost:9194/metrics | grep 'nvidia_gpu_memory_used_bytes'

# Erwartete Ausgabe:
# nvidia_gpu_memory_used_bytes{gpu="0_Tesla_P40"} 1.451229184e+010
# nvidia_gpu_memory_used_bytes{gpu="1_Tesla_P40"} 1.475346432e+010
```

---

## Vorteile

### Übersichtlichkeit
- ✅ Beide GPUs auf einen Blick
- ✅ Direkter Vergleich zwischen GPU 0 und GPU 1
- ✅ Sofort erkennbar wenn eine GPU mehr Last hat

### Monitoring
- ✅ Load-Balancing sichtbar (sollte 50/50 bei MoE sein)
- ✅ Temperaturunterschiede erkennbar
- ✅ VRAM-Verteilung transparent

### Debugging
- ✅ Probleme mit einzelner GPU sofort sichtbar
- ✅ Ungleiche Auslastung erkennbar
- ✅ Hilfreich für Dual-GPU Optimierung

---

## Use Cases

### 1. Ollama mit 50/50 Model Split

**Erwartetes Verhalten:**
```
VRAM:
  GPU 0: ████████████░░░ 12 GB  (50% Model)
  GPU 1: ████████████░░░ 12 GB  (50% Model)

GPU %:
  GPU 0: ████████░░░░░░░ 45%
  GPU 1: █████████░░░░░░ 50%
```

### 2. KoboldCpp mit Single-GPU

**Erwartetes Verhalten:**
```
VRAM:
  GPU 0: ████████████████ 18 GB  (Model + Context)
  GPU 1: ░░░░░░░░░░░░░░░░  0 GB  (Idle)

GPU %:
  GPU 0: ████████████████ 95%
  GPU 1: ░░░░░░░░░░░░░░░░  0%
```

### 3. Multi-Agent Setup (Zukunft)

**Erwartetes Verhalten:**
```
VRAM:
  GPU 0: ████████████░░░ 14 GB  (Agent A)
  GPU 1: ████████████░░░ 14 GB  (Agent B)

GPU %:
  GPU 0: ████████░░░░░░░ 40%    (Agent A aktiv)
  GPU 1: ██░░░░░░░░░░░░░ 10%    (Agent B idle)
```

---

## Bekannte Probleme

### APU vs NVIDIA Trennung

**Aktuell:**
- GPU Frequency und GPU Voltage zeigen AMD APU (integrierte Grafik)
- VRAM Dedicated / GTT Dynamic zeigen AMD APU
- Vermischt mit NVIDIA Panels

**TODO:**
- [ ] APU Panels in separaten Collapsible Bereich verschieben
- [ ] Klare Überschrift: "AMD APU Graphics (Integrated)"
- [ ] Von NVIDIA Tesla P40 Section trennen

---

## Maintenance

### Bei Hinzufügen weiterer GPUs

Falls ein 3. GPU hinzugefügt wird:

```python
# Query C hinzufügen
gpu2_target = {
    'expr': 'nvidia_gpu_memory_used_bytes{gpu="2_Tesla_P40"}',
    'legendFormat': 'GPU 2',
    'refId': 'C'
}

# Farbe hinzufügen
{
    "matcher": {"id": "byName", "options": "GPU 2"},
    "properties": [{"id": "color", "value": {"fixedColor": "orange", "mode": "fixed"}}]
}
```

### Dashboard Backup

**Automatisches Backup:**
```bash
# Cronjob für tägliches Backup
0 2 * * * docker exec grafana cat /var/lib/grafana/dashboards/node-exporter.json > /backup/grafana/node-exporter-$(date +\%Y\%m\%d).json
```

---

## Related Files

- `/var/lib/docker/volumes/.../grafana/dashboards/node-exporter.json` - Dashboard Definition
- `/tmp/node-exporter-*.json` - Backup & Modified Versionen
- `docker-compose.yml` - Grafana Container Config
- Prometheus Config - Scrape Targets für nvidia-gpu-exporter

---

## Changelog

### 2025-11-26 - Initial Dual-GPU Update
- Converted 7 gauge panels to bar gauges
- Added GPU 1 to 4 time-series panels
- Implemented green/blue color scheme
- Created documentation

---

## Sources & References

- [Grafana Bar Gauge Documentation](https://grafana.com/docs/grafana/latest/panels-visualizations/visualizations/bar-gauge/)
- [Prometheus NVIDIA GPU Exporter](https://github.com/utkuozdemir/nvidia_gpu_exporter)
- NVIDIA SMI Metrics Format

---

**Document Version**: 1.0
**Last Updated**: 2025-11-26
**Author**: System Monitoring Dashboard Update for Dual Tesla P40 Setup
