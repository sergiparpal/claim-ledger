# A review step for the extractor's precision

A design note, 6 November 2026. Nothing here is in the pipeline. It says what
would be built, why, what it must not break, and how it is measured before
anyone decides to build it.

## The problem

Phase 1 asks for recall of 0.90 or better on checkable claims and a spurious
share of at most 0.10 of everything extracted (REQUIREMENTS § Rollout
phases). The route in the hook, `mistral-medium-3.1` with `extract-6c`, finds
0.78 to 0.81 of the reference's checkable claims, and 0.47 to 0.49 of what it
extracts matches nothing in the reference. Four other routes, the same route
with two more rules, and the same route given the whole guide as its prompt all
stay between 0.43 and 0.49 (DECISIONS, 5 and 6 November). Against the user's
own annotations the share is 0.36 to 0.45. Recall is near; the spurious share
is four or five times the limit, and neither the wording nor the model moves
it.

About two in three of those claims fall in sentences the reference leaves
unmarked, mostly lines that describe code, tests or cases and lines under a
lead line; the rest are typed otherwise than the reference types them. One
reading of the whole report at once marks too much. A second reading that
only judges what the first marked may mark less.

## The proposal

After the extraction call, a second call on the same route reviews its answer.

- **What it is given.** The report, cut and numbered as the extractor reads it,
  the type vocabulary with the typing rules the extractor's prompt carries, and
  the first call's claims, each as its sentence's number and its type. Nothing
  else: not the turn's evidence, not the transcript, not a file.
- **What it does.** For each claim it says whether that sentence makes that
  assertion, of that type, by the rules. It answers with the claims to drop,
  as a JSON object the endpoint holds to a schema: `{"drop": [3, 7]}`.
- **What it may not do.** It never adds a claim and never changes a type. A
  claim of the wrong type is dropped, and the right one is kept only if the
  first call made it too. The step can only shorten the list.
- **When it is unsure.** It drops a claim only when the rules say that sentence
  does not make that assertion; where the rules leave it open, it keeps it.

The kept claims go to the join as the extractor's do now. A dropped claim is
never checked, as a claim the extractor missed is not.

## What it must not break

- **I-1 Separation.** The reviewer is part of the extractor. It sees the report,
  the vocabulary and an answer derived from the report and nothing else, so it
  never sees what ran. Whether an answer about the report counts as part of the
  report's text for I-1 is the user's reading to give.
- **I-2 Downgrade only.** Dropping a claim cannot produce `VERIFIED`: it can
  only remove a claim from the join. A dropped true claim is a recall loss,
  which the measurement counts.
- **I-3, I-4, I-5.** Untouched: the verdict table, the scope of a verdict and
  the weakest link do not change.
- **I-9 Failure is visible.** A review that fails, times out or answers out of
  shape makes the turn `UNKNOWN`, as a failed extraction does. The first call's
  answer is not used unreviewed, since that would make the review optional
  where it is slow.
- **I-10.** The report is not edited.

## Time

The turn has 20 seconds for the extractor, inside a budget of 23 and a hook
timeout of 28. The first call takes 4.1 seconds at the median and 11.8 at the
95th percentile on the corpus. The review sends the same report and a list of
claims, and answers with a few numbers, so its time should be mostly the
reading: a second or two. Both calls must fit inside the same 20 seconds; on
the slowest reports they may not, and the measurement says how often.

## How it is measured, before anything is built

The corpus runs keep each answer as its sentence numbers and types. The review
can be run on those stored answers without extracting again.

1. **One pass.** Review the answers of one stored pass of `extract-6c` on the
   corpus, 81 calls on the route in the hook, for about $0.15. Score the kept
   claims against the reference as every candidate is scored: recall, the
   spurious share, by type, and the time each review took.
2. **If it helps,** review the other two passes and the holdout's three, and
   judge it by its worst pass, as phase 1 judges a route.
3. **Then** the user decides whether the step goes into the pipeline. That
   would change SPEC § Extractor contract and the hook's timing, and possibly
   R-45.

What would count as helping: a spurious share well below the 0.47 to 0.49 of
the stored passes, for a recall loss of a few hundredths at most. A review that
cuts both together is the route being more cautious, which the screen of 25
October already showed costs recall as fast as it saves precision.

## Not decided here

- Whether the review covers every claim or the checkable ones only. Phase 1's
  spurious share counts every type, and the join only checkable ones; the
  first measurement reviews every claim, and reports both.
- Whether the reviewer is the same route as the extractor. The first
  measurement uses the same route, so that only the step is new.
- The review prompt's wording. The first one carries `extract-6c`'s typing
  rules unchanged, so that the reviewer judges by the rules the extractor was
  given.

## Measured, 6 November 2026

The review prompt is `src/ledger/prompts/review-2.md` (`review-2+c0704259`):
`extract-6c`'s typing rules unchanged, the claims given one a line with their
sentence repeated after a bar, and one verdict asked for each claim, keep or
drop. A first wording, `review-1`, asked for the numbers of the claims to drop.
On its first report it answered with sentence numbers instead, and it was
replaced before any measurement.

The route in the hook reviewed the 80 answers of the first stored pass of
`extract-6c` on the corpus, for $0.16. The four reports of the anchor and the
six with the most spurious claims went first, as samples, and are part of the
pass. No review was refused or answered out of shape.

| The first pass of `extract-6c` on the corpus | Before the review | After it |
| --- | --- | --- |
| Recall on checkable claims | 0.78 | 0.58 |
| Spurious share | 0.47 | 0.38 |
| `command_run`, `suite_passed`, `file_changed` found | 127, 332, 317 | 85, 255, 238 |
| Claims | 2,498 | 1,776 |

The review dropped 722 claims. 495 of them matched nothing in the reference,
and 227 were claims the reference makes: 94 `suite_passed`, 80 `file_changed`,
42 `command_run` and 11 `judgment`, 58 of them rows of tables. Most are the
readings the guide's finer rules create: what a run returned, typed
`command_run`, lines that say how a file's content changed, and rows that say
which tests catch a case. Some are plain, such as a line saying two checks
came out clean.

It is the route being more cautious, which this note said would not count as
help: the spurious share falls by nine hundredths and recall by twenty. A
second reading by the same model, given the same rules, applies them no
better than the first did. It also takes time the turn does not have: a median
of 3.7 seconds a review, 19.8 at the 95th percentile and 54.8 at the slowest,
with 4 of the 80 past 20 seconds before the extraction's own time is added.

So the review step, on this route and with this prompt, falls short of what
this note asked of it, and it is not proposed for the pipeline; the other
passes and the holdout were not reviewed. A reviewer of another family, or
one asked about one claim type at a time, was not tried.
