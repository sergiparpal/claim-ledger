# Provider measurements

**Measured 20–23 September and 17–18 October 2026. These go stale.** Provider
latency, routing and parameter support change without notice, and a number here
is one sample unless it says otherwise. Re-measure before trusting any row to
choose a pin; `tools/measure_route.py` repeats the runs of 17 October.

This file exists for one job: when the pinned provider fails the way
`phala/fp8` did, this is the table that decides where the pin goes next.
Nothing here can be re-derived by reading the repository.

**Conditions, common to every row.** The same 442-character captured report
(the one embedded in `tests/test_extract.py` as `CAPTURED_REPORT`); prompt
`extract-1+74af1596`; `output_config` carrying the claim JSON schema;
`max_tokens` 8192; routing with `allow_fallbacks` false, `data_collection`
deny, `require_parameters` true. Times are wall clock measured at the client,
network included, from a single machine in one location.

## deepseek/deepseek-v4.1-flash — the route in use, its pin down since 18 October 2026

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
| 17 Oct, every tenth call of the slow-hour run below | 11 | 0.55–2.61s, median 1.31s | the same three answers as the corpus run, five, three and three times; **no claims at all** in three |
| 18 Oct, 12:28 UTC | 8 | — | **HTTP 404 from routing**: "Filter Disabled Endpoints removed morph/fp8", under both keys; a call at 20:25 UTC the evening before had answered |

In September, thirteen of fourteen runs inside the deadline, every answer the
same. On 17 October all fourteen were inside it, with at least three distinct
answers among them, and so were the eleven of the slow hour, with the same
three. On 18 October the endpoint was disabled, now tagged `morph/fp8` where its
quantization had been undeclared, and every other endpoint of the model was
tried (below).

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

### The same corpus at a slow hour — 17 October 2026

The run above caught a fast hour, and the hook's own turns had been slower, so a
watcher waited for a slow one. From 12:22 UTC it sent a probe every five
minutes: the same request for one distiller report of 1,000 characters, whose
answers ran to 355–534 output tokens. Each call was timed in stages, DNS, TCP,
TLS, first byte and whole body, through `http.client` with urllib's headers,
since urllib times none of them. Two probes in a row at twice the fast run's
prediction, or one past 12s, would start the run. Four probes went past twice,
never two in a row, and at 16:57 one took 13.05s, 4.9 times. The run that
followed, 16:57 to 17:10 UTC, repeated the one above call for call: the same 48
reports in the same order, the fixed report every tenth call, the 150s deadline.
All 107 calls answered by Morph, `end_turn`, no reasoning token; $0.050 with the
57 probes.

| Wall, 96 calls on real reports | p50 | p75 | p90 | p95 | p99 | max |
| --- | --- | --- | --- | --- | --- | --- |
| fast run above, seconds | 2.4 | 4.0 | 6.6 | 10.0 | 12.7 | 14.1 |
| slow hour, seconds | 4.7 | 10.4 | 17.1 | 21.8 | 33.2 | 38.6 |

Inside 12s, 78 of the 96 (81%); inside 15s, 89%; 20s, 93%; 25s, 96%; 30s, 98%;
all inside 45s. About 1.6s plus 10.4ms per output token (r = 0.86), against
0.65s plus 4.7ms in the fast run. Connecting took a median of 43ms and the first
byte came at a median of 0.69s, against 0.84s in the probes before the episode:
the time went after the first byte, where the provider delivered a median of 89
tokens a second against 184 before it, and as few as 27. Whether that is a queue
at the provider or slower decoding cannot be told from a call that is not
streamed. The 11 reports whose turns had passed the deadline in the hook took
0.6 to 17.4s; 3 of their 22 calls went past 12s.

The answers varied as they had at the fast hour. 6 of the 48 reports got the
same answer twice; across the day's four runs, 2 of the 48 got one answer every
time, and the median was three distinct answers per report. 23 of the 107
answers were empty lists. 12 answers carried a span that is not in the report:
32 defects against 1,121 claims kept. The probe report never came back empty,
and gave 25 distinct answers in its 57 runs, the most common of them 11 times.

### Every other endpoint of the model — 18 October 2026

The route's request with only the pinned provider changed, fallbacks still off,
and a 60s deadline, from 12:33 to 12:40 UTC; $0.23 in all. The fixed report
above, and in the second stage a synthetic Spanish report written for the run in
distiller's style, with bold labels, guillemets, code and a negation. No corpus
report was sent to a new provider.

One call each, to the 33 endpoints besides Morph's:

| Result | Endpoints |
| --- | --- |
| answered, and **reasoned** although thinking is off | 25, at 304 (`coreweave/fp8`, 2.0s) to 5,950 thinking tokens (`crusoe/fp8`, 27s); the slowest took 49.4s (`deepinfra/fp8/flex`) |
| HTTP 404: the route's parameters refused | 6: `alibaba`, `gmicloud/fp8`, `novita/fp8`, `phala`, `siliconflow/fp8`, `streamlake/fp8` |
| HTTP 429 | `baseten/us` |
| past 60s | `open-inference/fp4` |

Then five calls per report to the six fastest of those that reason, fp4 left
out:

| Endpoint | Answered, fixed / synthetic | Distinct answers | Wall, median and max | Notes |
| --- | --- | --- | --- | --- |
| `nebius/fp8` | 5 / 5 | 5 / 5 | 7.8s, 13.5s | |
| `fireworks` | 5 / 5 | 4 / 4 | 19.2s, 40.8s | |
| `venice/fp8` | 5 / 4 | 5 / 4 | 29.5s, 60s | one past 60s |
| `baidu/fp8` | 5 / 2 | 3 / 2 | 16.4s, 28.8s | three answers lost: the reasoning used all 8,192 tokens |
| `relace` | 3 / 4 | 2 / 4 | 30.6s, 60s | two past 60s, one 429 |
| `coreweave/fp8` | 0 / 0 | — | — | all ten calls 429 |

None answered the same way twice as a rule, so none could carry the route even
with reasoning allowed.

## Other models — 18 October 2026

Every model in OpenRouter's catalogue that takes a JSON schema and a
temperature, does not reason, answers text, holds 32k tokens and costs at most
$1 a million tokens in and $4 out, with no free or batch variant and no audio,
image, code-apply or role-play model: 48. Each was pinned to the endpoint that
takes both parameters with the best uptime, not fp4, fallbacks off; the route's
prompt, `temperature` 0 and nothing else, since the thinking switch is
DeepSeek's template. The two reports of the section above. From 13:23 to 13:26
UTC, $0.06.

One call each: 46 answered and two returned 429; three found no claim in the
fixed report (`inference-net/schematron-v2-turbo`,
`mistralai/ministral-3b-2512`, `qwen/qwen3-30b-a3b-instruct-2507`), and
`meta-llama/llama-3.3-70b-instruct` took 15.8s. The twenty fastest then had
five calls per report. The best:

| Model, endpoint | Distinct answers, fixed / synthetic | Spans dropped in 10 answers | Claims, fixed / synthetic | Wall median | $ a call |
| --- | --- | --- | --- | --- | --- |
| `openai/gpt-4.1-nano`, `azure` | 1 / 1 | 0 | 1 / 6 | 1.7s | 0.00013 |
| `google/gemma-3-4b-it`, `parasail/bf16` | 1 / 1 | 5 | 1 / 6 | 1.5s | 0.00002 |
| `meta-llama/llama-3.2-3b-instruct`, `parasail/bf16` | 1 / 1 | 15 | 1 / 3 | 1.3s | 0.00008 |
| `inference-net/schematron-v2-small`, `inference-net/bf16` | 1 / 1 | 15 | 1 / 2 | 0.8s | 0.00007 |
| `openai/gpt-4.1-mini`, `azure` | 1 / 2 | 0 | 2 / 7 | 2.5s | 0.00057 |
| `qwen/qwen3-vl-8b-instruct`, `parasail/bf16` | 1 / 2 | 0 | 3 / 9–10 | 8.0s | 0.00031 |
| `qwen/qwen3-coder-next`, `parasail/bf16` | 1 / 2 | 0 | 1 / 5–8 | 2.9s | 0.00017 |

The other thirteen gave two to five distinct answers to the synthetic report.
Read whole, nano's answer to it missed both suite outputs and gave the `make`
line no referents; mini's took them all but typed the commit as a file change.

### gpt-4.1-nano and gpt-4.1-mini on the distiller corpus — 18 October 2026

The runs of "The distiller corpus under a long deadline" above, call for call,
with the model and the pinned provider changed and `temperature` 0 the only
parameter; the user agreed to the corpus going to Azure. From 13:29 to 13:35
UTC, the two side by side, $0.09.

| | DeepSeek via Morph, 17 Oct | `gpt-4.1-nano` | `gpt-4.1-mini` |
| --- | --- | --- | --- |
| Reports answered the same way in both passes | 8 of 48 | 31 of 48 | 26 of 48 |
| Empty answers | 21 of 107 | 38 of 107 | 11 of 107 |
| Spans dropped, against claims kept | 41 against 1,093 | 43 against 226 | 65 against 396 |
| Wall: median, p95, max | 2.4, 10.0, 14.1s | 1.6, 2.7, 11.8s | 1.7, 5.2, 9.6s |
| $ a call | 0.00034 | 0.00015 | 0.00067 |

The fixed report: nano gave one answer in its 11 calls, mini two. No reasoning
token in either run.

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
