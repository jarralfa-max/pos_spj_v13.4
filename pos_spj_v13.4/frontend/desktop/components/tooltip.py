"""Canonical tooltip API (FASE DS-3).

One entry point for every tooltip. Supports an optional title, description and
keyboard shortcut. Themed via the global ``QToolTip`` QSS rule. Tooltips must
never carry PII or stack traces and must not replace a required label.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QWidget


def build_tooltip_text(text: str = "", *, title: str | None = None,
                       description: str | None = None,
                       shortcut: str | None = None) -> str:
    """Compose the tooltip's rich text from its parts (single formatting policy)."""
    lines: list[str] = []
    if title:
        lines.append(f"<b>{title}</b>")
    body = description or text
    if body:
        lines.append(body)
    if shortcut:
        lines.append(f"<i>{shortcut}</i>")
    return "<br>".join(lines)


def apply_tooltip(widget: QWidget, text: str = "", *, title: str | None = None,
                  description: str | None = None, shortcut: str | None = None,
                  help_id: str | None = None) -> None:
    """Attach a canonical tooltip to ``widget``.

    ``help_id`` is stored as a property for future context-help wiring; it does
    not appear in the visible tooltip.
    """
    widget.setToolTip(build_tooltip_text(
        text, title=title, description=description, shortcut=shortcut))
    if not widget.accessibleDescription():
        widget.setAccessibleDescription(description or title or text)
    if help_id:
        widget.setProperty("helpId", help_id)
