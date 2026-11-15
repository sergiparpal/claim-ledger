"""tools/ship.py: the release copy moves only after every check, and a failure says where it is.

Each test builds its own repository, release copy and project in a temporary
folder, with git kept from the machine's config and from any repository a hook
runs in, as test_install does. The Claude Code CLI is the one thing replaced:
a double that answers `plugin list --json` from what the release copy holds
and records `plugin update`. Nothing here makes a network call.
"""

import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

from tests.test_install import GIT_ISOLATED, GIT_REPOSITORY_VARIABLES

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import ship  # noqa: E402

REAL_CLAUDE = ship.claude


class FakeClaude:
    """`claude plugin list --json` and `claude plugin update`, as the script calls them."""

    def __init__(self, release: Path, project: Path, version: str):
        self.release, self.project, self.version = release, project, version
        self.read_from, self.enabled, self.installed, self.update_exit = release, True, True, 0
        self.calls = []

    def __call__(self, project, *args):
        self.calls.append((Path(project), args))
        if args == ("plugin", "list", "--json"):
            entries = [{"id": ship.PLUGIN, "version": self.version, "scope": "local",
                        "enabled": self.enabled, "readFromFolder": str(self.read_from),
                        "folderVersion": self.folder_version(),
                        "projectPath": str(self.project)}] if self.installed else []
            return subprocess.CompletedProcess(args, 0, json.dumps(entries), "")
        if args == ("plugin", "update", ship.PLUGIN, "--scope", "local"):
            if self.update_exit == 0:
                self.version = self.folder_version()
            return subprocess.CompletedProcess(args, self.update_exit, "", "it broke")
        raise AssertionError(f"the script ran claude {args}")

    def folder_version(self):
        return json.loads((self.read_from / ship.MANIFEST).read_text())["version"]

    def updates(self):
        return [call for call in self.calls if call[1][:2] == ("plugin", "update")]


class ShipTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        isolated = unittest.mock.patch.dict(os.environ, GIT_ISOLATED)
        isolated.start()  # the machine's own git config must not decide these tests
        self.addCleanup(isolated.stop)
        for name in GIT_REPOSITORY_VARIABLES:
            os.environ.pop(name, None)  # nor the repository a hook runs in; stop() restores them
        self.repo, self.release = self.tmp / "repo", self.tmp / "release"
        self.project, self.config_dir = self.tmp / "project", self.tmp / "config"
        self.project.mkdir()
        self.git(self.tmp, "init", "-q", str(self.repo))
        self.shipped = self.commit_version("0.3.4")
        self.git(self.tmp, "clone", "-q", str(self.repo), str(self.release))
        self.git(self.release, "checkout", "-q", "--detach", self.shipped)
        self.raised = self.commit_version("0.3.5")
        self.cli = FakeClaude(self.release, self.project, "0.3.4")
        for name, value in (("claude", self.cli), ("REPO", self.repo)):
            patcher = unittest.mock.patch.object(ship, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def git(self, where, *args):
        return subprocess.run(["git", "-C", str(where), *args], check=True, capture_output=True,
                              text=True, timeout=60).stdout.strip()

    def commit_version(self, version):
        manifest = self.repo / ship.MANIFEST
        manifest.parent.mkdir(exist_ok=True)
        manifest.write_text(json.dumps({"name": "claim-ledger", "version": version}) + "\n")
        self.git(self.repo, "add", ship.MANIFEST)
        self.git(self.repo, "-c", "user.name=t", "-c", "user.email=t@example.com",
                 "commit", "-q", "--allow-empty", "-m", f"make it {version}")
        return self.git(self.repo, "rev-parse", "HEAD")

    def run_ship(self, commit, *flags, answer="yes", while_asked=lambda: None):
        argv = [commit, "--project", str(self.project), "--release", str(self.release),
                "--config-dir", str(self.config_dir), *flags]

        def ask(prompt):
            while_asked()  # whatever happens while the person reads the question
            return answer

        out = io.StringIO()
        with contextlib.redirect_stdout(out), \
                unittest.mock.patch("builtins.input", side_effect=ask):
            code = ship.main(argv)
        return code, out.getvalue()

    def head(self):
        return self.git(self.release, "rev-parse", "HEAD")

    def transcript(self, session="22e46465-8757-4a49-84b9-8db95e0d5392", ago=0):
        """A transcript of the project, where Claude Code keeps it, written `ago` seconds back."""
        folder = self.config_dir / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(self.project))
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{session}.jsonl"
        path.write_text("{}\n")
        written = time.time_ns() - ago * 10**9
        os.utime(path, ns=(written, written))
        return path

    def assertNothingMoved(self, code, out, says):
        self.assertEqual(code, 1, out)
        self.assertIn(says, out)
        self.assertEqual(self.head(), self.shipped)
        self.assertEqual(self.cli.updates(), [])


class ShipsTest(ShipTest):
    def test_a_raised_version_ships_and_is_checked_afterwards(self):
        code, out = self.run_ship(self.raised)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.head(), self.raised)
        self.assertEqual(self.cli.version, "0.3.5")
        self.assertEqual(self.cli.updates(),
                         [(self.project, ("plugin", "update", ship.PLUGIN, "--scope", "local"))])
        self.assertIn("the install reports 0.3.5", out)

    def test_a_copy_already_at_the_commit_only_finishes_the_update(self):
        self.git(self.release, "fetch", "-q")
        self.git(self.release, "checkout", "-q", "--detach", self.raised)  # an update left undone
        code, out = self.run_ship(self.raised, "--yes")
        self.assertEqual(code, 0, out)
        self.assertEqual((len(self.cli.updates()), self.cli.version), (1, "0.3.5"))

    def test_a_ship_already_done_does_nothing(self):
        self.git(self.release, "fetch", "-q")
        self.git(self.release, "checkout", "-q", "--detach", self.raised)
        self.cli.version = "0.3.5"
        code, out = self.run_ship(self.raised, "--yes")
        self.assertEqual(code, 0, out)
        self.assertIn("already shipped", out)
        self.assertEqual(self.cli.updates(), [])

    def test_a_hooks_repository_does_not_turn_the_script_to_it(self):
        os.environ["GIT_DIR"] = str(self.repo / ".git")  # what a pre-commit hook would pass on
        code, out = self.run_ship(self.raised, "--yes")
        self.assertEqual(code, 0, out)
        del os.environ["GIT_DIR"]
        self.assertEqual(self.head(), self.raised)


class NothingMovesTest(ShipTest):
    """Every refusal before the ship leaves the copy where it was and runs no update."""

    def test_anything_but_yes_ships_nothing(self):
        for answer in ("no", "", "sí"):
            with self.subTest(answer=answer):
                self.assertNothingMoved(*self.run_ship(self.raised, answer=answer),
                                        says="not shipped: nothing moved")

    def test_a_dry_run_ships_nothing(self):
        code, out = self.run_ship(self.raised, "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("dry run: nothing moved", out)
        self.assertEqual((self.head(), self.cli.updates()), (self.shipped, []))

    def test_a_version_not_raised_is_refused(self):
        for version in ("0.3.4", "0.3.3", "0.2.10"):
            with self.subTest(version=version):
                self.assertNothingMoved(*self.run_ship(self.commit_version(version), "--yes"),
                                        says=f"names {version}, not above the 0.3.4")

    def test_a_commit_this_repository_does_not_have_is_refused(self):
        self.assertNothingMoved(*self.run_ship("0123456789abcdef", "--yes"),
                                says="0123456789abcdef is not a commit of")

    def test_a_release_copy_with_changes_is_refused(self):
        (self.release / "stray.txt").write_text("x\n")
        self.assertNothingMoved(*self.run_ship(self.raised, "--yes"), says="has changes")

    def test_a_project_without_the_install_is_refused(self):
        self.cli.installed = False
        self.assertNothingMoved(*self.run_ship(self.raised, "--yes"),
                                says="is not installed at local scope")

    def test_an_install_that_reads_another_folder_is_refused(self):
        self.cli.read_from = self.repo
        self.assertNothingMoved(*self.run_ship(self.raised, "--yes"), says="not the release copy")

    def test_a_disabled_install_is_refused(self):
        self.cli.enabled = False
        self.assertNothingMoved(*self.run_ship(self.raised, "--yes"), says="but not enabled")


class FailureTest(ShipTest):
    def test_a_failed_update_says_where_the_copy_was_left_and_how_to_put_it_back(self):
        self.cli.update_exit = 1
        code, out = self.run_ship(self.raised, "--yes")
        self.assertEqual(code, 1, out)
        self.assertEqual(self.head(), self.raised)  # the checkout is the ship, and it happened
        self.assertIn("claude plugin update exited 1: it broke", out)
        self.assertIn(f"checkout --detach {self.shipped}", out)


class HintTest(ShipTest):
    def test_the_projects_last_transcript_is_shown(self):
        self.transcript()
        code, out = self.run_ship(self.raised, "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("22e46465 wrote its transcript less than a minute ago", out)

    def test_the_newest_of_several_transcripts_is_the_one_named(self):
        self.transcript("0f1e2d3c-4b5a-4978-8a9b-0c1d2e3f4a5b", ago=3 * 3600)
        self.transcript(ago=5 * 60)
        self.assertIn("22e46465 wrote its transcript 5 minutes ago",
                      self.run_ship(self.raised, "--dry-run")[1])

    def test_a_project_with_no_transcript_says_so(self):
        self.assertIn("no transcript of the project in", self.run_ship(self.raised, "--dry-run")[1])


class WhileAskedTest(ShipTest):
    """A transcript written while the question is open means a session of the project is running."""

    def test_a_transcript_written_while_asked_stops_the_ship(self):
        path = self.transcript(ago=3600)
        self.assertNothingMoved(*self.run_ship(self.raised, while_asked=lambda: os.utime(path)),
                                says="22e46465 wrote its transcript while the question was open")

    def test_a_session_begun_while_asked_stops_the_ship(self):
        self.transcript(ago=3600)
        code, out = self.run_ship(self.raised, while_asked=lambda: self.transcript(
            "0f1e2d3c-4b5a-4978-8a9b-0c1d2e3f4a5b", ago=3600))
        self.assertNothingMoved(code, out,
                                says="0f1e2d3c wrote its transcript while the question was open")

    def test_transcripts_left_alone_while_asked_let_it_ship(self):
        self.transcript(ago=3600)
        code, out = self.run_ship(self.raised)
        self.assertEqual(code, 0, out)
        self.assertEqual(self.head(), self.raised)


class EnvironmentTest(unittest.TestCase):
    def test_the_cli_runs_from_the_project_without_a_sessions_variables(self):
        session = {"CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "claude-desktop",
                   "ANTHROPIC_API_KEY": "k", "CLAUDE_CONFIG_DIR": "/elsewhere/.claude"}
        with unittest.mock.patch.dict(os.environ, session), \
                unittest.mock.patch.object(subprocess, "run") as run:
            REAL_CLAUDE(Path("/a/project"), "plugin", "list", "--json")
        environment, cwd = run.call_args.kwargs["env"], run.call_args.kwargs["cwd"]
        self.assertEqual(cwd, Path("/a/project"))
        self.assertEqual(environment["CLAUDE_CONFIG_DIR"], "/elsewhere/.claude")
        for name in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "ANTHROPIC_API_KEY"):
            self.assertNotIn(name, environment)

    def test_the_repository_variables_are_the_ones_git_names(self):
        named = subprocess.run(["git", "rev-parse", "--local-env-vars"], capture_output=True,
                               text=True, timeout=60, cwd=tempfile.gettempdir()).stdout.split()
        self.assertTrue(named)
        self.assertLessEqual(set(named), set(ship.GIT_REPOSITORY_VARIABLES))
