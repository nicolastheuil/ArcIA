FROM ghcr.io/nousresearch/hermes-agent:latest
RUN apt-get update && apt-get install -y git curl python3-pip jq procps && rm -rf /var/lib/apt/lists/*
RUN curl -L https://github.com/rtk-ai/rtk/releases/latest/download/rtk-linux-x86_64 -o /usr/local/bin/rtk \
    && chmod +x /usr/local/bin/rtk || true
COPY plugin.py /opt/hermes/plugins/arcia_tokenmaxing.py
ENV OPENAI_API_BASE=http://litellm-proxy.arcia.svc:4000/v1
ENV OPENAI_MODEL_NAME=auto
