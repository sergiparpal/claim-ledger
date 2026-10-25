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


claims = doubles.claims

# The three claims of the recorded answer, as numbers into REPORT's sentences.
REAL_CLAIMS = ((1, "judgment", []), (2, "suite_passed", ["unit test"]), (3, "intent", []))
SENTENCES = ["I've completed the first three steps successfully.", "The unit test passed.",
             "I'll proceed with staging, committing, and pushing the changes."]


class ExtractTest(unittest.TestCase):
    def run_extract(self, *answers, report=REPORT, settings=SETTINGS, **overrides):
        transport = doubles.Transport(*answers)
        if overrides:
            settings = dataclasses.replace(settings, **overrides)
        result = extract.extract(report, settings=settings, transport=transport)
        return result, transport


class RequestTest(unittest.TestCase):
    """What the model is shown: the report cut into numbered sentences."""

    def test_the_report_goes_out_as_numbered_sentences(self):
        request = extract.build_request(REPORT, vocabulary=schema.CLAIM_TYPES,
                                        settings=SETTINGS, prompt=extract.load_prompt())
        self.assertEqual(request.body["messages"], [{"role": "user", "content": (
            "[1] I've completed the first three steps successfully.\n"
            "[2] The unit test passed.\n"
            "[3] I'll proceed with staging, committing, and pushing the changes.")}])

    def test_the_enforced_shape_asks_for_a_number_and_no_text(self):
        item = schema.json_schema()["properties"]["claims"]["items"]
        self.assertEqual(item["properties"]["sentence"], {"type": "integer"})
        self.assertNotIn("span", item["properties"])
        self.assertEqual(sorted(item["required"]), ["referents", "sentence", "type"])


class AnswerTest(ExtractTest):
    """An answer under the sentence contract, through the real client."""

    def test_each_span_is_the_sentence_its_number_names(self):
        result, transport = self.run_extract(doubles.answer(*REAL_CLAIMS))
        self.assertEqual([(c.type, c.span) for c in result.claims],
                         list(zip(("judgment", "suite_passed", "intent"), SENTENCES)))
        self.assertEqual(result.claims[1].referents, ("unit test",))
        self.assertEqual(result.defects, ())
        self.assertEqual(len(transport.requests), 1)

    def test_a_span_keeps_the_report_s_markup_since_nobody_copied_it(self):
        """The defects of 17 October, a dropped ** and a dropped », cannot recur."""
        report = "**La regla** va aquí. Dice «`judge`»."
        result, _ = self.run_extract(doubles.answer((1, "file_changed", []),
                                                    (2, "judgment", [])), report=report)
        self.assertEqual([c.span for c in result.claims],
                         ["**La regla** va aquí.", "Dice «`judge`»."])

    def test_several_claims_may_point_at_one_sentence(self):
        result, _ = self.run_extract(doubles.answer((2, "suite_passed", ["unit test"]),
                                                    (2, "judgment", [])))
        self.assertEqual([(c.span, c.type) for c in result.claims],
                         [(SENTENCES[1], "suite_passed"), (SENTENCES[1], "judgment")])

    def test_a_reasoning_block_is_passed_over(self):
        result, _ = self.run_extract(doubles.answer(*REAL_CLAIMS, thinking=True))
        self.assertEqual(len(result.claims), 3)

    def test_the_provenance_travels_with_every_claim(self):
        result, _ = self.run_extract(doubles.answer(*REAL_CLAIMS, provider="Morph"))
        version = extract.load_prompt().version
        self.assertTrue(version.startswith("extract-2+"), version)
        expected = schema.Provenance(prompt_version=version,
                                     model="deepseek/deepseek-v4.1-flash",
                                     base_url="https://openrouter.ai/api/v1",
                                     provider="Morph")
        self.assertEqual({c.provenance for c in result.claims}, {expected})
        self.assertEqual(result.provenance, expected)


class RecordingTest(ExtractTest):
    """What the client does with the real answers recorded before 18 October 2026.

    All of them answer with copied spans, so the client refuses them all; the
    recordings are kept, not edited into the shape now asked for."""

    def test_the_route_it_was_frozen_on_answered_with_copied_spans(self):
        with self.assertRaises(schema.SchemaError) as caught:
            self.run_extract(doubles.recorded("openrouter-deepseek-v4.1-flash"),
                             report=CAPTURED_REPORT)
        self.assertIn("'span'", str(caught.exception))

    def test_that_route_sent_no_reasoning_at_all(self):
        envelope = json.loads(doubles.recorded("openrouter-deepseek-v4.1-flash").body)
        self.assertEqual([b["type"] for b in envelope["content"]], ["text"])
        self.assertEqual(envelope["model"], "deepseek/deepseek-v4.1-flash")

    def test_a_real_reasoning_block_is_passed_over_before_the_answer_is_read(self):
        """glm's recording: refused for its spans, which means the thinking
        block in front of them was stepped over and the text was read."""
        envelope = json.loads(doubles.recorded("openrouter-glm-5.3-flash").body)
        self.assertEqual([b["type"] for b in envelope["content"]], ["thinking", "text"])
        with self.assertRaises(schema.SchemaError) as caught:
            self.run_extract(doubles.recorded("openrouter-glm-5.3-flash"),
                             report=CAPTURED_REPORT)
        self.assertIn("'span'", str(caught.exception))

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

    def test_where_the_schema_is_enforced_it_is_refused_for_its_spans(self):
        with self.assertRaises(schema.SchemaError) as caught:
            self.run_extract(doubles.recorded_without_prefill("cli-no-prefill-haiku"))
        self.assertIn("'span'", str(caught.exception))


class DefectTest(ExtractTest):
    def test_a_number_the_report_does_not_have_is_dropped_and_counted(self):
        answer = claims((2, "suite_passed", []), (4, "suite_passed", []),
                        (0, "intent", []), (-1, "intent", []))
        result, _ = self.run_extract(doubles.reply(answer))
        self.assertEqual([c.span for c in result.claims], [SENTENCES[1]])
        self.assertEqual(result.defects, tuple(
            schema.Defect(f"sentence {n}", "the report has 3 sentences") for n in (4, 0, -1)))

    def test_a_report_with_no_sentence_makes_every_number_a_defect(self):
        result, _ = self.run_extract(doubles.answer((1, "judgment", [])), report="```\n```")
        self.assertEqual(result.claims, ())
        self.assertEqual(result.defects,
                         (schema.Defect("sentence 1", "the report has 0 sentences"),))

    def test_an_empty_claim_list_is_a_normal_answer(self):
        result, _ = self.run_extract(doubles.reply('{"claims": []}'))
        self.assertEqual((result.claims, result.defects), ((), ()))


class SchemaFailureTest(ExtractTest):
    def test_a_malformed_answer_raises_rather_than_returning_what_it_can(self):
        def one(**fields):
            return json.dumps({"claims": [fields]})
        cases = {
            "not JSON at all": "sorry, I cannot do that",
            "a type outside the vocabulary": claims((2, "behaviour_checked", [])),
            "a missing field": one(sentence=2, type="intent"),
            "an extra field": one(sentence=2, type="intent", referents=[], confidence=0.9),
            "claims that are not a list": '{"claims": {}}',
            "another key beside claims": '{"claims": [], "note": "done"}',
            "a sentence given as text": one(sentence="2", type="intent", referents=[]),
            "a sentence that is a fraction": one(sentence=2.5, type="intent", referents=[]),
            "a sentence that is a boolean": one(sentence=True, type="intent", referents=[]),
            "a copied span where the number belongs": one(span="The unit test passed.",
                                                          type="suite_passed", referents=[]),
            "referents that are not strings": claims((2, "suite_passed", [7])),
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
        self.assertEqual(declared, "extract-2")
        self.assertRegex(digest, r"^[0-9a-f]{8}$")

    def test_a_candidate_prompt_declares_the_version_its_file_is_named_for(self):
        """A prompt measured beside the hook's carries its own version, not the hook's."""
        for path in sorted(extract.PROMPT_PATH.parent.glob("extract-*.md")):
            declared, _, digest = extract.load_prompt(path).version.partition("+")
            self.assertEqual(declared, path.stem)
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
