from __future__ import annotations
import re


def normalize_to_digits(phone: str) -> str:
    if phone is None:
        return ""
    raw = str(phone).strip().lower()
    if raw.startswith("whatsapp:"):
        raw = raw.split("whatsapp:", 1)[1]
    return re.sub(r"\D", "", raw)


def normalize_to_mx_local10(phone: str) -> str:
    digits = normalize_to_digits(phone)
    if not digits:
        return ""
    if digits.startswith("521") and len(digits) >= 13:
        return digits[-10:]
    if digits.startswith("52") and len(digits) >= 12:
        return digits[-10:]
    return digits[-10:] if len(digits) >= 10 else digits


def normalize_to_e164(phone: str, default_country: str = "MX") -> str:
    digits = normalize_to_digits(phone)
    if not digits:
        return ""
    if default_country == "MX":
        if digits.startswith("521") and len(digits) >= 13:
            return f"+{digits}"
        if digits.startswith("52") and len(digits) >= 12:
            return f"+{digits}"
        if len(digits) == 10:
            return f"+52{digits}"
    return f"+{digits}"


def possible_match_key(phone: str) -> str:
    return normalize_to_mx_local10(phone) or normalize_to_digits(phone)
