"""ledger.coverage: the consequential actions a report leaves out (A-5, I-7).

What counts as consequential is R-22's list and the tiers the user's own
configuration assigns, never a guess about what a command does.
"""

import shutil
import tempfile
import unittest
from pathlib import Path

from ledger import config, coverage, evidence, schema

REPO = Path(__file__).resolve().parent.parent
REAL = Path(__file__).resolve().parent / "fixtures" / "sessions" / "real-v2"
WHERE = schema.Provenance("extract-1+test", "m", "https://openrouter.ai/api/v1", "Phala")


class CoverageTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        shutil.copy(REPO / config.CONFIG_FILENAME, self.root / config.CONFIG_FILENAME)
        self.log = evidence.session_log(self.root, "s1")

    def append(self, **fields):
        written = {"v": evidence.RECORD_VERSION, "session": "s1", "turn_id": "t1",
                   "turn_number": 1, "tool": "Bash", "kind": "other", "outcome": "ok",
                   "ts_end": "2026-09-20T12:00:00.000Z", "tier": "REVIEW"}
        written.update(fields)
        evidence.append(self.log, written)

    def mutation(self, path, *, outcome="ok", tier="REVIEW"):
        self.append(kind="mutation", tool="Write", outcome=outcome, tier=tier,
                    files=[{"path": path, "mtime": "2026-09-20T11:00:00.000Z"}])

    def claim(self, span, claim_type, *referents):
        return schema.Claim(span, claim_type, tuple(referents), WHERE)

    def unreported(self, *claims):
        return coverage.unreported(evidence.read(self.log), claims)


class WhatCountsTest(CoverageTest):
    def test_a5_a_report_saying_only_done_leaves_three_unreported(self):
        for path in ["src/a.py", "src/b.py", "docs/c.md"]:
            self.mutation(path)
        listed = self.unreported()
        self.assertEqual([(u.position, u.what) for u in listed],
                         [(1, "src/a.py"), (2, "src/b.py"), (3, "docs/c.md")])

    def test_a_claim_that_names_a_file_excuses_it(self):
        self.mutation("src/a.py")
        self.mutation("src/b.py")
        listed = self.unreported(self.claim("I updated a", "file_changed", "src/a.py"))
        self.assertEqual([u.what for u in listed], ["src/b.py"])

    def test_a_claim_that_names_a_command_excuses_it(self):
        self.append(kind="other", command="git push origin main", tier="HUMAN")
        self.assertEqual(self.unreported(self.claim("I pushed", "command_run", "git push")), ())

    def test_a_failed_check_is_consequential(self):
        self.append(kind="check", check_id="python-suite", command="pytest -q",
                    outcome="failed")
        self.assertEqual([u.what for u in self.unreported()], ["pytest -q"])

    def test_a_check_that_passed_is_not_unreported_on_its_own(self):
        self.append(kind="check", check_id="python-suite", command="pytest -q")
        self.assertEqual(self.unreported(), ())

    def test_only_commands_above_the_default_tier_count(self):
        self.append(kind="other", command="ls -la", tier="LOW")
        self.append(kind="other", command="git status", tier="REVIEW")
        self.append(kind="other", command="git push origin main", tier="HUMAN")
        self.assertEqual([(u.what, u.tier) for u in self.unreported()],
                         [("git push origin main", "HUMAN")])

    def test_a_write_that_failed_changed_nothing(self):
        self.mutation("src/a.py", outcome="failed")
        self.mutation("src/b.py", outcome="unknown")   # it may have
        self.assertEqual([u.what for u in self.unreported()], ["src/b.py"])

    def test_a_low_tier_mutation_is_still_reported_with_its_tier(self):
        self.mutation("docs/guide.md", tier="LOW")
        [listed] = self.unreported()
        self.assertEqual((listed.what, listed.tier, listed.kind),
                         ("docs/guide.md", "LOW", "mutation"))


class RealSessionTest(unittest.TestCase):
    def test_the_file_that_session_never_mentioned(self):
        """Its report named calc.py and test_calc.py, and not tests/__init__.py."""
        entries = evidence.read(REAL / "session.jsonl")
        claims = [schema.Claim("I created a simple calculator module in src/calc.py",
                               "file_changed", ("src/calc.py",), WHERE),
                  schema.Claim("set up a unittest in tests/test_calc.py", "file_changed",
                               ("tests/test_calc.py",), WHERE)]
        listed = coverage.unreported(entries, claims)
        self.assertEqual([(u.position, u.what) for u in listed], [(2, "tests/__init__.py")])


if __name__ == "__main__":
    unittest.main()
