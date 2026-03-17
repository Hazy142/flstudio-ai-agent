FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

# Install Python, system deps
RUN apt-get update && apt-get install -y python3.11 python3-pip git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone OmniParser V2
RUN git clone https://github.com/microsoft/OmniParser.git /app/omniparser

# Install OmniParser deps
RUN pip3 install torch torchvision --index-url https://download.pytorch.org/whl/cu121
RUN cd /app/omniparser && pip3 install -r requirements.txt
RUN pip3 install fastapi uvicorn python-multipart pillow

# Download models (this layer gets cached)
RUN pip3 install huggingface-hub && \
    huggingface-cli download microsoft/OmniParser-v2.0 icon_detect/train_args.yaml icon_detect/model.pt icon_detect/model.yaml icon_caption/config.json icon_caption/generation_config.json icon_caption/model.safetensors --local-dir /app/weights && \
    mv /app/weights/icon_caption /app/weights/icon_caption_florence

COPY server.py /app/server.py

EXPOSE 8080
CMD ["python3", "/app/server.py"]
