"""The turn's wall clock.

R-43 asks for a deadline over the whole pipeline, not a socket timeout, and
says that exceeding it is an UNKNOWN turn rather than a silent skip. Both
halves need the same object: something every stage can ask how much time is
left, and something the handler can ask whether the time ran out.

The budget is the pipeline's own, and it is strictly shorter than the timeout
the harness kills the hook at (hooks/hooks.json). That difference is the only
reason an overrun can be reported at all: a pipeline that discovers it is out
of time at the moment it is killed renders nothing, and a turn that renders
nothing is indistinguishable from a turn the ledger never saw.

Nothing here raises by itself. A stage asks for what remains and gets a number
that may be zero; the handler decides what an exhausted budget means, because
only the handler can still write the appendix that says so.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypeVar

T = TypeVar("T")


@dataclass
class Deadline:
    """How much of the turn's budget is left, from a monotonic clock."""

    seconds: float
    started: float = field(default_factory=time.monotonic)

    def remaining(self) -> float:
        """Seconds left, never negative."""
        return max(0.0, self.seconds - (time.monotonic() - self.started))

    def spent(self) -> float:
        return time.monotonic() - self.started

    def expired(self) -> bool:
        return self.remaining() <= 0

    def bounded(self, seconds: float) -> float:
        """A stage's own timeout, cut down to what the budget still allows."""
        return min(seconds, self.remaining())


class Overrun(Exception):
    """A stage did not finish inside the time it was given."""


def run_within(seconds: float, call: Callable[[], T]) -> T:
    """call()'s result, or Overrun, with the work abandoned rather than awaited.

    A socket timeout bounds one read, so a stage that blocks in many small
    pieces can outlive any per-read limit; a subprocess timeout bounds only
    that subprocess. This bounds the stage, whatever it is doing.

    The worker is a daemon thread, and that is the whole point rather than a
    detail. A concurrent.futures pool looks like it abandons work — shutdown
    with wait=False and cancel_futures returns at once — but the interpreter
    joins its workers at exit anyway, so the process lives as long as the call
    it stopped waiting for. Measured on 23 September 2026: a deadline that fired
    at 1.0s exited at 8.1s, the length of the call, which would hand the harness
    a hook to kill rather than an appendix to show. A daemon thread is not
    joined, so the deadline is also when the process can leave.
    """
    done = threading.Event()
    box: list[tuple[bool, object]] = []

    def run() -> None:
        try:
            box.append((True, call()))
        except BaseException as error:        # it travels back to the caller's thread
            box.append((False, error))
        finally:
            done.set()

    threading.Thread(target=run, daemon=True, name="claim-ledger-stage").start()
    if not done.wait(max(0.0, seconds)) or not box:
        raise Overrun(f"the stage passed its {seconds:.1f}s deadline")
    ok, value = box[0]
    if ok:
        return value  # type: ignore[return-value]
    raise value  # type: ignore[misc]
