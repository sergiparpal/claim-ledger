"""The extractor client: report text in, claim list out, and nothing else in.

The signature is the enforcement of I-1, not a convention: there is no
parameter for a session id, a transcript, an evidence log or a repository
path, so the component that types the claims cannot read the evidence they
will be checked against. Even the model and the timeout are passed in rather
than read from claim-ledger.toml here, because that file is a project file and
this function may not open one.

The timeout is a deadline, not a socket option. A socket timeout bounds one
read, so a model that answers slowly in many small pieces can run past it for
as long as it likes; the turn budget that the Stop handler will live inside
needs a wall clock. The call therefore runs in a worker thread that is
abandoned when the deadline passes, and the process it belongs to ends with
the turn.

One call per turn, no state, no retry beyond a single bounded one. Everything
that can go wrong ends the same way for the caller: an ExtractError or a
SchemaError, and a turn marked UNKNOWN (R-12, R-13). Nothing here repairs a
model's answer, reformats it, or unwraps it from a code fence. The assistant
turn is prefilled with the opening brace instead, so the model is already
inside the object and has no place to open a fence; the parser puts that brace
back before reading. The failure is removed rather than tolerated, and a fence
that still appears is a defect to see, not one to paper over.

The prompt lives in prompts/extract.md and carries a declared version. What
travels with each claim is that version plus a hash of the prompt's own text,
so a prompt edited without a version bump cannot quietly inherit a measurement
taken against the old one, together with the model, the address it was sent to
and the provider that answered.

Where a report is sent is configuration, never an environment variable: a
variable named for one vendor must not decide the destination of another's
report. The route is pinned to one provider with fallbacks off, because the
same model served by thirty of them is thirty measurements.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ledger import schema

if TYPE_CHECKING:  # the extractor may hold settings, never open the file they came from
    from ledger.config import Extractor as Settings

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "extract.md"
API_PATH = "/messages"
API_VERSION = "2023-06-01"
# This model reasons before it answers, and those tokens come out of the same
# ceiling, so the ceiling is generous and a reply cut off at it is refused.
MAX_TOKENS = 8192
RETRYABLE = frozenset({408, 429, 500, 502, 503, 504, 529})

# The assistant turn starts here, so the answer begins inside the object. No
# trailing whitespace: the API refuses a prefill that ends in one.
PREFILL = "{"


class ExtractError(Exception):
    """The model call did not produce an answer. The turn is UNKNOWN."""


@dataclass(frozen=True)
class Prompt:
    version: str
    text: str


@dataclass(frozen=True)
class Request:
    """What the client sends. No key: only the name of the variable holding one."""

    url: str
    body: Mapping[str, object]
    auth: str
    key_env: str
    prefilled: bool  # whether the answer will be a continuation or a whole object


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes = field(repr=False)


Transport = Callable[[Request, float], Response]


def extract(report_text: str, *, vocabulary: Sequence[str] = schema.CLAIM_TYPES,
            settings: "Settings", prompt: Prompt | None = None,
            transport: Transport | None = None) -> schema.Extraction:
    """The claims of one report, with the defects that reading it cost."""
    if len(report_text) > settings.max_report_chars:
        raise ExtractError(f"the report is {len(report_text)} characters, over the "
                           f"{settings.max_report_chars} this extractor accepts; "
                           f"it is not truncated")
    prompt = prompt or load_prompt()
    request = build_request(report_text, vocabulary=vocabulary, settings=settings,
                            prompt=prompt)
    response = _send(transport or https_transport, request, settings.timeout_s)
    payload, provider = _answer(response, prefilled=request.prefilled)
    provenance = schema.Provenance(prompt_version=prompt.version, model=settings.model,
                                   base_url=settings.base_url, provider=provider)
    return schema.validate(payload, report_text, provenance=provenance, vocabulary=vocabulary)


def load_prompt(path: Path = PROMPT_PATH) -> Prompt:
    """The prompt and the version that travels with every claim it produces."""
    text = path.read_text(encoding="utf-8")
    declared, _, body = text.partition("\n")
    if not declared.startswith("version: ") or not body.strip():
        raise ExtractError(f"{path} does not start with a version line and a prompt")
    digest = hashlib.sha256(body.strip().encode("utf-8")).hexdigest()[:8]
    return Prompt(f"{declared.removeprefix('version: ').strip()}+{digest}", body.strip())


def build_request(report_text: str, *, vocabulary: Sequence[str], settings: "Settings",
                  prompt: Prompt) -> Request:
    """The whole request: the report, the vocabulary, and the prompt that types them.

    Two shapes are supported and configuration picks one. `json_schema` asks
    the endpoint to enforce the answer's shape, which ends code fences and
    stray keys at the source. `prefill` is the fallback for a route that does
    not enforce schemas: the assistant turn is opened with a brace so the model
    continues an object instead of introducing one. A route that ignores a
    prefill returns a whole object, the brace put back would open a second, and
    the turn is UNKNOWN rather than quietly repaired.
    """
    types = "\n".join(f"- {name}" for name in vocabulary)
    body: dict[str, object] = {
        "model": settings.model, "max_tokens": MAX_TOKENS,
        # Whatever this route takes, and nothing the client assumes: a model
        # that refuses temperature leaves the router with no endpoint at all.
        **dict(settings.parameters),
        "system": f"{prompt.text}\n\nThe types, and nothing else:\n{types}",
        "messages": [{"role": "user", "content": report_text}],
        # One provider, no fallbacks, no training on the report, and it must
        # support everything sent or the call fails rather than degrading.
        "provider": {"order": [settings.provider], "allow_fallbacks": False,
                     "data_collection": "deny", "require_parameters": True},
    }
    prefilled = settings.answer_shape == "prefill"
    if prefilled:
        body["messages"] = [*body["messages"], {"role": "assistant", "content": PREFILL}]
    else:
        body["output_config"] = {"format": {"type": "json_schema",
                                            "schema": schema.json_schema(vocabulary)}}
    return Request(url=settings.base_url.rstrip("/") + API_PATH, body=body,
                   auth=settings.auth, key_env=settings.key_env, prefilled=prefilled)


def https_transport(request: Request, timeout_s: float) -> Response:
    """The only network the ledger does. The key is read here and never stored."""
    key = os.environ.get(request.key_env)
    if not key:
        raise ExtractError(f"{request.key_env} is not set")
    headers = {"content-type": "application/json", "anthropic-version": API_VERSION}
    headers["x-api-key" if request.auth == "x-api-key" else "authorization"] = (
        key if request.auth == "x-api-key" else f"Bearer {key}")
    posted = urllib.request.Request(request.url, method="POST", headers=headers,
                                    data=json.dumps(request.body).encode("utf-8"))
    try:
        with urllib.request.urlopen(posted, timeout=timeout_s) as reply:
            return Response(reply.status, reply.read())
    except urllib.error.HTTPError as e:
        return Response(e.code, e.read()[:2000])
    except (urllib.error.URLError, OSError) as e:
        raise ExtractError(f"the model call did not complete: {e}") from e


def _send(transport: Transport, request: Request, timeout_s: float) -> Response:
    """One call, and one retry if the first failed in a way that may not repeat."""
    deadline = time.monotonic() + timeout_s
    last: Exception | None = None
    for attempt in (1, 2):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            response = _within(transport, request, remaining)
        except ExtractError as e:
            last = e
        else:
            if response.status == 200:
                return response
            last = ExtractError(f"the model call returned HTTP {response.status}")
            if response.status not in RETRYABLE:
                raise last
        if attempt == 2:
            break
    raise last or ExtractError(f"no time left in the {timeout_s}s budget for the model call")


def _within(transport: Transport, request: Request, seconds: float) -> Response:
    """The transport, given a wall clock rather than a socket timeout."""
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        running = pool.submit(transport, request, seconds)
        try:
            return running.result(timeout=seconds)
        except concurrent.futures.TimeoutError as e:
            raise ExtractError(f"the model call passed its {seconds:.1f}s deadline") from e
    finally:
        # The call may still be in flight; it is abandoned rather than waited on,
        # and the hook process is about to end anyway.
        pool.shutdown(wait=False, cancel_futures=True)


def _answer(response: Response, *, prefilled: bool) -> tuple[object, str]:
    """The JSON object the model was asked for, and the provider that answered.

    A prefilled turn returns a continuation, so the brace goes back on. Under
    an enforced schema the text is a whole object and nothing is added. Reply
    blocks that are not text, such as the reasoning this model emits before it
    answers, are passed over rather than parsed.
    """
    try:
        envelope = json.loads(response.body)
    except ValueError as e:
        raise ExtractError(f"the reply is not JSON: {e}") from e
    blocks = envelope.get("content") if isinstance(envelope, dict) else None
    if not isinstance(blocks, list):
        raise ExtractError("the reply carries no content blocks")
    text = "".join(block.get("text", "") for block in blocks
                   if isinstance(block, dict) and block.get("type") == "text")
    if not text.strip():
        raise ExtractError("the reply carries no text")
    if envelope.get("stop_reason") == "max_tokens":
        raise schema.SchemaError(f"the answer was cut off at the {MAX_TOKENS} token "
                                 f"ceiling, so it is incomplete")
    try:
        return json.loads(PREFILL + text if prefilled else text), _provider(envelope)
    except ValueError as e:
        raise schema.SchemaError(f"the answer is not JSON: {e}") from e


def _provider(envelope: dict) -> str:
    """Which provider answered, as the reply names it.

    OpenRouter returns this as a top-level field and returns the quantization
    nowhere, so a claim's provenance can say who answered but not at what
    precision. That is the declared gap in an otherwise frozen route: the pin
    in [extractor] names a quantization only when the provider's own tag does,
    and the provider in use, morph, does not.
    """
    named = envelope.get("provider")
    return named if isinstance(named, str) and named else "unnamed"
