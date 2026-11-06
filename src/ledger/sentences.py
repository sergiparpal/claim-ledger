"""A report cut into sentences, each one a verbatim slice of it.

The extractor is handed the report as these sentences, numbered, and answers
with numbers; the annotator is asked about the same sentences one at a time.
One cutter for both is what lets an extracted claim and an annotated one be
compared sentence for sentence. It is also why a claim's span is always text
the report holds: the span is the sentence, taken from the report by the
client, never copied out by the model.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

# A list marker, a heading or a quote opening a line is layout, not the claim.
_MARKER = re.compile(r"(?:[-*+]|\d+[.)]|#{1,6}|>)\s+")
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def split(text: str) -> list[str]:
    """The report cut into sentences, each one a verbatim slice of it.

    Lines first, since bullets and paragraphs end claims as often as full stops
    do, then sentences within a line. A list marker, heading or quote opening
    a line is left out of the slice, and a code fence or anything with no
    letter or digit is not offered at all. A cut in the wrong place costs the
    annotator a keystroke, because a span typed by hand can cross it.
    """
    out = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("```"):
            continue
        marker = _MARKER.match(line)
        if marker:
            line = line[marker.end():]
        for sentence in _SENTENCE_END.split(line):
            sentence = sentence.strip()
            if any(char.isalnum() for char in sentence):
                out.append(sentence)
    return out


def holding(span: str, text: str, cut: Sequence[str]) -> frozenset[int]:
    """The numbers of the sentences that hold a span: the ones it is, failing those
    the ones it is part of, and failing those the ones it overlaps in the report.

    A span is placed by its text, since an annotation names no position: one
    found in several sentences is held by each of them.
    """
    whole = frozenset(n for n, sentence in enumerate(cut, 1) if sentence == span)
    if whole:
        return whole
    within = frozenset(n for n, sentence in enumerate(cut, 1) if span in sentence)
    if within:
        return within
    places, crossed = _places(text, cut), set()
    for start in _occurrences(span, text):
        crossed |= _overlapped(start, start + len(span), places)
    return frozenset(crossed)


def reach(span: str, text: str, cut: Sequence[str], number: int) -> frozenset[int]:
    """The sentences a span covers where it touches sentence `number`: that one,
    and the ones beside it when the span crosses a cut. Empty when it does not."""
    places = _places(text, cut)
    first, last = places[number - 1]
    covered: set[int] = set()
    for start in _occurrences(span, text):
        end = start + len(span)
        if first < end and start < last:
            covered |= _overlapped(start, end, places)
    return frozenset(covered)


def _places(text: str, cut: Sequence[str]) -> list[tuple[int, int]]:
    """Where each sentence of the cut sits in the report, a slice of it, in order."""
    places, at = [], 0
    for sentence in cut:
        start = text.index(sentence, at)
        places.append((start, start + len(sentence)))
        at = start + len(sentence)
    return places


def _occurrences(span: str, text: str) -> list[int]:
    found, start = [], text.find(span)
    while start != -1:
        found.append(start)
        start = text.find(span, start + 1)
    return found


def _overlapped(start: int, end: int, places: Sequence[tuple[int, int]]) -> set[int]:
    return {n for n, (first, last) in enumerate(places, 1) if first < end and start < last}


def numbered(sentences: Sequence[str]) -> str:
    """The sentences as the extractor reads them: one a line, numbered from 1."""
    return "\n".join(f"[{number}] {sentence}"
                     for number, sentence in enumerate(sentences, 1))
