"""ledger.turn: the Stop handler captures the turn's report and advances the counter.

The payload comes from tests/fixtures/hooks/stop.json, built from the field
names the hooks reference documents for Stop. Every run goes through
`python3 src/ledger/turn.py`, the way the hook will, and every run asserts the
handler never exits 2: on Stop that would continue the conversation, which is
the gate (R-30). Nothing here makes a network call.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ledger import config, evidence, record, turn

REPO = Path(__file__).resolve().parent.parent
HANDLER = REPO / "src" / "ledger" / "turn.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "hooks"
SESSION = "abc123"
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
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""))
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
        self.assertEqual(self.errors_entries(), [])

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
        self.assertEqual((result.returncode, result.stdout), (0, b""))
        header = self.header(self.report_file())
        self.assertEqual(header["report_chars"], "0")
        self.assertIn("no last_assistant_message", header["note"])
        self.assertEqual(self.report_text(self.report_file()), "")
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
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""))
        self.assertFalse(self.reports.exists())
        self.assertEqual(self.counter.read_text(), "2\n")
        self.assertEqual(self.errors_entries(), [])


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
