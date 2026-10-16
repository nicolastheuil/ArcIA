import os
import re
from typing import List, Dict, Any, Optional
try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel
except ImportError:
    class FastAPI:
        def __init__(self, *args, **kwargs): pass
        def get(self, *args, **kwargs): return lambda f: f
        def post(self, *args, **kwargs): return lambda f: f
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str):
            super().__init__(detail)
            self.status_code = status_code
    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

app = FastAPI(title="ArcIA Presidio DLP Sanitizer", version="0.3.0")

# Secret regex patterns
SECRET_PATTERNS = [
    re.compile(r'(?i)(?:password|passwd|pwd|secret|token|api[_-]?key)\s*[:=]\s*([^\s,;]+)'),
    re.compile(r'sk-[a-zA-Z0-9_\-]{20,}'),
    re.compile(r'(?:Bearer\s+)[a-zA-Z0-9_\-\.]{20,}'),
    re.compile(r'ghp_[a-zA-Z0-9]{36}'),
    re.compile(r'AKIA[0-9A-Z]{16}'),
    re.compile(r'eyJ[a-zA-Z0-9_\-]{10,}\.eyJ[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]+'),
]

# PII regex patterns
EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')
IP_PATTERN = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
IBAN_PATTERN = re.compile(r'\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}(?:[A-Z0-9]){0,16}\b')
PHONE_PATTERN = re.compile(r'(?:\+33|0033|0)[1-9](?:[\s\.\-]?[0-9]{2}){4}\b')
CREDIT_CARD_PATTERN = re.compile(r'\b(?:\d{4}[\s\-]?){3}\d{4}\b')

# Lazy load Presidio analyzer with multi-language NLP engine
_analyzer = None

def get_analyzer():
    global _analyzer
    if _analyzer is None:
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_analyzer.nlp_engine import NlpEngineProvider
            configuration = {
                "nlp_engine_name": "spacy",
                "models": [
                    {"lang_code": "fr", "model_name": "fr_core_news_sm"},
                    {"lang_code": "en", "model_name": "en_core_web_sm"}
                ]
            }
            provider = NlpEngineProvider(nlp_configuration=configuration)
            nlp_engine = provider.create_engine()
            _analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["fr", "en"])
        except Exception:
            try:
                from presidio_analyzer import AnalyzerEngine
                _analyzer = AnalyzerEngine()
            except Exception:
                _analyzer = None
    return _analyzer

class SanitizeRequest(BaseModel):
    text: str
    language: Optional[str] = "fr"

class SanitizeResponse(BaseModel):
    sanitized_text: str
    original_length: int
    sanitized_length: int
    entities_detected: List[str]

class AnalyzeRequest(BaseModel):
    text: str
    language: Optional[str] = "fr"
    entities: Optional[List[str]] = None

class AnonymizeRequest(BaseModel):
    text: str
    analyzer_results: Optional[List[Dict[str, Any]]] = None
    anonymizers: Optional[Dict[str, Any]] = None

@app.get("/")
@app.get("/healthz")
def health():
    analyzer = get_analyzer()
    return {
        "status": "ok",
        "service": "presidio-dlp",
        "version": "0.3.0",
        "analyzer_ready": analyzer is not None
    }

@app.post("/sanitize")
def sanitize(req: SanitizeRequest):
    text = req.text
    entities = []

    # 1. Caviardage des secrets explicites
    for pattern in SECRET_PATTERNS:
        matches = list(pattern.finditer(text))
        for match in matches:
            entities.append("SECRET")
            if match.groups():
                secret_val = match.group(1)
                text = text.replace(secret_val, "[SECRET_REMOVED]")
            else:
                text = text.replace(match.group(0), "[SECRET_REMOVED]")

    # 2. Caviardage des adresses IP (v0.3 active)
    ip_matches = [m.group(0) for m in IP_PATTERN.finditer(text)]
    for idx, ip in enumerate(ip_matches):
        entities.append("IP_ADDRESS")
        text = text.replace(ip, f"[ARCIA_IP_ADDRESS_{idx+1}]")

    # 3. Caviardage des emails
    email_matches = [m.group(0) for m in EMAIL_PATTERN.finditer(text)]
    for idx, email in enumerate(email_matches):
        entities.append("EMAIL_ADDRESS")
        text = text.replace(email, f"[ARCIA_EMAIL_{idx+1}]")

    # 4. Caviardage des IBANs
    iban_matches = [m.group(0) for m in IBAN_PATTERN.finditer(text)]
    for idx, iban in enumerate(iban_matches):
        entities.append("IBAN")
        text = text.replace(iban, f"[ARCIA_IBAN_{idx+1}]")

    # 5. Caviardage des numéros de téléphone
    phone_matches = [m.group(0) for m in PHONE_PATTERN.finditer(text)]
    for idx, phone in enumerate(phone_matches):
        entities.append("PHONE_NUMBER")
        text = text.replace(phone, f"[ARCIA_PHONE_{idx+1}]")

    # 6. Caviardage des cartes bancaires
    cc_matches = [m.group(0) for m in CREDIT_CARD_PATTERN.finditer(text)]
    for idx, cc in enumerate(cc_matches):
        entities.append("CREDIT_CARD")
        text = text.replace(cc, f"[ARCIA_CREDIT_CARD_{idx+1}]")

    # 7. Analyse PII avancée Presidio (Personnes, Organisations, Lieux)
    analyzer = get_analyzer()
    if analyzer and len(text) > 0:
        try:
            lang = req.language if req.language in ["fr", "en"] else "fr"
            results = analyzer.analyze(text=text, language=lang)
            for res in sorted(results, key=lambda r: r.start, reverse=True):
                if res.entity_type not in ["EMAIL_ADDRESS", "IBAN_CODE", "IP_ADDRESS", "PHONE_NUMBER"]:
                    entities.append(res.entity_type)
                    placeholder = f"[ARCIA_{res.entity_type}]"
                    text = text[:res.start] + placeholder + text[res.end:]
        except Exception:
            pass

    return {
        "text": text,
        "sanitized_text": text,
        "original_length": len(req.text),
        "sanitized_length": len(text),
        "entities_detected": list(set(entities))
    }

@app.post("/anonymize")
def anonymize(req: AnonymizeRequest):
    """Endpoint officiel consommé par LiteLLM Proxy guardrail."""
    res = sanitize(SanitizeRequest(text=req.text, language="fr"))
    return {"text": res["sanitized_text"], "items": []}

@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    """Endpoint standard d'analyse compatible LiteLLM."""
    analyzer = get_analyzer()
    items = []
    if analyzer:
        try:
            lang = req.language if req.language in ["fr", "en"] else "fr"
            results = analyzer.analyze(text=req.text, language=lang, entities=req.entities)
            for r in results:
                items.append({
                    "entity_type": r.entity_type,
                    "start": r.start,
                    "end": r.end,
                    "score": r.score
                })
            return items
        except Exception:
            pass

    # Regex de secours si l'analyseur n'est pas encore instancié
    for match in EMAIL_PATTERN.finditer(req.text):
        items.append({"entity_type": "EMAIL_ADDRESS", "start": match.start(), "end": match.end(), "score": 0.95})
    for match in IP_PATTERN.finditer(req.text):
        items.append({"entity_type": "IP_ADDRESS", "start": match.start(), "end": match.end(), "score": 0.95})
    for match in IBAN_PATTERN.finditer(req.text):
        items.append({"entity_type": "IBAN", "start": match.start(), "end": match.end(), "score": 0.95})
    for match in PHONE_PATTERN.finditer(req.text):
        items.append({"entity_type": "PHONE_NUMBER", "start": match.start(), "end": match.end(), "score": 0.90})

    return items

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
