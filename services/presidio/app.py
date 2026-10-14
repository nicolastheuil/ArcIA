import os
import re
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="ArcIA Presidio DLP Sanitizer", version="0.2.0")

# Secret regex patterns
SECRET_PATTERNS = [
    re.compile(r'(?i)(?:password|passwd|pwd|secret|token|api[_-]?key)\s*[:=]\s*([^\s,;]+)'),
    re.compile(r'sk-[a-zA-Z0-9_\-]{20,}'),
    re.compile(r'(?:Bearer\s+)[a-zA-Z0-9_\-\.]{20,}'),
    re.compile(r'ghp_[a-zA-Z0-9]{36}'),
]

# Simple regex for PII fallback
EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')
IP_PATTERN = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
IBAN_PATTERN = re.compile(r'\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}([A-Z0-9]?){0,16}\b')

# Lazy load Presidio analyzer
_analyzer = None

def get_analyzer():
    global _analyzer
    if _analyzer is None:
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
    language: Optional[str] = "en"
    entities: Optional[List[str]] = None

@app.get("/")
@app.get("/healthz")
def health():
    return {"status": "ok", "service": "presidio-dlp", "version": "0.2.0"}

@app.post("/sanitize")
def sanitize(req: SanitizeRequest):
    text = req.text
    entities = []

    # 1. Redact explicit secrets
    for pattern in SECRET_PATTERNS:
        matches = list(pattern.finditer(text))
        for match in matches:
            entities.append("SECRET")
            # If pattern has group 1, redact group 1
            if match.groups():
                secret_val = match.group(1)
                text = text.replace(secret_val, "[SECRET_REMOVED]")
            else:
                text = text.replace(match.group(0), "[SECRET_REMOVED]")

    # 2. Redact Emails
    email_matches = EMAIL_PATTERN.findall(text)
    for idx, email in enumerate(email_matches):
        entities.append("EMAIL_ADDRESS")
        text = text.replace(email, f"[ARCIA_EMAIL_{idx+1}]")

    # 3. Redact IBANs
    iban_matches = IBAN_PATTERN.findall(text)
    for idx, iban in enumerate(iban_matches):
        entities.append("IBAN")
        text = text.replace(iban, f"[ARCIA_IBAN_{idx+1}]")

    # 4. Use Presidio Analyzer if available
    analyzer = get_analyzer()
    if analyzer and len(text) > 0:
        try:
            lang = req.language if req.language in ["fr", "en"] else "en"
            results = analyzer.analyze(text=text, language=lang)
            # Sort by start descending to replace cleanly
            for res in sorted(results, key=lambda r: r.start, reverse=True):
                if res.entity_type not in ["EMAIL_ADDRESS", "IBAN_CODE"]:
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

@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    # Presidio standard /analyze endpoint compatible with LiteLLM
    analyzer = get_analyzer()
    if analyzer:
        try:
            lang = req.language if req.language in ["fr", "en"] else "en"
            results = analyzer.analyze(text=req.text, language=lang, entities=req.entities)
            return [
                {
                    "entity_type": r.entity_type,
                    "start": r.start,
                    "end": r.end,
                    "score": r.score
                }
                for r in results
            ]
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    # Fallback if Presidio analyzer not yet ready
    items = []
    for match in EMAIL_PATTERN.finditer(req.text):
        items.append({"entity_type": "EMAIL_ADDRESS", "start": match.start(), "end": match.end(), "score": 0.95})
    return items

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
