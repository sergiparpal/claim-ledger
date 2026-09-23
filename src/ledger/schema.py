"""The claim vocabulary, and the validation of what the extractor returns.

FROZEN. The five types below are the closed vocabulary of the requirements'
Definitions. Nothing outside them may be assigned by any component, and a
change here changes what every measurement taken against it means.

Two things can be wrong with a model's answer, and they end differently:

- The shape is wrong: not an object, no claims list, a claim that is not an
  object, a missing or extra field, a type outside the vocabulary. That is a
  schema failure. It raises, and the turn is UNKNOWN (R-12). Nothing is
  salvaged from an answer whose shape cannot be trusted, because a partial
  claim list read as complete is how coverage goes quietly blind.
- The shape is right, but a span is not in the report word for word. That one
  claim is dropped and counted as a defect, and the rest stands. A span that
  does not appear verbatim is an error rate to measure, never text to repair.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

#: The closed vocabulary. The first three join against the evidence log; the
#: last two carry no evidence contract and are always NOT_CHECKABLE (R-20).
CLAIM_TYPES = ("command_run", "suite_passed", "file_changed", "judgment", "intent")
CHECKABLE_TYPES = ("command_run", "suite_passed", "file_changed")
CLAIM_FIELDS = frozenset({"span", "type", "referents"})


class SchemaError(Exception):
    """The extractor's answer is not a claim list. The turn is UNKNOWN."""


@dataclass(frozen=True)
class Provenance:
    """Where a claim came from. Recall measured under one of these means nothing
    under another, so all of it travels with every claim and into the
    calibration log."""

    prompt_version: str  # the declared version and a hash of the prompt's own text
    model: str
    base_url: str
    provider: str        # the one that actually answered, as the reply names it


@dataclass(frozen=True)
class Claim:
    """One assertion, as the report words it."""

    span: str
    type: str
    referents: tuple[str, ...]
    provenance: Provenance


@dataclass(frozen=True)
class Defect:
    """A claim that was dropped, and why. Counted, never repaired."""

    span: str
    reason: str


@dataclass(frozen=True)
class Extraction:
    claims: tuple[Claim, ...]
    defects: tuple[Defect, ...]
    provenance: Provenance


def json_schema(vocabulary: Sequence[str] = CLAIM_TYPES) -> dict:
    """The shape an endpoint can be asked to enforce, from the same vocabulary.

    Enforcement is worth having — it ends code fences and stray keys — but it
    cannot make a span verbatim, which is why validate() still runs and the
    defect count still means something.
    """
    return {"type": "object", "additionalProperties": False, "required": ["claims"],
            "properties": {"claims": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": sorted(CLAIM_FIELDS),
                "properties": {"span": {"type": "string"},
                               "type": {"type": "string", "enum": list(vocabulary)},
                               "referents": {"type": "array",
                                             "items": {"type": "string"}}}}}}}


def validate(payload: object, report_text: str, *, provenance: Provenance,
             vocabulary: Sequence[str] = CLAIM_TYPES) -> Extraction:
    """The claims of a validated answer, and the claims it cost to get there."""
    if not isinstance(payload, dict):
        raise SchemaError(f"the answer is {type(payload).__name__}, not an object")
    if set(payload) != {"claims"}:
        raise SchemaError(f"the answer holds {sorted(payload)}, not one 'claims' key")
    listed = payload["claims"]
    if not isinstance(listed, list):
        raise SchemaError(f"claims is {type(listed).__name__}, not a list")

    claims, defects = [], []
    for position, item in enumerate(listed):
        span, claim_type, referents = _fields(item, position, vocabulary)
        if span not in report_text:
            defects.append(Defect(span, "not verbatim in the report"))
            continue
        claims.append(Claim(span, claim_type, referents, provenance))
    return Extraction(tuple(claims), tuple(defects), provenance)


def _fields(item: object, position: int, vocabulary: Sequence[str]) -> tuple[str, str, tuple]:
    where = f"claims[{position}]"
    if not isinstance(item, dict):
        raise SchemaError(f"{where} is {type(item).__name__}, not an object")
    if set(item) != CLAIM_FIELDS:
        raise SchemaError(f"{where} holds {sorted(item)}, not {sorted(CLAIM_FIELDS)}")

    span = item["span"]
    if not isinstance(span, str) or not span.strip():
        raise SchemaError(f"{where}.span is not a non-empty string")
    claim_type = item["type"]
    if claim_type not in vocabulary:
        raise SchemaError(f"{where}.type is {claim_type!r}, not one of {list(vocabulary)}")
    referents = item["referents"]
    if not isinstance(referents, list) or not all(
            isinstance(referent, str) and referent.strip() for referent in referents):
        raise SchemaError(f"{where}.referents is not a list of non-empty strings")
    return span, claim_type, tuple(referents)
