"""Status formatter — maps backend status codes to es-MX labels (single source)."""

from __future__ import annotations

from frontend.desktop.i18n.es_mx import status_label


def format_status(code: str | None) -> str:
    """``"AUTHORIZED"`` → ``Autorizado``. Unknown codes pass through unchanged."""
    return status_label(code)
