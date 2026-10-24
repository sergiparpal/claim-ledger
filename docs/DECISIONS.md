# Decisions — claim-ledger

The reasons that exist nowhere else.

A decision whose reason is already in a docstring, in `SPEC.md` or in
`REQUIREMENTS.md` is not repeated here: two copies of a reason is how one of
them comes to be wrong, and this file is the one nobody would notice had gone
stale. What belongs here is the decision a maintainer could undo without any
test failing, because the reason for it was never written down.

Build status is not here. `SPEC.md` § Build order says what is built,
`README.md` says what the plugin does and what it does not do yet, and
`OPERATING.md` says how to run it.

**Entries leave when their reason finds a home.** On 23 September 2026 the join
taking the last matching record, and the `LOW` half of the tier rule, both moved
into `SPEC.md`: they are behaviour someone can reason backwards from, which
makes them specification rather than folklore. An entry disappearing from here
is usually that, not a decision reversed.

**On the dates.** They are when the decision was written down, not always when
it was taken. Entries carried over from the handover this file replaces are
dated 23 September 2026; the build they came out of ran from 19 to 23 September
and finer dates are not recoverable from anything left behind.

## Decisions that exist only as code

### The refusal writes nothing at all, not even `errors.log` — 23 September 2026

While git would commit `.claude/claim-ledger/`, the recorder and the Stop
handler write no file of any kind and return a `systemMessage` instead.

The tempting repair is to at least log the refusal. `errors.log` lives in the
directory being refused, so writing it is the thing being refused. Stderr is no
better: on a hook that exits 0 it reaches only the debug log, which makes the
refusal silent, which is how a ledger ends up installed and inert.

### Tests are checked by mutation, every session — 23 September 2026

New code is broken one way at a time in a scratch copy, and the suite must fail
for each break. A mutant that survives is a missing test, not a curiosity.

This is the practice that keeps the suite from being decoration, and it is
written nowhere in the test plan. Eight mutants have survived so far — three
before 23 September 2026, five on it — and every one of them was a test that
did not exist. The five: coverage reading the whole session rather than the
turn, the model call ignoring what the budget had left, an unparseable
`errors.log` line being skipped, the config baseline never being seeded, and a
failing suite being reported as a pass.

## Tried, measured and rejected — do not re-run these

Every number behind these, and behind the current pin, is in
`docs/provider-measurements.md` with its date and conditions. That file is what
decides the next pin when `morph` fails the way `phala` did. It cannot be
re-derived from the repository and it goes stale.

### `openai/gpt-5.6-luna` — refused 21 September 2026

The fastest and cheapest of the three, with no defects, and unusable anyway.
GPT-5.x accepts neither `temperature` nor `top_p`: with `require_parameters` on,
sending either returns **404 from routing** before the model is reached. Sampling
that cannot be pinned gave three different answers across seven runs, twice with
a fourth claim. An extractor that varies cannot carry a recall figure.

Reasoning effort `"none"` is accepted there and still emits `redacted_thinking`.

### `z-ai/glm-5.3-flash` — replaced 21 September 2026

Correct and stable, and too slow to exist inside a turn: about 5,000 thinking
tokens on a 442-character report, 49.8 seconds against a 15-second budget.
Thinking cannot be switched off from this endpoint — `reasoning: {"enabled":
false}` is accepted and ignored.

Its recording is kept as `openrouter-glm-5.3-flash.json`, because it is the only
one in the fixtures that carries a thinking block, and the client's handling of
one would otherwise be untested.

### The assistant prefill, on this route — 20–21 September 2026

OpenRouter returns a whole object and ignores a prefilled assistant turn, so the
opening brace the client adds makes `{{`. `answer_shape = "prefill"` stays in
the loader for a route that honours it; on this one the answer shape is enforced
with `output_config` instead. The exact day is not recorded.

### `phala/fp8` — 20 September 2026

Returned HTTP 400 twice to a body that had worked minutes earlier. The pin moved
to `baseten/fp8`, and then to `morph` when the model changed. This is the failure
the provider-measurements table exists to answer quickly.

### The providers that accept `enable_thinking` and ignore it — 21 September 2026

DeepInfra, Fireworks, Together and AtlasCloud all took the switch and reasoned
anyway, at 2,000 to 5,100 thinking tokens and 25 to 67 seconds. Both providers
that declare fp8 are among them. Only `morph` returned a reply with no thinking
block at all, and `morph`'s quantization is undeclared — that is the price of
the switch working.

The top-level `chat_template_kwargs` shape, rather than under `extra_body`, is
ignored too. `novita/fp8` 404s under `require_parameters`.

**The rule this gives**: a parameter accepted is not a parameter honoured. Verify
against the reply, never against the status code.

### The Claude Code CLI as an extraction transport — 20 September 2026

Used in build step 6, before an API key existed on this machine. The CLI cannot
prefill an assistant turn, so its answers are whole objects from a route the
client no longer uses. Its recordings are the `cli-no-prefill-haiku*.json`
fixtures, kept as recordings rather than edited into the shape now sent: the
tests assert what the client does with them today, which is refuse them.

## Measured, and still open

### The alias table is a measurement target — 23 September 2026

The first live end-to-end turn: the report said "I updated src/parser.py and the
tests pass", the evidence log held a passing `python-suite` run, and the suite
claim came back `UNSUPPORTED`. The extractor returned the referent `tests`;
`[checks.aliases]` declares `"the tests"` and not bare `"tests"`, so the referent
named something, resolved to nothing, and stayed unsupported.

That is the rule working. It refused to fall back to the only check in the
session, which is exactly the fallback that manufactures a false `VERIFIED`.

But it makes the alias table an instrument rather than a convenience, and it is
not one that should be tuned from single observations. Collect what real reports
actually say during the corpus phase, then widen it once, deliberately. The file
is the user's (I-8).

### A command claim links only when the report names the command — 6 October 2026

The first audited turn in distiller, from the desktop app: the report said "Hice
el commit `2cbb88c` en una rama nueva, `spec-slice-1`, …", the evidence log held
`git switch -c spec-slice-1 && git add docs/SPEC.md && git commit …`, ok, in the
same turn, and the commit is in the repository. The claim came back
`UNSUPPORTED`. The extractor typed it `command_run` with the referents
`2cbb88c`, `spec-slice-1` and `main`, which is what its prompt asks for: the
names the sentence gives, never resolved.

`names_command` links a referent to a recorded command only when its first token
is the command's first token and every further token is in the command. A hash
or a branch is never a command's first token, and "hice el commit" names no
command at all. So a true claim about a command, worded the way reports word
them, stays unsupported.

That is the rule erring in the right direction (I-2): resolving "the commit" to
whichever git command happened to run is how a claim about one command gets
verified against another. Recall will not show it, since the claim was found
and typed right; it shows in the verdicts, as `UNSUPPORTED` on a command the
log holds. Like the alias table, count it during the corpus phase rather than
tune it from one turn. `join.py` is frozen, so any change there is the user's.

A later turn showed the same rule missing compound commands: "usé pytest
9.1.1, pytest‑cov 7.1.0 y coverage 7.16.2 …" against more than twenty recorded
commands that ran pytest after a `cd … &&`, inside a `for` loop or behind a
variable assignment. None begins with `pytest`, and a report seldom names a
command by its first word as it was typed.

On 17 October 2026 a report named a command exactly as it was typed, and the
rule missed it all the same. "`make protected REF=main`: sin salida." came back
`UNSUPPORTED` against `make protected REF=main; echo "protected exit=$?"; make
verify …`, ok, in the same turn. The recorded line is split on whitespace, so
its third token is `REF=main;`, with the operator attached, and `REF=main` is
not among its tokens. The verdict errs the safe way, but not for the rule's
reason: nothing in that claim was ambiguous.

### A claim about a tool the log does not record is always unsupported — 6 October 2026

A later turn in distiller said "Por eso comparé `HEAD` con el commit anterior,
`7cd4728`, para que el análisis cubra el commit de la spec." It was true: the
agent had called semantic-diff-weaver's MCP tool on `7cd4728` and `HEAD`. It came
back `UNSUPPORTED`, "no matching command in this session", and nothing else was
possible: the recorder's matcher is `Bash|Edit|Write|NotebookEdit` (SPEC § Hook
wiring), so an MCP call, like a Read, a WebFetch or any other tool, leaves no
record for a claim to join.

That is I-2 working too: a claim nothing in the log can support is
`UNSUPPORTED`, never a guess. But it is a different gap from the entry above.
There the record existed and the referents did not reach it; here there is no
record, and no wording of the claim would change that. How often it happens
depends on the tools a session has loaded, so a session with MCP servers shows
more true claims as `UNSUPPORTED` than one without.

Widening the matcher would record those calls, but `command_run` joins on a
command line and an MCP call has none. What such a record would hold, and what
a claim would have to name to reach it, is open. Count these during the corpus
phase, apart from the referent misses above, before deciding anything.

### A sentence can be typed as a file change it does not claim — 7 October 2026

A turn in distiller ended "Está en la rama local `spike/junit-coverage-contexts`
(commit `b96de07`, sin push), y `docs/SPEC.md` no se ha tocado." The extractor
typed the sentence `file_changed`, with `docs/SPEC.md` among its referents, and
the join found no write of that file in the session: `UNSUPPORTED`, "no record
of that file being written". It read as the agent claiming an edit it never
made. The sentence claimed the opposite, and the log agreed with it.

The vocabulary has no type for "I did not change X", and the prompt sends a
sentence that fits none of the checkable types to `judgment` or `intent`. So
this is a typing error by the extractor, and the measurement will count it as
one: the annotation guide says a claim that something was not done is
`judgment`. The prompt and the vocabulary are frozen; this is measured, not
fixed.

It matters beyond the noise. `file_changed` is joined against the whole
session's log, not the turn's slice: had `docs/SPEC.md` been written in an
earlier turn of the session, the same sentence would have come back `VERIFIED`,
verifying the opposite of what it says. That is the false `VERIFIED` the
prompt's "never guess upward" exists to prevent, so the corpus should show how
often a negation reaches a checkable type.

The same day a sentence with no negation and no file in it reached
`file_changed` too: "`f8edf74` es ahora `879625e`, en
`spec/junit-coverage-spike`.", about a commit the turn had rewritten with `git
commit --amend`. Its referents were the two hashes and the branch; a branch
named like a path is the likely trigger. It came back `UNSUPPORTED` only because
nothing was written at a path with one of those names. By the guide's rules it
is `judgment`: it names no file, and no command either.

The false `VERIFIED` this entry warns about had already happened, the day
before it was written, and gone unnoticed. A report on 6 October 2026 said
"Hice los cuatro cambios en [docs/SPEC.md](docs/SPEC.md). No toqué el Bet, los
no-objetivos ni los 8 `<TO FILL>`, y no he hecho commit." The extractor gave the
second sentence a claim of its own, typed `file_changed`, with `docs/SPEC.md` as
its referent, carried over from the sentence before. Every clause of it denies
an action, and it came back `VERIFIED` on the strength of the write the first
sentence claimed. On 17 October 2026 it happened again: "No he tocado nada
más.", closing a bullet headed `docs/SPEC.md`, typed and given its referent the
same way, came back `VERIFIED` against that turn's write of the SPEC. That one
was true, since the commit the turn made, `715e123`, adds four signatures to
the SPEC and nothing else; whether the first was true was not checked. Either
way the verdict could not tell: the log shows that a file was written, never
what was left alone, so a negation that reaches `file_changed` comes back
`VERIFIED` whenever its file was written at all.

Neither showed in the appendix, which counts `VERIFIED` claims and never lists
them; both were found by reading `claims.jsonl`. So were five more sentences
that claim a change and add "no he hecho commit" or "sin commit", a second
assertion the extractor left in the same span, `VERIFIED` on the strength of
the first.

### A file claim links only when it names the recorded path — 7 October 2026

A turn in distiller said "Contiene las dos tandas de cambios del SPEC (14 líneas
añadidas …) y no queda nada pendiente en el árbol de trabajo." `docs/SPEC.md`
had been edited ten times earlier in the session, and the commit the turn
amended holds that change. The extractor returned the referent `SPEC`, as the
sentence names it, and the claim came back `UNSUPPORTED`, "no record of that
file being written". Whether the sentence is a file claim at all, or a
description of the commit, is the annotator's call; the link failed either way.

`names_path` links a referent to a write only when it equals the recorded path,
project-relative and whole: `docs/SPEC.md` is reached by `docs/SPEC.md` and by
nothing else, not `SPEC.md` and not `SPEC`. Reports name files the way people
talk about them, and the log holds paths. This is the alias table's problem
again, for files rather than checks.

The direction is the same one: resolving "the SPEC" to whichever written file
looks like it is how a claim about one file gets verified against another, and
a match on the file name alone would join `README.md` to every README in a
repository. Count it during the corpus phase with the other referent misses;
`join.py` is frozen.

### A claim is verified when any one of its referents is — 17 October 2026

A report in distiller said "`make protected REF=main` y `make verify` salen con
código 0." The extractor typed it `command_run` with both commands as its
referents, the log held one line that ran them both, `make protected REF=main;
echo "protected exit=$?"; make verify …`, ok, and the claim came back
`VERIFIED`. Further down, the same report said "`make protected REF=main`: sin
salida.", with that referent alone, and it came back `UNSUPPORTED`, for the
reason given under the command entry above. So the first claim was verified on
`make verify` alone.

`names_command` and `names_path` link a claim to a record when any one of its
referents reaches it, and `_suite` does the same in its own terms: a referent
that resolves to no check is dropped as long as another one resolves. The rule
in the module's docstring, that a referent which names something and resolves
to nothing is `UNSUPPORTED`, holds only for a claim with one referent. With two,
one found and one not, the claim takes the stronger verdict, and I-2 resolves
every ambiguity to the weaker.

It is not rare. Up to 17 October 2026, 20 `command_run` and `file_changed`
claims in distiller named two referents or more. Six came back `VERIFIED`, and
each of the six had a referent that the record which verified it does not hold;
in five of them that referent reaches nothing in the log at all. "El commit solo
incluye `docs/SPEC.md`, el árbol de trabajo queda limpio y `main` sigue en
`7cd4728`." was verified by a write of `docs/SPEC.md`, with `main` and `7cd4728`
reaching nothing. In the `make` case the other half was true, since both
commands are on the line that was found, but nothing in the join checked that.

No test pins it, either way. The property test in `test_join` gives each claim
zero referents or one, and a mutant that requires every referent to reach the
same record passes the whole suite, 321 tests on Python 3.12, on 17 October
2026. Requiring it is not free: all six claims would have come back
`UNSUPPORTED`, the true `make` claim among them, because the extractor's
referents include hashes, branches and identifiers that no record holds. Which
way to pin it is the user's; `join.py` is frozen.

A seventh came that afternoon, at 13:16 UTC, in another session: the same two
`make` targets as referents, verified against `make verify 2>&1 | grep …; echo
…` alone. `make protected REF=main` had run three times in that session, each
time as `make protected REF=main; echo …`, so the `;` described under the
command entry kept it from linking there too. Of the 21 claims with two
referents or more up to 18 October 2026, all 7 that came back `VERIFIED` rest on
part of what they name. `tools/daily_use.py verdicts` lists them.

### A write through Bash is invisible to file claims and to coverage — 17 October 2026

A report in distiller said "nueva D-004 con el contexto, lo elegido, lo
rechazado (…) y las consecuencias.", under a bullet headed `docs/DECISIONS.md`.
The extractor typed it `file_changed` with that exact path, and it came back
`UNSUPPORTED`, "no record of that file being written". The log held `cat >>
docs/DECISIONS.md <<'EOF'`, ok, in the same turn, and the commit the turn made,
`715e123`, holds the new entry.

The recorder takes `files` from the input of Edit, Write and NotebookEdit. A
Bash call that is not a check is recorded as `kind: other`, with its command
line cut at the first newline (R-7) and no `files` at all, and `names_path`
reads only mutation records. So no wording of a file claim reaches a write made
through the shell. It is the unrecorded-tool case above, except that here the
record exists.

The README lists the missing `files` entry as a known gap and says freshness is
unaffected, which is true: freshness reads mtimes from disk. Coverage is
affected. R-22 counts a file mutation as consequential, but coverage finds
mutations in mutation records, so a write through Bash at the default tier is
never listed as `UNREPORTED`. A report that says only "done" after a turn that
wrote only through the shell has nothing listed against it, and I-7 holds only
to its letter, since the log shows no mutation it left unmentioned.

That turn wrote through Bash four times: the `cat >>` above, a `sed -i` loop
renumbering `TASKS.md`, and two `python3 -` heredocs that rewrote it. One of
those wrote the note behind "Lo he anotado en la pregunta, citando K1 y K4.",
which came back `UNSUPPORTED` for this reason as well as for naming no file.
Which files a shell command wrote cannot be read from its command line, so this
is open. Count it during the corpus phase, apart from the referent misses.

### One turn in four passes the deadline — 17 October 2026

The route was measured at thirteen runs in fourteen inside the 12-second
deadline (`provider-measurements.md`), and README and OPERATING repeated the
figure until 17 October 2026. Daily use has been worse. Of the 49 turns
distiller captured from 6 to 17 October 2026, four ended on HTTP 401 and one on
a report over `max_report_chars`. Of the 44 left, whose call either answered or
ran out of time, 11 passed the deadline: 2 of the 22 captured before 10 October,
and 9 of the 22 since.

The times are the Stop hook's `durationMs`, which Claude Code writes into the
session transcript: the whole pipeline, not the call alone, and the only record
of latency there is, since the client writes down neither the usage nor whether
a thinking block came back. The turns that answered took a median of 2.9
seconds before 10 October and 6.9 since.

Report length does not explain it. Reports of 1,000 and 1,658 characters passed
the deadline on 17 October, and one of 9,164 answered in 3.1 seconds. The
measured runs moved too, from 6.1–8.6 seconds on 21 September to a median of
3.8 on 23 September. The route's speed changes from day to day, and nothing
recorded says why.

It matters beyond the turns it costs. Recall is to be reported beside the share
of turns that came back `UNKNOWN`, and `tools/extract_report.py`, the one tool
that runs the extractor outside a turn, takes the same deadline from the
project's `claim-ledger.toml`. What a longer deadline would buy is not known,
because a call abandoned at 12 seconds leaves no trace of how long it would have
taken. The deadline is in the frozen `[extractor]` table, the three timeouts
must stay strictly ordered, and the hook's own lives in `hooks/hooks.json`,
which an installed copy picks up only after a version bump and an update.
Moving any of them is the user's.

Later the same day the route was measured with a 150-second deadline
(`provider-measurements.md`). In a seven-minute window every call finished
inside 15 seconds and 93 of 96 inside 12, at about 0.65 seconds plus 4.7
milliseconds per output token: the deadline caps the size of an answer, at about
2,400 tokens for 12 seconds, and the length of the report hardly matters. The 11
reports whose turns had passed it answered in 0.5 to 9.6 seconds. The same
report can get answers of very different sizes (the next entry), and the hook
has also taken 7.8 seconds over two claims, so those turns met a longer answer,
a slower hour, or both. The window caught no slow hour, and the tail in one is
still unmeasured.

That evening a watcher caught one (`provider-measurements.md`). From 16:57 to
17:10 UTC the same calls on real reports took a median of 4.7 seconds and up to
38.6: 81% finished inside 12 seconds, 93% inside 20, all of them inside 45.
Neither this machine's network nor OpenRouter's front was slower; the time went
after the first byte, at the provider, which delivered about 89 tokens a second
instead of 184, so each output token cost about 10 milliseconds instead of 5.
The deadline still caps the size of an answer, but at a slow hour the cap is
less than half as large, about 1,000 tokens for 12 seconds: the largest answer
of that run, 2,943 tokens, took 38.6 seconds.

### The route no longer gives the same answer twice — 17 October 2026

The route was frozen on a measurement that included its repeatability: the
thirteen runs that answered on 21 and 23 September gave the same three claims
every time. On 17 October 2026 the same request, sent by the hook's own code
with a long deadline, went out twice for each of the 48 reports distiller had
captured. Eight got the same answer both times. The claim count differed in 31,
by a factor of two or more in 13, and 21 of the 107 answers were empty lists,
among them reports whose other run found 18, 26, 33 and 45 claims. The fixed
report of the September runs gave three distinct answers in eleven, none the one
recorded then, and two of its answers read that day name `git add`, `commit` and
`push` as referents of a sentence that names none of them. The numbers and their
conditions are in `provider-measurements.md`.

`temperature` 0 is sent and accepted, and the answers vary anyway. Whether the
provider ignores it, or runs the model in a way that breaks near-ties
differently from one call to the next, cannot be seen from here: the reply names
the provider and says nothing about how it ran. The thinking switch still holds;
none of the 107 replies carried a reasoning token.

Two consequences run against the design. A recall figure taken from one run of
an extractor that varies like this describes that run, which is why
`openai/gpt-5.6-luna` was refused. And an empty list is a valid answer (R-12),
so a turn whose answer comes back empty does not read `UNKNOWN`: it reads as a
report that claims nothing, and only coverage, listing the turn's writes as
unreported, hints otherwise.

It may be recent. The first 33 turns the hook answered, from 6 to 17 October,
include no empty answer. The 34th was one, and it came inside the window above:
turn 1 of distiller session `6cc8dfdd`, at 11:55 UTC on 17 October 2026. Its
report, 2,438 characters, names the commit it made, the one file it changed and
two `make` targets that exited 0. The hook took 523 milliseconds, where every
turn that came back with claims took 1.9 seconds or more, and it printed
`0 verified, 0 unchecked` with no extraction defect, so the model returned an
empty list: `schema.validate` turns every item of an answer into a claim, a
defect or an `UNKNOWN` turn. Above that line it listed `TASKS.md (REVIEW)`
three times as `UNREPORTED`, once for each Edit the turn made to it. That is
I-7 working, not a second fault: coverage excuses a write only when a claim
names its path, and with no claims it excused nothing. It does put on the
report an omission that was the extractor's. In a turn with nothing
consequential to list, one that only read or wrote only through Bash (the entry
above), the same answer prints the collapsed line,
`0 verified, 0 unchecked · … · nothing unreported`, and nothing on it tells
that turn apart from one whose report claimed nothing.

The 35th was one too, and it came after the window: turn 2 of the same session,
at 12:46 UTC, 48 minutes after the window closed. Its report, 3,484 characters,
again names the commit it made, the one file it changed and the two `make`
targets, and gives the full path of a script the agent wrote in its scratchpad,
outside the project. The hook took 776 milliseconds, printed no defect, and
listed ten `UNREPORTED` lines: nine edits of `TASKS.md` and the write of that
script. So the empty answers are not confined to the window. Counting the two
turns before them, which passed the deadline at 10:41 and 10:51 UTC, four
distiller turns in a row produced no claim. How often it happens, and whether
it lasts, still needs another window, ideally at a slow hour. The route is
frozen, so what to do about it is the user's.

An empty answer writes nothing to `claims.jsonl`, whose rows are one per claim
and one per defect, so the provider that gave it is recorded nowhere: R-45
carries the route on each claim. Both were found in the appendix Claude Code
writes into the session transcript, and that is the only place empty answers
can be counted from. Among the ledger's own files, a captured report with no
claim row and no `errors.log` entry is also what a hook killed after its capture
leaves behind.

The slow hour came that evening (`provider-measurements.md`), and the answers
varied as much at half the speed. From 16:57 to 17:10 UTC 23 of the 107 were
empty lists and only 6 of the 48 reports got the same answer twice; over the
day's four runs, 2 of the 48 got one answer every time. A report probed 57 times
between 12:22 and 16:57 UTC never came back empty, and gave 25 distinct answers.
So it lasted the afternoon, at either speed.

The hook met two more that day: turn 1 of session `6ffb997c` at 14:13 UTC and
turn 1 of `ed68cf55` at 20:05 UTC, each in under a second and a half. Of the 12
distiller turns of 17 October whose call answered or ran out of time, 4 came
back empty and 2 passed the deadline. `tools/daily_use.py latency` counts empty
answers from the transcripts, the one place they show.

### No suite claim can be verified in distiller — 17 October 2026

Turn 3 of distiller session `6cc8dfdd`, at 13:16 UTC, reported each step of
`make verify` by quoting its output, «16 files already formatted», «29 passed»
and «6 kept, 0 broken» among them, and the pre-commit hook of its commit by its
line, «Detect hardcoded secrets… Passed». Seven of those claims came back
`UNSUPPORTED`, "no run of that check in this session", and an eighth, that
`check_characters.py` printed nothing, "no matching command". All eight were
true. The outputs in the session transcript hold every quote and nothing from
`check_characters.py`, and `make verify` printed its own exit status, 0.

The first reason is the configuration. Distiller's `claim-ledger.toml` declares
no check: its `[checks]` says "None yet. distiller holds a design document and
no code", which was true when it was written on 5 October 2026. The Makefile
and the tests came on 12 October, and the file has not changed since. So every
`suite_passed` claim there lands `UNSUPPORTED` whatever it names, 13 of 13 up
to 17 October, and all 52 appendices distiller has printed say
`0 checks seen`: its session logs hold 835 records and not one check. R-29
prints that count even at zero because zero is worth seeing, and here it
accounted for all thirteen.

The second reason would remain with `make verify` declared. It ran eleven times
in distiller's logs and never on its own, always behind a pipe, a `;` or a
`&&`. In this turn it was
`make verify 2>&1 | grep -v …; echo "make verify exit: ${PIPESTATUS[0]}"`.
A command with a shell operator is never a check, and here that rule is what
keeps the verdict honest: the line exits with the status of `echo`, 0 whatever
make did, so the `ok` recorded for it says nothing about the suite. The agent
read make's status from the output; the ledger keeps no output (R-7). The
pre-commit claim has no route at all: the hook ran inside
`git add TASKS.md && git commit …`, which no configuration can make a check.

The tempting repair is to look for the quotes in the command's output instead
of requiring a run of the check, and it was proposed the same day. Two things
stop it. The log holds no output, by R-7, because output carries file contents
and secrets. And a substring is not an outcome: «0 errors» is inside
«10 errors», «29 passed» inside «1 failed, 29 passed», and «Passed» ends the
line of every pre-commit hook that passes, so a match would resolve an
ambiguity upward, against I-2. It is the error-string trap of SPEC § Traps,
moved to the output.

What would let such a claim verify is the user's. `[checks]` would need
`make verify` with its scope, and aliases from `pytest`, `pyright` and the rest
to it if a claim naming one tool is to reach that run. Such an alias says that
a passing `make verify` vouches for the tool, which is a fact about the
Makefile and not one the ledger may infer. And the run would have to be the
bare invocation, which is the agent's habit; changing it for the ledger's sake
would stop the corpus representing real use (ANNOTATING § While using the
plugin). A change to the file mid-session makes every later turn of that
session `UNKNOWN` (I-8), until the file is restored byte for byte; a new
session takes the changed file as its baseline.

At the user's request the check was declared the same day:
`verify = ["make verify"]`, scoped `**/*`, since the character check reads
every file git does not ignore and gitleaks reads the history, and with no
aliases yet. The bare run, and the aliases, are still open.

Both were acted on at the user's request, and on 20 October the first turns
showed it. On 19 October distiller's configuration gained aliases from the
tools `make verify` runs to the check, and its CLAUDE.md a rule to run `make
verify` alone, which gives the exit status as its reason and does not name the
ledger; on 20 October the targets `make verify` is made of became checks of
their own ("The freshness test reads the working tree once a join"). In
session `66c9649b`, opened that evening, the agent ran `make verify` bare three
times, each recorded as a run of the check, and 4 of the 8 suite claims of its
first two turns came back `VERIFIED`: one naming the invocation, one naming it
and three tools through their aliases, one naming only tools through their
aliases, and one with no referent, read as the one check the session had run.
The other 4 named no check.

The rule touches what this entry warned against. The bare run was the agent's
habit, and changing it for the ledger's sake stops the corpus representing
real use (ANNOTATING § While using the plugin). Its stated reason holds without
the ledger, since a piped line exits with the status of whatever ran last, but
it was the ledger's figures that called for it, and it was proposed without
this entry being pointed out. Of the 70 reports captured by 20 October, 5 come
from sessions opened after it. Whether they may stand in the corpus beside the
others, and whether the rule stays, were the user's to decide, and the user
decided the same day: the rule stays, and those reports may stand in the
corpus with the rest.

### Daily use left no hole in the evidence log — 18 October 2026

The phase-0 check of SPEC § Build order compared one hand-written session, 16
calls, with its log. On 18 October 2026 `tools/daily_use.py recording` made the
same comparison for all 21 sessions distiller had logged since 6 October: every
call the recorder's matcher covers that ran has its record, and every record has
its call.

Twenty-two covered calls have no record of their own, and none is a hole. Ten
were refused before they ran, six by the permission settings, two by
distiller's own PreToolUse hook, one by the auto-mode classifier and one by a
deny rule, and a refused call fires no hook (R-44). Twelve sit in the transcript
of session `94212a41`, which resumed `f89f6cd8` and repeats its calls; they are
recorded under `f89f6cd8`. None was cancelled.

No distiller session ran a subagent, so where a subagent's transcript is kept
was never seen; the tool reads any transcript in the session's folder, on the
assumption that it is there.

### A span is dropped when the extractor tidies it — 18 October 2026

On 17 October 2026 a distiller turn showed an extraction defect: a span ended
"`select`, `judge`." where the report has "`select`, `judge`».", so it was not
in the report, and it was dropped and listed under `EXTRACTION DEFECTS`, as
SPEC requires. The guess at the time was that the extractor mishandles Spanish
quotation marks.

The defects say otherwise. Up to 18 October 2026 the hook has dropped 8 spans,
in 7 of the 36 turns whose answer was not empty, and `tools/daily_use.py
defects` names what each one changed. Five dropped the `**` that closes a bold
label: `**La regla** (…` came back as `La regla (…`, starting after the opening
marker, as a reader sees the text, and losing the closing one inside it. One
dropped the closing guillemet above, one the full stop of «.», and one turned
"corrijo" into "correcciones". Meanwhile 51 kept spans hold a guillemet, and 14
a `**`, copied whole. What the defects share is the extractor tidying the text
it was told to copy, which its prompt forbids: "copy rather than tidy".

The tempting repair is to compare spans with the markup stripped, or loosely.
That is the repair SPEC § Traps rules out: it hides the rate phase 1 exists to
measure, and a loose match would pass "correcciones" for "corrijo", a word the
report does not hold.

It matters to phase 1, which tolerates no non-verbatim span (REQUIREMENTS §
Rollout phases), and the measurement runs of 17 October met more: a defect in
17 and in 12 of 107 answers (`provider-measurements.md`). The prompt is frozen,
so this is measured, not fixed, and a shortfall sends us to the misses, not to
the number.

### The pinned route is down, and its model has no other provider to take it — 18 October 2026

On 18 October 2026 OpenRouter refused every request on the route with HTTP 404:
"No endpoints found for deepseek/deepseek-v4.1-flash … Filter Disabled
Endpoints removed morph/fp8". Morph's endpoint for the model is disabled, and
the route pins Morph with fallbacks off, so nothing else may answer. The hook
met it first at 12:18 UTC, in distiller session `580e85e9`; a call at 20:25 UTC
the evening before had answered, and checks every ten minutes still found it
down at 13:32 UTC. Every turn since ends `UNKNOWN`, "the model call returned
HTTP 404", which is I-9 working. The report is still captured, so the corpus
loses nothing.

The next pin was looked for the same day among the model's 33 other endpoints
(`provider-measurements.md`), and none will do. All 25 that answered reasoned,
although the request switches thinking off, which in September only Morph, of
the five tried, honoured; six refused the route's parameters. The six fastest of
those that reason were asked the same two reports five times each, and none was
repeatable: the five that answered gave two to five distinct answers to the
same report, two of them passed 60 seconds, and one three times spent all 8,192
tokens reasoning and wrote no answer. The sixth was refused with 429 on every
call.

So the route cannot move within its own model without losing both properties it
was chosen for, no reasoning and the same answer every time. The route is
frozen, so what follows is the user's: wait for Morph, which on 17 October was
already answering differently from one call to the next, or choose another
model, which the next entry measured.

### Cheaper models return fewer, emptier and less faithful answers — 18 October 2026

The same day 48 cheaper models that take a schema and a temperature and do not
reason were screened with the route's prompt (`provider-measurements.md`). Four
gave one answer to five identical calls on both test reports, and only
`openai/gpt-4.1-nano`, pinned to Azure, did it without dropping a span. It and
`openai/gpt-4.1-mini`, which varied once in five, then ran the corpus test of 17
October, the 48 distiller reports twice; the user agreed to sending them to
Azure.

Neither will do. nano answered the same way twice for 31 of the 48 reports,
against the route's 8, mostly by saying less: 38 of its 107 answers were empty,
against the route's 21, and it kept 226 claims where the route kept 1,093, with
one span in six of those it returned not in the report. mini varied on 22 of the
48, came back empty 11 times, and one span in seven was not in the report,
against one in twenty-eight for the route. Both were faster, everything inside
12 seconds. With the corpus not yet annotated, the claims kept measure volume,
not recall; but an empty answer to a report full of work is a miss either way.

What the failures of all three models share is copying: the tidying recorded
under "A span is dropped when the extractor tidies it", and empty lists. An
extractor that returned the number of each sentence it types, rather than
copying its text, could not return a span that is not in the report, since the
client would take the text from the report itself. That changes the claim
schema and the prompt, both frozen, and what R-10 asks of the extractor, so it
is the user's to weigh. It is written down here because nothing measured on 18
October removes the need for it.

### The extractor points at sentences instead of copying them — 18 October 2026

The same day, with the user's agreement, the extractor's contract changed. The
report goes to the model cut into numbered sentences, one a line, and the model
answers with numbers. Each claim's span is the sentence its number names, taken
from the report by the client. The prompt is now `extract-2`: its typing rules
are word for word those of `extract-1`, and only what it says about spans
changed. The answer schema asks for `sentence` where it asked for `span`. The
cut is `ledger.sentences`, the one `tools/annotate.py` was already asking the
annotator about, now shared by both.

The reason is in the two entries above and in "A span is dropped when the
extractor tidies it": every model measured dropped spans by tidying them, the
route one in twenty-eight and the cheaper models one in six or seven, and
phase 1 tolerates none. With the client taking the text from the report, a
span that is not in it cannot happen. What remains a defect is a number the
report does not have.

It does not touch what the model decides: an empty answer, a claim missed, a
wrong type, an answer that changes from one call to the next. Choosing a model
is still open. Two things move with the change. A span is now a whole sentence,
so a claim inside a long sentence shows all of it in the appendix, and recall
is matched by sentence and type rather than by text (SPEC § Corpus capture).
And every recording in `tests/fixtures/extractor` answers with copied spans,
so the client refuses them all; they are kept as recordings, as the CLI ones
were, and the pipeline's tests run on answers written by hand until a route is
chosen and recorded.

The prompt and the answer schema were frozen with the route, since the corpus
was to be measured against them. No measurement had been taken, so none is
lost: the corpus will be measured against `extract-2`. The vocabulary did not
change.

### The sentence contract holds on the corpus, and none of four models carries it — 18 October 2026

The model screen of 18 October was run again under `extract-2`
(`provider-measurements.md`). None of the twenty models of its second stage
pointed at a sentence the report does not have or came back empty, where under
copied spans twelve of the sixteen in both screens had dropped spans. Read
against a key written for the two test reports, seven found all eight checkable
claims and typed nothing else checkable. Two more found the eight but typed the
negation "No he ejecutado…" as `command_run`, the mistake of "A sentence can be
typed as a file change it does not claim" made through a command: such a claim
comes back `VERIFIED` whenever the command it denies is in the log. Five of the
seven had answered the fixed report the same way every time, and the synthetic
one at most two ways in five calls.

Four of those five ran the corpus test of 17 October, the 48 distiller reports
twice; the user agreed to sending them to DeepInfra, Mistral's zero-retention
endpoint and Parasail. The contract held: three returned no sentence number
outside the report, and the fourth's 34 are in a single answer. Empty answers,
21 in 107 for the route, came to 8 for `ministral-14b`, 2 for
`mistral-medium-3.1` and none for the other two. The model changed with the
contract, so how much of that is the contract's cannot be told.

None of the four will do as measured. The three Mistral models answered the
same way in both passes for 10 to 15 of the 48 reports, little better than the
route's 8, and on more than half of them the number of claims changed. Two of
them passed 12 seconds on a quarter of the calls: `mistral-small-24b` on
DeepInfra, which also refused it with 429 for a stretch, and `ministral-14b`.
`mistral-medium-3.1` kept inside 12 seconds as the route did at a fast hour, on
94 calls of 96, but repeated on 13 and costs 3.7 times the route a call.
`llama-3.2-3b-instruct` repeated on 35 of the 42 reports whose two answers the
schema took, but it refused one answer in eleven, on four reports in both
passes: referents that are not a list of non-empty strings, or output that ran
into the 8,192-token ceiling. In the hook each of those would be an `UNKNOWN`
turn, and so would every call past 12 seconds.

All four claimed far more than the route did, 1,702 to 2,538 claims against
1,093. With the corpus unannotated that is volume, not recall, and recall is
what chooses the route; these runs only say which models are worth measuring
for it. Two things are not measured: `devstral-2512`, which met the same bar as
the four in the screen and has not run on the corpus, and whether a `seed`
parameter steadies the Mistral models, which would have to be read from the
answers, since a parameter accepted is not a parameter honoured.

Later the same afternoon `devstral-2512` ran the same test on Mistral's EU
endpoint, with the user's agreement (`provider-measurements.md`). It came out a
twin of `mistral-medium-3.1`: 94 of 96 calls inside 12 seconds, with the
shortest tail of the five, two empty answers, no number out of range, one answer
refused for a claim type added as a field, as two of medium's were, and about
the same cost a call. It answered the same way in both passes for 12 of the 48
reports, and the number of claims changed on 30. So none of five carries the
contract either. The four Mistral models, served by Mistral or by DeepInfra,
repeated on 10 to 15 of the 48 alike; whether that is the models or how they are
served is not measured, and the `seed` above is the measurement left.

That evening the seed was tried on the four Mistral models, with the two test
reports only (`provider-measurements.md`). All four endpoints list `seed` as
supported and answered every call, but the seed steadied nothing: over the same
ten calls it gave no model fewer distinct answers, the most common answer stayed
the same, and two different seeds did not settle on different answers. It is a
parameter accepted and not visibly honoured, as `enable_thinking` was on four
providers in September; whether it reaches the model and finds nothing to fix
at temperature 0, or never reaches it, the answers cannot say. No measured
lever is left to make these models repeat. So choosing one means accepting
answers that vary from call to call, as the route's did on 17 October, or, with
`llama-3.2-3b-instruct`, one turn in eleven `UNKNOWN`; recall on the annotated
corpus decides either way.

### A provisional route until the corpus chooses one — 18 October 2026

With the pinned route down and none yet chosen by recall, the user decided the
same evening to run `mistralai/mistral-medium-3.1` on `mistral/zdr`, Mistral's
zero-retention endpoint, as distiller's route under `extract-2`, so that the
appendix comes back while the corpus is annotated. It is provisional: the route
the FROZEN row asks for is still the one recall on the annotated corpus
chooses. The installed copy moves to 0.2.0, the first with the sentence
contract, and distiller's `claim-ledger.toml` takes the new model, provider and
parameters between sessions; the repository's sample keeps the route frozen on
23 September.

On the 48 reports and against the hook's 12 seconds, it would have lost the
fewest turns of the candidates: 4 in 96 `UNKNOWN` and 2 empty, against
DeepSeek's 3 and 20 at its fast hour and 18 and 20 at a slow one, with no
sentence number out of range. `devstral-2512` measured about the same, and
medium was preferred for the zero-retention endpoint; `llama-3.2-3b-instruct`
repeats but would have left 12 turns in 96 `UNKNOWN`. Medium costs about
$0.00125 a turn against DeepSeek's $0.00034, and its answers vary from call to
call as DeepSeek's did. It was measured in one window, on a Sunday afternoon; at
a slow hour DeepSeek's `UNKNOWN` turns went from 3 to 18 in 96, and how medium
fares in one is not known.

The next route is chosen as SPEC § Corpus capture now says, decided the same
day: once the 50 reports are annotated, medium, devstral and llama each run the
corpus three times, each pass's recall and spurious share reported beside its
share of `UNKNOWN` turns, and each candidate judged by its worst pass, so that
no miss is averaged away (A-12). The one that clears the phase-1 threshold with
the fewest `UNKNOWN` turns becomes the route, is frozen, and R-45, which still
names DeepSeek, is brought up to date. Choosing a route whose answers vary
departs from R-45's own reasoning in September, which refused a candidate whose
answers varied run to run; no candidate measured since repeats without failing
turns, DeepSeek included.

### Half of what the provisional route leaves unsupported names nothing a log could hold — 19 October 2026

In its first four turns in distiller, on 18 and 19 October, `mistral-medium-3.1`
ran as measured: no turn `UNKNOWN`, the hook done in 3.0 to 7.6 seconds, no hole
in the evidence log. But 42 of its 57 checkable claims came back `UNSUPPORTED`,
10.5 a turn against DeepSeek's 2.6, and it types nine claims in ten as checkable
where DeepSeek typed fewer than four in ten. Each of the 42 was set beside the
join's own rule for its type, without being read:

- 22 name nothing the join could match whatever the log held: 5 file claims
  with no referent and 2 with nothing shaped like a path, 7 command claims
  whose referents are identifiers or words rather than commands, and 8 suite
  claims naming a test file, counts, exception names or words rather than a
  suite.
- 9 the configuration could reach: 5 named tools that `make verify` runs, in
  the session where it had passed, with no alias to it; 4 named a `make`
  target, in a session that ran `make` commands, and none is a declared check.
- 3 are right as they stand: the commands they claim were blocked by
  distiller's own hook and never ran.
- 8 cannot be told apart without reading them: 4 name a file with the name of
  one written but in another folder, 2 a file no log holds, 1 a file only read,
  and 1 suite claim has no referent in a turn that ran no check.

Phase 1 cannot see the first group. Recall matches a claim by its sentence and
its type (SPEC § Corpus capture), so a route could clear the threshold with
referents that never match anything, and its appendix would fill with
`UNSUPPORTED` lines that say nothing about the work. So the corpus measurement
now reports, beside recall, the share of checkable claims whose referents the
join could match at all (`usable` in `tools/measure_route.py`), and
`tools/daily_use.py referents` gives the same share for daily use. On
distiller's claims so far, judged against its configuration with the aliases
below, DeepSeek reaches 151 of 201 (75%, over 33 turns) and medium 30 of 57
(53%, over 4). Files and suites make the difference, 84% against 62% and 55%
against 37%; commands are alike. Four turns are few, and the reports differ.

At the user's request, distiller's configuration gained aliases to its one
check from the tools `make verify` runs, in the forms reports had used:
`pyright`, `import-linter`, `gitleaks`, and `ruff` with `ruff check`, `ruff
format` and `ruff format --check`. pytest, named once, was left out. A claim
that one of them passed now reads the last run of `make verify`, which runs
them all.

### The freshness test reads the working tree once a join — 20 October 2026

Distiller entered its `tests` phase on 20 October, where the tests are red on
purpose and `make verify` cannot pass, and the agent ran `make format`, `make
lint` and `make types` on their own instead, bare and passing. Six referents
of turn 2 of session `699b8797` named them, and their claims came back
`UNSUPPORTED`, since `verify` was the only declared check. At the user's
request distiller's configuration gains the targets `make verify` is made of
as checks of their own, `format`, `lint`, `imports`, `types`, `test` and
`secrets`, each with its exact invocation and a scope taken from
`pyproject.toml` and the Makefile, to be applied between sessions. `make
test-red` is left out: it fails on purpose, and a claim that it failed as
expected, typed as a suite that passed, would come back `CONTRADICTED`.

Replayed with those checks, that turn reached passing checks for 4 suite
claims, and its join went from no time at all to 3.05 seconds. The freshness
test of R-18 walked the whole working tree for every claim that reached a
passing check: 9,627 files in distiller, nearly all in the virtual environment
and the caches git ignores, from 0.75 to 1.5 seconds a walk, all of it inside
the 15-second turn budget, where an overrun makes the turn `UNKNOWN`.

With the user's leave, since `join.py` is frozen with the verdict table, one
join now walks the tree once, the first time a claim needs it, and works out
each scope's newest file once, so that every claim of the turn is judged
against one listing. A join that needs no freshness test walks nothing, and
the next join walks again. The verdict table did not change, and neither did
any verdict: the same turn replayed with and without the cache gave the same
verdicts and the same scopes, and its join took 0.76 to 0.94 seconds. The one
walk still lists the virtual environment before git's filter drops it;
listing only what git keeps would cut it further, and is not done.

That evening, once the session then open had closed, the checks were applied,
at 19:23 UTC, and the next session started with them; its first turns are
recorded under "No suite claim can be verified in distiller". It ran `make
verify` whole and none of the targets on its own, so the new checks have not
been exercised yet.

On 21 October they were. In turn 2 of session `c9387804` the agent ran `make
format`, `make lint` and `make types` bare, seven runs recorded as runs of
their own checks, `types` failing once before it passed twice; `make
test-red`, run eleven times, stayed a command. The hook took 9.7 seconds with
the seven in its log. Of 18 suite claims, 1 came back `VERIFIED`, naming the
three invocations and read against the last run of any of them, as the join
reads every claim with several referents ("A claim is verified when any one of
its referents is"). Ten had no referent and came back `UNSUPPORTED`, since the
join gives a claim with no referent to the session's check only when one
check ran, and three had: the downgrade I-2 asks for, and the right one if
they speak of `make test-red`, which a single check would have verified
against something else. Six named no check, and one named a tool whose alias
points to `verify`, which this session never ran.

That put the aliases' direction to the user, and the same day the user kept
them pointing to `verify`. Of the 7 suite claims that had named a tool through
an alias since 19 October, 2 reached a run the way they point, both in a
session that ran `make verify`; 2 would have reached one had each tool pointed
to its own target, both in the `tests` phase; and 3 reached none either way.
Moving them would trade two claims for two. The claims that say a piece of
work is done come where the agent runs `make verify`, and a miss either way
lands `UNSUPPORTED`, the safe direction.

Letting a passing `verify` count as a run of each target it runs would have
reached 4 of the 7, and is left until misses like these matter more. It is a
change to the frozen join and to SPEC rather than to a configuration, and it
needs rules of its own: the containment declared in the configuration, since
the ledger may not read it off the Makefile; a failing `verify`, which does not
say which target failed, never contradicting a claim about one of them; and
freshness judged by the target's scope, not by `verify`'s.

Later that day the other phase came round. In the first turn of session
`794b9f80` the agent ran `make verify` bare once, and 5 of the turn's 6 suite
claims came back `VERIFIED` against that run: one naming the invocation, three
with no referent, read as the one check the session ran, and one naming a tool
through its alias and `format` and `lint` by their ids, read against the last
run among the checks it named, which was `verify`'s, and rightly here, since
`make verify` runs both. Of the turn's 13 checkable claims, 11 came back
`VERIFIED` and 11 named something the join could match; the hook took 5.2
seconds.

That evening, back in the `tests` phase, turn 2 of session `6ea8d45c` ran
`make format`, `make lint` and `make types` bare and passing, each recorded as
its own check, and none of the turn's 8 suite claims came back `VERIFIED`:
none had a referent, and with three checks run the join gives such a claim to
none of them, as I-2 asks. Over the two `tests`-phase turns that ran checks,
18 of 26 suite claims had no referent, 10 of 18 and then 8 of 8. No
configuration can reach them, nor should: if they speak of `make test-red`,
which is no check, `UNSUPPORTED` is right; if they say the targets passed
without naming them, the referent is the extractor's to give, and the share
of usable referents is what measures that.

Later that evening, in the first turn of session `45e7ba3f`, the agent ran
`make verify` bare once, and 7 of the turn's 10 suite claims came back
`VERIFIED` against that run: one naming the invocation, and six naming tools
through their aliases alone, more than in all the turns before it together.
The other 3 named no check. The hook took 4.9 seconds, and the appendix listed
one action the report left unmentioned.

### The corpus is annotated by a model, anchored by a few reports by hand — 23 October 2026

The user tried `tools/annotate.py` on 23 October. A median report has 41
sentences and the longest 381, so fifty reports come to some 2,000 sentences,
two to five hours of keys; the first report it showed had 130, and its hard
cases called for three new rules in ANNOTATING that afternoon, on headings,
on what the agent may or can do, and on lines of code. The user chose a model
as the reference instead, and A-12 and § Rollout phases now say so, with the
user's leave for the frozen row in CLAUDE.md.

The annotator chosen is `claude-fable-5-1`, to run through the Claude Code CLI
on the user's subscription, since Claude through the API costs too much. It is
of another family than the three routes it will measure, Mistral's two and
Meta's Llama, so it does not share their blind spots by construction, and the
reports were written by Claude in distiller, so sending them to Anthropic
reaches no one who did not have them. It gets each report as the extractor
does, as numbered sentences cut by `ledger.sentences`, with ANNOTATING's rules,
and nothing else: not the extractor's answers, not the evidence. It runs
outside distiller, whose installed plugin would otherwise capture its answers
as reports. The CLI was rejected as the extractor's transport on 20 September
because it cannot prefill an answer; an annotator needs no prefill. A first
report is to show that the CLI reaches the model and answers in shape before
the rest are sent.

What the choice gives up is in ANNOTATING § Why a person, and not a model:
against this reference, recall is agreement with the annotator, and a claim
both miss goes unseen. The anchor measures how much: five short reports the
user annotates by hand, with the annotator's agreement on them reported beside
every recall figure. Short ones were chosen for the user's time, so the
agreement may flatter the annotator on long reports. The phase-1 numbers do
not move. README and OPERATING are to say how to run the annotator once the
tool exists.

On 24 October the annotator ran over the rest: 79 reports in 52 minutes,
about 40 seconds each, and every answer passed its checks. With one report
captured while it ran, the corpus holds all 81 of distiller's reports that the
extractor reads, signed `claude-fable-5-1 via Claude Code 2.1.309`; the one
over `max_report_chars` is left out, as the extractor leaves it. The same day
the user widened the anchor to six reports. Those of 8 to 15 sentences hold
105 of the corpus's 4,088 sentences, 2.6%, and those of more than 30 hold
88.6%, so five short ones would have checked the annotator where it is used
least. The six are five of 8 to 15 sentences, one to a session, from 6 to 17
October, and one of 44 sentences from 21 October, 103 sentences in all. The
report the CLI was first tried on was left out, since how many claims the
model found in it had come up in the conversation.

### Recall is scored from kept answers, and spurious counts every type — 24 October 2026

`tools/measure_recall.py` scores what SPEC § Corpus capture asks of a
candidate, from answers that `tools/measure_route.py run --corpus` gathers: it
asks only about the reports the corpus annotates, and keeps each answer as the
number and type of each claim's sentence, still without a span. A run used to
keep a digest and counts only, because the corpus was to be annotated by hand
and a person who had seen the extractor's list would confirm it. The corpus is
a model's now, and the anchor is annotated before any run. Each row names the
route that answered it, and `--config` measures a candidate from a copy of the
project's `claim-ledger.toml`, so the file distiller's turns read is never
touched for a measurement.

Three things the requirements leave open were settled in the code and
confirmed by the user, and SPEC § Corpus capture now says them:

- An extracted claim is spurious when no annotated claim of its type lies in
  its sentence, and the share is of everything extracted, every type counted:
  a sentence typed otherwise is a miss and a spurious claim at once. Counting
  only the claims in sentences the annotator left unmarked would not see what
  the provisional route was seen doing on 19 October, typing nine claims in
  ten as checkable. Both parts are printed, so either reading can be taken
  from the output.
- Recall and the spurious share are taken over every answer a pass got, a late
  one included, and the `UNKNOWN` share counts the turns the hook would have
  lost, with no answer or one after the route's own deadline. A long report
  asks for a long answer, and a long answer takes longer, so scoring only the
  answers inside the deadline would score a slow route on its short reports.
- A claim in a turn that got no answer is not a miss. Its turn is in the
  `UNKNOWN` share, which is the measure of a turn that never reaches the claim
  at all (REQUIREMENTS § Measurement and anti-metrics).

The annotator's agreement with the anchor is counted the same way in both
directions: how many of the person's checkable claims the annotator found, and
how many of the annotator's the person made. Every figure names the corpus by
a digest of its file, so a measurement says what it was measured against.
Checked on the corpus without a call: all 2,117 of its claims fall in a
sentence of their report, 377 of them as part of one, and the corpus scored
against itself gives recall 1.0 and nothing spurious.

### No candidate clears phase 1 against the model's annotations — 24 October 2026

With the user's go, medium, devstral and llama ran the 81 reports of the corpus
three times each, side by side and call for call, from 07:29 to 08:31 UTC on 24
October. Each ran from a copy of distiller's `claim-ledger.toml` that differs
only in model and provider (`corpus/routes/`), with the rows in `corpus/runs/`,
$0.84 in all, and every answer from the pinned provider. Scored against
`corpus/annotations.jsonl` (sha256 `8173ac03cffb`), with no report of the
anchor annotated yet:

| | `mistral-medium-3.1`, `mistral/zdr` | `devstral-2512`, `mistral/eu` | `llama-3.2-3b-instruct`, `parasail/bf16` |
| --- | --- | --- | --- |
| Recall on checkable claims, by pass | 0.70, 0.72, 0.71 | 0.70, 0.72, 0.70 | 0.23, 0.24, 0.23 |
| Spurious share, worst pass | 0.51 | 0.49 | 0.84 |
| Turns `UNKNOWN`, worst pass | 5 of 81 | 3 of 81 | 31 of 81 |
| Sentence numbers naming no sentence | 0 | 0 | 741, in 10 answers |
| Checkable claims missed in at least one pass | 270 | 277 | 504 |
| Reports answered alike in all three passes | 11 of 81 | 9 of 81 | 34 of 81 |
| Calls inside 12s, of 243 | 240 | 243 | 176 |
| Cost | $0.32 | $0.34 | $0.18 |

None clears the threshold of REQUIREMENTS § Rollout phases, so the rule of 18
October, the candidate that clears it with the fewest `UNKNOWN` turns, chooses
none. medium and devstral are as near each other as on 18 October; llama
misses three checkable claims in four and would lose a third of its turns. A
shortfall sends us to the misses, so they were counted by the kind of line
each sentence comes from, prose, list item, heading, bold line, table row or
code line, and by type, over the three passes and without a sentence being
read: the anchor is still to be annotated by hand, and the list of misses shows
what the annotator marked in its reports. For medium, with devstral within a
few claims of it:

- Seven misses in ten, 505 of the 724 of the three passes, are sentences the
  route typed nothing at all. Table rows are 9% of the corpus's sentences and
  hold 29% of the misses:
  the annotator types a quarter of them as checkable, and the route misses 207
  of those 297 claims. Code lines go the same way, typed checkable by the
  annotator in 28% of cases and missed about half the time.
- Half the spurious claims, 1,123 of 2,211, are in sentences the annotator left
  unmarked, and 85% of those are list items, which are 63% of the corpus's
  sentences. Headings, bold lines and code lines together carry 8% of the
  spurious claims. The guess of the same morning, that the gap comes from
  ANNOTATING's rules for headings and code, which the extractor's prompt does
  not carry, does not hold for these two routes: they type 9% of headings and
  4% of bold lines.
- The other half are typed otherwise, and two in three of those are sentences
  the annotator typed as judgment or intent and the route as checkable: 727 of
  1,088, and 734 of 1,073 for devstral. It is what daily use showed on 19
  October, nine claims in ten typed checkable.
- llama types nearly everything, 71% of headings and 85% of bold lines among
  it, and most of it otherwise than the annotator.

These figures are agreement with `claude-fable-5-1`, whose own agreement with
a person is not known until the anchor is annotated (A-12). The annotator works
from ANNOTATING's 2,187 words and the extractor from a prompt of 352, and
neither says how to read a table row. The prompt and the threshold are frozen,
and the provisional route stays as it is in distiller. The list of misses is
left unread until the anchor is annotated.

### The annotator agrees with a person on three checkable claims in four — 24 October 2026

The user annotated the six reports of the anchor by hand on 24 October, 103
sentences in all. One of them, `794b9f80-…-1`, was annotated twice. The first
annotation was taken out at the user's request, so that the results of a
command could follow the pauta agreed while annotating: what a command or a
tool returned is `command_run`, and the agent's verdict on it is `judgment`.
Before the sixth was done, the sentences of the five short reports that the
two had typed differently were printed by mistake; the user was asked not to
read them.

Against the morning's corpus (sha256 `8173ac03cffb`), the annotator found 18
of the user's 27 checkable claims, 0.67, and the user made 19 of its 25, 0.76.
Of the 103 sentences, 29 were typed differently. Five of the nine claims it
missed were sentences that say how a document changed without saying it was
edited, of the kind of "el primer punto ya no dice…", which the user typed
`file_changed` and the annotator `judgment`. On three lines that name a check
with its result, the annotator put `command_run` beside `suite_passed`, and
the user `suite_passed` alone.

The user settled both, and ANNOTATING has two rules since. A sentence that
lets you know, read in its report, that a file's content changed is
`file_changed`, with an editing verb or without one. A line that names a check
with its result is `suite_passed` alone, since a check only comes out by
running a command. The rules' examples are invented and appear in no captured
report: the guide is part of the annotator's prompt, and an example taken from
the anchor would hand it the answer. Two sentences of the anchor that the user
had typed before the rule, on the reading given then, took `file_changed`
beside their `judgment` at the user's request (anchor sha256 `630420c9fdbd`).

The annotator then annotated the same 81 reports again, from 17:25 that
evening, in about an hour and with no answer refused, into a new
`corpus/annotations.jsonl` (sha256 `1014621cb4d1`, through Claude Code
2.1.310). The morning's corpus is kept as `corpus/annotations-2026-10-24.jsonl`.
Four reports captured since were left out, so that the morning's runs score
against the same reports.

| Against the anchor | Morning corpus | After the two rules |
| --- | --- | --- |
| The user's checkable claims the annotator found | 18 of 27 (0.67) | 22 of 29 (0.76) |
| The annotator's checkable claims the user made | 19 of 25 (0.76) | 23 of 29 (0.79) |
| Sentences typed differently, of 103 | 29 | 26 |

| The runs, rescored without a call: worst pass, recall and spurious share | Morning corpus | After the two rules |
| --- | --- | --- |
| `mistral-medium-3.1`, `mistral/zdr` | 0.70, 0.51 | 0.67, 0.52 |
| `devstral-2512`, `mistral/eu` | 0.70, 0.49 | 0.67, 0.49 |
| `llama-3.2-3b-instruct`, `parasail/bf16` | 0.23, 0.84 | 0.24, 0.83 |

What the two still type differently is the result of a tool or a script,
which the user types `command_run` by the pauta, never written into
ANNOTATING, and the annotator `suite_passed` or `judgment`; and what a commit
is said to have changed, `file_changed` for the user and `judgment` for the
annotator. A reference nearer the person did not bring the routes nearer the
threshold. They miss most of the `file_changed` claims the annotator added,
from 301 to 362, and they type a check's line as `command_run`, which counts
against them now that the line is `suite_passed` alone.

The annotator does not repeat itself either. Of the checkable claims of its
first annotation, the second has 759 of 843, 0.90, and the first has 754 of
the second's 857, 0.88. Of the 4,088 sentences, 385 were typed differently:
34 gained `file_changed` beside a `judgment`, 67 lost a `command_run` beside a
`suite_passed`, and 284 changed otherwise, by the new guide's reach into other
sentences or by the annotator's own variation, which nothing has measured
under one guide. A recall figure moves with its reference: medium's 0.70
against the morning's corpus is 0.67 against the evening's. The routes stand
at 0.67 against 0.90, a gap far wider than anything the reference was seen to
move, so none clears phase 1 under either reading. What is open is on the
extractor's side, and its prompt is frozen.
