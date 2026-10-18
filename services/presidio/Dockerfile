FROM python:3.11-slim

LABEL org.opencontainers.image.title="ArcIA Presidio DLP Sanitizer"
LABEL org.opencontainers.image.description="Fail-Closed PII & Secrets Sanitizer for ArcIA (Hermes + LiteLLM Guardrail)"
LABEL org.opencontainers.image.version="0.4.0"

WORKDIR /app

RUN pip install --no-cache-dir \
    fastapi==0.115.0 \
    uvicorn==0.30.6 \
    pydantic==2.9.2 \
    presidio-analyzer==2.2.364 \
    presidio-anonymizer==2.2.364 \
    spacy==3.7.5 && \
    python -m spacy download fr_core_news_sm && \
    python -m spacy download en_core_web_sm

COPY app.py /app/app.py

EXPOSE 8080

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
