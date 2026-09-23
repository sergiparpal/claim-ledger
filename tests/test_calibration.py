"""ledger.calibration: the durable claims-and-verdicts log.

R-34 records every claim with its verdict and scope; R-35 accepts a later
outcome without rewriting what was written. R-36 is the one no code can test:
nothing computes a rate from this file, and the way to keep it that way is for
nothing here to offer one.
"""

import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ledger import calibration, config, join, schema

REPO = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)
WHERE = schema.Provenance("extract-1+74af1596", "deepseek/deepseek-v4.1-flash",
                          "https://openrouter.ai/api/v1", "Morph")


def judged(span, claim_type, verdict, scope=None, position=None, referents=()):
    return join.Judged(schema.Claim(span, claim_type, tuple(referents), WHERE),
                       verdict, scope, position)


class CalibrationTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        shutil.copy(REPO / config.CONFIG_FILENAME, self.root / config.CONFIG_FILENAME)

    def write(self, *rows):
        calibration.append(self.root, rows)
        return calibration.read(self.root)

    def rows(self, judged_claims=(), defects=()):
        return calibration.rows(judged_claims, defects, session="abc123", turn_id="p-1",
                                turn_number=3, now=NOW)


class RowTest(CalibrationTest):
    def test_a_claim_row_carries_its_verdict_scope_and_route(self):
        scope = "pytest -q failed at 2026-09-19T14:32:07.880Z"
        [row] = self.rows([judged("the tests pass", "suite_passed", join.CONTRADICTED,
                                  scope, position=4, referents=["the tests"])])
        self.assertEqual(row["row"], "claim")
        self.assertEqual(row["claim_id"], "abc123-3-0")
        self.assertEqual(row["span"], "the tests pass")
        self.assertEqual(row["type"], "suite_passed")
        self.assertEqual(row["referents"], ["the tests"])
        self.assertEqual(row["verdict"], join.CONTRADICTED)
        self.assertEqual(row["scope"], scope)
        self.assertEqual(row["position"], 4)
        self.assertEqual(row["route"]["provider"], "Morph")
        self.assertEqual(row["route"]["prompt_version"], "extract-1+74af1596")
        self.assertEqual((row["session"], row["turn_id"], row["turn_number"]),
                         ("abc123", "p-1", 3))

    def test_a_span_is_kept_whole_however_long_it_is(self):
        """The appendix elides to fit a cap; this file is what keeps the original."""
        span = "x" * 5000
        [row] = self.rows([judged(span, "command_run", join.UNSUPPORTED)])
        self.assertEqual(row["span"], span)

    def test_a_defect_is_recorded_as_its_own_row(self):
        rows = self.rows([], [schema.Defect("never written", "not verbatim in the report")])
        self.assertEqual([r["row"] for r in rows], ["defect"])
        self.assertEqual(rows[0]["claim_id"], "abc123-3-d0")
        self.assertEqual(rows[0]["reason"], "not verbatim in the report")

    def test_claims_keep_the_order_they_were_made_in(self):
        rows = self.rows([judged("first", "command_run", join.UNSUPPORTED),
                          judged("second", "judgment", join.NOT_CHECKABLE)])
        self.assertEqual([r["span"] for r in rows], ["first", "second"])
        self.assertEqual([r["claim_id"] for r in rows], ["abc123-3-0", "abc123-3-1"])


class AppendTest(CalibrationTest):
    def test_rows_land_one_per_line_and_survive_a_read(self):
        written = self.write(*self.rows([judged("done", "judgment", join.NOT_CHECKABLE)]))
        self.assertEqual(len(written), 1)
        text = calibration.claims_log(self.root).read_text(encoding="utf-8")
        self.assertEqual(len(text.splitlines()), 1)
        self.assertTrue(text.endswith("\n"))

    def test_a_later_turn_appends_rather_than_replaces(self):
        self.write(*self.rows([judged("first", "judgment", join.NOT_CHECKABLE)]))
        rows = self.write(*calibration.rows(
            [judged("second", "judgment", join.NOT_CHECKABLE)], (),
            session="abc123", turn_id="p-2", turn_number=4, now=NOW))
        self.assertEqual([r["span"] for r in rows], ["first", "second"])

    def test_nothing_is_read_back_before_a_row_is_written(self):
        """The evidence log's discipline: one write, no read-modify-write."""
        self.assertEqual(calibration.read(self.root), [])

    def test_a_truncated_last_row_is_refused_rather_than_skipped(self):
        self.write(*self.rows([judged("done", "judgment", join.NOT_CHECKABLE)]))
        log = calibration.claims_log(self.root)
        log.write_bytes(log.read_bytes() + b'{"row": "claim"')
        with self.assertRaises(Exception):
            calibration.read(self.root)


class AnnotationTest(CalibrationTest):
    def test_a_later_outcome_is_appended_and_names_the_claim(self):
        [row] = self.write(*self.rows([judged("the tests pass", "suite_passed",
                                              join.VERIFIED, "pytest -q ok at 12:00")]))
        calibration.annotate(self.root, row["claim_id"], outcome="false", by="SP",
                             now=NOW, note="the suite was scoped to one file")
        rows = calibration.read(self.root)
        self.assertEqual([r["row"] for r in rows], ["claim", "annotation"])
        self.assertEqual(rows[1]["annotates"], "abc123-3-0")
        self.assertEqual(rows[1]["outcome"], "false")
        self.assertEqual(rows[1]["by"], "SP")

    def test_the_row_it_annotates_is_left_exactly_as_it_was(self):
        """R-35: marked without rewriting history."""
        [row] = self.write(*self.rows([judged("done", "command_run", join.VERIFIED,
                                              "ls ok at 12:00")]))
        before = json.dumps(row, sort_keys=True)
        calibration.annotate(self.root, row["claim_id"], outcome="false", by="SP", now=NOW)
        self.assertEqual(json.dumps(calibration.read(self.root)[0], sort_keys=True), before)


if __name__ == "__main__":
    unittest.main()
