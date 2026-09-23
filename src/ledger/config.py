"""Load and validate claim-ledger.toml.

The file is the user's consequence table (I-8) and the only source of what the
ledger matches on: which exact invocations are checks, which files each check
covers, and which actions are consequential. Nothing is inferred from the
repository and nothing falls back to a default. Every key of the spec's sample
is required, no other key is accepted, and any problem raises ConfigError
naming the offending key (docs/SPEC.md, Configuration).

A [checks.scope] entry holding whitespace is refused, naming the key: it is
almost always an invocation written into the file-glob table, and a scope that
matches no path leaves the session with no checks and says nothing.

Checks are exact invocations, never patterns. A command is a check only when,
with its surrounding whitespace stripped, it equals an invocation listed in
[checks]; nothing else is normalised, so 'pytest --version' is not 'pytest'.
An invocation containing a shell operator is refused, since a command with one
is never a check: 'pytest || true' exits 0 whatever pytest did.

Globs ([checks.scope], and path entries in [tiers]) match the whole
project-relative path, case-sensitively. '*' and '?' stay inside one segment,
'[...]' is a character class, and '**' as a whole segment spans directories:
'docs/**' is everything under docs/, '**/*.md' is every .md file at any depth,
and '*.md' only those at the root. A glob that cannot mean what it appears to
(unclosed '[', '**' inside a segment, braces, backslashes, a leading '/' or
'~', '.' or '..' segments, empty segments) is rejected, never read literally.

Bash(...) entries in [tiers] use Claude Code's Bash permission-rule wildcards:
'*' matches any text including spaces and the pattern must match the whole
command; a trailing ' *' that is the only '*' also matches the bare command; a
trailing ':*' means ' *'. Where they meet compound commands, each reading errs
toward reporting more (I-2):

- A HUMAN entry matches the command, any segment of it split at shell
  operators, or either of those read from any word on, the way a deny rule
  sees past wrappers: 'cd app && timeout 60 git push' meets 'Bash(git push*)'.
- LOW applies only when a LOW entry covers every part of the action, as
  written: each path, or each segment of the command.

Tier precedence: HUMAN beats LOW beats the default, and within a tier the
first entry in file order that matches is the one reported.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

CONFIG_FILENAME = "claim-ledger.toml"

HUMAN, REVIEW, LOW = "HUMAN", "REVIEW", "LOW"

# R-26: "The default tier for unmatched actions is REVIEW, and the default is
# stated in the configuration file". The file must say it; this only checks it.
REQUIRED_DEFAULT_TIER = REVIEW

_TOP_LEVEL = ("checks", "tiers", "extractor", "budget", "log", "gate", "corpus")
_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")
_TOOL_RULE = re.compile(r"([A-Za-z][A-Za-z0-9_]*)\((.*)\)", re.DOTALL)
_BARE_TOOL_NAMES = frozenset({"Bash", "Edit", "Write", "NotebookEdit"})
# Anything that makes a command more than one simple command.
_NOT_SIMPLE = re.compile(r"[;&|<>()`\n\r]")
# Claude Code's command separators, plus the openings of subshells and
# substitutions. Splitting too often only adds parts to test.
_SEGMENT_SPLIT = re.compile(r"&&|\|\||\|&|\$\(|[;|&\n\r()`]")
_WORD_START = re.compile(r"(?<!\S)\S")


class ConfigError(Exception):
    """claim-ledger.toml is missing or invalid. Callers stop; they never default."""

    def __init__(self, path: Path, key: str | None, problem: str) -> None:
        self.path = path
        self.key = key
        self.problem = problem
        where = f"{path}: {key}" if key else str(path)
        super().__init__(f"{where}: {problem}")


@dataclass(frozen=True)
class Glob:
    """A project-relative path glob, as written in the file."""

    text: str
    regex: re.Pattern[str] = field(repr=False, compare=False)

    def matches(self, path: str) -> bool:
        _require_relative(path)
        return self.regex.fullmatch(path) is not None


@dataclass(frozen=True)
class CommandPattern:
    """A Bash command pattern in permission-rule syntax, as written."""

    text: str
    regex: re.Pattern[str] = field(repr=False, compare=False)

    def matches(self, command: str) -> bool:
        return self.regex.fullmatch(command) is not None


@dataclass(frozen=True)
class Check:
    check_id: str
    invocations: tuple[str, ...]  # exact command lines, in file order


@dataclass(frozen=True)
class TierRule:
    """One [tiers] entry: a path glob or a Bash(...) command pattern."""

    text: str
    glob: Glob | None = None
    command: CommandPattern | None = None


@dataclass(frozen=True)
class TierMatch:
    tier: str
    rule: str | None  # the entry that decided the tier; None when the default did


AUTH_HEADERS = ("x-api-key", "bearer")
ANSWER_SHAPES = ("json_schema", "prefill")


#: The client sets these itself; a route may not overwrite them from the config.
RESERVED_PARAMETERS = ("model", "max_tokens", "system", "messages", "provider",
                       "output_config")


@dataclass(frozen=True)
class Extractor:
    base_url: str
    auth: str        # which header carries the key: see AUTH_HEADERS
    key_env: str     # the variable the key is read from, never the key itself
    model: str
    provider: str    # exactly one, routed with fallbacks off; its suffix is the quantization
    answer_shape: str
    parameters: Mapping[str, object]  # what this route takes, sent as written
    timeout_s: float
    max_report_chars: int


@dataclass(frozen=True)
class Budget:
    turn_timeout_s: float


@dataclass(frozen=True)
class Log:
    max_command_chars: int


@dataclass(frozen=True)
class Gate:
    enabled: bool


@dataclass(frozen=True)
class Corpus:
    capture: bool


@dataclass(frozen=True)
class Config:
    path: Path
    checks: tuple[Check, ...]
    invocations: Mapping[str, str]  # exact invocation -> check id
    aliases: Mapping[str, str]      # lowercased words a report uses -> check id
    scopes: Mapping[str, tuple[Glob, ...]]
    human: tuple[TierRule, ...]
    low: tuple[TierRule, ...]
    default_tier: str
    extractor: Extractor
    budget: Budget
    log: Log
    gate: Gate
    corpus: Corpus

    def check_for(self, command: str) -> str | None:
        """Check id whose [checks] list holds this exact invocation, or None.

        Only surrounding whitespace is stripped. The loader refuses invocations
        with shell operators, so a compound command can never match.
        """
        return self.invocations.get(command.strip())

    def tier_for(
        self, tool: str, *, command: str | None = None, paths: Iterable[str] = ()
    ) -> TierMatch:
        """Consequence tier of one tool call.

        paths are the files the call touched, normalised project-relative;
        command is the Bash command line. Bash(...) entries apply only when
        tool is "Bash", globs only to paths.
        """
        paths = tuple(paths)
        for path in paths:
            _require_relative(path)
        segments = _segments(command) if tool == "Bash" and command else []

        human_texts: dict[str, None] = {}
        if tool == "Bash" and command:
            for part in (command, *segments):
                human_texts.update(dict.fromkeys(_from_each_word(part)))
        for rule in self.human:
            if rule.glob is not None and any(rule.glob.matches(p) for p in paths):
                return TierMatch(HUMAN, rule.text)
            if rule.command is not None and any(map(rule.command.matches, human_texts)):
                return TierMatch(HUMAN, rule.text)

        parts = [(p, None) for p in paths] + [(None, s) for s in segments]
        if parts and all(any(_covers(r, part) for r in self.low) for part in parts):
            first = next(r for r in self.low if any(_covers(r, part) for part in parts))
            return TierMatch(LOW, first.text)

        return TierMatch(self.default_tier, None)


def fingerprint(path: str | Path) -> str:
    """A hash of the configuration exactly as it sits on disk (R-27, I-8).

    Over the bytes, not over the parsed Config: a change the loader happens to
    read the same way is still the user's table changing under the session, and
    I-8 asks for detection of the change, not of its effect. Prevention is not
    available — any process the agent starts can write this file — so what the
    hash buys is that a change is reported, whoever made it, including the
    user's own edit mid-session.
    """
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path: str | Path) -> Config:
    """Read and validate the config at path. Raises ConfigError on any problem."""
    path = Path(path)
    try:
        with path.open("rb") as f:
            doc = tomllib.load(f)
    except FileNotFoundError as e:
        raise ConfigError(path, None, "file not found") from e
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(path, None, f"not valid TOML: {e}") from e
    except UnicodeDecodeError as e:
        raise ConfigError(path, None, f"not valid UTF-8: {e}") from e
    except OSError as e:
        raise ConfigError(path, None, f"cannot be read: {e.strerror or e}") from e
    return _validate(doc, path)


def _validate(doc: dict, path: Path) -> Config:
    for name in doc:
        if name not in _TOP_LEVEL:
            raise ConfigError(path, _key(name), "unknown key")

    checks, invocations, aliases, scopes = _checks(doc, path)

    tiers = _table(doc, "tiers", ("HUMAN", "LOW", "default"), path,
                   hints={REVIEW: "REVIEW is the default tier and takes no entries"})
    human = _tier_rules(tiers["HUMAN"], path, "HUMAN")
    low = _tier_rules(tiers["LOW"], path, "LOW")
    if tiers["default"] != REQUIRED_DEFAULT_TIER:
        raise ConfigError(path, "tiers.default",
                          f'must be "{REQUIRED_DEFAULT_TIER}" (R-26), got {tiers["default"]!r}')

    ext = _table(doc, "extractor", ("base_url", "auth", "key_env", "model", "provider",
                                    "answer_shape", "parameters", "timeout_s",
                                    "max_report_chars"), path)
    base_url = _word(ext["base_url"], path, "extractor.base_url")
    if not base_url.startswith("https://"):
        raise ConfigError(path, "extractor.base_url",
                          "must be an https:// address: a report leaves the machine here")
    key_env = _word(ext["key_env"], path, "extractor.key_env")
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key_env):
        raise ConfigError(path, "extractor.key_env",
                          "must be the name of an environment variable, not a key")
    extractor = Extractor(
        base_url=base_url.rstrip("/"),
        auth=_one_of(ext["auth"], AUTH_HEADERS, path, "extractor.auth"),
        key_env=key_env,
        model=_word(ext["model"], path, "extractor.model"),
        provider=_word(ext["provider"], path, "extractor.provider"),
        answer_shape=_one_of(ext["answer_shape"], ANSWER_SHAPES, path,
                             "extractor.answer_shape"),
        parameters=_parameters(ext["parameters"], path),
        timeout_s=_seconds(ext["timeout_s"], path, "extractor.timeout_s"),
        max_report_chars=_positive_int(ext["max_report_chars"], path,
                                       "extractor.max_report_chars"),
    )

    budget_table = _table(doc, "budget", ("turn_timeout_s",), path)
    budget = Budget(_seconds(budget_table["turn_timeout_s"], path, "budget.turn_timeout_s"))
    # R-43 reads "shorter", not "no longer": a timeout equal to the budget
    # containing it leaves no time to render the UNKNOWN that overrunning it is
    # supposed to produce, which is the one outcome the budget exists to make
    # visible. Equality is refused for that reason, not for tidiness.
    if extractor.timeout_s >= budget.turn_timeout_s:
        raise ConfigError(path, "extractor.timeout_s",
                          f"is {extractor.timeout_s}s, which is not shorter than the "
                          f"{budget.turn_timeout_s}s turn budget it has to fit inside (R-43)")

    log_table = _table(doc, "log", ("max_command_chars",), path)
    log = Log(_positive_int(log_table["max_command_chars"], path, "log.max_command_chars"))

    gate_table = _table(doc, "gate", ("enabled",), path)
    if gate_table["enabled"] is not False:
        # v1 has no gate to enable (R-30). Accepting true would leave a file
        # that says the gate is on while nothing blocks.
        raise ConfigError(path, "gate.enabled",
                          "must be false: the gate never blocks in v1 (R-30)")
    gate = Gate(enabled=False)

    corpus_table = _table(doc, "corpus", ("capture",), path)
    if not isinstance(corpus_table["capture"], bool):
        raise ConfigError(path, "corpus.capture", "must be true or false")
    corpus = Corpus(corpus_table["capture"])

    return Config(path, checks, invocations, aliases, scopes, human, low,
                  REQUIRED_DEFAULT_TIER,
                  extractor, budget, log, gate, corpus)


def _checks(doc: dict, path: Path) -> tuple[
        tuple[Check, ...], Mapping[str, str], Mapping[str, str],
        Mapping[str, tuple[Glob, ...]]]:
    table = doc.get("checks")
    if table is None:
        raise ConfigError(path, "checks", "missing required table")
    if not isinstance(table, dict):
        raise ConfigError(path, "checks", "must be a table")
    for subtable, shape in (("scope", "check id -> globs"),
                            ("aliases", "the words a report uses -> check id")):
        if subtable not in table:
            raise ConfigError(path, f"checks.{subtable}", "missing required table")
        if not isinstance(table[subtable], dict):
            raise ConfigError(path, f"checks.{subtable}", f"must be a table of {shape}")

    checks = []
    invocations: dict[str, str] = {}
    for check_id, listed in table.items():
        if check_id in ("scope", "aliases"):
            continue
        key = _key("checks", check_id)
        if not _BARE_KEY.fullmatch(check_id):
            raise ConfigError(path, key, "a check id is made of letters, digits, '-' and '_'")
        if not isinstance(listed, list) or not listed:
            raise ConfigError(path, key, "must be a non-empty list of exact invocations")
        for i, invocation in enumerate(listed):
            item = _key("checks", check_id, i)
            _require_invocation(invocation, path, item)
            if invocation in invocations:
                raise ConfigError(path, item, f"{invocation!r} is already listed under "
                                              f"{invocations[invocation]}")
            invocations[invocation] = check_id
        checks.append(Check(check_id, tuple(listed)))

    used = {c.check_id for c in checks}
    aliases: dict[str, str] = {}
    for alias, check_id in table["aliases"].items():
        key = _key("checks", "aliases", alias)
        if not alias.strip() or alias != alias.strip():
            raise ConfigError(path, key, "must be the words a report uses, without "
                                         "surrounding whitespace")
        if check_id not in used:
            raise ConfigError(path, key, f"names no check: {check_id!r} is not a check id")
        lowered = alias.lower()
        if lowered in aliases:
            raise ConfigError(path, key, f"{alias!r} is already an alias, "
                                         "and matching ignores case")
        if lowered in {i.lower() for i in invocations}:
            raise ConfigError(path, key, f"{alias!r} is already an invocation of a check")
        aliases[lowered] = check_id
    scopes = {}
    for check_id, globs in table["scope"].items():
        key = _key("checks", "scope", check_id)
        if check_id not in used:
            raise ConfigError(path, key, "no [checks] pattern maps to this check id")
        if not isinstance(globs, list) or not globs:
            raise ConfigError(path, key, "must be a non-empty list of globs")
        scopes[check_id] = tuple(_scope_glob(g, path, _key("checks", "scope", check_id, i))
                                 for i, g in enumerate(globs))
    for check in checks:
        if check.check_id not in scopes:
            raise ConfigError(path, _key("checks", "scope", check.check_id),
                              "missing: every check id needs the globs it covers")
    return (tuple(checks), MappingProxyType(invocations), MappingProxyType(aliases),
            MappingProxyType(scopes))


def _scope_glob(value: object, path: Path, key: str) -> Glob:
    if isinstance(value, str) and any(char.isspace() for char in value):
        raise ConfigError(path, key, "contains whitespace: [checks.scope] lists the file "
                                     "globs a check covers, not the invocations of [checks]")
    return _glob(value, path, key)


def _require_invocation(value: object, path: Path, key: str) -> None:
    if not isinstance(value, str):
        raise ConfigError(path, key, "must be a string: an exact command line")
    if not value.strip():
        raise ConfigError(path, key, "empty invocation")
    if value != value.strip():
        raise ConfigError(path, key, "leading or trailing whitespace: commands are "
                                     "stripped before matching, so it could never match")
    if _NOT_SIMPLE.search(value):
        raise ConfigError(path, key, "contains a shell operator: a command with one "
                                     "is never a check")


def _table(doc: dict, name: str, keys: tuple[str, ...], path: Path,
           hints: Mapping[str, str] = MappingProxyType({})) -> dict:
    if name not in doc:
        raise ConfigError(path, name, "missing required table")
    table = doc[name]
    if not isinstance(table, dict):
        raise ConfigError(path, name, "must be a table")
    for key in table:
        if key not in keys:
            hint = hints.get(key)
            raise ConfigError(path, _key(name, key),
                              f"unknown key ({hint})" if hint else "unknown key")
    for key in keys:
        if key not in table:
            raise ConfigError(path, _key(name, key), "missing required key")
    return table


def _tier_rules(entries: object, path: Path, tier: str) -> tuple[TierRule, ...]:
    if not isinstance(entries, list):
        raise ConfigError(path, _key("tiers", tier), "must be a list of entries")
    return tuple(_tier_rule(e, path, _key("tiers", tier, i)) for i, e in enumerate(entries))


def _tier_rule(entry: object, path: Path, key: str) -> TierRule:
    if not isinstance(entry, str):
        raise ConfigError(path, key, "must be a string: a path glob or Bash(<command pattern>)")
    tool_rule = _TOOL_RULE.fullmatch(entry)
    if tool_rule:
        tool, specifier = tool_rule.groups()
        if tool != "Bash":
            raise ConfigError(path, key, f"{tool}(...) is not a supported entry: "
                                         "write a path glob, or Bash(<command pattern>)")
        return TierRule(entry, command=_command_pattern(specifier, path, key))
    if entry in _BARE_TOOL_NAMES:
        raise ConfigError(path, key, "a bare tool name is not a supported entry: "
                                     "write a path glob, or Bash(<command pattern>)")
    return TierRule(entry, glob=_glob(entry, path, key))


def _command_pattern(text: str, path: Path, key: str) -> CommandPattern:
    if not text.strip():
        raise ConfigError(path, key, "empty command pattern")
    if text != text.strip():
        raise ConfigError(path, key, "command pattern has leading or trailing whitespace")
    body = text[:-2] + " *" if text.endswith(":*") else text
    if body.endswith(" *") and body.count("*") == 1:
        regex = re.escape(body[:-2]) + "(?: .*)?"
    else:
        regex = ".*".join(re.escape(piece) for piece in body.split("*"))
    return CommandPattern(text, re.compile(regex, re.DOTALL))


class _Malformed(ValueError):
    pass


def _glob(text: object, path: Path, key: str) -> Glob:
    if not isinstance(text, str):
        raise ConfigError(path, key, "must be a string glob")
    try:
        return Glob(text, re.compile(_glob_regex(text)))
    except _Malformed as e:
        problem = str(e)
    except re.error as e:  # a reversed range such as [z-a]
        problem = f"bad character class ({e.msg})"
    raise ConfigError(path, key, f"malformed glob {text!r}: {problem}")


def _glob_regex(glob: str) -> str:
    if not glob:
        raise _Malformed("empty")
    if glob != glob.strip():
        raise _Malformed("leading or trailing whitespace")
    if "\\" in glob:
        raise _Malformed("backslash: separate segments with '/'; escapes are not supported")
    if glob[0] in "/~":
        raise _Malformed(f"globs are relative to the project root; drop the leading {glob[0]!r}")
    if "{" in glob or "}" in glob:
        raise _Malformed("braces are not supported; list each pattern separately")
    segments = glob.split("/")
    out = []
    for i, segment in enumerate(segments):
        last = i == len(segments) - 1
        if segment == "":
            raise _Malformed("empty path segment; write 'dir/**' for everything in a directory"
                             if last else "empty path segment")
        if segment in (".", ".."):
            raise _Malformed(f"{segment!r} segment")
        if segment == "**":
            out.append("[^/]+(?:/[^/]+)*" if last else "(?:[^/]+/)*")
        elif "**" in segment:
            raise _Malformed("'**' must be a whole path segment")
        else:
            out.append(_segment_regex(segment) + ("" if last else "/"))
    return "".join(out)


def _segment_regex(segment: str) -> str:
    out = []
    i = 0
    while i < len(segment):
        char = segment[i]
        if char == "*":
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        elif char == "[":
            start = i + 1
            negate = start < len(segment) and segment[start] in "!^"
            body_start = start + negate
            search_from = body_start + (segment[body_start:body_start + 1] == "]")
            close = segment.find("]", search_from)
            if close == -1:
                raise _Malformed("unclosed '['")
            body = "".join("\\" + c if c in "\\^[]&~|" else c
                           for c in segment[body_start:close])
            out.append(f"[^/{body}]" if negate else f"(?!/)[{body}]")
            i = close
        else:
            out.append(re.escape(char))
        i += 1
    return "".join(out)


def _parameters(table: object, path: Path) -> Mapping[str, object]:
    """The sampling parameters this route takes, checked but not interpreted.

    Which ones a model accepts is a fact about the route, not about the ledger:
    GPT-5.x takes neither temperature nor top_p, and sending one with
    require_parameters on leaves the router with no endpoint at all. So the
    set is declared here rather than fixed in the client. What the client sets
    itself cannot be overwritten from here.
    """
    if not isinstance(table, dict):
        raise ConfigError(path, "extractor.parameters",
                          "must be a table of the parameters this route takes")
    for name, value in table.items():
        key = _key("extractor", "parameters", name)
        if name in RESERVED_PARAMETERS:
            raise ConfigError(path, key, "the client sets this itself")
        if not isinstance(value, (str, int, float, bool, dict)):
            raise ConfigError(path, key, "must be a value the API takes, not "
                                         f"{type(value).__name__}")
    return MappingProxyType(dict(table))


def _word(value: object, path: Path, key: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ConfigError(path, key, "must be a non-empty string without surrounding space")
    return value


def _one_of(value: object, allowed: tuple[str, ...], path: Path, key: str) -> str:
    if value not in allowed:
        raise ConfigError(path, key, f"must be one of {list(allowed)}, not {value!r}")
    return value


def _seconds(value: object, path: Path, key: str) -> float:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value <= 0):
        raise ConfigError(path, key, "must be a positive number of seconds")
    return float(value)


def _positive_int(value: object, path: Path, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigError(path, key, "must be a positive integer")
    return value


def _key(*parts: str | int) -> str:
    out = ""
    for part in parts:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            name = part if _BARE_KEY.fullmatch(part) else json.dumps(part)
            out += f".{name}" if out else name
    return out


def _require_relative(path: str) -> None:
    if (not isinstance(path, str) or not path or path.startswith("/") or "\\" in path
            or any(seg in ("", ".", "..") for seg in path.split("/"))):
        raise ValueError(f"expected a normalised project-relative path, got {path!r}")


def _segments(command: str) -> list[str]:
    return [s.strip() for s in _SEGMENT_SPLIT.split(command) if s.strip()]


def _from_each_word(text: str) -> list[str]:
    return [text[m.start():] for m in _WORD_START.finditer(text)]


def _covers(rule: TierRule, part: tuple[str | None, str | None]) -> bool:
    path, segment = part
    if path is not None:
        return rule.glob is not None and rule.glob.matches(path)
    return rule.command is not None and rule.command.matches(segment)
