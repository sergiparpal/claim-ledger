"""ledger.appendix: one line unless something needs saying.

The collapsed form is the one a normal turn gets, so it is the one most likely
to rot unnoticed; A-11 is here. Everything else asserts that a severe verdict
cannot be buried — not by ordering, not by the harness's 10,000 character cap,
and not by a long span.
"""

import unittest

from ledger import appendix, coverage, join, schema

WHERE = schema.Provenance("extract-1+test", "deepseek/deepseek-v4.1-flash",
                          "https://openrouter.ai/api/v1", "Morph")


def judged(span, claim_type, verdict, scope=None, position=1):
    return join.Judged(schema.Claim(span, claim_type, (), WHERE), verdict, scope, position)


def unreported(what, tier="REVIEW", kind="mutation", position=1):
    return coverage.Unreported(position=position, kind=kind, what=what, tier=tier, record={})


class CollapsedTest(unittest.TestCase):
    def test_a11_everything_verified_and_nothing_unreported_is_one_line(self):
        turn = appendix.Turn(
            judged=[judged("I updated the parser", "file_changed", join.VERIFIED,
                           "src/parser.py written ok at 2026-09-20T12:00:00.000Z"),
                    judged("the tests pass", "suite_passed", join.VERIFIED,
                           "pytest -q ok at 2026-09-20T12:00:00.000Z"),
                    judged("this will scale", "judgment", join.NOT_CHECKABLE)],
            checks_seen=2)
        self.assertEqual(appendix.render(turn),
                         "claim-ledger · 2 verified, 1 unchecked · 2 checks seen · "
                         "nothing unreported")

    def test_a_turn_with_no_claims_at_all_still_says_how_many_checks_it_saw(self):
        """R-29: zero is worth seeing, which is the whole reason it is printed."""
        self.assertIn("0 checks seen", appendix.render(appendix.Turn()))

    def test_one_check_is_not_pluralised(self):
        self.assertIn("1 check seen", appendix.render(appendix.Turn(checks_seen=1)))

    def test_an_unreported_action_stops_it_collapsing(self):
        turn = appendix.Turn(judged=[judged("done", "judgment", join.NOT_CHECKABLE)],
                             unreported=[unreported("migrations/0007.sql", "HUMAN")])
        self.assertIn("UNREPORTED", appendix.render(turn))

    def test_a_defect_stops_it_collapsing(self):
        """A span the report does not contain means a claim went unjudged. The
        collapse rule of R-29 does not name defects because the renderer did not
        exist when it was written; hiding one would be the wrong direction (I-2)."""
        turn = appendix.Turn(defects=[schema.Defect("a span nobody wrote",
                                                    "not verbatim in the report")])
        self.assertIn("EXTRACTION DEFECTS", appendix.render(turn))


class ExpandedTest(unittest.TestCase):
    def render(self, **fields):
        return appendix.render(appendix.Turn(**fields))

    def test_contradicted_stands_at_the_head(self):
        text = self.render(judged=[
            judged("I ran the migration", "command_run", join.UNSUPPORTED),
            judged("the suite is green", "suite_passed", join.STALE,
                   "pytest -q ok at 10:00; src/engine.py modified at 12:00"),
            judged("the tests pass", "suite_passed", join.CONTRADICTED,
                   "pytest -q failed at 2026-09-19T14:32:07.880Z")])
        groups = [line for line in text.splitlines() if line and not line.startswith(" ")]
        self.assertEqual(groups, ["claim-ledger", "CONTRADICTED", "STALE", "UNSUPPORTED",
                                  "0 verified, 0 unchecked · 0 checks seen"])

    def test_every_group_follows_the_severity_order(self):
        """I-5's order is the one the appendix reads by, so it is asserted whole."""
        self.assertEqual(appendix.SEVERITY,
                         (join.CONTRADICTED, join.UNKNOWN, join.STALE, join.UNSUPPORTED,
                          join.NOT_CHECKABLE, join.VERIFIED))

    def test_a_verdict_carries_the_scope_the_join_gave_it(self):
        """I-4: no bare verdict, and the appendix does not reformat one."""
        scope = "pytest -q failed at 2026-09-19T14:32:07.880Z"
        text = self.render(judged=[judged("the tests pass", "suite_passed",
                                          join.CONTRADICTED, scope)])
        self.assertIn(f"  {scope}", text.splitlines())

    def test_an_unsupported_claim_says_what_was_looked_for(self):
        text = self.render(judged=[judged("I ran the migration script", "command_run",
                                          join.UNSUPPORTED)])
        self.assertIn("  no matching command in this session", text.splitlines())

    def test_not_checkable_is_counted_and_never_listed(self):
        text = self.render(judged=[judged("this design will scale", "judgment",
                                          join.NOT_CHECKABLE),
                                   judged("nothing ran", "command_run", join.UNSUPPORTED)])
        self.assertNotIn("this design will scale", text)
        self.assertIn("0 verified, 1 unchecked", text)

    def test_low_tier_actions_are_counted_not_listed(self):
        text = self.render(unreported=[unreported("docs/notes.md", "LOW"),
                                       unreported("src/engine.py", "REVIEW")])
        self.assertIn("  src/engine.py (REVIEW)", text.splitlines())
        self.assertNotIn("docs/notes.md", text)
        self.assertIn("1 LOW-tier action not listed", text)

    def test_the_tier_travels_with_an_unreported_action(self):
        self.assertIn("  migrations/0007_add_index.sql (HUMAN)",
                      self.render(unreported=[unreported("migrations/0007_add_index.sql",
                                                         "HUMAN")]).splitlines())


class UnknownTest(unittest.TestCase):
    def test_an_unknown_turn_is_one_line_that_says_why(self):
        text = appendix.render(appendix.Turn(
            unknown="ExtractError: the model call passed its 12.0s deadline",
            checks_seen=3))
        self.assertEqual(text, "claim-ledger · UNKNOWN · ExtractError: the model call "
                               "passed its 12.0s deadline · 3 checks seen")
        self.assertEqual(len(text.splitlines()), 1)

    def test_an_unknown_turn_never_reads_as_a_clean_one(self):
        """I-9. The collapsed line and the UNKNOWN line must not be confusable."""
        text = appendix.render(appendix.Turn(unknown="ConfigError: it changed"))
        self.assertIn("UNKNOWN", text)
        self.assertNotIn("nothing unreported", text)


class LimitTest(unittest.TestCase):
    def test_a_long_span_is_elided_in_its_middle(self):
        span = "a" * 200 + "UNIQUE" + "b" * 200
        text = appendix.render(appendix.Turn(
            judged=[judged(span, "command_run", join.UNSUPPORTED)]))
        self.assertNotIn("UNIQUE", text)
        self.assertIn(appendix.ELLIPSIS, text)
        self.assertIn("a" * 20, text)
        self.assertIn("b" * 20, text)

    def test_a_span_holding_newlines_stays_on_one_line(self):
        self.assertEqual(appendix.elide("two\nlines"), "two lines")

    def test_the_whole_thing_fits_the_harness_cap(self):
        turn = appendix.Turn(judged=[judged(f"claim number {i} " + "x" * 100,
                                            "command_run", join.UNSUPPORTED)
                                     for i in range(400)])
        text = appendix.render(turn)
        self.assertLessEqual(len(text), appendix.LIMIT)
        self.assertIn("dropped to fit", text.splitlines()[-1])

    def test_the_most_severe_entries_are_the_last_to_be_dropped(self):
        turn = appendix.Turn(
            judged=[judged("the tests pass", "suite_passed", join.CONTRADICTED,
                           "pytest -q failed at 2026-09-19T14:32:07.880Z")]
            + [judged(f"claim {i} " + "x" * 100, "command_run", join.UNSUPPORTED)
               for i in range(400)])
        text = appendix.render(turn)
        self.assertLessEqual(len(text), appendix.LIMIT)
        self.assertIn("the tests pass", text)
        self.assertIn("CONTRADICTED", text)


if __name__ == "__main__":
    unittest.main()
