"""tools/annotate_model.py: a model annotates, against the report alone, as a person would.

What is tested is what would quietly spoil the reference A-12 makes of the
model: a prompt that carries the turn's evidence or anything but the guide and
the report, a span that is not in its sentence, an answer read past an error or
signed by a model that did not give it, a report the extractor never reads
taken into the corpus, and a CLI that runs inside the session or the project
that started it. No call leaves the machine: every answer here is written by
the test.
"""

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from datetime import date
from pathlib import Path

from ledger import config
from tests.test_annotate import EVIDENCE, REPORT, SENTENCES, capture

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import annotate_model  # noqa: E402

TODAY = date(2026, 10, 23)
MODEL = annotate_model.MODEL


def envelope(answer, *, model=MODEL, error=False, subtype="success"):
    """What the CLI prints in JSON mode, around the model's answer."""
    text = answer if isinstance(answer, str) else json.dumps(answer)
    return {"type": "result", "subtype": subtype, "is_error": error, "result": text,
            "modelUsage": {model: {"inputTokens": 900, "outputTokens": 40}}}


class Answers:
    """The model, played by the test: hands back these envelopes and keeps the prompts."""

    def __init__(self, *envelopes):
        self.envelopes = list(envelopes)
        self.prompts = []

    def __call__(self, prompt, *, model):
        self.prompts.append(prompt)
        return self.envelopes.pop(0)


class AnnotateModelCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        self.project = self.tmp / "project"
        self.project.mkdir()
        shutil.copy(REPO / config.CONFIG_FILENAME, self.project / config.CONFIG_FILENAME)
        self.corpus = self.tmp / "corpus" / "annotations.jsonl"

    def run_tool(self, answers, *options):
        out, err = io.StringIO(), io.StringIO()
        argv = ["annotate_model.py", "--corpus", str(self.corpus), *options, str(self.project)]
        with contextlib.redirect_stderr(err):
            code = annotate_model.main(argv, run=answers, version=lambda: "9.9.9",
                                       today=lambda: TODAY, out=out)
        return code, out.getvalue(), err.getvalue()

    def lines(self):
        if not self.corpus.exists():
            return []
        return [json.loads(line) for line in self.corpus.read_text(encoding="utf-8").splitlines()]


class PromptTest(AnnotateModelCase):
    def test_the_model_gets_the_guide_and_the_numbered_report_and_nothing_else(self):
        capture(self.project, 1, REPORT)
        answers = Answers(envelope({"claims": []}))
        self.run_tool(answers)
        [prompt] = answers.prompts
        self.assertIn(annotate_model.GUIDE.read_text(encoding="utf-8").strip(), prompt)
        for number, sentence in enumerate(SENTENCES, 1):
            self.assertIn(f"[{number}] {sentence}", prompt)
        self.assertNotIn("--evidence-only-marker", prompt)   # the capture holds it
        self.assertNotIn(EVIDENCE, prompt)

    def test_a_dry_run_prints_the_prompt_and_calls_nothing(self):
        capture(self.project, 1, REPORT)
        answers = Answers()
        code, out, _ = self.run_tool(answers, "--dry-run")
        self.assertEqual(code, 0)
        self.assertEqual(answers.prompts, [])
        self.assertIn(f"[2] {SENTENCES[1]}", out)
        self.assertEqual(self.lines(), [])


class AnswerTest(AnnotateModelCase):
    def setUp(self):
        super().setUp()
        self.report = capture(self.project, 1, REPORT)

    def saved_claims(self, *answers):
        code, out, err = self.run_tool(Answers(*answers))
        return code, (self.lines()[0]["claims"] if self.lines() else None), err

    def test_an_answer_is_saved_in_the_spec_shape_signed_by_the_model(self):
        code, _, _ = self.run_tool(Answers(envelope({"claims": [
            {"sentence": 2, "type": "suite_passed"}, {"sentence": 3, "type": "intent"}]})))
        self.assertEqual(code, 0)
        self.assertEqual(self.lines(), [{
            "report": self.report, "annotated": "2026-10-23",
            "by": f"{MODEL} via Claude Code 9.9.9",
            "claims": [{"span": SENTENCES[1], "type": "suite_passed"},
                       {"span": SENTENCES[2], "type": "intent"}]}])

    def test_a_split_sentence_keeps_each_span_as_given(self):
        _, claims, _ = self.saved_claims(envelope({"claims": [
            {"sentence": 3, "type": "intent", "span": "I'll proceed with staging"},
            {"sentence": 3, "type": "judgment", "span": "pushing the changes"}]}))
        self.assertEqual(claims, [{"span": "I'll proceed with staging", "type": "intent"},
                                  {"span": "pushing the changes", "type": "judgment"}])

    def test_a_span_must_be_in_its_own_sentence_word_for_word(self):
        for span in ("the unit tests passed", "The unit test passed."):   # the second is sentence 2's
            with self.subTest(span):
                code, claims, err = self.saved_claims(envelope({"claims": [
                    {"sentence": 1, "type": "judgment", "span": span}]}))
                self.assertEqual((code, claims), (1, None))
                self.assertIn(f"left {self.report} unannotated", err)
                self.assertIn("not in sentence 1 word for word", err)

    def test_what_the_answer_names_must_be_in_the_report_and_the_vocabulary(self):
        for item in ({"sentence": 4, "type": "judgment"}, {"sentence": 0, "type": "judgment"},
                     {"sentence": True, "type": "judgment"}, {"sentence": "2", "type": "judgment"},
                     {"sentence": 2, "type": "behaviour_checked"},
                     {"sentence": 2, "type": "judgment", "referents": []}, {"sentence": 2}):
            with self.subTest(item):
                code, claims, _ = self.saved_claims(envelope({"claims": [item]}))
                self.assertEqual((code, claims), (1, None))

    def test_a_fenced_answer_is_read_and_one_wrapped_in_prose_is_not(self):
        answer = json.dumps({"claims": [{"sentence": 2, "type": "suite_passed"}]})
        _, claims, _ = self.saved_claims(envelope(f"```json\n{answer}\n```"))
        self.assertEqual(claims, [{"span": SENTENCES[1], "type": "suite_passed"}])
        self.corpus.unlink()
        code, claims, err = self.saved_claims(envelope(f"Here it is: {answer}"))
        self.assertEqual((code, claims), (1, None))
        self.assertIn("not JSON", err)

    def test_an_answer_the_cli_calls_an_error_is_not_read(self):
        for broken in (envelope({"claims": []}, error=True),
                       envelope({"claims": []}, subtype="error_max_turns")):
            with self.subTest(broken["subtype"]):
                code, claims, err = self.saved_claims(broken)
                self.assertEqual((code, claims), (1, None))
                self.assertIn("reports an error", err)

    def test_an_answer_another_model_gave_is_not_signed_as_this_one(self):
        code, claims, err = self.saved_claims(envelope({"claims": []}, model="claude-haiku-5-5"))
        self.assertEqual((code, claims), (1, None))
        self.assertIn(f"answered by claude-haiku-5-5, not {MODEL}", err)

    def test_the_same_claim_twice_is_kept_once(self):
        item = {"sentence": 2, "type": "suite_passed"}
        _, claims, _ = self.saved_claims(envelope({"claims": [item, item]}))
        self.assertEqual(claims, [{"span": SENTENCES[1], "type": "suite_passed"}])


class ChoiceTest(AnnotateModelCase):
    def test_annotated_reports_are_left_and_only_and_limit_choose_among_the_rest(self):
        first, second, third = (capture(self.project, n, REPORT) for n in (1, 2, 3))
        self.corpus.parent.mkdir(parents=True)
        self.corpus.write_text(json.dumps({"report": first, "claims": []}) + "\n",
                               encoding="utf-8")
        answers = Answers(envelope({"claims": []}))
        self.run_tool(answers, "--only", third)
        self.assertEqual([line["report"] for line in self.lines()], [first, third])
        answers = Answers(envelope({"claims": []}))
        self.run_tool(answers, "--limit", "1")
        self.assertEqual([line["report"] for line in self.lines()], [first, third, second])
        self.assertEqual(len(answers.prompts), 1)

    def test_a_report_longer_than_the_extractor_reads_is_left_out(self):
        limit = config.load(self.project / config.CONFIG_FILENAME).extractor.max_report_chars
        capture(self.project, 1, "Long. " * (limit // 6 + 1))
        answers = Answers()
        code, _, err = self.run_tool(answers)
        self.assertEqual((code, answers.prompts, self.lines()), (0, [], []))
        self.assertIn("longer than the extractor reads", err)

    def test_a_report_with_no_sentence_is_saved_empty_without_asking(self):
        report = capture(self.project, 1, "---")
        answers = Answers()
        self.run_tool(answers)
        self.assertEqual(answers.prompts, [])
        self.assertEqual(self.lines()[0]["claims"], [])
        self.assertEqual(self.lines()[0]["report"], report)


class CliTest(unittest.TestCase):
    def test_the_cli_reaches_nothing_but_the_prompt(self):
        command = annotate_model.cli_command(MODEL)
        self.assertEqual(command[:2], ["claude", "-p"])
        self.assertEqual(command[command.index("--model") + 1], MODEL)
        self.assertEqual(command[command.index("--output-format") + 1], "json")
        self.assertEqual(command[command.index("--tools") + 1], "")
        self.assertEqual(command[command.index("--setting-sources") + 1], "project")
        for flag in ("--strict-mcp-config", "--disable-slash-commands",
                     "--no-session-persistence"):
            self.assertIn(flag, command)

    def test_the_cli_does_not_run_as_the_child_of_a_session(self):
        environ = {"PATH": "/usr/bin", "HOME": "/home/x", "CLAUDECODE": "1",
                   "CLAUDE_CODE_SESSION_ID": "s", "ANTHROPIC_BASE_URL": "http://proxy",
                   "ANTHROPIC_API_KEY": "key"}
        self.assertEqual(annotate_model.cli_env(environ), {"PATH": "/usr/bin",
                                                           "HOME": "/home/x"})

    def test_the_cli_runs_from_an_empty_folder_with_the_prompt_on_stdin(self):
        seen = {}

        def fake(command, **kwargs):
            seen.update(kwargs, listing=sorted(Path(kwargs["cwd"]).iterdir()))
            return subprocess.CompletedProcess(command, 0, json.dumps(envelope({"claims": []})),
                                               "")
        with unittest.mock.patch.object(annotate_model.subprocess, "run", fake):
            result = annotate_model.run_cli("the prompt", model=MODEL)
        self.assertEqual(result["result"], json.dumps({"claims": []}))
        self.assertEqual((seen["input"], seen["listing"]), ("the prompt", []))
        self.assertFalse(Path(seen["cwd"]).is_relative_to(REPO))
        self.assertNotIn("CLAUDE_CODE_SESSION_ID", seen["env"])

    def test_a_failing_cli_is_an_annotation_error_not_a_crash(self):
        def fake(command, **kwargs):
            return subprocess.CompletedProcess(command, 1, "", "not logged in")
        with unittest.mock.patch.object(annotate_model.subprocess, "run", fake):
            with self.assertRaisesRegex(annotate_model.AnnotationError, "not logged in"):
                annotate_model.run_cli("p", model=MODEL)


if __name__ == "__main__":
    unittest.main()
