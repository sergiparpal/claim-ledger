# Provider measurements

**Measured 20–23 September and 17 October 2026. These go stale.** Provider
latency, routing and parameter support change without notice, and a number here
is one sample unless it says otherwise. Re-measure before trusting any row to
choose a pin.

This file exists for one job: when the pinned provider fails the way
`phala/fp8` did, this is the table that decides where the pin goes next.
Nothing here can be re-derived by reading the repository.

**Conditions, common to every row.** The same 442-character captured report
(the one embedded in `tests/test_extract.py` as `CAPTURED_REPORT`); prompt
`extract-1+74af1596`; `output_config` carrying the claim JSON schema;
`max_tokens` 8192; routing with `allow_fallbacks` false, `data_collection`
deny, `require_parameters` true. Times are wall clock measured at the client,
network included, from a single machine in one location.

## deepseek/deepseek-v4.1-flash — the route in use

Thinking-switch test, 21 September 2026, one call per provider, all sent
`extra_body.chat_template_kwargs.enable_thinking = false` and `temperature` 0.

| Provider | Quantization | Honours the switch | Thinking tokens | Wall |
| --- | --- | --- | --- | --- |
| `morph` | undeclared | **yes** | 0 | 8.3s |
| `together` | undeclared | no | 2,376 | 7.4s |
| `fireworks` | undeclared | no | 1,996 | 25.5s |
| `deepinfra/fp8` | fp8 | no | 2,526 | 35.5s |
| `atlas-cloud/fp8` | fp8 | no | 2,902 | 44.9s |

Both providers that declare fp8 ignore the switch. On `deepinfra/fp8`, the
same request with thinking left on took 29.4s at 2,420 thinking tokens, and the
top-level `chat_template_kwargs` shape (rather than under `extra_body`) took
66.9s at 5,155 — accepted and ignored in both shapes.

`morph` over time, against the 12s deadline:

| When | Runs | Wall | Result |
| --- | --- | --- | --- |
| 21 Sep, five consecutive | 5 | 6.1, 8.6, 8.1, 7.9, 6.1s | 3 claims, 0 defects each, identical; $0.000085 a report |
| 21 Sep, one CLI run | 1 | over 12s | **missed the deadline** |
| 23 Sep | 8 | 2.9–7.6s, median 3.8s | none missed, all identical |
| 17 Oct, every tenth call of the corpus run below | 11 | 0.61–1.32s, median 0.76s | **three distinct answers**: two different sets of 3 claims (nine runs and one), and once **no claims at all**; none identical to the recording |
| 17 Oct, three more, read | 3 | 0.4–0.9s | one with no claims; two with the recording's three claims, the intent now carrying `git add`, `commit` and `push` as referents, which the sentence does not name; one of the two without the spans' final full stops |

In September, thirteen of fourteen runs inside the deadline, every answer the
same. On 17 October all fourteen were inside it, with at least three distinct
answers among them. 18 of the 22 providers serving this model are untested.

### The distiller corpus under a long deadline — 17 October 2026

Conditions differ from the rows above. The request the Stop hook sends, built by
the same code (the installed copy's `src/ledger` is identical to the
repository's) from distiller's `claim-ledger.toml` and sent with the hook's key:
the same route, prompt `extract-1+74af1596`, `temperature` 0, thinking off. The
deadline was a 150s wall clock instead of 12s, with no retry. One call at a
time, a second apart, from 11:51 to 11:58 UTC: the 48 reports distiller had
captured under `max_report_chars`, 210 to 12,488 characters, each twice in
shuffled order, with the fixed report above every tenth call. 107 calls, all
answered by Morph, all `end_turn`, none with a reasoning token; $0.037 in all.
Only timings and a digest of each answer were kept, so that nobody read the
claims of reports still to be annotated.

| Wall, 96 calls on real reports | p50 | p75 | p90 | p95 | p99 | max |
| --- | --- | --- | --- | --- | --- | --- |
| seconds | 2.4 | 4.0 | 6.6 | 10.0 | 12.7 | 14.1 |

93 of the 96 inside 12s, all 96 inside 15s. The time follows the size of the
answer, about 0.65s plus 4.7ms per output token (r = 0.95, some 211 tokens a
second), and hardly the size of the report (r = 0.19). Output ran from 6 to
2,963 tokens a call, median 377; the three calls past 12s carried 1,826 to 2,963
of them. The 11 reports whose turns had passed the deadline in the hook answered
in 0.5 to 9.6s. Seven minutes is one window, and a fast one: the turns the hook
answered from 10 October took a median of 6.9s.

The answers were not stable. Of the 48 reports asked twice, 8 got the same
answer both times; the claim count differed in 31, by a factor of two or more in
13. 21 of the 107 answers were empty lists, among them four reports whose other
run found 18, 26, 33 and 45 claims. 17 answers carried at least one span that is
not in the report: 41 defects against 1,093 claims kept.

## z-ai/glm-5.3-flash — replaced 21 September 2026

Measured 20 September, `temperature` 0, thinking on (it cannot be switched
off from this endpoint: `reasoning: {"enabled": false}` was accepted and
ignored).

| Provider | Quantization | Wall | Notes |
| --- | --- | --- | --- |
| `baseten/fp8` | fp8 | 4.4s | the pin when the model was replaced; rate-limited twice (429) during earlier probes |
| `deepinfra/fp4` | fp4 | 6.2s, 11.8s | fp4: the wrong quantization for a measurement |
| `phala/fp8` | fp8 | 20.6s, then 49.8s | the recorded run: 5,041 thinking tokens, $0.0026. Later returned **HTTP 400 twice** to a body that had worked |
| `near-ai/fp8` | fp8 | 61.4s | |
| `sail-research/fp8` | fp8 | — | HTTP 429 |
| `novita/fp8` | fp8 | — | HTTP 404: cannot take the parameters `require_parameters` demands |

## openai/gpt-5.6-luna — refused 21 September 2026

Provider `openai`, quantization undeclared. Rejected because sampling cannot be
pinned, not because of speed.

| Condition | Result |
| --- | --- |
| `temperature` 0 | **HTTP 404 from routing**: no endpoint accepts it, so `require_parameters` leaves nothing to route to |
| `reasoning: {"effort": "none"}` | accepted, 5.2s, still 230 thinking tokens in a `redacted_thinking` block |
| no `reasoning` field | 7.7s, 423 thinking tokens |
| seven extraction runs | 5.9–8.7s, ~$0.0008 a report, **three distinct answers**, twice with a fourth claim |

Bedrock serves this model without `response_format` or `structured_outputs`,
so it cannot carry the schema at all. Azure was not tested.
