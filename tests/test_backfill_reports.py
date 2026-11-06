"""tools/backfill_reports.py: reports rebuilt from transcripts, as the Stop handler writes them.

What is tested is what would put in the corpus a report no Stop would have
captured, or leave one out: a message that did not end its turn, a subagent's
message, a message copied into a resumed session's transcript counted twice, a
message split over several entries read as several, and a report that does not
read back exactly as it was written. Nothing here reads ~/.claude.
"""

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from ledger import evidence, turn

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import backfill_reports  # noqa: E402

SESSION = "5e55a0b1-0000-4000-8000-000000000001"


def user(text, prompt_id=None):
    entry = {"type": "user", "sessionId": SESSION, "message": {"role": "user", "content": text}}
    if prompt_id:
        entry["promptId"] = prompt_id
    return entry


def tool_result():
    return {"type": "user", "sessionId": SESSION,
            "message": {"role": "user", "content": [{"type": "tool_result", "content": "ok"}]}}


def assistant(message_id, block, stop, at, *, sidechain=False):
    return {"type": "assistant", "sessionId": SESSION, "timestamp": at, "isSidechain": sidechain,
            "message": {"id": message_id, "role": "assistant", "content": [block],
                        "stop_reason": stop}}


def text(words):
    return {"type": "text", "text": words}


FIRST = [
    user("Run the tests.", "prompt-1"),
    assistant("m1", {"type": "tool_use", "name": "Bash", "input": {}}, "tool_use",
              "2026-11-01T10:00:01Z"),
    tool_result(),
    assistant("m2", {"type": "thinking", "thinking": "..."}, "end_turn", "2026-11-01T10:00:05Z"),
    assistant("m2", text("Ran pytest: 12 passed."), "end_turn", "2026-11-01T10:00:06Z"),
    assistant("s1", text("A subagent's report to its parent."), "end_turn",
              "2026-11-01T10:00:07Z", sidechain=True),
    user("Now the docs.", "prompt-2"),
    assistant("m3", text("Started on the docs"), None, "2026-11-01T10:01:00Z"),  # interrupted
    user("[Request interrupted by user]"),
    user("Finish them.", "prompt-3"),
    assistant("m4", text("I updated README.md."), "end_turn", "2026-11-01T10:02:00Z"),
    assistant("m4", text("Nothing else changed."), "end_turn", "2026-11-01T10:02:01Z"),
]
# A resumed session's transcript copies what came before, and goes on.
SECOND = FIRST[3:5] + [
    user("And the changelog?", "prompt-4"),
    assistant("m5", text("CHANGELOG.md has the entry."), "end_turn", "2026-11-02T09:00:00Z"),
]


class BackfillTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.transcripts = Path(tmp.name) / "transcripts"
        self.transcripts.mkdir()
        for name, entries in (("a.jsonl", FIRST), ("b.jsonl", SECOND)):
            (self.transcripts / name).write_text(
                "".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8")
        self.root = Path(tmp.name) / "root"

    def run_tool(self, *options):
        printed = io.StringIO()
        code = backfill_reports.main(["backfill_reports.py", *options, str(self.transcripts),
                                      str(self.root)], out=printed)
        return code, printed.getvalue()

    def reports(self):
        folder = self.root / evidence.STATE_DIR / turn.REPORTS
        return {path.stem: turn.read_capture(path) for path in sorted(folder.glob("*.md"))}

    def test_each_turn_that_ended_is_one_report_and_nothing_else_is(self):
        code, printed = self.run_tool()
        self.assertEqual(code, 0)
        self.assertIn("3 turns ended", printed)
        texts = {stem: body for stem, (_, body) in self.reports().items()}
        self.assertEqual(texts, {f"{SESSION}-1": "Ran pytest: 12 passed.",
                                 f"{SESSION}-2": "I updated README.md.\n\nNothing else changed.",
                                 f"{SESSION}-3": "CHANGELOG.md has the entry."})

    def test_a_report_says_it_was_rebuilt_and_names_its_prompt(self):
        self.run_tool()
        header, _ = self.reports()[f"{SESSION}-1"]
        self.assertEqual(header["note"], backfill_reports.NOTE)
        self.assertEqual(header["turn_id"], "prompt-1")
        self.assertEqual(header["captured"], "2026-11-01T10:00:06.000Z")
        self.assertEqual(header["records"], "0")

    def test_a_second_run_writes_nothing_again(self):
        self.run_tool()
        _, printed = self.run_tool()
        self.assertIn("written 0, already there 3", printed)

    def test_a_dry_run_counts_and_writes_nothing(self):
        _, printed = self.run_tool("--dry-run")
        self.assertIn("3 turns ended", printed)
        self.assertFalse(self.root.exists())


if __name__ == "__main__":
    unittest.main()
