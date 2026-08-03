# Plan: Upwork Proposal Generator

## Goal / Objective

Given the details of an Upwork job posting, automatically produce a complete,
ready-to-submit proposal package (cover letter, VSL script, infographic) and
record it in a Google Sheet so every application is tracked in one place.

## Required Inputs

For each job, the following MUST be supplied:

- **Job Title** — the title of the Upwork posting
- **Job URL** — the Upwork job posting URL (used to derive the Apply URL)
- **Job Description** — the full text of the posting, pasted from Upwork

Inputs may arrive interactively (pasted into a running prompt) or as a batch
(a JSON file containing a list of jobs), and via the command line for a
single job.

## Expected Outputs

For each job, produce:

1. **Cover Letter** — personalized to the detected solution category, using
   the fixed bio/template content, with a placeholder for the Loom link the
   user records separately.
2. **VSL Script** — a conversational, ~60-second video script that
   references the job's likely pain point, mentions the infographic, and
   ends with a call to action for a quick call.
3. **Infographic URL** — a `mermaid.ink` link that renders a vertical
   (`flowchart TB`) diagram of 4–5 color-coded subgraphs describing the
   proposed approach for the detected solution category.
4. **Apply URL** — `https://www.upwork.com/nx/proposals/job/~{job_id}/apply/`
   derived from the job's numeric ID in the Job URL.

All of the above MUST be appended as one row to the configured Google Sheet,
with the Apply URL and Infographic URL rendered as clickable links via
`=HYPERLINK()`.

Sheet columns, in order:

`Job Title | Apply URL | Cover Letter | VSL Script | Infographic URL | Status | Date`

New rows default to `Status = New` and `Date = today (YYYY-MM-DD)`.

## Constraints and Assumptions

- Solution category is detected from keywords in the title + description
  only — no external classification service is required.
- Six solution categories are supported: AI Lead Generation, Email
  Automation, AI Receptionist, Lead Automation, Social Automation, and
  Workflow Automation (the default/fallback category).
- The Loom link is NOT recorded automatically; the cover letter and VSL
  script leave an explicit placeholder for the user to fill in after
  recording their walkthrough video.
- Secrets (Google service account path, target Sheet ID/name) are read from
  `.env` at the project root. `.env`, `credentials.json`, and `token.json`
  are never committed (see `.gitignore`).
- Google Sheets access requires a service account (`credentials.json`)
  that has been granted Editor access on the target sheet. If the sheet has
  not been shared with the service account email, pushing MUST fail
  explicitly with a clear error rather than silently skipping the row.
- Mermaid diagram text is transported to `mermaid.ink` as URL-safe base64;
  it is not validated against the mermaid grammar — malformed mermaid syntax
  will simply render an error image, which is an acceptable, visible
  failure mode.
- No LLM call is required to produce the cover letter or VSL script — both
  are generated deterministically from templates plus the detected solution
  category, so the system works with zero API credits spent. An
  `OPENROUTER_API_KEY` in `.env` is reserved for future, optional
  LLM-assisted personalization but is not required for the current scope.

## Allowed Operations and Tools

- `operations/generate_proposal.py` — the single entry point. Reads job
  input (interactive stdin, CLI flags, or a JSON batch file), calls the
  tools below in order, and pushes the resulting rows to Google Sheets.
- `tools/job_parser.py` — extracts the numeric job ID from a job URL and
  builds the Apply URL.
- `tools/solution_identifier.py` — keyword-matches the job title and
  description to one of the six solution categories and returns its name,
  explanation, steps, and mermaid diagram source.
- `tools/infographic.py` — encodes mermaid diagram source into a
  `mermaid.ink` image URL.
- `tools/proposal_content.py` — renders the cover letter and VSL script from
  the fixed templates and the detected solution.
- `tools/sheets_client.py` — authenticates with the Google service account
  and appends rows to the target sheet using `USER_ENTERED` so `HYPERLINK()`
  formulas render as clickable links.

## Known Edge Cases and Failure Modes

- **Job URL has no `~{id}`** — the Apply URL cannot be derived; the
  operation MUST fail explicitly for that job rather than guessing an ID.
- **Sheet not shared with the service account** — `gspread` raises a
  permission error; this MUST surface to the user with a message pointing
  at the setup step (share the sheet with the service account email).
- **`credentials.json` missing or malformed** — fail explicitly before
  attempting to generate content, since content generation without a place
  to record it defeats the point of the run.
- **No keyword match** — falls back to the "Workflow Automation" category
  rather than erroring, since it is the intended default.
- **Description contains characters that break mermaid syntax** (e.g. raw
  `"`, `{`, `}` in node labels) — the solution templates use fixed node
  labels, not raw description text, so this cannot occur from user input
  contaminating the diagram.
- **Batch job missing a required field** — that job is skipped with a
  clear error printed to stdout/stderr; the run continues with the
  remaining jobs rather than aborting the whole batch.
