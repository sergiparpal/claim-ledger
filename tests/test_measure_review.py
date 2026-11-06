"""tools/measure_review.py: a review measured on stored answers, which can only drop.

What is tested is what would spoil the figure without a sign: a review sent
more than the report and an answer about it, a reply read as dropping a claim
it did not name, a claim left without a verdict counted as dropped, a failure
that stops the run instead of becoming its row, a row that holds text of the
report, and a score that is not the scorer's. No call leaves the machine: the
transport is a double.
"""

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from ledger import config, extract, sentences
from tests import doubles, test_annotate
from tests.test_extract import SETTINGS

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import measure_recall  # noqa: E402
import measure_review  # noqa: E402

PROMPT = extract.load_prompt(measure_review.PROMPT_PATH)
CUT = test_annotate.SENTENCES
CLAIMS = [measure_recall.Marked(frozenset({1}), "judgment"),
          measure_recall.Marked(frozenset({2}), "suite_passed"),
          measure_recall.Marked(frozenset({3}), "intent")]


def verdicts(*pairs):
    """A reply that gives these verdicts, as the route returns one under the schema."""
    return doubles.reply(json.dumps({"verdicts": [{"claim": name, "keep": keep}
                                                  for name, keep in pairs]}))


class RequestTest(unittest.TestCase):
    def test_the_review_is_sent_the_report_and_the_claims_and_nothing_else(self):
        body = measure_review.build_request(CUT, CLAIMS, settings=SETTINGS, prompt=PROMPT).body
        self.assertEqual(len(body["messages"]), 1)
        content = body["messages"][0]["content"]
        self.assertTrue(content.startswith(sentences.numbered(CUT)))
        self.assertIn("c2: [2] suite_passed | The unit test passed.", content)
        self.assertNotIn("evidence-only-marker", json.dumps(body))
        self.assertTrue(body["system"].startswith(PROMPT.text))

    def test_it_goes_to_the_extractors_route_pinned_and_held_to_the_schema(self):
        request = measure_review.build_request(CUT, CLAIMS, settings=SETTINGS, prompt=PROMPT)
        self.assertTrue(request.url.endswith(extract.API_PATH))
        self.assertEqual((request.body["model"], request.body["temperature"]),
                         (SETTINGS.model, 0))
        self.assertEqual(request.body["provider"],
                         {"order": [SETTINGS.provider], "allow_fallbacks": False,
                          "data_collection": "deny", "require_parameters": True})
        self.assertEqual(request.body["output_config"]["format"]["schema"],
                         measure_review.SCHEMA)


class VerdictsTest(unittest.TestCase):
    def test_a_reply_drops_only_the_claims_it_says_to_drop(self):
        reply = verdicts(("c1", True), ("c2", False), ("c3", True))
        self.assertEqual(measure_review.verdicts(reply.body, 3), ([2], 0))

    def test_a_claim_with_no_verdict_is_kept_and_counted(self):
        self.assertEqual(measure_review.verdicts(verdicts(("c2", False)).body, 3), ([2], 2))

    def test_the_first_verdict_on_a_claim_is_the_one_that_counts(self):
        reply = verdicts(("c1", True), ("c1", False))
        self.assertEqual(measure_review.verdicts(reply.body, 1), ([], 0))

    def test_a_verdict_on_a_claim_that_was_not_sent_makes_the_review_unusable(self):
        with self.assertRaises(measure_review.ReviewError):
            measure_review.verdicts(verdicts(("c4", False)).body, 3)

    def test_a_reply_that_is_not_verdicts_makes_the_review_unusable(self):
        for text in ('{"drop": [2]}', "not json",
                     '{"verdicts": [{"claim": "c1", "keep": "no"}]}'):
            with self.subTest(text=text), self.assertRaises(measure_review.ReviewError):
                measure_review.verdicts(doubles.reply(text).body, 3)


class RowTest(unittest.TestCase):
    def row(self, *answers):
        transport = doubles.Transport(*answers)
        made = measure_review.review_row("a-1", CUT, CLAIMS, settings=SETTINGS, prompt=PROMPT,
                                         number=1, transport=transport, deadline=5.0)
        return made, transport

    def test_a_row_names_what_was_dropped_and_holds_no_text_of_the_report(self):
        made, _ = self.row(verdicts(("c1", True), ("c2", False), ("c3", True)))
        self.assertEqual((made["outcome"], made["drop"], made["missing"], made["claims"]),
                         ("usable", [2], 0, 3))
        self.assertEqual(made["prompt"], PROMPT.version)
        for sentence in CUT:
            self.assertNotIn(sentence, json.dumps(made))

    def test_a_failure_becomes_the_row_after_the_clients_one_retry(self):
        made, transport = self.row(doubles.raw("busy", status=429),
                                   doubles.raw("busy", status=429))
        self.assertEqual(made["outcome"], "failed")
        self.assertEqual(len(transport.requests), 2)

    def test_a_reply_that_cannot_be_read_is_unusable_not_failed(self):
        made, _ = self.row(doubles.reply("not json"))
        self.assertEqual(made["outcome"], "unusable")


class TalliesTest(unittest.TestCase):
    REFERENCE = [measure_recall.Marked(frozenset({2}), "suite_passed")]

    def test_dropping_what_the_reference_does_not_make_costs_no_recall(self):
        before, after = measure_review.tallies(self.REFERENCE, CLAIMS, [1, 3])
        self.assertEqual((before.found, after.found), (1, 1))
        self.assertEqual((before.unmarked + before.retyped, after.unmarked + after.retyped),
                         (2, 0))

    def test_dropping_a_claim_the_reference_makes_costs_recall(self):
        before, after = measure_review.tallies(self.REFERENCE, CLAIMS, [2])
        self.assertEqual((before.found, after.found), (1, 0))


class RunTest(unittest.TestCase):
    """A run reviews what a stored pass answered on the corpus, and resumes."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / config.CONFIG_FILENAME).write_text(
            (REPO / config.CONFIG_FILENAME).read_text(encoding="utf-8"), encoding="utf-8")
        self.ids = [test_annotate.capture(self.root, number, text) for number, text
                    in enumerate((test_annotate.REPORT, "The parser is simpler now."), 1)]
        self.corpus = self.root / "annotations.jsonl"
        annotated = ((self.ids[0], [{"span": CUT[1], "type": "suite_passed"}]), (self.ids[1], []))
        self.corpus.write_text("".join(
            json.dumps({"report": report, "annotated": "2026-11-06", "by": "claude-fable-5-1",
                        "claims": claims}) + "\n" for report, claims in annotated),
            encoding="utf-8")
        route = {"model": "m", "provider": "p", "prompt": "extract-test+0", "timeout_s": 20}
        stored = ((self.ids[0], [[1, "judgment"], [2, "suite_passed"], [3, "intent"]], 3),
                  (self.ids[1], [[1, "judgment"]], 1))
        self.run_file = self.root / "run.jsonl"
        self.run_file.write_text("".join(
            json.dumps({"pass": 1, "report": report, "outcome": "usable", "answer": answer,
                        "sentences": count, "route": route}) + "\n"
            for report, answer, count in stored), encoding="utf-8")
        self.out = self.root / "reviews.jsonl"

    def tool(self, command, *answers):
        transport = doubles.Transport(*answers)
        printed = io.StringIO()
        extra = {"transport": transport, "pause": 0} if command == "run" else {}
        code = measure_review.main(["measure_review.py", command, "--run", str(self.run_file),
                                    "--pass", "1", "--root", str(self.root),
                                    "--corpus", str(self.corpus), str(self.out)],
                                   out=printed, **extra)
        return code, printed.getvalue(), transport

    def test_a_run_reviews_each_stored_answer_and_a_second_run_resumes(self):
        code, _, transport = self.tool("run", verdicts(("c1", False), ("c2", True), ("c3", False)),
                                       verdicts(("c1", True)))
        self.assertEqual(code, 0)
        self.assertEqual(len(transport.requests), 2)
        rows = [json.loads(line) for line in self.out.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([row["drop"] for row in rows], [[1, 3], []])
        _, _, transport = self.tool("run")
        self.assertEqual(transport.requests, [])

    def test_the_score_is_the_pass_before_and_after_the_review(self):
        self.tool("run", verdicts(("c1", False), ("c2", True), ("c3", False)),
                  verdicts(("c1", True)))
        code, printed, _ = self.tool("score")
        self.assertEqual(code, 0)
        self.assertIn("before the review: recall 1/1 = 1.000, spurious 3/4 = 0.750", printed)
        self.assertIn("after it: recall 1/1 = 1.000, spurious 1/2 = 0.500", printed)


if __name__ == "__main__":
    unittest.main()
