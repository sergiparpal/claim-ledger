"""ledger.budget: the turn's wall clock, and what abandoning work really costs.

R-43 wants a deadline over the whole pipeline and an UNKNOWN when it is
exceeded. The second half is the one that can quietly fail: a deadline that
fires while the process cannot leave produces a hook the harness kills, and a
killed hook renders nothing at all.
"""

import subprocess
import sys
import time
import unittest
from pathlib import Path

from ledger import budget

REPO = Path(__file__).resolve().parent.parent


class DeadlineTest(unittest.TestCase):
    def test_it_counts_down_and_never_goes_negative(self):
        clock = budget.Deadline(0.05)
        self.assertGreater(clock.remaining(), 0)
        time.sleep(0.08)
        self.assertEqual(clock.remaining(), 0.0)
        self.assertTrue(clock.expired())

    def test_a_stage_gets_the_smaller_of_its_own_limit_and_what_is_left(self):
        self.assertAlmostEqual(budget.Deadline(30).bounded(12), 12, places=1)
        self.assertLess(budget.Deadline(2).bounded(12), 2.1)

    def test_it_counts_from_when_the_process_started_not_from_construction(self):
        started = time.monotonic() - 10
        self.assertAlmostEqual(budget.Deadline(15, started=started).remaining(), 5, places=1)


class RunWithinTest(unittest.TestCase):
    def test_a_result_comes_straight_back(self):
        self.assertEqual(budget.run_within(5, lambda: "done"), "done")

    def test_an_exception_travels_back_to_the_caller(self):
        def boom():
            raise ValueError("from the worker")
        with self.assertRaises(ValueError) as caught:
            budget.run_within(5, boom)
        self.assertIn("from the worker", str(caught.exception))

    def test_overrunning_raises_rather_than_waiting(self):
        start = time.monotonic()
        with self.assertRaises(budget.Overrun):
            budget.run_within(0.1, lambda: time.sleep(5))
        self.assertLess(time.monotonic() - start, 2)

    def test_an_abandoned_stage_does_not_hold_the_process_open(self):
        """Measured 23 September 2026, and the reason this helper exists at all.

        With concurrent.futures, shutdown(wait=False, cancel_futures=True) looks
        like abandonment and is not: the interpreter joins pool workers at exit,
        so a 1s deadline over an 8s call exited at 8.1s. The margin between the
        turn budget and the harness's kill is worth exactly nothing if the
        process cannot leave when the deadline says so.
        """
        probe = ("import sys, time; sys.path.insert(0, 'src')\n"
                 "from ledger import budget\n"
                 "try:\n"
                 "    budget.run_within(0.2, lambda: time.sleep(20))\n"
                 "except budget.Overrun:\n"
                 "    print('overran')\n")
        start = time.monotonic()
        done = subprocess.run([sys.executable, "-c", probe], cwd=REPO,
                              capture_output=True, text=True, timeout=60)
        elapsed = time.monotonic() - start
        self.assertEqual(done.stdout.strip(), "overran")
        self.assertLess(elapsed, 10, "the process waited for work it said it had abandoned")


if __name__ == "__main__":
    unittest.main()
