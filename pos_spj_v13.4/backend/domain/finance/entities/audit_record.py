"""AuditRecord — rastro inmutable de una operación financiera (§25).

Guarda quién, qué operación, sobre qué entidad, qué acción, el estado antes y
después, el motivo, cuándo y en qué sucursal. Nunca guarda secretos
bancarios completos: los números de cuenta se enmascaran antes de auditar.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.finance.enums import AuditAction
from backend.domain.finance.exceptions import FinanceDomainError
from backend.shared.ids import new_uuid

_SENSITIVE_KEYS = ("account_number", "clabe", "card_number", "iban", "cuenta")
_DIGITS = re.compile(r"\d")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def mask_account_number(value: str | None) -> str:
    """``012345678901234567`` → ``••••4567``. Vacío se queda vacío."""
    text = re.sub(r"\s+", "", str(value or ""))
    if not text:
        return ""
    if len(text) <= 4:
        return "••••"
    return "••••" + text[-4:]


def scrub(data):
    """Copia de ``data`` con los campos sensibles enmascarados."""
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in _SENSITIVE_KEYS) and value \
                    and _DIGITS.search(str(value)) and "masked" not in lowered:
                result[key] = mask_account_number(str(value))
            else:
                result[key] = scrub(value)
        return result
    if isinstance(data, (list, tuple)):
        return [scrub(item) for item in data]
    return data


@dataclass(frozen=True, slots=True)
class AuditRecord:
    id: str
    action: AuditAction
    entity_type: str
    entity_id: str
    operation_id: str
    user_id: str | None
    before_json: str
    after_json: str
    reason: str
    branch_id: str | None
    occurred_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, *, action: AuditAction, entity_type: str, entity_id: str,
               operation_id: str, user_id: str | None, before: dict | None = None,
               after: dict | None = None, reason: str | None = None,
               branch_id: str | None = None) -> "AuditRecord":
        if not entity_type or not entity_id or not operation_id:
            raise FinanceDomainError("La auditoría requiere entidad y operación")
        return cls(
            id=new_uuid(), action=action, entity_type=entity_type, entity_id=entity_id,
            operation_id=operation_id, user_id=user_id,
            before_json=json.dumps(scrub(before or {}), ensure_ascii=False, default=str,
                                   sort_keys=True),
            after_json=json.dumps(scrub(after or {}), ensure_ascii=False, default=str,
                                  sort_keys=True),
            reason=(reason or "").strip(), branch_id=branch_id,
        )
