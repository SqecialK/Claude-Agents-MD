"""Reusable parsing helpers for Upwork job URLs.

Extracts the numeric job ID Upwork embeds in job URLs (after a leading
``~``) and builds the direct "apply" URL from it.
"""

import re

_JOB_ID_PATTERN = re.compile(r"~(\d+)")


class JobUrlError(ValueError):
    """Raised when a job URL does not contain a recognizable job ID."""


def extract_job_id(job_url: str) -> str:
    """Return the numeric job ID embedded in an Upwork job URL.

    Upwork job URLs contain the ID as ``~0212345678901234`` somewhere in the
    path, e.g. ``https://www.upwork.com/jobs/~021234567890``.
    """
    match = _JOB_ID_PATTERN.search(job_url or "")
    if not match:
        raise JobUrlError(f"Could not find a job ID (~digits) in URL: {job_url!r}")
    return match.group(1)


def build_apply_url(job_url: str) -> str:
    """Build the direct proposal-submission URL for a given job URL."""
    job_id = extract_job_id(job_url)
    return f"https://www.upwork.com/nx/proposals/job/~{job_id}/apply/"
