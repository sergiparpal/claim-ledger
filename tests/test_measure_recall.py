"""tools/measure_recall.py: a score that flatters nothing, and shows nothing early.

What is tested is what would make a figure read better than the answers it
counts, or show the person what the model said before they say it: a claim
found under another type or in another sentence, a span typed by hand that the
cut divides, a turn with no answer or a late one counted as clean, a candidate
judged by its best pass, a run whose answers were not kept scored as if they
were, a report cut otherwise than when it was asked, and a report the person
has not annotated shown beside the annotator's claims. No call is made.
"""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from ledger import sentences
from tests.test_annotate import REPORT, SENTENCES, capture

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import measure_recall  # noqa: E402

# A second report: a heading, a list and a closing line, cut into five sentences.
LISTED = ("## Done\n"
          "- Edited `src/parser.py` to handle empty lines.\n"
          "- Ran `make verify`. It passed.\n"
          "The parser is simpler now.\n")
PIECES = ["Done", "Edited `src/parser.py` to handle empty lines.", "Ran `make verify`.",
          "It passed.", "The parser is simpler now."]
ANNOTATOR = "claude-fable-5-1 via Claude Code 2.1.309"
ROUTE = {"model": "mistralai/mistral-medium-3.1", "provider": "mistral/zdr",
         "prompt": "extract-2+4e6f09ab", "timeout_s": 12}
Marked = measure_recall.Marked


def at(number, kind):
    return Marked(frozenset({number}), kind)


def asked(number, report, answer=(), *, outcome="usable", wall=3.0, cut=None, defects=0,
          usable=None):
    """A row of measure_route.py run --corpus, as it would have written it."""
    row = {"pass": number, "report": report, "route": ROUTE, "chars": 100, "wall": wall,
           "outcome": outcome}
    if outcome == "usable":
        row.update(claims=len(answer), defects=defects, digest="0" * 12, sentences=cut,
                   answer=[list(item) for item in answer])
        if usable is not None:
            row["usable"] = usable
    return row


class MeasureTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.project = self.tmp / "project"
        self.project.mkdir()
        self.short = capture(self.project, 1, REPORT)
        self.listed = capture(self.project, 2, LISTED)
        self.corpus = self.tmp / "annotations.jsonl"
        self.anchor = self.tmp / "anchor.jsonl"
        self.write(self.corpus, ANNOTATOR, {
            self.short: [(SENTENCES[0], "judgment"), (SENTENCES[1], "suite_passed"),
                         (SENTENCES[2], "intent")],
            self.listed: [(PIECES[1], "file_changed"), (PIECES[2], "command_run"),
                          (PIECES[3], "suite_passed"), (PIECES[4], "judgment")]})

    def write(self, path, by, annotations):
        path.write_text("".join(
            json.dumps({"report": report, "annotated": "2026-10-24", "by": by,
                        "claims": [{"span": span, "type": kind} for span, kind in claims]})
            + "\n" for report, claims in annotations.items()), encoding="utf-8")

    def by_hand(self):
        """The person typed the first sentence as a command and left the third unmarked."""
        self.write(self.anchor, "SP", {self.short: [(SENTENCES[0], "command_run"),
                                                    (SENTENCES[1], "suite_passed")]})

    def tool(self, command, *options):
        out, err = io.StringIO(), io.StringIO()
        argv = ["measure_recall.py", command, "--root", str(self.project), "--anchor",
                str(self.anchor), "--corpus", str(self.corpus), *options]
        with contextlib.redirect_stderr(err):
            code = measure_recall.main(argv, out=out)
        return code, out.getvalue(), err.getvalue()


class HoldingTest(unittest.TestCase):
    def test_a_whole_sentence_is_held_by_itself(self):
        self.assertEqual(measure_recall.holding(SENTENCES[1], REPORT, SENTENCES), {2})

    def test_part_of_a_sentence_is_held_by_that_sentence(self):
        self.assertEqual(measure_recall.holding("unit test", REPORT, SENTENCES), {2})

    def test_a_sentence_said_twice_is_held_by_both(self):
        text = "Done. The tests pass. Done."
        self.assertEqual(measure_recall.holding("Done.", text, sentences.split(text)), {1, 3})

    def test_a_span_typed_across_a_cut_is_held_by_the_sentences_on_both_sides(self):
        span = "successfully. The unit test"
        self.assertEqual(measure_recall.holding(span, REPORT, SENTENCES), {1, 2})

    def test_a_span_the_report_does_not_hold_is_held_by_none(self):
        self.assertEqual(measure_recall.holding("the tests pass", REPORT, SENTENCES), set())


class ScoreTest(unittest.TestCase):
    def test_a_claim_is_found_by_its_sentence_and_its_type(self):
        tally, missed = measure_recall.score([at(2, "suite_passed")], [at(2, "suite_passed")])
        self.assertEqual((tally.found, tally.checkable, tally.spurious, missed), (1, 1, 0, []))

    def test_the_sentence_under_another_type_is_a_miss_and_spurious(self):
        reference = [at(2, "suite_passed")]
        tally, missed = measure_recall.score(reference, [at(2, "judgment")])
        self.assertEqual((tally.found, missed), (0, reference))
        self.assertEqual((tally.unmarked, tally.retyped), (0, 1))

    def test_the_type_in_another_sentence_is_a_miss_and_spurious(self):
        tally, _ = measure_recall.score([at(2, "suite_passed")], [at(3, "suite_passed")])
        self.assertEqual((tally.found, tally.unmarked, tally.retyped), (0, 1, 0))

    def test_recall_counts_checkable_claims_and_spurious_counts_every_type(self):
        tally, _ = measure_recall.score([at(1, "judgment"), at(2, "suite_passed")],
                                        [at(1, "judgment"), at(2, "suite_passed"),
                                         at(3, "intent")])
        self.assertEqual((tally.checkable, tally.found, tally.extracted), (1, 1, 3))
        self.assertAlmostEqual(tally.spurious, 1 / 3)

    def test_an_empty_answer_misses_everything_and_has_no_spurious_share(self):
        tally, missed = measure_recall.score([at(2, "suite_passed"), at(3, "file_changed")], [])
        self.assertEqual((tally.recall, len(missed), tally.spurious), (0, 2, None))

    def test_a_claim_held_by_two_sentences_is_found_in_either(self):
        held = Marked(frozenset({1, 2}), "suite_passed")
        tally, _ = measure_recall.score([held], [at(2, "suite_passed")])
        self.assertEqual(tally.found, 1)


class AgreementTest(MeasureTestCase):
    def setUp(self):
        super().setUp()
        self.by_hand()

    def test_each_side_is_measured_against_the_other(self):
        code, out, _ = self.tool("agreement")
        self.assertEqual(code, 0)
        self.assertIn("the annotator found 1 of the person's 2 checkable claims (0.50)", out)
        self.assertIn("the person made 1 of the annotator's 1 checkable claims (1.00)", out)
        self.assertIn("of the annotator's 3 claims of every type, 2 (0.67) are not the "
                      "person's: 1 in sentences the person left unmarked, 1 in sentences the "
                      "person typed otherwise", out)

    def test_every_sentence_typed_differently_is_named_and_shown_only_when_asked(self):
        _, out, _ = self.tool("agreement")
        self.assertIn("2 sentences typed differently:", out)
        self.assertIn(f"{self.short} [1] by hand command_run; annotator judgment", out)
        self.assertIn(f"{self.short} [3] by hand none; annotator intent", out)
        self.assertNotIn(f"{self.short} [2]", out)
        self.assertNotIn(SENTENCES[0], out)
        _, out, _ = self.tool("agreement", "--spans")
        self.assertIn(f"      {SENTENCES[0]}", out)

    def test_nothing_is_shown_of_a_report_the_person_has_not_annotated(self):
        for options in ((), ("--spans",)):
            _, out, err = self.tool("agreement", *options)
            self.assertNotIn(self.listed, out + err)
            for piece in PIECES[1:]:
                self.assertNotIn(piece, out + err)

    def test_an_anchor_with_nothing_in_it_yet_measures_nothing(self):
        self.anchor.unlink()
        code, out, _ = self.tool("agreement")
        self.assertEqual(code, 1)
        self.assertIn("holds no report annotated by hand yet", out)


class RecallTest(MeasureTestCase):
    def rows(self):
        short, listed = self.short, self.listed
        return [
            {"pass": 0, "report": "fixed-442", "route": ROUTE, "wall": 1.0,
             "outcome": "usable", "sentences": 6, "answer": [[1, "judgment"]]},
            asked(1, short, [(2, "suite_passed"), (1, "judgment")], cut=3,
                  usable={"suite_passed": [1, 1]}),
            asked(1, listed, [(2, "file_changed"), (3, "command_run"), (4, "suite_passed"),
                              (5, "judgment")], cut=5,
                  usable={"file_changed": [1, 1], "command_run": [1, 1],
                          "suite_passed": [1, 0]}),
            asked(2, short, [(2, "judgment")], cut=3),
            asked(2, listed, outcome="over_deadline", wall=150.0),
            asked(3, short, [(2, "suite_passed")], cut=3, wall=20.0),
            asked(3, listed, [(2, "file_changed"), (3, "command_run"), (4, "suite_passed"),
                              (1, "command_run")], cut=5, defects=1),
        ]

    def run_file(self, rows):
        path = self.tmp / "medium.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        return path

    def recall(self, rows, *options):
        return self.tool("recall", *options, str(self.run_file(rows)))

    def test_each_pass_is_scored_on_its_own(self):
        code, out, _ = self.recall(self.rows())
        self.assertEqual(code, 0)
        self.assertIn("pass 1  recall 1.00: 4 of 4 checkable claims found, in 2 answers, "
                      "0 of them empty", out)
        self.assertIn("referents the join could match: 3 of 4 checkable claims (75%)", out)
        self.assertIn("pass 2  recall 0.00: 0 of 1 checkable claims found, in 1 answers", out)
        self.assertIn("spurious 1.00: 1 of 1 claims extracted, 0 in unmarked sentences, "
                      "1 typed otherwise", out)
        self.assertIn("UNKNOWN 1 of 2 turns (50%): 1 without an answer, 0 after 12s", out)

    def test_a_late_answer_is_scored_and_its_turn_still_counted_unknown(self):
        _, out, _ = self.recall(self.rows())
        self.assertIn("pass 3  recall 1.00: 4 of 4 checkable claims found, in 2 answers", out)
        self.assertIn("UNKNOWN 1 of 2 turns (50%): 0 without an answer, 1 after 12s; "
                      "1 defects", out)
        self.assertIn("spurious 0.20: 1 of 5 claims extracted, 1 in unmarked sentences, "
                      "0 typed otherwise", out)

    def test_a_candidate_is_judged_by_its_worst_pass_against_the_declared_threshold(self):
        _, out, _ = self.recall(self.rows())
        self.assertIn("worst pass: recall 0.00, spurious 1.00, UNKNOWN 50%, 1 defects", out)
        self.assertIn("does not clear the phase-1 threshold: the corpus holds 2 reports, "
                      "under 50; recall 0.00 is under 0.90; spurious 1.00 is over 0.10; "
                      "1 sentence numbers named no sentence", out)

    def test_fewer_passes_than_spec_asks_for_fall_short(self):
        _, out, _ = self.recall(self.rows()[:3])
        self.assertIn("1 of the 3 passes SPEC asks for", out)

    def test_a_claim_one_pass_missed_is_listed_with_that_pass(self):
        _, out, _ = self.recall(self.rows())
        self.assertIn("1 checkable claims missed in at least one pass", out)
        self.assertIn(f"{self.short} [2] suite_passed: missed in pass 2", out)
        self.assertNotIn(f"{self.listed} [", out)       # unanswered in pass 2, not missed
        self.assertNotIn(SENTENCES[1], out)
        _, out, _ = self.recall(self.rows(), "--spans")
        self.assertIn(f"      {SENTENCES[1]}", out)

    def test_the_anchors_agreement_goes_beside_every_figure(self):
        _, out, _ = self.recall(self.rows())
        self.assertIn("has not been checked against a person", out)
        self.by_hand()
        _, out, _ = self.recall(self.rows())
        self.assertIn("anchor: 1 reports by SP", out)
        self.assertIn("the annotator found 1 of the person's 2 checkable claims (0.50), and "
                      "the person made 1 of the annotator's 1 (1.00)", out)

    def test_the_corpus_is_named_by_what_it_holds(self):
        _, out, _ = self.recall(self.rows())
        self.assertIn(f"2 reports, sha256 {measure_recall.digest(self.corpus)}, by {ANNOTATOR}",
                      out)

    def test_a_run_whose_answers_were_not_kept_is_refused(self):
        rows = self.rows()
        for row in rows:
            row.pop("answer", None)
        code, out, err = self.recall(rows)
        self.assertEqual((code, out), (2, ""))
        self.assertIn("make the run with --corpus", err)

    def test_a_file_of_two_routes_is_refused(self):
        rows = self.rows()
        rows[-1]["route"] = dict(ROUTE, model="mistralai/devstral-2512")
        code, _, err = self.recall(rows)
        self.assertEqual(code, 2)
        self.assertIn("more than one route", err)

    def test_a_report_cut_otherwise_than_when_it_was_asked_is_refused(self):
        rows = self.rows()
        rows[1]["sentences"] = 4
        code, _, err = self.recall(rows)
        self.assertEqual(code, 2)
        self.assertIn("is cut into 3 sentences now, and was cut into 4", err)

    def test_a_pass_that_asks_twice_about_one_report_is_refused(self):
        rows = self.rows() + [asked(1, self.short, [(2, "suite_passed")], cut=3)]
        code, _, err = self.recall(rows)
        self.assertEqual(code, 2)
        self.assertIn("twice", err)

    def test_a_corpus_claim_in_none_of_its_sentences_is_refused(self):
        self.write(self.corpus, ANNOTATOR, {self.short: [("the tests pass", "suite_passed")]})
        code, _, err = self.recall(self.rows())
        self.assertEqual(code, 2)
        self.assertIn("in none of its sentences", err)


if __name__ == "__main__":
    unittest.main()
