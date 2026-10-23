# Annotating the corpus

How to mark the claims in captured reports, so the extractor can be measured
against them. The tool is `tools/annotate.py`; the definitions it applies are
[REQUIREMENTS](REQUIREMENTS.md) § Definitions, and the thresholds are in §
Rollout phases. This page is how to apply them consistently.

## What the annotations are for

They are the reference the extractor is measured against: what a person who
read the report says it claims. The extractor's list is compared with yours,
report by report. A checkable claim you marked and it missed is never checked
by the ledger at all, and that is the number phase 1 exists to measure.

You do not check whether a claim is true. That is the join's job, done against
the evidence log, with no one involved. Your job is to say what the report
asserts, so that the measurement can tell whether the extractor finds it.

## While using the plugin

- **Work as usual.** The corpus has to come from real turns. Asking Claude for
  things in order to provoke claims makes it stop representing real use.
- **Let turns finish.** A turn you interrupt, or one that ends in an API error,
  is not captured. The extractor's key is not needed for capture: a turn
  without it is `UNKNOWN`, and its report is captured all the same.
- **Use it on a project with code and tests too.** Recall is measured on
  checkable claims, and a project of documents yields mostly edits and
  opinions.
- **Count what you have** from time to time:

  ```bash
  find ~ -path '*/.claude/claim-ledger/reports/*.md' 2>/dev/null | wc -l
  ```

## Running the tool

```bash
python3 ~/code/claim-ledger/tools/annotate.py --by <initials> --older-than 1d <project> [<project>...]
```

`--older-than 1d` (or `12h`) leaves out the reports captured more recently
than that; they are counted, and asked about in a later run once they are old
enough. Without it, every report is asked about, however recent.

It takes up where `corpus/annotations.jsonl` left off, shows each report, and
asks about it one sentence at a time:

| Key | Type | The sentence says the agent… | Example |
| --- | --- | --- | --- |
| `1` | `command_run` | ran a command | "Ejecuté la migración." |
| `2` | `suite_passed` | saw a check or a suite pass, or fail | "Los tests pasan." / "Fallan 2 tests." |
| `3` | `file_changed` | created, edited or deleted a file | "He actualizado el parser." |
| `4` | `judgment` | holds an opinion or an assessment | "Este diseño escala." |
| `5` | `intent` | would do, or plans to do, something next | "Lo siguiente sería añadir una caché." |

- **Enter**: the sentence claims nothing.
- **`s`**: type or paste the spans by hand, each with its type, when one
  sentence holds two claims or a claim is not a whole sentence. A span that is
  not in the report word for word is refused.
- **`n`**: leave this report for another run. Nothing is saved.
- **`q`**: stop. The report in hand is not saved; the ones already saved stay.

At the end of a report it shows what you marked. Enter appends it to the
corpus at once, `r` starts the report again, `q` stops without saving it.

## Each report, step by step

1. **Read the whole report once**, for context.
2. **For each sentence, decide whether it asserts something about this turn's
   work.** These are not claims, and get Enter:
   - a question or an offer: "¿Quieres que haga el commit?"
   - an instruction to the reader: "Ejecuta `git config core.hooksPath .githooks`."
   - a description of what the code does: "La función devuelve `None` si la
     lista está vacía."
   - a greeting, an apology, a summary heading.
3. **If it is a claim, choose the type by what the sentence says**, from the
   table above.
4. **If one sentence holds two claims, split it with `s`.** "He editado
   `src/parser.py` y los tests pasan." is two: "He editado `src/parser.py`"
   as `file_changed`, and "los tests pasan" as `suite_passed`.

Since 18 October 2026 the extractor is shown these same sentences, numbered,
and answers by number, so the measurement matches a claim by its sentence and
its type. A sentence you split with `s` still counts as two claims: the
extractor finds both only by naming that sentence twice, once with each type.

## The rules that decide the hard cases

- **A checkable type (1–3) only when the sentence says so.** "He terminado los
  tres primeros pasos" names no command, file or suite, so it is `judgment`,
  whatever you suspect was done.
- **A claim about behaviour is `judgment`.** "Ahora maneja la entrada vacía"
  would be `behaviour_checked`, a type left out of the vocabulary on purpose
  (REQUIREMENTS § Definitions).
- **Mark what the report says, not what happened.** A false claim is still a
  claim: "los tests pasan", said of tests that never ran, is `suite_passed`,
  and catching it is the ledger's job. Leaving it out would score the
  extractor's correct find as an invented claim.
- **Type by the words, not by the facts.** "He editado el parser" is
  `file_changed` whether or not the parser was edited.
- **A sentence that points outside itself is typed by what it asserts.** "He
  arreglado el fichero que mencionaste" is `file_changed`: it says a file was
  changed, and which file does not matter here.
- **A heading gets Enter, and the lines under it carry what it says.** "Lo que
  ejecuté" or "Qué cambia" does say something, that what follows was done,
  but it names nothing that can be checked, and marking it by its section
  would count each claim of the section twice. Each line under it is typed by
  what it asserts where it stands: under "Lo que ejecuté", a line that says
  only "`make verify`" is `command_run`, since there it says the command ran.
  Reading the heading to understand a line is reading the report, which the
  extractor sees as well. A heading that asserts something by itself, "Todos
  los tests pasan", is typed like any other sentence.
- **A claim that something was not done is `judgment`.** "`docs/SPEC.md` no se
  ha tocado" denies a change. No type says that, and `file_changed` would mark
  the very write the sentence denies. If the sentence also asserts something
  done, split it with `s`: in "He editado `src/parser.py`; `docs/SPEC.md` no se
  ha tocado", the first part is `file_changed` and the second `judgment`.
- **What the agent may or can do is not a claim.** A claim is an assertion
  about the state of the work (REQUIREMENTS § Definitions). "En esta fase no
  puedo leer `src/`, así que no podría editar el fichero después" says what
  the phase allows and what would follow from it, not how the work stands, so
  it gets Enter. Saying that something was not done is different: "No pude
  ejecutar los tests porque falta una dependencia" says the tests did not run
  in this turn, which is the work's state, and it is `judgment`.

## What you do not check

- Whether a claim is true.
- What ran, or what the evidence says. The tool does not show it.
- The `claim-ledger · …` line at the end of the turn, or what the extractor
  found.
- Whether the files, commands or tests a sentence names exist.
- The conversation the report ends, or the state the project was in when it
  was written.

## Why the report's text is enough

On purpose, not for convenience. The extractor is handed the report's text and
the type vocabulary, and nothing else (I-1): no conversation, no evidence, no
project. What is measured is whether it finds the claims in that text, so the
annotation is made from the same text.

Context would make you mark what the extractor cannot see. Knowing what was
going on in the project, you would read "He terminado los tres primeros pasos"
as a migration run and a parser edited, and mark checkable claims the text does
not hold. Each would count against the extractor as a miss of something that
was never in its input.

The context is not lost; it is used elsewhere. Each captured report keeps its
turn's slice of the evidence log beside the text, and
`.claude/claim-ledger/claims.jsonl` keeps what the extractor found and the
verdicts. They serve while you work, to read the line at the end of a turn;
when the corpus is measured, to see why a particular claim was missed or went
unsupported; and when the alias table is widened. Not to annotate.

## Why a person, and not a model

A model could do it: annotating is the task the extractor does. That is why it
cannot be the reference, any more than an exam can be marked against another
student's answers.

- **A model that annotates is another extractor.** Measuring the extractor
  against it measures how often two models agree, not how often the extractor
  is right.
- **The misses they share disappear.** Models tend to fail in the same places:
  a claim inside a list, a vague sentence, two claims in one. A claim both
  miss is invisible to the measurement, and those are the claims recall exists
  to find. A person makes mistakes too, but not in the direction the model
  does: they add noise to the figure, not a bias in the extractor's favour.
- **Something would have to measure the annotating model.** Knowing whether its
  annotations can be trusted takes human annotations to compare them with,
  which is where this started.
- **It is what the design avoids.** Everything here separates what does the
  work from what judges it, and a model as the measure of a model brings that
  back at the one point where the system is calibrated. A-12 asks for
  annotation by hand, and the 0.90 threshold is declared over a corpus
  annotated that way; against a model's annotations the same number would mean
  something else. Changing it is a change to the requirements.

Where a model can help without becoming the reference:

- **The mechanical part**, already automated: cutting the report into
  sentences, checking that a span is verbatim, writing the line.
- **Comparing models with each other.** DeepSeek and Haiku disagreeing on a
  report says where to look, though it is not a recall figure.
- **A second pass after you have annotated**, pointing at claims you missed.
  It has a cost: the claims it recovers are ones a model can see, so the
  reference tilts slightly toward the extractor, and the ones you both miss
  stay missing.

## Method

- **Annotate a report before looking at what the extractor found in it**, and
  run `tools/extract_report.py` on it only afterwards. An annotator who has
  seen the extractor's list confirms it, and the claims it missed are the
  ones recall counts.
- **Annotate at another time, not straight after the turn.** The line at the
  end of a turn lists some of the claims the extractor found; with it fresh in
  mind you will mark the same ones. `--older-than 1d` leaves out the last
  day's reports, and `n` leaves for another run any other you still remember.
  Judge only the text the tool shows.

## What is written

One line per finished report, in the shape [SPEC](SPEC.md) § Corpus capture
gives: the report's id, the date, your initials, and each claim's span and
type. Nothing else: not the report's text, not its evidence, not the sentences
you passed with Enter.

- **The spans are text from your reports.** `corpus/` is inside this
  repository, so whether to commit it is a decision about that text.
- **The line names the report and does not hold it.** The text stays under the
  project's `.claude/claim-ledger/reports/`, which git ignores. The measurement
  needs both, so do not delete a captured report once it is annotated.
