FROM python:3.11-slim

LABEL org.opencontainers.image.title="ArcIA Presidio DLP Sanitizer"
LABEL org.opencontainers.image.description="Admission PII et secrets avec rejet fermé"
LABEL org.opencontainers.image.version="0.6.0"

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY app.py /app/app.py
EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
