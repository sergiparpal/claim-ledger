"""tools/daily_use.py: reading back daily use without misreading it.

What is tested is what would turn a read-back into a wrong finding: a refused
call counted as a hole in the log or a real hole missed, a resumed session's
inherited calls counted as holes, a transcript line lost to a character that
splitlines() breaks on, a turn's ending misread or paired with the next turn's
hook, a verdict candidate missed, a pattern of misplaced verdicts read off a
record other than the one that decided the claim, a reading by hand misread,
and a span shown to someone who did not ask for spans. Every project and
transcript here is built in a temporary folder.
"""

import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ledger import evidence, turn

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import daily_use  # noqa: E402

SESSION = "0f8fad5b-d9cb-469f-a165-70867728950e"
EARLIER = "7c9e6679-7425-40de-944b-e07fc1f90ae7"


class DailyUseCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = Path(tmp.name) / "project"
        self.transcripts = Path(tmp.name) / "transcripts"
        self.project.mkdir()
        self.transcripts.mkdir()

    def run_tool(self, *args):
        shown = io.StringIO()
        with contextlib.redirect_stdout(shown):
            code = daily_use.main(["daily_use.py", *args, "--root", str(self.project)])
        return code, shown.getvalue()

    def record(self, session, tool_use_id, tool="Bash", **fields):
        evidence.append(evidence.session_log(self.project, session),
                        {"v": evidence.RECORD_VERSION, "session": session,
                         "tool_use_id": tool_use_id, "tool": tool, "kind": "other",
                         "outcome": "ok", "ts_end": "2026-10-17T10:00:00.000Z",
                         "tier": "REVIEW", **fields})

    def transcript(self, session, lines):
        with (self.transcripts / f"{session}.jsonl").open("a", encoding="utf-8") as out:
            for line in lines:
                out.write(json.dumps(line, ensure_ascii=False) + "\n")

    def claims(self, *rows):
        path = self.project / evidence.STATE_DIR / "claims.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as out:
            for row in rows:
                out.write(json.dumps({"v": 1, "session": SESSION, **row}, ensure_ascii=False)
                          + "\n")


def called(tool_use_id, name="Bash", **given):
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": tool_use_id, "name": name, "input": given}]}}


def answered(tool_use_id, text="done", error=False):
    return {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": tool_use_id, "content": text,
         "is_error": error}]}}


class RecordingTest(DailyUseCase):
    def check(self):
        return self.run_tool("recording", "--transcripts", str(self.transcripts))

    def test_every_call_recorded_is_no_hole_and_a_refusal_is_none_either(self):
        self.record(SESSION, "toolu_A")
        self.record(SESSION, "toolu_B", tool="Edit")
        self.transcript(SESSION, [
            called("toolu_A", command="ls"), answered("toolu_A"),
            called("toolu_B", "Edit", file_path="docs/SPEC.md"), answered("toolu_B"),
            called("toolu_C", "Read", file_path="README.md"), answered("toolu_C"),
            called("toolu_D", command="rm -rf build"),
            answered("toolu_D", "Permission to use Bash with command rm -rf build has been "
                                "denied.", error=True)])
        code, shown = self.check()
        self.assertEqual(code, 0)
        self.assertIn("1 errors and 0 cancelled with no record, 0 ran with no record", shown)
        self.assertIn("error, no record: Bash toolu_D: Permission to use Bash", shown)
        self.assertIn("0 holes", shown)

    def test_a_call_that_ran_with_no_record_is_a_hole(self):
        self.record(SESSION, "toolu_A")
        self.transcript(SESSION, [called("toolu_A", command="ls"), answered("toolu_A"),
                                  called("toolu_E", command="make"), answered("toolu_E")])
        code, shown = self.check()
        self.assertEqual(code, 1)
        self.assertIn("ran, no record:  Bash toolu_E make", shown)

    def test_a_record_with_no_call_is_a_hole(self):
        self.record(SESSION, "toolu_A")
        self.record(SESSION, "toolu_F")
        self.transcript(SESSION, [called("toolu_A", command="ls"), answered("toolu_A")])
        code, shown = self.check()
        self.assertEqual(code, 1)
        self.assertIn("record, no call: toolu_F", shown)

    def test_a_resumed_sessions_inherited_calls_are_no_holes(self):
        self.record(EARLIER, "toolu_A")
        self.record(SESSION, "toolu_G")
        self.transcript(EARLIER, [called("toolu_A", command="ls"), answered("toolu_A")])
        self.transcript(SESSION, [called("toolu_A", command="ls"), answered("toolu_A"),
                                  called("toolu_G", command="pwd"), answered("toolu_G")])
        code, shown = self.check()
        self.assertEqual(code, 0)
        self.assertIn("1 recorded here, 1 under an earlier session", shown)

    def test_a_line_carrying_a_line_separator_is_not_lost(self):
        self.record(SESSION, "toolu_A")
        self.transcript(SESSION, [called("toolu_A", command="echo 'a b'"),
                                  answered("toolu_A")])
        code, shown = self.check()
        self.assertEqual(code, 0)
        self.assertIn("1 recorded here", shown)


class LatencyTest(DailyUseCase):
    def capture(self, number, minute):
        turn.capture(self.project, {"last_assistant_message": "Done. The tests pass."},
                     SESSION, number, datetime(2026, 10, 17, 10, minute, tzinfo=timezone.utc),
                     [], None)

    def stop(self, minute, seconds, message):
        return {"type": "attachment", "sessionId": SESSION,
                "timestamp": f"2026-10-17T10:{minute:02d}:30.000Z",
                "attachment": {"type": "hook_success", "hookEvent": "Stop",
                               "durationMs": int(seconds * 1000),
                               "stdout": json.dumps({"systemMessage": message})}}

    def test_each_ending_is_read_from_where_it_is_written(self):
        for number in range(1, 7):
            self.capture(number, number * 5)
        self.claims({"turn_number": 1, "row": "claim", "span": "The tests pass.",
                     "type": "suite_passed", "referents": []},
                    {"turn_number": 6, "row": "claim", "span": "The tests pass.",
                     "type": "suite_passed", "referents": []})
        errors = self.project / evidence.STATE_DIR / "errors.log"
        errors.write_text("".join(json.dumps({"component": "turn", "session": SESSION,
                                              "turn_number": n, "error": text}) + "\n"
                                  for n, text in [
                                      (2, "ExtractError: the model call passed its 12.0s "
                                          "deadline"),
                                      (3, "ExtractError: the model call returned HTTP 401")]),
                          encoding="utf-8")
        self.transcript(SESSION, [
            self.stop(5, 2.5, "claim-ledger · 1 unchecked · 0 checks seen"),
            self.stop(10, 12.1, "claim-ledger · UNKNOWN · ExtractError: … deadline"),
            self.stop(15, 0.4, "claim-ledger · UNKNOWN · ExtractError: … HTTP 401"),
            self.stop(20, 0.5, "claim-ledger · 0 verified, 0 unchecked · 0 checks seen"),
            # turn 5 (minute 25) left no Stop: its row must not take turn 6's
            self.stop(30, 3.0, "claim-ledger · 1 unchecked · 0 checks seen")])
        code, shown = self.run_tool("latency", "--transcripts", str(self.transcripts))
        self.assertEqual(code, 0)
        endings = {line.split()[2]: line for line in shown.splitlines()
                   if line.startswith("2026-10-17T10:")}
        self.assertIn("answered", endings["1"])
        self.assertIn("deadline", endings["2"])
        self.assertIn("http 401", endings["3"])
        self.assertIn("empty answer", endings["4"])
        self.assertIn("no hook found", endings["5"])
        self.assertIn("answered", endings["6"])
        self.assertIn("of the 4 turns whose call answered or ran out of time, 1 passed the "
                      "deadline and 1 came back empty", shown)

    def test_an_ending_needs_no_guess(self):
        self.assertEqual(daily_use.ending("ExtractError: the report is 25575 characters, "
                                          "over the 20000 this extractor accepts", None, None),
                         "too long")
        self.assertEqual(daily_use.ending(None, None, ("t", 900, "claim-ledger · 0 verified, "
                                                       "0 unchecked\n\nEXTRACTION DEFECTS")),
                         "unclear")


class VerdictsTest(DailyUseCase):
    SPANS = ["El commit solo incluye docs/SPEC.md y main sigue igual.",
             "Los dos salen con código 0.", "No he tocado nada más.",
             "He añadido el anexo sobre nodos."]   # "nodos" is not "no"

    def setUp(self):
        super().setUp()
        self.record(SESSION, "toolu_1", tool="Edit", kind="mutation",
                    files=[{"path": "docs/SPEC.md", "mtime": "2026-10-17T10:00:00.000Z"}])
        self.record(SESSION, "toolu_2", command="make verify 2>&1 | tail -3")
        decided = {"verdict": "VERIFIED", "row": "claim", "turn_number": 1}
        self.claims(
            {**decided, "claim_id": "c-1", "span": self.SPANS[0], "type": "file_changed",
             "referents": ["docs/SPEC.md", "main"], "position": 1, "scope": "SPEC written"},
            {**decided, "claim_id": "c-2", "span": self.SPANS[1], "type": "command_run",
             "referents": ["make protected REF=main", "make verify"], "position": 2,
             "scope": "make verify ran"},
            {**decided, "claim_id": "c-3", "span": self.SPANS[2], "type": "file_changed",
             "referents": ["docs/SPEC.md"], "position": 1, "scope": "SPEC written"},
            {**decided, "claim_id": "c-4", "span": self.SPANS[3], "type": "file_changed",
             "referents": ["docs/SPEC.md"], "position": 1, "scope": "SPEC written"})

    def test_both_kinds_of_candidate_are_found_and_nothing_else(self):
        code, shown = self.run_tool("verdicts")
        self.assertEqual(code, 0)
        self.assertIn("does not reach the record that verified it: 2", shown)
        self.assertIn("c-1  file_changed", shown)
        self.assertIn("of them reaching nothing at all ['main']", shown)
        self.assertIn("c-2  command_run", shown)
        self.assertIn("negative word in the span: 1", shown)
        self.assertIn("c-3  file_changed", shown)
        self.assertNotIn("c-4", shown)

    def test_spans_are_shown_only_when_asked_for(self):
        _, shown = self.run_tool("verdicts")
        for span in self.SPANS:
            self.assertNotIn(span, shown)
        _, shown = self.run_tool("verdicts", "--spans")
        self.assertIn(self.SPANS[0], shown)
        self.assertIn(self.SPANS[2], shown)


class ReferentsTest(DailyUseCase):
    OLD = {"model": "deepseek/deepseek-v4.1-flash", "prompt_version": "extract-1+74af1596"}
    NEW = {"model": "mistralai/mistral-medium-3.1", "prompt_version": "extract-2+4e6f09ab"}
    SPANS = ["Cambié docs/SPEC.md.", "Pasé zzz-tool sin errores.", "Llamé a set_context.",
             "281 passed."]

    def setUp(self):
        super().setUp()
        shutil.copy(REPO / "claim-ledger.toml", self.project / "claim-ledger.toml")
        self.record(SESSION, "toolu_1", command="zzz-tool --all")
        claim = {"row": "claim", "verdict": "UNSUPPORTED"}
        self.claims(
            {**claim, "turn_number": 1, "route": self.OLD, "type": "file_changed",
             "referents": ["docs/SPEC.md"], "verdict": "VERIFIED", "span": self.SPANS[0]},
            {**claim, "turn_number": 1, "route": self.OLD, "type": "judgment",
             "referents": [], "verdict": "NOT_CHECKABLE", "span": "Va bien."},
            {**claim, "turn_number": 2, "route": self.NEW, "type": "command_run",
             "referents": ["zzz-tool"], "span": self.SPANS[1]},
            {**claim, "turn_number": 2, "route": self.NEW, "type": "command_run",
             "referents": ["set_context"], "span": self.SPANS[2]},
            {**claim, "turn_number": 2, "route": self.NEW, "type": "suite_passed",
             "referents": ["281 passed"], "span": self.SPANS[3]})

    def test_each_route_gets_its_share_and_its_unsupported_that_match_nothing(self):
        code, shown = self.run_tool("referents")
        self.assertEqual(code, 0)
        self.assertIn("deepseek/deepseek-v4.1-flash, extract-1+74af1596, 1 turn: 1 of 1 (100%)",
                      shown)
        self.assertIn("mistralai/mistral-medium-3.1, extract-2+4e6f09ab, 1 turn: 1 of 3 (33%); "
                      "command_run 1 of 2, file_changed 0 of 0, suite_passed 0 of 1; "
                      "of 3 UNSUPPORTED, 2 could match nothing", shown)

    def test_no_span_and_no_referent_is_shown(self):
        _, shown = self.run_tool("referents")
        for text in [*self.SPANS, "set_context", "docs/SPEC.md"]:
            self.assertNotIn(text, shown)


class MisplacedTest(DailyUseCase):
    """Turn 1 runs pytest and writes src/app.py, turn 2 commits it, turn 3 does neither."""

    EARLY = {"model": "mistralai/mistral-medium-3.1", "prompt_version": "extract-6c+bf5a552b"}
    LATE = {"model": "mistralai/mistral-medium-3-5", "prompt_version": "extract-6c+bf5a552b"}
    RAN, WROTE, COMMITTED = ("2026-11-17T10:01:00.000Z", "2026-11-17T10:02:00.000Z",
                             "2026-11-19T10:03:00.000Z")
    SPAN = "Los tests pasan."

    def setUp(self):
        super().setUp()
        shutil.copy(REPO / "claim-ledger.toml", self.project / "claim-ledger.toml")
        commit = "git add src/app.py && git commit -m app"
        self.record(SESSION, "toolu_1", kind="check", check_id="python-suite", command="pytest",
                    turn_number=1, ts_end=self.RAN)
        self.record(SESSION, "toolu_2", tool="Edit", kind="mutation", turn_number=1,
                    files=[{"path": "src/app.py", "mtime": self.WROTE}], ts_end=self.WROTE)
        self.record(SESSION, "toolu_3", command=commit, turn_number=2, ts_end=self.COMMITTED)
        ran, wrote = f"pytest ok at {self.RAN}", f"src/app.py written ok at {self.WROTE}"
        self.claims(
            self.claim(1, 0, "suite_passed", [], 1, ran),                 # fallback
            self.claim(1, 1, "suite_passed", ["pytest"], 1, ran),         # nothing
            self.claim(1, 2, "suite_passed", ["the tests"], 1, ran),      # alias
            self.claim(1, 3, "judgment", [], None, None, verdict="NOT_CHECKABLE"),
            # names lint directly, and was verified on pytest, which it reached by an alias
            self.claim(1, 4, "suite_passed", ["ruff check .", "the tests"], 1, ran),
            self.claim(2, 0, "file_changed", ["src/app.py"], 2, wrote),   # what was committed
            self.claim(2, 1, "suite_passed", ["pytest"], 1, ran),         # earlier
            self.claim(2, 2, "command_run", ["git commit"], 3,
                       f"{commit} ok at {self.COMMITTED}"),               # nothing
            self.claim(3, 0, "file_changed", ["src/app.py"], 2, wrote),   # earlier: no commit
            self.claim(3, 1, "suite_passed", ["pytest"], 9, ran),         # no record there
            self.claim(3, 2, "suite_passed", [], 1,
                       "pytest ok at 2026-11-19T09:00:00.000Z"))          # another record's

    def claim(self, number, index, kind, referents, position, scope, verdict="VERIFIED"):
        route, day = (self.EARLY, "2026-11-17") if number == 1 else (self.LATE, "2026-11-19")
        return {"row": "claim", "ts": f"{day}T10:0{number}:30.000Z", "turn_number": number,
                "claim_id": f"{SESSION}-{number}-{index}", "span": self.SPAN, "type": kind,
                "referents": referents, "verdict": verdict, "scope": scope,
                "position": position, "route": route}

    def labels(self, *lines):
        path = self.project / "labels.jsonl"
        path.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
        return str(path)

    def test_each_pattern_is_read_off_the_record_that_decided_the_claim(self):
        code, shown = self.run_tool("misplaced")
        self.assertEqual(code, 0)
        self.assertIn("mistralai/mistral-medium-3.1, extract-6c+bf5a552b, 2026-11-17 to "
                      "2026-11-17, 1 turn: 4 VERIFIED\n      fallback 1, earlier 0 (not "
                      "counting 0 file changes in a turn that ran git commit), alias 2; "
                      "fallback or earlier 1 of 4 (25%)", shown)
        self.assertIn("mistralai/mistral-medium-3-5, extract-6c+bf5a552b, 2026-11-19 to "
                      "2026-11-19, 2 turns: 6 VERIFIED, 2 of them without their record\n"
                      "      fallback 0, earlier 2 (not counting 1 file change in a turn that "
                      "ran git commit), alias 0; fallback or earlier 2 of 4 (50%)", shown)
        # by when a route was first used, not by its name, which sorts 3-5 before 3.1
        self.assertLess(shown.index("medium-3.1"), shown.index("medium-3-5"))
        self.assertNotIn("not read by hand", shown)

    def test_the_patterns_are_set_against_a_reading_by_hand(self):
        code, shown = self.run_tool("misplaced", "--labels", self.labels(
            json.dumps({"claim_id": f"{SESSION}-1-0", "label": "ok"}),
            json.dumps({"claim_id": f"{SESSION}-1-2", "label": "alias"}),
            json.dumps({"claim_id": f"{SESSION}-2-0", "label": "ok"}),
            json.dumps({"claim_id": f"{SESSION}-2-1", "label": "plan"}),
            json.dumps({"claim_id": f"{SESSION}-3-1", "label": "ok"}),
            json.dumps({"claim_id": f"{EARLIER}-1-0", "label": "ok"})))
        self.assertEqual(code, 0)
        for line in ("against labels.jsonl: 4 VERIFIED claims read by hand, of which 2 do not "
                     "hold (alias 1, plan 1)",
                     "  fallback            flags   1: 0 do not hold, 1 holds",
                     "  earlier             flags   1: 1 does not hold, 0 hold",
                     "  alias               flags   1: 1 does not hold, 0 hold",
                     "  fallback or earlier flags   2: 1 does not hold, 1 holds",
                     f"  not flagged, though they do not hold: 1\n    {SESSION}-1-2 (alias)",
                     f"  flagged, though they hold: 1\n    {SESSION}-1-0",
                     f"  labels naming no VERIFIED claim in claims.jsonl: 1\n    {EARLIER}-1-0",
                     "  labelled claims whose record the log no longer holds: 1\n"
                     f"    {SESSION}-3-1",
                     "(25%)\n      of the 2 not read by hand, 0 flagged",
                     "(50%)\n      of the 2 not read by hand, 1 flagged"):
            self.assertIn(line, shown)

    def test_the_words_of_the_reading_of_8_november_are_read_too(self):
        code, shown = self.run_tool("misplaced", "--labels", self.labels(
            json.dumps({"claim_id": f"{SESSION}-1-1", "label": "other-run"}),
            json.dumps({"claim_id": f"{SESSION}-1-4", "label": "other-hand"}),
            json.dumps({"claim_id": f"{SESSION}-2-2", "label": "neg"})))
        self.assertEqual(code, 0)
        self.assertIn("3 VERIFIED claims read by hand, of which 3 do not hold (", shown)
        for kind in ("other-run 1", "other-hand 1", "neg 1"):
            self.assertIn(kind, shown)

    def test_a_route_none_of_whose_claims_were_read_is_not_said_to_be_unread(self):
        _, shown = self.run_tool("misplaced", "--labels", self.labels(
            json.dumps({"claim_id": f"{SESSION}-1-0", "label": "ok"})))
        self.assertIn("(25%)\n      of the 3 not read by hand, 0 flagged", shown)
        self.assertTrue(shown.endswith("fallback or earlier 2 of 4 (50%)\n"))

    def test_a_reading_that_cannot_be_read_stops_the_count(self):
        for lines, said in (([json.dumps({"claim_id": f"{SESSION}-1-0", "label": "holds"})],
                             "labels.jsonl:1: wants a claim_id and a label, one of ok, plan"),
                            ([json.dumps({"claim_id": f"{SESSION}-1-0", "label": "ok"}),
                              json.dumps({"claim_id": f"{SESSION}-1-0", "label": "plan"})],
                             f"labels.jsonl:2: {SESSION}-1-0 is labelled twice")):
            told = io.StringIO()
            with contextlib.redirect_stderr(told):
                code, shown = self.run_tool("misplaced", "--labels", self.labels(*lines))
            self.assertEqual(code, 2)
            self.assertIn(said, told.getvalue())
            self.assertEqual(shown, "")

    def test_a_log_that_cannot_be_read_is_named_and_its_claims_set_apart(self):
        log = evidence.session_log(self.project, EARLIER)
        log.write_text("not a record\n", encoding="utf-8")
        self.claims({**self.claim(3, 3, "suite_passed", ["pytest"], 1, f"pytest ok at {self.RAN}"),
                     "session": EARLIER, "claim_id": f"{EARLIER}-3-3"})
        code, shown = self.run_tool("misplaced")
        self.assertEqual(code, 0)
        self.assertIn("3 turns: 7 VERIFIED, 3 of them without their record", shown)
        self.assertIn(f"{EARLIER[:8]}  the log cannot be read: {log}:1: not a JSON record", shown)

    def test_no_span_is_shown(self):
        label = json.dumps({"claim_id": f"{SESSION}-1-0", "label": "ok"})
        for args in (["misplaced"], ["misplaced", "--labels", self.labels(label)]):
            _, shown = self.run_tool(*args)
            self.assertNotIn(self.SPAN, shown)


class DefectsTest(DailyUseCase):
    REPORT = ("Dice que `selection` contiene «`pair_of`, `judge`». **La regla** va aquí. "
              "Las corrijo respecto al plan.")

    def setUp(self):
        super().setUp()
        turn.capture(self.project, {"last_assistant_message": self.REPORT}, SESSION, 3,
                     datetime(2026, 10, 17, 10, 0, tzinfo=timezone.utc), [], None)
        self.claims(*({"turn_number": 3, "row": "defect", "claim_id": f"{SESSION}-3-d{n}",
                       "span": span, "reason": "not verbatim in the report"}
                      for n, span in enumerate([
                          "Dice que `selection` contiene «`pair_of`, `judge`.",
                          "La regla va aquí.",
                          "Las correcciones respecto al plan."])),
                    {"turn_number": 3, "row": "defect", "claim_id": f"{SESSION}-3-d3",
                     "span": "sentence 9", "reason": "the report has 3 sentences"})

    def test_each_difference_is_named_and_sorted_by_kind(self):
        code, shown = self.run_tool("defects")
        self.assertEqual(code, 0)
        self.assertIn("-3-d0: dropped '»'", shown)
        self.assertIn("-3-d1: dropped '**'", shown)
        self.assertIn("-3-d2: 'corrijo' became 'correcciones'", shown)
        self.assertIn("-3-d3: sentence 9, but the report has 3 sentences", shown)
        self.assertIn("4 defects; differences by kind:", shown)
        for kind in ("quotes 1", "markup 1", "words 1", "no such sentence 1"):
            self.assertIn(kind, shown)

    def test_spans_are_shown_only_when_asked_for(self):
        _, shown = self.run_tool("defects")
        self.assertNotIn("La regla va aquí.", shown)
        _, shown = self.run_tool("defects", "--spans")
        self.assertIn("La regla va aquí.", shown)


if __name__ == "__main__":
    unittest.main()
