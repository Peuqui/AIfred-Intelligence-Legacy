FROM python:3.12-slim

# Install system dependencies (including ffmpeg for torchcodec)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Clone MOSS-TTS repository for Realtime model code
RUN git clone https://github.com/OpenMOSS/MOSS-TTS.git /opt/moss-tts

# Install dependencies
RUN pip install --no-cache-dir \
    torch>=2.0.0 \
    torchaudio>=2.0.0 \
    transformers>=5.0.0 \
    websockets>=12.0

# Install MOSS-TTS package with PyTorch CUDA support
RUN cd /opt/moss-tts && pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cu128 -e .

# Set working directory
WORKDIR /app

# Add MOSS-TTS to Python path
ENV PYTHONPATH="/opt/moss-tts:${PYTHONPATH}"

# Copy server and voices
COPY server.py .
COPY voices/ /app/voices/

# Expose WebSocket port (5056 to not conflict with MOSS-TTS on 5055)
EXPOSE 5056

# Run server
CMD ["python", "server.py"]
