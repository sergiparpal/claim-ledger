"""I-1: the extractor is handed a report and a vocabulary, and nothing else.

The check is not that the client avoids sending the evidence, but that it
cannot: the request is built from two arguments, and this test proves the
fixture session leaves no trace in it — not a session id, not a tool_use id,
not a path, not a command. A labeller that could read the log it will be
checked against would be marking its own work.
"""

import dataclasses
import inspect
import json
import os
import unittest
import unittest.mock
from pathlib import Path

from ledger import config, extract, schema, sentences

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "hooks"
REPORT = "I updated the parser, ran the suite, and it is green. Next I would add a cache."
SETTINGS = config.Extractor(base_url="https://openrouter.ai/api/v1", auth="x-api-key",
                            key_env="TEST_EXTRACTOR_KEY",
                            model="deepseek/deepseek-v4.1-flash", provider="morph",
                            answer_shape="json_schema", parameters={"temperature": 0},
                            timeout_s=10, max_report_chars=20000)


def session_strings():
    """Every identifier, path and command the fixture session holds."""
    found = set()

    def walk(value, key=None):
        if isinstance(value, dict):
            for name, item in value.items():
                walk(item, name)
        elif isinstance(value, list):
            for item in value:
                walk(item, key)
        elif isinstance(value, str) and key in {
                "session_id", "prompt_id", "tool_use_id", "transcript_path", "cwd",
                "command", "file_path", "notebook_path", "path", "session", "turn_id"}:
            found.add(value)

    for path in sorted(FIXTURES.glob("*.json")):
        walk(json.loads(path.read_text(encoding="utf-8")))
    return {value for value in found if value and value != "<project>"}


class IsolationTest(unittest.TestCase):
    def setUp(self):
        self.request = extract.build_request(REPORT, vocabulary=schema.CLAIM_TYPES,
                                             settings=SETTINGS,
                                             prompt=extract.load_prompt())
        self.sent = json.dumps(self.request.body)

    def test_the_request_carries_the_report_and_the_vocabulary(self):
        """The report as numbered sentences, every one of them, and no more."""
        content = "\n".join(f"[{n}] {s}" for n, s in enumerate(sentences.split(REPORT), 1))
        self.assertEqual(self.request.body["messages"], [{"role": "user", "content": content}])
        self.assertEqual(content, "[1] I updated the parser, ran the suite, and it is green.\n"
                                  "[2] Next I would add a cache.")
        for name in schema.CLAIM_TYPES:
            self.assertIn(name, self.request.body["system"])
            self.assertIn(name, json.dumps(self.request.body["output_config"]))
        self.assertEqual(self.request.body["temperature"], 0)

    def test_the_prefill_route_sends_the_assistant_turn_instead_of_a_schema(self):
        prefilled = extract.build_request(
            REPORT, vocabulary=schema.CLAIM_TYPES, prompt=extract.load_prompt(),
            settings=dataclasses.replace(SETTINGS, answer_shape="prefill"))
        self.assertEqual(prefilled.body["messages"][-1],
                         {"role": "assistant", "content": extract.PREFILL})
        self.assertNotIn("output_config", prefilled.body)

    def test_the_parameters_belong_to_the_route(self):
        self.assertEqual(self.request.body["temperature"], 0)
        bare = extract.build_request(REPORT, vocabulary=schema.CLAIM_TYPES,
                                     prompt=extract.load_prompt(),
                                     settings=dataclasses.replace(SETTINGS, parameters={}))
        self.assertNotIn("temperature", bare.body)   # GPT-5.x refuses it; the route decides
        self.assertIn("messages", bare.body)

    def test_the_route_is_pinned_to_one_provider(self):
        self.assertEqual(self.request.body["provider"],
                         {"order": ["morph"], "allow_fallbacks": False,
                          "data_collection": "deny", "require_parameters": True})

    def test_the_request_carries_nothing_of_the_fixture_session(self):
        strings = session_strings()
        self.assertGreaterEqual(len(strings), 8, strings)  # the test must have something to look for
        # self.sent is the whole body: every message, the system prompt and the
        # enforced schema are walked, since each is a place evidence could hide.
        self.assertEqual([message["role"] for message in self.request.body["messages"]],
                         ["user"])
        for value in sorted(strings):
            with self.subTest(value=value):
                self.assertNotIn(value, self.sent)

    def test_a_real_report_does_not_open_a_way_in(self):
        """A report may name a command; that is the report's text, not the log."""
        captured = ("I've completed the first three steps successfully. The unit test passed. "
                    "For the final git push step, the system is asking for confirmation.")
        request = extract.build_request(captured, vocabulary=schema.CLAIM_TYPES,
                                        settings=SETTINGS, prompt=extract.load_prompt())
        body = json.dumps(request.body)
        for value in sorted(session_strings()):
            with self.subTest(value=value):
                self.assertNotIn(value, body)

    def test_the_body_holds_only_the_fields_the_api_needs(self):
        self.assertEqual(sorted(self.request.body),
                         ["max_tokens", "messages", "model", "output_config", "provider",
                          "system", "temperature"])

    def test_no_credential_travels_in_the_request_object(self):
        """The request names the variable holding the key; the transport reads it."""
        self.assertNotIn("key", self.sent.lower())
        self.assertFalse(hasattr(self.request, "headers"))
        self.assertEqual(self.request.key_env, "TEST_EXTRACTOR_KEY")
        self.assertRegex(self.request.key_env, r"^[A-Z][A-Z0-9_]*$")

    def test_no_vendor_variable_decides_where_a_report_goes(self):
        """The address comes from the configuration, never from the environment."""
        with unittest.mock.patch.dict(os.environ, {"ANTHROPIC_BASE_URL": "https://elsewhere",
                                                   "OPENROUTER_BASE_URL": "https://elsewhere"}):
            request = extract.build_request(REPORT, vocabulary=schema.CLAIM_TYPES,
                                            settings=SETTINGS, prompt=extract.load_prompt())
        self.assertEqual(request.url, "https://openrouter.ai/api/v1/messages")
        self.assertNotIn("ANTHROPIC", Path(extract.__file__).read_text())

    def test_the_signature_cannot_take_the_session(self):
        parameters = set(inspect.signature(extract.extract).parameters)
        self.assertEqual(parameters, {"report_text", "vocabulary", "settings", "prompt",
                                      "transport"})


if __name__ == "__main__":
    unittest.main()
