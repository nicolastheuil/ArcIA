FROM nousresearch/hermes-agent:latest

LABEL org.opencontainers.image.title="ArcIA Hermes Agent Runtime"
LABEL org.opencontainers.image.description="Hermes Agent with ArcIA Tokenmaxing (RTK, Headroom CCR, Graphify, Ponytail) and Presidio DLP"
LABEL org.opencontainers.image.version="0.4.0"

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl python3-pip jq procps ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Installation de RTK (Rust Token Killer) et Headroom CCR
RUN curl -fsSL https://github.com/rtk-ai/rtk/releases/latest/download/rtk-x86_64-unknown-linux-musl.tar.gz \
    | tar -xz -C /usr/local/bin rtk && chmod +x /usr/local/bin/rtk || true
RUN pip install --no-cache-dir headroom-ai || true

COPY plugin.py /opt/hermes/plugins/plugin.py
RUN chmod +x /opt/hermes/plugins/plugin.py
