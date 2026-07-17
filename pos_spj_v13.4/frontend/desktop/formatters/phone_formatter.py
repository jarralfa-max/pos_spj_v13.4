"""Phone formatter — E.164 → readable. Display only; never for identity/storage."""

from __future__ import annotations


def format_phone(e164: str | None) -> str:
    """``+525512345678`` → ``+52 55 1234 5678``. Non-E.164 returned as-is."""
    if not e164:
        return "—"
    text = str(e164).strip()
    if not text.startswith("+"):
        return text
    digits = text[1:]
    if not digits.isdigit():
        return text
    # Mexico (+52): country + 10 national digits → +52 AA BBBB CCCC
    if digits.startswith("52") and len(digits) == 12:
        nat = digits[2:]
        return f"+52 {nat[0:2]} {nat[2:6]} {nat[6:10]}"
    # US/Canada (+1): +1 AAA BBB CCCC
    if digits.startswith("1") and len(digits) == 11:
        nat = digits[1:]
        return f"+1 {nat[0:3]} {nat[3:6]} {nat[6:10]}"
    # Generic: group the national part in blocks of 3-4
    return text
