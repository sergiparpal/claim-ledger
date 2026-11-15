#!/usr/bin/env python3
"""Ship a commit to a project: move the release copy, update the install, check both.

    cd ~/code/distiller
    python3 ~/code/claim-ledger/tools/ship.py COMMIT [--dry-run] [--yes]

docs/OPERATING.md § Ship a version gives the three commands this runs, and why
a version ships between sessions. It is meant for a person in a terminal. A
Claude Code session cannot run it, since its sandbox keeps the release copy
and ~/.claude/plugins read-only, and that is as it should be: the release copy
is a clone apart so that nothing done in a session can move it.

Nothing moves until every check has passed:

- COMMIT is a commit of this repository, and its plugin.json names a higher
  version than the release copy holds, since `claude plugin update` goes by
  the version;
- the release copy is clean, since it is never edited;
- the plugin is installed in the project at local scope, enabled, and read
  from the release copy;
- a person answers yes, after being shown when a session of the project
  last wrote its transcript, since only a person knows whether one is open;
- and no transcript of the project was written, or begun, while the question
  was open, since a session that writes is running whatever the answer says.
  A session open and idle writes nothing, so this catches only a busy one,
  and transcripts that cannot be read would hide even that: then nothing
  ships, unless --yes says to ship without asking.

Then it fetches, checks COMMIT out detached and runs the update from the
project, and it checks the result: the copy at COMMIT and clean, and the
install reporting the new version both as installed and as the folder holds
it. Nothing is rolled back on a failure: it says where the copy was left and
how to put it back. Run again on a copy already at COMMIT, it only finishes
the update.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLUGIN = "claim-ledger@claim-ledger"
MANIFEST = ".claude-plugin/plugin.json"
RELEASE = Path.home() / "code" / "claim-ledger-release"

# What git tells a command about the repository it runs in, as `git rev-parse --local-env-vars`
# lists it. Left set, by a hook for one, they would turn every `git -C` here to that repository.
GIT_REPOSITORY_VARIABLES = (
    "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_CONFIG", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT",
    "GIT_OBJECT_DIRECTORY", "GIT_DIR", "GIT_WORK_TREE", "GIT_IMPLICIT_WORK_TREE",
    "GIT_GRAFT_FILE", "GIT_INDEX_FILE", "GIT_NO_REPLACE_OBJECTS", "GIT_REPLACE_REF_BASE",
    "GIT_PREFIX", "GIT_SHALLOW_FILE", "GIT_COMMON_DIR",
)


class Refused(Exception):
    """A check failed. Before the ship nothing has moved; after it, main says what has."""


@dataclass(frozen=True)
class Plan:
    sha: str
    version: str
    shipped_sha: str
    shipped_version: str
    installed_version: str
    release: Path
    project: Path

    @property
    def moves(self) -> bool:
        return self.sha != self.shipped_sha

    @property
    def done(self) -> bool:
        return not self.moves and self.installed_version == self.version


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("commit", help="the commit of this repository to ship")
    parser.add_argument("--project", type=Path, default=Path.cwd(),
                        help="the project the plugin is installed in (default: here)")
    parser.add_argument("--release", type=Path, default=RELEASE,
                        help=f"the release copy (default: {RELEASE})")
    parser.add_argument("--config-dir", type=Path,
                        default=Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude"),
                        help="where Claude Code keeps its transcripts (default: ~/.claude)")
    parser.add_argument("--dry-run", action="store_true", help="check everything, move nothing")
    parser.add_argument("--yes", action="store_true",
                        help="ship without asking, and so without a second look at the transcripts")
    args = parser.parse_args(argv)
    project = args.project.expanduser().resolve()
    release = args.release.expanduser().resolve()

    try:
        plan = prepare(args.commit, release, project)
    except Refused as refusal:
        print(f"not shipped: {refusal}")
        return 1
    print(f"claim-ledger · ship {plan.version} ({plan.sha[:7]}) to {project}\n")
    print(f"  release copy  {release}, clean, at {plan.shipped_version} ({plan.shipped_sha[:7]})")
    print(f"  install       local, enabled, read from the release copy, "
          f"reports {plan.installed_version}")
    if plan.done:
        print("\nalready shipped: nothing to do")
        return 0
    folder = transcript_folder(project, args.config_dir.expanduser())
    seen = transcripts(folder)
    print(f"  last session  {last_session(seen, folder)}")
    if not plan.moves:
        print("\nthe release copy is already at the commit: only the update is left to run")
    if args.dry_run:
        print("\ndry run: nothing moved")
        return 0
    if not args.yes:
        if isinstance(seen, str):
            print(f"\nnot shipped: {unseen(folder)}: nothing moved")
            return 1
        if not confirmed():
            print("not shipped: nothing moved")
            return 1
        now = transcripts(folder)  # the answer may come much later
        if isinstance(now, str):
            print(f"not shipped: {unseen(folder)}: nothing moved")
            return 1
        running = written_since(seen, now)
        if running:
            whose = "its transcript" if len(running) == 1 else "their transcripts"
            print(f"not shipped: {', '.join(session[:8] for session in running)} wrote {whose} "
                  f"while the question was open, so a session of the project is running. "
                  f"Close it, or if you just did, run this again: nothing moved")
            return 1

    try:
        ship(plan)
        verify(plan)
    except Refused as refusal:
        print(f"\nfailed: {refusal}")
        print(left(plan))
        return 1
    print(f"\nshipped {plan.version} ({plan.sha[:7]}) to {project}: its next session runs it")
    return 0


def prepare(commit: str, release: Path, project: Path) -> Plan:
    """Every check that comes before the ship. Raises Refused, having moved nothing."""
    try:
        sha = git(REPO, "rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}")
    except Refused:
        raise Refused(f"{commit} is not a commit of {REPO}") from None
    version = version_of(git(REPO, "show", f"{sha}:{MANIFEST}"), f"{MANIFEST} at {sha[:7]}")
    if not (release / ".git").exists():
        raise Refused(f"{release} is not a clone")
    changed = git(release, "status", "--porcelain")
    if changed:
        raise Refused(f"the release copy {release} has changes, and it is never edited:\n{changed}")
    shipped_sha = git(release, "rev-parse", "HEAD")
    shipped_version = version_of(git(release, "show", f"HEAD:{MANIFEST}"),
                                 f"{MANIFEST} in the release copy")
    if sha != shipped_sha and numbers(version) <= numbers(shipped_version):
        raise Refused(f"{MANIFEST} at {sha[:7]} names {version}, not above the "
                      f"{shipped_version} the release copy holds: raise the version first")
    entry = install(project)
    if entry.get("enabled") is not True:
        raise Refused(f"{PLUGIN} is installed in {project} but not enabled")
    if not same(entry.get("readFromFolder"), release):
        raise Refused(f"the install in {project} reads {entry.get('readFromFolder')}, "
                      f"not the release copy {release}")
    return Plan(sha, version, shipped_sha, shipped_version, str(entry.get("version")),
                release, project)


def ship(plan: Plan) -> None:
    if plan.moves:
        git(plan.release, "fetch", "--quiet")
        try:
            git(plan.release, "cat-file", "-e", f"{plan.sha}^{{commit}}")
        except Refused:
            raise Refused(f"after fetching, the release copy has no {plan.sha[:7]}: "
                          f"is it on a branch of {REPO}?") from None
        git(plan.release, "checkout", "--quiet", "--detach", plan.sha)
        print(f"\n  checked out   {plan.sha[:7]} in the release copy")
    updated = claude(plan.project, "plugin", "update", PLUGIN, "--scope", "local")
    if updated.returncode != 0:
        raise Refused(f"claude plugin update exited {updated.returncode}: "
                      f"{(updated.stderr or updated.stdout).strip()}")
    print(f"  updated       {(updated.stdout or '').strip() or 'claude plugin update exited 0'}")


def verify(plan: Plan) -> None:
    """The ship as the copy and the install report it afterwards, not as it was asked for."""
    head = git(plan.release, "rev-parse", "HEAD")
    if head != plan.sha:
        raise Refused(f"the release copy is at {head[:7]}, not {plan.sha[:7]}")
    if git(plan.release, "status", "--porcelain"):
        raise Refused("the release copy has changes after the checkout")
    entry = install(plan.project)
    for key in ("version", "folderVersion"):
        if entry.get(key) != plan.version:
            raise Refused(f"the install reports {key} {entry.get(key)}, not {plan.version}")
    if entry.get("enabled") is not True or not same(entry.get("readFromFolder"), plan.release):
        raise Refused("the install is no longer enabled and read from the release copy")
    print(f"  checked       release copy at {plan.sha[:7]} and clean; "
          f"the install reports {plan.version}")


def left(plan: Plan) -> str:
    """Where a failed ship left the release copy, and how to put it back."""
    try:
        head = git(plan.release, "rev-parse", "HEAD")
    except Refused:
        return "  where the release copy stands could not be read"
    if head == plan.shipped_sha:
        return "  the release copy did not move"
    return (f"  the release copy is at {head[:7]}, and the project runs it from its next hook.\n"
            f"  to put it back:  git -C {plan.release} checkout --detach {plan.shipped_sha}\n"
            f"  and then, from {plan.project}:  claude plugin update {PLUGIN} --scope local")


def install(project: Path) -> dict:
    """The plugin's local install in the project, as `claude plugin list --json` reports it."""
    listed = claude(project, "plugin", "list", "--json")
    if listed.returncode != 0:
        raise Refused(f"claude plugin list --json exited {listed.returncode}: "
                      f"{(listed.stderr or listed.stdout).strip()}")
    try:
        entries = json.loads(listed.stdout)
    except json.JSONDecodeError:
        raise Refused("claude plugin list --json did not answer JSON") from None
    for entry in entries if isinstance(entries, list) else []:
        if (isinstance(entry, dict) and entry.get("id") == PLUGIN
                and entry.get("scope") == "local" and same(entry.get("projectPath"), project)):
            return entry
    raise Refused(f"{PLUGIN} is not installed at local scope in {project}")


def claude(project: Path, *args: str) -> subprocess.CompletedProcess:
    """The Claude Code CLI, run from the project, without a session's variables around it.

    Started from inside a session, CLAUDECODE and the rest would tell the CLI it
    is nested. CLAUDE_CONFIG_DIR stays, since it says which install to read.
    """
    environment = {name: value for name, value in os.environ.items()
                   if not name.startswith(("CLAUDE", "ANTHROPIC")) or name == "CLAUDE_CONFIG_DIR"}
    try:
        return subprocess.run(["claude", *args], cwd=project, env=environment,
                              capture_output=True, text=True, timeout=300)
    except FileNotFoundError:
        raise Refused("claude is not on PATH") from None
    except subprocess.TimeoutExpired:
        raise Refused(f"claude {' '.join(args)} did not finish in 300 seconds") from None


def git(repository: Path, *args: str) -> str:
    environment = {name: value for name, value in os.environ.items()
                   if name not in GIT_REPOSITORY_VARIABLES}
    try:
        done = subprocess.run(["git", "-C", str(repository), *args], env=environment,
                              capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        raise Refused(f"git {' '.join(args)} did not finish in 120 seconds") from None
    if done.returncode != 0:
        raise Refused(f"git -C {repository} {' '.join(args)} exited {done.returncode}: "
                      f"{(done.stderr or done.stdout).strip()}")
    return done.stdout.strip()


def version_of(manifest: str, where: str) -> str:
    try:
        version = json.loads(manifest)["version"]
    except (json.JSONDecodeError, KeyError, TypeError):
        raise Refused(f"{where} names no version") from None
    if not isinstance(version, str) or not re.fullmatch(r"\d+(\.\d+)*", version):
        raise Refused(f"{where} names the version {version!r}, which cannot be compared")
    return version


def numbers(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def same(path: object, other: Path) -> bool:
    return isinstance(path, str) and bool(path) and Path(path).resolve() == other.resolve()


def transcript_folder(project: Path, config_dir: Path) -> Path:
    """Where Claude Code keeps a project's transcripts: a folder named for its path,
    each character that is not a letter or a digit turned into a dash."""
    return config_dir / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(project))


def transcripts(folder: Path) -> dict[str, int] | str:
    """Each transcript in the folder, by session, with when it was last written in
    nanoseconds; or, when the folder is there but cannot be read, why not.

    A folder that is not there holds no transcript: the project has had no session.
    Path.glob is not used, since how it treats a folder it cannot read differs
    between Python versions, and here that folder must not pass for an empty one.
    """
    try:
        with os.scandir(folder) as entries:
            found = [entry for entry in entries if entry.name.endswith(".jsonl")]
    except FileNotFoundError:
        return {}
    except OSError as error:
        return error.strerror or type(error).__name__
    written = {}
    for entry in found:
        try:
            written[entry.name.removesuffix(".jsonl")] = entry.stat().st_mtime_ns
        except OSError:
            continue  # gone between the listing and the look
    return written


def last_session(written: dict[str, int] | str, folder: Path) -> str:
    """Which transcript was written last, and when: the hint the person is shown.

    A session left open and idle writes nothing, which is why a person is asked.
    """
    if isinstance(written, str):
        return f"the transcripts in {folder} could not be read: {written}"
    if not written:
        return f"no transcript of the project in {folder}"
    session = max(written, key=written.__getitem__)
    return f"{session[:8]} wrote its transcript {ago(time.time() - written[session] / 1e9)}"


def written_since(before: dict[str, int], after: dict[str, int]) -> list[str]:
    """The sessions whose transcript was written, or begun, between two looks at the folder."""
    return sorted(session for session, when in after.items() if before.get(session) != when)


def unseen(folder: Path) -> str:
    """Why nothing ships while the transcripts cannot be read, unless --yes says to."""
    return (f"the transcripts in {folder} could not be read, so a session writing one while "
            f"the question is open would not be seen. Make them readable, or pass --yes")


def ago(seconds: float) -> str:
    minutes = int(seconds // 60)
    if minutes < 1:
        return "less than a minute ago"
    if minutes < 120:
        return f"{minutes} minutes ago"
    if minutes < 48 * 60:
        return f"{minutes // 60} hours ago"
    return f"{minutes // (24 * 60)} days ago"


def confirmed() -> bool:
    try:
        answer = input("\nAre the project's sessions closed, and should it ship? [yes/no] ")
    except EOFError:
        return False
    return answer.strip().lower() in ("yes", "y")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
