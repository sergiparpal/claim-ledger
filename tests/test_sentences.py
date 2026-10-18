"""ledger.sentences: one cut of the report, for the extractor and the annotator.

What is tested is what the sentence contract stands on: every sentence is a
verbatim slice of the report, so a span taken from one is always text the
report holds; the extractor and the annotator cut the same report the same
way, so their claims can be compared sentence for sentence; and the numbering
the model reads is the numbering the answer is read back with.
"""

import sys
import unittest
from pathlib import Path

from ledger import extract, schema, sentences
from tests.test_extract import SETTINGS

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

import annotate  # noqa: E402

WHERE = schema.Provenance("extract-2+test", "a-model", "https://example.invalid", "a-provider")
REPORT = """He hecho el commit 3 (`715e123`), sin push. `make verify` sale con código 0.

**Qué cambia:**
- **`docs/SPEC.md`**: en Interfaces he añadido las cuatro firmas. No he tocado nada más.
1. Dice que `selection` contiene «`pair_of`, `judge`».
## Salida
> «All checks passed!» de ruff.

```
make verify
```
---
¿Lo actualizo? Dime."""


class SplitTest(unittest.TestCase):
    def test_every_sentence_is_a_verbatim_slice_of_the_report(self):
        cut = sentences.split(REPORT)
        self.assertGreater(len(cut), 5)
        for sentence in cut:
            with self.subTest(sentence=sentence):
                self.assertIn(sentence, REPORT)
                self.assertEqual(sentence, sentence.strip())
                self.assertNotIn("\n", sentence)

    def test_the_cut_is_the_one_the_annotator_is_asked_about(self):
        self.assertEqual(sentences.split(REPORT), [
            "He hecho el commit 3 (`715e123`), sin push.",
            "`make verify` sale con código 0.",
            "**Qué cambia:**",
            "**`docs/SPEC.md`**: en Interfaces he añadido las cuatro firmas.",
            "No he tocado nada más.",
            "Dice que `selection` contiene «`pair_of`, `judge`».",
            "Salida",
            "«All checks passed!» de ruff.",
            "make verify",
            "¿Lo actualizo?",
            "Dime."])

    def test_extractor_and_annotator_share_one_cut(self):
        self.assertIs(annotate.pieces, sentences.split)

    def test_nothing_without_a_letter_or_digit_is_a_sentence(self):
        self.assertEqual(sentences.split("```\n---\n- \n…\n"), [])


class NumberedTest(unittest.TestCase):
    def test_the_model_reads_one_numbered_sentence_a_line(self):
        self.assertEqual(sentences.numbered(["Uno.", "Dos."]), "[1] Uno.\n[2] Dos.")
        self.assertEqual(sentences.numbered([]), "")

    def test_a_number_read_back_names_the_sentence_the_model_was_shown(self):
        cut = sentences.split(REPORT)
        shown = extract.build_request(REPORT, vocabulary=schema.CLAIM_TYPES,
                                      settings=SETTINGS, prompt=extract.load_prompt())
        lines = shown.body["messages"][0]["content"].split("\n")
        answer = {"claims": [{"sentence": n, "type": "judgment", "referents": []}
                             for n in range(1, len(cut) + 1)]}
        read_back = schema.validate(answer, REPORT, provenance=WHERE)
        for number, (line, claim) in enumerate(zip(lines, read_back.claims, strict=True), 1):
            with self.subTest(line=line):
                self.assertEqual(line, f"[{number}] {claim.span}")

    def test_the_prompt_tells_the_model_the_numbering_it_will_see(self):
        text = extract.load_prompt().text
        self.assertIn("[1], [2]", text)
        self.assertIn('"sentence": 2', text)
        self.assertNotIn('"span"', text)


if __name__ == "__main__":
    unittest.main()
