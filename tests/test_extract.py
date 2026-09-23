"""ledger.extract and ledger.schema, replayed through the transport double.

Every case here runs the real client: the request is built, the envelope is
parsed, the answer is validated and its defects are counted. What the double
replaces is the network, so no test makes a call.
"""

import dataclasses
import json
import os
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

from ledger import config, extract, schema
from tests import doubles

REPORT = ("I've completed the first three steps successfully. The unit test passed. "
          "I'll proceed with staging, committing, and pushing the changes.")
# The report the recorded answer was really taken from, captured on 20 September 2026.
CAPTURED_REPORT = (
    "I've completed the first three steps successfully. The unit test passed. For the "
    "final git push step, the system is asking for confirmation since git operations "
    "affect the remote repository. Since you explicitly requested the push, I'll proceed "
    "with staging, committing, and pushing the changes.\n\nHowever, I need to confirm: "
    "should I proceed with the git add, commit, and push operations? This will push the "
    "new code to the remote repository.")
SETTINGS = config.Extractor(base_url="https://openrouter.ai/api/v1", auth="x-api-key",
                            key_env="TEST_EXTRACTOR_KEY",
                            model="deepseek/deepseek-v4.1-flash", provider="morph",
                            answer_shape="json_schema", parameters={"temperature": 0},
                            timeout_s=10, max_report_chars=20000)
PREFILLED = dataclasses.replace(SETTINGS, answer_shape="prefill")


def claims(*items):
    """The claims as an enforced schema returns them: one whole object."""
    return json.dumps({"claims": [dict(zip(("span", "type", "referents"), item))
                                  for item in items]})


REAL_CLAIMS = (("I've completed the first three steps successfully", "judgment", []),
               ("The unit test passed", "suite_passed", ["unit test"]),
               ("I'll proceed with staging, committing, and pushing the changes",
                "intent", []))


class ExtractTest(unittest.TestCase):
    def run_extract(self, *answers, report=REPORT, settings=SETTINGS, **overrides):
        transport = doubles.Transport(*answers)
        if overrides:
            settings = dataclasses.replace(settings, **overrides)
        result = extract.extract(report, settings=settings, transport=transport)
        return result, transport


class AnswerTest(ExtractTest):
    """A real answer from the route in use, replayed through the real client."""

    def test_a_recorded_answer_replays_end_to_end(self):
        result, transport = self.run_extract(
            doubles.recorded("openrouter-deepseek-v4.1-flash"), report=CAPTURED_REPORT)
        self.assertEqual([(c.type, c.span) for c in result.claims], [
            ("judgment", "I've completed the first three steps successfully."),
            ("suite_passed", "The unit test passed."),
            ("intent", "I'll proceed with staging, committing, and pushing the changes.")])
        self.assertEqual(result.claims[1].referents, ("unit test",))
        self.assertEqual(result.defects, ())
        self.assertEqual(len(transport.requests), 1)

    def test_the_route_in_use_returns_no_reasoning_at_all(self):
        envelope = json.loads(doubles.recorded("openrouter-deepseek-v4.1-flash").body)
        self.assertEqual([b["type"] for b in envelope["content"]], ["text"])
        self.assertEqual(envelope["model"], "deepseek/deepseek-v4.1-flash")

    def test_a_reasoning_block_is_passed_over_where_a_route_sends_one(self):
        """glm's recording, kept because that route reasons before it answers."""
        envelope = json.loads(doubles.recorded("openrouter-glm-5.3-flash").body)
        self.assertEqual([b["type"] for b in envelope["content"]], ["thinking", "text"])
        result, _ = self.run_extract(doubles.recorded("openrouter-glm-5.3-flash"),
                                     report=CAPTURED_REPORT)
        self.assertEqual(len(result.claims), 3)

    def test_the_provenance_travels_with_every_claim(self):
        result, _ = self.run_extract(doubles.recorded("openrouter-deepseek-v4.1-flash"),
                                     report=CAPTURED_REPORT)
        version = extract.load_prompt().version
        self.assertTrue(version.startswith("extract-1+"), version)
        expected = schema.Provenance(prompt_version=version,
                                     model="deepseek/deepseek-v4.1-flash",
                                     base_url="https://openrouter.ai/api/v1",
                                     provider="Morph")
        self.assertEqual({c.provenance for c in result.claims}, {expected})
        self.assertEqual(result.provenance, expected)


class RecordingFromTheOldRouteTest(ExtractTest):
    """What the client does with answers recorded before the prefill existed."""

    def test_the_code_fence_it_really_sent_is_refused(self):
        # Observed on 20 September 2026 through the CLI: haiku wrapped the
        # JSON in ```json. The client repairs nothing, so the turn is UNKNOWN.
        with self.assertRaises(schema.SchemaError):
            self.run_extract(doubles.recorded_without_prefill("cli-no-prefill-haiku-fenced"))

    def test_a_whole_object_does_not_parse_behind_a_prefill(self):
        # The brace the client puts back would open a second object.
        with self.assertRaises(schema.SchemaError):
            self.run_extract(doubles.recorded_without_prefill("cli-no-prefill-haiku"),
                             settings=PREFILLED)

    def test_the_same_recording_reads_fine_where_the_schema_is_enforced(self):
        # Nothing about the recording changed: the route it is replayed on did.
        result, _ = self.run_extract(doubles.recorded_without_prefill("cli-no-prefill-haiku"))
        self.assertEqual(len(result.claims), 3)


class DefectTest(ExtractTest):
    def test_a_span_that_is_not_verbatim_is_dropped_and_counted(self):
        answer = claims(("The unit test passed", "suite_passed", []),
                        ("the unit tests passed", "suite_passed", []),   # not in the report
                        ("I'll proceed with staging", "intent", []))
        result, _ = self.run_extract(doubles.reply(answer))
        self.assertEqual([c.span for c in result.claims],
                         ["The unit test passed", "I'll proceed with staging"])
        self.assertEqual(result.defects,
                         (schema.Defect("the unit tests passed", "not verbatim in the report"),))

    def test_a_span_a_tidy_up_would_rescue_is_still_a_defect(self):
        """Nothing is repaired: not punctuation, not a curly quote, not a space."""
        near_misses = ["The unit test passed,",
                       "I’ve completed the first three steps successfully",
                       "The  unit test passed",
                       " The unit test passed "]
        for span in near_misses:
            with self.subTest(span=span):
                result, _ = self.run_extract(doubles.reply(claims((span, "suite_passed", []))))
                self.assertEqual(result.claims, ())
                self.assertEqual([d.span for d in result.defects], [span])

    def test_an_empty_claim_list_is_a_normal_answer(self):
        result, _ = self.run_extract(doubles.reply('{"claims": []}'))
        self.assertEqual((result.claims, result.defects), ((), ()))


class SchemaFailureTest(ExtractTest):
    def test_a_malformed_answer_raises_rather_than_returning_what_it_can(self):
        cases = {
            "not JSON at all": "sorry, I cannot do that",
            "a type outside the vocabulary": claims(("The unit test passed",
                                                     "behaviour_checked", [])),
            "a missing field": '{"claims": [{"span": "The unit test passed",'
                               ' "type": "intent"}]}',
            "an extra field": '{"claims": [{"span": "The unit test passed", "type": "intent",'
                              ' "referents": [], "confidence": 0.9}]}',
            "claims that are not a list": '{"claims": {}}',
            "another key beside claims": '{"claims": [], "note": "done"}',
            "a span that is empty": claims(("", "intent", [])),
            "referents that are not strings": claims(("The unit test passed",
                                                      "suite_passed", [7])),
        }
        for label, answer in cases.items():
            with self.subTest(label), self.assertRaises(schema.SchemaError):
                self.run_extract(doubles.reply(answer))

    def test_an_answer_cut_off_at_the_token_ceiling_is_not_read(self):
        envelope = json.loads(doubles.reply(claims(*REAL_CLAIMS)).body)
        envelope["stop_reason"] = "max_tokens"
        with self.assertRaises(schema.SchemaError) as caught:
            self.run_extract(doubles.raw(json.dumps(envelope)))
        self.assertIn("cut off", str(caught.exception))

    def test_an_envelope_without_text_is_a_transport_failure(self):
        for label, answer in {"no content": doubles.raw('{"id": "x"}'),
                              "empty text": doubles.reply("   "),
                              "not JSON": doubles.raw("<html>502</html>")}.items():
            with self.subTest(label), self.assertRaises(extract.ExtractError):
                self.run_extract(answer)


class BudgetTest(ExtractTest):
    def test_a_report_over_the_limit_is_not_truncated_and_is_never_sent(self):
        transport = doubles.Transport()
        with self.assertRaises(extract.ExtractError) as caught:
            extract.extract("x" * 51, transport=transport,
                            settings=dataclasses.replace(SETTINGS, max_report_chars=50))
        self.assertIn("not truncated", str(caught.exception))
        self.assertEqual(transport.requests, [])

    def test_no_budget_left_means_no_call(self):
        transport = doubles.Transport()
        with self.assertRaises(extract.ExtractError):
            extract.extract(REPORT, transport=transport,
                            settings=dataclasses.replace(SETTINGS, timeout_s=0))
        self.assertEqual(transport.requests, [])

    def test_a_slow_call_is_cut_off_at_the_deadline(self):
        """A socket timeout bounds a read; the budget has to bound the call."""
        def crawling(request, timeout_s):
            time.sleep(5)          # never returns inside the budget below
            raise AssertionError("the deadline should have passed first")

        started = time.monotonic()
        with self.assertRaises(extract.ExtractError) as caught:
            extract.extract(REPORT, transport=crawling,
                            settings=dataclasses.replace(SETTINGS, timeout_s=0.3))
        self.assertIn("deadline", str(caught.exception))
        self.assertLess(time.monotonic() - started, 4)

    def test_the_transport_is_told_what_is_left_of_the_budget(self):
        _, transport = self.run_extract(doubles.reply(claims(*REAL_CLAIMS)))
        self.assertLessEqual(transport.timeouts[0], 10)
        self.assertGreater(transport.timeouts[0], 9)


class RetryTest(ExtractTest):
    def test_a_retryable_status_is_tried_once_more(self):
        result, transport = self.run_extract(doubles.raw("{}", status=429),
                                             doubles.reply(claims(*REAL_CLAIMS)))
        self.assertEqual(len(transport.requests), 2)
        self.assertEqual(len(result.claims), 3)

    def test_a_transport_failure_is_tried_once_more(self):
        result, transport = self.run_extract(extract.ExtractError("connection reset"),
                                             doubles.reply(claims(*REAL_CLAIMS)))
        self.assertEqual(len(transport.requests), 2)
        self.assertEqual(len(result.claims), 3)

    def test_a_status_that_will_not_change_is_not_retried(self):
        transport = doubles.Transport(doubles.raw('{"error": "bad request"}', status=400))
        with self.assertRaises(extract.ExtractError) as caught:
            extract.extract(REPORT, transport=transport, settings=SETTINGS)
        self.assertIn("400", str(caught.exception))
        self.assertEqual(len(transport.requests), 1)

    def test_a_second_failure_ends_it(self):
        transport = doubles.Transport(doubles.raw("{}", status=503),
                                      doubles.raw("{}", status=503))
        with self.assertRaises(extract.ExtractError):
            extract.extract(REPORT, transport=transport, settings=SETTINGS)
        self.assertEqual(len(transport.requests), 2)


class PromptTest(unittest.TestCase):
    def test_the_version_is_the_declared_one_plus_a_hash_of_the_prompt(self):
        prompt = extract.load_prompt()
        declared, _, digest = prompt.version.partition("+")
        self.assertEqual(declared, "extract-1")
        self.assertRegex(digest, r"^[0-9a-f]{8}$")

    def test_editing_the_prompt_changes_the_version_even_without_a_bump(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "extract.md"
            original = extract.PROMPT_PATH.read_text(encoding="utf-8")
            path.write_text(original + "\nOne more rule.\n", encoding="utf-8")
            self.assertNotEqual(extract.load_prompt(path).version,
                                extract.load_prompt().version)

    def test_the_prefill_ends_where_the_answer_begins(self):
        """The API refuses an assistant turn that ends in whitespace."""
        self.assertEqual(extract.PREFILL, "{")
        self.assertEqual(extract.PREFILL, extract.PREFILL.rstrip())

    def test_a_prompt_without_a_version_line_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "extract.md"
            path.write_text("You label claims.\n", encoding="utf-8")
            with self.assertRaises(extract.ExtractError):
                extract.load_prompt(path)


class DoubleTest(unittest.TestCase):
    """The double has to be honest about the shape it replays."""

    def test_a_continuation_is_only_made_from_a_whole_object(self):
        self.assertEqual(doubles.continuation('{"claims": []}'), '"claims": []}')
        for already_a_continuation in ['"claims": []}', "", "sorry"]:
            with self.subTest(text=already_a_continuation), self.assertRaises(AssertionError):
                doubles.continuation(already_a_continuation)


class TransportTest(unittest.TestCase):
    def test_the_real_transport_needs_a_key_and_makes_no_call_without_one(self):
        request = extract.build_request(REPORT, vocabulary=schema.CLAIM_TYPES,
                                        settings=SETTINGS, prompt=extract.load_prompt())
        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(extract.ExtractError) as caught:
                extract.https_transport(request, 1)
        self.assertIn("TEST_EXTRACTOR_KEY", str(caught.exception))
        self.assertNotIn("ANTHROPIC", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
