# Transcripts

Drop saved chat transcripts in this folder (nested subfolders are fine) and
they become searchable via `operations/search_transcripts.py`.

## Format

Each transcript is a plain text or Markdown file with an optional metadata
header:

```
---
date: 2026-08-11
title: Deploy pipeline discussion
tags: deploy, infra
---
Whatever the conversation content is goes here, line by line.
```

- `date` — `YYYY-MM-DD`, used for `--after` / `--before` filtering.
- `title` — free text, shown next to search results.
- `tags` — comma-separated, used for `--tag` filtering.

The header is optional. Files without one are still searched; their date
and title are just reported as unknown.

## Searching

```
python operations/search_transcripts.py "some query"
python operations/search_transcripts.py "err(or)?s?" --regex -C 2
python operations/search_transcripts.py "budget" --tag finance --json
```

Run `python operations/search_transcripts.py --help` for all options.
