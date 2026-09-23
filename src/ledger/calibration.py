"""The durable claims-and-verdicts log.

Every claim of every turn, with its type, verdict and scope, appended to
.claude/claim-ledger/claims.jsonl and never rewritten (R-34). This is the file
that eventually lets something above a heuristic exist, and until it reaches
the sample size declared in advance it only records: no hit rate, no
confidence, no probability is computed from it (R-36).

A claim found false afterwards is marked by appending, not by editing (R-35).
An annotation row names the claim id it annotates, so history stays as it was
written and the later knowledge sits beside it. That is why every claim row
carries an id that can be written down: <session>-<turn_number>-<index>.

What the extractor route was travels with each row, because recall measured
under one route says nothing under another (R-45). So does a defect: a span
the model returned that the report does not contain is part of the error rate
phase 1 exists to measure, and a defect count with nowhere to live disappears.

The same append discipline as the evidence log: one write() per row on an
O_APPEND descriptor, no read-modify-write, no lock.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Iterable, Sequence
from datetime import datetime
from pathlib import Path

from ledger import evidence, join, record, schema

CLAIMS_LOG = evidence.STATE_DIR / "claims.jsonl"
ROW_VERSION = 1


def claims_log(root: Path) -> Path:
    return root / CLAIMS_LOG


def claim_id(session: str, turn_number: int, index: int | str) -> str:
    """A name for one claim that an annotation written later can still find."""
    return f"{session}-{turn_number}-{index}"


def rows(judged: Sequence[join.Judged], defects: Sequence[schema.Defect], *,
         session: str, turn_id: str | None, turn_number: int,
         now: datetime) -> list[dict]:
    """One row per claim, then one per defect, in the order they were made."""
    stamped = record.iso(now)
    common = {"v": ROW_VERSION, "ts": stamped, "session": session,
              "turn_id": turn_id, "turn_number": turn_number}
    out = []
    for index, one in enumerate(judged):
        out.append({**common, "row": "claim",
                    "claim_id": claim_id(session, turn_number, index),
                    "span": one.claim.span,          # whole, never elided (the appendix elides)
                    "type": one.claim.type,
                    "referents": list(one.claim.referents),
                    "verdict": one.verdict,
                    "scope": one.scope,
                    "position": one.position,
                    "route": dataclasses.asdict(one.claim.provenance)})
    for index, defect in enumerate(defects):
        out.append({**common, "row": "defect",
                    "claim_id": claim_id(session, turn_number, f"d{index}"),
                    "span": defect.span, "reason": defect.reason})
    return out


def append(root: Path, entries: Iterable[dict]) -> None:
    """Append rows to the calibration log, one write() each."""
    log = claims_log(root)
    for entry in entries:
        evidence.append(log, entry)


def annotate(root: Path, claim: str, *, outcome: str, by: str,
             now: datetime, note: str | None = None) -> dict:
    """Mark a claim's later outcome without rewriting the row it annotates (R-35)."""
    entry = {"v": ROW_VERSION, "ts": record.iso(now), "row": "annotation",
             "annotates": claim, "outcome": outcome, "by": by}
    if note is not None:
        entry["note"] = note
    evidence.append(claims_log(root), entry)
    return entry


def read(root: Path) -> list[dict]:
    """Every row, in the order they were appended. Nothing is skipped or repaired."""
    log = claims_log(root)
    try:
        raw = log.read_bytes()
    except FileNotFoundError:
        return []
    lines = raw.split(b"\n")
    if lines[-1]:
        raise evidence.EvidenceError(f"{log}:{len(lines)}: last row has no line end")
    out = []
    for position, line in enumerate(lines[:-1], 1):
        try:
            out.append(json.loads(line))
        except ValueError as e:
            raise evidence.EvidenceError(f"{log}:{position}: not a JSON row") from e
    return out
