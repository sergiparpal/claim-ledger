"""ledger.join: which record a claim is about, and the verdict that follows.

The acceptance rows of the requirements are named in the tests that carry
them. A-7's extractor half lives in test_extract, A-8 in test_install, and
A-9 is the gate, which phase 3 builds; the rows that the join and coverage
decide are here and in test_coverage.

Every log is written through the real writer and read back through the real
reader, so a record's position is the reader's, not the test's.
"""

import os
import random
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from ledger import config, evidence, join, record, schema

REPO = Path(__file__).resolve().parent.parent
REAL = Path(__file__).resolve().parent / "fixtures" / "sessions" / "real-v2"
WHERE = schema.Provenance("extract-1+test", "z-ai/glm-5.3-flash",
                          "https://openrouter.ai/api/v1", "Phala")
EARLIER, LATER = "2026-09-20T10:00:00.000Z", "2026-09-20T12:00:00.000Z"


class JoinTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        shutil.copy(REPO / config.CONFIG_FILENAME, self.root / config.CONFIG_FILENAME)
        self.cfg = config.load(self.root / config.CONFIG_FILENAME)
        self.log = evidence.session_log(self.root, "s1")

    def check(self, *, check_id="python-suite", command="pytest -q", outcome="ok",
              ts_end=LATER):
        self.append(kind="check", check_id=check_id, command=command, outcome=outcome,
                    ts_end=ts_end)

    def mutation(self, path, *, outcome="ok", mtime=EARLIER, ts_end=LATER):
        self.append(kind="mutation", outcome=outcome, ts_end=ts_end,
                    files=[{"path": path, "mtime": mtime}])

    def command(self, command, *, outcome="ok", tier="REVIEW"):
        self.append(kind="other", command=command, outcome=outcome, tier=tier)

    def append(self, **fields):
        written = {"v": evidence.RECORD_VERSION, "session": "s1", "turn_id": "t1",
                   "turn_number": 1, "tool": "Bash", "kind": "other", "outcome": "ok",
                   "ts_end": LATER, "tier": "REVIEW"}
        written.update(fields)
        evidence.append(self.log, written)

    def claim(self, span, claim_type, *referents):
        return schema.Claim(span, claim_type, tuple(referents), WHERE)

    def verdicts(self, *claims):
        judged = join.judge(claims, evidence.read(self.log), cfg=self.cfg, root=self.root)
        return [j.verdict for j in judged]

    def judge_one(self, claim):
        [judged] = join.judge([claim], evidence.read(self.log), cfg=self.cfg, root=self.root)
        return judged


class AcceptanceTest(JoinTest):
    def test_a1_a_suite_edited_after_it_ran_is_stale(self):
        self.check()
        self.mutation("src/engine.py")          # covered by python-suite, later in the log
        judged = self.judge_one(self.claim("the tests pass", "suite_passed", "pytest"))
        self.assertEqual(judged.verdict, join.STALE)
        self.assertIn("src/engine.py was written after it", judged.scope)

    def test_a2_a_failed_run_contradicts_the_claim(self):
        self.check(outcome="failed")
        self.assertEqual(self.verdicts(self.claim("the tests pass", "suite_passed", "pytest")),
                         [join.CONTRADICTED])

    def test_a3_and_a6_opinions_and_abstentions_are_not_checkable(self):
        self.check()
        self.assertEqual(self.verdicts(self.claim("I did not run the tests", "judgment"),
                                       self.claim("this design will scale", "judgment"),
                                       self.claim("next I would add a cache", "intent")),
                         [join.NOT_CHECKABLE] * 3)

    def test_a4_a_file_the_log_shows_written_is_verified(self):
        self.mutation("src/parser.py")
        judged = self.judge_one(self.claim("I updated the parser", "file_changed",
                                           "src/parser.py"))
        self.assertEqual(judged.verdict, join.VERIFIED)
        self.assertIn("src/parser.py written ok", judged.scope)

    def test_a7_a_run_that_may_not_have_finished_is_unknown(self):
        self.check(outcome="unknown")
        self.assertEqual(self.verdicts(self.claim("the tests pass", "suite_passed", "pytest")),
                         [join.UNKNOWN])

    def test_a10_a_command_absent_from_the_log_is_unsupported(self):
        self.check()
        self.assertEqual(self.verdicts(self.claim("I ran the migration script", "command_run",
                                                  "python migrate.py")),
                         [join.UNSUPPORTED])

    def test_a11_a_turn_where_everything_holds(self):
        self.mutation("src/parser.py")
        self.check()
        self.assertEqual(self.verdicts(self.claim("I updated the parser", "file_changed",
                                                  "src/parser.py"),
                                       self.claim("the tests pass", "suite_passed", "pytest"),
                                       self.claim("this will scale", "judgment")),
                         [join.VERIFIED, join.VERIFIED, join.NOT_CHECKABLE])


class ReferentTest(JoinTest):
    def test_a_referent_that_resolves_to_nothing_never_falls_back(self):
        self.check()   # the session used exactly one check
        self.assertEqual(self.verdicts(self.claim("the migration suite passed",
                                                  "suite_passed", "the migration suite")),
                         [join.UNSUPPORTED])

    def test_a_claim_naming_no_suite_resolves_only_when_one_check_ran(self):
        self.check()
        self.assertEqual(self.verdicts(self.claim("the tests pass", "suite_passed")),
                         [join.VERIFIED])
        self.check(check_id="lint", command="ruff check .")
        self.assertEqual(self.verdicts(self.claim("the tests pass", "suite_passed")),
                         [join.UNSUPPORTED])

    def test_referents_resolve_through_ids_invocations_and_aliases(self):
        self.check()
        for referent in ["python-suite", "pytest -q", "unit test", "The Tests", "the suite"]:
            with self.subTest(referent=referent):
                self.assertEqual(self.verdicts(self.claim("the tests pass", "suite_passed",
                                                          referent)), [join.VERIFIED])

    def test_a_command_matches_on_its_first_token_and_the_words_named(self):
        self.command("git push origin main")
        self.assertEqual(self.verdicts(self.claim("I pushed", "command_run", "git push")),
                         [join.VERIFIED])
        self.assertEqual(self.verdicts(self.claim("I pushed a tag", "command_run",
                                                  "git push --tags")), [join.UNSUPPORTED])
        self.assertEqual(self.verdicts(self.claim("I pushed", "command_run", "hg push")),
                         [join.UNSUPPORTED])

    def test_a_failed_write_verifies_nothing(self):
        self.mutation("src/parser.py", outcome="failed")
        self.assertEqual(self.verdicts(self.claim("I updated the parser", "file_changed",
                                                  "src/parser.py")), [join.UNSUPPORTED])

    def test_a_command_that_failed_still_ran(self):
        self.command("git push origin main", outcome="failed")
        judged = self.judge_one(self.claim("I pushed", "command_run", "git push"))
        self.assertEqual(judged.verdict, join.VERIFIED)
        self.assertIn("failed", judged.scope)


class LastRunTest(JoinTest):
    """A claim is about the last run, not a run: the A-2 row depends on it."""

    def test_a_later_failure_decides_against_an_earlier_pass(self):
        self.check(outcome="ok")
        self.check(outcome="failed")
        self.assertEqual(self.verdicts(self.claim("the tests pass", "suite_passed", "pytest")),
                         [join.CONTRADICTED])

    def test_a_later_pass_decides_over_an_earlier_failure(self):
        self.check(outcome="failed")
        self.check(outcome="ok")
        self.assertEqual(self.verdicts(self.claim("the tests pass", "suite_passed", "pytest")),
                         [join.VERIFIED])

    def test_the_same_holds_for_a_file_written_twice(self):
        self.mutation("src/parser.py", outcome="ok")
        self.mutation("src/parser.py", outcome="failed")
        self.assertEqual(self.verdicts(self.claim("I updated the parser", "file_changed",
                                                  "src/parser.py")), [join.UNSUPPORTED])

    def test_and_for_a_command_run_twice(self):
        self.command("git push origin main", outcome="ok")
        self.command("git push origin main", outcome="failed")
        judged = self.judge_one(self.claim("I pushed", "command_run", "git push"))
        self.assertEqual((judged.verdict, judged.position), (join.VERIFIED, 2))
        self.assertIn("failed", judged.scope)


class FreshnessTest(JoinTest):
    """R-18: log order and current mtimes, and either one can make a check stale."""

    def write(self, relative, *, mtime=None):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n")
        if mtime is not None:
            self.age(path, mtime)
        return path

    @staticmethod
    def age(path, mtime="old"):
        """11 September 2026 for "old", 21 September for "new": either side of LATER."""
        stamp = 1789000000 if mtime == "old" else 1790000000
        os.utime(path, (stamp, stamp))

    def test_log_order_alone_makes_it_stale(self):
        self.check()
        self.mutation("src/engine.py")     # nothing of this exists on disk
        self.assertEqual(self.verdicts(self.claim("the tests pass", "suite_passed", "pytest")),
                         [join.STALE])

    def test_a_current_mtime_alone_makes_it_stale(self):
        self.check(ts_end=EARLIER)
        self.write("src/engine.py")        # written now, after the check ran
        judged = self.judge_one(self.claim("the tests pass", "suite_passed", "pytest"))
        self.assertEqual(judged.verdict, join.STALE)
        self.assertIn("src/engine.py was modified", judged.scope)

    def test_neither_test_failing_leaves_it_fresh(self):
        self.write("src/engine.py", mtime="old")
        self.check(ts_end=LATER)
        self.assertEqual(self.verdicts(self.claim("the tests pass", "suite_passed", "pytest")),
                         [join.VERIFIED])

    def test_a_file_outside_the_scope_cannot_make_it_stale(self):
        self.check()
        self.mutation("docs/guide.md")     # not in python-suite's scope
        self.assertEqual(self.verdicts(self.claim("the tests pass", "suite_passed", "pytest")),
                         [join.VERIFIED])

    def test_the_ledger_writing_its_own_log_does_not_make_a_check_stale(self):
        self.write("README.md", mtime="old")
        self.age(self.root / config.CONFIG_FILENAME)  # the only other file lint covers
        self.check(check_id="lint", command="ruff check .", ts_end=LATER)  # scope **/*
        self.assertEqual(self.verdicts(self.claim("lint is clean", "suite_passed", "lint")),
                         [join.VERIFIED])
        self.assertTrue(self.log.exists())  # written now, and inside the scope glob


class WorkingTreeTest(JoinTest):
    """The mtime test reads the project, not git's bookkeeping or ours."""

    def git_init(self, gitignore):
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True, capture_output=True,
                       timeout=60, env={"PATH": os.environ.get("PATH", ""),
                                        "GIT_CONFIG_GLOBAL": os.devnull,
                                        "GIT_CONFIG_SYSTEM": os.devnull})
        (self.root / ".gitignore").write_text(gitignore)
        FreshnessTest.age(self.root / ".gitignore")
        FreshnessTest.age(self.root / config.CONFIG_FILENAME)

    def test_a_file_git_ignores_cannot_stale_a_check(self):
        self.git_init("build/\n")
        (self.root / "build").mkdir()
        (self.root / "build" / "out.o").write_text("fresh\n")   # written now, under **/*
        self.check(check_id="lint", command="ruff check .", ts_end=LATER)
        self.assertEqual(self.verdicts(self.claim("lint is clean", "suite_passed", "lint")),
                         [join.VERIFIED])

    def test_git_adding_a_file_cannot_stale_a_check(self):
        self.git_init("\n")
        (self.root / "src").mkdir()
        source = self.root / "src" / "engine.py"
        source.write_text("x\n")
        FreshnessTest.age(source)
        self.check(check_id="lint", command="ruff check .", ts_end=LATER)
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True, capture_output=True,
                       timeout=60, env={"PATH": os.environ.get("PATH", ""),
                                        "GIT_CONFIG_GLOBAL": os.devnull,
                                        "GIT_CONFIG_SYSTEM": os.devnull})
        self.assertTrue((self.root / ".git" / "index").exists())  # written just now
        self.assertEqual(self.verdicts(self.claim("lint is clean", "suite_passed", "lint")),
                         [join.VERIFIED])

    def test_a_file_git_keeps_still_stales_it(self):
        self.git_init("build/\n")
        (self.root / "src").mkdir()
        (self.root / "src" / "engine.py").write_text("fresh\n")
        self.check(ts_end=EARLIER)
        self.assertEqual(self.verdicts(self.claim("the tests pass", "suite_passed", "pytest")),
                         [join.STALE])


class RealSessionTest(unittest.TestCase):
    """The A-1 row as it happened, in a session recorded under RECORD_VERSION 2."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        shutil.copy(REAL / config.CONFIG_FILENAME, self.root / config.CONFIG_FILENAME)
        self.cfg = config.load(self.root / config.CONFIG_FILENAME)
        self.entries = evidence.read(REAL / "session.jsonl")

    def test_the_recorded_session_is_the_shape_the_recorder_writes(self):
        self.assertEqual([e.record["kind"] for e in self.entries],
                         ["mutation", "mutation", "mutation", "check", "mutation"])
        self.assertEqual({e.record["v"] for e in self.entries}, {evidence.RECORD_VERSION})
        self.assertEqual({e.record["turn_number"] for e in self.entries}, {1})

    def test_the_claim_that_session_really_made_is_stale(self):
        """Its report said the tests still pass, after editing a file they cover."""
        claim = schema.Claim("all tests still pass successfully", "suite_passed",
                             ("the tests",), WHERE)
        [judged] = join.judge([claim], self.entries, cfg=self.cfg, root=self.root)
        self.assertEqual(judged.verdict, join.STALE)
        self.assertIn("src/calc.py was written after it", judged.scope)
        self.assertEqual(judged.position, 4)   # the check, not the edit that stales it

    def test_nothing_on_disk_was_needed_to_catch_it(self):
        """The root here is empty: log order alone did it, which is R-18's point."""
        self.assertEqual(list(self.root.glob("src/**")), [])


class NoUpgradeTest(JoinTest):
    """No generated log and claim pair ever reaches VERIFIED without a record."""

    def test_verified_always_points_at_a_record_that_matches(self):
        rng = random.Random(20260920)
        spans = ["the tests pass", "I updated the parser", "I ran the migration"]
        paths = ["src/engine.py", "src/parser.py", "docs/guide.md", "tests/test_x.py"]
        commands = ["pytest -q", "git push origin main", "npm test", "ruff check ."]
        for run in range(200):
            with self.subTest(run=run):
                self.log.unlink(missing_ok=True)
                for _ in range(rng.randrange(0, 4)):
                    choice = rng.random()
                    if choice < 0.4:
                        self.mutation(rng.choice(paths),
                                      outcome=rng.choice(["ok", "failed", "unknown"]))
                    elif choice < 0.7:
                        self.check(command=rng.choice(commands),
                                   outcome=rng.choice(["ok", "failed", "unknown"]))
                    else:
                        self.command(rng.choice(commands),
                                     outcome=rng.choice(["ok", "failed", "unknown"]))
                referents = tuple(rng.sample(paths + commands + ["unit test", "python-suite"],
                                             rng.randrange(0, 2)))
                claim = schema.Claim(rng.choice(spans),
                                     rng.choice(list(schema.CLAIM_TYPES)), referents, WHERE)
                entries = evidence.read(self.log)
                [judged] = join.judge([claim], entries, cfg=self.cfg, root=self.root)
                if judged.verdict != join.VERIFIED:
                    continue
                self.assertIsNotNone(judged.position, judged)
                deciding = entries[judged.position - 1].record
                self.assertNotEqual(deciding.get("outcome"), "unknown")
                if claim.type == "file_changed":
                    self.assertTrue(join.names_path(claim.referents, deciding))
                    self.assertEqual(deciding.get("outcome"), "ok")
                elif claim.type == "command_run":
                    self.assertTrue(join.names_command(claim.referents, deciding))
                else:
                    self.assertEqual(deciding.get("kind"), "check")
                    self.assertEqual(deciding.get("outcome"), "ok")


if __name__ == "__main__":
    unittest.main()
