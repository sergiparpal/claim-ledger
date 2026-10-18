"""The claim vocabulary, and the validation of what the extractor returns.

FROZEN. The five types below are the closed vocabulary of the requirements'
Definitions. Nothing outside them may be assigned by any component, and a
change here changes what every measurement taken against it means.

The model is shown the report as numbered sentences and answers with numbers.
A claim's span is the sentence its number names, taken from the report here,
so a span is always text the report holds: the model never copies one out.

Two things can be wrong with a model's answer, and they end differently:

- The shape is wrong: not an object, no claims list, a claim that is not an
  object, a missing or extra field, a sentence that is not a whole number, a
  type outside the vocabulary. That is a schema failure. It raises, and the
  turn is UNKNOWN (R-12). Nothing is salvaged from an answer whose shape
  cannot be trusted, because a partial claim list read as complete is how
  coverage goes quietly blind.
- The shape is right, but a number names no sentence of the report. That one
  claim is dropped and counted as a defect, and the rest stands. It is an
  error rate to measure, never a number to guess at.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ledger import sentences

#: The closed vocabulary. The first three join against the evidence log; the
#: last two carry no evidence contract and are always NOT_CHECKABLE (R-20).
CLAIM_TYPES = ("command_run", "suite_passed", "file_changed", "judgment", "intent")
CHECKABLE_TYPES = ("command_run", "suite_passed", "file_changed")
CLAIM_FIELDS = frozenset({"sentence", "type", "referents"})


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
    """One assertion, and the sentence of the report that makes it."""

    span: str
    type: str
    referents: tuple[str, ...]
    provenance: Provenance


@dataclass(frozen=True)
class Defect:
    """A claim that was dropped, and why. Counted, never repaired.

    The span names what the model pointed at, a sentence number the report
    does not have, since there is no text of the report to show for it."""

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
    cannot know how many sentences the report has, which is why validate()
    still runs and the defect count still means something. No minimum is set
    on the number, since not every endpoint enforces one.
    """
    return {"type": "object", "additionalProperties": False, "required": ["claims"],
            "properties": {"claims": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": sorted(CLAIM_FIELDS),
                "properties": {"sentence": {"type": "integer"},
                               "type": {"type": "string", "enum": list(vocabulary)},
                               "referents": {"type": "array",
                                             "items": {"type": "string"}}}}}}}


def validate(payload: object, report_text: str, *, provenance: Provenance,
             vocabulary: Sequence[str] = CLAIM_TYPES) -> Extraction:
    """The claims of a validated answer, and the claims it cost to get there.

    The report is cut here exactly as it was cut for the request, so a number
    means here what it meant to the model."""
    if not isinstance(payload, dict):
        raise SchemaError(f"the answer is {type(payload).__name__}, not an object")
    if set(payload) != {"claims"}:
        raise SchemaError(f"the answer holds {sorted(payload)}, not one 'claims' key")
    listed = payload["claims"]
    if not isinstance(listed, list):
        raise SchemaError(f"claims is {type(listed).__name__}, not a list")

    cut = sentences.split(report_text)
    claims, defects = [], []
    for position, item in enumerate(listed):
        number, claim_type, referents = _fields(item, position, vocabulary)
        if not 1 <= number <= len(cut):
            defects.append(Defect(f"sentence {number}", f"the report has {len(cut)} "
                                  f"sentence{'' if len(cut) == 1 else 's'}"))
            continue
        claims.append(Claim(cut[number - 1], claim_type, referents, provenance))
    return Extraction(tuple(claims), tuple(defects), provenance)


def _fields(item: object, position: int, vocabulary: Sequence[str]) -> tuple[int, str, tuple]:
    where = f"claims[{position}]"
    if not isinstance(item, dict):
        raise SchemaError(f"{where} is {type(item).__name__}, not an object")
    if set(item) != CLAIM_FIELDS:
        raise SchemaError(f"{where} holds {sorted(item)}, not {sorted(CLAIM_FIELDS)}")

    number = item["sentence"]
    if not isinstance(number, int) or isinstance(number, bool):
        raise SchemaError(f"{where}.sentence is not a whole number")
    claim_type = item["type"]
    if claim_type not in vocabulary:
        raise SchemaError(f"{where}.type is {claim_type!r}, not one of {list(vocabulary)}")
    referents = item["referents"]
    if not isinstance(referents, list) or not all(
            isinstance(referent, str) and referent.strip() for referent in referents):
        raise SchemaError(f"{where}.referents is not a list of non-empty strings")
    return number, claim_type, tuple(referents)
