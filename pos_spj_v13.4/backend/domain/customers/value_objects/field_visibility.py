"""Field-level masking for sensitive Customer/CRM data (§75).

Protected fields: teléfono, correo, RFC, CURP, dirección, saldo, límite de
crédito, notas privadas, documentos, evidencia de consentimiento. The UI
renders one of four visibility states; it never decides on its own whether a
field is sensitive — that is a property of the field itself
(`SENSITIVE_FIELDS`), and *how much* of it a given viewer sees is a function
of their granted permission, resolved here rather than left to each dialog to
improvise (which is exactly how the legacy `modulos/clientes.py` UI ended up
inconsistent — see docs/architecture/CRM_0_CUSTOMER_MASTER_AUDIT.md).

Masked values must never reach tooltips, logs, error messages, breadcrumbs or
generic notifications (§75) — that is a UI/logging-layer discipline this
module cannot enforce by itself; `mask()` exists so there is exactly one
place that knows how to redact each field type, instead of every call site
reinventing it.
"""

from __future__ import annotations

from enum import Enum

SENSITIVE_FIELDS = frozenset({
    "telefono", "phone",
    "correo", "email",
    "rfc", "curp",
    "direccion", "address",
    "saldo", "balance",
    "limite_credito", "credit_limit",
    "notas_privadas", "private_notes",
    "documento", "document",
    "evidencia_consentimiento", "consent_evidence",
})


class FieldVisibility(str, Enum):
    """How much of a sensitive field value the current viewer may see."""

    MASKED = "MASKED"
    PARTIALLY_VISIBLE = "PARTIALLY_VISIBLE"
    VISIBLE = "VISIBLE"
    RESTRICTED = "RESTRICTED"  # not shown at all, not even masked (field absent)


def is_sensitive_field(field_name: str) -> bool:
    return (field_name or "").strip().lower() in SENSITIVE_FIELDS


def mask(value: str, visibility: FieldVisibility, *, reveal_last: int = 4) -> str:
    """Render ``value`` for the given visibility. Never raises on empty input.

    - RESTRICTED: caller must not display the field at all; this returns ""
      as a safety net so an accidental render doesn't leak the value.
    - MASKED: every character replaced.
    - PARTIALLY_VISIBLE: only the last ``reveal_last`` characters shown.
    - VISIBLE: value returned unchanged.
    """
    text = str(value or "")
    if visibility == FieldVisibility.RESTRICTED:
        return ""
    if visibility == FieldVisibility.VISIBLE:
        return text
    if visibility == FieldVisibility.PARTIALLY_VISIBLE:
        if len(text) <= reveal_last:
            return "•" * len(text)
        return "•" * (len(text) - reveal_last) + text[-reveal_last:]
    # MASKED (default / fail-safe for any unrecognized state)
    return "•" * len(text)
