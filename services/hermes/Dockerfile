FROM nousresearch/hermes-agent:v0.22.2@sha256:36099926da316742423544e055d4734777105ffe6341873af5459b957d0c2919

LABEL org.opencontainers.image.title="ArcIA Hermes Agent Runtime"
LABEL org.opencontainers.image.description="Hermes avec admission DLP obligatoire avant SQLite et inférence"
LABEL org.opencontainers.image.version="0.7.0"

COPY plugin.py runtime_guard.py bootstrap.py sitecustomize.py arcia_required.py arcia_governance.pth __init__.py plugin.yaml /opt/arcia-governance/
COPY arcia_governance.pth /opt/hermes/.venv/lib/python3.14/site-packages/arcia_governance.pth
ENV ARCIA_GOVERNANCE_REQUIRED=true PYTHONPATH=/opt/arcia-governance
ENTRYPOINT ["python3", "/opt/arcia-governance/bootstrap.py"]
CMD ["hermes", "gateway"]
