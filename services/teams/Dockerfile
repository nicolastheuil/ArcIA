FROM python:3.11-slim

LABEL org.opencontainers.image.title="ArcIA Microsoft Teams Bot Adapter"
LABEL org.opencontainers.image.description="Bot Framework Adapter for ArcIA (LiteLLM simple/auto & Hermes agentic/auto)"
LABEL org.opencontainers.image.version="0.4.0"

WORKDIR /app

RUN pip install --no-cache-dir \
    aiohttp==3.10.5 \
    botbuilder-core==4.16.1 \
    botbuilder-schema==4.16.1

COPY app.py /app/app.py

EXPOSE 3978

CMD ["python", "app.py"]
