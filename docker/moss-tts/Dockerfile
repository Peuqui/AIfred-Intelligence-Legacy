FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Clone MOSS-TTS repository (no pip-only install available)
RUN git clone https://github.com/OpenMOSS/MOSS-TTS.git /opt/moss-tts

# Install MOSS-TTS with PyTorch 2.9+cu128 and Transformers 5.0
RUN cd /opt/moss-tts && pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cu128 -e .

# Flask + Gunicorn for API server
RUN pip install --no-cache-dir flask gunicorn

# Copy server
COPY server.py /app/server.py
WORKDIR /app

# Port 5055 (XTTS=5051, F5=5052, Qwen3=5053, Higgs=5054)
EXPOSE 5055

# Run with gunicorn for production stability
CMD ["gunicorn", "--bind", "0.0.0.0:5055", "--timeout", "300", "--workers", "1", "server:app"]
