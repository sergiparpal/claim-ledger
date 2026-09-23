"""Installation: the deny rule, the .gitignore line and its refusal, the hook registration.

Everything runs against temporary projects: nothing here touches this
repository's own settings or .gitignore, and nothing makes a network call.
"""

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from ledger import config, evidence, install

REPO = Path(__file__).resolve().parent.parent
HOOKS = REPO / "hooks" / "hooks.json"
INSTALLER = REPO / "src" / "ledger" / "install.py"
FIXTURE = REPO / "tests" / "fixtures" / "hooks" / "post_tool_use_bash.json"
GIT_ISOLATED = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}


class ProjectTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        shutil.copy(REPO / config.CONFIG_FILENAME, self.root / config.CONFIG_FILENAME)
        isolated = unittest.mock.patch.dict(os.environ, GIT_ISOLATED)
        isolated.start()  # the machine's own git config must not decide these tests
        self.addCleanup(isolated.stop)

    def git_init(self, gitignore=None):
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True,
                       capture_output=True, timeout=60)
        if gitignore is not None:
            (self.root / ".gitignore").write_text(gitignore)

    def settings(self):
        return json.loads((self.root / install.SETTINGS).read_text(encoding="utf-8"))

    def run_installer(self):
        return subprocess.run([sys.executable, str(INSTALLER), str(self.root)],
                              capture_output=True, text=True, timeout=60)

    def run_registered_hook(self):
        """Run the recorder exactly as hooks.json registers it for PostToolUse."""
        handler = json.loads(HOOKS.read_text())["hooks"]["PostToolUse"][0]["hooks"][0]
        argv = [shutil.which(handler["command"])]
        argv += [arg.replace("${CLAUDE_PLUGIN_ROOT}", str(REPO)) for arg in handler["args"]]
        payload = FIXTURE.read_text().replace("<project>", json.dumps(str(self.root))[1:-1])
        environment = {"PATH": os.environ.get("PATH", ""), "CLAUDE_PROJECT_DIR": str(self.root),
                       "CLAUDE_PLUGIN_ROOT": str(REPO), **GIT_ISOLATED}
        return subprocess.run(argv, input=payload.encode(), env=environment, cwd=self.root,
                              capture_output=True, timeout=handler["timeout"])


class DenyRuleTest(ProjectTest):
    def test_install_writes_the_deny_rule(self):
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(install.DENY_RULE, self.settings()["permissions"]["deny"])

    def test_the_rule_names_the_config_file(self):
        self.assertEqual(install.DENY_RULE, f"Edit({config.CONFIG_FILENAME})")

    def test_existing_settings_are_kept_and_nothing_is_duplicated(self):
        existing = {"model": "m", "hooks": {},
                    "permissions": {"allow": ["Bash(ls)"], "deny": ["Read(.env)"]}}
        (self.root / ".claude").mkdir()
        (self.root / install.SETTINGS).write_text(json.dumps(existing))
        self.assertTrue(install.add_deny_rule(self.root))
        self.assertFalse(install.add_deny_rule(self.root))
        self.assertEqual(self.settings(), {
            "model": "m", "hooks": {},
            "permissions": {"allow": ["Bash(ls)"], "deny": ["Read(.env)", install.DENY_RULE]}})
        self.assertEqual(list((self.root / ".claude").iterdir()), [self.root / install.SETTINGS])

    def test_a_settings_file_it_cannot_merge_into_is_left_untouched(self):
        (self.root / ".claude").mkdir()
        path = self.root / install.SETTINGS
        for text in ["{not json", "[1, 2]", '{"permissions": []}',
                     '{"permissions": {"deny": "Edit(x)"}}']:
            with self.subTest(text=text):
                path.write_text(text)
                with self.assertRaises(install.InstallError):
                    install.add_deny_rule(self.root)
                self.assertEqual(path.read_text(), text)
        result = self.run_installer()
        self.assertEqual(result.returncode, 2)
        self.assertIn("left untouched", result.stderr)

    def test_a_config_that_does_not_load_is_reported_after_installing(self):
        (self.root / config.CONFIG_FILENAME).unlink()
        result = self.run_installer()
        self.assertEqual(result.returncode, 1)
        self.assertIn("does not load", result.stdout)
        self.assertIn(install.DENY_RULE, self.settings()["permissions"]["deny"])
        self.assertTrue(install.gitignore_has_line(self.root))


class GitignoreTest(ProjectTest):
    """git decides whether the ledger may write, not a search for one line."""

    def test_git_answers_for_each_kind_of_project(self):
        cases = [(".claude/claim-ledger/\n", install.IGNORED),   # the line the installer adds
                 (".claude/\n", install.IGNORED),                 # a project that ignores it all
                 (".claude/*\n", install.IGNORED),
                 ("", install.NOT_IGNORED),
                 ("# .claude/claim-ledger/\n", install.NOT_IGNORED),
                 ("  .claude/claim-ledger/\n", install.NOT_IGNORED)]
        for gitignore, state in cases:
            with self.subTest(gitignore=gitignore):
                shutil.rmtree(self.root / ".git", ignore_errors=True)
                self.git_init(gitignore)
                self.assertEqual(install.ignore_state(self.root), state)

    def test_outside_a_repository_there_is_nothing_to_commit(self):
        self.assertEqual(install.ignore_state(self.root), install.NO_GIT)
        self.assertTrue(install.state_is_ignored(self.root))

    def test_a_git_that_cannot_answer_inside_a_repository_is_not_a_pass(self):
        self.git_init()
        # git refuses check-ignore outside a work tree, but still reports a repository.
        self.assertEqual(install.ignore_state(self.root / ".git"), install.UNKNOWN)
        self.assertFalse(install.state_is_ignored(self.root / ".git"))

    def test_no_git_to_ask_means_nothing_can_be_committed(self):
        self.git_init()
        with unittest.mock.patch.dict(os.environ, {"PATH": ""}):
            self.assertEqual(install.ignore_state(self.root), install.NO_GIT)
            self.assertTrue(install.state_is_ignored(self.root))

    def test_install_adds_the_line_once(self):
        (self.root / ".gitignore").write_text("node_modules/")  # no final newline
        self.assertTrue(install.add_gitignore_line(self.root))
        self.assertFalse(install.add_gitignore_line(self.root))
        self.assertEqual((self.root / ".gitignore").read_text(),
                         "node_modules/\n.claude/claim-ledger/\n")

    def test_install_creates_a_missing_gitignore(self):
        self.git_init()
        self.assertEqual(self.run_installer().returncode, 0)
        self.assertEqual((self.root / ".gitignore").read_text(), ".claude/claim-ledger/\n")
        self.assertEqual(install.ignore_state(self.root), install.IGNORED)

    def test_install_leaves_a_project_that_already_ignores_it_alone(self):
        self.git_init(".claude/\n")
        result = self.run_installer()
        self.assertEqual(result.returncode, 0)
        self.assertIn("git already ignores", result.stdout)
        self.assertEqual((self.root / ".gitignore").read_text(), ".claude/\n")

    def test_the_refusal_fires_when_git_does_not_ignore_it(self):
        for gitignore in ["", "# .claude/claim-ledger/\n"]:
            with self.subTest(gitignore=gitignore):
                shutil.rmtree(self.root / ".git", ignore_errors=True)
                self.git_init(gitignore)
                result = self.run_registered_hook()
                self.assertEqual((result.returncode, result.stderr), (0, b""))
                message = json.loads(result.stdout)["systemMessage"]
                self.assertIn("claim-ledger is not recording", message)
                self.assertIn(install.NOT_IGNORED, message)
                self.assertFalse((self.root / ".claude").exists())  # nothing written at all

    def test_the_hook_records_where_git_ignores_the_directory(self):
        for gitignore in [".claude/claim-ledger/\n", ".claude/\n"]:
            with self.subTest(gitignore=gitignore):
                shutil.rmtree(self.root / ".git", ignore_errors=True)
                shutil.rmtree(self.root / ".claude", ignore_errors=True)
                self.git_init(gitignore)
                result = self.run_registered_hook()
                self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""))
                entries = evidence.read(evidence.session_log(self.root, "abc123"))
                self.assertEqual([(e.position, e.record["kind"], e.record["command"])
                                  for e in entries], [(1, "check", "pytest -q")])

    def test_the_hook_records_outside_a_repository(self):
        result = self.run_registered_hook()
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b"", b""))
        self.assertEqual(len(evidence.read(evidence.session_log(self.root, "abc123"))), 1)


class HookRegistrationTest(unittest.TestCase):
    def test_the_registration_parses_and_its_paths_resolve(self):
        script = {"PostToolUse": "record.py", "PostToolUseFailure": "record.py",
                  "Stop": "turn.py"}
        hooks = json.loads(HOOKS.read_text())
        self.assertEqual(sorted(hooks["hooks"]), sorted(script))
        for event, groups in hooks["hooks"].items():
            for group in groups:
                if event == "Stop":
                    self.assertNotIn("matcher", group)  # Stop matches on nothing
                else:
                    # Letters and '|' only: Claude Code reads it as exact tool names,
                    # not as an unanchored regular expression.
                    self.assertRegex(group["matcher"], r"^[A-Za-z|]+$")
                    self.assertEqual(group["matcher"].split("|"),
                                     ["Bash", "Edit", "Write", "NotebookEdit"])
                for handler in group["hooks"]:
                    with self.subTest(event=event):
                        self.assertEqual(handler["type"], "command")
                        self.assertIsNotNone(shutil.which(handler["command"]))
                        self.assertEqual(handler["timeout"], 15 if event == "Stop" else 5)
                        for arg in handler["args"]:
                            self.assertTrue(arg.startswith("${CLAUDE_PLUGIN_ROOT}/"), arg)
                            resolved = Path(arg.replace("${CLAUDE_PLUGIN_ROOT}", str(REPO)))
                            self.assertEqual(resolved, REPO / "src" / "ledger" / script[event])
                            self.assertTrue(resolved.is_file())

    def test_the_stop_handler_captures_and_does_not_audit_yet(self):
        stop = json.loads(HOOKS.read_text())["hooks"]["Stop"][0]["hooks"][0]
        self.assertIn("Capturing", stop["statusMessage"])
        tree = ast.parse((REPO / "src" / "ledger" / "turn.py").read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {alias.name.rsplit(".", 1)[-1] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported |= {alias.name for alias in node.names}
        self.assertEqual(imported & {"extract", "schema", "join", "coverage", "appendix",
                                     "calibration"}, set(), "the Stop handler only captures")

    def test_the_python3_the_hook_runs_is_new_enough(self):
        interpreter = shutil.which("python3")
        version = subprocess.run([interpreter, "-c", "import sys; print(*sys.version_info[:2])"],
                                 capture_output=True, text=True, timeout=60).stdout.split()
        self.assertGreaterEqual(tuple(map(int, version)), (3, 11), interpreter)


if __name__ == "__main__":
    unittest.main()
