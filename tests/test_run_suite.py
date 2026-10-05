"""tools/run_suite.py: the suite declares what it runs on.

A session that asks PATH and a session that asks uv get different answers about
the same machine, and this project cannot be the one reporting "it passed on
whatever I found". So the set is declared, and a version that is not there is a
named failure.

Nothing here runs the suite — that would be the suite running itself three
times per version. What is tested is the resolution and the refusal.
"""

import io
import subprocess
import sys
import unittest
import unittest.mock
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import run_suite  # noqa: E402


class DeclaredTest(unittest.TestCase):
    def test_the_set_is_declared_and_not_discovered(self):
        self.assertEqual(run_suite.DECLARED, tuple(sorted(set(run_suite.DECLARED),
                                                          key=_as_numbers)))
        self.assertTrue(run_suite.DECLARED)
        for version in run_suite.DECLARED:
            self.assertRegex(version, r"^3\.\d+$")

    def test_the_declared_set_is_at_or_above_the_floor_the_project_claims(self):
        """CLAUDE.md says Python 3.11+. Declaring something below it would mean
        the suite gates on a version the project does not support."""
        self.assertTrue(all(_as_numbers(v) >= (3, 11) for v in run_suite.DECLARED))

    def test_every_declared_version_resolves_on_this_machine(self):
        """The one test that is allowed to be about this machine: if it fails,
        the pre-commit hook is about to refuse for the same reason."""
        for version in run_suite.DECLARED:
            with self.subTest(version=version):
                path, source = run_suite.find(version)
                self.assertIsNotNone(path, f"{version} is declared and not installed")
                self.assertIn(source, ("system", "uv"))


class ResolutionTest(unittest.TestCase):
    def test_a_version_is_read_from_the_interpreter_not_from_its_name(self):
        running = "%d.%d" % sys.version_info[:2]
        self.assertEqual(run_suite.version_of(sys.executable), running)

    def test_an_interpreter_that_does_not_run_reports_no_version(self):
        """A file that is not executable, and a path that is not there at all.
        Both must report no version rather than raise: the runner's job is to
        name the missing version, not to die on the way to naming it."""
        self.assertIsNone(run_suite.version_of(str(REPO / "README.md")))
        self.assertIsNone(run_suite.version_of(str(REPO / "no-such-interpreter")))

    def test_a_broken_interpreter_makes_its_version_missing_not_present(self):
        with unittest.mock.patch.object(run_suite.shutil, "which",
                                        side_effect=lambda n: str(REPO / "README.md")
                                        if n == "python3.13" else None):
            self.assertEqual(run_suite.find("3.13"), (None, ""))

    def test_a_name_that_lies_about_its_version_is_not_accepted(self):
        """python3.13 on PATH that is really 3.12 must not answer for 3.13."""
        with unittest.mock.patch.object(run_suite, "version_of", return_value="3.12"), \
             unittest.mock.patch.object(run_suite.shutil, "which",
                                        side_effect=lambda name: "/fake/" + name):
            with unittest.mock.patch.object(run_suite.subprocess, "run") as ran:
                ran.return_value = subprocess.CompletedProcess([], 1, "", "no")
                self.assertEqual(run_suite.find("3.13"), (None, ""))

    def test_uv_is_asked_in_a_way_that_cannot_download(self):
        """A commit that quietly turns into a 30MB download is not a refusal."""
        source = (REPO / "tools" / "run_suite.py").read_text(encoding="utf-8")
        self.assertIn('"uv", "python", "find"', source)
        self.assertNotIn('"install"', source.split("def find")[1].split("def version_of")[0])


class RefusalTest(unittest.TestCase):
    def run_main(self, declared, argv=()):
        out = []
        with unittest.mock.patch.object(run_suite, "DECLARED", declared), \
             unittest.mock.patch("builtins.print", lambda *a, **k: out.append(" ".join(map(str, a)))):
            code = run_suite.main(list(argv))
        return code, "\n".join(out)

    def test_a_missing_version_fails_and_names_itself(self):
        code, said = self.run_main(("3.2",))       # long gone, never installed
        self.assertEqual(code, 1)
        self.assertIn("3.2", said)
        self.assertIn("MISSING", said)
        self.assertIn("uv python install 3.2", said)

    def test_it_refuses_rather_than_running_the_ones_it_has(self):
        """The failure this exists to prevent: a shorter run reported as a pass."""
        resolved = {v: ("/usr/bin/python" + v, "system") for v in run_suite.DECLARED}
        with unittest.mock.patch.object(run_suite, "find",
                                        lambda v: resolved.get(v, (None, ""))), \
             unittest.mock.patch.object(run_suite.subprocess, "run") as ran:
            code, said = self.run_main(("3.2", *run_suite.DECLARED))
            ran.assert_not_called()   # not one suite started
        self.assertEqual(code, 1)
        self.assertIn("refusing to run on", said)
        self.assertIn(f"{len(run_suite.DECLARED)} of {len(run_suite.DECLARED) + 1}", said)

    def run_against(self, *results):
        """main() with every declared version present and these suite results."""
        resolved = {v: ("/usr/bin/python" + v, "system") for v in run_suite.DECLARED}
        # main() dumps a failing run's own streams through sys.stdout/stderr.
        # Left alone, this test's fake unittest summary would land in the real
        # stderr of the real suite, and the runner above would quote it back.
        with unittest.mock.patch.object(run_suite, "find", lambda v: resolved[v]), \
             unittest.mock.patch.object(run_suite.subprocess, "run",
                                        side_effect=list(results)), \
             unittest.mock.patch.object(run_suite.sys, "stdout", io.StringIO()), \
             unittest.mock.patch.object(run_suite.sys, "stderr", io.StringIO()):
            return self.run_main(run_suite.DECLARED)

    @staticmethod
    def suite(returncode, ran=268):
        status = "OK" if returncode == 0 else "FAILED (failures=1)"
        return subprocess.CompletedProcess(
            [], returncode, "", f"...\n{'-' * 70}\nRan {ran} tests in 5.9s\n\n{status}\n")

    def test_a_failing_suite_is_a_failing_run(self):
        """The one thing this script exists to get right. Nothing runs the real
        suite here — that would be the suite running itself once per version."""
        results = [self.suite(0)] * (len(run_suite.DECLARED) - 1) + [self.suite(1)]
        code, said = self.run_against(*results)
        self.assertEqual(code, 1)
        self.assertIn(f"1 of {len(run_suite.DECLARED)} declared versions failed", said)
        self.assertIn(run_suite.DECLARED[-1], said)

    def test_every_version_runs_even_after_one_fails(self):
        """A later version's failure must not be hidden by an earlier one, so
        the run does not stop at the first."""
        results = [self.suite(1)] + [self.suite(0)] * (len(run_suite.DECLARED) - 2) \
            + [self.suite(1)]
        code, said = self.run_against(*results)
        self.assertEqual(code, 1)
        self.assertIn(f"2 of {len(run_suite.DECLARED)} declared versions failed", said)

    def test_the_count_comes_from_the_run_not_from_something_it_printed(self):
        """A suite whose own output holds a line looking like a summary must
        not have that line reported as its result."""
        decoy = subprocess.CompletedProcess(
            [], 0, "", "Ran 1 test in 0.001s\nOK\n"          # a test printed this
                       "..\n" + "-" * 70 + "\nRan 268 tests in 5.9s\n\nOK\n")
        code, said = self.run_against(*[decoy] * len(run_suite.DECLARED))
        self.assertEqual(code, 0)
        self.assertIn("Ran 268 tests", said)
        self.assertNotIn("Ran 1 test in", said)

    def test_all_passing_is_the_only_way_to_exit_zero(self):
        code, said = self.run_against(*[self.suite(0)] * len(run_suite.DECLARED))
        self.assertEqual(code, 0)
        self.assertIn(f"all {len(run_suite.DECLARED)} declared versions passed", said)
        self.assertIn("Ran 268 tests", said)

    def test_listing_a_missing_version_is_also_a_failure(self):
        code, said = self.run_main(("3.2",), ["--list"])
        self.assertEqual(code, 1)
        self.assertIn("MISSING", said)


class WiringTest(unittest.TestCase):
    """The hook and CI have to go through the script, or the declared set is a
    comment. Each of these fails if someone reaches past it to `unittest
    discover` for the convenience of a faster commit."""

    def test_the_pre_commit_hook_runs_the_declared_set(self):
        hook = (REPO / ".githooks" / "pre-commit").read_text(encoding="utf-8")
        self.assertIn("tools/run_suite.py", hook)
        self.assertNotIn("-m unittest discover", hook)

    def test_ci_runs_the_declared_set_and_reads_it_from_one_place(self):
        ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("python3 tools/run_suite.py", ci)
        self.assertIn("--versions", ci)   # the matrix is not written out twice

    def test_the_floor_the_project_claims_is_the_lowest_declared_version(self):
        """CLAUDE.md claims 3.11. Until 5 October 2026 it was left to a CI job,
        and this repository has no remote, so that job never ran and the claim
        rested on nothing. The floor belongs in the set the pre-commit hook
        runs, with nothing below it."""
        claimed = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
        floor = "3.11"
        self.assertIn(f"Python {floor}+", claimed)
        self.assertEqual(run_suite.DECLARED[0], floor)

    def test_the_versions_flag_prints_the_declared_set_and_nothing_else(self):
        done = subprocess.run([sys.executable, str(REPO / "tools" / "run_suite.py"),
                               "--versions"], capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, 0)
        self.assertEqual(done.stdout.split(), list(run_suite.DECLARED))

    def test_the_readme_states_the_declared_set(self):
        readme = (REPO / "README.md").read_text(encoding="utf-8")
        for version in run_suite.DECLARED:
            self.assertIn(version, readme)


def _as_numbers(version):
    return tuple(int(part) for part in version.split("."))


if __name__ == "__main__":
    unittest.main()
