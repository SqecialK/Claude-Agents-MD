#!/usr/bin/env python3
"""
Deterministic CLI operation: search past chat transcripts in transcripts/.
Calls into tools/transcript_search.py for all loading/search logic.
See plans/search-chat-transcripts.md for the governing plan.

Usage:
    python operations/search_transcripts.py "some query" [options]

Examples:
    python operations/search_transcripts.py "deploy checklist"
    python operations/search_transcripts.py "err(or)?s?" --regex -C 2
    python operations/search_transcripts.py "budget" --tag finance --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.transcript_search import KeywordSearchBackend, load_transcripts

DEFAULT_TRANSCRIPTS_DIR = Path(__file__).resolve().parent.parent / "transcripts"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Search past chat transcripts.")
    parser.add_argument("query", help="Text or regex pattern to search for.")
    parser.add_argument(
        "--dir",
        type=Path,
        default=DEFAULT_TRANSCRIPTS_DIR,
        help="Directory containing transcript files (default: transcripts/).",
    )
    parser.add_argument("--regex", action="store_true", help="Treat query as a regular expression.")
    parser.add_argument("--case-sensitive", action="store_true", help="Match case exactly.")
    parser.add_argument("-C", "--context", type=int, default=1, help="Lines of context around each match.")
    parser.add_argument("--after", dest="date_after", help="Only match transcripts dated on/after YYYY-MM-DD.")
    parser.add_argument("--before", dest="date_before", help="Only match transcripts dated on/before YYYY-MM-DD.")
    parser.add_argument("--tag", help="Only match transcripts carrying this tag.")
    parser.add_argument("--limit", type=int, help="Maximum number of results to return.")
    parser.add_argument("--json", action="store_true", help="Print results as JSON instead of text.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    transcripts, skipped = load_transcripts(args.dir)

    try:
        results = KeywordSearchBackend().search(
            transcripts,
            args.query,
            regex=args.regex,
            case_sensitive=args.case_sensitive,
            context=args.context,
            date_after=args.date_after,
            date_before=args.date_before,
            tag=args.tag,
            limit=args.limit,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        payload = {
            "query": args.query,
            "transcripts_searched": len(transcripts),
            "skipped": skipped,
            "results": [
                {
                    "file": str(r.path),
                    "date": r.date,
                    "title": r.title,
                    "line_number": r.line_number,
                    "line": r.line,
                    "context_before": r.context_before,
                    "context_after": r.context_after,
                }
                for r in results
            ],
        }
        print(json.dumps(payload, indent=2))
        return 0

    if skipped:
        for message in skipped:
            print(f"skipped: {message}", file=sys.stderr)

    if not results:
        print(f"No matches for {args.query!r} across {len(transcripts)} transcript(s).")
        return 0

    for r in results:
        header = f"{r.path}"
        if r.date or r.title:
            header += f"  [{r.date or 'unknown date'} — {r.title or 'untitled'}]"
        print(header)
        for line in r.context_before:
            print(f"    {line}")
        print(f" >  {r.line}")
        for line in r.context_after:
            print(f"    {line}")
        print()

    print(f"{len(results)} match(es) across {len(transcripts)} transcript(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
