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


def numbered(sentences: Sequence[str]) -> str:
    """The sentences as the extractor reads them: one a line, numbered from 1."""
    return "\n".join(f"[{number}] {sentence}"
                     for number, sentence in enumerate(sentences, 1))
