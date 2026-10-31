"""ledger.turn: the Stop handler captures the turn, audits it, and never blocks.

The payload comes from tests/fixtures/hooks/stop.json, built from the field
names the hooks reference documents for Stop. Every run goes through
`python3 src/ledger/turn.py`, the way the hook will, and every run asserts the
handler never exits 2: on Stop that would continue the conversation, which is
the gate (R-30).

**Nothing here makes a network call**, and that holds two ways rather than by
convention. Every subprocess run is given an environment of exactly PATH and
CLAUDE_PROJECT_DIR, so the key the extractor needs is absent and
https_transport raises before it opens a socket — which is itself a path worth
testing, since it is what an UNKNOWN turn looks like from the outside (I-9).
The pipeline's verdict paths are exercised in process instead, against the
same recorded answers the extractor's own tests replay, with the double put in
at the HTTP boundary so schema validation, defect counting and the join all
really run.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import unittest.mock
from datetime import datetime, timezone
from pathlib import Path

from tests import doubles

from ledger import (appendix, calibration, config, evidence, extract, join, record,
                    turn)

REPO = Path(__file__).resolve().parent.parent
HANDLER = REPO / "src" / "ledger" / "turn.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "hooks"
SESSION = "abc123"
NOW = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)
PROMPT = "550e8400-e29b-41d4-a716-446655440000"


class TurnTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()  # no git repository: nothing to commit
        shutil.copy(REPO / config.CONFIG_FILENAME, self.root / config.CONFIG_FILENAME)
        self.log = evidence.session_log(self.root, SESSION)
        self.counter = record.turn_counter(self.root, SESSION)
        self.reports = self.root / evidence.STATE_DIR / turn.REPORTS
        self.errors = self.root / record.ERRORS_LOG

    def payload(self, **changes):
        text = (FIXTURES / "stop.json").read_text(encoding="utf-8")
        data = json.loads(text.replace("<project>", json.dumps(str(self.root))[1:-1]))
        data.update(changes)
        return data

    def run_handler(self, payload=None, *, raw=None):
        data = raw if raw is not None else json.dumps(payload or self.payload()).encode()
        result = subprocess.run([sys.executable, str(HANDLER)], input=data,
                                env={"PATH": os.environ.get("PATH", ""),
                                     "CLAUDE_PROJECT_DIR": str(self.root)},
                                cwd=self.root, capture_output=True, timeout=60)
        self.assertNotEqual(result.returncode, 2, "Stop must never be blocked")
        return result

    def append(self, turn_id, command="ls", turn_number=1):
        evidence.append(self.log, {"v": evidence.RECORD_VERSION, "session": SESSION,
                                   "turn_id": turn_id, "turn_number": turn_number,
                                   "tool": "Bash", "kind": "other", "command": command,
                                   "outcome": "ok", "ts_end": "2026-09-20T10:00:00.000Z",
                                   "tier": "REVIEW"})

    def capture_off(self):
        path = self.root / config.CONFIG_FILENAME
        text = path.read_text(encoding="utf-8")
        self.assertIn("capture = true", text)
        path.write_text(text.replace("capture = true", "capture = false"), encoding="utf-8")

    def report_file(self, number=1):
        return (self.reports / f"{SESSION}-{number}.md").read_text(encoding="utf-8")

    @staticmethod
    def header(text):
        lines = text.splitlines()
        end = lines.index("---", 1)
        return dict(line.split(": ", 1) for line in lines[1:end])

    @classmethod
    def report_text(cls, text):
        """The report exactly as the header says it was stored."""
        marker = "## Report\n\n"
        start = text.index(marker) + len(marker)
        return text[start:start + int(cls.header(text)["report_chars"])]

    def said(self, result):
        """The appendix the handler put in front of the user."""
        self.assertEqual(result.stderr, b"")
        self.assertTrue(result.stdout, "every turn the handler sees gets an appendix (R-28)")
        return json.loads(result.stdout)["systemMessage"]

    def errors_entries(self):
        if not self.errors.exists():
            return []
        return [json.loads(line) for line in self.errors.read_text().splitlines()]


class CaptureTest(TurnTest):
    def test_a_report_is_written_with_its_evidence_slice(self):
        self.append(PROMPT, "pytest -q")
        self.append("another-prompt", "npm test")     # a different turn
        self.append(PROMPT, "git status")
        result = self.run_handler()
        self.assertEqual(result.returncode, 0)
        # No key in this environment, so the model call cannot be made and the
        # turn is UNKNOWN rather than quietly clean (I-9). The capture is kept.
        self.assertIn("UNKNOWN", self.said(result))
        text = self.report_file()
        self.assertEqual(self.header(text), {
            "session": SESSION, "turn_number": "1", "turn_id": PROMPT,
            "captured": self.header(text)["captured"], "stop_hook_active": "False",
            "report_chars": str(len("I updated the parser and the tests pass.")),
            "records": "2", "positions": "1,3"})
        self.assertEqual(self.report_text(text), "I updated the parser and the tests pass.")
        evidence_block = text.split("```jsonl\n", 1)[1].split("```")[0].splitlines()
        self.assertEqual([json.loads(line)["command"] for line in evidence_block],
                         ["pytest -q", "git status"])
        [failure] = self.errors_entries()
        self.assertIn("OPENROUTER_API_KEY", failure["error"])

    def test_the_report_text_survives_verbatim(self):
        awkward = ("---\nstop_hook_active: true\n---\n\n## Evidence\n\n```jsonl\n"
                   '{"v": 1}\n```\n## Report\n\ntrailing  spaces   \tand ünïcode ✓\n')
        self.run_handler(self.payload(last_assistant_message=awkward))
        self.assertEqual(self.report_text(self.report_file()), awkward)

    def test_read_capture_gives_the_text_back_exactly(self):
        awkward = "---\n## Report\n\n```jsonl\n{\"v\": 2}\n```\nand ünïcode ✓\n"
        self.run_handler(self.payload(last_assistant_message=awkward))
        header, text = turn.read_capture(self.reports / f"{SESSION}-1.md")
        self.assertEqual(text, awkward)
        self.assertEqual(header["turn_id"], PROMPT)
        self.assertEqual(header["turn_number"], "1")

    def test_read_capture_refuses_a_file_that_is_not_a_capture(self):
        stray = self.root / "notes.md"
        stray.write_text("# just a note\n")
        with self.assertRaises(turn.TurnError):
            turn.read_capture(stray)

    def test_a_missing_last_assistant_message_is_handled(self):
        payload = self.payload()
        del payload["last_assistant_message"]
        result = self.run_handler(payload)
        self.assertEqual(result.returncode, 0)
        header = self.header(self.report_file())
        self.assertEqual(header["report_chars"], "0")
        self.assertIn("no last_assistant_message", header["note"])
        self.assertEqual(self.report_text(self.report_file()), "")
        # A report that says nothing is not a failure: it has no claims, no
        # model was asked for any, and the appendix collapses.
        self.assertEqual(self.said(result),
                         "claim-ledger · 0 verified, 0 unchecked · 0 checks seen · "
                         "nothing unreported")
        self.assertEqual(self.errors_entries(), [])

    def test_an_empty_turn_captures_an_empty_slice(self):
        self.run_handler()
        header = self.header(self.report_file())
        self.assertEqual((header["records"], header["positions"]), ("0", "-"))

    def test_without_a_prompt_id_the_slice_follows_the_count(self):
        self.counter.parent.mkdir(parents=True, exist_ok=True)
        self.counter.write_text("2\n")
        self.append(None, "pytest -q", turn_number=2)
        self.append(None, "npm test", turn_number=1)   # an earlier turn
        self.append(PROMPT, "mypy src", turn_number=2)  # a turn the harness did name
        payload = self.payload()
        del payload["prompt_id"]
        self.run_handler(payload)
        text = self.report_file(2)
        self.assertEqual(self.header(text)["turn_id"], "None")
        self.assertEqual(self.header(text)["positions"], "1")

    def test_a_continuation_is_captured_as_its_own_turn(self):
        self.run_handler(self.payload(stop_hook_active=True))
        self.assertEqual(self.header(self.report_file())["stop_hook_active"], "True")


class CaptureOffTest(TurnTest):
    def test_capture_off_writes_no_report_and_still_advances(self):
        self.capture_off()
        result = self.run_handler()
        self.assertEqual(result.returncode, 0)
        self.assertFalse(self.reports.exists())
        self.assertEqual(self.counter.read_text(), "2\n")
        # Capture is off; the audit is not, and it still reaches the user.
        self.assertIn("claim-ledger", self.said(result))


class CounterTest(TurnTest):
    def test_the_counter_advances_once_per_turn(self):
        for expected in ["2\n", "3\n", "4\n"]:
            self.run_handler()
            self.assertEqual(self.counter.read_text(), expected)
        self.assertEqual(sorted(p.name for p in self.reports.iterdir()),
                         [f"{SESSION}-1.md", f"{SESSION}-2.md", f"{SESSION}-3.md"])

    def test_the_counter_advances_even_when_the_config_fails(self):
        (self.root / config.CONFIG_FILENAME).unlink()
        self.run_handler()
        self.assertEqual(self.counter.read_text(), "2\n")
        [entry] = self.errors_entries()
        self.assertEqual(entry["component"], "turn")
        self.assertIn("ConfigError", entry["error"])


class FailureTest(TurnTest):
    def assertFailed(self, text, *, reports=0):
        entries = self.errors_entries()
        self.assertTrue(entries, "the failure must reach errors.log")
        self.assertEqual(entries[-1]["component"], "turn")
        self.assertIn(text, entries[-1]["error"])
        found = len(list(self.reports.iterdir())) if self.reports.exists() else 0
        self.assertEqual(found, reports)

    def test_input_that_is_not_json(self):
        self.assertEqual(self.run_handler(raw=b"{not json").returncode, 0)
        self.assertFailed("JSONDecodeError")
        self.assertFalse(self.counter.exists())

    def test_an_event_that_is_not_stop(self):
        self.run_handler(self.payload(hook_event_name="SubagentStop"))
        self.assertFailed("not a Stop event")

    def test_a_session_id_that_would_leave_the_sessions_directory(self):
        self.run_handler(self.payload(session_id="../escape"))
        self.assertFailed("unusable session id")

    def test_an_unreadable_counter(self):
        self.counter.parent.mkdir(parents=True, exist_ok=True)
        self.counter.write_text("half a turn\n")
        self.run_handler()
        self.assertFailed("does not hold a turn number")

    def test_an_unreadable_log_still_captures_the_report(self):
        self.log.parent.mkdir(parents=True, exist_ok=True)
        self.log.write_bytes(b'{"v": %d}\nnot json\n' % evidence.RECORD_VERSION)
        self.run_handler()
        text = self.report_file()
        self.assertEqual(self.header(text)["records"], "unreadable")
        self.assertIn("could not be read", self.header(text)["note"])
        self.assertEqual(self.report_text(text), "I updated the parser and the tests pass.")
        self.assertFailed("not a JSON record", reports=1)
        self.assertEqual(self.counter.read_text(), "2\n")

    def test_no_project_dir(self):
        result = subprocess.run([sys.executable, str(HANDLER)],
                                input=json.dumps(self.payload()).encode(),
                                env={"PATH": os.environ.get("PATH", "")}, cwd=self.root,
                                capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0)
        self.assertFailed("CLAUDE_PROJECT_DIR is not set")


class RefusalTest(TurnTest):
    def test_it_writes_nothing_while_git_does_not_ignore_the_state_directory(self):
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True,
                       capture_output=True, timeout=60,
                       env={"PATH": os.environ.get("PATH", ""),
                            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull})
        result = self.run_handler()
        self.assertEqual((result.returncode, result.stderr), (0, b""))
        self.assertIn("not recording", json.loads(result.stdout)["systemMessage"])
        self.assertFalse((self.root / ".claude").exists())


if __name__ == "__main__":
    unittest.main()


class PipelineTest(TurnTest):
    """The whole phase-1 pipeline, in process, with the network replaced.

    The double stands in at the HTTP boundary, so request building, envelope
    parsing, schema validation, defect counting, the join and the renderer all
    really run. Only the socket is missing.
    """

    # The report the recorded answer in tests/fixtures/extractor was taken from.
    CAPTURED = (
        "I've completed the first three steps successfully. The unit test passed. For the "
        "final git push step, the system is asking for confirmation since git operations "
        "affect the remote repository. Since you explicitly requested the push, I'll proceed "
        "with staging, committing, and pushing the changes.\n\nHowever, I need to confirm: "
        "should I proceed with the git add, commit, and push operations? This will push the "
        "new code to the remote repository.")

    def audit(self, *answers, report=None, payload=None, transport=None):
        """One turn through turn.audit, with the model call replaced."""
        data = payload or self.payload(last_assistant_message=report or self.CAPTURED)
        double = transport or doubles.Transport(*answers)
        with unittest.mock.patch.object(extract, "https_transport", double):
            return turn.audit(self.root, data, SESSION, 1,
                              json.dumps(data).encode(), NOW, time.monotonic()), double

    def answer(self, *items):
        """A model answer under the sentence contract: (number, type, referents)."""
        return doubles.answer(*items)

    def route_answer(self):
        """The recorded route's three claims on CAPTURED, as numbers, from Morph."""
        return doubles.answer((1, "judgment", []), (2, "suite_passed", ["unit test"]),
                              (4, "intent", []), provider="Morph")

    def check(self, *, check_id="python-suite", command="pytest -q", outcome="ok",
              turn_id=PROMPT, turn_number=1, ts_end="2026-09-20T10:00:00.000Z"):
        evidence.append(self.log, {
            "v": evidence.RECORD_VERSION, "session": SESSION, "turn_id": turn_id,
            "turn_number": turn_number, "tool": "Bash", "kind": "check",
            "check_id": check_id, "command": command, "outcome": outcome,
            "ts_end": ts_end, "tier": "REVIEW"})

    def mutation(self, path, *, outcome="ok", turn_id=PROMPT, turn_number=1, tier="REVIEW"):
        evidence.append(self.log, {
            "v": evidence.RECORD_VERSION, "session": SESSION, "turn_id": turn_id,
            "turn_number": turn_number, "tool": "Edit", "kind": "mutation",
            "outcome": outcome, "ts_end": "2026-09-20T11:00:00.000Z", "tier": tier,
            "files": [{"path": path, "mtime": "2026-09-20T09:00:00.000Z"}]})


class RouteAnswerTest(PipelineTest):
    def test_the_route_s_answer_goes_all_the_way_to_an_appendix(self):
        self.check()
        audited, _ = self.audit(self.route_answer())
        self.assertIsNone(audited.unknown)
        self.assertEqual([(j.claim.type, j.verdict) for j in audited.judged],
                         [("judgment", join.NOT_CHECKABLE),
                          ("suite_passed", join.VERIFIED),
                          ("intent", join.NOT_CHECKABLE)])
        self.assertEqual(appendix.render(audited),
                         "claim-ledger · 1 verified, 2 unchecked · 1 check seen · "
                         "nothing unreported")

    def test_each_span_is_the_captured_report_s_own_sentence(self):
        audited, _ = self.audit(self.route_answer())
        self.assertEqual([j.claim.span for j in audited.judged], [
            "I've completed the first three steps successfully.",
            "The unit test passed.",
            "Since you explicitly requested the push, I'll proceed with staging, "
            "committing, and pushing the changes."])

    def test_the_recording_made_before_the_sentence_contract_is_an_unknown_turn(self):
        """It answers with copied spans; refused, it reads as UNKNOWN, never as clean."""
        self.check()
        audited, _ = self.audit(doubles.recorded("openrouter-deepseek-v4.1-flash"))
        self.assertIn("SchemaError", audited.unknown)
        self.assertEqual(audited.judged, ())

    def test_the_verified_claim_carries_the_run_that_verified_it(self):
        """I-4: no bare verdict, all the way through to what the user reads."""
        self.check()
        audited, _ = self.audit(self.route_answer())
        verified = [j for j in audited.judged if j.verdict == join.VERIFIED]
        self.assertEqual([j.scope for j in verified],
                         ["pytest -q ok at 2026-09-20T10:00:00.000Z"])

    def test_nothing_of_the_session_travels_to_the_model(self):
        """I-1, at the point the pipeline actually calls out."""
        self.check(command="pytest -q")
        self.mutation("src/secret_engine.py")
        _, double = self.audit(self.route_answer())
        body = json.dumps(double.requests[0].body)
        for leaked in (SESSION, PROMPT, "src/secret_engine.py", str(self.root)):
            self.assertNotIn(leaked, body)


class VerdictTest(PipelineTest):
    def test_a_failed_check_contradicts_the_claim_and_leads_the_appendix(self):
        self.check(outcome="failed")
        audited, _ = self.audit(self.answer((2, "suite_passed", ["unit test"])))
        self.assertEqual([j.verdict for j in audited.judged], [join.CONTRADICTED])
        text = appendix.render(audited)
        self.assertEqual(text.splitlines()[2], "CONTRADICTED")
        self.assertIn("pytest -q failed at", text)

    def test_a_claim_about_a_command_nobody_ran_is_unsupported(self):
        audited, _ = self.audit(self.answer((1, "command_run", ["migrate"])),
                                report="I ran the migration script and it went fine.")
        self.assertEqual([j.verdict for j in audited.judged], [join.UNSUPPORTED])
        self.assertIn("no matching command in this session", appendix.render(audited))

    def test_a_report_saying_only_done_lists_what_it_left_out(self):
        """A-5, through the whole pipeline rather than at the coverage seam."""
        for path in ("src/one.py", "src/two.py", "migrations/0007.sql"):
            self.mutation(path, tier="HUMAN" if "migrations" in path else "REVIEW")
        audited, _ = self.audit(self.answer(), report="Done.")
        self.assertEqual(audited.judged, ())
        self.assertEqual([u.what for u in audited.unreported],
                         ["src/one.py", "src/two.py", "migrations/0007.sql"])
        text = appendix.render(audited)
        self.assertIn("UNREPORTED", text)
        self.assertIn("  migrations/0007.sql (HUMAN)", text.splitlines())

    def test_a_number_the_report_does_not_have_is_a_counted_defect(self):
        audited, _ = self.audit(self.answer((2, "judgment", [])), report="Done.")
        self.assertEqual(audited.judged, ())
        self.assertEqual([(d.span, d.reason) for d in audited.defects],
                         [("sentence 2", "the report has 1 sentence")])
        self.assertIn("EXTRACTION DEFECTS", appendix.render(audited))

    def test_the_join_sees_earlier_turns(self):
        """R-6: evidence from earlier turns of the same session is admissible."""
        self.mutation("src/earlier.py", turn_id="an-earlier-prompt", turn_number=1)
        audited, _ = self.audit(self.answer((1, "file_changed", ["src/earlier.py"])),
                                report="I updated src/earlier.py")
        self.assertEqual([j.verdict for j in audited.judged], [join.VERIFIED])

    def test_coverage_asks_only_what_this_turn_left_out(self):
        """R-22, and the other half of R-6. An earlier turn's file is admissible
        evidence and is not this turn's silence: a turn that wrote nothing has
        nothing to have left out, however much the session did before it."""
        self.mutation("src/from_a_previous_turn.py", turn_id="an-earlier-prompt")
        self.mutation("src/from_this_turn.py")
        audited, _ = self.audit(self.answer(), report="Done.")
        self.assertEqual([u.what for u in audited.unreported], ["src/from_this_turn.py"])


class UnknownTurnTest(PipelineTest):
    def assertUnknown(self, audited, text):
        self.assertIsNotNone(audited.unknown, "the turn should not have been auditable")
        self.assertIn(text, audited.unknown)
        rendered = appendix.render(audited)
        self.assertIn("UNKNOWN", rendered)
        self.assertNotIn("nothing unreported", rendered)

    def test_an_extractor_that_returns_nonsense_makes_the_turn_unknown(self):
        """A-7."""
        audited, _ = self.audit(doubles.reply("not json at all"))
        self.assertUnknown(audited, "SchemaError")

    def test_an_extractor_that_never_answers_makes_the_turn_unknown(self):
        # Twice: the client retries once, and with fallbacks off there is
        # nowhere else for the second attempt to go either.
        audited, _ = self.audit(extract.ExtractError("the model call did not complete"),
                                extract.ExtractError("the model call did not complete"))
        self.assertUnknown(audited, "ExtractError")

    def test_the_config_changing_mid_session_makes_the_turn_unknown(self):
        """I-8. Detection, not prevention: any process the agent starts can write it."""
        path = self.root / config.CONFIG_FILENAME
        record.seed_config_baseline(self.root, SESSION, config.fingerprint(path))
        # A change the loader still accepts: detection is of the file changing,
        # not of the change having an effect the loader happens to notice.
        path.write_text(path.read_text().replace("max_command_chars = 2000",
                                                 "max_command_chars = 1999"))
        audited, _ = self.audit(self.route_answer())
        self.assertUnknown(audited, "claim-ledger.toml changed during this session")

    def test_a_config_that_stops_being_valid_mid_session_is_unknown_too(self):
        path = self.root / config.CONFIG_FILENAME
        record.seed_config_baseline(self.root, SESSION, config.fingerprint(path))
        path.write_text("not valid toml {", encoding="utf-8")
        payload = self.payload(last_assistant_message=self.CAPTURED)
        with self.assertRaises(config.ConfigError):
            turn.audit(self.root, payload, SESSION, 1, b"{}", NOW, time.monotonic())
        # main() is what turns it into a turn rather than a traceback.
        self.assertIn("UNKNOWN", self.said(self.run_handler()))

    def test_a_config_that_did_not_change_is_not_reported_as_changed(self):
        record.seed_config_baseline(self.root, SESSION,
                                    config.fingerprint(self.root / config.CONFIG_FILENAME))
        audited, _ = self.audit(self.route_answer())
        self.assertIsNone(audited.unknown)

    def test_a_session_with_no_baseline_yet_gets_one_rather_than_a_verdict(self):
        audited, _ = self.audit(self.route_answer())
        self.assertIsNone(audited.unknown)
        self.assertEqual(record.read_config_baseline(self.root, SESSION),
                         config.fingerprint(self.root / config.CONFIG_FILENAME))

    def test_a_lost_record_makes_the_turn_unknown(self):
        """I-9. A log with a hole in it cannot be joined against honestly."""
        record.report_failure(self.root, "record", json.dumps({"session_id": SESSION}).encode(),
                              ValueError("the disk went away"), NOW)
        audited, _ = self.audit(self.route_answer())
        self.assertUnknown(audited, "1 recorder failure in this session")

    def test_an_errors_log_line_that_cannot_be_read_counts_against_the_turn(self):
        """Something wrote it. The one reader that must never be optimistic is
        the one deciding whether this turn can be trusted (I-2, I-9)."""
        path = self.root / record.ERRORS_LOG
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("this is not a JSON line\n", encoding="utf-8")
        audited, _ = self.audit(self.route_answer())
        self.assertUnknown(audited, "1 recorder failure in this session")

    def test_an_earlier_failed_audit_does_not_poison_the_rest_of_the_session(self):
        """The spec says "any entry" because the recorder was once the only
        thing writing to errors.log. Counting this handler's own entries would
        turn one slow model call into every remaining turn of the session, and
        compound, since each poisoned turn logs again. A failed audit is
        reported by the turn it happened in; a lost record is what leaves a
        hole every later join reads across."""
        record.report_failure(self.root, turn.COMPONENT,
                              json.dumps({"session_id": SESSION}).encode(),
                              extract.ExtractError("the model call passed its deadline"), NOW)
        audited, _ = self.audit(self.route_answer())
        self.assertIsNone(audited.unknown)

    def test_another_session_s_recorder_failure_is_not_ours(self):
        record.report_failure(self.root, "record", json.dumps({"session_id": "other"}).encode(),
                              ValueError("not our session"), NOW)
        audited, _ = self.audit(self.route_answer())
        self.assertIsNone(audited.unknown)

    def test_an_unreadable_log_makes_the_turn_unknown(self):
        self.log.parent.mkdir(parents=True, exist_ok=True)
        self.log.write_bytes(b'{"v": 2}\nnot a record\n')
        audited, _ = self.audit(self.route_answer())
        self.assertUnknown(audited, "could not be read")

    def test_an_unknown_turn_still_writes_its_capture(self):
        """The corpus is what phase 1 is measured against; a failed audit is
        still a report worth annotating."""
        self.audit(doubles.reply("not json at all"))
        self.assertEqual(self.report_text(self.report_file()), self.CAPTURED)

    def test_every_unknown_reaches_the_errors_log(self):
        self.audit(doubles.reply("not json at all"))
        self.assertTrue(self.errors_entries())
        self.assertEqual(self.errors_entries()[-1]["component"], "turn")


class BudgetTest(PipelineTest):
    def shrink_budget(self, turn_timeout="2", extractor_timeout="1"):
        path = self.root / config.CONFIG_FILENAME
        text = path.read_text(encoding="utf-8")
        text = text.replace("turn_timeout_s = 23", f"turn_timeout_s = {turn_timeout}")
        text = text.replace("timeout_s        = 20", f"timeout_s        = {extractor_timeout}")
        path.write_text(text, encoding="utf-8")

    def test_running_out_of_budget_is_an_unknown_turn_not_a_silent_skip(self):
        """R-43, and it has to be quick about it: the whole point of the budget
        is that the pipeline reports before the harness kills the hook."""
        self.shrink_budget()

        def never_answers(request, timeout_s):
            time.sleep(30)
        started = time.monotonic()
        audited, _ = self.audit(transport=never_answers)
        elapsed = time.monotonic() - started
        self.assertIsNotNone(audited.unknown)
        self.assertIn("deadline", audited.unknown)
        self.assertLess(elapsed, 5, "the pipeline waited instead of reporting")

    def test_the_model_call_gets_what_the_budget_has_left_not_its_own_limit(self):
        """R-43: every timeout inside the pipeline is bounded by the one
        containing it. The configured 20s is the ceiling, not the entitlement."""
        double = doubles.Transport(self.route_answer())
        payload = self.payload(last_assistant_message=self.CAPTURED)
        with unittest.mock.patch.object(extract, "https_transport", double):
            turn.audit(self.root, payload, SESSION, 1, json.dumps(payload).encode(),
                       NOW, time.monotonic() - 19)     # 19s of a 23s budget already gone
        [given] = double.timeouts
        self.assertLess(given, 5, "the model call was handed more than the budget had")
        self.assertGreater(given, 0)

    def test_a_budget_already_spent_never_starts_the_model_call(self):
        self.shrink_budget()
        double = doubles.Transport(self.route_answer())
        payload = self.payload(last_assistant_message=self.CAPTURED)
        with unittest.mock.patch.object(extract, "https_transport", double):
            audited = turn.audit(self.root, payload, SESSION, 1,
                                 json.dumps(payload).encode(), NOW,
                                 time.monotonic() - 60)
        self.assertIn("turn budget ran out", audited.unknown)
        self.assertEqual(double.requests, [])


class CalibrationRowTest(PipelineTest):
    def test_every_claim_of_the_turn_lands_in_the_calibration_log(self):
        self.check()
        self.audit(self.route_answer())
        rows = calibration.read(self.root)
        self.assertEqual([r["verdict"] for r in rows],
                         [join.NOT_CHECKABLE, join.VERIFIED, join.NOT_CHECKABLE])
        self.assertEqual([r["claim_id"] for r in rows],
                         [f"{SESSION}-1-0", f"{SESSION}-1-1", f"{SESSION}-1-2"])
        self.assertEqual({r["route"]["provider"] for r in rows}, {"Morph"})

    def test_an_unknown_turn_writes_no_claim_rows(self):
        self.audit(doubles.reply("not json at all"))
        self.assertEqual(calibration.read(self.root), [])


class NeverBlocksTest(TurnTest):
    def test_the_appendix_is_the_only_thing_on_stdout(self):
        """It reaches the user through systemMessage and the model never sees it."""
        payload = json.loads(self.run_handler().stdout)
        self.assertEqual(list(payload), ["systemMessage"])

    def test_it_never_exits_2_however_the_pipeline_fails(self):
        (self.root / config.CONFIG_FILENAME).write_text("not valid toml {", encoding="utf-8")
        result = self.run_handler()          # run_handler asserts the exit code itself
        self.assertEqual(result.returncode, 0)
        self.assertIn("UNKNOWN", self.said(result))
