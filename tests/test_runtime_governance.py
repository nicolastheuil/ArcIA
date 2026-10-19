"""Admission réelle SQLite/httpx et arrêt obligatoire, avec données synthétiques."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import httpx
from services.hermes import runtime_guard as guard

ROOT = Path(__file__).resolve().parents[1]
EMAIL = "alice.synthetic@example.org"
ENV = {"API_SERVER_KEY": "synthetic-runtime-key-" + "x" * 32,
       "OPENAI_BASE_URL": "http://gateway.invalid:4000/v1"}


def sanitized_batch(texts, **kwargs):
    return [sanitized(text, **kwargs) for text in texts]


def sanitized(text, **kwargs):
    if "SYNTHETIC_BLOCKED" in text:
        raise RuntimeError("synthetic private material")
    return text.replace(EMAIL, "[EMAIL_01]")


class RuntimeGovernanceTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, ENV)
        env.start()
        self.addCleanup(env.stop)
        sanitizer = patch.object(guard.plugin, "sanitize_via_presidio", side_effect=sanitized)
        sanitizer.start()
        self.addCleanup(sanitizer.stop)
        batch = patch.object(guard.plugin, "sanitize_batch_via_presidio", side_effect=sanitized_batch)
        batch.start()
        self.addCleanup(batch.stop)

    def test_sqlite_connection_cursor_and_batch_never_write_raw_pii(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(sqlite3, "connect", sqlite3.connect):
            guard.install_sqlite()
            path = Path(directory) / "state.db"
            connection = sqlite3.connect(path)
            connection.execute("CREATE TABLE messages (content TEXT)")
            connection.execute("INSERT INTO messages VALUES (?)", (EMAIL,))
            connection.cursor().execute("INSERT INTO messages VALUES (?)", (EMAIL,))
            connection.executemany("INSERT INTO messages VALUES (?)", [(EMAIL,), (EMAIL,)])
            connection.commit()
            self.assertEqual(connection.execute("SELECT content FROM messages").fetchall(), [("[EMAIL_01]",)] * 4)
            with self.assertRaises(guard.DLPStop):
                connection.execute("INSERT INTO messages VALUES ('" + EMAIL + "')")
            with self.assertRaises(guard.DLPStop):
                connection.cursor().executemany("INSERT INTO messages VALUES (?)", [(EMAIL,), ("SYNTHETIC_BLOCKED",)])
            self.assertEqual(connection.execute("SELECT count(*) FROM messages").fetchone()[0], 4)
            connection.close()
            self.assertNotIn(EMAIL.encode(), path.read_bytes())

    def test_fts_control_word_does_not_allow_private_literals_or_outage(self):
        with patch.object(guard.plugin, "sanitize_batch_via_presidio", return_value=["[PERSON_01]"]):
            guard.admit_sql("INSERT INTO messages_fts(messages_fts) VALUES ('delete')")
            with self.assertRaises(guard.DLPStop):
                guard.admit_sql("INSERT INTO messages VALUES ('" + EMAIL + "')")
        with patch.object(guard.plugin, "sanitize_batch_via_presidio", side_effect=OSError()):
            with self.assertRaises(guard.DLPStop):
                guard.admit_sql("INSERT INTO messages_fts(messages_fts) VALUES ('delete')")

    def test_sql_comments_never_turn_schema_into_a_string_literal(self):
        with patch.object(guard.plugin, "sanitize_batch_via_presidio", side_effect=sanitized_batch) as batch:
            guard.admit_sql("-- user's schema\nCREATE TABLE example (content TEXT DEFAULT 'safe'); -- don't parse this")
            self.assertEqual(batch.call_args.args[0], ["safe"])
            with self.assertRaises(guard.DLPStop):
                guard.admit_sql("INSERT INTO example VALUES ('" + EMAIL + "--value')")

    def test_outage_denies_parameter_and_literal_sql_and_keeps_reads_available(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(sqlite3, "connect", sqlite3.connect):
            guard.install_sqlite()
            connection = sqlite3.connect(Path(directory) / "state.db")
            connection.execute("CREATE TABLE messages (content TEXT)")
            with patch.object(guard.plugin, "sanitize_batch_via_presidio", side_effect=OSError("synthetic unavailable")):
                for sql, params in (("INSERT INTO messages VALUES (?)", ("test",)), ("-- comment\nINSERT INTO messages VALUES ('test')", ())):
                    with self.assertRaises(guard.DLPStop):
                        connection.execute(sql, params)
            self.assertEqual(connection.execute("SELECT count(*) FROM messages").fetchone()[0], 0)
            connection.close()

    def test_httpx_transport_redacts_tools_and_rejects_outage_and_other_gateways(self):
        captured = []
        def receive(request):
            captured.append(json.loads(request.read()))
            return httpx.Response(200, json={"ok": True})
        with patch.object(httpx.Client, "send", httpx.Client.send), patch.object(httpx.AsyncClient, "send", httpx.AsyncClient.send):
            guard.install_httpx()
            with httpx.Client(transport=httpx.MockTransport(receive)) as client:
                payload = {"model": "mission", "messages": [{"role": "tool", "content": EMAIL}], "instructions": EMAIL}
                client.post(ENV["OPENAI_BASE_URL"] + "/chat/completions", json=payload)
                self.assertNotIn(EMAIL, json.dumps(captured))
                self.assertIn("[EMAIL_01]", json.dumps(captured))
                with self.assertRaises(guard.DLPStop):
                    client.post("http://other.invalid:4000/v1/responses", json=payload)
                with patch.object(guard.plugin, "sanitize_batch_via_presidio", side_effect=OSError("unavailable")):
                    with self.assertRaises(guard.DLPStop):
                        client.post(ENV["OPENAI_BASE_URL"] + "/responses", json=payload)
                self.assertEqual(len(captured), 1)

    def test_identity_scope_differs_between_users_and_ignores_plugin_disable_flag(self):
        first = guard.scope()
        with patch.dict(os.environ, {"API_SERVER_KEY": "other-synthetic-key-" + "y" * 32}):
            self.assertNotEqual(first, guard.scope())
        with patch.object(guard.plugin, "PRESIDIO_FAIL_CLOSED", False):
            guard.clean_text("synthetic")
            self.assertTrue(guard.plugin.PRESIDIO_FAIL_CLOSED)

    def test_model_identifier_is_preserved_but_same_text_in_content_is_sanitized(self):
        with patch.object(guard.plugin, "sanitize_batch_via_presidio", side_effect=lambda texts, **kwargs: [s.replace("Claude", "[PERSON_01]") for s in texts]):
            value = {"model": "Claude", "messages": [{"role": "user", "content": "Claude"}]}
            result = guard.transform(value)
            self.assertEqual(result["model"], "Claude")
            self.assertEqual(result["messages"][0]["content"], "[PERSON_01]")
            self.assertEqual(guard.clean_parameters(("fts_rebuild_high_water",)), ["fts_rebuild_high_water"])

    def test_generated_lease_holder_is_preserved_only_in_the_native_lease_table(self):
        holder = "pid=1:pidns=4026532534:turn=api-0123456789abcdef:api-0123456789abcdef:1234abcd:platform=api_server"
        sql = "INSERT INTO session_turn_leases (holder) VALUES (?)"
        with patch.object(guard.plugin, "sanitize_batch_via_presidio", side_effect=lambda texts, **kwargs: [text.replace("4026532534", "[PHONE_01]") for text in texts]):
            self.assertEqual(guard.clean_parameters((holder,), sql), [holder])
            self.assertNotEqual(guard.clean_parameters((holder,), "INSERT INTO messages VALUES (?)"), [holder])
        with patch.object(guard.plugin, "sanitize_batch_via_presidio", side_effect=OSError()), self.assertRaises(guard.DLPStop):
            guard.clean_parameters((holder,), sql)

    def test_native_display_digest_is_opaque_but_blob_content_is_refused(self):
        digest = bytes(range(32))
        sql = "INSERT INTO messages (content, display_identity) VALUES (?, ?)"
        self.assertEqual(guard.clean_parameters((EMAIL, digest), sql), ["[EMAIL_01]", digest])
        self.assertEqual(guard.clean_parameters((1, digest, 2), "UPDATE messages SET display_order = ?, display_identity = ? WHERE id = ?"), [1, digest, 2])
        for data in ((digest, None), (EMAIL, digest[:-1])):
            with self.assertRaises(guard.DLPStop):
                guard.clean_parameters(data, sql)
        with patch.object(guard.plugin, "sanitize_batch_via_presidio", side_effect=OSError()), self.assertRaises(guard.DLPStop):
            guard.clean_parameters((EMAIL, digest), sql)

    def test_encoded_json_keeps_grammar_and_rejects_unqualified_media(self):
        payload = {"arguments": json.dumps({"contact": EMAIL, "count": 2}), "role": "tool"}
        result = guard.clean_structure(payload)
        self.assertEqual(json.loads(result["arguments"]), {"contact": "[EMAIL_01]", "count": 2})
        self.assertEqual(result["role"], "tool")
        with self.assertRaises(guard.DLPStop):
            guard.transform({"type": "image_url", "image_url": {"url": "data:synthetic"}})

    def test_startup_cannot_continue_without_private_identity(self):
        environment = dict(os.environ, PYTHONPATH=str(ROOT / "services/hermes"), ARCIA_GOVERNANCE_REQUIRED="true", API_SERVER_KEY="")
        result = subprocess.run([sys.executable, "-c", "raise AssertionError('unprotected startup')"], env=environment,
                                capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 78)
        self.assertNotIn(b"unprotected startup", result.stderr)

    def test_native_launcher_cannot_drop_guard_by_resetting_pythonpath(self):
        with tempfile.TemporaryDirectory() as directory:
            anchor = (ROOT / "services/hermes/arcia_governance.pth").read_text().replace("/opt/arcia-governance", str(ROOT / "services/hermes"))
            Path(directory, "arcia_governance.pth").write_text(anchor)
            code = "import site; site.addsitedir(" + repr(directory) + "); import runtime_guard; print(runtime_guard.INSTALLED)"
            environment = dict(os.environ, PYTHONPATH="", ARCIA_GOVERNANCE_REQUIRED="true", **ENV)
            result = subprocess.run([sys.executable, "-c", code], env=environment, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0)
            self.assertIn(b"True", result.stdout)
            environment["API_SERVER_KEY"] = ""
            denied = subprocess.run([sys.executable, "-c", code], env=environment, capture_output=True, timeout=30)
            self.assertEqual(denied.returncode, 78)

    def test_numeric_entity_type_and_generation_are_rehydrated_in_private_scope(self):
        token = "[IPV4_" + "A" * 32 + "_01]"
        with patch.object(guard.plugin, "deanonymize_via_presidio", return_value="10.20.30.40") as restore:
            self.assertEqual(guard.transform(token, True), "10.20.30.40")
            self.assertEqual(restore.call_args.kwargs["session_id"], guard.scope())

    def test_streaming_rehydrates_a_split_token_only_with_the_private_scope(self):
        pending = {}
        with patch.object(guard.plugin, "deanonymize_via_presidio", return_value=EMAIL) as hydrate:
            first = guard.hydrate_sse_event({"choices": [{"index": 0, "delta": {"content": "Bonjour [EMA"}}]}, pending)
            self.assertEqual(first["choices"][0]["delta"]["content"], "Bonjour ")
            hydrate.assert_not_called()
            last = guard.hydrate_sse_event({"choices": [{"index": 0, "delta": {"content": "IL_01]"}}]}, pending)
            self.assertEqual(last["choices"][0]["delta"]["content"], EMAIL)
            self.assertEqual(hydrate.call_args.kwargs["session_id"], guard.scope())
            self.assertEqual(pending, {})


class AsyncGovernanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_aiohttp_admission_precedes_handler_and_rehydrates_sse(self):
        from aiohttp import web
        from aiohttp.test_utils import TestClient, TestServer
        handled = []
        async def endpoint(request):
            handled.append(await request.json())
            response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
            await response.prepare(request)
            await response.write(b'event: approval.request\ndata: {"choices": ["once", "deny"]}\n\n')
            for text, finish in (("Bonjour [EMA", None), ("IL_01]", None), ("", "stop")):
                event = {"choices": [{"index": 0, "delta": {"content": text}, "finish_reason": finish}]}
                await response.write(b"data: " + json.dumps(event).encode() + b"\n\n")
            await response.write(b"data: [DONE]\n\n")
            await response.write_eof()
            return response
        with patch.dict(os.environ, ENV), patch.object(guard.plugin, "sanitize_batch_via_presidio", side_effect=sanitized_batch), \
             patch.object(guard.plugin, "deanonymize_via_presidio", return_value=EMAIL), \
             patch.object(web.Application, "__init__", web.Application.__init__), patch.object(web.StreamResponse, "write", web.StreamResponse.write):
            guard.install_aiohttp()
            app = web.Application()
            app.router.add_post("/v1/chat/completions", endpoint)
            async with TestClient(TestServer(app)) as client:
                response = await client.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": EMAIL}]})
                self.assertEqual(response.status, 200)
                streamed = await response.text()
                self.assertIn(EMAIL, streamed)
                self.assertIn('event: approval.request', streamed)
                self.assertIn('"choices": ["once", "deny"]', streamed)
                self.assertNotIn(EMAIL, json.dumps(handled))
                with patch.object(guard.plugin, "sanitize_batch_via_presidio", side_effect=OSError("unavailable")):
                    denied = await client.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "synthetic"}]})
                    self.assertEqual(denied.status, 422)
                self.assertEqual(len(handled), 1)

    async def test_async_llm_transport_uses_the_same_admission(self):
        captured = []
        def receive(request):
            captured.append(request.read())
            return httpx.Response(200, json={"ok": True})
        with patch.dict(os.environ, ENV), patch.object(guard.plugin, "sanitize_batch_via_presidio", side_effect=sanitized_batch), \
             patch.object(httpx.Client, "send", httpx.Client.send), patch.object(httpx.AsyncClient, "send", httpx.AsyncClient.send):
            guard.install_httpx()
            async with httpx.AsyncClient(transport=httpx.MockTransport(receive)) as client:
                await client.post(ENV["OPENAI_BASE_URL"] + "/chat/completions", json={"messages": [{"role": "user", "content": EMAIL}]})
            self.assertNotIn(EMAIL.encode(), captured[0])


if __name__ == "__main__":
    unittest.main()
