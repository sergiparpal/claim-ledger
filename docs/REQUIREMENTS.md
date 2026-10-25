# Claim Ledger — Requirements v0.1

2026-09-19 · @Someone

## Purpose

Every factual claim in an agent's end-of-turn report gets a verdict that the agent did not write. The verdict comes from the harness's own execution record, not from the model's account of it.

Today the same model produces the work, the report and the confidence. A sentence backed by a passing test suite and a sentence backed by nothing read alike. The harness already holds what separates them — which commands ran, with what exit status, at what time, against which files — and never consults it.

This is a requirements document. It states what the system must do and what it must never do. The technical design follows separately.

**Name.** `claim-ledger` is provisional. Last edited 25 October 2026, when R-45 came to name the provisional route, `mistral-medium-3.1` with the prompt `extract-3`, since no route measured clears phase 1; on 23 October the extractor corpus came to be annotated by a model of another family than the routes it measures, anchored by a few reports annotated by hand (A-12), and § Rollout phases said what the phase-1 numbers measure against it: a copy of this document without this sentence is stale.

**Validity.** The approach covers claims about what the agent did inside a recorded environment. It does not cover claims about the world or about the quality of a design, and no amount of engineering here will make it.

## Scope

v1 covers one Claude Code session on its main thread, in one repository.

**In scope**

- Claims about commands run, files changed and checks passed during the session.
- Verdicts assigned by a deterministic join against an evidence log the harness writes.
- A ledger appendix shown to the user at the end of every turn.
- A consequence table owned by the user, used in v1 only to mark which actions count as consequential.
- A persistent log of claims and verdicts, for later calibration.

**Out of scope in v1**

- Blocking a turn. The gate is specified in this document but ships in phases 2 and 3, once the extractor has been measured. v1 observes and reports.
- Repeating what the permission system already does. Claude Code's own permission rules and hooks stop consequential actions before they run; this system only notices when an action that did run goes unmentioned.
- Subagent turns, parallel worktrees and multi-repository sessions.
- Claims about the world, about design quality, or about anything with no event behind it.
- Confidence figures of any kind, until the calibration log reaches a declared sample size.
- Rewriting the report. The system annotates or blocks; it never edits the agent's text.
- Enforcement written as instructions to the model. Every rule lives in harness-side code.

## Definitions

The two vocabularies below are closed. Nothing outside them may be assigned by any component.

- **Turn** — one agent response, ending when the agent stops.
- **Report** — the final assistant message of a turn, the text the user actually reads.
- **Claim** — one assertion in the report about the state of the work, held as a verbatim span.
- **Evidence event** — one record the harness writes when a tool call runs: tool, arguments, outcome, end time, and the files it touched.
- **Referent** — a file path, command, or test name a claim mentions, used to join it to evidence.

**Claim types**

| Type | Example | Checkable |
| --- | --- | --- |
| `command_run` | "I ran the migration script" | yes |
| `suite_passed` | "the tests pass" | yes |
| `file_changed` | "I updated the parser" | yes |
| `judgment` | "this design will scale" | no |
| `intent` | "next I would add a cache" | no, not an assertion about work done |

A sixth type, `behaviour_checked` ("it now handles empty input"), is deliberately left out. It is the only type that could produce a false `VERIFIED`, and the one whose extraction needs the most corpus to get right. It returns when there is a measured extractor to carry it.

**Verdicts**

| Verdict | Assigned when |
| --- | --- |
| `VERIFIED` | matching evidence exists, succeeded, and is fresh |
| `CONTRADICTED` | matching evidence exists and failed |
| `STALE` | matching successful evidence predates a later mutation of a referent |
| `UNSUPPORTED` | no matching evidence |
| `NOT_CHECKABLE` | the claim type carries no evidence contract |
| `UNKNOWN` | a pipeline component failed, so no verdict was computed |

**Consequence tier** — `LOW`, `REVIEW` or `HUMAN`, attached to paths, tools and commands by a configuration file, never inferred.

## Invariants

These hold in every version. A change that violates one is a different system, not a new release.

1. **I-1 Separation.** The component that assigns verdicts is never the component that wrote the report. The extractor receives the report text and the type vocabulary, and nothing else: no transcript, no tool results, no project files.
2. **I-2 Downgrade only.** Every ambiguity resolves to the weaker verdict. No judgment, by any component, can produce `VERIFIED`.
3. **I-3 Deterministic verification.** `VERIFIED` is assigned only by a table-driven join over the evidence log. The mapping from claim type and evidence state to verdict is data, not reasoning.
4. **I-4 Scope travels with the label.** Every `VERIFIED` carries the command, its outcome and its timestamp. There is no bare "verified".
5. **I-5 Weakest link.** Wherever the system reduces several verdicts to one, the result is the most severe among them. Severity runs `CONTRADICTED`, `UNKNOWN`, `STALE`, `UNSUPPORTED`, `NOT_CHECKABLE`, `VERIFIED`, from most severe to least. Every claim keeps its own verdict and is shown with it; no summary, count or label standing for several claims may read milder than the worst of them.
6. **I-6 Abstention is free.** Rewording a claim downward always satisfies the gate as far as that claim goes, and the system never requires that a check be run. A `HUMAN`-tier action is a separate condition, cleared only by acknowledgement.
7. **I-7 No vacuous pass.** A report that claims nothing does not pass while the evidence log shows consequential actions it left unmentioned.
8. **I-8 The consequence table is the user's.** Prevention is not achievable: any process the agent starts can write the file. So the requirement is detection. The configuration is hashed when the session opens and rechecked at the end of every turn, and a change makes the turn `UNKNOWN` and is reported.
9. **I-9 Failure is visible.** If any component fails, the turn is marked `UNKNOWN` and shown as such. A broken pipeline never reads as a clean turn.
10. **I-10 The report is not edited.** The system annotates and blocks. The agent's own words stay as written.

## Threat model

This system defends against an optimistic agent, not a dishonest one. The failure it exists to catch is a report written in good faith that the evidence does not support.

The evidence log is as writable as any other file in the project, and so is the configuration. A record appended through a shell command would read as evidence. That is accepted rather than defended against, for one reason: an agent set on deceiving the ledger has a cheaper route than forging a record, which is to run the check and ignore its result, or to run something narrower than the claim implies. No mechanism on this side of the boundary sees that.

So integrity machinery — hashes over the log, signatures, chains — buys nothing against an agent whose own source sits in the repository, and costs the simplicity that makes everything else auditable. Detection and visibility are the defence: what changed, when, and in front of the user.

**The rule this gives the implementer.** Never add a mechanism whose only justification is stopping deliberate forgery. Add mechanisms that make honest mistakes visible. The configuration hash of I-8 qualifies, because a change there is worth reporting whatever caused it, including the user's own edit mid-session.

## Requirements — evidence log

The log is the only source of truth for verdicts, so it is written by the harness and never by the model's narration.

- **R-1** The system records every tool call that mutates state or produces a check result.
- **R-2** Each record holds: tool name, command or arguments, an outcome of `ok`, `failed` or `unknown`, an end timestamp, and the files the call touched. A start time is recorded only when the harness supplies one, and nothing depends on it.
- **R-3** Records are append-only and written as they happen. Their order is their position in the file, which is the only ordering that survives: the harness stamps a hook after the call returns, so its timestamps cannot order a check against an edit that overlapped it.
- **R-4** The system records the modification time of every file the agent writes, and reads current mtimes again at join time. Neither source alone is sufficient, which is why R-18 tests both.
- **R-5** Each record is tagged with a session identifier and a turn identifier, and one field name never carries two meanings: the turn identifier is the harness's prompt id where it exists, and a per-session sequence number is a separate field where one is needed.
- **R-6** Evidence from earlier turns of the same session is admissible. Freshness is decided by the tests in R-18, not by turn boundaries.
- **R-7** The log stores command lines truncated at the first newline and at a declared length. It never stores file contents or environment variables.
- **R-44** A tool call the harness refuses, cancels, or never runs leaves no record. The system treats an absent record as an absent action, which is why every claim about it lands as `UNSUPPORTED` rather than as anything stronger.

## Requirements — claim extraction

Extraction is the only step that needs a model, so it is kept narrow, isolated and cheap.

- **R-8** At the end of every turn the system extracts the claims of the report.
- **R-9** Extraction runs in an isolated context. Its input is the report text plus the type vocabulary; it has no access to the transcript, the tool results or the repository.
- **R-10** Each extracted claim carries a verbatim span of the report, one type from the closed vocabulary, and the referents it names.
- **R-11** Anything ambiguous, or of a type the vocabulary does not cover, is emitted as `NOT_CHECKABLE`. The extractor never guesses upward.
- **R-12** Extraction returns schema-validated output. A parse or schema failure marks the turn `UNKNOWN`; it never yields an empty claim list.
- **R-13** Extraction runs on a fast model within a declared time budget. A timeout is a failure under R-12, not a pass.
- **R-45** The extraction route is pinned and declared: one model, one provider, one prompt. Since 18 October 2026 that is, provisionally, `mistralai/mistral-medium-3.1` through Mistral's zero-retention endpoint on OpenRouter, `mistral/zdr`, with `temperature` 0, and since 25 October its prompt is `extract-3`, the sentence contract with the typing rules of `docs/ANNOTATING.md`. It is provisional because no route measured clears the phase-1 threshold, stronger models screened with the same prompt included, and its answers vary from call to call, which the reasoning of September below refused; no route measured since repeats without losing turns (DECISIONS). From 21 September to 18 October the route was `deepseek/deepseek-v4.1-flash` through one OpenRouter provider, Morph, with reasoning switched off at the provider's chat template, until Morph's endpoint went down; it had replaced a model whose reasoning cost 49.8 seconds against a 15-second turn budget, and a second candidate was refused because its sampling could not be pinned and its answers varied run to run. Where a report is sent is configuration, never an environment variable named for a vendor. A recall figure measured on one route says nothing about another, so the prompt and its hash, the model, the address and the provider that answered travel with every claim and into the calibration log.
- **R-14** The extractor is replaceable. Its interface is report text in, claim list out, so it can be swapped or run twice with different models without touching the rest.

## Requirements — verdicts and coverage

The join runs without a model. Given a claim and the log, the verdict is a lookup.

- **R-15** For each checkable claim the system searches the log for evidence matching its type and referents.
- **R-16** Evidence whose outcome is `ok` and which passes both freshness tests yields `VERIFIED`, with command, outcome and timestamp attached.
- **R-17** Evidence whose outcome is `failed` yields `CONTRADICTED`, whatever the report says.
- **R-18** A check is stale when either test fails: a mutation record for a file it covers sits later in the log than the check, or a covered file's current mtime is later than the check's end timestamp. The first test catches what the agent did, the second what happened outside it. Both can only add `STALE`, never remove it.
- **R-19** No matching evidence yields `UNSUPPORTED`. Absence is never read as success.
- **R-20** Claims of type `judgment` and `intent` carry no evidence contract. They are always `NOT_CHECKABLE`: listed in the appendix, never joined.
- **R-21** The type-and-state to verdict mapping lives in one table in the codebase, readable in full on one screen.

**Coverage — what the report left out**

- **R-22** The system compares the consequential actions of the turn against the claims, and lists every one the report does not mention as `UNREPORTED`. Consequential means a file mutation, a check that failed, or a command at a tier above the default. A mutation whose outcome is `failed` changed nothing and is not consequential; one whose outcome is `unknown` may have changed something, so it is. Absence of knowledge counts against the report, never for it.
- **R-23** Which actions count as consequential comes from the consequence table, not from a heuristic.
- **R-24** `UNREPORTED` items appear in the appendix even when the gate does not block.

## Requirements — consequence tiers and the gate

The tier decides how much the gate demands from phase 2 onwards. In v1 it does one job: marking which actions count as consequential when the system checks what the report left out.

Claude Code's permission rules and hooks already stop consequential actions before they run, and that is where hard enforcement belongs. This system covers the other half: an action that ran, was allowed, and then went unmentioned.

| Tier | Applies to | Gate behaviour, phase 2 onwards |
| --- | --- | --- |
| `LOW` | paths and commands with cheap, reversible effects | appendix only, never blocks |
| `REVIEW` | anything unmatched, by default | appendix, blocks on `CONTRADICTED` |
| `HUMAN` | paths and commands the user names: migrations, deploys, deletions, anything with money | blocks until the user acknowledges, whatever the verdicts say |

- **R-25** Tiers are matched by path glob and command pattern, in a declared precedence order.
- **R-26** The default tier for unmatched actions is `REVIEW`, and the default is stated in the configuration file rather than left implicit.
- **R-27** The configuration file is hashed when the session opens and rechecked at the end of every turn; a change makes the turn `UNKNOWN` and is reported. A deny rule is installed as well, but it is a speed bump rather than a guarantee, since any process the agent starts can write the file.
- **R-28** The system emits a ledger appendix on every turn it is given the chance to. Turns the harness ends without a stop event produce none, and that limit is stated in the appendix's own documentation rather than papered over.
- **R-29** The appendix states how many checks the session has seen, since zero is worth seeing, and is otherwise one line when every claim is `VERIFIED` or `NOT_CHECKABLE` and nothing is unreported. It expands only when there is something to report, and `CONTRADICTED` stands at its head, apart from the rest.
- **R-30** In v1 the gate never blocks a turn. Blocking ships in phase 2 for `CONTRADICTED` and `UNKNOWN`, and in phase 3 for `STALE` and unacknowledged `HUMAN`-tier actions.
- **R-31** Once enabled, the gate never blocks on `UNSUPPORTED` for `judgment` or `intent` claims.
- **R-32** When it blocks, the gate states both acceptable resolutions — run the check, or reword the claim — and blocking is bounded: after a declared number of blocks in one turn it escalates to the user instead of looping.
- **R-33** The gate's decision is computed by harness-side code. No part of it is delegated to the agent.

## Requirements — calibration log, packaging, budget

The calibration log is what eventually lets a level above "heuristic" exist. It only needs to record, at first.

- **R-34** Every claim, with its type, verdict and scope, is appended to a persistent per-project log.
- **R-35** The log accepts a later outcome annotation, so a claim found false afterwards can be marked without rewriting history.
- **R-36** No hit rate, confidence or probability is computed or displayed until a sample size declared in advance is reached.
- **R-37** Recurring types of wrong claim are reported as candidates for new deterministic checks. That is how the ledger's coverage grows.

**Packaging and configuration**

- **R-38** The system ships as a Claude Code plugin, installable per project, with its hooks bundled.
- **R-39** It runs with no network access beyond the extractor's model call, and degrades visibly when that call is unavailable.
- **R-40** All state lives under the project directory in files a person can read and diff.
- **R-41** A single switch disables the gate while leaving the appendix and the logs running.

**Budget**

- **R-42** Evidence recording adds no perceptible latency to a tool call.
- **R-43** The end-of-turn pipeline completes within a declared budget, and exceeding it is an `UNKNOWN` turn rather than a silent skip. The budget is a wall clock over the whole pipeline, not a socket timeout: a model that answers slowly in many small pieces satisfies a per-read timeout indefinitely. Every timeout inside the pipeline is therefore shorter than the budget that contains it, and the configuration refuses a pair that is not.

## Acceptance criteria

Each row is a scenario the implementation must reproduce, as an automated test with no live model call in the loop. In v1 every row closes the turn and lands in the appendix; the last column states what will block from phase 2 onwards.

| # | Scenario | Expected verdict | Gate, phase 2 onwards |
| --- | --- | --- | --- |
| A-1 | Suite passes, then a referenced file is edited, then the report claims the tests pass | `STALE` | blocks from phase 3 |
| A-2 | Last suite run exited non-zero, report claims the tests pass | `CONTRADICTED` | blocks |
| A-3 | Report says the tests were not run | `NOT_CHECKABLE` | closes |
| A-4 | Report claims a file was updated and the log shows the edit, after the last check | `VERIFIED` | closes |
| A-5 | Report says only "done" while the log shows three files edited | three `UNREPORTED` | blocks if any is `HUMAN` tier |
| A-6 | Report asserts a design judgment | `NOT_CHECKABLE` | closes, listed as unverified |
| A-7 | Extractor times out or returns invalid output | `UNKNOWN` | blocks |
| A-8 | Agent attempts to edit the consequence table | — | refused by the harness, surfaced, in every phase |
| A-9 | Gate blocks twice in one turn on the same claim | — | escalates to the user, no third block |
| A-10 | Report claims a command was run that appears nowhere in the log | `UNSUPPORTED` | appendix, blocks only at `HUMAN` tier |
| A-11 | Every claim verified and nothing unreported | — | appendix collapses to one line |

**A-12 Extractor corpus.** A fixed set of at least 50 real reports with their claims annotated by a reference annotator: a model of another family than any route measured against it, given each report as the extractor gets it and the rules of `docs/ANNOTATING.md`, and nothing else. A few reports the user annotates by hand are its anchor, and the annotator's agreement with them is reported beside every recall figure. Who annotated each report, a model with its version or a person's initials, and when, travels with its annotation. Against this reference, recall is agreement with the annotator: a claim the annotator and the extractor both miss goes unseen. Recall on checkable claims is the headline number, and misses are listed individually rather than averaged away. The corpus is frozen before the first measurement, and any change to it is dated.

## Measurement and anti-metrics

The system is judged by its worst declared claim, not by how much it verifies.

**Tracked**

- False `VERIFIED` rate: claims labelled verified that later turn out false. Target zero, and every instance is investigated rather than counted.
- `CONTRADICTED` and `STALE` caught per hundred turns.
- Extractor recall on the frozen corpus, with the misses named, reported beside the share of turns that came back `UNKNOWN`. A measurement whose turns are a quarter unknown says as little as one with poor recall, and the two fail in opposite directions: recall misses what was claimed, an `UNKNOWN` turn never reaches the claim at all.
- Share of blocks resolved by rewording against those resolved by running the check. Both are successes; the ratio says what the agent was doing.
- End-of-turn overhead, and the rate of `UNKNOWN` turns.

**Never optimised**

- Share of claims verified. Raising it rewards making trivially verifiable claims.
- Number of claims per report. Raising it rewards padding; lowering it rewards silence.
- Block rate in either direction. A low rate can mean an honest agent or a blind gate, and the figure alone cannot tell them apart.

## Rollout phases

Each phase declares, before it runs, what result would stop it. Nothing blocks a turn until the instrument has been measured.

| Phase | Ships | Must hold before the next phase |
| --- | --- | --- |
| 0 | evidence log only, nothing else | the log captures every mutating call and every check, verified against a hand-written session |
| 1 | extraction, appendix and coverage of unreported actions, never blocking — this is v1 | extractor recall on the frozen corpus clears its declared threshold |
| 2 | blocking on `CONTRADICTED` and `UNKNOWN` | no false `VERIFIED` in the phase-1 sample |
| 3 | blocking on `STALE` and on unacknowledged `HUMAN`-tier actions | block rate and resolution mix are stable over a declared number of sessions |
| 4 | calibration figures per claim type | the calibration log reaches the sample size declared in phase 1 |

**Declared 20 September 2026, before the extractor existed.** Phase 1 clears when recall on checkable claims reaches 0.90 or better over a frozen corpus of at least 50 reports, spurious extractions stay at or below 0.10 of everything extracted, and no non-verbatim span is tolerated. A shortfall sends us to the misses, never to the number.

**Changed 23 October 2026, at the user's request.** The corpus is annotated by a model rather than by hand (A-12). The numbers do not move; against that reference they measure agreement with the annotator, reported beside the annotator's agreement with the reports annotated by hand.

Phase 0 is the equivalent of loading the correct answer into the engine before measuring anything else. If the log misses calls, every verdict above it is uninterpretable, and no amount of work on the extractor will show it.

## Open questions

Five are settled, and their answers are recorded in the sections they affect. The rest are decisions, not research, and each one changes the technical spec.

- [x] Does v1 block at all — decided on 19 September 2026: it does not. v1 ships as appendix only, and blocking arrives in phases 2 and 3.
- [x] Which claim types make the v1 vocabulary — decided: five. The three that join against the log, plus judgment and intent as labels without a verdict.
- [ ] Does the pipeline fail open or fail closed, given that a misconfigured hook is silently inert?
- [ ] Does `HUMAN` tier require an explicit acknowledgement per action, or one per turn?
- [x] Where does the evidence log live so that it survives compaction but is not committed by accident? Decided: one JSONL file per session under .claude/claim-ledger/, gitignored, ordered by position in the file.
- [x] How are files modified outside the agent, by the user editing in parallel, treated for staleness? Decided: mtimes are read at join time, so a change by any route counts.
- [x] One extractor call per turn, or two with different models so that disagreement itself downgrades? Decided: one per turn in v1, behind an interface that allows two.
- [x] What is the declared corpus size and recall threshold for phase 1, written before the first measurement — declared 20 September 2026, before the extractor existed, and recorded in § Rollout phases: recall 0.90 or better on checkable claims over a frozen corpus of at least 50 reports, spurious extractions at or below 0.10 of everything extracted, and no non-verbatim span tolerated. Checked here on 23 September 2026; the declaration itself does not move.
