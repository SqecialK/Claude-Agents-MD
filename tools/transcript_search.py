"""
Reusable logic for loading and searching chat transcripts stored in
transcripts/. See plans/search-chat-transcripts.md for the governing plan.

Search backends are pluggable: KeywordSearchBackend is implemented here.
A future EmbeddingSearchBackend can be added without changing Transcript
loading, metadata parsing, or SearchResult shape.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable, Optional

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
FIELD_RE = re.compile(r"^(\w+):\s*(.*)$")


@dataclass
class Transcript:
    path: Path
    date: Optional[str]
    title: Optional[str]
    tags: list[str]
    body: str
    lines: list[str]


@dataclass
class SearchResult:
    path: Path
    date: Optional[str]
    title: Optional[str]
    line_number: int
    line: str
    context_before: list[str]
    context_after: list[str]


class TranscriptLoadError(Exception):
    """Raised when a transcript file cannot be decoded as text."""


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text

    header, body = match.group(1), match.group(2)
    fields: dict = {}
    for raw_line in header.splitlines():
        field_match = FIELD_RE.match(raw_line.strip())
        if field_match:
            fields[field_match.group(1).lower()] = field_match.group(2).strip()
    return fields, body


def load_transcript(path: Path) -> Transcript:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        raise TranscriptLoadError(f"{path}: {exc}") from exc

    fields, body = _parse_frontmatter(text)
    tags_raw = fields.get("tags", "")
    tags = [t.strip() for t in tags_raw.split(",") if t.strip()]

    return Transcript(
        path=path,
        date=fields.get("date"),
        title=fields.get("title"),
        tags=tags,
        body=body,
        lines=body.splitlines(),
    )


def load_transcripts(directory: Path) -> tuple[list[Transcript], list[str]]:
    """Load every transcript in `directory`.

    Returns (transcripts, skipped_messages) — unreadable files are skipped,
    not fatal, with a human-readable reason recorded for each.
    """
    transcripts: list[Transcript] = []
    skipped: list[str] = []

    if not directory.exists():
        return transcripts, skipped

    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.name == "README.md":
            continue
        try:
            transcripts.append(load_transcript(path))
        except TranscriptLoadError as exc:
            skipped.append(str(exc))

    return transcripts, skipped


class KeywordSearchBackend:
    """Deterministic substring/regex search over transcript lines."""

    def search(
        self,
        transcripts: Iterable[Transcript],
        query: str,
        *,
        regex: bool = False,
        case_sensitive: bool = False,
        context: int = 0,
        date_after: Optional[str] = None,
        date_before: Optional[str] = None,
        tag: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[SearchResult]:
        if regex:
            flags = 0 if case_sensitive else re.IGNORECASE
            try:
                pattern = re.compile(query, flags)
            except re.error as exc:
                raise ValueError(f"Invalid regular expression: {exc}") from exc
            matches_line = lambda line: pattern.search(line) is not None
        else:
            needle = query if case_sensitive else query.lower()
            matches_line = lambda line: needle in (line if case_sensitive else line.lower())

        results: list[SearchResult] = []
        for transcript in transcripts:
            if tag and tag not in transcript.tags:
                continue
            if date_after and (transcript.date is None or transcript.date < date_after):
                continue
            if date_before and (transcript.date is None or transcript.date > date_before):
                continue

            for i, line in enumerate(transcript.lines):
                if not matches_line(line):
                    continue
                results.append(
                    SearchResult(
                        path=transcript.path,
                        date=transcript.date,
                        title=transcript.title,
                        line_number=i + 1,
                        line=line,
                        context_before=transcript.lines[max(0, i - context):i],
                        context_after=transcript.lines[i + 1:i + 1 + context],
                    )
                )
                if limit is not None and len(results) >= limit:
                    return results

        return results
