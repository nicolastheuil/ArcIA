import os
import re
import time
import json
import uuid
import threading
from typing import List, Dict, Any, Optional, Tuple

try:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel
except ImportError:
    class FastAPI:
        def __init__(self, *args, **kwargs): pass
        def get(self, *args, **kwargs): return lambda f: f
        def post(self, *args, **kwargs): return lambda f: f
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: Any):
            super().__init__(str(detail))
            self.status_code = status_code
            self.detail = detail
    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

app = FastAPI(title="ArcIA Presidio DLP Sanitizer", version="0.4.0")

# ==============================================================================
# 1. Ephemeral In-Memory Vault for Reversible & Consistent Pseudonymization
# ==============================================================================

ENTITY_TOKEN_PREFIXES = {
    "IP_ADDRESS": "IPV4",
    "IPV4_PRIVATE": "IPV4",
    "IPV4": "IPV4",
    "IPV6": "IPV6",
    "CIDR_NETWORK": "CIDR",
    "MAC_ADDRESS": "MAC",
    "INTERNAL_HOSTNAME": "HOST",
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "PHONE",
    "IBAN_CODE": "IBAN",
    "IBAN": "IBAN",
    "CREDIT_CARD": "CREDIT_CARD",
    "FR_NIR": "NIR",
    "FR_SIRET": "SIRET",
    "FR_SIREN": "SIREN",
    "PERSON": "PERSON",
    "ORGANIZATION": "ORG",
    "LOCATION": "LOC",
    "CLIENT_PROJECT": "PROJECT",
    "FORBIDDEN_TERMS": "DENIED",
    "SENSITIVE_PATH": "PATH",
}


class EphemeralVault:
    """
    Stateful in-memory vault holding reversible token mappings strictly in RAM.
    Zero disk persistence, zero plaintext logging.
    Enforces TTL expiration and bounded memory capacity.
    """
    def __init__(self, ttl_seconds: int = 1800, max_sessions: int = 5000):
        self.ttl = ttl_seconds
        self.max_sessions = max_sessions
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _cleanup_unlocked(self, now: float):
        expired = [sid for sid, d in self._sessions.items() if now - d.get("updated_at", 0) > self.ttl]
        for sid in expired:
            del self._sessions[sid]
        if len(self._sessions) > self.max_sessions:
            sorted_sids = sorted(self._sessions.keys(), key=lambda s: self._sessions[s].get("updated_at", 0))
            to_remove = sorted_sids[:len(self._sessions) - self.max_sessions]
            for sid in to_remove:
                del self._sessions[sid]

    def get_or_create_session(self, session_id: str) -> Dict[str, Any]:
        with self._lock:
            now = time.time()
            self._cleanup_unlocked(now)
            if session_id not in self._sessions:
                self._sessions[session_id] = {
                    "raw_to_token": {},
                    "token_to_raw": {},
                    "counters": {},
                    "created_at": now,
                    "updated_at": now,
                }
            else:
                self._sessions[session_id]["updated_at"] = now
            return self._sessions[session_id]

    def get_or_assign_token(self, session_id: str, raw_value: str, entity_type: str) -> str:
        with self._lock:
            now = time.time()
            self._cleanup_unlocked(now)
            if session_id not in self._sessions:
                self._sessions[session_id] = {
                    "raw_to_token": {},
                    "token_to_raw": {},
                    "counters": {},
                    "created_at": now,
                    "updated_at": now,
                }
            session = self._sessions[session_id]
            session["updated_at"] = now

            if raw_value in session["raw_to_token"]:
                return session["raw_to_token"][raw_value]

            prefix = ENTITY_TOKEN_PREFIXES.get(entity_type, entity_type.upper()[:6])
            idx = session["counters"].get(prefix, 0) + 1
            session["counters"][prefix] = idx
            token = f"[{prefix}_{idx:02d}]"

            session["raw_to_token"][raw_value] = token
            session["token_to_raw"][token] = raw_value
            return token

    def deanonymize(self, session_id: Optional[str], text: str, custom_tokens: Optional[Dict[str, str]] = None) -> Tuple[str, int]:
        with self._lock:
            token_map: Dict[str, str] = {}
            if session_id and session_id in self._sessions:
                token_map.update(self._sessions[session_id]["token_to_raw"])
                self._sessions[session_id]["updated_at"] = time.time()
            if custom_tokens:
                token_map.update(custom_tokens)

            # Résolution de secours sur les sessions récentes actives si des jetons [TYPE_NN] restent non résolus
            if "[" in text and "]" in text:
                for sid, sdata in sorted(self._sessions.items(), key=lambda item: item[1].get("updated_at", 0), reverse=True):
                    for tok, raw in sdata.get("token_to_raw", {}).items():
                        if tok not in token_map:
                            token_map[tok] = raw

        if not token_map or not text:
            return text, 0

        replaced_count = 0
        # Sort tokens by length descending to prevent partial match collisions
        for token, raw_val in sorted(token_map.items(), key=lambda item: len(item[0]), reverse=True):
            if token in text:
                text = text.replace(token, raw_val)
                replaced_count += 1
        return text, replaced_count

    def active_sessions_count(self) -> int:
        with self._lock:
            return len(self._sessions)


vault = EphemeralVault()


# ==============================================================================
# 2. Couche 1 : Filtre Déterministe Pré-NLP & Signatures de Secrets (Fail-Closed)
# ==============================================================================

# Signatures critiques déclenchant un rejet immédiat (HTTP 422 Fail-Closed)
RAW_SECRET_DUMP_SIGNATURES = [
    (re.compile(r'-----BEGIN (?:[A-Z0-9_-]+ )?PRIVATE KEY-----'), "PEM_PRIVATE_KEY_DETECTED"),
    (re.compile(r'-----BEGIN OPENSSH PRIVATE KEY-----'), "SSH_PRIVATE_KEY_DETECTED"),
    (re.compile(r'root:\$[156]\$[a-zA-Z0-9./]{8,16}\$[a-zA-Z0-9./]{86}'), "SHADOW_HASH_DUMP_DETECTED"),
]

# Patterns Kubeconfig
KUBECONFIG_API_PATTERN = re.compile(r'apiVersion:\s*v1')
KUBECONFIG_CLUSTER_PATTERN = re.compile(r'(?:clusters:|current-context:)')
KUBECONFIG_SECRET_PATTERN = re.compile(r'(?:client-certificate-data:|certificate-authority-data:|client-key-data:|server:\s*https?://)')

# Regex de caviardage de secrets en ligne
SECRET_PATTERNS = [
    re.compile(r'(?i)(?:password|passwd|pwd|secret|token|api[_-]?key)\s*[:=]\s*([^\s,;]+)'),
    re.compile(r'sk-[a-zA-Z0-9_\-]{20,}'),
    re.compile(r'(?:Bearer\s+)([a-zA-Z0-9_\-\.]{20,})'),
    re.compile(r'ghp_[a-zA-Z0-9]{36}'),
    re.compile(r'AKIA[0-9A-Z]{16}'),
    re.compile(r'eyJ[a-zA-Z0-9_\-]{10,}\.eyJ[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]+'),
    re.compile(r'(?:postgres|postgresql|mysql|mongodb|amqp|redis|mssql):\/\/[^\s]+'),
]

# Regex d'infrastructure & réseau
IPV4_REGEX = re.compile(r'(?<![\w\.])(?:\d{1,3}\.){3}\d{1,3}(?![\w\.])')
IP_PATTERN = IPV4_REGEX  # Backward compatibility alias
IPV6_REGEX = re.compile(r'(?<![\w:])(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}(?![\w:])')
CIDR_REGEX = re.compile(r'(?<![\w\.])(?:\d{1,3}\.){3}\d{1,3}\/(?:[0-9]|[1-2][0-9]|3[0-2])\b')
MAC_REGEX = re.compile(r'\b[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}\b|\b[0-9a-fA-F]{2}(?:-[0-9a-fA-F]{2}){5}\b')
INTERNAL_HOSTNAME_REGEX = re.compile(r'\b[a-zA-Z0-9][a-zA-Z0-9\-_]*\.(?:local|lan|internal|corp|home|cluster\.local)\b', re.IGNORECASE)
SENSITIVE_PATHS_REGEX = re.compile(r'(?:/etc/(?:shadow|sudoers|master\.passwd)|/root/\.ssh/(?:id_rsa|id_ed25519|authorized_keys))\b')

# PII regex patterns
EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')
IBAN_PATTERN = re.compile(r'\b[A-Z]{2}\d{2}(?:[\s]?[A-Z0-9]{4}){3,7}(?:[\s]?[A-Z0-9]{1,4})?\b')
PHONE_PATTERN = re.compile(r'(?:\+33|0033|0)[1-9](?:[\s\.\-]?[0-9]{2}){4}\b')
CREDIT_CARD_PATTERN = re.compile(r'\b(?:\d{4}[\s\-]?){3}\d{4}\b')

# French specific PII (FR_NIR & FR_SIRET)
FR_NIR_PATTERN = re.compile(r'\b([12]\s*\d{2}\s*(?:0[1-9]|1[0-2]|[2-9]\d)\s*(?:\d{2}|2[ABab])\s*\d{3}\s*\d{3}(?:\s*\d{2})?)\b')
FR_SIRET_PATTERN = re.compile(r'\b(\d{3}\s*\d{3}\s*\d{3}\s*\d{5}|\d{14})\b')


def is_valid_ipv4(ip_str: str) -> bool:
    parts = ip_str.split('.')
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(p) <= 255 for p in parts)
    except ValueError:
        return False


def is_rfc1918_private(ip_str: str) -> bool:
    try:
        parts = [int(p) for p in ip_str.split('.')]
        if parts[0] == 10:
            return True
        if parts[0] == 172 and 16 <= parts[1] <= 31:
            return True
        if parts[0] == 192 and parts[1] == 168:
            return True
        if parts[0] == 127 or (parts[0] == 169 and parts[1] == 254):
            return True
        return False
    except Exception:
        return False


def validate_fr_nir(nir_str: str) -> bool:
    cleaned = re.sub(r'[\s]', '', nir_str).upper().replace('2A', '19').replace('2B', '18')
    if len(cleaned) == 13:
        return True
    if len(cleaned) == 15:
        try:
            base = int(cleaned[:13])
            key = int(cleaned[13:])
            return (97 - (base % 97)) == key
        except ValueError:
            return False
    return False


def validate_luhn(digits_str: str) -> bool:
    cleaned = re.sub(r'[\s\.\-]', '', digits_str)
    if not cleaned.isdigit() or len(cleaned) != 14:
        return False
    total = 0
    parity = len(cleaned) % 2
    for i, char in enumerate(cleaned):
        d = int(char)
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return (total % 10) == 0


def detect_kubeconfig_dump(text: str) -> bool:
    if KUBECONFIG_API_PATTERN.search(text) and KUBECONFIG_CLUSTER_PATTERN.search(text) and KUBECONFIG_SECRET_PATTERN.search(text):
        return True
    return False


# ==============================================================================
# 3. Couche 2 : Deny-Lists d'Instance & Support GLiNER
# ==============================================================================

_deny_list_cache: Optional[Dict[str, List[str]]] = None
_deny_list_mtime: float = 0


def get_deny_list() -> Dict[str, List[str]]:
    global _deny_list_cache, _deny_list_mtime
    raw_env = os.environ.get("ARCIA_DENY_LIST")
    if raw_env:
        try:
            parsed = json.loads(raw_env)
            return parsed.get("entities", {})
        except Exception:
            pass

    path = os.environ.get("ARCIA_DENY_LIST_PATH", "/etc/arcia/deny-list.json")
    if not os.path.isfile(path):
        return {}

    try:
        mtime = os.path.getmtime(path)
        if _deny_list_cache is not None and mtime == _deny_list_mtime:
            return _deny_list_cache
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            _deny_list_cache = data.get("entities", {})
            _deny_list_mtime = mtime
            return _deny_list_cache
    except Exception:
        return {}


# Exclusion stricte d'entités publiques/techniques de l'analyse NLP
NON_PII_ENTITIES = {
    "LOCATION", "ORGANIZATION", "DATE_TIME", "NRP", "MISC",
    "URL"
}

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


# ==============================================================================
# 4. Modèles de Données API REST
# ==============================================================================

class SanitizeRequest(BaseModel):
    text: str
    language: Optional[str] = "fr"
    session_id: Optional[str] = None
    strict_secrets: Optional[bool] = True


class SanitizeResponse(BaseModel):
    text: str
    sanitized_text: str
    session_id: str
    original_length: int
    sanitized_length: int
    entities_detected: List[str]
    vault_tokens_count: int


class DeanonymizeRequest(BaseModel):
    text: str
    session_id: Optional[str] = None
    custom_tokens: Optional[Dict[str, str]] = None


class DeanonymizeResponse(BaseModel):
    text: str
    tokens_replaced: int
    session_id: Optional[str] = None


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


# ==============================================================================
# 5. Pipeline de Traitement Principal
# ==============================================================================

@app.get("/")
@app.get("/healthz")
def health():
    analyzer = get_analyzer()
    return {
        "status": "ok" if analyzer is not None else "degraded",
        "service": "presidio-dlp",
        "version": "0.4.0",
        "analyzer_ready": analyzer is not None,
        "active_vault_sessions": vault.active_sessions_count(),
        "deny_list_configured": bool(get_deny_list())
    }


@app.post("/sanitize")
def sanitize(req: SanitizeRequest):
    text = req.text or ""
    session_id = req.session_id or str(uuid.uuid4())
    entities_detected: List[str] = []

    # -------------------------------------------------------------------------
    # Couche 1A : Contrôle FAIL-CLOSED sur dumps de secrets bruts / kubeconfig
    # -------------------------------------------------------------------------
    strict_secrets = req.strict_secrets if req.strict_secrets is not None else True
    if strict_secrets and text:
        for pattern, reason in RAW_SECRET_DUMP_SIGNATURES:
            if pattern.search(text):
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": "FAIL_CLOSED_SECRET_REJECTED",
                        "reason": reason,
                        "message": "Fichier secret brut ou clé privée détecté. Requête rejetée pour traitement local."
                    }
                )
        if detect_kubeconfig_dump(text):
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "FAIL_CLOSED_SECRET_REJECTED",
                    "reason": "KUBECONFIG_DUMP_DETECTED",
                    "message": "Extraction kubeconfig détectée dans le payload. Requête rejetée pour traitement local."
                }
            )

    # -------------------------------------------------------------------------
    # Couche 1B : Caviardage irréversible des secrets en ligne (Non-réhydratables)
    # -------------------------------------------------------------------------
    for pattern in SECRET_PATTERNS:
        def _secret_repl(match: re.Match) -> str:
            entities_detected.append("SECRET")
            if match.groups():
                full = match.group(0)
                val = match.group(1)
                if val == "[SECRET_REMOVED]":
                    return full
                return full.replace(val, "[SECRET_REMOVED]")
            return "[SECRET_REMOVED]"

        text = pattern.sub(_secret_repl, text)

    # Caviardage des chemins système critiques
    def _path_repl(match: re.Match) -> str:
        raw_val = match.group(0)
        entities_detected.append("SENSITIVE_PATH")
        return vault.get_or_assign_token(session_id, raw_val, "SENSITIVE_PATH")

    text = SENSITIVE_PATHS_REGEX.sub(_path_repl, text)

    # -------------------------------------------------------------------------
    # Couche 1C & 2 : Deny-Lists dynamiques de l'instance
    # -------------------------------------------------------------------------
    deny_lists = get_deny_list()
    if deny_lists:
        for category, terms in deny_lists.items():
            for term in terms:
                if not term or len(term.strip()) < 2:
                    continue
                term_escaped = re.escape(term.strip())
                term_regex = re.compile(rf'\b{term_escaped}\b', re.IGNORECASE)
                if term_regex.search(text):
                    entities_detected.append(category)
                    token = vault.get_or_assign_token(session_id, term.strip(), category)
                    text = term_regex.sub(token, text)

    # -------------------------------------------------------------------------
    # Couche 1D : Réseau & Infrastructure (CIDR, MAC, Hostnames internes, IPv4)
    # -------------------------------------------------------------------------
    # CIDR
    def _cidr_repl(match: re.Match) -> str:
        raw = match.group(0)
        entities_detected.append("CIDR_NETWORK")
        return vault.get_or_assign_token(session_id, raw, "CIDR_NETWORK")
    text = CIDR_REGEX.sub(_cidr_repl, text)

    # MAC
    def _mac_repl(match: re.Match) -> str:
        raw = match.group(0)
        entities_detected.append("MAC_ADDRESS")
        return vault.get_or_assign_token(session_id, raw, "MAC_ADDRESS")
    text = MAC_REGEX.sub(_mac_repl, text)

    # Internal Hostnames
    def _host_repl(match: re.Match) -> str:
        raw = match.group(0)
        entities_detected.append("INTERNAL_HOSTNAME")
        return vault.get_or_assign_token(session_id, raw, "INTERNAL_HOSTNAME")
    text = INTERNAL_HOSTNAME_REGEX.sub(_host_repl, text)

    # IPv4 (avec validation d'octets et distinction RFC1918)
    def _ipv4_repl(match: re.Match) -> str:
        raw = match.group(0)
        if not is_valid_ipv4(raw):
            return raw
        entity_type = "IPV4_PRIVATE" if is_rfc1918_private(raw) else "IPV4"
        entities_detected.append("IP_ADDRESS")
        return vault.get_or_assign_token(session_id, raw, entity_type)
    text = IPV4_REGEX.sub(_ipv4_repl, text)

    # -------------------------------------------------------------------------
    # Couche 2 : PII Déterministe (NIR, SIRET, Email, IBAN, Téléphone, CB)
    # -------------------------------------------------------------------------
    # FR NIR
    def _nir_repl(match: re.Match) -> str:
        raw = match.group(0)
        if validate_fr_nir(raw):
            entities_detected.append("FR_NIR")
            return vault.get_or_assign_token(session_id, raw, "FR_NIR")
        return raw
    text = FR_NIR_PATTERN.sub(_nir_repl, text)

    # FR SIRET
    def _siret_repl(match: re.Match) -> str:
        raw = match.group(0)
        if validate_luhn(raw):
            entities_detected.append("FR_SIRET")
            return vault.get_or_assign_token(session_id, raw, "FR_SIRET")
        return raw
    text = FR_SIRET_PATTERN.sub(_siret_repl, text)

    # Email
    def _email_repl(match: re.Match) -> str:
        raw = match.group(0)
        entities_detected.append("EMAIL_ADDRESS")
        return vault.get_or_assign_token(session_id, raw, "EMAIL_ADDRESS")
    text = EMAIL_PATTERN.sub(_email_repl, text)

    # IBAN
    def _iban_repl(match: re.Match) -> str:
        raw = match.group(0)
        entities_detected.append("IBAN")
        return vault.get_or_assign_token(session_id, raw, "IBAN")
    text = IBAN_PATTERN.sub(_iban_repl, text)

    # Phone
    def _phone_repl(match: re.Match) -> str:
        raw = match.group(0)
        entities_detected.append("PHONE_NUMBER")
        return vault.get_or_assign_token(session_id, raw, "PHONE_NUMBER")
    text = PHONE_PATTERN.sub(_phone_repl, text)

    # Credit Card
    def _cc_repl(match: re.Match) -> str:
        raw = match.group(0)
        entities_detected.append("CREDIT_CARD")
        return vault.get_or_assign_token(session_id, raw, "CREDIT_CARD")
    text = CREDIT_CARD_PATTERN.sub(_cc_repl, text)

    # -------------------------------------------------------------------------
    # Couche 2 : Analyse PII Sémantique NLP via Presidio (Personnes, etc.)
    # -------------------------------------------------------------------------
    analyzer = get_analyzer()
    if analyzer and len(text) > 0:
        lang = req.language if req.language in ["fr", "en"] else "fr"
        try:
            results = analyzer.analyze(text=text, language=lang)
            # Remplacement des entités de droite à gauche pour préserver les index
            for res in sorted(results, key=lambda r: r.start, reverse=True):
                if res.entity_type not in NON_PII_ENTITIES:
                    span_text = text[res.start:res.end]
                    # Ne pas ré-anonymiser un token déjà inséré
                    if span_text.startswith("[") and span_text.endswith("]"):
                        continue
                    entities_detected.append(res.entity_type)
                    token = vault.get_or_assign_token(session_id, span_text, res.entity_type)
                    text = text[:res.start] + token + text[res.end:]
        except Exception:
            pass

    session_data = vault.get_or_create_session(session_id)
    tokens_count = len(session_data.get("token_to_raw", {}))

    return {
        "text": text,
        "sanitized_text": text,
        "session_id": session_id,
        "original_length": len(req.text or ""),
        "sanitized_length": len(text),
        "entities_detected": list(dict.fromkeys(entities_detected)),
        "vault_tokens_count": tokens_count
    }


@app.post("/deanonymize")
def deanonymize(req: DeanonymizeRequest):
    """
    Couche 3 : Ré-hydratation inverse et dé-anonymisation des réponses LLM.
    Remplace les jetons typés [IPV4_01], [PERSON_01] par leurs valeurs originales depuis le Vault éphémère.
    """
    raw_text = req.text or ""
    restored, replaced = vault.deanonymize(req.session_id, raw_text, req.custom_tokens)
    return {
        "text": restored,
        "tokens_replaced": replaced,
        "session_id": req.session_id
    }


@app.post("/anonymize")
def anonymize(req: AnonymizeRequest):
    """Endpoint officiel consommé par LiteLLM Proxy guardrail pre_call."""
    res = sanitize(SanitizeRequest(text=req.text, language="fr", strict_secrets=False))
    return {"text": res["sanitized_text"], "items": []}


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    """Endpoint standard d'analyse compatible LiteLLM guardrail (inclut regex, infra & NLP)."""
    text = req.text or ""
    items: List[Dict[str, Any]] = []

    # Secrets
    for pattern in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span(1) if match.groups() else match.span(0)
            if text[start:end] != "[SECRET_REMOVED]":
                items.append({"entity_type": "SECRET", "start": start, "end": end, "score": 1.0})

    # Infra & PII
    for match in IPV4_REGEX.finditer(text):
        if is_valid_ipv4(match.group(0)):
            items.append({"entity_type": "IP_ADDRESS", "start": match.start(), "end": match.end(), "score": 1.0})
    for match in CIDR_REGEX.finditer(text):
        items.append({"entity_type": "CIDR_NETWORK", "start": match.start(), "end": match.end(), "score": 1.0})
    for match in MAC_REGEX.finditer(text):
        items.append({"entity_type": "MAC_ADDRESS", "start": match.start(), "end": match.end(), "score": 1.0})
    for match in INTERNAL_HOSTNAME_REGEX.finditer(text):
        items.append({"entity_type": "INTERNAL_HOSTNAME", "start": match.start(), "end": match.end(), "score": 1.0})
    for match in EMAIL_PATTERN.finditer(text):
        items.append({"entity_type": "EMAIL_ADDRESS", "start": match.start(), "end": match.end(), "score": 0.99})
    for match in IBAN_PATTERN.finditer(text):
        items.append({"entity_type": "IBAN_CODE", "start": match.start(), "end": match.end(), "score": 0.99})
    for match in PHONE_PATTERN.finditer(text):
        items.append({"entity_type": "PHONE_NUMBER", "start": match.start(), "end": match.end(), "score": 0.95})
    for match in CREDIT_CARD_PATTERN.finditer(text):
        items.append({"entity_type": "CREDIT_CARD", "start": match.start(), "end": match.end(), "score": 0.99})

    # Deny-lists
    deny_lists = get_deny_list()
    for cat, terms in deny_lists.items():
        for t in terms:
            if not t: continue
            for m in re.finditer(rf'\b{re.escape(t)}\b', text, re.IGNORECASE):
                items.append({"entity_type": cat, "start": m.start(), "end": m.end(), "score": 1.0})

    # Presidio NLP
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


# ==============================================================================
# 6. Buffer de Dé-anonymisation Streaming pour Relais / SSE
# ==============================================================================

class DeanonymizingStreamBuffer:
    """
    Buffer glissant pour ré-hydrater les jetons [TYPE_01] arrivant par morceaux
    dans les flux de réponse streaming (Server-Sent Events / OpenAI chunking).
    """
    def __init__(self, session_id: Optional[str] = None, custom_tokens: Optional[Dict[str, str]] = None):
        self.session_id = session_id
        self.custom_tokens = custom_tokens or {}
        self.buffer = ""

    def process_chunk(self, chunk: str) -> str:
        self.buffer += chunk
        # Si aucun '[' dans le buffer, tout le contenu peut être émis directement
        if "[" not in self.buffer:
            out = self.buffer
            self.buffer = ""
            return out

        # Détection des jetons complets [...]
        out_parts = []
        while "[" in self.buffer and "]" in self.buffer:
            start = self.buffer.find("[")
            end = self.buffer.find("]", start)
            if end == -1:
                break
            # Émettre la partie avant '['
            out_parts.append(self.buffer[:start])
            token = self.buffer[start:end + 1]
            # Résoudre le jeton
            restored, _ = vault.deanonymize(self.session_id, token, self.custom_tokens)
            out_parts.append(restored)
            self.buffer = self.buffer[end + 1:]

        # Si le buffer restant ne contient pas de jeton potentiel en cours (ex: '[' sans ']'),
        # garder uniquement à partir du dernier '[' si proche de la fin
        if "[" in self.buffer:
            last_bracket = self.buffer.rfind("[")
            # Si le jeton partiel est plus long que 30 caractères, ce n'est probablement pas un de nos jetons
            if len(self.buffer) - last_bracket > 30:
                out_parts.append(self.buffer)
                self.buffer = ""
            else:
                out_parts.append(self.buffer[:last_bracket])
                self.buffer = self.buffer[last_bracket:]
        else:
            out_parts.append(self.buffer)
            self.buffer = ""

        return "".join(out_parts)

    def flush(self) -> str:
        out, _ = vault.deanonymize(self.session_id, self.buffer, self.custom_tokens)
        self.buffer = ""
        return out


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
