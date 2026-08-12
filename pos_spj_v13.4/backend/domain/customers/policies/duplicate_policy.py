"""CustomerDuplicatePolicy — detects likely duplicate customers (§45).

Mirrors backend/domain/suppliers/policies.py::SupplierDuplicatePolicy. Never
merges automatically — it only reports candidates for a human decision
(``CustomerDuplicateCandidate`` persistence and the merge workflow itself are
CRM-11). This directly preserves the legacy dedupe check
(``ClienteService.existe_similar`` — exact-match on nombre+apellido+teléfono,
see docs/architecture/CRM_0_CUSTOMER_MASTER_AUDIT.md §1) but widens it to the
§45 criteria (teléfono, correo, RFC, nombre normalizado), matching what
Suppliers already does for its own duplicate detection.
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
class CustomerDuplicateMatch:
    customer_id: str
    reasons: tuple[str, ...]


class CustomerDuplicatePolicy:
    """``existing`` rows are dicts with keys: id, tax_identifier, display_name,
    legal_name, phone_e164, email."""

    def find_matches(self, candidate: dict, existing: list[dict]) -> list[CustomerDuplicateMatch]:
        matches: list[CustomerDuplicateMatch] = []
        cand_rfc = (candidate.get("tax_identifier") or "").strip().upper()
        cand_name = _normalize_name(candidate.get("display_name", ""))
        cand_legal = _normalize_name(candidate.get("legal_name", ""))
        cand_phone = re.sub(r"\D", "", candidate.get("phone_e164", "") or "")
        cand_email = (candidate.get("email") or "").strip().lower()

        for row in existing:
            reasons: list[str] = []
            if cand_rfc and cand_rfc == (row.get("tax_identifier") or "").strip().upper():
                reasons.append("Mismo RFC")
            row_names = {_normalize_name(row.get("display_name", "")),
                         _normalize_name(row.get("legal_name", ""))}
            if cand_name and cand_name in row_names:
                reasons.append("Mismo nombre")
            elif cand_legal and cand_legal in row_names:
                reasons.append("Misma razón social")
            if cand_phone and cand_phone == re.sub(r"\D", "", row.get("phone_e164", "") or ""):
                reasons.append("Mismo teléfono")
            if cand_email and cand_email == (row.get("email") or "").strip().lower():
                reasons.append("Mismo correo")
            if reasons:
                matches.append(CustomerDuplicateMatch(
                    customer_id=row.get("id", ""), reasons=tuple(reasons)))
        return matches
