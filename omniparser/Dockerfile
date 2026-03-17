FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

# Prevent interactive prompts during apt install
ENV DEBIAN_FRONTEND=noninteractive

# Install Python 3.11, git, and system deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3.11 python3.11-venv python3-pip git wget && \
    rm -rf /var/lib/apt/lists/*

# Make python3.11 the default
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

WORKDIR /app

# Install Python dependencies first (layer caching)
RUN pip3 install --no-cache-dir \
    torch torchvision --index-url https://download.pytorch.org/whl/cu121

RUN pip3 install --no-cache-dir \
    fastapi uvicorn[standard] python-multipart pillow huggingface-hub

# Clone OmniParser V2
RUN git clone --depth=1 https://github.com/microsoft/OmniParser.git /app/omniparser

# Install OmniParser dependencies
RUN cd /app/omniparser && pip3 install --no-cache-dir -r requirements.txt

# Download model weights (~3GB, cached as Docker layer)
RUN huggingface-cli download microsoft/OmniParser-v2.0 \
        icon_detect/train_args.yaml \
        icon_detect/model.pt \
        icon_detect/model.yaml \
        icon_caption/config.json \
        icon_caption/generation_config.json \
        icon_caption/model.safetensors \
        --local-dir /app/weights && \
    mv /app/weights/icon_caption /app/weights/icon_caption_florence

# Copy our server
COPY server.py /app/server.py

# Cloud Run requires the container to listen on $PORT (default 8080)
ENV PORT=8080
EXPOSE 8080

# Health check for Cloud Run
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

CMD ["python3", "/app/server.py"]
