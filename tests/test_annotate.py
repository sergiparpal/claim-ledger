"""tools/annotate.py: the corpus is annotated by a person, against the report alone.

What is tested is what would quietly spoil the measurement the corpus exists
for: a span that is not in the report, a report shown beside the extractor's
answer or the turn's evidence, a half-annotated report saved as if finished, a
corpus line rewritten, and an append onto a file that cannot take one. The
prompts are driven by a script of answers; nothing here waits for a person.
"""

import contextlib
import io
import json
import re
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from ledger import calibration, evidence, schema, turn

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import annotate  # noqa: E402

TODAY = date(2026, 10, 2)  # not today: a run that reads the clock must show
NOW = datetime(2026, 10, 5, 12, 0, 0, tzinfo=timezone.utc)
# The clock --older-than is measured against. Not now either: a run that
# reads the real clock would find every report here old enough, and must show.
CLOCK = datetime(2026, 9, 21, 12, 0, 0, tzinfo=timezone.utc)
SESSION = "0f8fad5b-d9cb-469f-a165-70867728950e"
REPORT = ("I've completed the first three steps successfully. The unit test passed. "
          "I'll proceed with staging, committing, and pushing the changes.")
SENTENCES = ["I've completed the first three steps successfully.",
             "The unit test passed.",
             "I'll proceed with staging, committing, and pushing the changes."]
# What the turn ran, as the capture records it. The annotator never sees it.
EVIDENCE = ('{"v": 2, "tool": "Bash", "command": "pytest -q --evidence-only-marker", '
            '"outcome": "ok"}')


class Script:
    """Answers to the prompts, in order. Running out is the end of input."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        if not self.answers:
            raise EOFError
        return self.answers.pop(0)


def capture(root, number, text, session=SESSION, at=NOW):
    """A report captured by the Stop handler's own writer, evidence slice and all."""
    entry = evidence.Entry(position=number, record=json.loads(EVIDENCE), raw=EVIDENCE)
    turn.capture(root, {"last_assistant_message": text}, session, number, at, [entry], None)
    return f"{session}-{number}"


class AnnotateTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        self.project = self.tmp / "project"
        self.project.mkdir()
        self.corpus = self.tmp / "corpus" / "annotations.jsonl"

    def run_tool(self, *answers, projects=None, options=(), now=CLOCK):
        script = Script(*answers)
        out, err = io.StringIO(), io.StringIO()
        argv = ["annotate.py", "--by", "SP", "--corpus", str(self.corpus), *options]
        argv += [str(project) for project in (projects or [self.project])]
        with contextlib.redirect_stderr(err):
            code = annotate.main(argv, ask=script, out=out, today=lambda: TODAY,
                                 now=lambda: now)
        return code, out.getvalue(), err.getvalue(), script

    def lines(self):
        if not self.corpus.exists():
            return []
        return [json.loads(line) for line in self.corpus.read_text(encoding="utf-8").splitlines()]


class PiecesTest(unittest.TestCase):
    SAMPLES = [
        REPORT,
        "## Resumen\n\n- Edité `src/parser.py`.\n- Los tests pasan: 12 de 12.\n\n"
        "¿Quieres que lo suba?",
        "1. Ran pytest -q\r\n2) Fixed the import.\r\n> Quoted. Line\n```bash\npytest -q\n"
        "```\n---\n| a | b |\n|---|---|",
        "Version 3.12 is required. I edited README.md and ran it… It passed!",
    ]

    def test_every_piece_is_a_verbatim_slice_in_report_order(self):
        for text in self.SAMPLES:
            with self.subTest(text=text[:30]):
                position = 0
                for piece in annotate.pieces(text):
                    found = text.find(piece, position)
                    self.assertNotEqual(found, -1, piece)
                    position = found + len(piece)

    def test_a_sentence_ends_at_a_stop_followed_by_a_space(self):
        self.assertEqual(annotate.pieces(REPORT), SENTENCES)
        self.assertEqual(annotate.pieces("I edited README.md for 3.12. Done… It passed!"),
                         ["I edited README.md for 3.12.", "Done…", "It passed!"])

    def test_layout_opening_a_line_is_left_out_of_the_slice(self):
        self.assertEqual(
            annotate.pieces("## Summary\n- Edited a.py\n1. Ran it\n2) Fixed b\n> Quoted\n"
                            "**Bold** stays\n1.5 seconds stays"),
            ["Summary", "Edited a.py", "Ran it", "Fixed b", "Quoted", "**Bold** stays",
             "1.5 seconds stays"])

    def test_fences_and_rules_are_not_offered(self):
        self.assertEqual(annotate.pieces("```bash\npytest -q\n```\n---\n|---|---|\n"),
                         ["pytest -q"])

    def test_an_empty_report_has_nothing_to_ask(self):
        self.assertEqual(annotate.pieces(""), [])
        self.assertEqual(annotate.pieces("\n  \n"), [])


class VocabularyTest(unittest.TestCase):
    def test_one_key_per_type_in_the_frozen_order(self):
        self.assertEqual(list(annotate.KEYS), ["1", "2", "3", "4", "5"])
        self.assertEqual(list(annotate.KEYS.values()), list(schema.CLAIM_TYPES))

    def test_the_annotation_guide_names_the_keys_the_tool_reads(self):
        """docs/ANNOTATING.md is what an annotator reads; a key that means one
        type there and another here would put a wrong type in the corpus."""
        guide = (REPO / "docs" / "ANNOTATING.md").read_text(encoding="utf-8")
        rows = re.findall(r"^\| `(\d)` \| `([a-z_]+)` \|", guide, re.MULTILINE)
        self.assertEqual(rows, list(annotate.KEYS.items()))

    def test_the_default_corpus_is_the_file_the_documents_name(self):
        self.assertEqual(annotate.CORPUS, REPO / "corpus" / "annotations.jsonl")
        for document in ("docs/SPEC.md", "docs/OPERATING.md"):
            with self.subTest(document=document):
                self.assertIn("corpus/annotations.jsonl",
                              (REPO / document).read_text(encoding="utf-8"))


class CorpusReadTest(AnnotateTestCase):
    def write(self, text):
        self.corpus.parent.mkdir(parents=True, exist_ok=True)
        self.corpus.write_bytes(text.encode("utf-8"))

    def test_no_corpus_yet_is_an_empty_one(self):
        self.assertEqual(annotate.annotated(self.corpus), set())

    def test_the_report_ids_it_holds(self):
        self.write('{"report": "a-1", "claims": []}\n{"report": "a-2", "claims": []}\n')
        self.assertEqual(annotate.annotated(self.corpus), {"a-1", "a-2"})

    def test_a_last_line_without_a_line_end_is_refused(self):
        """The next append would be written onto it, and both lines would be lost."""
        self.write('{"report": "a-1", "claims": []}')
        with self.assertRaisesRegex(annotate.AnnotateError, "no line end"):
            annotate.annotated(self.corpus)

    def test_a_line_that_is_not_json_is_refused_by_number(self):
        self.write('{"report": "a-1", "claims": []}\nnot json\n')
        with self.assertRaisesRegex(annotate.AnnotateError, r"annotations\.jsonl:2: not a JSON"):
            annotate.annotated(self.corpus)

    def test_a_blank_line_is_refused_rather_than_skipped(self):
        self.write('{"report": "a-1", "claims": []}\n\n{"report": "a-2", "claims": []}\n')
        with self.assertRaisesRegex(annotate.AnnotateError, ":2:"):
            annotate.annotated(self.corpus)

    def test_a_line_that_names_no_report_is_refused(self):
        for line in ('{"claims": []}', '["a-1"]', '{"report": ""}', '{"report": 7}'):
            with self.subTest(line=line):
                self.write(line + "\n")
                with self.assertRaisesRegex(annotate.AnnotateError, "names no report"):
                    annotate.annotated(self.corpus)

    def test_a_report_annotated_twice_is_refused(self):
        self.write('{"report": "a-1", "claims": []}\n{"report": "a-1", "claims": []}\n')
        with self.assertRaisesRegex(annotate.AnnotateError, ":2: a-1 is already annotated "
                                                            "at line 1"):
            annotate.annotated(self.corpus)


class FindReportsTest(AnnotateTestCase):
    def test_turns_come_in_number_order_not_text_order(self):
        for number in (10, 2, 1):
            capture(self.project, number, REPORT)
        reports, unreadable = annotate.find_reports([self.project])
        self.assertEqual([report.report_id for report in reports],
                         [f"{SESSION}-1", f"{SESSION}-2", f"{SESSION}-10"])
        self.assertEqual(unreadable, [])

    def test_the_text_is_the_report_exactly_and_nothing_else_of_the_file(self):
        capture(self.project, 1, REPORT)
        (report,), _ = annotate.find_reports([self.project])
        self.assertEqual(report.text, REPORT)

    def test_a_project_without_captured_reports_is_named(self):
        with self.assertRaisesRegex(annotate.AnnotateError, "project: no captured reports"):
            annotate.find_reports([self.project])

    def test_a_capture_that_does_not_read_is_listed_and_the_rest_are_kept(self):
        capture(self.project, 1, REPORT)
        broken = self.project / evidence.STATE_DIR / turn.REPORTS / f"{SESSION}-2.md"
        broken.write_text("not a captured report\n", encoding="utf-8")
        reports, unreadable = annotate.find_reports([self.project])
        self.assertEqual([report.report_id for report in reports], [f"{SESSION}-1"])
        self.assertEqual(len(unreadable), 1)
        self.assertIn(str(broken), unreadable[0])

    def test_the_same_report_in_two_projects_is_refused(self):
        other = self.tmp / "other"
        capture(self.project, 1, REPORT)
        capture(other, 1, REPORT)
        with self.assertRaisesRegex(annotate.AnnotateError, "captured twice"):
            annotate.find_reports([self.project, other])


class SessionTest(AnnotateTestCase):
    def test_a_finished_report_is_one_line_in_the_spec_shape(self):
        report = capture(self.project, 1, REPORT)
        code, _, _, script = self.run_tool("4", "2", "5", "")
        self.assertEqual(code, 0)
        self.assertEqual(script.answers, [])
        raw = self.corpus.read_text(encoding="utf-8")
        self.assertEqual(raw.count("\n"), 1)
        self.assertTrue(raw.endswith("\n"))
        written = json.loads(raw)
        self.assertEqual(list(written), ["report", "annotated", "by", "claims"])
        self.assertEqual(written, {
            "report": report, "annotated": "2026-10-02", "by": "SP",
            "claims": [{"span": SENTENCES[0], "type": "judgment"},
                       {"span": SENTENCES[1], "type": "suite_passed"},
                       {"span": SENTENCES[2], "type": "intent"}]})

    def test_the_annotator_sees_the_report_and_nothing_else(self):
        """Not the evidence the capture holds, and not the extractor's claims."""
        report = capture(self.project, 1, REPORT)
        calibration_log = calibration.claims_log(self.project)
        calibration_log.write_text(json.dumps({"claim_id": f"{report}-0",
                                               "span": "a span only the extractor returned"})
                                   + "\n", encoding="utf-8")
        _, out, err, script = self.run_tool("", "", "", "")
        self.assertIn(REPORT, out)
        shown = out + err + "".join(script.prompts)
        self.assertNotIn("evidence-only-marker", shown)
        self.assertNotIn("only the extractor returned", shown)

    def test_enter_marks_a_sentence_that_claims_nothing(self):
        capture(self.project, 1, REPORT)
        self.run_tool("", "", "", "")
        self.assertEqual(self.lines()[0]["claims"], [])

    def test_an_empty_report_can_be_saved_as_claiming_nothing(self):
        capture(self.project, 1, "")
        _, out, _, script = self.run_tool("")
        self.assertIn("(the report is empty)", out)
        self.assertEqual(script.answers, [])
        self.assertEqual(self.lines()[0]["claims"], [])

    def test_a_key_that_is_not_one_is_asked_again(self):
        capture(self.project, 1, "Ran it.")
        _, out, _, _ = self.run_tool("7", "x", "1", "")
        self.assertIn("'7' is not a key", out)
        self.assertEqual(self.lines()[0]["claims"], [{"span": "Ran it.", "type": "command_run"}])

    def test_keys_are_read_without_case_or_surrounding_spaces(self):
        capture(self.project, 1, "Ran it.")
        self.run_tool(" 3 ", " ")
        self.assertEqual(self.lines()[0]["claims"], [{"span": "Ran it.", "type": "file_changed"}])

    def test_spans_by_hand_must_be_in_the_report_word_for_word(self):
        capture(self.project, 1, "I updated src/parser.py and the tests pass.")
        _, out, _, script = self.run_tool(
            "s", "I updated src/parser.py", "3",
            "the test pass",                      # not in the report: asked again
            "the tests pass", "9", "2",           # 9 is not a type: asked again
            "", "")
        self.assertEqual(script.answers, [])
        self.assertIn("not in the report word for word", out)
        self.assertIn("'9' is not a type", out)
        self.assertEqual(self.lines()[0]["claims"],
                         [{"span": "I updated src/parser.py", "type": "file_changed"},
                          {"span": "the tests pass", "type": "suite_passed"}])

    def test_a_span_by_hand_may_cross_a_cut_in_the_wrong_place(self):
        capture(self.project, 1, "Ran it, e.g. the suite. Done.")
        self.assertEqual(annotate.pieces("Ran it, e.g. the suite. Done."),
                         ["Ran it, e.g.", "the suite.", "Done."])
        _, _, _, script = self.run_tool("s", "Ran it, e.g. the suite.", "1", "",  # first piece
                                        "", "",                                 # the other two
                                        "")                                     # save
        self.assertEqual(script.answers, [])
        self.assertEqual(self.lines()[0]["claims"],
                         [{"span": "Ran it, e.g. the suite.", "type": "command_run"}])

    def test_a_typed_span_loses_only_its_surrounding_spaces(self):
        capture(self.project, 1, "I updated src/parser.py and the tests pass.")
        self.run_tool("s", "  the tests pass  ", "2", "", "")
        self.assertEqual(self.lines()[0]["claims"],
                         [{"span": "the tests pass", "type": "suite_passed"}])

    def test_redo_starts_the_report_again_from_nothing(self):
        capture(self.project, 1, "Ran it.")
        _, _, _, script = self.run_tool("1", "r", "4", "")
        self.assertEqual(script.answers, [])
        self.assertEqual(self.lines()[0]["claims"], [{"span": "Ran it.", "type": "judgment"}])

    def test_quit_saves_nothing_of_the_report_in_hand(self):
        first = capture(self.project, 1, "Ran it.")
        second = capture(self.project, 2, "Ran it again.")
        code, out, _, _ = self.run_tool("1", "", "1", "q")
        self.assertEqual(code, 0)
        self.assertEqual([line["report"] for line in self.lines()], [first])
        self.assertIn(f"nothing of {second}", out)

    def test_quit_at_the_confirmation_saves_nothing_of_the_report(self):
        capture(self.project, 1, "Ran it.")
        code, _, _, _ = self.run_tool("1", "q")
        self.assertEqual(code, 0)
        self.assertFalse(self.corpus.exists())

    def test_running_out_of_input_is_a_quit(self):
        capture(self.project, 1, "Ran it.")
        code, out, _, _ = self.run_tool("1")
        self.assertEqual(code, 0)
        self.assertIn("stopped", out)
        self.assertFalse(self.corpus.exists())

    def test_a_skipped_report_comes_back_next_run(self):
        first = capture(self.project, 1, "Ran it.")
        second = capture(self.project, 2, "Ran it again.")
        self.run_tool("n", "1", "")
        self.assertEqual([line["report"] for line in self.lines()], [second])
        self.run_tool("4", "")
        self.assertEqual([line["report"] for line in self.lines()], [second, first])

    def test_a_second_run_takes_up_after_the_saved_reports(self):
        first = capture(self.project, 1, "Ran it.")
        second = capture(self.project, 2, "Ran it again.")
        self.run_tool("1", "", "q")
        _, out, _, _ = self.run_tool("4", "")
        self.assertIn("1 of 2 captured reports still to do", out)
        self.assertNotIn(first, out)
        self.assertEqual([line["report"] for line in self.lines()], [first, second])

    def test_lines_already_written_are_never_rewritten(self):
        existing = ('{"report": "x-1",   "annotated": "2026-10-01", "by": "SP", '
                    '"claims": [{"span": "Probé el parser.", "type": "command_run"}]}\n')
        self.corpus.parent.mkdir(parents=True)
        self.corpus.write_bytes(existing.encode("utf-8"))
        capture(self.project, 1, "Ran it.")
        self.run_tool("1", "")
        raw = self.corpus.read_bytes()
        self.assertTrue(raw.startswith(existing.encode("utf-8")))
        self.assertEqual(len(self.lines()), 2)

    def test_a_corpus_it_cannot_append_to_stops_the_run_before_anything_is_asked(self):
        broken = b'{"report": "x-1", "claims": []}'
        self.corpus.parent.mkdir(parents=True)
        self.corpus.write_bytes(broken)
        capture(self.project, 1, "Ran it.")
        code, _, err, script = self.run_tool("1", "")
        self.assertEqual(code, 2)
        self.assertEqual(script.prompts, [])
        self.assertIn("no line end", err)
        self.assertEqual(self.corpus.read_bytes(), broken)

    def test_a_missing_project_stops_the_run_before_anything_is_asked(self):
        code, _, err, script = self.run_tool("1", "", projects=[self.tmp / "elsewhere"])
        self.assertEqual(code, 2)
        self.assertEqual(script.prompts, [])
        self.assertIn("no captured reports", err)

    def test_an_unreadable_capture_is_named_and_the_rest_are_asked(self):
        capture(self.project, 1, "Ran it.")
        broken = self.project / evidence.STATE_DIR / turn.REPORTS / f"{SESSION}-2.md"
        broken.write_text("not a captured report\n", encoding="utf-8")
        code, _, err, _ = self.run_tool("1", "")
        self.assertEqual(code, 0)
        self.assertIn(str(broken), err)
        self.assertEqual([line["report"] for line in self.lines()], [f"{SESSION}-1"])

    def test_spans_are_written_readable_not_escaped(self):
        capture(self.project, 1, "Edité el parser y los tests pasan.")
        self.run_tool("3", "")
        raw = self.corpus.read_bytes()
        self.assertIn("Edité".encode("utf-8"), raw)
        self.assertNotIn(b"\\u00e9", raw)

    def test_initials_are_required_and_are_not_padded(self):
        capture(self.project, 1, "Ran it.")
        for by in (None, "", " SP"):
            with self.subTest(by=by):
                argv = ["annotate.py", "--corpus", str(self.corpus), str(self.project)]
                if by is not None:
                    argv[1:1] = ["--by", by]
                script = Script("1", "")
                with self.assertRaises(SystemExit) as caught, \
                        contextlib.redirect_stderr(io.StringIO()):
                    annotate.main(argv, ask=script, out=io.StringIO(), today=lambda: TODAY)
                self.assertEqual(caught.exception.code, 2)
                self.assertEqual(script.prompts, [])
        self.assertFalse(self.corpus.exists())


class OnlyTest(AnnotateTestCase):
    """--only: the anchor of a model-annotated corpus is a few reports chosen by
    id, and no others are asked about."""

    def test_only_the_named_reports_are_asked(self):
        first, second, third = (capture(self.project, n, f"Ran it {n} times.") for n in (1, 2, 3))
        code, out, _, script = self.run_tool("1", "", "2", "",
                                             options=("--only", third, "--only", first))
        self.assertEqual((code, script.answers), (0, []))
        self.assertEqual([line["report"] for line in self.lines()], [first, third])
        self.assertNotIn(second, out)

    def test_a_named_report_that_is_not_to_do_is_named(self):
        done = capture(self.project, 1, "Ran it.")
        self.run_tool("1", "")
        code, _, err, script = self.run_tool(options=("--only", done, "--only", "nope-1"))
        self.assertEqual((code, script.prompts), (0, []))
        self.assertIn(f"{done} is not a report still to do", err)
        self.assertIn("nope-1 is not a report still to do", err)


class AgeTest(AnnotateTestCase):
    """--older-than: a report annotated with its turn fresh in mind is annotated
    against the line that ended the turn, which lists some of the extractor's
    claims."""

    def options(self, written):
        return ("--older-than", written)

    def test_an_age_is_whole_hours_or_whole_days(self):
        self.assertEqual(annotate.age("12h"), annotate.Age("12h", timedelta(hours=12)))
        self.assertEqual(annotate.age("2d"), annotate.Age("2d", timedelta(days=2)))

    def test_only_reports_captured_before_the_cutoff_are_asked(self):
        old = capture(self.project, 1, "Ran it.", at=CLOCK - timedelta(days=3))
        recent = [capture(self.project, 2, "Ran it again.", at=CLOCK - timedelta(hours=2)),
                  capture(self.project, 3, "Ran it once more.", at=CLOCK - timedelta(hours=1))]
        code, out, _, script = self.run_tool("1", "", options=self.options("1d"))
        self.assertEqual(code, 0)
        self.assertEqual(script.answers, [])
        self.assertIn("1 of 3 captured reports still to do; "
                      "2 captured in the last 1d left for later", out)
        for report in recent:
            self.assertNotIn(report, out)
        self.assertEqual([line["report"] for line in self.lines()], [old])

    def test_a_recent_report_is_asked_once_it_is_old_enough(self):
        recent = capture(self.project, 1, "Ran it.", at=CLOCK - timedelta(hours=2))
        _, _, _, script = self.run_tool(options=self.options("1d"))
        self.assertEqual(script.prompts, [])
        self.run_tool("1", "", options=self.options("1d"), now=CLOCK + timedelta(days=1))
        self.assertEqual([line["report"] for line in self.lines()], [recent])

    def test_a_report_exactly_at_the_cutoff_is_old_enough(self):
        capture(self.project, 1, "Ran it.", at=CLOCK - timedelta(days=1))
        self.run_tool("1", "", options=self.options("1d"))
        self.assertEqual(len(self.lines()), 1)

    def test_hours_are_an_age_as_well_as_days(self):
        older = capture(self.project, 1, "Ran it.", at=CLOCK - timedelta(hours=13))
        capture(self.project, 2, "Ran it again.", at=CLOCK - timedelta(hours=11))
        self.run_tool("1", "", options=self.options("12h"))
        self.assertEqual([line["report"] for line in self.lines()], [older])

    def test_without_the_option_a_report_is_asked_however_recent(self):
        capture(self.project, 1, "Ran it.", at=CLOCK - timedelta(minutes=1))
        self.run_tool("1", "")
        self.assertEqual(len(self.lines()), 1)

    def test_a_report_with_no_readable_capture_time_is_named_and_left_out(self):
        """Its age is unknown, so it may be fresh. Without the option it is
        asked about like any other."""
        reports = self.project / evidence.STATE_DIR / turn.REPORTS
        undated = []
        for number, written in ((1, "yesterday"), (2, "2026-09-18T12:00:00")):
            report = capture(self.project, number, "Ran it.", at=CLOCK - timedelta(days=3))
            path = reports / f"{report}.md"
            path.write_text(re.sub(r"^captured: .*$", f"captured: {written}",
                                   path.read_text(encoding="utf-8"), flags=re.MULTILINE),
                            encoding="utf-8")
            undated.append((report, path))
        code, _, err, script = self.run_tool(options=self.options("1d"))
        self.assertEqual(code, 0)
        self.assertEqual(script.prompts, [])
        for _, path in undated:
            self.assertIn(f"no capture time: {path}", err)
        self.run_tool("1", "", "1", "")
        self.assertEqual([line["report"] for line in self.lines()],
                         [report for report, _ in undated])

    def test_an_age_that_is_not_one_is_refused_before_anything_is_asked(self):
        capture(self.project, 1, "Ran it.", at=CLOCK - timedelta(days=3))
        for written in ("1", "d", "0d", "1w", "1.5d", "-1d", "1 d", "1D"):
            with self.subTest(age=written):
                script = Script("1", "")
                argv = ["annotate.py", "--by", "SP", "--corpus", str(self.corpus),
                        "--older-than", written, str(self.project)]
                with self.assertRaises(SystemExit) as caught, \
                        contextlib.redirect_stderr(io.StringIO()):
                    annotate.main(argv, ask=script, out=io.StringIO(), today=lambda: TODAY,
                                  now=lambda: CLOCK)
                self.assertEqual(caught.exception.code, 2)
                self.assertEqual(script.prompts, [])
        self.assertFalse(self.corpus.exists())


if __name__ == "__main__":
    unittest.main()
