"""Le chemin d'authentification LiteLLM peut réassigner le message après création."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch


class TestLateAuthenticationMessage(unittest.TestCase):
    def test_late_token_diagnostics_are_sanitized_without_accepting_the_token(self):
        class ProxyException(Exception):
            def __init__(self, message="", type=None, param=None, code=None, headers=None, **kwargs):
                self.message, self.type, self.param = message, type, param
                self.code, self.headers = code, headers

        modules = {name: ModuleType(name) for name in (
            "fastapi", "fastapi.responses", "litellm", "litellm.integrations",
            "litellm.integrations.custom_logger", "litellm.proxy",
            "litellm.proxy.proxy_server", "litellm.proxy._types")}
        for name, module in modules.items():
            if "." in name:
                parent, child = name.rsplit(".", 1)
                setattr(modules[parent], child, module)
        modules["fastapi"].HTTPException = Exception
        modules["fastapi"].Request = object
        modules["fastapi.responses"].JSONResponse = object
        modules["litellm.integrations.custom_logger"].CustomLogger = object
        modules["litellm.proxy._types"].ProxyException = ProxyException
        modules["litellm.proxy.proxy_server"].app = SimpleNamespace(add_exception_handler=lambda *args: None)
        path = Path(__file__).resolve().parents[1] / "services/litellm/error_handler.py"
        with patch.dict(sys.modules, modules):
            spec = importlib.util.spec_from_file_location("synthetic_litellm_error_handler", path)
            handler = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(handler)
            error = ProxyException(message="Authentication Error, token not found in db",
                                   type="token_not_found_in_db", param="key", code=401)
            # Comportement de user_api_key_auth.py v1.72.6 après avoir attrapé l'exception.
            error.message = ("Authentication Error, Invalid proxy server token passed. "
                             "Received API Key = sk-synthetic-private-key, Key Hash (Token) = synthetic-hash. "
                             "Unable to find token in cache or `LiteLLM_VerificationTokenTable`")
            self.assertEqual(str(error.code), "401")
            self.assertEqual(error.type, "token_not_found_in_db")
            self.assertEqual(error.param, "key")
            self.assertIn("Session d'administration", error.message)
            self.assertNotIn("sk-synthetic", error.message)
            self.assertNotIn("Key Hash", error.message)
            self.assertNotIn("VerificationTokenTable", error.message)


if __name__ == "__main__":
    unittest.main()
