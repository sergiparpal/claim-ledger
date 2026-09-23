"""ledger.record and ledger.evidence: one hook event in, one evidence record out.

Payloads come from tests/fixtures/hooks/, built from the field names verified
against the hooks reference and the installed CLI's tool schemas. Their paths
use a "<project>" placeholder, replaced here by a temporary project holding the
committed claim-ledger.toml. Each <name>.expected.json is the exact record its
payload must produce, with ts_end fixed at 2026-09-19T14:32:07.880Z and the
project files' mtimes set to 2026-09-19T14:35:12.004Z. Most tests run the
recorder the way the hook will, as `python3 src/ledger/record.py` with the
payload on stdin. Nothing here makes a network call.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ledger import config, evidence, install, record

REPO = Path(__file__).resolve().parent.parent
RECORDER = REPO / "src" / "ledger" / "record.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "hooks"
SESSION = "abc123"
PROMPT = "550e8400-e29b-41d4-a716-446655440000"
FIXED_END = datetime(2026, 9, 19, 14, 32, 7, 880000, tzinfo=timezone.utc)
FIXED_MTIME_NS = (int(datetime(2026, 9, 19, 14, 35, 12, tzinfo=timezone.utc).timestamp())
                  * 1_000_000_000 + 4_000_000)
TOOL_EVENTS = ["post_tool_use_bash", "post_tool_use_failure_bash",
               "post_tool_use_bash_background", "post_tool_use_write",
               "post_tool_use_edit", "post_tool_use_notebook_edit"]
PROJECT_FILES = ["src/engine.py", "migrations/0007_add_index.sql", "docs/analysis.ipynb"]
ISO_MS = "%Y-%m-%dT%H:%M:%S.%fZ"


class RecorderTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        shutil.copy(REPO / config.CONFIG_FILENAME, self.root / config.CONFIG_FILENAME)
        (self.root / ".gitignore").write_text(install.GITIGNORE_LINE + "\n")
        for rel in PROJECT_FILES:
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x\n")
            os.utime(path, ns=(FIXED_MTIME_NS, FIXED_MTIME_NS))
        self.log = evidence.session_log(self.root, SESSION)
        self.errors = self.root / record.ERRORS_LOG

    def payload(self, name, **changes):
        text = (FIXTURES / f"{name}.json").read_text(encoding="utf-8")
        data = json.loads(text.replace("<project>", json.dumps(str(self.root))[1:-1]))
        data.update(changes)
        return data

    @staticmethod
    def expected(name):
        return json.loads((FIXTURES / f"{name}.expected.json").read_text(encoding="utf-8"))

    def build(self, payload):
        cfg = config.load(self.root / config.CONFIG_FILENAME)
        turn_id, turn_number = record.turn_ids(payload, self.root)
        return record.build(payload, cfg, self.root, turn_id=turn_id,
                            turn_number=turn_number, ts_end=FIXED_END)

    def run_recorder(self, payload=None, *, raw=None, env=None, project_dir=True):
        """Run the hook script; it must exit 0 and print nothing, whatever happens."""
        environment = {"PATH": os.environ.get("PATH", "")}
        if project_dir:
            environment["CLAUDE_PROJECT_DIR"] = str(self.root)
        environment.update(env or {})
        data = raw if raw is not None else json.dumps(payload).encode()
        result = subprocess.run([sys.executable, str(RECORDER)], input=data, env=environment,
                                cwd=self.root, capture_output=True, timeout=60)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""))

    def records(self):
        """The records of the session log, in file order."""
        return [entry.record for entry in evidence.read(self.log)]

    def error_entries(self):
        if not self.errors.exists():
            return []
        return [json.loads(line) for line in self.errors.read_text(encoding="utf-8").splitlines()]

    def state_text(self):
        """Everything the ledger wrote under .claude/claim-ledger/, as one string."""
        state = self.root / evidence.STATE_DIR
        return "".join(p.read_text(encoding="utf-8")
                       for p in sorted(state.rglob("*")) if p.is_file())


class FixtureRecordTest(RecorderTest):
    def test_fixtures_produce_the_exact_records(self):
        for name in TOOL_EVENTS:
            with self.subTest(name):
                self.assertEqual(self.build(self.payload(name)), self.expected(name))

    def test_one_record_per_event_through_the_hook(self):
        for count, name in enumerate(TOOL_EVENTS, 1):
            with self.subTest(name):
                before = datetime.now(timezone.utc).replace(microsecond=0)
                self.run_recorder(self.payload(name))
                after = datetime.now(timezone.utc)
                records = self.records()
                self.assertEqual(len(records), count)
                written, expected = records[-1], self.expected(name)
                ts_end = datetime.strptime(written.pop("ts_end"), ISO_MS)
                self.assertTrue(before <= ts_end.replace(tzinfo=timezone.utc) <= after)
                expected.pop("ts_end")
                self.assertEqual(written, expected)
        self.assertEqual(self.error_entries(), [])


class FailingBashTest(RecorderTest):
    def test_failing_bash_lands_as_failed_with_its_detail(self):
        self.run_recorder(self.payload("post_tool_use_failure_bash"))
        [written] = self.records()
        self.assertEqual((written["outcome"], written["outcome_detail"]), ("failed", "Exit code 1"))
        # The rest of the error string is the command's output (R-7).
        self.assertNotIn("Cannot find module", self.state_text())

    def test_the_detail_is_never_parsed(self):
        payload = self.payload("post_tool_use_failure_bash", error="Exit code 0\nall fine")
        self.assertEqual((self.build(payload)["outcome"], self.build(payload)["outcome_detail"]),
                         ("failed", "Exit code 0"))

    def test_a_failure_without_an_error_string_is_still_failed(self):
        payload = self.payload("post_tool_use_failure_bash")
        del payload["error"]
        built = self.build(payload)
        self.assertEqual(built["outcome"], "failed")
        self.assertNotIn("outcome_detail", built)


class CommandTruncationTest(RecorderTest):
    def bash(self, command):
        payload = self.payload("post_tool_use_bash")
        payload["tool_input"]["command"] = command
        self.run_recorder(payload)
        return self.records()[-1]

    def test_a_heredoc_is_cut_at_its_first_newline(self):
        written = self.bash("cat > notes.txt <<'EOF'\nHEREDOC-BODY-SENTINEL\nEOF")
        self.assertEqual(written["command"], "cat > notes.txt <<'EOF'")
        self.assertNotIn("HEREDOC-BODY-SENTINEL", self.state_text())

    def test_multiline_commands_keep_their_first_line(self):
        for command, stored in [("echo one\necho two", "echo one"),
                                ("echo one\r\necho two", "echo one"),
                                ("echo one\recho two", "echo one"),
                                ("\necho two", "")]:
            with self.subTest(command=command):
                self.assertEqual(self.bash(command)["command"], stored)

    def test_long_commands_are_cut_at_max_command_chars(self):
        command = "echo " + "x" * 5000
        self.assertEqual(self.bash(command)["command"], command[:2000])

    def test_check_and_tier_see_the_whole_command(self):
        written = self.bash("echo ok\ngit push origin main")
        self.assertEqual((written["command"], written["kind"], written["tier"]),
                         ("echo ok", "other", "HUMAN"))
        written = self.bash("pytest -q\n")
        self.assertEqual((written["command"], written["kind"]), ("pytest -q", "check"))


class AssignmentMaskTest(RecorderTest):
    def test_leading_assignment_values_are_masked(self):
        cases = [
            ("API_KEY=sk-123 curl https://x", "API_KEY=<redacted> curl https://x"),
            ("A=1 B=2 make", "A=<redacted> B=<redacted> make"),
            ('TOKEN="a b c" deploy --prod', "TOKEN=<redacted> deploy --prod"),
            ("TOKEN='x y' deploy", "TOKEN=<redacted> deploy"),
            ("TOKEN=$(cat ~/.t) deploy", "TOKEN=<redacted> deploy"),
            ("TOKEN=`cat t` deploy", "TOKEN=<redacted> deploy"),
            ("TOKEN=a\\ b deploy", "TOKEN=<redacted> deploy"),
            ("PATH+=:/opt/bin tool", "PATH+=<redacted> tool"),
            ("ARR=(a b) cmd", "ARR=<redacted> cmd"),
            ("  X=1\tcmd", "  X=<redacted>\tcmd"),
            ("X= cmd", "X=<redacted> cmd"),
            ("X=1", "X=<redacted>"),
            ("X=1;echo hi", "X=<redacted>;echo hi"),
            ('X="never closed cmd', "X=<redacted>"),
        ]
        for command, masked in cases:
            with self.subTest(command=command):
                self.assertEqual(record.mask_assignments(command), masked)

    def test_the_known_limits_are_stored_as_written(self):
        for command in ["deploy --token=s3cr3t", "export TOKEN=s3cr3t", "env TOKEN=s3cr3t deploy",
                        "cd app && TOKEN=s3cr3t deploy", "1X=2 cmd", "pytest -q"]:
            with self.subTest(command=command):
                self.assertEqual(record.mask_assignments(command), command)

    def test_the_hook_stores_the_masked_first_line_and_tiers_the_whole_command(self):
        payload = self.payload("post_tool_use_bash")
        payload["tool_input"]["command"] = ('DEPLOY_TOKEN="ASSIGN-SENTINEL\nsecond" '
                                            "git push origin main\nnext line")
        self.run_recorder(payload)
        [written] = self.records()
        self.assertEqual(written["command"], "DEPLOY_TOKEN=<redacted> git push origin main")
        self.assertEqual(written["tier"], "HUMAN")
        self.assertNotIn("ASSIGN-SENTINEL", self.state_text())


class NoLeakTest(RecorderTest):
    SECRETS = {"CLAIM_LEDGER_TEST_TOKEN": "ENV-SENTINEL-4f1c",
               "ANTHROPIC_API_KEY": "sk-ant-ENV-SENTINEL-9b2e"}

    def test_no_environment_variable_reaches_the_log(self):
        for name in TOOL_EVENTS:
            self.run_recorder(self.payload(name), env=self.SECRETS)
        self.run_recorder(raw=b"not json", env=self.SECRETS)  # errors.log too
        self.assertEqual(len(self.records()), len(TOOL_EVENTS))
        self.assertEqual(len(self.error_entries()), 1)
        text = self.state_text()
        for name, value in [*self.SECRETS.items(), ("PATH", os.environ.get("PATH", ""))]:
            with self.subTest(name):
                self.assertNotIn(value, text)
                self.assertNotIn(name, text)

    def test_no_file_content_or_tool_output_reaches_the_log(self):
        for name in TOOL_EVENTS:
            self.run_recorder(self.payload(name))
        # Write content, Edit strings, originalFile, notebook sources and Bash stdout.
        self.assertNotIn("SENTINEL", self.state_text())


class RecorderFailureTest(RecorderTest):
    def assertFailure(self, text):
        """One errors.log entry naming the failure, and no record written."""
        self.assertFalse(self.log.exists())
        [entry] = self.error_entries()
        self.assertEqual(entry["component"], "record")
        self.assertIn(text, entry["error"])
        return entry

    def test_a_config_error_writes_errors_log_and_exits_0(self):
        path = self.root / config.CONFIG_FILENAME
        text = path.read_text(encoding="utf-8")
        self.assertIn("[log]\nmax_command_chars = 2000\n", text)
        path.write_text(text.replace("[log]\nmax_command_chars = 2000\n", ""), encoding="utf-8")
        self.run_recorder(self.payload("post_tool_use_bash"))
        entry = self.assertFailure("ConfigError")
        self.assertIn("log: missing required table", entry["error"])
        self.assertEqual((entry["session"], entry["turn_id"], entry["turn_number"],
                          entry["tool_use_id"]), (SESSION, PROMPT, 1, "toolu_01BASH"))

    def test_a_missing_config_writes_errors_log(self):
        (self.root / config.CONFIG_FILENAME).unlink()
        self.run_recorder(self.payload("post_tool_use_bash"))
        self.assertFailure("file not found")

    def test_input_that_is_not_json(self):
        self.run_recorder(raw=b"{not json")
        entry = self.assertFailure("JSONDecodeError")
        self.assertIsNone(entry["session"])

    def test_a_stop_event_is_not_a_tool_event(self):
        self.run_recorder(self.payload("stop"))
        self.assertFailure("not a tool event")

    def test_a_session_id_that_would_leave_the_sessions_directory(self):
        self.run_recorder(self.payload("post_tool_use_bash", session_id="../escape"))
        self.assertFailure("unusable session id")
        self.assertEqual(list((self.root / evidence.STATE_DIR).glob("**/*.jsonl")), [])

    def test_a_relative_file_path(self):
        payload = self.payload("post_tool_use_edit")
        payload["tool_input"]["file_path"] = "migrations/0007_add_index.sql"
        self.run_recorder(payload)
        self.assertFailure("not an absolute path")

    def test_a_notebook_path_given_as_file_path(self):
        payload = self.payload("post_tool_use_notebook_edit")
        payload["tool_input"]["file_path"] = payload["tool_input"].pop("notebook_path")
        self.run_recorder(payload)
        self.assertFailure("tool_input has no notebook_path")

    def test_a_file_missing_after_a_successful_write(self):
        payload = self.payload("post_tool_use_write")
        payload["tool_input"]["file_path"] = str(self.root / "src" / "vanished.py")
        self.run_recorder(payload)
        self.assertFailure("FileNotFoundError")

    def test_an_unreadable_turn_counter(self):
        payload = self.payload("post_tool_use_bash")
        del payload["prompt_id"]
        counter = record.turn_counter(self.root, SESSION)
        counter.parent.mkdir(parents=True)
        counter.write_text("three\n")
        self.run_recorder(payload)
        self.assertFailure("does not hold a turn number")

    def test_no_project_dir_is_reported_where_the_hook_runs(self):
        self.run_recorder(self.payload("post_tool_use_bash"), project_dir=False)
        self.assertFailure("CLAUDE_PROJECT_DIR is not set")


class OutcomeTest(RecorderTest):
    def test_bash_that_did_not_run_to_its_end_is_unknown(self):
        variants = {
            "run_in_background": lambda p: p["tool_input"].update(run_in_background=True),
            "interrupted": lambda p: p["tool_response"].update(interrupted=True),
            "backgroundTaskId": lambda p: p["tool_response"].update(backgroundTaskId="bash_7"),
            "timedOutAfterMs": lambda p: p["tool_response"].update(timedOutAfterMs=120000),
            "backgroundedByUser": lambda p: p["tool_response"].update(backgroundedByUser=True),
            "no tool_response": lambda p: p.pop("tool_response"),
        }
        self.assertEqual(self.build(self.payload("post_tool_use_bash"))["outcome"], "ok")
        for label, change in variants.items():
            with self.subTest(label):
                payload = self.payload("post_tool_use_bash")
                change(payload)
                self.assertEqual(self.build(payload)["outcome"], "unknown")

    def test_outcome_comes_from_the_event_that_fired(self):
        for event, outcome in [("PostToolUse", "ok"), ("PostToolUseFailure", "failed"),
                               ("PreToolUse", "unknown"), (None, "unknown")]:
            with self.subTest(event=event):
                payload = self.payload("post_tool_use_write", hook_event_name=event)
                self.assertEqual(self.build(payload)["outcome"], outcome)

    def test_a_failed_write_to_a_missing_file_has_no_mtime(self):
        payload = self.payload("post_tool_use_write", hook_event_name="PostToolUseFailure",
                               error="EACCES: permission denied\nmore")
        payload["tool_input"]["file_path"] = str(self.root / "src" / "never_written.py")
        built = self.build(payload)
        self.assertEqual(built["files"], [{"path": "src/never_written.py", "mtime": None}])
        self.assertEqual(built["outcome_detail"], "EACCES: permission denied")


class TurnTest(RecorderTest):
    """turn_id is the harness's prompt id and nothing else; turn_number counts turns."""

    def test_the_prompt_id_is_the_turn_id(self):
        built = self.build(self.payload("post_tool_use_bash"))
        self.assertEqual((built["turn_id"], built["turn_number"]), (PROMPT, 1))

    def test_without_a_prompt_id_the_turn_id_is_null_and_the_count_still_runs(self):
        payload = self.payload("post_tool_use_bash")
        del payload["prompt_id"]
        for variant in [payload, {**payload, "prompt_id": ""}]:
            built = self.build(variant)
            self.assertEqual((built["turn_id"], built["turn_number"]), (None, 1))
        counter = record.turn_counter(self.root, SESSION)
        counter.parent.mkdir(parents=True)
        counter.write_text("3\n")
        built = self.build(payload)
        self.assertEqual((built["turn_id"], built["turn_number"]), (None, 3))

    def test_the_count_travels_with_a_prompt_id_too(self):
        counter = record.turn_counter(self.root, SESSION)
        counter.parent.mkdir(parents=True)
        counter.write_text("4\n")
        built = self.build(self.payload("post_tool_use_bash"))
        self.assertEqual((built["turn_id"], built["turn_number"]), (PROMPT, 4))


class PathTest(RecorderTest):
    def test_symlinks_resolve_to_the_project_path(self):
        link = self.root / "engine_link.py"
        link.symlink_to(self.root / "src" / "engine.py")
        payload = self.payload("post_tool_use_write")
        payload["tool_input"]["file_path"] = str(link)
        self.assertEqual(self.build(payload)["files"][0]["path"], "src/engine.py")

    def test_a_path_outside_the_project_stays_absolute_with_the_default_tier(self):
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        outside = Path(other.name).resolve() / "migrations" / "0001.sql"
        outside.parent.mkdir()
        outside.write_text("x\n")
        payload = self.payload("post_tool_use_edit")
        payload["tool_input"]["file_path"] = str(outside)
        built = self.build(payload)
        self.assertEqual(built["files"][0]["path"], outside.as_posix())
        self.assertEqual(built["tier"], "REVIEW")  # tier globs are project-relative


class ConcurrencyTest(RecorderTest):
    def test_parallel_recorders_each_append_one_whole_record(self):
        environment = {"PATH": os.environ.get("PATH", ""), "CLAUDE_PROJECT_DIR": str(self.root)}
        ids = [f"toolu_{i:02d}" for i in range(16)]
        procs = [subprocess.Popen([sys.executable, str(RECORDER)], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  env=environment, cwd=self.root) for _ in ids]
        for proc, tool_use_id in zip(procs, ids):  # every process is started before any input
            proc.stdin.write(json.dumps(self.payload("post_tool_use_bash",
                                                     tool_use_id=tool_use_id)).encode())
            proc.stdin.close()
        for proc in procs:
            self.assertEqual((proc.wait(timeout=60), proc.stdout.read(), proc.stderr.read()),
                             (0, b"", b""))
            proc.stdout.close()
            proc.stderr.close()
        self.assertEqual(sorted(r["tool_use_id"] for r in self.records()), ids)
        self.assertEqual(self.error_entries(), [])


class EvidenceReaderTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.log = evidence.session_log(Path(tmp.name), "s1")

    def test_records_come_back_in_file_order_with_their_positions(self):
        for n in range(3):
            evidence.append(self.log, {"v": evidence.RECORD_VERSION, "n": n,
                                       "note": "line\nbreak"})
        self.assertEqual(len(self.log.read_bytes().splitlines()), 3)
        entries = evidence.read(self.log)
        self.assertEqual([(e.position, e.record["n"]) for e in entries],
                         [(1, 0), (2, 1), (3, 2)])
        self.assertEqual(entries[0].record["note"], "line\nbreak")
        self.assertEqual(entries[0].raw,
                         '{"v": %d, "n": 0, "note": "line\\nbreak"}' % evidence.RECORD_VERSION)

    def test_no_log_means_no_records(self):
        self.assertEqual(evidence.read(self.log), [])

    def test_a_damaged_log_raises_instead_of_skipping(self):
        current = b'{"v": %d}' % evidence.RECORD_VERSION
        version = f"version {evidence.RECORD_VERSION}"
        for content, where in [(current + b"\n" + current[:-1], "no line end"),
                               (current + b"\nnot json\n", ":2:"),
                               (b'{"v": 1}\n', version),   # a log from the older schema
                               (b"[1]\n", version),
                               (b"\n", ":1:")]:
            with self.subTest(content=content):
                self.log.parent.mkdir(parents=True, exist_ok=True)
                self.log.write_bytes(content)
                with self.assertRaises(evidence.EvidenceError) as caught:
                    evidence.read(self.log)
                self.assertIn(where, str(caught.exception))

    def test_session_ids_cannot_leave_the_sessions_directory(self):
        for session in ["../x", "a/b", "", ".", None, 5]:
            with self.subTest(session=session), self.assertRaises(evidence.EvidenceError):
                evidence.session_log(Path("/p"), session)


if __name__ == "__main__":
    unittest.main()
