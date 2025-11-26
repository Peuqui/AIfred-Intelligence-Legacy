# KoboldCPP Setup-Guide für 2x Tesla P40 mit Context-Offloading

## 🎯 Ausgangssituation

**Hardware:**
- 2x Tesla P40 (je 24GB VRAM)
- GPU 0: Oculink-Anschluss (8GB/s Bandbreite)
- GPU 1: USB4-Anschluss (5GB/s Bandbreite)
- Mini-PC unter Linux

**Problem:**
- 70B Modelle verteilt auf beide GPUs: **sehr langsam** (hohe Inter-Card-Kommunikation)
- 33B Modelle auf einer GPU: nur **2-4k Context** verfügbar (zu wenig)

**Lösung:**
KoboldCPP mit Context-Offloading: **Model auf GPU0, Context auf GPU1**

---

## 💡 Warum Context-Offloading?

### Traditionelle Multi-GPU Setups (OHNE Context-Offloading)
```
GPU 0 (Oculink 8GB/s):  Layers 1-35  ←→  Layers 36-70  :GPU 1 (USB4 5GB/s)
                             ↑                    ↓
                          BOTTLENECK: Jeder Token muss beide GPUs durchlaufen!
```
- **Problem**: Jeder Token muss sequentiell durch **beide** GPUs
- **Bandbreite**: Limitiert durch langsamstes Glied (USB4: 5GB/s)
- **Latenz**: Addiert sich bei jedem Layer-Übergang
- **Ergebnis**: ~3-5 tok/s bei 70B Modellen

### Mit Context-Offloading (KoboldCPP)
```
GPU 0 (Oculink 8GB/s):  [ALLE Model-Layers]  →  Tokens generieren
                                ↓
GPU 1 (USB4 5GB/s):     [KV-Cache Speicher]  ←  Context Window
```
- **Vorteil**: Model bleibt auf einer GPU (keine Layer-Übergänge)
- **Context-Daten**: Werden separat auf GPU1 gespeichert
- **Kommunikation**: Nur beim Abruf von Context (nicht bei jedem Token!)
- **Ergebnis**: ~25-35 tok/s bei 30B Modellen

---

## 📊 Performance-Vergleich

| Setup | Model Size | Context | Speed | VRAM GPU0 | VRAM GPU1 |
|-------|-----------|---------|-------|-----------|-----------|
| **Ollama 70B Split** | 70B | 8K | 3-5 tok/s | 22GB | 22GB |
| **Ollama 30B Single** | 30B | 8K | 20-25 tok/s | 23GB | 0GB |
| **KoboldCPP 30B Split** | 30B | 8K | 15-20 tok/s | 12GB | 12GB |
| **KoboldCPP 30B + Context** | 30B | 32K | **25-35 tok/s** | 20GB | 8GB |

**Vorteil KoboldCPP**: Bei gleicher Modellgröße (30B) ermöglicht Context-Offloading **4x mehr Context** (32K vs 8K) bei gleicher oder besserer Performance.

**Empfehlung**: KoboldCPP 30B mit Context-Offloading für maximalen Context bei voller GPU-Geschwindigkeit.

---

## 🔧 Installation

### 1. KoboldCPP Installieren

#### Option A: Binary Release (Empfohlen)
```bash
cd ~
wget https://github.com/LostRuins/koboldcpp/releases/latest/download/koboldcpp-linux-x64-cuda1150
chmod +x koboldcpp-linux-x64-cuda1150
sudo mv koboldcpp-linux-x64-cuda1150 /usr/local/bin/koboldcpp
```

#### Option B: Aus Source kompilieren
```bash
cd ~
git clone https://github.com/LostRuins/koboldcpp
cd koboldcpp
make LLAMA_CUBLAS=1

# Optional: Nach /usr/local/bin verschieben
sudo cp koboldcpp /usr/local/bin/
```

### 2. Modell herunterladen (GGUF Format)

**Empfohlene Modelle für 2x P40 Setup:**

```bash
# Qwen3-30B (Empfohlen - beste Balance)
huggingface-cli download bartowski/Qwen3-30B-Instruct-2507-GGUF \
    Qwen3-30B-Instruct-2507-Q4_K_M.gguf \
    --local-dir ~/models/

# Alternative: Qwen2.5-32B
huggingface-cli download bartowski/Qwen2.5-32B-Instruct-GGUF \
    Qwen2.5-32B-Instruct-Q4_K_M.gguf \
    --local-dir ~/models/
```

**Wichtig**: Verwende **Q4_K_M** Quantisierung für beste Balance zwischen Qualität und VRAM.

---

## 🚀 KoboldCPP Starten

### Basis-Konfiguration (ohne AIfred Integration)

```bash
koboldcpp ~/models/Qwen3-30B-Instruct-2507-Q4_K_M.gguf \
    --port 5001 \
    --contextsize 32768 \
    --gpulayers 40 \
    --usecublas \
    --contextoffload \
    --tensor_split 1,0 \
    --flashattention \
    --quantkv
```

**Parameter-Erklärung:**
- `--port 5001`: API Port (Standard: 5001, Ollama: 11434, vLLM: 8000)
- `--contextsize 32768`: Context Window (32K tokens)
- `--gpulayers 40`: Anzahl Layers auf GPU (30B ≈ 40 layers, passt auf 24GB)
- `--usecublas`: CUDA aktivieren (NVIDIA GPUs)
- `--contextoffload`: **WICHTIG**: Context auf GPU1 auslagern
- `--tensor_split 1,0`: Model nur auf GPU0 (1 = 100%, 0 = 0%)
- `--flashattention`: Flash Attention aktivieren (schneller, weniger VRAM)
- `--quantkv`: Quantized KV Cache (weniger VRAM für Context)

### Erweiterte Konfiguration (maximale Performance)

```bash
koboldcpp ~/models/Qwen3-30B-Instruct-2507-Q4_K_M.gguf \
    --port 5001 \
    --host 0.0.0.0 \
    --contextsize 40960 \
    --gpulayers 42 \
    --usecublas \
    --contextoffload \
    --tensor_split 1,0 \
    --flashattention \
    --quantkv \
    --threads 8 \
    --batch 512 \
    --noblas
```

**Zusätzliche Parameter:**
- `--host 0.0.0.0`: Server von außen erreichbar (für Netzwerk-Zugriff)
- `--contextsize 40960`: Maximaler Context (40K tokens, volle Qwen3-Kapazität)
- `--gpulayers 42`: Mehr Layers für bessere Performance
- `--threads 8`: CPU Threads für Prompt-Processing
- `--batch 512`: Batch Size für schnelleres Processing
- `--noblas`: Deaktiviert CPU BLAS (alles auf GPU)

---

## 🔌 AIfred Integration

### 1. KoboldCPP Manager verwenden (Python)

```python
from aifred.lib.koboldcpp_manager import get_koboldcpp_manager

# Manager abrufen
manager = get_koboldcpp_manager(port=5001)

# Server starten mit Context-Offloading
await manager.start(
    model_path="~/models/Qwen3-30B-Instruct-2507-Q4_K_M.gguf",
    context_size=32768,
    gpu_layers=40,
    context_offload=True,  # Context auf GPU1
    tensor_split="1,0",     # Model auf GPU0
    flash_attention=True,
    quantized_kv=True
)

# Health Check
is_healthy = await manager.health_check()
print(f"Server Status: {'OK' if is_healthy else 'ERROR'}")

# Server stoppen
await manager.stop()
```

### 2. Backend-Konfiguration in AIfred

In [aifred/lib/config.py](../aifred/lib/config.py) oder [aifred/lib/settings.py](../aifred/lib/settings.py):

```python
from aifred.backends import BackendFactory

# KoboldCPP Backend erstellen
backend = BackendFactory.create(
    backend_type="koboldcpp",
    base_url="http://localhost:5001/v1"
)

# Modell auflisten
models = await backend.list_models()
print(f"Available models: {models}")

# Chat-Anfrage senden
from aifred.backends.base import LLMMessage, LLMOptions

messages = [
    LLMMessage(role="system", content="Du bist ein hilfreicher Assistent."),
    LLMMessage(role="user", content="Erkläre mir Quantencomputer in 3 Sätzen.")
]

response = await backend.chat(
    model=models[0],
    messages=messages,
    options=LLMOptions(
        temperature=0.7,
        num_ctx=32768,
        num_predict=500
    )
)

print(response.text)
print(f"Speed: {response.tokens_per_second:.1f} tok/s")
```

---

## 🎛️ Optimierungs-Tipps

### GPU Layer Kalibrierung

Die optimale Anzahl an `--gpulayers` hängt von der VRAM-Größe ab:

```bash
# Test 1: Zu wenig Layers (→ CPU wird genutzt, langsam)
--gpulayers 30  # 18GB VRAM, aber langsam

# Test 2: Optimal (→ alle Layers auf GPU0)
--gpulayers 40  # 20GB VRAM, schnell

# Test 3: Zu viel (→ OOM Fehler)
--gpulayers 45  # 25GB VRAM needed → CRASH
```

**Empfehlung**: Starte mit `--gpulayers 40`, erhöhe schrittweise bis VRAM voll ist.

### Context Size vs. VRAM

```bash
# Kleiner Context (weniger VRAM auf GPU1)
--contextsize 16384  # 16K → ~4GB VRAM auf GPU1

# Großer Context (mehr VRAM auf GPU1)
--contextsize 40960  # 40K → ~10GB VRAM auf GPU1

# Maximaler Context (nutzt fast gesamte GPU1)
--contextsize 65536  # 64K → ~16GB VRAM auf GPU1
```

**Wichtig**: Mit `--quantkv` (Quantized KV Cache) halbiert sich der VRAM-Bedarf!

### Bandbreiten-Optimierung

```bash
# Tensor Split: Nur GPU0 für Model (Context auf GPU1)
--tensor_split 1,0  # ← EMPFOHLEN für 2x P40

# Alternativen (nicht empfohlen):
--tensor_split 0.9,0.1  # 90% GPU0, 10% GPU1 (Layers überlappen)
--tensor_split 0.5,0.5  # 50/50 Split (wie Ollama, LANGSAM)
```

---

## 📈 Monitoring & Debugging

### GPU-Auslastung überwachen

```bash
# Terminal 1: KoboldCPP starten
koboldcpp ~/models/Qwen3-30B-Instruct-2507-Q4_K_M.gguf --contextoffload ...

# Terminal 2: GPU Monitor
watch -n 1 nvidia-smi
```

**Erwartete Werte:**
- **GPU 0**: 90-100% Auslastung, ~20GB VRAM (Model)
- **GPU 1**: 10-30% Auslastung, ~8GB VRAM (Context)

### Performance-Test

```bash
# Test-Request via curl
curl -s http://localhost:5001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-30b",
    "messages": [
      {"role": "user", "content": "Schreibe eine lange Geschichte über KI (500 Wörter)."}
    ],
    "max_tokens": 500,
    "temperature": 0.7
  }' | jq '.usage'
```

**Erwartete Performance:**
- **Prompt Processing**: 500-1000 tok/s
- **Generation**: 25-35 tok/s
- **Context Handling**: Keine Slowdowns bis 32K tokens

---

## 🔍 Troubleshooting

### Problem 1: KoboldCPP startet nicht

**Symptom:**
```
CUDA_ERROR_OUT_OF_MEMORY: out of memory
```

**Lösung:**
```bash
# 1. VRAM freigeben
sudo fuser -k 5001/tcp  # Alte KoboldCPP-Prozesse beenden
nvidia-smi  # Prüfen ob VRAM frei ist

# 2. Layers reduzieren
--gpulayers 35  # Statt 40

# 3. Context reduzieren
--contextsize 24576  # 24K statt 32K
```

### Problem 2: Langsame Generierung

**Symptom:**
- Nur 5-10 tok/s statt 25-35 tok/s

**Lösung:**
```bash
# 1. Prüfen ob Context-Offloading aktiv ist
# In KoboldCPP Logs nach "context offload: enabled" suchen

# 2. Flash Attention aktivieren
--flashattention

# 3. Quantized KV aktivieren
--quantkv

# 4. Tensor Split korrigieren
--tensor_split 1,0  # Nicht 0.5,0.5!
```

### Problem 3: GPU1 wird nicht genutzt

**Symptom:**
- GPU1 zeigt 0GB VRAM-Nutzung
- Context-Fehler bei langen Konversationen

**Lösung:**
```bash
# Context-Offloading explizit aktivieren
--contextoffload

# Prüfen ob beide GPUs sichtbar sind
nvidia-smi -L
# Erwartete Ausgabe:
# GPU 0: Tesla P40 (UUID: ...)
# GPU 1: Tesla P40 (UUID: ...)
```

### Problem 4: API-Fehler (404 Not Found)

**Symptom:**
```
ConnectionError: http://localhost:5001/v1/models not found
```

**Lösung:**
```bash
# 1. Prüfen ob Server läuft
curl http://localhost:5001/v1/models

# 2. Korrekten Port verwenden
--port 5001  # Standard für KoboldCPP

# 3. OpenAI-kompatible API aktivieren
# KoboldCPP aktiviert diese automatisch bei --port Angabe
```

---

## 📚 Weiterführende Ressourcen

- **KoboldCPP GitHub**: https://github.com/LostRuins/koboldcpp
- **Llama.cpp Dokumentation**: https://github.com/ggerganov/llama.cpp
- **GGUF Model Hub**: https://huggingface.co/models?library=gguf
- **Qwen3 Models**: https://huggingface.co/Qwen
- **Tesla P40 Specs**: https://www.nvidia.com/en-us/data-center/tesla-p40/

---

## ✅ Checkliste für optimales Setup

- [ ] KoboldCPP Binary installiert (`/usr/local/bin/koboldcpp`)
- [ ] GGUF Model heruntergeladen (Q4_K_M Quantisierung)
- [ ] Beide GPUs erkannt (`nvidia-smi -L`)
- [ ] Context-Offloading aktiviert (`--contextoffload`)
- [ ] Tensor Split korrekt (`--tensor_split 1,0`)
- [ ] Flash Attention aktiviert (`--flashattention`)
- [ ] Quantized KV aktiviert (`--quantkv`)
- [ ] Performance-Test durchgeführt (25-35 tok/s)
- [ ] GPU-Monitoring aktiv (`watch nvidia-smi`)

---

**Stand**: November 2025
**Version**: 1.0
**Autor**: AIfred Intelligence Team
