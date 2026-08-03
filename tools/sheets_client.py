"""Pushes generated proposal rows to a Google Sheet.

Imports for ``gspread`` / ``google-auth`` are done lazily inside the
functions below so the rest of the tool suite stays importable and
testable in environments where those packages aren't installed.
"""

import datetime

SHEET_COLUMNS = [
    "Job Title",
    "Apply URL",
    "Cover Letter",
    "VSL Script",
    "Infographic URL",
    "Status",
    "Date",
]

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


class SheetsError(RuntimeError):
    """Raised when the sheet cannot be reached or written to."""


def _hyperlink(url: str, label: str) -> str:
    escaped_label = label.replace('"', '""')
    return f'=HYPERLINK("{url}", "{escaped_label}")'


def build_row(proposal: dict) -> list:
    """Build one sheet row (list of cell values) from a proposal dict.

    ``proposal`` MUST contain: job_title, apply_url, cover_letter,
    vsl_script, infographic_url. ``status`` defaults to "New" and ``date``
    defaults to today (YYYY-MM-DD) if not supplied.
    """
    return [
        proposal["job_title"],
        _hyperlink(proposal["apply_url"], "Apply"),
        proposal["cover_letter"],
        proposal["vsl_script"],
        _hyperlink(proposal["infographic_url"], "View Infographic"),
        proposal.get("status", "New"),
        proposal.get("date", datetime.date.today().isoformat()),
    ]


def _open_sheet(credentials_path: str, sheet_id: str = None, sheet_name: str = None):
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError as exc:
        raise SheetsError(
            "Missing dependency: run `pip install gspread google-auth` "
            "before pushing to Google Sheets."
        ) from exc

    try:
        creds = Credentials.from_service_account_file(credentials_path, scopes=_SCOPES)
        client = gspread.authorize(creds)
    except FileNotFoundError as exc:
        raise SheetsError(f"credentials.json not found at: {credentials_path}") from exc

    try:
        if sheet_id:
            return client.open_by_key(sheet_id).sheet1
        return client.open(sheet_name).sheet1
    except gspread.exceptions.SpreadsheetNotFound as exc:
        raise SheetsError(
            "Spreadsheet not found or not shared with the service account. "
            "Share the sheet with the service account's client_email from "
            "credentials.json."
        ) from exc


def ensure_header(worksheet) -> None:
    """Write the header row if the sheet is currently empty."""
    if not worksheet.get_all_values():
        worksheet.append_row(SHEET_COLUMNS, value_input_option="USER_ENTERED")


def push_to_sheets(
    proposals: list,
    credentials_path: str,
    sheet_id: str = None,
    sheet_name: str = None,
) -> int:
    """Append one row per proposal to the target Google Sheet.

    Returns the number of rows written. Raises ``SheetsError`` on any
    authentication, access, or missing-dependency failure.
    """
    if not sheet_id and not sheet_name:
        raise SheetsError("Provide either sheet_id or sheet_name to locate the sheet.")

    worksheet = _open_sheet(credentials_path, sheet_id=sheet_id, sheet_name=sheet_name)
    ensure_header(worksheet)

    rows = [build_row(proposal) for proposal in proposals]
    worksheet.append_rows(rows, value_input_option="USER_ENTERED")
    return len(rows)
