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

app = FastAPI(title="ArcIA Presidio DLP Sanitizer", version="0.4.0")

# Secret regex patterns
SECRET_PATTERNS = [
    re.compile(r'(?i)(?:password|passwd|pwd|secret|token|api[_-]?key)\s*[:=]\s*([^\s,;]+)'),
    re.compile(r'sk-[a-zA-Z0-9_\-]{20,}'),
    re.compile(r'(?:Bearer\s+)([a-zA-Z0-9_\-\.]{20,})'),
    re.compile(r'ghp_[a-zA-Z0-9]{36}'),
    re.compile(r'AKIA[0-9A-Z]{16}'),
    re.compile(r'eyJ[a-zA-Z0-9_\-]{10,}\.eyJ[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]+'),
]

# PII regex patterns
EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')
IP_PATTERN = re.compile(r'(?<![\w\.])(?:\d{1,3}\.){3}\d{1,3}(?![\w\.])')
IBAN_PATTERN = re.compile(r'\b[A-Z]{2}\d{2}(?:[\s]?[A-Z0-9]{4}){3,7}(?:[\s]?[A-Z0-9]{1,4})?\b')
PHONE_PATTERN = re.compile(r'(?:\+33|0033|0)[1-9](?:[\s\.\-]?[0-9]{2}){4}\b')
CREDIT_CARD_PATTERN = re.compile(r'\b(?:\d{4}[\s\-]?){3}\d{4}\b')

# Entities excluded from semantic NLP redaction to preserve technical/public context
NON_PII_ENTITIES = {
    "LOCATION", "ORGANIZATION", "DATE_TIME", "NRP", "MISC",
    "PERSON", "EMAIL_ADDRESS", "IBAN_CODE", "IP_ADDRESS", "PHONE_NUMBER", "URL"
}

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
    score_threshold: Optional[float] = None
    ad_hoc_recognizers: Optional[List[Any]] = None


class AnonymizeRequest(BaseModel):
    text: str
    analyzer_results: Optional[List[Dict[str, Any]]] = None
    anonymizers: Optional[Dict[str, Any]] = None


@app.get("/")
@app.get("/healthz")
def health():
    analyzer = get_analyzer()
    return {
        "status": "ok" if analyzer is not None else "degraded",
        "service": "presidio-dlp",
        "version": "0.4.0",
        "analyzer_ready": analyzer is not None
    }


def _replace_with_counter(pattern: re.Pattern, text: str, label_prefix: str, entities: List[str], entity_name: str) -> str:
    counter = [0]

    def _repl(match: re.Match) -> str:
        counter[0] += 1
        entities.append(entity_name)
        return f"[{label_prefix}_{counter[0]}]"

    return pattern.sub(_repl, text)


@app.post("/sanitize")
def sanitize(req: SanitizeRequest):
    try:
        text = req.text or ""
        entities: List[str] = []

        # 1. Caviardage des secrets explicites
        for pattern in SECRET_PATTERNS:
            def _secret_repl(match: re.Match) -> str:
                entities.append("SECRET")
                if match.groups():
                    full = match.group(0)
                    secret_val = match.group(1)
                    if secret_val == "[SECRET_REMOVED]":
                        return full
                    return full.replace(secret_val, "[SECRET_REMOVED]")
                return "[SECRET_REMOVED]"

            text = pattern.sub(_secret_repl, text)

        # 2. Caviardage des adresses IP (sans collision de sous-chaînes)
        text = _replace_with_counter(IP_PATTERN, text, "ARCIA_IP_ADDRESS", entities, "IP_ADDRESS")

        # 3. Caviardage des emails
        text = _replace_with_counter(EMAIL_PATTERN, text, "ARCIA_EMAIL", entities, "EMAIL_ADDRESS")

        # 4. Caviardage des IBANs
        text = _replace_with_counter(IBAN_PATTERN, text, "ARCIA_IBAN", entities, "IBAN")

        # 5. Caviardage des numéros de téléphone
        text = _replace_with_counter(PHONE_PATTERN, text, "ARCIA_PHONE", entities, "PHONE_NUMBER")

        # 6. Caviardage des cartes bancaires
        text = _replace_with_counter(CREDIT_CARD_PATTERN, text, "ARCIA_CREDIT_CARD", entities, "CREDIT_CARD")

        # 7. Analyse PII avancée Presidio (Exclusion stricte des entités publiques/techniques)
        analyzer = get_analyzer()
        if analyzer and len(text) > 0:
            lang = req.language if req.language in ["fr", "en"] else "fr"
            results = analyzer.analyze(text=text, language=lang)
            for res in sorted(results, key=lambda r: r.start, reverse=True):
                if res.entity_type not in NON_PII_ENTITIES:
                    span_text = text[res.start:res.end]
                    if span_text.startswith("[ARCIA_") or span_text == "[SECRET_REMOVED]":
                        continue
                    entities.append(res.entity_type)
                    placeholder = f"[ARCIA_{res.entity_type}]"
                    text = text[:res.start] + placeholder + text[res.end:]

        return {
            "text": text,
            "sanitized_text": text,
            "original_length": len(req.text or ""),
            "sanitized_length": len(text),
            "entities_detected": list(dict.fromkeys(entities))
        }
    except Exception as e:
        # En cas d'erreur inattendue, Presidio déclenche un Fail-Closed strict
        raise HTTPException(status_code=500, detail=f"Presidio DLP fail-closed error: {str(e)}")


@app.post("/anonymize")
def anonymize(req: AnonymizeRequest):
    """Endpoint officiel consommé par LiteLLM Proxy guardrail pre_call."""
    res = sanitize(SanitizeRequest(text=req.text, language="fr"))
    return {"text": res["sanitized_text"], "items": []}


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    """Endpoint standard d'analyse compatible LiteLLM guardrail (inclut regex + NLP)."""
    text = req.text or ""
    items: List[Dict[str, Any]] = []

    # 1. Détection déterministe systématique (secrets, IP, email, IBAN, téléphone, CB)
    for pattern in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span(1) if match.groups() else match.span(0)
            if text[start:end] != "[SECRET_REMOVED]":
                items.append({"entity_type": "SECRET", "start": start, "end": end, "score": 1.0})
    for match in EMAIL_PATTERN.finditer(text):
        items.append({"entity_type": "EMAIL_ADDRESS", "start": match.start(), "end": match.end(), "score": 0.99})
    for match in IP_PATTERN.finditer(text):
        items.append({"entity_type": "IP_ADDRESS", "start": match.start(), "end": match.end(), "score": 0.99})
    for match in IBAN_PATTERN.finditer(text):
        items.append({"entity_type": "IBAN_CODE", "start": match.start(), "end": match.end(), "score": 0.99})
    for match in PHONE_PATTERN.finditer(text):
        items.append({"entity_type": "PHONE_NUMBER", "start": match.start(), "end": match.end(), "score": 0.95})
    for match in CREDIT_CARD_PATTERN.finditer(text):
        items.append({"entity_type": "CREDIT_CARD", "start": match.start(), "end": match.end(), "score": 0.99})

    # 2. Détection NLP complémentaire via Presidio Analyzer
    analyzer = get_analyzer()
    if analyzer and text:
        try:
            lang = req.language if req.language in ["fr", "en"] else "fr"
            results = analyzer.analyze(text=text, language=lang, entities=req.entities)
            for r in results:
                if r.entity_type in NON_PII_ENTITIES:
                    continue
                items.append({
                    "entity_type": r.entity_type,
                    "start": r.start,
                    "end": r.end,
                    "score": r.score
                })
        except Exception:
            pass

    return items


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
