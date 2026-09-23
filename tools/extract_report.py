"""Run the extractor over one captured report and print the claims.

    python3 tools/extract_report.py [--root PROJECT] [--request] REPORT.md

The report is a file the Stop handler captured under
.claude/claim-ledger/reports/. Where it is sent, which model reads it, which
provider must answer and which variable holds the key all come from
PROJECT/claim-ledger.toml. Nothing is written anywhere: this prints what the
extractor saw, so that a corpus can be annotated against real output rather
than against imagination.

--request prints the request instead of sending it, which needs no key.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ledger import config, extract, schema, turn  # noqa: E402


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Extract the claims of a captured report.")
    parser.add_argument("report", type=Path, help="a captured reports/<session>-<n>.md")
    parser.add_argument("--root", type=Path, default=Path("."), help="project root (default: .)")
    parser.add_argument("--request", action="store_true",
                        help="print the request that would be sent, and send nothing")
    args = parser.parse_args(argv[1:])

    try:
        header, report_text = turn.read_capture(args.report)
        settings = config.load(args.root / config.CONFIG_FILENAME).extractor
    except (turn.TurnError, config.ConfigError, OSError) as e:
        print(e, file=sys.stderr)
        return 2

    prompt = extract.load_prompt()
    print(f"{args.report}: session {header.get('session')}, turn {header.get('turn_number')}, "
          f"{len(report_text)} characters")
    print(f"prompt {prompt.version}, model {settings.model} at {settings.base_url}, "
          f"provider {settings.provider}, answer shape {settings.answer_shape}")

    if args.request:
        request = extract.build_request(report_text, vocabulary=schema.CLAIM_TYPES,
                                        settings=settings, prompt=prompt)
        print(f"POST {request.url}")
        print(json.dumps(request.body, indent=2))
        return 0

    try:
        result = extract.extract(report_text, settings=settings, prompt=prompt)
    except (extract.ExtractError, schema.SchemaError) as e:
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        print("the turn this report belongs to would be UNKNOWN", file=sys.stderr)
        return 1

    answered = result.provenance
    print(f"\nanswered by {answered.provider}\n"
          f"{len(result.claims)} claims, {len(result.defects)} defects")
    for claim in result.claims:
        referents = ", ".join(claim.referents) or "-"
        print(f"  {claim.type:13} {claim.span!r}\n                referents: {referents}")
    for defect in result.defects:
        print(f"  DEFECT        {defect.span!r}\n                {defect.reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
