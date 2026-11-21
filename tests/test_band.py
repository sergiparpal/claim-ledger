"""mods/claim-ledger-band/band.py: the turn's appendix, and the band's one line.

The band is a summary of the appendix, so I-5 is what these tests hold it to:
it names every group the appendix lists, the most severe first, and never
reads milder than the worst of them. The appendices are made by
ledger.appendix itself, so a change to the renderer that the band would
misread fails here rather than on screen.

The reader is held to the other half: the appendix it returns is the one the
Stop hook left after the turn's last answer, and a turn that left none says
so, since an earlier turn's appendix shown in its place would read as a clean
turn (I-9).
"""

import importlib.util
import itertools
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ledger import appendix, config, coverage, join, schema

BAND_PY = Path(__file__).resolve().parent.parent / "mods" / "claim-ledger-band" / "band.py"

_spec = importlib.util.spec_from_file_location("claim_ledger_band", BAND_PY)
band = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(band)

WHERE = schema.Provenance("extract-1+test", "deepseek/deepseek-v4.1-flash",
                          "https://openrouter.ai/api/v1", "Morph")
AT = "2026-11-21T10:00:00.000Z"


def judged(span, verdict, claim_type="suite_passed", scope=None):
    return join.Judged(schema.Claim(span, claim_type, (), WHERE), verdict, scope, 1)


def unreported(what, tier=config.REVIEW):
    return coverage.Unreported(position=1, kind="mutation", what=what, tier=tier, record={})


def of(turn, reason="answer"):
    return band.band(appendix.render(turn), reason)


class OneLineFormsTest(unittest.TestCase):
    def test_the_collapsed_line_is_the_band_as_it_is(self):
        turn = appendix.Turn(judged=[judged("the tests pass", join.VERIFIED,
                                            scope=f"make verify ok at {AT}"),
                                     judged("this is cleaner", join.NOT_CHECKABLE, "judgment")],
                             checks_seen=1)
        self.assertEqual(of(turn), (appendix.render(turn), "quiet"))

    def test_a_turn_with_no_claims_is_the_collapsed_line_too(self):
        self.assertEqual(of(appendix.Turn()),
                         ("claim-ledger · 0 verified, 0 unchecked · 0 checks seen · "
                          "nothing unreported", "quiet"))

    def test_an_unknown_turn_is_its_line_as_it_is_and_reads_as_an_error(self):
        turn = appendix.Turn(unknown="ExtractError: the model call returned HTTP 404",
                             checks_seen=2)
        self.assertEqual(of(turn), (appendix.render(turn), "error"))


class ExpandedFormTest(unittest.TestCase):
    def test_each_group_is_named_with_its_count_then_the_appendixs_last_line(self):
        turn = appendix.Turn(
            judged=[judged("the suite is green", join.STALE,
                           scope=f"make verify ok at {AT}; src/a.py was modified after it ran"),
                    judged("I ran the migration", join.UNSUPPORTED, "command_run"),
                    judged("I updated the parser", join.UNSUPPORTED, "file_changed"),
                    judged("it reads better", join.NOT_CHECKABLE, "judgment"),
                    judged("lint passes", join.VERIFIED, scope=f"make lint ok at {AT}")],
            unreported=[unreported("migrations/0007.sql", config.HUMAN)],
            checks_seen=2)
        self.assertEqual(of(turn), (
            "claim-ledger · STALE 1 · UNSUPPORTED 2 · UNREPORTED 1 · "
            "1 verified, 1 unchecked · 2 checks seen", "warn"))

    def test_defects_are_counted_as_a_group_of_their_own(self):
        turn = appendix.Turn(defects=[schema.Defect("sentence 40", "no such sentence"),
                                      schema.Defect("sentence 41", "no such sentence")])
        self.assertEqual(of(turn), (
            "claim-ledger · EXTRACTION DEFECTS 2 · 0 verified, 0 unchecked · 0 checks seen",
            "note"))

    def test_unsupported_claims_alone_are_a_note_and_stale_ones_a_warning(self):
        """The colour scale: most turns hold an UNSUPPORTED claim, few a STALE one."""
        unsupported = judged("I ran the migration", join.UNSUPPORTED, "command_run")
        stale = judged("the suite is green", join.STALE,
                       scope=f"make verify ok at {AT}; src/a.py was modified after it ran")
        self.assertEqual(of(appendix.Turn(judged=[unsupported]))[1], "note")
        self.assertEqual(of(appendix.Turn(judged=[unsupported, stale]))[1], "warn")

    def test_a_contradicted_or_unknown_claim_makes_it_an_error(self):
        for verdict in (join.CONTRADICTED, join.UNKNOWN):
            with self.subTest(verdict=verdict):
                turn = appendix.Turn(judged=[judged("the tests pass", verdict,
                                                    scope=f"pytest -q failed at {AT}")])
                line, level = of(turn)
                self.assertTrue(line.startswith(f"claim-ledger · {verdict} 1 · "), line)
                self.assertEqual(level, "error")

    def test_only_low_tier_actions_left_unlisted_is_quiet(self):
        """The renderer expands for them and lists none; its last line says how many."""
        turn = appendix.Turn(judged=[judged("lint passes", join.VERIFIED,
                                            scope=f"make lint ok at {AT}")],
                             unreported=[unreported("notes.txt", config.LOW)], checks_seen=1)
        self.assertEqual(of(turn), (
            "claim-ledger · 1 verified, 0 unchecked · 1 check seen · "
            "1 LOW-tier action not listed", "quiet"))

    def test_a_scope_or_an_action_over_several_lines_does_not_change_the_counts(self):
        heredoc = "python3 - <<'EOF'\nprint('ok')\n\nprint(\"done\")\nEOF"
        turn = appendix.Turn(
            judged=[judged("I ran the script", join.STALE, "command_run",
                           scope=f"{heredoc} ok at {AT}; src/a.py was modified after it ran"),
                    judged("the tests pass", join.UNSUPPORTED)],
            unreported=[unreported(heredoc), unreported("src/b.py")])
        line, _ = of(turn)
        self.assertTrue(line.startswith(
            "claim-ledger · STALE 1 · UNSUPPORTED 1 · UNREPORTED 2 · 0 verified"), line)

    def test_the_most_severe_group_leads_and_every_group_is_named(self):
        """I-5, over every mix of the listed verdicts, with and without the rest."""
        listed = appendix.LISTED
        for size in range(1, len(listed) + 1):
            for verdicts in itertools.combinations(listed, size):
                for extra in ((), ("UNREPORTED",), ("UNREPORTED", "EXTRACTION DEFECTS")):
                    with self.subTest(verdicts=verdicts, extra=extra):
                        turn = appendix.Turn(
                            judged=[judged(f"claim {v}", v, scope=f"pytest -q ok at {AT}")
                                    for v in reversed(verdicts)],
                            unreported=[unreported("src/x.py")] if extra else [],
                            defects=([schema.Defect("sentence 9", "no such sentence")]
                                     if "EXTRACTION DEFECTS" in extra else []))
                        line, level = of(turn)
                        named = [part.rsplit(" ", 1)[0] for part in line.split(" · ")[1:]
                                 if part.rsplit(" ", 1)[0] in band.GROUPS]
                        worst = min(verdicts, key=appendix.SEVERITY.index)
                        self.assertEqual(named[0], worst)
                        self.assertEqual(named, [v for v in listed if v in verdicts] + list(extra))
                        self.assertEqual(level, "error" if set(verdicts) & set(band.SEVERE)
                                         else "warn" if join.STALE in verdicts else "note")

    def test_entries_dropped_to_fit_are_said_as_the_appendix_says_them(self):
        long = "x" * 119
        turn = appendix.Turn(judged=[judged(f"{long} {i}", join.UNSUPPORTED)
                                     for i in range(80)]
                             + [judged("the tests pass", join.CONTRADICTED,
                                       scope=f"pytest -q failed at {AT}")])
        text = appendix.render(turn)
        self.assertIn("dropped to fit", text.rsplit("\n", 1)[-1])
        line, level = band.band(text)
        self.assertTrue(line.startswith("claim-ledger · CONTRADICTED 1 · UNSUPPORTED "), line)
        self.assertTrue(line.endswith("dropped to fit"), line)
        self.assertEqual(level, "error")

    def test_an_appendix_cut_at_the_cap_says_so_and_reads_as_an_error(self):
        """Unreported actions are never dropped, so enough of them cut the text."""
        turn = appendix.Turn(unreported=[unreported(f"src/{'d' * 60}/{i}.py")
                                         for i in range(300)])
        text = appendix.render(turn)
        self.assertEqual(len(text), appendix.LIMIT)
        line, level = band.band(text)
        self.assertTrue(line.startswith("claim-ledger · UNREPORTED "), line)
        self.assertTrue(line.endswith(" · appendix cut short"), line)
        self.assertEqual(level, "error")

    def test_text_in_no_form_the_renderer_writes_is_not_summarised(self):
        for text in ("claim-ledger · something new", "claim-ledger\n\nsomething new",
                     "another plugin"):
            with self.subTest(text=text):
                self.assertEqual(band.band(text), band.UNREADABLE)
                self.assertEqual(band.UNREADABLE[1], "error")


class MissingTest(unittest.TestCase):
    def test_an_answered_turn_without_an_appendix_reads_as_an_error(self):
        self.assertEqual(band.band(None, "answer"),
                         ("claim-ledger · no appendix for this turn", "error"))

    def test_a_turn_with_no_stop_says_it_was_not_audited(self):
        for reason, why in (("aborted", "the turn was interrupted"),
                            ("error", "the turn ended on an API error"),
                            ("refusal", "the model refused")):
            with self.subTest(reason=reason):
                self.assertEqual(band.band(None, reason),
                                 (f"claim-ledger · not audited: {why}", "warn"))

    def test_a_reason_it_does_not_know_reads_as_an_answered_turn(self):
        self.assertEqual(band.band(None, "something new"), band.band(None, "answer"))


def prompt(text="go", prompt_id="p2"):
    return {"type": "user", "promptId": prompt_id, "message": {"role": "user", "content": text}}


def tool_result(prompt_id="p2"):
    return {"type": "user", "promptId": prompt_id, "toolUseResult": {},
            "message": {"role": "user", "content": []}}


def answer(text="done"):
    return {"type": "assistant", "message": {"role": "assistant", "content": text}}


def system_message(content, event="Stop"):
    return {"type": "attachment", "attachment": {"type": "hook_system_message",
                                                 "content": content, "hookName": event,
                                                 "hookEvent": event, "toolUseID": "t"}}


def hook_success():
    return {"type": "attachment", "attachment": {"type": "hook_success", "hookEvent": "Stop"}}


def stop_summary():
    return {"type": "system", "subtype": "stop_hook_summary", "hookCount": 1, "hookErrors": []}


EARLIER = "claim-ledger · 2 verified, 0 unchecked · 1 check seen · nothing unreported"
THIS = "claim-ledger\n\nUNSUPPORTED\n  \"I ran it\"\n  no matching command in this session\n\n" \
       "0 verified, 0 unchecked · 0 checks seen"


class TranscriptTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "session.jsonl"

    def write(self, *rows, tail=""):
        self.path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
                             + tail, encoding="utf-8")
        return str(self.path)

    def earlier_turn(self):
        return [prompt(prompt_id="p1"), answer(), hook_success(), system_message(EARLIER),
                stop_summary()]

    def test_the_appendix_after_the_last_answer_is_this_turns(self):
        path = self.write(*self.earlier_turn(), prompt(), answer("tool use"), tool_result(),
                          answer(), hook_success(), system_message(THIS), stop_summary())
        self.assertEqual(band.this_turns_appendix(path), THIS)

    def test_an_earlier_turns_appendix_is_never_this_turns(self):
        path = self.write(*self.earlier_turn(), prompt(), answer(), hook_success(),
                          stop_summary())
        self.assertIsNone(band.this_turns_appendix(path))

    def test_a_turn_that_ended_before_any_answer_does_not_reach_back(self):
        path = self.write(*self.earlier_turn(), prompt(),
                          {"type": "system", "subtype": "api_error"})
        self.assertIsNone(band.this_turns_appendix(path))

    def test_of_several_stops_in_one_prompt_the_last_is_taken(self):
        path = self.write(prompt(), answer(), system_message(EARLIER), stop_summary(),
                          answer("went on"), system_message(THIS), stop_summary())
        self.assertEqual(band.this_turns_appendix(path), THIS)

    def test_a_last_stop_that_left_none_is_missing_though_an_earlier_one_did(self):
        path = self.write(prompt(), answer(), system_message(EARLIER), stop_summary(),
                          answer("went on"), stop_summary())
        self.assertIsNone(band.this_turns_appendix(path))

    def test_other_system_messages_are_passed_over(self):
        path = self.write(prompt(), answer(), system_message(THIS),
                          system_message("format_edited: 2 files formatted"),
                          system_message("claim-ledger-band says hello"),
                          system_message("claim-ledger · from another event", "SessionStart"),
                          stop_summary())
        self.assertEqual(band.this_turns_appendix(path), THIS)

    def test_a_line_still_being_written_is_passed_over(self):
        path = self.write(prompt(), answer(), system_message(THIS),
                          tail='{"type": "system", "subtype": "stop_hook_su')
        self.assertEqual(band.this_turns_appendix(path), THIS)

    def test_lines_are_split_on_newline_only(self):
        """A span may quote any character; the row holding it is still one line."""
        text = ("claim-ledger\n\nUNSUPPORTED\n  \"a b c\x85d\x0ce\"\n"
                "  no matching command in this session\n\n0 verified, 0 unchecked · 0 checks seen")
        path = self.write(prompt(), answer(), system_message(text))
        self.assertIn(" ", self.path.read_text(encoding="utf-8"))
        self.assertEqual(band.this_turns_appendix(path), text)

    def test_blocks_smaller_than_a_line_read_the_same(self):
        rows = [*self.earlier_turn(), prompt(), answer(), system_message(THIS), stop_summary()]
        path = self.write(*rows)
        whole = list(band.lines_from_end(path))
        for size in (1, 7, 64, 1 << 16):
            with self.subTest(block=size):
                self.assertEqual(list(band.lines_from_end(path, block=size)), whole)
        self.assertEqual([json.loads(line) for line in reversed(whole) if line],
                         [json.loads(json.dumps(r)) for r in rows])


class MainTest(unittest.TestCase):
    def run_band(self, *args):
        return subprocess.run([sys.executable, "-I", str(BAND_PY), *args],
                              capture_output=True, text=True, timeout=30)

    def test_it_prints_the_band_the_level_and_the_appendix(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "session.jsonl"
            path.write_text("\n".join(json.dumps(r) for r in
                                      (prompt(), answer(), system_message(THIS))) + "\n",
                            encoding="utf-8")
            done = self.run_band(str(path), "answer")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue(done.stdout.isascii())
        self.assertEqual(json.loads(done.stdout), {
            "band": "claim-ledger · UNSUPPORTED 1 · 0 verified, 0 unchecked · 0 checks seen",
            "level": "note", "appendix": THIS})

    def test_a_turn_without_an_appendix_prints_none(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "session.jsonl"
            path.write_text(json.dumps(prompt()) + "\n", encoding="utf-8")
            done = self.run_band(str(path), "aborted")
        self.assertEqual(json.loads(done.stdout), {
            "band": "claim-ledger · not audited: the turn was interrupted",
            "level": "warn", "appendix": None})

    def test_a_transcript_that_is_not_there_is_said_not_raised(self):
        for path in ("", "/nonexistent/claim-ledger-band/session.jsonl"):
            with self.subTest(path=path):
                done = self.run_band(path)
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(json.loads(done.stdout), {
                    "band": "claim-ledger · no transcript to read", "level": "error",
                    "appendix": None})

    def test_it_needs_a_transcript_and_at_most_a_reason(self):
        for args in ((), ("a", "b", "c")):
            with self.subTest(args=args):
                done = self.run_band(*args)
                self.assertEqual(done.returncode, 2)
                self.assertIn("usage", done.stderr)


if __name__ == "__main__":
    unittest.main()
