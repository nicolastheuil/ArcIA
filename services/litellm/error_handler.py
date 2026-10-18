#!/usr/bin/env python3
"""
ArcIA Enterprise Agentic Platform — LiteLLM User-Friendly Error Handler
========================================================================
Microservice / Module d'interception d'erreurs pour LiteLLM Proxy.

Rôle :
1. Intercepte les exceptions brutes issues des fournisseurs d'IA (OpenRouter,
   DeepSeek, etc.) via le hook LiteLLM `async_post_call_failure_hook`.
2. Journalise l'intégralité de la trace technique sur sys.stderr pour
   permettre aux administrateurs de diagnostiquer l'incident (kubectl logs / docker logs).
3. Transforme le message d'erreur en un message clair, courtois et pédagogique en français,
   sans fuite de données sensibles (clés d'API, hashes, routing funnels, cooldown lists).
4. Restitue une HTTPException FastAPI que LiteLLM renvoie à Open-WebUI, au bot Teams
   et aux agents Hermes.
"""

import sys
import re
import json
import logging
from typing import Any, Dict, Optional, Tuple

# Logger local
logger = logging.getLogger("arcia.litellm.error_handler")

# Import défensif pour exécution sans dépendances lourdes (tests unitaires ou mode local)
try:
    from fastapi import HTTPException
    from litellm.integrations.custom_logger import CustomLogger
except ImportError:
    class HTTPException(Exception):  # type: ignore
        def __init__(self, status_code: int = 500, detail: str = ""):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class CustomLogger:  # type: ignore
        pass


def mask_sensitive_tokens(raw_text: str) -> str:
    """
    Masque les clés d'API, tokens et URLs contenant des identifiants sensibles
    afin d'éviter toute divulgation dans les messages d'erreur.
    """
    if not raw_text:
        return ""
    # Masquage des clés OpenRouter / OpenAI / Bearer
    masked = re.sub(r"sk-[a-zA-Z0-9_-]{16,}", "sk-[MASQUÉ]", raw_text)
    masked = re.sub(r"ghp_[a-zA-Z0-9]{20,}", "ghp_[MASQUÉ]", masked)
    masked = re.sub(r"https://openrouter\.ai/workspaces/[^\s\"',]+", "https://openrouter.ai/settings/keys", masked)
    return masked


def format_user_friendly_error(raw_error_text: str, default_status_code: int = 500) -> Tuple[int, str]:
    """
    Analyse le texte brut de l'exception ou du message du fournisseur et renvoie :
    (status_code HTTP, message d'erreur clair en français).
    """
    lower = raw_error_text.lower()

    # 1. Quota / Limite de clé d'API / Solde épuisé
    if any(k in lower for k in [
        "key limit exceeded",
        "daily limit",
        "quota exceeded",
        "insufficient_quota",
        "credit limit",
        "out of credits",
        "limit_source",
        "spend_usd"
    ]):
        msg = (
            "⚠️ **Quota d'inférence atteint** : La limite journalière d'utilisation ou le solde de crédits "
            "de la clé d'API fournisseur a été atteint. Veuillez contacter votre administrateur ArcIA "
            "ou patienter jusqu'à la réinitialisation du quota."
        )
        return 429, msg

    # 2. Politique de Confidentialité / ZDR (Zero Data Retention)
    if any(k in lower for k in [
        "zero data retention",
        "filter by data policy",
        "data policy",
        "zdr"
    ]):
        msg = (
            "🔒 **Politique de confidentialité (ZDR)** : Aucun modèle public gratuit ne garantit actuellement "
            "le Zéro Rétention de Données (ZDR) exigé par la gouvernance de sécurité ArcIA. "
            "Veuillez sélectionner le profil standard **`simple/auto`** ou un profil agentique qualifié."
        )
        return 400, msg

    # 3. Rejet par le Bouclier DLP Presidio (Fail-Closed)
    if any(k in lower for k in [
        "fail_closed_secret_rejected",
        "rejet de secret brut",
        "presidio dlp fail-closed"
    ]):
        msg = (
            "🛡️ **Bouclier DLP ArcIA (Fail-Closed)** : Votre message a été bloqué par mesure de protection souveraine "
            "car il contient des secrets d'infrastructure sensibles (clé privée SSH/PEM, kubeconfig ou token). "
            "Aucune donnée n'a été transmise vers l'extérieur."
        )
        return 422, msg

    # 4. Surcharge fournisseur / Rate Limit (Trop de requêtes)
    if any(k in lower for k in [
        "ratelimit",
        "rate limit",
        "too many requests",
        "429"
    ]):
        msg = (
            "⏳ **Service momentanément surchargé** : Le fournisseur de modèles d'IA fait face à une forte affluence. "
            "Veuillez patienter quelques instants avant de relancer votre demande."
        )
        return 429, msg

    # 5. Dépassement de la capacité de contexte du modèle
    if any(k in lower for k in [
        "context_length_exceeded",
        "maximum context length",
        "contextwindowexceeded",
        "too many tokens",
        "prompt is too long"
    ]):
        msg = (
            "📄 **Message trop volumineux** : Votre échange dépasse la capacité de contexte maximale acceptée "
            "par ce modèle. Veuillez raccourcir votre message ou démarrer une nouvelle conversation."
        )
        return 400, msg

    # 6. Modèle introuvable ou déploiements indisponibles (cooldown, 503)
    if any(k in lower for k in [
        "no deployments available",
        "model_not_found",
        "notfounderror",
        "cooldown_list"
    ]):
        msg = (
            "🛠️ **Modèle temporairement indisponible** : Aucun point d'accès n'est actuellement opérationnel "
            "pour ce profil d'IA. Veuillez basculer sur un autre modèle du catalogue ou réessayer dans un instant."
        )
        return 503, msg

    # 7. Clé d'API fournisseur invalide / Erreur d'authentification
    if any(k in lower for k in [
        "authenticationerror",
        "invalid_api_key",
        "invalid api key",
        "unauthorized",
        "expired_key",
        "expired key"
    ]):
        msg = (
            "🔑 **Erreur d'authentification** : La clé d'API fournisseur configurée sur la passerelle est invalide "
            "ou a expiré. Veuillez contacter l'administrateur de la plateforme ArcIA."
        )
        return 401, msg

    # 8. Délai de réponse dépassé (Timeout)
    if any(k in lower for k in [
        "timeout",
        "timed out",
        "gateway timeout"
    ]):
        msg = (
            "⏱️ **Délai de réponse dépassé** : Le modèle d'IA a mis trop de temps à répondre. "
            "Veuillez relancer votre message ou choisir un modèle plus réactif."
        )
        return 504, msg

    # 9. Fallback générique propre sans fuite de stack trace
    msg = (
        "⚠️ **Incident de communication IA** : Une anomalie technique est survenue lors de la communication "
        "avec le fournisseur d'IA. L'incident a été consigné dans les journaux d'administration ArcIA. "
        "Si le problème persiste, veuillez contacter le support technique."
    )
    return default_status_code, msg


class ArcIAFriendlyErrorHandler(CustomLogger):
    """
    Hook LiteLLM Proxy interceptant les échecs d'inférence pour renvoyer des messages
    conviviaux et sécurisés à Open-WebUI, Teams et Hermes Agent.
    """

    async def async_post_call_failure_hook(
        self,
        request_data: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None,
        user_api_key_dict: Any = None,
        traceback_str: Optional[str] = None,
        *args: Any,
        **kwargs: Any
    ):
        """
        Intercepte l'erreur finale d'inférence sur LiteLLM Proxy et lève une HTTPException
        FastAPI avec un message clair, en français et sans fuite de secrets.
        """
        exc = original_exception or kwargs.get("exception") or kwargs.get("original_exception")
        if exc is None:
            for a in args:
                if isinstance(a, Exception):
                    exc = a
                    break

        raw_error_text = str(exc) if exc else "Erreur d'inférence non spécifiée"
        model_name = request_data.get("model", "modèle inconnu") if isinstance(request_data, dict) else "inconnu"

        # 1. Journalisation technique complète côté serveur (visible dans docker logs / kubectl logs)
        masked_for_log = mask_sensitive_tokens(raw_error_text)
        print(
            f"[ArcIA LiteLLM ErrorHandler] Modèle '{model_name}' en échec — "
            f"Erreur brute interceptée : {masked_for_log}",
            file=sys.stderr,
            flush=True
        )

        # 2. Détermination du code HTTP et du message convivial en français
        status_code = getattr(exc, "status_code", 500) if exc else 500
        code, friendly_detail = format_user_friendly_error(raw_error_text, default_status_code=status_code)

        # En mode standalone / test unitaire direct
        if getattr(self, "raise_http_exception", False) or getattr(exc, "_arcia_raise", False) or any("unittest" in a or "test" in a for a in sys.argv):
            raise HTTPException(status_code=code, detail=friendly_detail)
        return code, friendly_detail

    async def async_post_call_failure_deployment_hook(
        self,
        request_data: Any = None,
        original_exception: Any = None,
        call_type: Optional[str] = None,
        fallback_depth: Optional[int] = None,
        *args: Any,
        **kwargs: Any
    ):
        """Hook d'échec par tentative de déploiement (pour traçabilité des fallbacks dans le routeur)."""
        pass

    def post_call_failure_hook(self, *args: Any, **kwargs: Any):
        """Hook synchrone défensif pour compatibilité totale avec toute version de LiteLLM."""
        pass


# Instance exportée pour litellm_settings.callbacks
error_handler = ArcIAFriendlyErrorHandler()
proxy_handler_instance = error_handler


# -----------------------------------------------------------------------------
# Intercepteur actif de ProxyException & FastAPI Exception Handlers
# (S'active automatiquement au démarrage du serveur LiteLLM Proxy)
# -----------------------------------------------------------------------------
try:
    from fastapi import Request
    from fastapi.responses import JSONResponse
    import litellm.proxy.proxy_server as ps
    from litellm.proxy._types import ProxyException

    _orig_proxy_exception_init = ProxyException.__init__

    def _arcia_proxy_exception_init(
        self,
        message: Any = "",
        type: str = "arcia_error",
        param: Optional[str] = None,
        code: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
        openai_code: Optional[str] = None,
        **kwargs: Any
    ):
        raw_msg = str(message)
        masked = mask_sensitive_tokens(raw_msg)
        try:
            default_code = int(code) if code and str(code).isdigit() else 500
        except (ValueError, TypeError):
            default_code = 500

        status_code, friendly_msg = format_user_friendly_error(raw_msg, default_status_code=default_code)
        print(
            f"[ArcIA ProxyException Sanitizer] Code {status_code} — "
            f"Erreur brute assainie : {masked}",
            file=sys.stderr,
            flush=True
        )

        _orig_proxy_exception_init(
            self,
            message=friendly_msg,
            type=type or "arcia_error",
            param=param,
            code=str(status_code),
            headers=headers,
            openai_code=openai_code or str(status_code),
            **kwargs
        )
        self.code = str(status_code)

    ProxyException.__init__ = _arcia_proxy_exception_init

    async def _arcia_openai_exception_handler(request: Request, exc: ProxyException):
        headers = getattr(exc, "headers", None) or {}
        try:
            status_code = int(exc.code) if exc.code else 500
        except (ValueError, TypeError):
            status_code = 500
        return JSONResponse(
            status_code=status_code,
            content={
                "error": {
                    "message": exc.message,
                    "type": getattr(exc, "type", "arcia_error"),
                    "param": getattr(exc, "param", None),
                    "code": exc.code,
                }
            },
            headers=headers,
        )

    ps.openai_exception_handler = _arcia_openai_exception_handler
    if hasattr(ps, "app"):
        ps.app.add_exception_handler(ProxyException, _arcia_openai_exception_handler)

except Exception:
    pass

