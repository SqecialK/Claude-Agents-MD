# Plan — Search Past Chat Transcripts

## Goal / Objective
Give Claude a way to search back through previously saved chat transcripts
stored in this repository, so past conversations can be referenced, recalled,
or reused without the user having to paste them back in manually.

## Required Inputs
- A collection of transcript files stored under `transcripts/`, each
  representing one past conversation. Each transcript SHOULD begin with a
  small metadata header (date, title, optional tags) followed by the
  conversation text, in the format described in `transcripts/README.md`.
- A search query supplied by Claude or the user (a keyword, phrase, or
  regular expression).
- Optional filters: date range, tag, case sensitivity, result limit, and
  amount of surrounding context to return per match.

## Expected Outputs
- A list of matches, each identifying: the source transcript file, its date
  and title (if present), the matching line, and surrounding context.
- Output MUST be available in both a human-readable form and a structured
  (JSON) form, so it can be read directly by a person or parsed by Claude.
- No matches is a valid, explicit result — not an error.

## Constraints and Assumptions
- Transcripts are plain text/Markdown files checked into `transcripts/`.
  This plan does not cover fetching transcripts from an external service,
  database, or API — only searching files already present in the repo.
- The initial search mode is keyword/substring/regex matching. It MUST be
  exact and deterministic (no ranking by "relevance" beyond match order).
- The system MUST be structured so a second search mode — semantic
  (embedding-based) search — can be added later without changing how
  transcripts are stored or how results are reported. Semantic search is
  NOT implemented in this pass.
- No transcript content is modified, moved, or deleted by the search tool.
- No network access or paid APIs are required for keyword search.

## Allowed Operations and Tools
- Tool: `tools/transcript_search.py` — reusable logic for loading
  transcripts, parsing their metadata header, and running a search backend
  against them. This is where the keyword backend and the future semantic
  backend both live.
- Operation: `operations/search_transcripts.py` — the deterministic,
  invokable entry point (CLI) that Claude runs to perform a search. It
  reads arguments, calls into the tool, and prints results.

## Known Edge Cases and Failure Modes
- `transcripts/` is empty or missing → return zero results, not an error.
- A transcript file has no metadata header → it is still searched; date and
  title are reported as unknown.
- A transcript file is not valid text (binary, unreadable encoding) → it is
  skipped and reported as skipped, not fatal to the whole search.
- An invalid regular expression is supplied → the operation MUST fail
  explicitly with a clear error message rather than silently falling back
  to substring search.
- Very large transcript collections → keyword search remains linear scan
  for now; if this becomes a performance problem, an index should be added
  as a new Tool rather than rewritten inline in the operation.
