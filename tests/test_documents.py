"""The documents say the same thing as each other, and as the code.

CLAUDE.md carries the invariants "copied verbatim" from the requirements. Two
copies of a frozen text, both edited by hand, is how a frozen text stops being
one — and an invariant that says two different things in two files is worse
than an invariant in one, because whichever a reader finds first looks
authoritative.

Nothing here judges what the documents say. It checks that the copies match,
that a label means one thing, and that a number written in prose is the number
the code uses.
"""

import re
import unittest
from pathlib import Path

from ledger import appendix, config, join

REPO = Path(__file__).resolve().parent.parent
REQUIREMENTS = (REPO / "docs" / "REQUIREMENTS.md").read_text(encoding="utf-8")
CLAUDE = (REPO / "CLAUDE.md").read_text(encoding="utf-8")
SPEC = (REPO / "docs" / "SPEC.md").read_text(encoding="utf-8")

INVARIANT = re.compile(r"^\d+\. \*\*(I-\d+) [^*]+\*\*.*$", re.MULTILINE)


def invariants(text):
    """Each invariant of a document, by id, as one line of text."""
    return {INVARIANT.match(line).group(1): line.strip()
            for line in text.splitlines() if INVARIANT.match(line)}


class InvariantCopyTest(unittest.TestCase):
    def test_both_copies_are_word_for_word_the_same(self):
        theirs, ours = invariants(REQUIREMENTS), invariants(CLAUDE)
        self.assertEqual(set(theirs), {f"I-{n}" for n in range(1, 11)})
        self.assertEqual(set(ours), set(theirs))
        for name in theirs:
            with self.subTest(invariant=name):
                self.assertEqual(ours[name], theirs[name])

    def test_there_are_ten_of_them_and_no_more(self):
        self.assertEqual(len(invariants(REQUIREMENTS)), 10)


class SeverityTest(unittest.TestCase):
    def test_the_order_in_the_code_is_the_order_i5_declares(self):
        """I-5 names the order in prose; appendix.SEVERITY is it as data. If
        they part, the appendix sorts by one rule and the document promises
        another."""
        written = invariants(REQUIREMENTS)["I-5"]
        named = re.findall(r"`([A-Z_]+)`", written)
        self.assertEqual(tuple(named), appendix.SEVERITY)

    def test_every_verdict_the_table_can_produce_has_a_severity(self):
        self.assertEqual(set(join.VERDICT_TABLE.values()) | {join.UNKNOWN},
                         set(appendix.SEVERITY))


class LabelTest(unittest.TestCase):
    def test_no_acceptance_label_names_two_different_things(self):
        """A-11 named both the collapsed-appendix row and the extractor corpus
        until 23 September 2026, and both references were live."""
        rows = re.findall(r"^\| (A-\d+) \|", REQUIREMENTS, re.MULTILINE)
        headings = re.findall(r"^\*\*(A-\d+) ", REQUIREMENTS, re.MULTILINE)
        used = rows + headings
        self.assertEqual(len(set(used)), len(used), "one label, two meanings")

    def test_every_acceptance_label_the_spec_cites_exists(self):
        declared = set(re.findall(r"^\| (A-\d+) \|", REQUIREMENTS, re.MULTILINE))
        declared |= set(re.findall(r"^\*\*(A-\d+) ", REQUIREMENTS, re.MULTILINE))
        for cited in set(re.findall(r"\bA-\d+\b", SPEC)):
            with self.subTest(label=cited):
                self.assertIn(cited, declared)


class BudgetTest(unittest.TestCase):
    def test_the_three_timeouts_are_strictly_ordered(self):
        """R-43, as the shipped configuration and hooks actually set it."""
        import json
        cfg = config.load(REPO / config.CONFIG_FILENAME)
        hooks = json.loads((REPO / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        kill = hooks["hooks"]["Stop"][0]["hooks"][0]["timeout"]
        self.assertLess(cfg.extractor.timeout_s, cfg.budget.turn_timeout_s)
        self.assertLess(cfg.budget.turn_timeout_s, kill)

    def test_the_appendix_cap_is_the_one_the_documents_state(self):
        self.assertIn("10,000 character", SPEC)
        self.assertEqual(appendix.LIMIT, 10_000)


if __name__ == "__main__":
    unittest.main()
