"""Extractor answers replayed at the HTTP boundary.

The double stands in for the transport, not for extract(), so a test that uses
it still runs the real request building, the real envelope parsing, the real
schema validation and the real defect counting. Only the network is missing.

The client prefills the assistant turn with an opening brace, so the text a
model returns is a continuation: it starts inside the object. Every answer
built here is one, which is what continuation() is for.

Each fixtures/extractor/openrouter-*.json is a real answer, named for the
model that gave it. recorded("openrouter-deepseek-v4.1-flash") is the route
the ledger uses: deepseek/deepseek-v4.1-flash through OpenRouter's Messages
endpoint, pinned to morph, thinking off, the answer's shape enforced by a JSON
schema. openrouter-glm-5.3-flash.json is the route it replaced, kept because
that one reasons before it answers and is the only recording here that carries
a thinking block.

fixtures/extractor/cli-no-prefill-*.json are the exception. They hold the text
claude-haiku-4-5 really returned for the one report captured on 20 September
2026, reached through the Claude Code CLI because this machine has no API key.
The CLI cannot prefill an assistant turn, so those answers are whole objects
from a route the client no longer uses. They are kept as recordings rather than
edited into the shape we now send, and the tests assert what the client does
with them today: refuses them.
"""

import json
from pathlib import Path

from ledger import extract

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "extractor"


def continuation(whole_object_json):
    """The text a prefilled turn returns: everything after the opening brace."""
    text = whole_object_json.lstrip()
    if not text.startswith("{"):
        raise AssertionError(f"a continuation is made from a whole object, not {text[:20]!r}")
    return text[1:]


def recorded(name):
    """An answer a model really gave with the prefill in place."""
    return extract.Response(200, (FIXTURES / f"{name}.json").read_bytes())


def recorded_without_prefill(name):
    """A recording from before the assistant turn was prefilled.

    A whole JSON object, not a continuation, so the client refuses it. That is
    the point of keeping it: the route changed, the recording did not.
    """
    return extract.Response(200, (FIXTURES / f"{name}.json").read_bytes())


def reply(answer_text, *, status=200, thinking=False):
    """A handwritten answer: the model's turn, as the route in use returns it.

    Under an enforced schema that is a whole object; behind a prefill it is a
    continuation. thinking=True puts a reasoning block in front of the text,
    which is what this model really sends.
    """
    envelope = {"id": "msg_double", "type": "message", "role": "assistant",
                "model": "z-ai/glm-5.3-flash", "provider": "BaseTen",
                "content": [{"type": "text", "text": answer_text}],
                "stop_reason": "end_turn", "usage": {"input_tokens": 0, "output_tokens": 0}}
    if thinking:
        envelope["content"] = [{"type": "thinking", "thinking": "weighing the sentences",
                                "signature": ""}, *envelope["content"]]
    return extract.Response(status, json.dumps(envelope).encode())


def raw(body, *, status=200):
    """An answer that is not a Messages envelope at all."""
    return extract.Response(status, body if isinstance(body, bytes) else body.encode())


class Transport:
    """Replays answers in order, and remembers every request it was given."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.requests = []
        self.timeouts = []

    def __call__(self, request, timeout_s):
        self.requests.append(request)
        self.timeouts.append(timeout_s)
        if not self.answers:
            raise AssertionError("the double was asked for more answers than it holds")
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer
