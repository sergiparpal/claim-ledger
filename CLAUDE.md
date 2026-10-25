# claim-ledger

A Claude Code plugin that gives every factual claim in an agent's end-of-turn
report a verdict taken from the harness's own execution record.

## Read first

- `docs/REQUIREMENTS.md`, then `docs/SPEC.md`.
- `docs/DECISIONS.md` for reasons that are in neither, and for what was
  already tried and rejected.
- If the two disagree, the requirements win. Tell the user about the
  disagreement; do not resolve it yourself.
- Build order: `docs/SPEC.md` § Build order. Before changing the pipeline,
  read `docs/SPEC.md` § Traps.

## Commands

- Tests: `python3 tools/run_suite.py`, from the repo root. It runs
  `python3 -m unittest discover` on every version declared in
  `tools/run_suite.py` (3.11, 3.12, 3.13, 3.14), and a declared version that
  is not installed is a named failure, not a shorter run. Nothing to install
  beyond those interpreters; uv is only needed for one that is not on PATH.
- Pre-commit hook: run `git config core.hooksPath .githooks` once per clone.
  The hook runs `tools/run_suite.py`; a failing suite, or a declared version
  that is missing, blocks the commit.
- CI: `.github/workflows/ci.yml` runs `tools/run_suite.py` on the declared set,
  but only where something is pushed, and this repository has no remote. The
  pre-commit hook is what gates.

## Constraints

- Python 3.11+, standard library only, no dependencies.
- No test makes a network call or a model call.
- Neither the tests nor the hooks write to `.claude/claim-ledger/`.
- `claim-ledger.toml` belongs to the user (I-8). `src/ledger/config.py` never
  falls back to defaults: a missing or invalid file raises `ConfigError` naming
  the offending key.

## Invariants

Copied verbatim from `docs/REQUIREMENTS.md` § Invariants.

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

## FROZEN

A FROZEN file is never edited without asking the user first. This file is one:
it holds the invariants.

| Frozen | File | Status |
| --- | --- | --- |
| Invariants I-1 to I-10 | `docs/REQUIREMENTS.md` § Invariants, and § Invariants above | frozen |
| Claim-type vocabulary | `src/ledger/schema.py` | frozen (written at build step 6) |
| Verdict table | `src/ledger/join.py` | frozen (written at build step 7) |
| Extractor route and prompt | `claim-ledger.toml` § `[extractor]`, `src/ledger/prompts/extract.md` | route `mistral-medium-3.1` on `mistral/zdr`, provisional, in the sample since 25 October 2026 at the user's leave; prompt `extract-3`, the sentence contract with ANNOTATING's rules, since 25 October 2026 at the user's leave, after `extract-2`, the sentence contract alone, from 18 October, the day the route pinned on 23 September went down; the next route is to be chosen by recall on the annotated corpus: the corpus is measured against both |
| Phase-1 recall threshold | `docs/REQUIREMENTS.md` § Rollout phases | frozen: declared before the extractor existed, and does not move; since 23 October 2026 it is measured against a model's annotations, anchored by a few reports annotated by hand (A-12) |
