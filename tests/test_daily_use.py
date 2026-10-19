"""tools/daily_use.py: reading back daily use without misreading it.

What is tested is what would turn a read-back into a wrong finding: a refused
call counted as a hole in the log or a real hole missed, a resumed session's
inherited calls counted as holes, a transcript line lost to a character that
splitlines() breaks on, a turn's ending misread or paired with the next turn's
hook, a verdict candidate missed, and a span shown to someone who did not ask
for spans. Every project and transcript here is built in a temporary folder.
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
