#!/usr/bin/env python3
"""Generate Upwork proposal packages and push them to Google Sheets.

Usage:
    # Interactive: paste Title, then URL, then Description ending in a
    # line that says just "done". Repeat, or type "done" at the title
    # prompt to finish and push everything to Sheets.
    python operations/generate_proposal.py

    # Single job via flags (useful for scripting/testing):
    python operations/generate_proposal.py \\
        --title "AI Automation Specialist" \\
        --url "https://www.upwork.com/jobs/~021234567890" \\
        --description "Looking for someone to build ..."

    # Batch from a JSON file: a list of {"title", "url", "description"}.
    python operations/generate_proposal.py --input jobs.json

    # Generate content only, skip the Google Sheets push:
    python operations/generate_proposal.py --input jobs.json --no-sheets
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.env_loader import load_env
from tools.job_parser import JobUrlError, build_apply_url
from tools.solution_identifier import identify_solution
from tools.proposal_content import render_cover_letter, generate_vsl_script
from tools.infographic import generate_infographic_url
from tools.sheets_client import SheetsError, push_to_sheets


def generate_proposal(job_title: str, job_url: str, job_description: str) -> dict:
    """Build the full proposal package for a single job.

    Raises ``tools.job_parser.JobUrlError`` if the Apply URL can't be
    derived from ``job_url``.
    """
    apply_url = build_apply_url(job_url)
    solution = identify_solution(job_title, job_description)
    cover_letter = render_cover_letter(job_title, solution)
    vsl_script = generate_vsl_script(job_title, job_description, solution)
    infographic_url = generate_infographic_url(solution["mermaid"])

    return {
        "job_title": job_title,
        "job_url": job_url,
        "apply_url": apply_url,
        "solution_category": solution["name"],
        "cover_letter": cover_letter,
        "vsl_script": vsl_script,
        "infographic_url": infographic_url,
    }


def _print_proposal(proposal: dict) -> None:
    print("\n" + "=" * 70)
    print(f"Job: {proposal['job_title']}")
    print(f"Solution category: {proposal['solution_category']}")
    print(f"Apply URL: {proposal['apply_url']}")
    print(f"Infographic: {proposal['infographic_url']}")
    print("-" * 70)
    print("COVER LETTER:\n")
    print(proposal["cover_letter"])
    print("-" * 70)
    print("VSL SCRIPT:\n")
    print(proposal["vsl_script"])
    print("=" * 70)


def _read_multiline_description() -> str:
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip().lower() == "done":
            break
        lines.append(line)
    return "\n".join(lines)


def run_interactive() -> list:
    proposals = []
    print("Paste job details below. Type 'done' at the Job Title prompt to finish.\n")
    while True:
        try:
            title = input("Job Title (or 'done' to finish): ").strip()
        except EOFError:
            break
        if not title or title.lower() == "done":
            break
        url = input("Job URL: ").strip()
        print("Job Description (end with a line containing only 'done'):")
        description = _read_multiline_description()

        try:
            proposal = generate_proposal(title, url, description)
        except JobUrlError as exc:
            print(f"Skipping job — {exc}", file=sys.stderr)
            continue

        _print_proposal(proposal)
        proposals.append(proposal)
    return proposals


def run_batch(jobs: list) -> list:
    proposals = []
    for job in jobs:
        try:
            title, url, description = job["title"], job["url"], job["description"]
        except KeyError as exc:
            print(f"Skipping job — missing field {exc}", file=sys.stderr)
            continue
        try:
            proposal = generate_proposal(title, url, description)
        except JobUrlError as exc:
            print(f"Skipping job {title!r} — {exc}", file=sys.stderr)
            continue
        _print_proposal(proposal)
        proposals.append(proposal)
    return proposals


def push_proposals(proposals: list) -> None:
    if not proposals:
        print("Nothing to push.")
        return

    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    sheet_name = os.environ.get("GOOGLE_SHEET_NAME")
    credentials_path = os.environ.get("GOOGLE_CREDENTIALS_PATH", "credentials.json")

    try:
        count = push_to_sheets(
            proposals,
            credentials_path=credentials_path,
            sheet_id=sheet_id,
            sheet_name=sheet_name,
        )
        print(f"\nPushed {count} row(s) to Google Sheets.")
    except SheetsError as exc:
        print(f"\nSheets error: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--title", help="Job title (single-job mode)")
    parser.add_argument("--url", help="Job URL (single-job mode)")
    parser.add_argument("--description", help="Job description (single-job mode)")
    parser.add_argument("--input", help="Path to a JSON file with a list of {title, url, description} jobs")
    parser.add_argument("--no-sheets", action="store_true", help="Generate content only; skip the Google Sheets push")
    args = parser.parse_args()

    load_env()

    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            jobs = json.load(f)
        proposals = run_batch(jobs)
    elif args.title or args.url or args.description:
        if not (args.title and args.url and args.description):
            parser.error("--title, --url, and --description must be provided together")
        try:
            proposals = [generate_proposal(args.title, args.url, args.description)]
        except JobUrlError as exc:
            parser.error(str(exc))
        _print_proposal(proposals[0])
    else:
        proposals = run_interactive()

    if not args.no_sheets:
        push_proposals(proposals)


if __name__ == "__main__":
    main()
