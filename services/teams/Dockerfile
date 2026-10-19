FROM python:3.14.8-slim-bookworm@sha256:48b13b003dda20b16f9442b8475aa05fe21bf6579a8c881db92ffb4d8fd20f83

LABEL org.opencontainers.image.title="ArcIA Microsoft Teams Bot Adapter"
LABEL org.opencontainers.image.description="Bot Framework Adapter for ArcIA (LiteLLM simple/auto & Hermes agentic/auto)"
LABEL org.opencontainers.image.version="0.7.0"

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app.py /app/app.py

EXPOSE 3978

CMD ["python", "app.py"]
