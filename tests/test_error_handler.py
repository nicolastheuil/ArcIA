#!/usr/bin/env python3
"""
Unit tests for ArcIA User-Friendly Error Handlers (LiteLLM & Hermes Agent).
Validates sanitization, masking of sensitive keys, French friendly formatting,
and fail-safe exception transformation.
"""

import os
import sys
import asyncio
import unittest

# Ajouter les chemins de modules
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "services", "litellm"))
sys.path.insert(0, os.path.join(ROOT_DIR, "services", "hermes"))

from error_handler import (
    format_user_friendly_error,
    mask_sensitive_tokens,
    error_handler,
    HTTPException,
)
import plugin as hermes_plugin


class TestLiteLLMErrorHandler(unittest.TestCase):

    def setUp(self):
        self.raw_user_reported_error = (
            'litellm.NotFoundError: NotFoundError: OpenrouterException - {"error":{"message":"No endpoints found '
            'matching your data policy (Zero data retention). Configure: https://openrouter.ai/settings/privacy","code":404,'
            '"metadata":{"routing_funnel":[{"step":"Initial Endpoints","endpoint_count":10}],'
            '"failed_routing_step":"Filter by Data Policy"}}}. Received Model Group=simple/free '
            'Available Model Group Fallbacks=[\'simple/auto\'] Error doing the fallback: litellm.APIError: APIError: '
            'OpenrouterException - {"error":{"message":"Key limit exceeded (daily limit). Manage it using '
            'https://openrouter.ai/workspaces/default/keys/dacb4c9ed1a320fade86cbac6692ec636e1d8cc94308a63bf66279c519bf1d7a '
            '$0.00 of $0.00 used; resets 2026-10-19T00:00:00.000Z.","code":403,"metadata":{"limit_source":"openrouter_key_limit",'
            '"remedy_hint":"Raise or remove this API key\'s usage limit at https://openrouter.ai/settings/keys, or use a key without a limit.",'
            '"scope":"key_limit","limit_usd":0,"spend_usd":0,"resets_at":"2026-10-19T00:00:00.000Z"}}}. '
            'Received Model Group=simple/auto Available Model Group Fallbacks=[\'simple/free\'] Error doing the fallback: '
            'No deployments available for selected model, Try again in 5 seconds. Passed model=simple/free. pre-call-checks=False, '
            'cooldown_list=[(\'ac135b918daa0bc4e25fa0a89924bb85a1a6308dfa139aedd2271e7348716ac6\', {\'exception_received\': \'...\'})]'
        )

    def test_user_reported_error_maps_to_quota_reached(self):
        """Vérifie que l'erreur exacte rapportée par l'utilisateur renvoie un message de quota clair sans fuite de clé."""
        status_code, msg = format_user_friendly_error(self.raw_user_reported_error)
        self.assertEqual(status_code, 429)
        self.assertIn("Quota d'inférence atteint", msg)
        self.assertNotIn("dacb4c9ed1a320fade86cbac6692ec636e1d8cc94308a63bf66279c519bf1d7a", msg)
        self.assertNotIn("routing_funnel", msg)
        self.assertNotIn("cooldown_list", msg)

    def test_zdr_policy_formatting(self):
        """Vérifie qu'une incompatibilité ZDR pure renvoie un message orientant vers simple/auto."""
        err = '{"error":{"message":"No endpoints found matching your data policy (Zero data retention)"}}'
        status_code, msg = format_user_friendly_error(err)
        self.assertEqual(status_code, 400)
        self.assertIn("Politique de confidentialité (ZDR)", msg)
        self.assertIn("simple/auto", msg)

    def test_presidio_fail_closed_formatting(self):
        """Vérifie le message convivial en cas de blocage de secret brut par Presidio."""
        err = 'HTTP 422 FAIL_CLOSED_SECRET_REJECTED: Clé privée PEM détectée'
        status_code, msg = format_user_friendly_error(err)
        self.assertEqual(status_code, 422)
        self.assertIn("Bouclier DLP ArcIA (Fail-Closed)", msg)

    def test_rate_limit_formatting(self):
        """Vérifie le message en cas de surcharge du fournisseur."""
        err = "litellm.RateLimitError: 429 Too Many Requests from OpenAI"
        status_code, msg = format_user_friendly_error(err)
        self.assertEqual(status_code, 429)
        self.assertIn("Service momentanément surchargé", msg)

    def test_context_window_exceeded_formatting(self):
        """Vérifie le message en cas de message trop volumineux pour le modèle."""
        err = "litellm.ContextWindowExceededError: This model's maximum context length is 8192 tokens"
        status_code, msg = format_user_friendly_error(err)
        self.assertEqual(status_code, 400)
        self.assertIn("Message trop volumineux", msg)

    def test_mask_sensitive_tokens(self):
        """Vérifie que les clés d'API et URLs privées sont caviardées dans les logs."""
        raw = "Error with key sk-abcdef1234567890123456 and url https://openrouter.ai/workspaces/default/keys/secret123"
        masked = mask_sensitive_tokens(raw)
        self.assertNotIn("sk-abcdef1234567890123456", masked)
        self.assertNotIn("secret123", masked)
        self.assertIn("sk-[MASQUÉ]", masked)
        self.assertIn("https://openrouter.ai/settings/keys", masked)

    def test_async_post_call_failure_hook_raises_http_exception(self):
        """Vérifie que le hook LiteLLM lève bien une HTTPException typée avec message convivial."""
        async def run_hook():
            class DummyExc(Exception):
                status_code = 404
            exc = DummyExc(self.raw_user_reported_error)
            await error_handler.async_post_call_failure_hook(
                request_data={"model": "simple/free"},
                original_exception=exc,
            )

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(run_hook())

        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIn("Quota d'inférence atteint", ctx.exception.detail)


class TestHermesErrorHandler(unittest.TestCase):

    def test_hermes_format_error_presidio_blocked(self):
        """Vérifie le formatage Markdown d'un blocage Presidio pour les Power Users."""
        formatted = hermes_plugin.format_hermes_error("Presidio DLP Fail-Closed [422 Rejet de secret brut]")
        self.assertIn("[!CAUTION]", formatted)
        self.assertIn("ArcIA Presidio DLP — Rejet Fail-Closed", formatted)

    def test_hermes_format_error_presidio_unavailable(self):
        """Vérifie le formatage Markdown en cas de Presidio indisponible."""
        formatted = hermes_plugin.format_hermes_error("Presidio DLP unreachable or failed in Fail-Closed mode")
        self.assertIn("[!WARNING]", formatted)
        self.assertIn("Service Indisponible", formatted)

    def test_hermes_format_error_quota(self):
        """Vérifie le formatage Markdown en cas de quota dépassé."""
        formatted = hermes_plugin.format_hermes_error("Key limit exceeded (daily limit)")
        self.assertIn("[!WARNING]", formatted)
        self.assertIn("Quota d'inférence atteint", formatted)

    def test_hermes_format_error_zdr(self):
        """Vérifie le formatage Markdown en cas de conflit ZDR."""
        formatted = hermes_plugin.format_hermes_error("No endpoints found matching your data policy (Zero data retention)")
        self.assertIn("[!IMPORTANT]", formatted)
        self.assertIn("Politique de confidentialité (ZDR)", formatted)

    def test_hermes_custom_exceptions_inheritance(self):
        """Vérifie que les exceptions Presidio d'Hermes héritent de RuntimeError pour compatibilité."""
        self.assertTrue(issubclass(hermes_plugin.ArcIAPresidioBlockedException, RuntimeError))
        self.assertTrue(issubclass(hermes_plugin.ArcIAPresidioUnavailableException, RuntimeError))


if __name__ == "__main__":
    unittest.main()
