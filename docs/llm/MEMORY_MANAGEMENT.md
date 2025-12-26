# 🧠 Smart Model Loading & Memory Management

## Überblick

AIfred Intelligence verfügt über ein intelligentes Memory-Management-System, das **automatisch** entscheidet, wann Modelle aus dem RAM entladen werden müssen, um Swapping zu vermeiden.

---

## ⚙️ Konfiguration

### Ollama Keep-Alive

**Einstellung:** `15 Minuten` (Standard: 5 Minuten)

**Was es bedeutet:**
- Modelle bleiben 15 Minuten im RAM nach dem letzten Request
- Bei Agent-Recherche (3 KI-Calls in ~2 Min): **Kein Re-Loading!**
- Spart ~0.5s pro Call = **1.5s pro Recherche**

**Konfiguration:**
```bash
# /etc/systemd/system/ollama.service
Environment="OLLAMA_KEEP_ALIVE=15m"
```

---

## 🧩 Komponenten

### 1. `get_available_memory()`

**Was es tut:**
- Liest `/proc/meminfo`
- Gibt **MemAvailable** zurück (nicht MemFree!)
- Berücksichtigt Kernel-Buffer & Caches

**Beispiel-Output:**
```
Verfügbar: 23.5 GB
```

---

### 2. `get_loaded_models_size()`

**Was es tut:**
- Fragt Ollama API: `GET /api/ps`
- Gibt Größe aller aktuell geladenen Modelle zurück
- Zeigt Liste der geladenen Modelle im Log

**Beispiel-Output:**
```
📊 Geladene Modelle: qwen3:1.7b (2.0 GB), qwen3:8b (5.2 GB)
Gesamt: 7.2 GB
```

---

### 3. `unload_all_models()`

**Was es tut:**
- Holt Liste aller geladenen Modelle via `GET /api/ps`
- Entlädt **jedes Modell einzeln** via `POST /api/generate` mit `keep_alive: 0`
- Gibt RAM frei für große Modelle

**Beispiel-Output:**
```
🧹 Entlade aktuell geladene Modelle...
   🗑️ qwen3:1.7b entladen
   🗑️ qwen3:8b entladen
🧹 Alle Modelle aus RAM entladen
```

---

### 4. `get_model_size(model_name)`

**Was es tut:**
- Holt Modellgröße **dynamisch** von Ollama via `ollama list`
- Parst Output und extrahiert Größe (GB/MB)
- Konvertiert zu Bytes für RAM-Berechnungen

**Beispiel-Output:**
```bash
$ ollama list | grep qwen3:8b
qwen3:8b  500a1f067a9f  5.2 GB  42 hours ago

→ get_model_size("qwen3:8b") = 5,583,457,484 bytes (5.2 GB)
```

**Vorteile:**
- ✅ Keine Hard-Codierung!
- ✅ Funktioniert mit ALLEN Modellen (auch neu installierte)
- ✅ Automatische Erkennung von Model-Updates

---

### 5. `smart_model_load(model_name)`

**Das Herzstück!** Intelligente Entscheidungslogik.

#### **Ablauf:**

```
1. Hole Modellgröße DYNAMISCH von Ollama
   ├─ Via get_model_size(model_name)
   ├─ Wenn nicht gefunden (noch nicht gepullt) → ⚠️ Warning, continue
   └─ Wenn gefunden → Weiter zu Schritt 2

2. RAM-Check durchführen
   ├─ Verfügbarer RAM (get_available_memory)
   ├─ Geladene Modelle (get_loaded_models_size)
   └─ Benötigter RAM = Modellgröße × 1.20 (Safety Margin)

3. Entscheidung (REIN RAM-basiert, keine Hard-Codierung!)
   ├─ Wenn: Verfügbar >= Benötigt
   │   └─ ✅ Kein Entladen - Modell passt rein!
   └─ Wenn: Verfügbar < Benötigt
       └─ ⚠️ Entlade geladene Modelle, dann lade neues Modell
```

#### **Safety Margin (20%):**

Ollama braucht **zusätzlichen RAM** während der Inferenz:

```
Modell: 19 GB (Weights)
+ Context Buffer: 0.5 GB
+ KV Cache: 1.5 GB
+ Temporäre Tensoren: 1.0 GB
────────────────────────────
= ~22.8 GB (19 × 1.20)
```

---

## 🎯 Intelligente RAM-basierte Entscheidung

**Keine Hard-Codierung!** Das System entscheidet **rein auf Basis von verfügbarem RAM**, nicht anhand vordefinierter Listen.

### **Wie funktioniert's?**

1. **Modellgröße dynamisch ermitteln** via `ollama list`
   - Beispiel: qwen3:8b → 5.2 GB
   - Beispiel: qwen2.5:32b → 19 GB
   - Beispiel: qwen3:32b → ~20 GB (auch neue Modelle!)

2. **RAM-Check durchführen**
   - Verfügbar: 23.5 GB
   - Benötigt: Modellgröße × 1.20 (mit Safety Margin)

3. **Smart Decision:**
   - Genug RAM? → Lade parallel, kein Entladen
   - Zu wenig RAM? → Entlade erst, dann lade

### **Beispiel: Automatische Unterstützung neuer Modelle**

```bash
# Neues Modell installieren
$ ollama pull qwen3:32b

# Smart Model Loading funktioniert SOFORT!
→ get_model_size("qwen3:32b") = 20 GB
→ RAM-Check: 23.5 GB verfügbar
→ Benötigt: 20 × 1.20 = 24 GB
→ Zu wenig! Entlade andere Modelle
→ ✅ Funktioniert ohne Code-Änderung!
```

**Vorteil:** Alle aktuellen und zukünftigen Modelle werden automatisch unterstützt!

---

## 🎯 Beispiele

### **Szenario 1: Kleines Modell**

```
Verfügbar: 25.5 GB
Geladen: 0 GB
Neues Modell: qwen3:1.7b (1.4 GB)

Berechnung:
  Required: 1.4 GB × 1.20 = 1.68 GB
  Available: 25.5 GB > 1.68 GB ✅

Entscheidung: ✅ Kein Entladen nötig!
```

---

### **Szenario 2: Großes Modell, genug RAM**

```
Verfügbar: 25.5 GB
Geladen: qwen3:1.7b (2.0 GB)
Neues Modell: qwen2.5:14b (9.0 GB)

Berechnung:
  Required: 9.0 GB × 1.20 = 10.8 GB
  Available: 25.5 GB > 10.8 GB ✅

Entscheidung: ✅ Kein Entladen nötig!
  → qwen3:1.7b BLEIBT im RAM
  → qwen2.5:14b wird zusätzlich geladen
  → Beide können parallel laufen!
```

---

### **Szenario 3: Sehr großes Modell, RAM knapp**

```
Verfügbar: 18.0 GB
Geladen: qwen3:8b (5.7 GB)
Neues Modell: qwen2.5:32b (19.0 GB)

Berechnung:
  Required: 19.0 GB × 1.20 = 22.8 GB
  Available: 18.0 GB < 22.8 GB ❌

Entscheidung: ⚠️ Zu wenig RAM!
  → qwen3:8b wird ENTLADEN (5.7 GB frei)
  → RAM nach Entladen: ~23.6 GB
  → qwen2.5:32b wird geladen (19 GB)
  → Genug Platz! ✅ Kein Swapping!
```

---

## 📝 Log-Output

### **Genug RAM (kein Entladen):**

```
📊 Memory Check:
   Verfügbar: 25.5 GB
   Geladen: 2.0 GB
   Neues Modell: qwen2.5:14b (9.0 GB)
✅ Genug RAM! 25.5 GB > 10.8 GB (mit 20% Reserve)
   Kein Entladen nötig - Modell passt rein!
```

### **Zu wenig RAM (Entladen):**

```
📊 Memory Check:
   Verfügbar: 18.0 GB
   Geladen: 5.7 GB
   Neues Modell: qwen2.5:32b (19.0 GB)
⚠️ Zu wenig RAM! 18.0 GB < 22.8 GB (mit 20% Reserve)
🔄 Großes Modell: qwen2.5:32b (19.0 GB)
🧹 Entlade aktuell geladene Modelle (5.7 GB)...
   🗑️ qwen3:8b entladen
🧹 Alle Modelle aus RAM entladen
✅ RAM nach Entladen: 23.6 GB verfügbar
```

---

## 🔧 Wo wird es verwendet?

### **1. Normale Fragen (ohne Agent)**

`chat_audio_step2_ai()` - [aifred_intelligence.py:579](../aifred_intelligence.py#L579)

```python
# Smart Model Loading: Entlade kleine Modelle wenn großes Modell kommt
smart_model_load(model_choice)

# Zeit messen
start_time = time.time()
response = ollama.chat(model=model_choice, messages=messages)
```

### **2. Agent-Recherche**

`perform_agent_research()` - [aifred_intelligence.py:1259](../aifred_intelligence.py#L1259)

```python
# Smart Model Loading: Entlade kleine Modelle wenn großes Modell kommt
smart_model_load(model_choice)

inference_start = time.time()
response = ollama.chat(model=model_choice, messages=messages)
```

---

## ⚠️ Wichtig

### **Warum 20% Safety Margin?**

Ollama benötigt während der Inferenz **mehr RAM** als nur die Model-Weights:
- Context Buffer (Prompt + History)
- KV Cache (Key-Value Cache für Attention)
- Temporäre Tensoren (Zwischenrechnungen)

**Ohne Safety Margin → Swapping → 10x langsamer!**

### **Warum nicht mehr als 20%?**

- 20% ist ein guter Kompromiss
- Zu viel Reserve → Unnötiges Entladen
- Zu wenig Reserve → Risiko von Swapping

---

## 🧪 Testing

**Test-Script:** `test_memory_logic.py` (wird nach Commit gelöscht)

**Manuelle Tests:**

```bash
# RAM-Status prüfen
free -h

# Geladene Modelle prüfen
ollama ps

# Modell manuell entladen
curl -X POST http://localhost:11434/api/generate \
  -d '{"model": "qwen3:8b", "keep_alive": 0}'
```

---

## 📌 Hardware-Anforderungen

**Minimum:**
- 16 GB RAM für kleine Modelle (< 5 GB)
- 32 GB RAM für große Modelle (> 10 GB)

**Empfohlen:**
- 32 GB RAM (wie Aoostar GEM10)
- Ermöglicht paralleles Laden mehrerer Modelle

**Swap:**
- 8 GB Swap als Backup
- **Sollte normalerweise LEER sein!**
- Wenn Swap benutzt wird → Performance-Problem!

---

## 🔍 Troubleshooting

### **Problem: Swap wird benutzt**

```bash
# Swap-Status prüfen
free -h | grep Swap

# Swap leeren (temporär)
sudo swapoff -a && sudo swapon -a
```

### **Problem: Modelle werden nicht entladen**

```bash
# Prüfe Ollama-Logs
journalctl -u ollama.service -n 50

# Prüfe AIfred-Logs
journalctl -u aifred-intelligence.service -n 100 | grep "Memory Check"
```

### **Problem: Performance schlecht trotz genug RAM**

```bash
# Prüfe CPU-Auslastung
htop

# Prüfe Disk I/O (sollte niedrig sein!)
iostat -x 1

# Wenn Disk I/O hoch → Swapping aktiv!
```

---

## 📚 Weiterführende Links

- [Ollama API Dokumentation](https://github.com/ollama/ollama/blob/main/docs/api.md)
- [Linux Memory Management](https://www.kernel.org/doc/html/latest/admin-guide/mm/concepts.html)
- [Model Benchmarks](../benchmarks/BENCHMARK_QUALITY_ANALYSIS.md)

---

**Letzte Aktualisierung:** 2025-12-26
**Version:** 2.0 - Dynamic Model Size Detection (keine Hard-Codierung mehr!)
**Autor:** AI Assistant
