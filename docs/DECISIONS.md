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

Corrected on 1 November 2026: that the switch worked on `morph` was never
shown. No call went to it without the switch, so a reply with no thinking
block cannot tell a switch honoured from a deployment that did not reason. On
1 November `morph/fp8`, listed again, reasoned with the switch in this form,
in the top-level shape below and as `reasoning: {"enabled": false}`
(§ The pinned route is down, and its model has no other provider to take it).

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

Since 3 November 2026 the guide types it `file_changed`: a commit that now
holds other changes is a change of the files the report says it holds, here
the SPEC's (§ What a commit is said to have changed is `file_changed`, whoever
ran it). Its referents still name no file, so it would still come back
`UNSUPPORTED`.

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

Corrected on 1 November 2026: no installed copy picks it up. Claude Code reads
the plugin, `hooks/hooks.json` with it, out of the marketplace's folder, which
until that day was this working tree, and not out of the copy an update makes:
§ distiller runs a release copy, not this tree.

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

Moved on 31 October 2026, at the user's leave, to 20 seconds, with the budget
and the hook's timeout after it: § The deadline moves to 20 seconds.

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

Listed again, 1 November 2026. Morph's endpoint was back in OpenRouter's list
by 31 October, still tagged `morph/fp8`, and on 1 November, at the user's
request, the route ran the annotated corpus once with `extract-4+4a21e3ea`
under distiller's configuration, the switch as before
(`provider-measurements.md` § The annotated corpus on `morph/fp8`). It reasons
on every call. All 77 replies carried a thinking block, 38 spent the 8,192
tokens on it and wrote nothing, and 56 of the 80 calls that were not refused
took more than 20 seconds. 65 of the 81 turns would be `UNKNOWN`, and 56 of
72 leaving out the nine reports a run of HTTP 402 cut off. On the 31 reports
it answered, the short ones, recall was 0.74 and the spurious share 0.20,
where medium's worst pass gives 0.76 and 0.42 on the same reports. The switch
was then sent in the other two forms, top-level `chat_template_kwargs` and
`reasoning: {"enabled": false}`, three calls each with the fixed report, and
all six were accepted and reasoned, as the route's own form had. Whether Morph
honoured the switch in September or served a deployment that did not reason,
the calls of that month cannot say, since none went to it without the switch.
Either way, waiting for Morph no longer leads back to the route of September:
what answers on its pin now reasons, and does not fit the deadline. At the
user's choice this is recorded rather than probed further, and the forms not
tried are in `provider-measurements.md`. The provisional route stays.

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

Corrected on 3 November 2026: the three with no referent were results of a
script the agent had written and run by hand, typed `suite_passed`, and `make
verify` passing says nothing of them (§ Nine claims about runs by hand were
verified against a check that says nothing of them).

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

### The annotator repeats itself within the threshold — 24 October 2026

At the user's request, the annotator annotated the same 81 reports a second
time, from 19:15 to about 20:15 on 24 October, with no answer refused, into
`corpus/annotations-repeat.jsonl` (sha256 `fe8b772d2131`). It used the same
guide as the evening's annotation, ANNOTATING unchanged since 16:35, and the
same CLI, Claude Code 2.1.310. The reference stays `corpus/annotations.jsonl`
(sha256 `1014621cb4d1`).

Scored against the first as an extractor would be, the second pass reaches
recall 0.95 on checkable claims, 818 of 857, with a spurious share of 0.07,
149 of 2,041: 108 claims in sentences the first left unmarked and 41 typed
otherwise. The other way round, it is 0.96 and 0.08. Phase 1 asks for 0.90 and
at most 0.10, so an extractor as good as the annotator would clear it against
one annotation of it, with five hundredths to spare on recall and two or three
on the spurious share. The routes' 0.67 is the extractor's gap, not the
reference's noise.

Of the 4,088 sentences, 286 were typed differently, 7%. That is about as many
as the 284 the previous entry could put down to neither rule, which were then
most likely the annotator's own variation. The counts by type barely move:
`file_changed` 362 and 361, `judgment` 1,033 and 1,034. What varies is the
border between `judgment`, `intent` and no claim at all, and that border is
what makes the spurious share the tighter half of the threshold. The 0.88 to
0.90 of the previous entry came from the change of guide, not from the
annotator.

The second pass agrees with the anchor as the first did: it finds 22 of the
user's 29 checkable claims, 0.76, and the user made 22 of its 27, 0.81. None
of the twenty quoted examples of ANNOTATING is a sentence of a captured report,
only the command name `make verify` appears in reports, so the guide hands the
annotator no answer. What was not measured is a reference made by the majority
of three passes or more. What is open is a prompt that carries ANNOTATING's
rules, which needs the user's leave for the frozen prompt and a reading of
I-1.

Corrected on 25 October 2026: the sentence above saying that no quoted
example of ANNOTATING is a sentence of a captured report is wrong. The check
matched an example only when its quotes fell on one line of the guide, and
two that wrap across lines are sentences of captured reports. "En esta fase no
puedo leer `src/`, así que no podría editar el fichero después" is in
`069e1689-…-1`, and "`docs/SPEC.md` no se ha tocado" in `51e5603c-…-2`,
`57fec1fa-…-1` and `afd27afb-…-1`. All four reports are in the corpus and none
is in the anchor. So the guide did hand the annotator the answer for those
four sentences, and it gave that answer: no claim for the first, `judgment`
for the other three. Recall, which counts checkable claims, does not see them,
and the agreement with the anchor does not include them. The examples stay in
ANNOTATING for now, since the corpus was annotated with them, and a guide
changed under it would no longer be the one that made it.

### A prompt with the guide's rules gains recall and does not clear phase 1 — 25 October 2026

On 25 October the user gave leave to unfreeze the prompt and read I-1 so that
the rules for typing are part of the type vocabulary the extractor is given,
not context. `extract-3` (`src/ledger/prompts/extract-3.md`,
`extract-3+47a8c259`) is `extract-2` with ANNOTATING's rules condensed into
it: what is not a claim, headings, code, what was not done, what the agent may
do, a file's content and a check's line. It has 784 words to `extract-2`'s 352.
Its examples are invented, and none of its 26 quoted examples is in a captured
report, checked with the lines joined; the two of ANNOTATING that are, named
in the correction above, were replaced. The hook still sends `extract-2`, and
`tools/measure_route.py --prompt` measures a candidate file beside it.

medium and devstral ran the corpus with it three times each, from 08:06 to
08:27 UTC, in the same order as their `extract-2` runs, for $0.84 in all.
Before that, one call per route on the fixed report gave the three types it
was recorded with. Scored against the frozen corpus (sha256 `1014621cb4d1`):

| Worst pass | medium, `extract-2` | medium, `extract-3` | devstral, `extract-2` | devstral, `extract-3` |
| --- | --- | --- | --- | --- |
| Recall on checkable claims | 0.67 | 0.74 | 0.67 | 0.75 |
| Spurious share | 0.52 | 0.49 | 0.49 | 0.46 |
| Turns `UNKNOWN` | 5 of 81 | 3 of 81 | 3 of 81 | 3 of 81 |
| Checkable claims missed in at least one pass | 306 | 254 | 309 | 242 |
| Median call; calls inside 12s, of 243 | 2.2s; 240 | 3.3s; 237 | 2.2s; 243 | 3.2s; 238 |
| Cost | $0.32 | $0.41 | $0.34 | $0.43 |

Counted by type over the three passes, without a sentence being read, the
rules did what they say for medium, and devstral went the same way. The
annotator's `file_changed` claims in sentences the route typed nothing at all
fell from 295 to 140, and its `suite_passed` claims from 299 to 212. Check
lines typed `command_run` fell from 226 to 101, and judgments typed
`suite_passed` from 169 to 55. But the route now calls far more sentences
opinions where the annotator saw no claim, from 393 to 1,318, so it extracts
half as much again and the spurious share hardly moves. Some checkable claims
it now types `judgment`, `suite_passed` ones from 20 to 71, by the prompt's
caution. Counted on checkable claims alone, 0.40 to 0.45 of what it types
checkable matches nothing of the annotator's, where it was 0.46 to 0.52.

The rules are worth seven or eight hundredths of recall. With these two models
the prompt closes neither the gap to the 0.90 and 0.10 of phase 1 nor the one
to the annotator's 0.95 and 0.07 against itself. Nothing was confirmed on
reports outside the corpus: the four captured since are not annotated. What is
open is adopting `extract-3` in the hook, which recovers more claims and loses
fewer turns for about 30% more a turn and a slower tail, 10 seconds at the
95th percentile against 6; stronger models, of another family than the
annotator's; or phase 1 as an observer only.

### extract-3 goes into the hook, and phase 1 stays an observer — 25 October 2026

On 25 October the user accepted three things: `extract-3` in the hook, a
screen of stronger models with it, and phase 1 as an observer while no route
clears its threshold.

Before the swap, the isolation test of I-1 refused the prompt. Its example
"`pytest -q`: 41 passed" held `pytest -q`, a command of the test's fixture
session, and the test cannot tell a prompt's example from a leak. The example
became "`pytest`: 41 passed", which no captured report holds, and the prompt
`extract-3+32d58f9c`. A changed prompt does not inherit a measurement, so
medium ran the corpus again with it, three passes from 09:00 to 09:20 UTC, for
$0.47. Its worst pass gives recall 0.72 and a spurious share of 0.47, against
0.74 and 0.49 with `extract-3+47a8c259` and 0.67 and 0.52 with `extract-2`.
Two turns of 81 are `UNKNOWN` in its worst pass, both late, with no answer
missing and none refused, and 239 of its 243 calls came inside 12 seconds,
the median at 3.1.

`prompts/extract.md` is now `extract-3`, and `prompts/extract-2.md` keeps the
sentence contract alone, for measurement. The frozen row of CLAUDE.md says so,
with the user's leave, and SPEC § Extractor contract says how the rules travel
with the vocabulary. The plugin goes to 0.3.0 with this change and is
installed in distiller from this commit; a session already open keeps 0.2.1
until it closes.

Corrected on 1 November 2026: it did not keep 0.2.1. The hooks ran this
working tree as it stood at each call, so turn 2 of `9da7aee8` sent `extract-3`
at 09:09 UTC, from the tree, before this commit and before the install:
§ distiller runs a release copy, not this tree.

Phase 1 goes on as an observer. Nothing blocks a turn in phase 1, and phase 2
waits for a route that clears the threshold. Until then the appendix reads as
an instrument that misses about a quarter of the checkable claims the
annotator marks.

### No stronger model screened does better than medium — 25 October 2026

The screen the user accepted ran from 09:02 to 09:31 UTC on 25 October: one
pass each with `extract-3+32d58f9c` over the frozen corpus (sha256
`1014621cb4d1`), of models that do not reason, take a schema and a
temperature, and are of another family than the annotator's. The same day the
user agreed to the corpus going to Azure, Novita and SiliconFlow, beyond the
providers agreed on 18 October. `mistral-large-2512` answered 429 to every
call on Mistral's zero-retention endpoint and ran on its EU one. Each was
first asked the fixed report once, and answered in shape.

| Model, provider | Recall | Spurious share | Turns `UNKNOWN` | Median call | A pass |
| --- | --- | --- | --- | --- | --- |
| `mistral-medium-3.1`, `mistral/zdr`, the route, worst of 3 passes | 0.72 | 0.47 | 2 of 81 | 3.1s | $0.16 |
| `mistral-large-2512`, `mistral/eu` | 0.64 | 0.32 | 3 of 81 | 3.6s | $0.11 |
| `kimi-k2-0905`, `novita/fp8` | 0.61 | 0.43 | 37 of 81 | 10.9s | $0.26 |
| `deepseek-chat-v3-0324`, `siliconflow/fp8` | 0.58 | 0.33 | 44 of 81 | 13.1s | $0.09 |
| `qwen3-235b-a22b-2507`, `deepinfra/fp8` | 0.57 | 0.31 | 21 of 81 | 7.2s | $0.03 |
| `gpt-4.1`, `azure` | 0.53 | 0.24 | 2 of 81 | 3.8s | $0.46 |

The stronger models are more cautious, not more right: they mark fewer claims,
which lowers their spurious share and their recall together. `gpt-4.1`
extracted 865 claims in its pass, where medium extracts about 2,200 and the
annotator marks about 2,050. `kimi-k2-0905` and `deepseek-chat-v3-0324` would
lose half their turns to the 12 seconds as well. None reached the 0.85 of one
pass that was to earn three, so none ran three. The route stays medium with
`extract-3`, and phase 1 stays an observer. The screen cost $0.95.

Not measured: models that reason, with the reasoning switched off, since a
parameter accepted has more than once not been a parameter honoured; Claude's
models, which A-12 rules out against an annotator of their family; and more
than one pass of any candidate, so each figure may move by a few hundredths.

The 0.3.0 install copied the working tree into the plugin cache, the
untracked `corpus/` with it, since a directory marketplace takes the directory
as it is. That copy, a stale snapshot, was deleted at the user's request. An
install from a tree with untracked data in it carries the data along.

### The sample configuration names the provisional route — 25 October 2026

At the user's leave, the `[extractor]` of the repository's sample
`claim-ledger.toml`, a frozen section, and its copy in SPEC moved from
`deepseek/deepseek-v4.1-flash` on `morph` to `mistralai/mistral-medium-3.1` on
`mistral/zdr`, with `temperature` 0 and nothing else. The thinking switch went
with the old route, since this model does not reason. A sample that names an
endpoint answering 404 since 18 October helps no one who copies it. The route
is as provisional in the sample as in distiller, and the frozen row of
CLAUDE.md says so. The test that the sample loads as written now expects the
new route, and a new one keeps the nested parameter table of the old route
loading.

### The deadline moves to 20 seconds — 31 October 2026

On 31 October, at the user's leave, `[extractor] timeout_s` went from 12 to 20
seconds, `[budget] turn_timeout_s` from 15 to 23, and the Stop hook's timeout in
`hooks/hooks.json` from 20 to 28. The margins between them are the ones
measured on 23 September: three seconds for the rest of the pipeline, five to
render the `UNKNOWN`. The plugin goes to 0.3.1 with the hook's timeout.
Distiller's `claim-ledger.toml`, which is the user's, moves after the plugin is
installed and between sessions. The other order would put a 23-second budget
inside a hook killed at 20, and a killed hook reports nothing.

The reason is daily use. Of the first 20 distiller turns with `extract-3`, from
25 to 31 October, 4 passed the 12 seconds, every one a report of 136 to 201
sentences. That is 4 of the 6 turns of 120 sentences or more, and none of the
14 shorter. With `extract-2` on the same route, from 18 to 25 October, none of
29 had, 6 of them that long.

The time is the size of the answer. Over the corpus the route costs the same
per output token with either prompt, 4.35 milliseconds with `extract-2` and
4.38 with `extract-3`, and 12 seconds hold about 2,550 tokens. `extract-3`
writes more of them, 0.55 claims a sentence against 0.38 at about 25 tokens
each, and nearly half of what it writes is `judgment`: 47% of its claims, and
52% of those in answers over 2,000 tokens. The answer to one long report also
changes size from call to call by four times or more: `699b8797-…-1`, of 166
sentences, got 4,341, 3,869 and 991 tokens in three passes. The corpus holds 5
reports of 120 sentences or more among 81, so its 239 calls in 243 inside 12
seconds were decided by short reports. On those 5, 3 calls of 15 passed 12
seconds with `extract-3`, and 2 with `extract-2`.

What a longer deadline buys was not known, because a call abandoned at 12
seconds leaves no trace of how long it would have taken. So the six long
reports of daily use with `extract-3`, the four that passed the deadline and
two that did not, were sent again on 31 October from 12:24 to 12:27 UTC: three
passes with each prompt under a 150-second deadline, for $0.12, kept in
`corpus/runs/long-reports-*.jsonl`. The two runs went side by side, and 8 of
their 36 calls on reports came back HTTP 429; they were not repeated. With
`extract-3`, 4 of the 12 answers passed 12 seconds, up to 14.0 seconds and
3,127 tokens. With `extract-2`, 4 of 16 did, up to 17.4 seconds and 3,512
tokens. Going back to `extract-2` would not have saved these turns: the size of
an answer follows the report and the call more than the prompt.

With the corpus's answers beside them, every answer to a report of 120
sentences or more came inside 20 seconds as measured: 27 with `extract-3` and
31 with `extract-2`. Every window ran at about 235 to 240 tokens a second after
the first byte. At half that speed, an estimate from the size of each answer
puts 20 of the 27 inside 20 seconds, 23 inside 25 and 25 inside 30, and single
calls have been slower still, the slowest at 85 tokens a second. The user chose
20 as the smallest figure that holds every answer measured. It costs time only
on the turns 12 seconds would have lost, at most eight seconds each: a turn
that answered inside 12 waits no longer than it did, and a call slower than 20
is still `UNKNOWN`.

Not measured: the route at a slow hour, which on 17 October halved the old
route's speed, and any report beyond these 6 and the corpus. The route copies
under `corpus/routes/` keep 12 and 15, as they were measured, and every earlier
run's rows carry the deadline they were scored against.

### Out of the corpus, the route finds half the checkable claims — 31 October 2026

The corpus froze on 24 October, and `extract-3` was written while it was being
measured. So on 31 October, at the user's request, the 27 reports distiller
captured after it that the extractor reads were annotated as the corpus was:
`claude-fable-5-1` through `tools/annotate_model.py`, under the guide
unchanged since 24 October. They went into a file of their own,
`corpus/holdout.jsonl` (sha256 `e11bd53fbae6`), with 1,113 claims, and the
corpus was not touched. The CLI that carried the model was 2.1.316, where the
corpus's was 2.1.310. The route, `mistral-medium-3.1` with
`extract-3+32d58f9c`, ran them three times from 13:30 to 13:39 UTC under the
20-second deadline, for $0.23.

| Worst pass | The corpus, 81 reports | After it, 27 reports |
| --- | --- | --- |
| Recall on checkable claims | 0.72 | 0.50 (passes 0.55, 0.50, 0.57) |
| Spurious share | 0.47 | 0.58 |
| Turns `UNKNOWN` | 2 of 81 | 1 of 27 |

Counted by type, without a sentence being read, the loss is the suites'.
Recall on `suite_passed` is 0.42 to 0.52 across the three passes, against 0.69
to 0.71 on the corpus. `file_changed` is 0.73 to 0.77 against 0.79 to 0.80, and
`command_run` 0.62 to 0.69 against 0.59 to 0.62. These reports also hold more
suite claims. `suite_passed` is 35% of what the annotator marked in them,
against 20% in the corpus: 15.3 claims for every 100 sentences, against 9.8.
Where the route misses a suite claim, it misses it as it does in the corpus:
it types the sentence nothing 72% of the time, and `judgment` 27%, where the
corpus gave 67% and 29%. What is not known is whether these suite claims are a
harder kind, or whether the annotator marks them differently now. None of the
anchor's reports is among the 27, so nothing here sets the annotator against a
person.

The one `UNKNOWN` was `c1f27201-…-1` in every pass: an answer in which one
claim had no `referents`, which the schema requires and the client refuses
under R-12. It is not new. Six of the `extract-2` corpus run's answers were
the same, and one of the first `extract-3` run's, which also had one answer
that was not JSON. SPEC § Extractor contract says the answer's shape is
enforced rather than asked for. On this route the endpoint takes the schema
and does not hold every answer to it, and SPEC is left as it is for the user
to decide. Every one of the run's 81 calls on these reports came inside 20
seconds, and 73 of them inside 12.

Annotated again, 31 October 2026. To tell the two apart, the annotator
annotated the same 27 reports a second time that afternoon, with the same
guide and CLI and no answer refused, into `corpus/holdout-repeat.jsonl`
(sha256 `52600b0fa830`). Scored against the first annotation as an extractor
would be, the way the corpus's second pass was, it reaches recall 0.98 on
checkable claims, 537 of 547, and finds every one of the first's 389 suite
claims. The other way round it is 0.95, and 0.96 on suite claims. Against the
second annotation the route's worst pass is 0.49, against the first 0.50. The
suite claims the route misses are ones the annotator marks the same way
twice, so the gap is the extractor's.

Corrected on 6 November 2026: the second annotation finds 388 of the first's
389 suite claims, not every one. The one it misses, a sentence of
`25b4c7b6-…-3`, it types `judgment`. The scorer and both files are as they
were on 31 October, and the conclusion stands.

What varies is the border between `intent`, `judgment` and no claim, and it
is wider here than in the corpus. 259 of the 2,543 sentences were typed
differently, 10% against 7%, and the second pass marked 184 `intent` claims
where the first had 111. Its spurious share against the first is 0.16, and
0.08 the other way. Against one annotation of reports like these, then, even
an extractor as good as the annotator could go over the 0.10 that phase 1
allows. Not measured: whether the annotator under CLI 2.1.316 marks the
corpus's reports as it did under 2.1.310. A few of them annotated again would
show it.

### A rule for table rows recovers the suite claims, and is not in the hook yet — 31 October 2026

Counted by the form of their sentence, without one being read, the suite
claims the route misses sit in table rows. It found 0.15 of those the
annotator marked in table rows of the corpus and 0.18 in the reports after
it, against 0.86 and 0.88 in prose. Rows hold 23% of the corpus's suite claims
and 57% of the later reports', which is what the later reports lost. Neither
`extract-3` nor ANNOTATING says anything about tables. The annotator types a
row that gives a check's result as `suite_passed` by the rule for a check's
line, the same way both times, and leaves most other rows unmarked: 218 of the
corpus's 335 rows and 344 of the later 565, the header rows almost always.

At the user's leave, `src/ledger/prompts/extract-4.md` (`extract-4+4a21e3ea`)
is `extract-3` with one rule more and half a sentence saying a table comes a
row to a sentence. The rule reads a row under its header row, the way a line
is read under its heading. It leaves the header out, types a row that names a
check with its result `suite_passed` and nothing else, a row about a file
`file_changed`, and leaves out rows that only lay out data, options or a plan.
It is the guide's rules for a check's line and for a heading, carried over to
tables, and was not fitted to any row of a report. Its three quoted examples
are invented, and none is in the 109 captured reports or the 21 fixture files.

`mistral-medium-3.1` ran it three times over the corpus, from 16:06 to 16:28
UTC on 31 October for $0.41, and three times over the later reports, from
16:28 to 16:38 UTC for $0.25:

| Worst pass | After the corpus: `extract-3`, `extract-4` | The corpus: `extract-3`, `extract-4` |
| --- | --- | --- |
| Recall on checkable claims | 0.50, 0.77 (passes 0.81, 0.86, 0.77) | 0.72, 0.79 (0.81, 0.80, 0.79) |
| Spurious share | 0.58, 0.55 | 0.47, 0.52 (0.52, 0.45, 0.42) |
| Suite claims found in table rows | 0.18, 0.82 | 0.15, 0.81 |
| Suite claims found in prose | 0.88, 0.88 | 0.86, 0.88 |

The rule does what it says and nothing else moves much. It also types more of
the rows the annotator left unmarked. Claims the route takes from table rows
went from 266 to 567 in the corpus and from 600 to 1,013 after it, and those
in unmarked rows from 120 to 241 and from 337 to 445. The spurious share of
claims from rows fell all the same, from 66% to 50% and from 80% to 46%,
because most of the new ones are the annotator's suite claims: those that
match went from 90 to 282 and from 119 to 547. The spurious share overall hardly
moves: most of it is still `judgment` where the annotator saw no claim. All 81
calls on the later reports came inside 20 seconds, the slowest at 15.2.

The run over the later reports is whole. The one over the corpus is not: the
endpoint refused 31 of its 269 calls with HTTP 429 that afternoon, one call
stalled to the 150-second deadline, and 4 answers lacked `referents`. Its
recall is over the 72, 73 and 67 reports each pass got an answer for, and its
`UNKNOWN` share, up to 14 of 81, says more about the endpoint that afternoon
than about the prompt. The three corpus passes are to run again at a quiet
hour, on the night of 31 October, before the user decides. The hook sends
`extract-3` until then, and phase 1 is not cleared either way.

Run again, 1 November 2026. The three corpus passes ran again from 01:00 to
01:20 UTC on 1 November, for $0.46, once five probes had all answered.
No call was refused and none passed 20 seconds, the slowest at 16.1. Three
answers lacked `referents`, two in the first pass and one in the second, and
the hook would have left those turns `UNKNOWN`. Over its two corpus runs
`extract-4` has given 7 such answers in 459, on four reports.
`extract-3+32d58f9c` gave none in 243, and its slowest answer, 19.7 seconds,
came inside the 20 now in force, so under them none of its turns would be
`UNKNOWN`.

| Worst pass, the corpus | `extract-3` | `extract-4`, again |
| --- | --- | --- |
| Recall on checkable claims | 0.72 | 0.80 (passes 0.80, 0.81, 0.83) |
| Spurious share | 0.47 | 0.47 (0.47, 0.46, 0.46) |
| Turns `UNKNOWN` under 20 seconds | 0 of 81 | 2 of 81 |
| Suite claims found in table rows | 0.15 | 0.87 |
| Suite claims found in prose | 0.86 | 0.88 |

The afternoon's figure holds: 0.79 then, over the reports that got an answer,
and 0.80 now. The gain is all the suites'. `suite_passed` is 0.84, 0.88 and
0.92 across the passes, against 0.69 to 0.71, and `file_changed` 0.80 to 0.81,
against 0.79 to 0.80. `command_run`, 94 claims, is 0.54 to 0.58 against 0.59
to 0.62, and all six passes `extract-4` has had are under `extract-3`'s
lowest. The spurious share does not move, but more of it is checkable. Claims
typed `suite_passed` in a sentence the annotator did not type so are 113, 145
and 121 a pass, against 74, 77 and 78, and 12 to 22 of them are table rows,
against at most 1. Spurious claims of the three checkable types together are
476, 505 and 492, against 430, 489 and 438. The join could match the
referents of 811 of the 1,520 `suite_passed` claims the passes typed, 53%,
against 651 of 1,108, 59%, and a claim whose referents it cannot match stays
`UNSUPPORTED` whatever ran.

Phase 1 is not cleared either way. Whether `extract-4` goes into the hook is
the user's to decide, and the hook sends `extract-3` until then.

### extract-4 goes into the hook — 1 November 2026

On 1 November, with the clean corpus run in hand, the user put `extract-4` in
the hook. It goes as it was measured: `prompts/extract.md` is the candidate's
text unchanged, `extract-4+4a21e3ea`, so the figures above are its own and
nothing had to run again. The isolation test of I-1 finds none of its fixture
session's strings in it. `prompts/extract-3.md` keeps `extract-3+32d58f9c`,
and `prompts/extract-2.md` the sentence contract alone, both for measurement.

The gain comes with the costs recorded above. Its worst pass reaches recall
0.80 over the corpus, against 0.72, and 0.77 over the reports after it,
against 0.50, with the spurious share where it was. More of the spurious
claims are `suite_passed`; 7 of its 459 answers over the corpus lacked
`referents`, which leaves a turn `UNKNOWN`, against none of 243 with
`extract-3`; and `command_run` sits a few hundredths lower.

The frozen row of CLAUDE.md says so, with the user's leave, and so does the
comment over the route in the sample configuration, also frozen and also at
the user's leave. R-45, SPEC § Extractor contract, README and OPERATING say so
too. `docs/ANNOTATING.md` is not touched. The prompt now has a rule for tables
that the guide does not state, but the annotator already types a row that
gives a check's result the way the guide types a check's line, so the
reference stays as it was annotated. The plugin goes to 0.3.2 with this change
and is installed in distiller from this commit; a session already open keeps
0.3.1 until it closes. Phase 1 goes on as an observer.

Corrected on 1 November 2026: a session already open would not have kept
0.3.1, since the hooks ran this working tree as it stood at each call
(§ distiller runs a release copy, not this tree). No turn fell between the
edit and the install: the first to send `extract-4` is the one below.

The first turn, 1 November 2026. The first distiller turn under 0.3.2,
`268e3821-…-1` at 10:46 UTC, sent `extract-4+4a21e3ea` a report of 10,718
characters, 126 sentences and no table, and its answer came inside the
deadline: the hook took 15.2 seconds, and the old deadline of 12 would have
cut the call off. The turn ran no command and wrote no file, so the 5 of its
102 claims typed checkable all came out `UNSUPPORTED`, and none became
`VERIFIED`. Read where they stand, none says that anything was done. One is a
command the agent says distiller's own hook stopped, typed `command_run`.
Three are sentences of a plan, typed `file_changed`, in a report that opens by
saying the agent only read files. The fifth says how a proposed test would
run, typed `command_run`.

At the user's request the route was asked about the same report three times
with each prompt, alternating, for $0.05
(`corpus/runs/268e3821-mistral-medium-3.1-extract-3+32d58f9c.jsonl`, and the
same with `extract-4+4a21e3ea`). `extract-3` typed the same five sentences the
same way in all three calls, and once a sixth, so they are not the table
rule's doing: the report has no table for it to read. `extract-4` left one of
the five as `intent` in one call. It gave fewer claims, 102 to 119, the hook's
answer counted, against 115 to 122, and fewer of them `judgment`, 75 to 110
against 106 to 113. It also repeated itself less on this report: its three calls typed 78 of 116
sentences alike, against 111 of 119 for `extract-3`'s, mostly because one
call moved 20 sentences from `judgment` to `intent`. Both are
`NOT_CHECKABLE`, so no verdict moves with them. A call took 10.7 to 15.8
seconds with `extract-4` and 15.3 to 16.2 with `extract-3`. The report is not
annotated, so none of this is a recall figure.

### distiller runs a release copy, not this tree — 1 November 2026

The plugin does not run from the copy that `claude plugin install` and
`claude plugin update` make in `~/.claude/plugins/cache`. From a `directory`
marketplace, Claude Code reads it out of the marketplace's folder as the folder
stands at each hook call, and until this day that folder was this working tree:
`claude plugin list --json` names it as `readFromFolder`, beside the cache's
`installPath`. Turn 2 of distiller's `9da7aee8` was the first sign. It sent
`extract-3+32d58f9c` at 09:09 UTC on 25 October, while the copy installed was
0.2.1, whose prompt is `extract-2`; the prompt had been in this tree since
08:59, and 0.3.0 was committed at 09:22 and copied at 09:23. That copy's
`turn.py` and `record.py` were last read at 09:23 the same day, by the check
made after installing it, though the hooks ran on each day from 28 to 31
October with it installed, and on this disk a read more than a day after the
last one moves the access time.

So what distiller ran was this tree as it stood, edits not yet committed
included, and an install gated nothing. The version a claim carries is still
true, since it is the hash of the prompt sent (R-45), but nothing else that ran
carried one. An edit half made in `src/` could have cost turns their audit, or
the evidence log a record, with nothing in `errors.log` to say so, since the
code that writes it is the code that would have broken.

At the user's decision the plugin now runs from a release copy,
`~/code/claim-ledger-release`: a clone of this repository, detached at the
commit that shipped the version its `plugin.json` names, 189f0c8 for 0.3.2,
and never edited. distiller's marketplace is that folder, so an edit here
reaches no session until it is shipped, the way OPERATING gives. A clone and
not a worktree, whose state would live in this repository's `.git`, so that
nothing done here can move it or break it. Not taken: working in a worktree and
keeping this tree at shipped commits, which leaves what distiller runs to
discipline; and a marketplace on GitHub, which would make a push the release,
and where Claude Code would run it from was not checked.

Shipping moves the folder under any session open on it, and each hook starts
Python on the folder's files afresh, so a session open across a ship would run
the new scripts from its next hook. Whether Claude Code reads
`hooks/hooks.json` again before then was not checked. So a version ships
between sessions.

The switch was made at 12:56 UTC. Removing the marketplace from distiller
uninstalled the plugin with it; the marketplace was added again from the
release copy with `--scope local`, and the plugin installed again. distiller's
`.claude/settings.local.json` kept its `env` as it was. The release copy
matches the 0.3.2 copy in the cache file for file, `.git` and `__pycache__`
aside, and `readFromFolder` names it. Not checked: what Claude Code's
documentation says about any of this, and whether a session open across the
switch holds the folder it started with.

Seen the same day. With the access times of `turn.py`, `record.py`,
`hooks/hooks.json` and `plugin.json` set back to 1 January in the release copy
and in the cache at 13:02 UTC, session `fcc7c6b4`, opened at 13:06, read the
last two out of the release copy as it opened, `record.py` with its first Bash
call at 13:07, and `turn.py` at 14:01:01, as its Stop began. Nothing in the
cache was read. The Stop ran two hooks, distiller's own and this one, the 29
calls the recorder covers are all in the evidence log, the hook took 3.7
seconds, and `errors.log` has nothing new.

### In one report, 14 of the route's 17 misses are misses for a person — 2 November 2026

One of the five reports added to the holdout on 1 November, `fcc7c6b4-…-1`,
holds 17 of the 26 checkable claims the route missed in at least one pass.
On 1 and 2 November the user read those 17 sentences beside the annotator's
types, and typed each.

| The user's type | Sentences |
| --- | --- |
| The annotator's | 8, and on one of them the user added `file_changed` beside its `command_run` |
| Another checkable type | 6: results of programs run by hand, `command_run` where the annotator put `suite_passed` |
| `judgment` | 3: two items under a line that says a file was changed, typed `file_changed` by the annotator, and one verdict on a hand run, typed `suite_passed` |

So 14 of the 17 sentences hold checkable claims for the user too, 15 in all,
and the route missed each in all three passes: it never gave them the
checkable type the user gave, and the five it typed `suite_passed` in its
first pass match the annotator, not the user. Here the misses are the
extractor's. The annotator was right on whether a sentence claims something
checkable 14 times in 17, and wrong mostly on the type. No figure is
corrected: only the route's misses were read, which leaves out what it found
and what the annotator did not mark, so the sample is not fair either way.

Where the two differ, the guide was silent, and at the user's request it now
has two rules. What a command returned is `command_run` unless the command is
a check, and the agent's verdict on it is `judgment`: the pauta of 24
October, written down, with what a check is. And under a line that says a
file was changed, an item saying what went into it does not claim the change
again. Two of the user's types moved while the rules were checked against
them: one sentence took `command_run` beside its `file_changed`, and one went
from `judgment` to `command_run`. The examples are invented and appear in
none of the 117 captured reports. The other difference recorded on 24
October, what a commit is said to have changed, is not settled here. The
corpus and the holdout stay as annotated under the old guide: annotating them
again is a decision of its own, and if it is taken, recall will move with the
reference, not with the extractor. The prompt has neither rule, and is
frozen; R-45 and SPEC § Extractor contract say so. Neither this report nor the other four of 1 November, whose counts
the user has seen, can be a blind anchor.

### Four sentences of the anchor move to the rule on what a command returned — 3 November 2026

Before the corpus is annotated again under the guide of 2 November, the
annotator annotated the six reports of the anchor twice under it on 3
November (`docs/ANNOTATING.md` sha256 `f1d48f664f01`, Claude Code 2.1.316),
into `corpus/anchor-fable-b4ed0a0-1.jsonl` and `-2.jsonl`. The two passes
under the guide of 24 October are the corpus and its repeat, through Claude
Code 2.1.310.

| Against the anchor as the user typed it, sha256 `630420c9fdbd` | Guide of 24 October | Guide of 2 November |
| --- | --- | --- |
| The user's checkable claims the annotator found | 22 of 29 (0.76), 22 of 29 (0.76) | 24 of 29 (0.83), 23 of 29 (0.79) |
| The annotator's checkable claims the user made | 23 of 29 (0.79), 22 of 27 (0.81) | 25 of 31 (0.81), 24 of 30 (0.80) |
| The annotator's claims of every type that are not the user's | 0.25, 0.22 | 0.25, 0.25 |

The rule on what a command returned did what it was written to do. Three
results of programs run by hand, which the user had typed `command_run` and
the annotator `suite_passed` or `judgment`, came out `command_run` in both
passes, and a fourth in one. It also moved four sentences away from the user
in both passes, by its own words and its example. Two are results of a script
the agent wrote and ran, typed `suite_passed` by the user beside a third
result of the same script typed `command_run`. Two say what git does, under a
line in which the agent says it checked a text with git, and the user had
left them unmarked. The three sentences that say what a commit changed stayed
`judgment` in every pass, since no rule covers them yet. The rule on the items
under a line that says a file was changed found no clear case in the anchor,
so these passes say nothing of it. The change of CLI between the guides is
not ruled out as a cause, but the sentences that moved are the ones the rule
describes.

The user sided with the rule on all four on 3 November, as recommended. It is
what the written rules give. The user's own types of 2 November already follow
it, and so do two sentences of the anchor itself: the third result of the
script, and the line about checking with git. And `suite_passed` on a run by
hand is what let nine claims be verified against a check that says nothing of
them (next entry). The two results of the script are now `command_run`, and
so are the two sentences about git, each as a whole sentence (anchor sha256
`bb2906b07b52`). Their rows keep the date of 24 October; the change is
recorded here and in git.

Those four sentences were typed after the user had seen the annotator's types
for them, so the anchor is not blind on them, and part of what it measures
from now on is agreement with the rule rather than with the person.

| Against the anchor as it now stands, sha256 `bb2906b07b52` | Found | Made | Not the user's |
| --- | --- | --- | --- |
| The morning corpus of 24 October, before the guide's first rules | 16 of 31 (0.52) | 17 of 25 (0.68) | 0.31 |
| Guide of 24 October: `corpus/annotations.jsonl`, and its repeat | 20 of 31 (0.65), 20 of 31 (0.65) | 21 of 29 (0.72), 20 of 27 (0.74) | 0.28, 0.25 |
| Guide of 2 November, two passes | 28 of 31 (0.90), 27 of 31 (0.87) | 29 of 31 (0.94), 28 of 30 (0.93) | 0.19, 0.19 |

So the reference every recall figure so far is measured against,
`corpus/annotations.jsonl`, agrees with the anchor as it now stands on about
two checkable claims in three, where the figure of 24 October was three in
four. On checkable claims, the first pass under the new guide still differs
from the user on the three sentences about commits, on an item typed
`file_changed` under a heading on changes to a commit message, and on the
line that introduces the script, typed `command_run`. Annotating the corpus
and the holdout again under the guide of 2 November is still a decision of
its own, and what a commit is said to have changed is still not settled.

### Nine claims about runs by hand were verified against a check that says nothing of them — 3 November 2026

Of the 2,012 claims distiller's log has judged since 6 October, 92 are
`suite_passed` claims that came back `VERIFIED`, and 17 of those named no
suite: the session had run exactly one check, and the join read them as that
check, as SPEC § Matching, per type says. Eight are about what that check
runs, tests, lint, coverage and import contracts, and `make verify` passing
says what they say. The other nine are results of programs the agent ran by
hand. Three are the results of the script in the entry above, in the first
turn of `794b9f80` on 21 October, under `extract-2`. Six are in the first
turn of `fcc7c6b4` on 1 November, under `extract-4`, five of them runs of
distiller's own command; the user typed them `command_run` or `judgment` on 2
November. All nine carry `make verify ok` and its time as their scope, and
`make verify` passing says nothing of what those programs returned.

The join did what its table says. The extractor typed the nine `suite_passed`
and gave them no referent, and the fallback is safe only while the type is
right: a `command_run` claim has none, and must name its command or stay
`UNSUPPORTED`. So the nine were verified because they were typed as checks,
which the guide's rule of 2 November on what a command returned types
against, and the anchor with it since 3 November. The prompt the hook sends
does not have that rule.

The claims are probably true: nothing in the log says otherwise, and nothing
in it says so. Whether they count as false `VERIFIED` against the condition
for phase 2, no false `VERIFIED` in the phase-1 sample, is the user's to
decide, and is not decided. Narrowing the fallback would be a change to the
frozen join. The paragraph that reported three of them, under § The
freshness test reads the working tree once a join, has a correction beneath
it.

### What a commit is said to have changed is `file_changed`, whoever ran it — 3 November 2026

The last difference the anchor showed on 24 October, what a commit is said to
have changed, was settled on 3 November. Three sentences of the anchor say it,
and the user had typed each `file_changed`, beside a `judgment` for the
reasoning in two of them; the annotator typed all three `judgment` in every
pass under every guide. Two of the commits were in the repository before the
turn, and the third was one the turn had rewritten with `git commit --amend`.

Asked whose commits these were, the user said the agent gave the commands and
the user ran them. The log adds that from 6 to 17 October the agent ran `git
commit` itself 30 times, each recorded and passing, and that it has run none
since. Who runs the command changed halfway and whose work a commit holds did
not, so the guide now types what a commit is said to have changed as
`file_changed`, whoever ran it: the change is the agent's unless the report
gives it to someone else, which is how the rule on a file's content already
reads a change. A sentence that says a commit now holds other changes is
`file_changed` when the report says which files, and the line that says which
files does not claim the change again. A sentence that only says a commit was
made says that a command ran, and is `command_run`, as the user typed one in
the anchor. A change the report gives to someone else is `judgment`. A first
draft typed a commit made like a commit rewritten; read against the anchor, it
gave `file_changed` where the user had typed `command_run`, and it was changed
before the annotator saw it. The examples are invented and appear in none of
the 117 captured reports, nor in the tests. The anchor did not move.

A claim about a commit of an earlier session comes back `UNSUPPORTED`, which
is true of this session's log, and one about a file the session also wrote
comes back `VERIFIED` against that write, as any `file_changed` claim does,
since the join matches by path over the whole session (§ A sentence can be
typed as a file change it does not claim). That is not the way the nine
verdicts of the entry above came: those were suite claims with no referent,
read as the session's one check, and a `file_changed` claim has no fallback.

The annotator annotated the anchor twice under the guide with this rule
(`docs/ANNOTATING.md` sha256 `3b11b78931a8`, Claude Code 2.1.316), into
`corpus/anchor-fable-commit-rule-1.jsonl` and `-2.jsonl`.

| Against the anchor, sha256 `bb2906b07b52` | Found | Made | Not the user's |
| --- | --- | --- | --- |
| Guide of 2 November, two passes | 28 of 31 (0.90), 27 of 31 (0.87) | 29 of 31 (0.94), 28 of 30 (0.93) | 0.19, 0.19 |
| With the rule on commits, two passes | 30 of 31 (0.97), 31 of 31 (1.00) | 31 of 34 (0.91), 32 of 34 (0.94) | 0.19, 0.17 |

The three sentences about commits came out as the user typed them in both
passes, and the commit that was only made stayed `command_run`. The one claim
the first pass missed is a result of a run by hand that the annotator types
`command_run` in one pass and `judgment` in the other, under this guide and
the one before. Two of its checkable claims the user does not have in either
pass: an item typed `file_changed` under a heading on changes to a commit
message, and the line that introduces a script, typed `command_run`, both
typed so under every guide since the rules of 24 October. A third, in the
first pass only, is a line about a command that a hook blocked.

These figures say that the guide now gives the anchor's types and that the
annotator applies it, not that it agrees with a person to that degree
elsewhere. Seven sentences of the anchor no longer measure that on their own:
four the user typed after seeing the annotator's types, and three a rule was
written from. A test of the guide against a person needs reports the user
annotates by hand before seeing the annotator's types; three captured reports
are in no file yet, 157 sentences. Annotating the corpus and the holdout again
under this guide is still a decision of its own.

### The corpus and the holdout are annotated again under the guide as it stands — 3 November 2026

At the user's request, the annotator annotated the 81 reports of the corpus
and the 32 of the holdout again on 3 November, under the guide with the rules
of 2 and 3 November (`docs/ANNOTATING.md` sha256 `3b11b78931a8`, Claude Code
2.1.316), in three processes side by side. Eight reports were cut off at 13:08
UTC, when the subscription's usage limit ran out and the CLI exited before
making any call; they were annotated once it was restored, at 20:47 UTC, and
none was refused. The new annotations are now `corpus/annotations.jsonl`
(sha256 `49b617e87aa8`) and `corpus/holdout.jsonl` (sha256 `c932f01d206c`).
The ones they replace are kept as `corpus/annotations-2026-10-24-evening.jsonl`
(sha256 `1014621cb4d1`) and `corpus/holdout-2026-11-01.jsonl` (sha256
`8919e6ada7fa`), and `corpus/annotations-repeat.jsonl` and
`corpus/holdout-repeat.jsonl` are repeats of those. No repeat has been made
under the new guide, so how much the annotator varies under it, and how near
the threshold an extractor could come, is not measured.

| Claims in the reference | Corpus, before and now | Holdout, before and now |
| --- | --- | --- |
| `command_run` | 94, 234 | 62, 160 |
| `suite_passed` | 401, 362 | 419, 398 |
| `file_changed` | 362, 372 | 118, 108 |

The stored runs were scored again without a call. Recall moves here with the
reference, not with the extractor.

| Worst pass, recall and spurious share | Before | Now |
| --- | --- | --- |
| `extract-4`, the hook's prompt: the corpus, run of 1 November | 0.80, 0.47 | 0.69, 0.45 |
| `extract-4`: 27 reports of the holdout | 0.77, 0.55 | 0.70, 0.54 |
| `extract-4`: the 5 reports of 1 November | 0.50, 0.69 | 0.44, 0.67 |
| `extract-3`: the corpus | 0.72, 0.47 | 0.65, 0.46 |
| `extract-3`: 27 reports of the holdout | 0.50, 0.58 | 0.45, 0.56 |

Every one of the 14 stored corpus runs lost between 0.03 and 0.10 of recall,
the two runs of the hook's prompt the most, 0.104 each before rounding, and
no spurious share moved by more than about 0.02. Most of the drop is the claims
the rule of 2 November on what a command returned moved. In the corpus,
`command_run` claims went from 94 to 234, mostly results of programs run by
hand that had been `suite_passed` or `judgment`, and in its worst pass the
route finds 55 of 230, 0.24, where it found 0.54 of the 93 before; in the
holdout it finds 0.37, where it found 0.65. The prompt has no such rule.
`suite_passed` went from 0.84 to 0.87, and `file_changed` from 0.80 to 0.79.

Against the anchor, the new corpus finds all 31 of the user's checkable
claims, and the user made 31 of its 34. That is not an independent measure,
since the newest rules were written from sentences of the anchor (§ What a
commit is said to have changed is `file_changed`, whoever ran it). The
independent one is to come from the three reports captured on 1 November that
were in no file. The annotator has annotated them too, into
`corpus/anchor-blind-fable.jsonl`, which is kept out of the repository, out of
the holdout and out of every figure here until the user has annotated the
three by hand, into `corpus/anchor-blind.jsonl`, without seeing it. They join
the holdout after that. No route clears phase 1 against either reference.

### extract-5c goes into the hook — 4 November 2026

The reference of 3 November types what a program run by hand returned as
`command_run`, and `extract-4` found 0.24 of those claims, having no such
rule. At the user's leave, three candidate prompts were measured with the
route in use, three passes each, against that reference.

- `extract-5` (`extract-5+c5b8e1d0`) is `extract-4` with the guide's three
  rules of 2 and 3 November, condensed, and one more change: "this turn's
  work" became "the state of the work" in the line that says which assertions
  are claims, since the rule on commits reaches commits of other sessions and
  the guide speaks of the state of the work.
- `extract-5b` (`extract-5b+3d0c0982`) is `extract-5` without that change.
- `extract-5c` (`extract-5c+0dbdf6be`) is `extract-5b` with one rule more for
  tables: a row that says which tests catch or cover a case is read as a
  check's line, though it names no command.

| Worst pass, recall and spurious share | `extract-4` | `extract-5` | `extract-5b` | `extract-5c` |
| --- | --- | --- | --- | --- |
| The corpus | 0.69, 0.45 | 0.72, 0.50 | not run | 0.75, 0.48 |
| 27 reports of the holdout, passes 1 and 2 | 0.73, 0.54 | 0.63, 0.61 | 0.64, 0.60 | 0.80, 0.56 |
| The corpus: answers past 20 seconds, of 243 | 0 | 12 | not run | 0 |

On the corpus, `extract-5c` finds 0.36 to 0.42 of the `command_run` claims
in its three passes, where `extract-4` found 0.24 to 0.25, `suite_passed`
0.89 to 0.91, where it found 0.87 to 0.94, and `file_changed` 0.84 to 0.87,
where it found 0.79 to 0.81. In the third pass of the holdout, `extract-5`
lost 15 of 32 calls to HTTP 429 around 22:30 UTC, so its first two passes
stand for it here.

What the three showed. `extract-5` lost 111 of the holdout's `suite_passed`
claims that `extract-4` found, 98 of them rows of tables that give, for each
case, the tests that catch or cover it, and typed those rows `judgment`: the
rule on what a command returned calls a check a command, and these rows name
tests, not a command. It also extracted over half as many `judgment` claims
again as `extract-4`, most in sentences the annotator left unmarked, and its
answers grew long enough that 12 corpus calls passed 20 seconds; the
provider's speed per token was the same as on 1 November. Without the change
of scope, `extract-5b` lost 69 such claims, 63 of them table rows, and fewer
answers came late; the change of scope was part of the cost, not most of it.
With the rule for test rows, `extract-5c` lost 10, none of them table rows,
and kept what the rule on command results gained. The prompt therefore still
says "this turn's work" where the guide speaks of the state of the work, and
has two rules for tables the guide does not state.

So `src/ledger/prompts/extract.md` is now `extract-5c+0dbdf6be` byte for
byte, and the figures above are its own. `extract-4` stays as
`prompts/extract-4.md`, and `extract-5` and `extract-5b`, measured and not
taken, stay as their own files. The plugin is 0.3.3. Its answers are longer
than `extract-4`'s: a median of 722 output tokens on the corpus against 516,
a 95th percentile of 12.7 seconds against 9.3, and a slowest answer of 19.2
seconds, under the 20-second deadline; on the holdout 2 answers of 81 passed
it. At a slow hour, when the provider generates at half speed, more turns will
come back `UNKNOWN` than with `extract-4`. Its spurious share is 0.48 on the
corpus, against 0.45. Phase 1 is not cleared, and the hook stays an observer.
The runs are in `corpus/runs/`, with the prompt's version in their names; the
five runs cost about $2.20.

### On three reports annotated blind, the annotator finds 0.58 of the user's checkable claims — 4 November 2026

The three reports captured on 1 November that were in no file, the second and
third turns of `5a44896f` and the first of `75d5aae0`, 157 sentences in all,
give the first measure of the annotator against a person that no rule of the
guide was written from. The annotator annotated them on 3 November under the
guide as it stands (`docs/ANNOTATING.md` sha256 `3b11b78931a8`, Claude Code
2.1.316), into `corpus/anchor-blind-fable.jsonl`. The user annotated them by
hand on 3 and 4 November, into `corpus/anchor-blind.jsonl`, without seeing
that file or any figure drawn from it.

| Against reports the user annotated by hand | Found | Made | Not the user's |
| --- | --- | --- | --- |
| The three reports, blind, sha256 `0b78354418ed` | 28 of 48 (0.58) | 29 of 31 (0.94) | 5 of 71 (0.07) |
| The six of the anchor, sha256 `bb2906b07b52`, which the newest rules were written from, with `corpus/annotations.jsonl` | 31 of 31 (1.00) | 31 of 34 (0.91) | 13 of 74 (0.18) |

What the annotator marks, the user nearly always marks too, but on these
three reports it left out two in five of the user's checkable claims. The
first figure taken on the anchor, on 24 October, before the guide had any of
its rules, was 0.67 found and 0.76 made.

Seventeen of the twenty it missed are items of three lists, each under a line
that ends in a colon. Thirteen are in two lists of `5a44896f-…-2`, under a
line that says how many tests fail and one that says how many of the new
tests pass; each item names a group of those tests, some with how many. The
user typed each item `suite_passed`; the annotator typed the two lines
`suite_passed`, as the user did, and left the items unmarked. Four are in a list of `75d5aae0-…-1`,
under a line that names a file and nothing more, itself under the heading of
what the agent wrote. The user left that line unmarked and typed the four
items `file_changed`; the annotator typed the line `file_changed` and left the
items. The guide decides neither. The rule on the items under a line that says
a file was changed says that such an item does not claim the change again, but
it speaks of files, and the first two lines say how checks came out; the rule
on headings gives the lines under a heading its claim, but a line that says
how many tests fail asserts by itself and is not a heading. For the third
list, the question is whether a line that only names a file is a heading or a
line that says a file was changed. The user's reading is the one the user gave
on 2 November to the lines under a heading that named the file (§ In one
report, 14 of the route's 17 misses are misses for a person), where the
annotator read them the same way.

The other three. Two are `make format` given with its result, once in each of
the two turns of `5a44896f`: the user typed it `command_run`, the annotator
`suite_passed`. Here the rule on what a command returned decides, and the
annotator's way: a check is a command whose job is to pass or fail, and in
distiller `make format` runs the formatter in check mode, as one of the steps
of `make verify`. One is a line that gives what `git status` and `git diff`
showed, that only two files changed: the user typed it `command_run` and
`file_changed`, the annotator `command_run` alone. The rule on what a command
returned gives the first, the rule on a file's content allows the second
beside it, and "and only that" is written for a check's line alone. Of the
annotator's checkable claims, the two the user did not make are the first
`make format` line and the line that names the file. Four sentences more
differ only in `judgment`.

One claim of the user's file was a slip, and was removed at the user's leave
before these figures were taken: a span of one character, typed at the
annotation tool's prompt for a span where a type was meant.
`tools/annotate.py` checks a span against the report and not against the
sentence being typed, so it took it, and the scorer placed the claim in every
sentence holding that character. With it, the file's sha256 was
`311aba223151`, the annotator found 29 of 49 (0.59), and 27 sentences were
typed differently rather than 25.

How much of the reference such lists stand for was counted from the structure
alone: lines that end in a colon, followed by a list. In
`corpus/annotations.jsonl` the annotator typed the line checkable and left
every item unmarked in 12 lists, of 60 items, beside 968 checkable claims; in
the holdout as it stood, in 9 lists, of 36 items, beside 666. In 13 lists of
the corpus and 10 of the holdout it typed some item as well, for reasons not
looked at. The three reports hold more of them than the reference does: 17 of
the user's 48 checkable claims stand in such lists.

The route in use ran the three reports three times with `extract-5c` on 4
November, for about $0.02, into
`corpus/runs/holdout-blind-mistral-medium-3.1-extract-5c+0dbdf6be.jsonl`. In
the first pass the answer for `75d5aae0-…-1` lacked the referents of one
claim, so that turn would have been `UNKNOWN`; every other answer took 7
seconds at most.

| On the three reports | Recall, worst pass and the other two | Spurious share, worst pass and the other two |
| --- | --- | --- |
| Against the annotator | 0.89; 0.94, 0.94 | 0.62; 0.55, 0.51 |
| Against the user | 0.91; 0.94, 0.94 | 0.43; 0.21, 0.23 |

On these reports the route is nearer the user than the annotator is: it typed
the items of the three lists as the user did, and found 45 of the user's 48
checkable claims in each pass that answered for all three. What it missed of
the user's, in every pass, are a file change in the opening sentence of
`5a44896f-…-2`, a test said to fail in `5a44896f-…-3`, and the `make format`
the user typed `command_run`. Three reports are too few for a figure of their
own, and they say nothing of the corpus. They do say that the reference can
stand between a route and a person as much as the route itself: on reports
like these, recall measured against the annotator says little of recall
against a person, and part of the spurious share it measures is claims a
person makes.

The three reports have joined the holdout with the annotator's annotations, as
the entry of 3 November said they would: `corpus/holdout.jsonl` now holds 35
reports, sha256 `8432c191c9bb`, its first 32 rows unchanged
(`c932f01d206c`). The figures given for 27 of its reports, and for the 5 of 1
November, stand as measured. Over the 35, `extract-5c`'s worst pass has recall
0.78 and a spurious share of 0.58, as over the 32, and 3 of the 35 turns would
have been `UNKNOWN`. Both blind files are now in the repository.

Which reading of such lists the guide should state, whether the user's two
`command_run` for `make format` stand against the rule on what a command
returned, and whether what a command shows of the files carries
`file_changed` beside `command_run`, are the user's to decide, and are not
decided. The three reports are no longer blind: their differences have been
read, and a rule written from them would be measured on them as the anchor's
rules were on the anchor. The next blind measure needs reports not yet
captured.

### Each item of a list under a check's result is typed, and the reference is annotated again — 4 November 2026

After the blind measure above, the user decided the three questions it left
open, on 4 November. The lists go the user's way: a line that only says where,
and ends in a colon, is a heading, and the items under it are typed by what
they say was done there; under a line that says how a check came out, each
item that names some of its tests is `suite_passed`, with a count or without
one; under a line that says a file was changed, the items still do not claim
the change again. `make format` stays a check, as the rule on what a command
returned already had it, and the user's two `command_run` for it moved to
`suite_passed` in `corpus/anchor-blind.jsonl` (sha256 `7a3507354391`), as four
sentences of the anchor moved on 3 November; against that file the
annotation of 3 November finds 30 of the user's 48 checkable claims (0.62),
and the user makes 30 of its 31. What a command returned about the files the
turn changed is `file_changed` as well as `command_run`, as the user typed it.
In `docs/ANNOTATING.md` (sha256 `0f5da6f36293`) that is two rules, the first
added to the rule on headings and the second a rule of its own after the rule
on the items under a change, and two examples: a formatter run to check among
the checks of the rule on what a command returned, and a line of `git diff
--stat` after it. A dated sentence closes the section. The examples are absent
from the 117 captured reports and the 42 test files.

The annotator annotated the nine reports annotated by hand twice under it,
into `corpus/anchor-fable-lists-1.jsonl` and `-2.jsonl`.

| Against the user | Found | Made |
| --- | --- | --- |
| The three reports of the blind measure | 48 of 48 in both passes | 47 of 47, 47 of 49 |
| The six of the anchor | 30 of 31 in both passes | 32 of 36, 31 of 33 |

Every item of the three lists, the line that only names a file and the line
of `git status` came out as the user typed them. The claim of the anchor both
passes missed is in a sentence of `f89f6cd8-…-2` that the two probes of 3
November typed `command_run` in one pass and `judgment` in the other. Neither
figure is independent: the rules were written from these reports.

The corpus and the holdout were then annotated again under this guide, in
three processes. The subscription's limit stopped them after 33 reports; they
finished once it reset, with no report left out (Claude Code 2.1.316). The new
files are `corpus/annotations.jsonl` (sha256 `fad4ddaa2cee`) and
`corpus/holdout.jsonl` (sha256 `b9ce220545cb`); those of 3 November are now
`corpus/annotations-2026-11-03.jsonl` (`49b617e87aa8`) and
`corpus/holdout-2026-11-03.jsonl` (`8432c191c9bb`).

| Claims in the reference | Corpus, 3 and 4 November | Holdout, 3 and 4 November |
| --- | --- | --- |
| `command_run` | 234, 211 | 162, 169 |
| `suite_passed` | 362, 402 | 416, 448 |
| `file_changed` | 372, 409 | 119, 147 |
| `judgment` | 1,152, 1,177 | 696, 731 |
| `intent` | 242, 250 | 315, 365 |

The new reference holds 54 more checkable claims in the corpus, 19 of them on
the lines of a list, and 67 more in the holdout, 62 of them on such lines.
Lists under a line that says how a check came out with every item left
unmarked: 1 in the corpus before and none now, 4 in the holdout before and
none now. Lists under a line that says a file was changed with every item left
unmarked, as the rule on such items allows: 13 in the corpus and 4 in the
holdout. Against the user, the new corpus finds 30 of the anchor's 31
checkable claims (0.97), and the user makes 30 of its 32 (0.94); the new
holdout finds all 48 of the three reports of the blind measure, and the user
makes all 49 of its own. No repeat has been made under this guide; under the
guide of 24 October between 7 and 10 percent of sentences moved from one pass
to the next, so some of the moves in the table, `command_run` in the corpus
among them, may be the annotator's own.

The stored runs were scored again without a call.

| Worst pass, recall and spurious share | Against 3 November | Against 4 November |
| --- | --- | --- |
| `extract-5c`, the hook's prompt: the corpus | 0.75, 0.48 | 0.75, 0.46 |
| `extract-5c`: the holdout, 35 reports | 0.78, 0.58 | 0.75, 0.55 |
| `extract-5c`: 27 reports of the holdout | 0.80, 0.56 | 0.76, 0.54 |
| `extract-4`: the corpus, run of 1 November | 0.69, 0.45 | 0.69, 0.44 |
| `extract-4`: 27 reports of the holdout | 0.70, 0.54 | 0.67, 0.53 |
| `extract-3`: 27 reports of the holdout | 0.45, 0.56 | 0.44, 0.53 |

The route finds some of the claims the reference gained and not all of them:
on the corpus, `extract-5c` finds 0.86 of the `suite_passed` claims in its
worst pass where it found 0.89, 0.81 of the `file_changed` where it found
0.84, and 0.37 of the `command_run` where it found 0.36. Its spurious share
falls by two or three hundredths, as claims it made in lists now count as
found. The prompt carries neither of the two new rules, and a candidate that
does is the user's to allow. No route clears phase 1 against either reference.

### Under the guide as it stands, the annotator does not repeat itself within the threshold — 5 November 2026

At the user's request, the annotator annotated the corpus's 81 reports a
second time under the guide as it stands, `docs/ANNOTATING.md` of commit
`383afc1` (sha256 `0f5da6f36293`), with the same CLI as the reference, Claude
Code 2.1.316, into `corpus/annotations-repeat-383afc1.jsonl` (sha256
`64db7dc378de`). The run began at 22:54 UTC on 4 November; the subscription's
usage limit stopped it after 26 reports, and the other 55 were annotated from
09:20 to 09:38 UTC on 5 November, with no answer refused. It measures what the
entry of 3 November left unmeasured. The reference stays
`corpus/annotations.jsonl` (sha256 `fad4ddaa2cee`), and every figure given
against it stands.

The two annotations were scored against each other as an extractor would be,
as on 24 October; the same count, run on that day's two annotations, gives
that day's figures again.

| The annotator against itself | 24 October: the evening's guide, CLI 2.1.310 | 4 and 5 November: the guide of `383afc1`, CLI 2.1.316 |
| --- | --- | --- |
| The second annotation against the first: recall, spurious share | 0.95, 0.07 | 0.96, 0.13 |
| The first against the second | 0.96, 0.08 | 0.90, 0.12 |
| Sentences typed differently, of 4,088 | 286 (7%) | 512 (12.5%) |

The second finds 982 of the first's 1,022 checkable claims, and 333 of its
2,489 claims match none of the first's; the first finds 974 of the second's
1,087, 0.896, and 282 of its 2,449 match none. Phase 1 asks for recall 0.90
and a spurious share of at most 0.10. On 24 October an extractor as good as
the annotator would have cleared that against one annotation of it. Under the
guide as it stands it would not: the spurious share passes 0.10 both ways, and
one way recall falls just short. The holdout's repeat of 31 October went over
in one direction; the corpus now goes over in both.

Where the two differ:

- The border between `judgment`, `intent` and no claim, as in October, now in
  310 of the 512 sentences: 198 between no claim and `judgment`, 112 between
  no claim and `intent`, where October had 200 of 286. It moves the spurious
  share and not recall, which counts checkable claims only.
- How far `command_run` reaches. The second annotation makes 269 `command_run`
  claims where the first makes 211. It has 64 the first lacks, in sentences
  the first typed `judgment` (52) or left unmarked (12), and lacks 6 of the
  first's. In October the two differed on 19 `command_run` claims; now on 70.
- `suite_passed` and `file_changed` stay close: the second finds 0.98 of the
  first's `suite_passed` claims and 0.94 of its `file_changed`, and the first
  0.97 and 0.91 of the second's.

What the first annotation types `command_run`, the second does too, 205 of
211. Of the 123 such claims that `extract-5c`'s worst pass missed on the
corpus, the second makes 120, so those misses are the extractor's, not the
reference's variation. Scored against the second annotation, `extract-5c`'s
worst pass has recall 0.70 and a spurious share of 0.49, against 0.75 and 0.46
against the reference, and it finds 0.30 to 0.33 of the `command_run` claims in
its three passes, against 0.37 to 0.42. Which of two annotations by the same
annotator stands as the reference moves the route's recall by about five
hundredths, and the reference is the kinder of the two to this route.

Against the six reports of the anchor (sha256 `bb2906b07b52`), the second
annotation finds 31 of the user's 31 checkable claims and the user made 31 of
its 33, where the reference finds 30 of 31 and the user made 30 of its 32; 13
of the second's 75 claims are not the user's, and 13 of the reference's 72.
The anchor does not tell the two apart.

Not measured: whether the guide or the CLI made the difference, since both
changed between the two repeats, and how much of it is chance, with one repeat
each time. The holdout was not annotated again. What follows is the user's to
decide: whether to make the guide more repeatable at those two borders and
measure a repeat again, or to measure against more than one annotation, which
would change how the frozen numbers of phase 1 are measured and is a matter
for the requirements (A-12, § Rollout phases). A candidate prompt for the
`command_run` claims the route misses is the user's to allow, and its runs can
be scored against whichever reference stands.

### extract-6c goes into the hook — 5 November 2026

At the user's leave, three candidates were written from `extract-5c` and
measured on the corpus and the holdout, three passes each, with distiller's
route, on 5 November between 10:13 and 11:53 UTC. Their examples are absent
from the 117 captured reports and the 42 test files.

- `extract-6a` (`extract-6a+21b220f1`) is `extract-5c` with the guide's rules
  of 4 November, on a line that only says where and on the items under a
  check's result, its examples of a formatter run to check and of what a
  command returned about the files, and three rules for the `command_run`
  claims the route missed: what a run returned is `command_run` in whatever
  form the report gives it, a time, a count, an output or an error, once the
  report says the run was made; one sentence can hold an edit and a search,
  and an instruction can carry a claim; and a row that says what a run that is
  not a check returned is `command_run`.
- `extract-6b` (`extract-6b+aa80bad9`) is `extract-6a` with five rules against
  what the route marked and the reference did not: a description of the code
  is left out, the agent's own included; a step the report gives as still to
  come is `intent`, in whatever tense; what the agent expects a check to give
  is `judgment`; reading a file is not running it; and a row that names a test
  and says what it checks, or how many cases it has, is left out.
- `extract-6c` (`extract-6c+bf5a552b`) is `extract-6b` without the first of
  the five.

| Worst pass | `extract-5c` | `extract-6a` | `extract-6b` | `extract-6c` |
| --- | --- | --- | --- | --- |
| The corpus: recall, spurious share | 0.75, 0.46 | 0.78, 0.50 | 0.77, 0.47 | 0.80, 0.44 |
| The corpus against its second annotation | 0.70, 0.49 | 0.75, 0.51 | 0.73, 0.49 | 0.76, 0.47 |
| The holdout, 35 reports | 0.75, 0.55 | 0.84, 0.56 | 0.83, 0.49 | 0.84, 0.50 |
| 27 reports of the holdout: recall | 0.76 | 0.85 | 0.84 | 0.85 |
| The corpus: `command_run`, `suite_passed` and `file_changed` | 0.37, 0.86, 0.81 | 0.58, 0.82, 0.84 | 0.54, 0.86, 0.78 | 0.61, 0.87, 0.83 |
| Turns `UNKNOWN`: the corpus, the holdout | 2, 3 | 4, 6 | 2, 2 | 2, 2 |
| Answers past 20 seconds: the corpus, the holdout | 0 of 239, 2 of 100 | 1 of 235, 13 of 104 | 0 of 239, 4 of 105 | 0 of 238, 2 of 104 |

Corrected on 6 November 2026: two cells of the table above were rounded from
three decimals rather than from the counts. `extract-6b`'s spurious share is
0.4847 against the corpus's second annotation and 0.4848 on the holdout, 0.48
both, not 0.49. The other cells hold when rounded from the counts.

What the three showed. Each finds more of the `command_run` claims: in the
holdout's worst pass, the sentences the reference types `command_run` and the
route typed `judgment` fall from 63 with `extract-5c` to 2 with `extract-6c`.
`extract-6a` paid for it: it typed 49 of the corpus's `suite_passed` claims
`command_run`, its spurious share rose, and its answers grew long enough that
13 of the holdout's 104 passed 20 seconds. The five rules of `extract-6b` cut
what the route marks that matches nothing: of its checkable claims in the
corpus's worst pass, 588 matched nothing, against 707 for `extract-5c`, and
its `suite_passed` claims in sentences the reference left unmarked fell from
194 to 87; 123 of the 194 were rows of tables. Its spurious share on the
corpus did not fall with them, since it marked `intent` in 112 sentences the
reference left unmarked, against 63, and made fewer claims in all. It also
found fewer `file_changed` claims, 0.78 against 0.81. Of the 33 that
`extract-5c` found in two passes or three and it found in one or none, 5 are
in a report it got no usable answer for, and most of the others say how a
file's content changed without an editing verb, which is what the rule on
describing the agent's own code would take away.

Without that rule, `extract-6c` keeps most of the rest and finds 0.83 of the
`file_changed` claims. Against `extract-5c`, counting the claims found in two
passes or three, it finds 28 `file_changed` claims more and 17 fewer, 51
`command_run` more and 5 fewer, and 11 `suite_passed` more and 23 fewer; 27
of its `suite_passed` misses in the worst pass are results of checks typed
`command_run`. Of its checkable claims, 650 matched nothing in the corpus's
worst pass and 477 in the holdout's, against 707 and 661, and its
`suite_passed` claims in table rows the reference left unmarked fell from 123
to 52. With one run of each, part of what separates `extract-6b` from
`extract-6c` beyond `file_changed` may be the route's variation from run to
run.

Its answers are shorter than `extract-5c`'s: a median of 646 output tokens on
the corpus against 722, and 1,120 on the holdout against 1,455. On the corpus
none passed 20 seconds, the slowest taking 18.8; on the holdout 2 of 104 did,
as 2 of 100 did for `extract-5c`, though the provider generated about a sixth
slower on 5 November, at a median of 195 tokens a second against 232. The
answers left unusable were of the kind seen before, a claim without its
referents.

So `src/ledger/prompts/extract.md` is now `extract-6c+bf5a552b` byte for byte,
and the figures above are its own. `extract-5c` stays as
`prompts/extract-5c.md`, and `extract-6a` and `extract-6b`, measured and not
taken, as their own files. The plugin is 0.3.4. The prompt now holds rules the
guide does not state, each drawn from a rule it does, and whether to write
them into the guide is the user's to decide. Phase 1 is not cleared, and the
hook stays an observer. The six runs are in `corpus/runs/`, with the prompt's
version in their names, and cost $2.70.

### The guide's newer rules, not the annotator, doubled its variation, and the annotator has moved since October — 5 November 2026

The entry before the last could not tell whether the guide or the CLI made
the annotator vary more. At the user's request the annotator annotated the
corpus's 81 reports twice more on 5 November under the guide of 24 October,
`docs/ANNOTATING.md` of commit `a272162` (sha256 `afa2de54c994`), the last to
change it before 2 November, with the reference's CLI, Claude Code 2.1.316.
`tools/annotate_model.py` and the sentence cut are as they were on 24
October, so only the guide differs from the annotations of 4 and 5 November.
The first is `corpus/annotations-repeat-a272162.jsonl` (sha256
`61b5ab16c9cf`), made from 12:18 to 14:31 UTC, and the second
`corpus/annotations-repeat-a272162-2.jsonl` (sha256 `a63d9e1b9591`), from
14:49 to 15:53 UTC. The subscription's usage limit stopped each once, and no
answer was refused.

| Two annotations of the corpus, each scored against the other | Recall | Spurious share | Sentences typed differently, of 4,088 |
| --- | --- | --- | --- |
| The guide of 24 October, both made that day, CLI 2.1.310 | 0.95, 0.96 | 0.07, 0.08 | 286 (7%) |
| The guide of 24 October, both made on 5 November, CLI 2.1.316 | 0.95, 0.97 | 0.05, 0.05 | 200 (4.9%) |
| The guide as it stands, made on 4 and 5 November, CLI 2.1.316 | 0.96, 0.90 | 0.13, 0.12 | 512 (12.5%) |
| The guide of 24 October, each of 5 November against each of 24 October | 0.92 to 0.94, 0.88 to 0.89 | 0.15 to 0.16, 0.11 to 0.12 | 453 to 509 |

Under one guide, annotating twice the same day, the annotator repeats itself
within the threshold, as it did on 24 October and a little better; under the
guide as it stands it does not. The rules added since 2 November are what more
than doubled its variation. Between the two annotations of 5 November under
the guide of 24 October, the border between `judgment`, `intent` and no claim
moves in 126 sentences, against 310 between the two under the guide as it
stands, and one annotation types a sentence `command_run` where the other does
not in 17 sentences, against 70.

The annotator has also moved since October. Under the same guide, the two
annotations of 5 November differ from the two of 24 October about as much as
the two under the guide as it stands differ from each other, and they differ
in one direction: 401 and 410 `file_changed` claims against 361 and 362, 202
and 220 `intent` against 157 and 163, and 116 and 113 `command_run` against 94
and 103. With the code and the guide the same, what changed is the CLI, from
2.1.310 to 2.1.316, or the model as it is served. Annotations made on
different dates are therefore not one reference, and an annotation made today
does not read as one made in October.

Not measured: the pair under the guide as it stands was annotated over a
night, the pair of 5 November within four hours, so a change
between days adding variation that hours do not is unlikely but not ruled
out. What follows is the user's to decide: which rules of the guide to make
more repeatable while keeping the readings the user gave. The reference is
unchanged, and so is every figure given against it.

### Two rules make the annotator repeat itself again, and the reference is annotated under them — 5 November 2026

The two annotations of the corpus under the guide as it stood typed 512
sentences differently, and 448 of them are sentences the two annotations
under the guide of 24 October type alike. Most fall in two places: 310 are at
the border between `judgment`, `intent` and no claim, 216 of those in items
or rows under a lead line that describe a test, a case, the code or a plan,
which the guide of 24 October left unmarked; and 62 are sentences one
annotation types `command_run` and the other not, mostly how the code behaves,
under a label or a numbered section. At the user's request the guide gained
two rules for them.

- A description gets Enter wherever it stands, under a lead line as anywhere:
  a line that says what the code, a test or a case does asserts nothing about
  the work, whatever the line above it says was done. A line that says how a
  file's content changed is not a description, and is `file_changed` by the
  rule on a file's content wherever it stands.
- In the rule on what a command returned, a line stands under a run when the
  report says that run in the line itself, in the line it is an item of, or in
  the heading or the lead line of its section. A label, or a numbered section,
  says none.

Their examples are absent from the 117 captured reports and the 42 test files,
and a dated sentence closes the section. `docs/ANNOTATING.md` is now sha256
`349bb2305511`.

The rules were tried on the nine reports annotated by hand, twice for each of
three wordings, into `corpus/anchor-fable-descriptions-1.jsonl` and `-2`, `-b-1`
and `-b-2`, and `-c-1` and `-c-2`. The first wording said a description of
what the code or a test holds, and two of the user's `file_changed` items, in a
list under a line that says how a commit's message changed, went to
`judgment`. The second added that a change of a file's content is not a
description, and a sentence saying when an item claims something, which made
the annotator type `file_changed` items under a change and a heading that names
where some decisions were noted; the third, the guide as it stands, drops that
sentence. In five of the six passes the annotator typed `command_run`, as the
user did, a line that says what a tool's run did not do, which the guide as it
stood had typed `judgment`. In every wording the two items under the line about
the commit's message went to `judgment` in most passes. The user chose to move
them to `judgment` in `corpus/anchor.jsonl`, now sha256 `3c94491963ee`: a
commit's message is not a file, the join verifies `file_changed` only against a
write to a path, so the claim would be `UNSUPPORTED` however true, and the
amend itself is claimed in the line that gives the commit's new id. On nine
reports that already varied little, the two passes of each guide differ in
about the same number of sentences.

To measure what the rules do where the annotator varies, 40 of the corpus's
75 reports outside the anchor were drawn with seed `20261105` and annotated
twice under the guide as it stands, from 20:07 to 20:24 UTC, into
`corpus/annotations-half-g349bb23-1.jsonl` (sha256 `bf909bf09675`) and `-2`
(sha256 `0c8dddedd722`).

| Two annotations of the same 40 reports, each scored against the other | Recall | Spurious share | Sentences typed differently, of 2,171 | At the border of `judgment`, `intent` and no claim | `command_run` in one only |
| --- | --- | --- | --- | --- | --- |
| The guide of 4 November, the annotations of 4 and 5 November | 0.95, 0.87 | 0.15, 0.17 | 335 (15.4%) | 205 | 54 |
| The guide as it stands | 0.98, 0.96 | 0.06, 0.04 | 107 (4.9%) | 64 | 16 |
| The guide of 24 October, the two of 5 November | 0.95, 0.96 | 0.06, 0.05 | 116 (5.3%) | 71 | 9 |

Under the guide as it stands the annotator repeats itself as it did under the
guide of 24 October while keeping the readings added since. An extractor as
good as the annotator would come under the 0.10 phase 1 allows against one
annotation of it. Which rule does what is not separable here: both changed at
once.

The user then had the reference annotated again under the guide as it stands.
The corpus is the first annotation of the 40 reports drawn and an annotation
of the other 41, made from 20:29 to 20:41 UTC; the holdout's 35 reports were
annotated from 21:01 to 21:14 UTC. No answer was refused. They are now
`corpus/annotations.jsonl` (sha256 `20ce8755afcd`) and `corpus/holdout.jsonl`
(sha256 `86126b791b69`), and the ones they replace are kept as
`corpus/annotations-2026-11-04.jsonl` (sha256 `fad4ddaa2cee`) and
`corpus/holdout-2026-11-04.jsonl` (sha256 `b9ce220545cb`).

| Claims in the reference, before and now | The corpus | The holdout |
| --- | --- | --- |
| `command_run` | 211, 232 | 169, 171 |
| `suite_passed` | 402, 396 | 448, 439 |
| `file_changed` | 409, 391 | 147, 134 |
| `judgment` | 1,177, 1,074 | 731, 542 |
| `intent` | 250, 177 | 365, 203 |

Against the six reports of the anchor the annotation finds all 29 of the
user's checkable claims, the user made 29 of its 31, and 12 of its 76 claims
are not the user's; against the three reports annotated blind it finds all 48,
and the user made all 47 of its own. Both measures are of reports the rules
were tried on.

| Worst pass, recall and spurious share | Against 4 November | Against 5 November |
| --- | --- | --- |
| `extract-6c`, the hook's prompt: the corpus | 0.80, 0.44 | 0.78, 0.49 |
| `extract-6c`: the holdout, 35 reports | 0.84, 0.50 | 0.85, 0.55 |
| `extract-6c`: 27 reports of the holdout | 0.85, 0.49 | 0.85, 0.54 |
| `extract-5c`: the corpus | 0.75, 0.46 | 0.74, 0.51 |
| `extract-5c`: 27 reports of the holdout | 0.76, 0.54 | 0.77, 0.58 |
| `extract-4`: 27 reports of the holdout | 0.67, 0.53 | 0.68, 0.55 |
| `extract-3`: 27 reports of the holdout | 0.44, 0.53 | 0.45, 0.59 |

Corrected on 6 November 2026: three cells of the table above were rounded
from three decimals rather than from the counts. `extract-6c`'s spurious share
on the corpus against 5 November is 0.4849, 0.48, not 0.49; on 27 reports of
the holdout it is 0.4849 against 4 November and 0.5345 against 5 November,
0.48 and 0.53, not 0.49 and 0.54. The rises the next paragraph gives stay
between two and six hundredths.

The reference now leaves unmarked descriptions the route still types
`judgment` or `intent`, so every spurious share rises by two to six
hundredths. The prompt carries neither rule, and a candidate that does is the
user's to allow. Not measured: the annotator's agreement with itself over the
whole corpus and the holdout under the guide as it stands; the 40 reports
drawn are the measure of it. Phase 1 is not cleared.

### extract-7 and extract-7b, with the guide's two rules of 5 November, stay out of the hook — 6 November 2026

At the user's leave, two candidates that carry the guide's two rules of 5
November were written from `extract-6c` and measured on the corpus and the
holdout against the reference of that day, three passes each, with
distiller's route, between 22:27 UTC on 5 November and 09:27 UTC on 6
November.

- `extract-7` (`extract-7+c8d01670`) is `extract-6c` with the two rules where
  the guide puts them, and with the guide's examples. The sentence on what a
  line stands under follows the rule on what a command returned, and the rule
  on what a run returned now asks for a line that stands under that run,
  where it asked that the report say the run was made. The rule that a
  description is left out wherever it stands follows the rule on the items
  under a check's result. One wording is not the guide's: a description is
  left out "under a heading or a lead line", where the guide says a lead line,
  since the route marked the items under headings that say what was written.
- `extract-7b` (`extract-7b+25e161ad`) is `extract-7` with one exception to
  the rule on descriptions: a row that says which tests catch or cover a case
  or a mutant, or how many, is not a description, and is `suite_passed` by the
  rule on tables, which now names mutants too. The exception is for rows only.
  Of the table rows that speak of mutants or of tests that catch or detect, by
  their words or their table's header, the reference types 48 of 51 in the
  corpus and 178 of 201 in the holdout `suite_passed`; of the items under a
  lead line that do, by their words or their lead line's, 12 of 49 and 4 of
  30.

`extract-7`'s examples are the guide's, absent from the 117 captured reports
and the 42 test files, and `extract-7b` adds none.

The endpoint refused calls with HTTP 429 in bursts of a minute or two.
`extract-7`'s first runs, the corpus and the holdout at once from 22:27 UTC,
lost 10 of the corpus's 81 first-pass calls and 9 of the holdout's 35, all in
the first minute. Both ran again from 07:27 UTC on 6 November, one after the
other, into files whose names end in `-r2`: the holdout lost no call, and the
corpus lost 7 calls of its first pass and 13 of its second. `extract-7` is
judged here on the three passes over the corpus in which no call was refused,
the second and third of the first run and the third of the second, and on the
holdout's second run. `extract-7b` ran from 08:48 to 09:27 UTC, one set after
the other, and no call was refused. The answers left unusable, five, five and
three on the corpus and one, none and one on the holdout, were of the kind
seen before, a claim without its referents.

| Worst pass, against the reference of 5 November | `extract-6c` | `extract-7` | `extract-7b` |
| --- | --- | --- | --- |
| The corpus: recall, spurious share | 0.78, 0.48 | 0.78, 0.47 | 0.76, 0.50 |
| The holdout, 35 reports | 0.85, 0.55 | 0.81, 0.50 | 0.85, 0.52 |
| 27 reports of the holdout | 0.85, 0.53 | 0.82, 0.48 | 0.86, 0.52 |
| The corpus against the reference of 4 November | 0.80, 0.44 | 0.81, 0.43 | 0.78, 0.47 |
| The corpus: `command_run`, `suite_passed` and `file_changed` | 0.55, 0.87, 0.82 | 0.57, 0.88, 0.81 | 0.55, 0.84, 0.81 |
| The holdout: the same | 0.68, 0.91, 0.77 | 0.72, 0.85, 0.78 | 0.74, 0.91, 0.77 |
| Claims found in two passes or three: the corpus, of 232, 396 and 391 | 126, 343, 322 | 133, 331, 311 | 136, 344, 321 |
| The same: the holdout, of 171, 439 and 134 | 125, 405, 105 | 124, 404, 106 | 128, 405, 107 |
| The user's own checkable claims found: the anchor, of 29 | 23 | 21 | 20 |
| The same: the three reports annotated blind, of 48 | 45 | 43 | 40 |
| Turns `UNKNOWN`: the corpus, the holdout | 2, 2 | 2, 1 | 1, 1 |
| Answers past 20 seconds: the corpus, the holdout | 0 of 238, 2 of 104 | 0 of 238, 2 of 105 | 0 of 240, 1 of 104 |
| Median output tokens: the corpus, the holdout | 646, 1,120 | 496, 955 | 570, 996 |

What the two showed. The rule on descriptions takes away most of what it was
written against. Over each candidate's three passes on average, the claims
that match nothing fall from 1,212 a pass with `extract-6c` to 1,063 with
`extract-7` on the corpus, and from 1,010 to 844 on the holdout; its
`suite_passed` claims in table rows under a lead line that the reference
leaves unmarked fall from 42 a pass to 8 on the corpus, and its `judgment`
claims in unmarked lines under a lead line from 228 to 179 on the corpus and
from 160 to 110 on the holdout. The spurious share moves less, because the
route also stops marking `judgment` claims the reference keeps: on the corpus
those it matches fall from 499 a pass to 397.

`extract-7`'s worst pass on the holdout is one answer. In one pass of three,
in `64907bb0-…-5`, it left out the 24 rows of a table of mutants with the
tests that catch each, and typed eight results of checks `command_run`: of
the report's 38 `suite_passed` claims it found 6, where its other two passes
found 37. The rule on descriptions reads such a row as what a case does,
where the rule on tables makes it a result. `extract-7b`'s exception mends that
report, of whose 38 `suite_passed` claims it finds 36, 36 and 30 in its three
passes, and its worst pass on the holdout goes back to 0.85. It also draws in the tables
that say what each test covers, which the reference leaves unmarked: against
`extract-7`, its `suite_passed` claims in unmarked table rows rise from 8 a
pass to 30 under a lead line on the corpus, and from 58 to 137 on the
holdout. On the corpus its worst pass, the first, is a few answers on long
reports: in one of them it found 20 of 50 checkable claims, against 31 in
each of its other two passes.

Counted by the claims found in two passes or three, the three prompts are
within a few claims of each other. Against the user's own annotations both
candidates find fewer than `extract-6c`, and among the losses of both, an
item of one report of the anchor that names a file and two functions in it,
which the user typed `file_changed`, is left out in every pass, as a
description. At temperature 0 the route gives a report the same claims in two
passes for only 22 to 48 of the 78 or 79 corpus reports both passes answered,
and 5 to 14 of the holdout's 34 or 35, depending on the prompt and the pair of
passes, and one answer
or a few on long reports move a worst pass by two to four hundredths, which
is the size of the differences between the three prompts. By its worst pass,
neither candidate does better than `extract-6c`.

So the hook keeps sending `extract-6c`, and the two candidates stay as
`prompts/extract-7.md` and `prompts/extract-7b.md`, measured and not taken, as
the user agreed on 6 November. Their runs are in `corpus/runs/`, four files for
`extract-7` and two for `extract-7b`, and cost $1.52 and $0.84. Phase 1 is not
cleared: every worst pass above has a spurious share between 0.47 and 0.55,
against the 0.10 it allows. What would move that next is not a rule of this
size but another route, or another way for phase 1 to judge a candidate,
which is a matter for the requirements (§ Rollout phases). Both are the user's
to decide.

### Neither another route nor the guide itself brings the spurious share down — 6 November 2026

Since rules of the size of `extract-7`'s had stopped standing out from the
route's own variation, the user had other routes screened with `extract-6c` on
6 November, the first screen of other models since 25 October, which used
`extract-3` and the reference of that day. The candidates came from
OpenRouter's public lists of models and of zero-retention endpoints, read that
morning. Of 453 models, 187 are not of the annotator's family, read text, hold
32,000 tokens or more, take a JSON schema and a temperature, and do not
require reasoning. Four were taken, at the user's leave, among the strongest
of them by OpenRouter's indices, each on a zero-retention endpoint:
`mistralai/mistral-large-4-0` on `mistral/zdr`, `xiaomi/mimo-v2.6-pro` on
`deepinfra/fp8`, `upstage/solar-pro4` on `upstage/zdr`, a provider the user
agreed to that day, and `deepseek/deepseek-v4-flash` on `deepinfra/fp8`. Their
files in `corpus/routes/` are copies of distiller's configuration that differ
in the model, the provider and a switch for reasoning.

The client speaks OpenRouter's `/messages`, and each endpoint honoured a
different switch or none. On the fixed report `mistral-large-4-0` reasoned
whether it was sent `reasoning: {"effort": "none"}`, `reasoning: {"enabled":
false}` or a top-level `reasoning_effort: "none"`, spending 3,606 to 5,851
thinking tokens and 27.9 to 43.3 seconds a call, one call past 60, and it
refused `thinking: {"type": "disabled"}` with HTTP 400. Under the 20-second
deadline it is no candidate, and it ran no pass. `mimo-v2.6-pro` reasoned
under the first two forms and stopped under `thinking: {"type": "disabled"}`,
which its file sends; `solar-pro4` and `deepseek-v4-flash` did not reason
under `effort: none`. The other three ran the corpus once each, from 11:47 to
12:34 UTC, and no call was refused.

| Against the reference of 5 November | Recall | Spurious share | Turns `UNKNOWN`, of 81 | Median call, 95th percentile | Tokens a second | A pass |
| --- | --- | --- | --- | --- | --- | --- |
| `mistral-medium-3.1` with `extract-6c`, the route, worst of three passes | 0.78 | 0.48 | 2 | 4.1s, 11.8s | 232 | $0.17 |
| `mimo-v2.6-pro`, `deepinfra/fp8` | 0.81 | 0.43 | 28 | 12.9s, 76.9s | 57 | $0.11 |
| `deepseek-v4-flash`, `deepinfra/fp8` | 0.74 | 0.44 | 10 | 8.1s, 24.9s | 81 | $0.03 |
| `solar-pro4`, `upstage/zdr` | 0.69 | 0.47 | 15 | 10.7s, 37.2s | 50 | $0.07 |
| `mistral-medium-3.1` with the guide as its prompt | 0.70 | 0.49 | 9 | 5.5s, 34.2s | 226 | $0.22 |

What the screen showed. Only `mimo-v2.6-pro` does better than medium on both
counts, and by a little: in its one pass it finds 0.81 of the checkable claims
and 0.88 of the `file_changed` ones, against 0.82 to 0.83 in medium's passes,
and 0.43 of what it extracts matches nothing. On its one zero-retention
endpoint at a price like medium's it generates about 57 tokens a second, a
quarter of medium's speed, and 28 of its 81 calls passed 20 seconds, the
slowest at 123; its other zero-retention endpoint costs about ten times as
much. The other two find less than medium and mark about as much that matches
nothing. On every route the spurious share stays between 0.43 and 0.49, so a
stronger model is not what keeps it far from 0.10.

To tell whether the gap is the prompt's, which condenses the guide and adds
readings of its own, the user then had the route sent the guide itself.
`extract-guide` (`extract-guide+35709cd6`) is the instructions
`tools/annotate_model.py` gives the annotator and the whole of
`docs/ANNOTATING.md` as it stands (sha256 `349bb2305511`), changed only where
the extractor answers otherwise: by sentence number, with referents and no
span, and with one claim for each part of a sentence the guide splits. It ran
the corpus once with distiller's route, from 12:44 to 12:58 UTC, and is the
table's last row. Given the guide, the route marks more opinions, 1,449 claims
of `judgment` or `intent` against 1,031 to 1,106 a pass with `extract-6c`,
finds fewer `command_run` claims, 0.37 against 0.55 to 0.61, and leaves the
spurious share where it was. The condensed prompt does better than the guide
it condenses, and the gap is not in the wording.

Nor is it there because the reference is a model's. Against the user's own
annotations, `extract-6c`'s passes have a spurious share of 0.36 to 0.40 on
the six reports of the anchor and 0.39 to 0.45 on the three annotated blind:
the route marks more than a person does, as it marks more than the annotator.

So the hook keeps sending `extract-6c` on medium, as the user agreed on 6
November, and phase 1 stays an observer. The declared numbers do not move
(REQUIREMENTS § Rollout phases): a shortfall sends us to the misses, and the
misses have been read. What is left is not a rule, a prompt or a route but a
change of design, such as a second step that reviews each checkable claim
before it is kept, within the same 20 seconds, and that is the user's to
decide. The screen cost about $0.30 with its probes and the guide's run $0.22,
and $4.80 is left. The four route files, `prompts/extract-guide.md` and the
four runs are in the repository.

### A span typed by hand must fall in the sentence it is typed for — 6 November 2026

On 4 November a span of one character, typed at the annotation tool's prompt
for a span where a type was meant, went into the user's blind annotation, and
the scorer placed it in every sentence holding that character (§ On three
reports annotated blind, the annotator finds 0.58 of the user's checkable
claims). The tool checked a span against the whole report, and the scorer
places a span by its text: in the sentences it is, failing those in the ones
it is part of, failing those in the ones it crosses. At the user's request,
`tools/annotate.py` now refuses a span typed by hand that the scorer would not
place in the sentence being typed, or would place in another sentence as well,
and asks again. A span that crosses a cut made in the wrong place, into the
sentence beside it, is still taken.

The placement the scorer gives a span, which the tool now checks by, moved
from `tools/measure_recall.py` to `ledger/sentences.py`, beside the cut, so
that the two cannot drift apart. No figure moves: `extract-6c`'s worst corpus
pass scores 776 of 991 and 1,269 of 2,617 before and after. No span of
`corpus/anchor.jsonl` or `corpus/anchor-blind.jsonl` is placed in more than one
sentence. `docs/ANNOTATING.md` still says only that a span not in the report
word for word is refused, which stays true; saying more would change the digest
of the guide the reference was annotated under, and that is the user's to
decide.

### A review step after the extraction costs recall faster than it saves the spurious share — 6 November 2026

With no route and no wording bringing the spurious share down, the user had
the one structural idea left written up and measured: a second call that reads
the extractor's answer and drops the claims the report does not make, never
adding or retyping one (`docs/precision-step.md`). It was measured on answers a
corpus run had kept, so that only the step was new. The route in the hook, with
the review prompt `review-2+c0704259` (`prompts/review-2.md`: `extract-6c`'s
typing rules, the claims one a line with their sentence, and a verdict asked on
each), reviewed the 80 answers of the first stored pass of `extract-6c`, for
$0.16. A first wording, asking for the numbers of the claims to drop, answered
with sentence numbers on its first report and was replaced before any
measurement.

| The first pass of `extract-6c` on the corpus | Before the review | After it |
| --- | --- | --- |
| Recall on checkable claims | 0.78 | 0.58 |
| Spurious share | 0.47 | 0.38 |
| `command_run`, `suite_passed`, `file_changed` found | 127, 332, 317 | 85, 255, 238 |
| Claims | 2,498 | 1,776 |

The review dropped 722 claims: 495 matched nothing in the reference, and 227
were claims the reference makes, most of them readings the guide's finer rules
create. A review took 3.7 seconds at the median and 19.8 at the 95th
percentile, and 4 of the 80 passed 20 seconds before the extraction's own time
is added. The spurious share falls by nine hundredths and recall by twenty: the
route reviewing itself is the route made more cautious, which the note said in
advance would not count. The step is not proposed for the pipeline, and the
other passes and the holdout were not reviewed. Not tried: a reviewer of
another family, or one asked about one claim type at a time.
`tools/measure_review.py` measures such a step, and the reviews are in
`corpus/runs/review-mistral-medium-3.1-review-2+c0704259-extract-6c+bf5a552b-pass1.jsonl`.
Phase 1 stays an observer.

### On semantic-diff-weaver the route finds a little less, and marks less that matches nothing — 6 November 2026

Distiller is paused until 14 November, when the user decides whether to go on
with it. So, at the user's request, the route was measured on another
project's reports, `semantic-diff-weaver`, where the plugin never ran. Its
reports were rebuilt from its Claude Code transcripts by
`tools/backfill_reports.py`, by the rule the Stop handler follows: each
message of a session's main thread that ended its turn, `stop_reason`
`end_turn`, is the report, its text blocks in order. A turn interrupted or cut
by an API error does not end so, and is left out as the handler leaves it out.
A message copied into a resumed session's transcript is written once. Each
report is written through the handler's own `turn.capture`, with a header note
that it was rebuilt and that no evidence was recorded. The transcripts held
423 such reports from 34 sessions, between 30 July and 6 November, with a
median of 890 characters and 10 sentences, far shorter than distiller's. They
are in `~/code/claim-ledger-corpora/semantic-diff-weaver`, outside both
repositories, beside a copy of distiller's configuration;
`semantic-diff-weaver` itself was not touched. The user agreed to these
reports going to the route and to the annotator.

100 of them, drawn with seed `20261106`, were annotated by the annotator as
the corpus is, `claude-fable-5-1` through Claude Code 2.1.316 under the guide as
it stands (`docs/ANNOTATING.md` sha256 `349bb2305511`), in three processes,
and none was refused. The annotation holds 1,199 claims in 1,425 sentences,
422 of them checkable, and is in that folder (sha256 `351d0bdc13c3`). It is not
in this repository, since its spans are text of those sessions, until the user
decides whether it should be. `extract-6c` then ran the sample three times
with distiller's route, from 15:12 to 15:38 UTC, for $0.23, into
`corpus/runs/sdw-mistral-medium-3.1-extract-6c+bf5a552b.jsonl`.

| Worst pass of `extract-6c` | distiller's corpus, 81 reports | `semantic-diff-weaver`, 100 reports |
| --- | --- | --- |
| Recall on checkable claims | 0.78 | 0.73 |
| Spurious share | 0.48 | 0.38 |
| `command_run`, `suite_passed`, `file_changed` | 0.55, 0.87, 0.82 | 0.58, 0.89, 0.82 |
| Turns `UNKNOWN` | 2 of 81 | 6 of 100, 4 of them refused with HTTP 429 |
| Median call, 95th percentile | 4.1s, 11.8s | 2.4s, 11.9s |

What it showed. On these short reports the annotator marks a claim in most
sentences, so few sentences are left unmarked for the route to over-mark, and
most of what matches nothing is typed otherwise: about 250 claims a pass,
against about 100 in unmarked sentences. The commonest is a different border
from distiller's: in the first pass, 87 claims the route typed `file_changed`
are sentences the annotator typed `judgment`, sentences that say how the code
behaves now, which the route reads as a change to a file's content and the
guide reads as a claim about behaviour. `command_run` is as hard to find here
as in distiller. Which border costs the route its precision depends on the
project's reports, and neither figure is near the 0.90 and 0.10 of phase 1.

Not checked: no report of this sample has been annotated by hand, so these
figures measure agreement with the annotator on reports it has not been set
against a person on; how far the annotator repeats itself on them; and
whether a rebuilt report is exactly what the handler would have captured. The
corpus phase 1 is judged on stays distiller's, and phase 1 stays an observer.
