# Provider measurements

**Measured 20–23 September 2026. These go stale.** Provider latency, routing
and parameter support change without notice, and a number here is one sample
unless it says otherwise. Re-measure before trusting any row to choose a pin.

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

Thirteen of fourteen runs inside the deadline. 18 of the 22 providers serving
this model are untested.

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
