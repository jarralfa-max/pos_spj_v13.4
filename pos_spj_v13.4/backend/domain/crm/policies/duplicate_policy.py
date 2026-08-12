"""LeadDuplicatePolicy — detects likely duplicate leads (§16, "evitar
duplicado"). Mirrors
backend/domain/customers/policies/duplicate_policy.py::CustomerDuplicatePolicy,
kept as its own copy rather than a cross-context import — Leads and
Customers are separate bounded contexts and Lead has no RFC/legal_name axis
to match on.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


def _normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", (value or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", text)


@dataclass(frozen=True)
class LeadDuplicateMatch:
    lead_id: str
    reasons: tuple[str, ...]


class LeadDuplicatePolicy:
    """``existing`` rows are dicts with keys: id, display_name, phone_e164, email."""

    def find_matches(self, candidate: dict, existing: list[dict]) -> list[LeadDuplicateMatch]:
        matches: list[LeadDuplicateMatch] = []
        cand_name = _normalize_name(candidate.get("display_name", ""))
        cand_phone = re.sub(r"\D", "", candidate.get("phone_e164", "") or "")
        cand_email = (candidate.get("email") or "").strip().lower()

        for row in existing:
            reasons: list[str] = []
            if cand_name and cand_name == _normalize_name(row.get("display_name", "")):
                reasons.append("Mismo nombre")
            if cand_phone and cand_phone == re.sub(r"\D", "", row.get("phone_e164", "") or ""):
                reasons.append("Mismo teléfono")
            if cand_email and cand_email == (row.get("email") or "").strip().lower():
                reasons.append("Mismo correo")
            if reasons:
                matches.append(LeadDuplicateMatch(lead_id=row.get("id", ""),
                                                   reasons=tuple(reasons)))
        return matches
