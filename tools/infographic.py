"""Turns Mermaid diagram source into a renderable mermaid.ink image URL."""

import base64

_MERMAID_INK_BASE = "https://mermaid.ink/img/"


def generate_infographic_url(mermaid_source: str) -> str:
    """Encode Mermaid diagram source as a mermaid.ink image URL.

    mermaid.ink renders ``/img/<base64>`` where ``<base64>`` is a URL-safe
    base64 encoding of the raw diagram text.
    """
    encoded = base64.urlsafe_b64encode(mermaid_source.encode("utf-8")).decode("ascii")
    return f"{_MERMAID_INK_BASE}{encoded}"
