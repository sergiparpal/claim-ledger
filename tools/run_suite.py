#!/usr/bin/env python3
"""Run the test suite on every declared Python version, or fail saying which is missing.

The point is that the set is declared here rather than discovered per machine.
A session that asks PATH and a session that asks uv get different answers about
the same computer, and "it passed on the versions I happened to find" is the
kind of claim this project exists to stop being made. So this refuses to run on
fewer than the declared set: a missing interpreter is a failure that names
itself, not a quietly shorter run.

    python3 tools/run_suite.py             every declared version
    python3 tools/run_suite.py --list      what is declared, and where each was found
    python3 tools/run_suite.py --versions  the declared versions alone, for CI

Each version is resolved twice over, and which answered is printed: a system
interpreter on PATH first, then uv's managed and discovered installs. uv is
asked with `python find`, which never downloads, so a missing version stays
missing and says so instead of turning a commit into a download.

3.11, the floor the project claims to support, is declared like the rest. It
was left to a CI job of its own until 5 October 2026, and this repository has
never had a remote, so that job never ran: the floor was claimed and tested
nowhere. The pre-commit hook runs on every commit; CI runs only where something
is pushed.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

#: The versions the suite is declared to pass on. One place; CI reads it too.
DECLARED = ("3.11", "3.12", "3.13", "3.14")

REPO = Path(__file__).resolve().parent.parent
SUITE = ("-m", "unittest", "discover")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--list", action="store_true",
                        help="print the declared set and where each was found, run nothing")
    parser.add_argument("--versions", action="store_true",
                        help="print the declared versions and nothing else, for CI to read")
    args = parser.parse_args(argv)

    if args.versions:   # the one output with no prose: CI feeds it to uv
        print(" ".join(DECLARED))
        return 0

    print(f"claim-ledger · declared: {', '.join(DECLARED)}\n")
    found = {version: find(version) for version in DECLARED}
    if args.list:
        for version, (path, source) in found.items():
            print(f"  {version}  {source or 'MISSING':<7} {path or '-'}")
        return 0 if all(path for path, _ in found.values()) else 1

    missing = [version for version, (path, _) in found.items() if path is None]
    if missing:
        for version in missing:
            print(f"  {version}  MISSING — declared, and no interpreter for it here.")
            print(f"        install it with:  uv python install {version}")
        print(f"\nrefusing to run on {len(DECLARED) - len(missing)} of {len(DECLARED)} "
              f"declared versions")
        return 1

    failed = []
    for version in DECLARED:
        path, source = found[version]
        started = time.monotonic()
        done = subprocess.run([path, *SUITE], cwd=REPO, capture_output=True, text=True)
        elapsed = time.monotonic() - started
        # unittest writes its summary to stderr, last. Both lines are taken
        # from the end for that reason: a test that writes something looking
        # like a summary would otherwise be quoted here instead of the real
        # one, and a run reporting another run's numbers is the exact failure
        # this script exists to prevent.
        lines = done.stderr.strip().splitlines()
        summary = lines[-1] if lines else "no output"
        count = next((line for line in reversed(lines)
                      if line.startswith("Ran ")), "ran nothing")
        print(f"  {version}  {source:<7} {count:<22} {summary:<28} {elapsed:5.1f}s")
        if done.returncode != 0:
            failed.append((version, done.stdout, done.stderr))

    if failed:
        for version, out, err in failed:
            print(f"\n{'=' * 70}\n{version} failed:\n{'=' * 70}")
            sys.stdout.write(out)
            sys.stderr.write(err)
        print(f"\n{len(failed)} of {len(DECLARED)} declared versions failed")
        return 1
    print(f"\nall {len(DECLARED)} declared versions passed")
    return 0


def find(version: str) -> tuple[str | None, str]:
    """An interpreter for this version, and which of the two found it."""
    on_path = shutil.which(f"python{version}")
    if on_path and version_of(on_path) == version:
        return on_path, "system"
    if shutil.which("uv"):
        # `python find` resolves without downloading, which is what keeps a
        # missing version a failure rather than a surprise install.
        done = subprocess.run(["uv", "python", "find", version],
                              capture_output=True, text=True)
        path = done.stdout.strip()
        if done.returncode == 0 and path and version_of(path) == version:
            return path, "uv"
    return None, ""


def version_of(interpreter: str) -> str | None:
    """major.minor as the interpreter itself reports it, never as its name claims.

    Anything that will not run and answer is no version at all: a dangling
    symlink, a file without the execute bit, a python3.13 that is really 3.12.
    Those resolve to None and the version goes on to be reported missing, which
    is the whole point — a broken interpreter must not read as an absent one
    any more than an absent one may read as a pass.
    """
    try:
        done = subprocess.run([interpreter, "-c",
                               "import sys; print('%d.%d' % sys.version_info[:2])"],
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
