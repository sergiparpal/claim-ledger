"""tools/measure_route.py: a measurement of the route that spoils nothing quietly.

What is tested is what would spoil either the corpus or the figure without a
sign: a row that carries a claim of a report still to be annotated, two answers
the digest confuses or tells apart wrongly, a call past its deadline recorded
as anything but that, a failure that stops a run instead of becoming its row,
an order that changes between runs meant to compare call for call, and a
watcher that starts the run on one noisy probe. No call leaves the machine:
every POST here is a double.
"""

import contextlib
import io
import json
import os
import sys
import tempfile
import time
import unittest
import unittest.mock
from pathlib import Path

from ledger import extract, schema
from tests import doubles
from tests.test_extract import CAPTURED_REPORT, SETTINGS

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import measure_route  # noqa: E402

PROMPT = extract.load_prompt()
STAGES = {"dns": 0.01, "tcp": 0.01, "tls": 0.02, "first_byte": 0.5, "api": 1.0}
# A real envelope from before the sentence contract: its answer is refused now,
# but how the reply was made is still read off it.
RECORDED = doubles.recorded("openrouter-deepseek-v4.1-flash")
# The recorded route's three claims on CAPTURED_REPORT, as sentence numbers.
ROUTE = doubles.answer((1, "judgment", []), (2, "suite_passed", ["unit test"]),
                       (4, "intent", []), provider="Morph")
SPANS = ["I've completed the first three steps successfully.", "The unit test passed.",
         "Since you explicitly requested the push, I'll proceed with staging, "
         "committing, and pushing the changes."]


def post(*answers):
    """A POST that hands back these answers in order, timed as if it had run."""
    queue = list(answers)

    def answer(request, timeout_s):
        given = queue.pop(0)
        if isinstance(given, Exception):
            raise given
        return given.status, given.body, dict(STAGES)
    return answer


def row(*answers, deadline=10.0):
    return measure_route.call(CAPTURED_REPORT, settings=SETTINGS, prompt=PROMPT,
                              deadline=deadline, post=post(*answers))


answer = doubles.answer


class RowTest(unittest.TestCase):
    def test_a_row_names_no_claim(self):
        made = row(ROUTE)
        self.assertEqual((made["outcome"], made["claims"], made["defects"]), ("usable", 3, 0))
        written = json.dumps(made, ensure_ascii=False)
        for span in SPANS:
            self.assertNotIn(span, written)
        self.assertNotIn("unit test", written)

    def test_the_same_answer_has_one_digest_and_another_answer_another(self):
        first = row(ROUTE)["digest"]
        self.assertEqual(row(ROUTE)["digest"], first)
        one = answer((2, "suite_passed", ["unit test"]))
        self.assertNotEqual(row(one)["digest"], first)
        retyped = answer((2, "judgment", ["unit test"]))
        self.assertNotEqual(row(retyped)["digest"], row(one)["digest"])
        empty = row(answer())
        self.assertEqual(empty["claims"], 0)
        self.assertNotEqual(empty["digest"], first)

    def test_a_defect_counts_and_changes_the_digest(self):
        kept = answer((2, "suite_passed", ["unit test"]))
        astray = answer((2, "suite_passed", ["unit test"]), (99, "suite_passed", []))
        made = row(astray)
        self.assertEqual((made["claims"], made["defects"]), (1, 1))
        self.assertNotEqual(made["digest"], row(kept)["digest"])

    def test_a_call_past_its_deadline_is_recorded_as_one(self):
        def slow(request, timeout_s):
            time.sleep(2)
            return 200, ROUTE.body, dict(STAGES)
        started = time.monotonic()
        made = measure_route.call(CAPTURED_REPORT, settings=SETTINGS, prompt=PROMPT,
                                  deadline=0.2, post=slow)
        self.assertLess(time.monotonic() - started, 1.5)
        self.assertEqual(made["outcome"], "over_deadline")
        self.assertNotIn("status", made)
        self.assertNotIn("digest", made)

    def test_a_failure_becomes_a_row_after_the_clients_one_retry(self):
        made = row(doubles.reply("{}", status=503), doubles.reply("{}", status=503))
        self.assertEqual((made["outcome"], made["status"], made["attempts"]), ("failed", 503, 2))
        made = row(extract.ExtractError("the model call did not complete: reset"), ROUTE)
        self.assertEqual((made["outcome"], made["attempts"]), ("usable", 2))
        made = row(doubles.raw("not json"))
        self.assertEqual(made["outcome"], "failed")

    def test_an_answer_the_schema_refuses_is_unusable_not_failed(self):
        made = row(doubles.reply('{"claims": [{"span": "x"}]}'))
        self.assertEqual(made["outcome"], "unusable")

    def test_a_reply_says_how_it_was_made_even_when_its_answer_is_refused(self):
        made = row(RECORDED)
        self.assertEqual(made["outcome"], "unusable")   # copied spans, from before 18 October
        self.assertEqual((made["provider"], made["stop_reason"]), ("Morph", "end_turn"))
        self.assertEqual(made["stages"], STAGES)
        self.assertEqual((made["usage"]["output_tokens"], made["thinking_tokens"]), (88, 0))
        self.assertEqual(made["blocks"], ["text"])

    def test_the_staged_post_needs_the_key_before_it_touches_the_network(self):
        request = extract.build_request(CAPTURED_REPORT, vocabulary=schema.CLAIM_TYPES,
                                        settings=SETTINGS, prompt=PROMPT)
        with unittest.mock.patch.dict(os.environ):
            os.environ.pop(SETTINGS.key_env, None)
            with self.assertRaises(extract.ExtractError):
                measure_route.staged_post(request, 1.0)


class PlanTest(unittest.TestCase):
    REPORTS = [f"session-{n}" for n in range(1, 26)]

    def test_every_report_comes_once_a_pass_and_the_fixed_one_every_tenth_call(self):
        calls = measure_route.plan(self.REPORTS, passes=2)
        self.assertEqual(len(calls), 56)
        fixed = [i for i, (_, report) in enumerate(calls) if report == measure_route.FIXED]
        self.assertEqual(fixed, [0, 11, 22, 33, 44, 55])
        asked = [(number, report) for number, report in calls if number]
        for number in (1, 2):
            self.assertEqual(sorted(r for n, r in asked if n == number), sorted(self.REPORTS))

    def test_runs_meant_to_compare_call_for_call_do(self):
        self.assertEqual(measure_route.plan(self.REPORTS, passes=2),
                         measure_route.plan(list(reversed(self.REPORTS)), passes=2))
        self.assertNotEqual(measure_route.plan(self.REPORTS, passes=2),
                            measure_route.plan(self.REPORTS, passes=2, seed=1))
        order = [report for _, report in measure_route.plan(self.REPORTS, passes=2,
                                                            fixed_every=0)]
        self.assertNotEqual(order[:25], order[25:])   # each pass in its own order

    def test_an_earlier_run_names_the_reports_it_asked_about(self):
        rows = [{"pass": 1, "report": "a-1"}, {"pass": 2, "report": "a-1"},
                {"pass": 1, "report": "b-2"}, {"pass": 0, "report": measure_route.FIXED},
                {"probe": True, "report": "c-3"}]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "run.jsonl"
            path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
            self.assertEqual(measure_route.reports_of(path), {"a-1", "b-2"})


class ProbeTest(unittest.TestCase):
    def probe(self, wall, tokens, outcome="usable"):
        made = {"wall": wall, "outcome": outcome, "usage": {"output_tokens": tokens}}
        made["slowdown"] = measure_route.slowdown(made)
        return made

    def test_the_fast_run_is_the_yardstick(self):
        self.assertEqual(self.probe(0.65 + 0.0047 * 400, 400)["slowdown"], 1.0)

    def test_one_slow_probe_does_not_start_the_run(self):
        self.assertFalse(measure_route.slow_now(self.probe(6.0, 400), False, slow=2,
                                                route_deadline=12))

    def test_two_in_a_row_do(self):
        self.assertTrue(measure_route.slow_now(self.probe(6.0, 400), True, slow=2,
                                               route_deadline=12))

    def test_one_past_the_routes_own_deadline_does(self):
        self.assertTrue(measure_route.slow_now(self.probe(12.5, 2400), False, slow=2,
                                               route_deadline=12))

    def test_a_probe_with_no_answer_counts_as_slow(self):
        failed = self.probe(3.0, None, outcome="failed")
        self.assertIsNone(failed["slowdown"])
        self.assertFalse(measure_route.slow_now(failed, False, slow=2, route_deadline=12))
        self.assertTrue(measure_route.slow_now(failed, True, slow=2, route_deadline=12))


class SummaryTest(unittest.TestCase):
    def test_percentiles_interpolate(self):
        self.assertEqual(measure_route.percentile([1, 2, 3, 4], 50), 2.5)
        self.assertEqual(measure_route.percentile([4, 1, 3, 2], 100), 4)
        self.assertEqual(measure_route.percentile([5], 99), 5)

    def test_a_run_is_summarised_from_its_rows_alone(self):
        def made(number, report, wall, tokens, digest, claims):
            return {"pass": number, "report": report, "chars": 1000, "wall": wall,
                    "started": f"2026-10-17T16:5{number}:00.000+00:00", "outcome": "usable",
                    "usage": {"output_tokens": tokens, "cost": 0.001}, "stages": dict(STAGES),
                    "provider": "Morph", "thinking_tokens": 0, "claims": claims,
                    "defects": 0, "digest": digest}
        rows = [made(1, "a-1", 2.0, 300, "aaa", 5), made(2, "a-1", 2.2, 300, "aaa", 5),
                made(1, "b-2", 9.0, 1500, "bbb", 20), made(2, "b-2", 0.6, 6, "ccc", 0),
                made(1, "c-3", 4.0, 700, "ddd", 9), made(2, "c-3", 13.0, 2300, "eee", 30)]
        shown = io.StringIO()
        with contextlib.redirect_stdout(shown):
            measure_route._summarise(rows)
        text = shown.getvalue()
        self.assertIn("1 of 3 reports got the same answer every pass", text)
        self.assertIn("the claim count differed in 2, by two times or more in 2", text)
        self.assertIn("1 of 6 answers were empty", text)
        self.assertIn("inside 12s 5,", text)


if __name__ == "__main__":
    unittest.main()
