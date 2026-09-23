"""Install claim-ledger into a project: the deny rule and the .gitignore line.

    python3 <plugin>/src/ledger/install.py [PROJECT_DIR]

Adds, when missing:

- Edit(claim-ledger.toml) to permissions.deny in PROJECT_DIR/.claude/settings.json.
  That is the shared project file: committed, it reaches every clone, and deny
  rules in it apply without the workspace-trust step. The rule is a speed bump,
  not protection, since any process the agent starts can write the file (R-27).
- .claude/claim-ledger/ to PROJECT_DIR/.gitignore, unless git already ignores
  the directory. Whether it does is git's answer, not a search for that line:
  a project that ignores .claude/ wholesale, or through its global excludes,
  is already covered, and a later negation un-ignores the line again. Outside
  a repository there is nothing to commit, so the recorder runs; inside one
  that git cannot answer for, it refuses rather than guess.

Nothing else in either file changes, running it twice changes nothing, and a
settings file that is not a JSON object is left untouched and reported. Hooks
are not registered here: they ship in hooks/hooks.json and load with the plugin.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

if __name__ == "__main__" and not __package__:
    sys.path[0] = str(Path(__file__).resolve().parents[1])

from ledger import config  # noqa: E402

DENY_RULE = "Edit(claim-ledger.toml)"
GITIGNORE_LINE = ".claude/claim-ledger/"
SETTINGS = Path(".claude") / "settings.json"
PLUGIN_ROOT = Path(__file__).resolve().parents[2]

IGNORED, NOT_IGNORED, NO_GIT, UNKNOWN = "ignored", "not ignored", "no git", "unknown"
_GIT_TIMEOUT_S = 5


class InstallError(Exception):
    """The project cannot be installed into without overwriting something."""


def ignore_state(root: Path) -> str:
    """What git says about .claude/claim-ledger/ under root.

    IGNORED or NOT_IGNORED when git can answer, NO_GIT when there is no
    repository or no git to ask, and UNKNOWN inside a repository whose git
    could not answer.
    """
    checked = _git(root, "check-ignore", "-q", GITIGNORE_LINE)
    if checked is not None and checked.returncode in (0, 1):
        return IGNORED if checked.returncode == 0 else NOT_IGNORED
    inside = _git(root, "rev-parse", "--is-inside-work-tree")
    return UNKNOWN if inside is not None and inside.returncode == 0 else NO_GIT


def state_is_ignored(root: Path) -> bool:
    """Whether the ledger may write: git ignores the directory, or cannot commit it."""
    return ignore_state(root) in (IGNORED, NO_GIT)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(["git", *args], cwd=root, capture_output=True,
                              timeout=_GIT_TIMEOUT_S)
    except (OSError, subprocess.SubprocessError):
        return None  # no git binary, no readable directory, or git hung


def gitignore_has_line(root: Path) -> bool:
    """Whether root/.gitignore holds the state line exactly, trailing spaces aside."""
    try:
        text = (root / ".gitignore").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return any(line.rstrip() == GITIGNORE_LINE for line in text.splitlines())


def add_gitignore_line(root: Path) -> bool:
    """Append the state line to root/.gitignore. Returns whether it changed."""
    if gitignore_has_line(root):
        return False
    path = root / ".gitignore"
    existing = path.read_bytes() if path.exists() else b""
    separator = b"" if not existing or existing.endswith(b"\n") else b"\n"
    with path.open("ab") as f:
        f.write(separator + GITIGNORE_LINE.encode() + b"\n")
    return True


def add_deny_rule(root: Path) -> bool:
    """Add DENY_RULE to root/.claude/settings.json. Returns whether it changed."""
    path = root / SETTINGS
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        text = ""
    try:
        settings = json.loads(text) if text.strip() else {}
    except ValueError as e:
        raise InstallError(f"{path} is not valid JSON ({e}); left untouched") from e
    if not isinstance(settings, dict):
        raise InstallError(f"{path} is not a JSON object; left untouched")
    permissions = settings.setdefault("permissions", {})
    if not isinstance(permissions, dict):
        raise InstallError(f"{path}: permissions is not an object; left untouched")
    deny = permissions.setdefault("deny", [])
    if not isinstance(deny, list):
        raise InstallError(f"{path}: permissions.deny is not a list; left untouched")
    if DENY_RULE in deny:
        return False
    deny.append(DENY_RULE)
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    staged.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    os.replace(staged, path)  # never leaves a half-written settings file
    return True


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else ".").resolve()
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2
    try:
        rule = add_deny_rule(root)
        before = ignore_state(root)
        line = add_gitignore_line(root) if before != IGNORED else False
    except (InstallError, OSError) as e:
        print(f"install failed: {e}", file=sys.stderr)
        return 2
    print(f"claim-ledger install into {root}")
    print(f"  {SETTINGS}: {'added' if rule else 'already has'} deny rule {DENY_RULE}")
    if before == IGNORED:
        print(f"  .gitignore: git already ignores {GITIGNORE_LINE}")
    else:
        print(f"  .gitignore: {'added' if line else 'already has'} {GITIGNORE_LINE}"
              f" (git said: {before})")
    after = ignore_state(root)
    if not state_is_ignored(root):
        print(f"  the ledger will not record: git still says {after} for {GITIGNORE_LINE}."
              " A later .gitignore rule may re-include it.", file=sys.stderr)
        return 2
    try:
        config.load(root / config.CONFIG_FILENAME)
    except config.ConfigError as e:
        print(f"  {config.CONFIG_FILENAME}: does not load: {e}")
        print("The recorder logs an error for every tool call until the config loads.")
        return 1
    print(f"  {config.CONFIG_FILENAME}: loads")
    print(f"Start Claude Code at {root} with: claude --plugin-dir {PLUGIN_ROOT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
