"""CRMAutomationRule — declarative trigger→action rule (§56, CRM-26).

``trigger_config``/``action_config`` are flat JSON parameter dicts (e.g.
``{"idle_days": 3}``, ``{"title": "Dar seguimiento", "due_in_hours": 24}``)
never executable code — "No permitir scripts arbitrarios. Usar reglas
declarativas." is enforced structurally: nothing in this bounded context
ever ``eval()``s or imports anything named by a rule, it only reads known
keys off these dicts when the matching action executor runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.crm.enums import CRMAutomationAction, CRMAutomationTrigger
from backend.domain.crm.exceptions import InvalidCRMAutomationRuleError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class CRMAutomationRule:
    id: str
    name: str
    trigger_type: CRMAutomationTrigger
    action_type: CRMAutomationAction
    trigger_config: dict
    action_config: dict
    description: str = ""
    active: bool = True
    created_by_user_id: str = ""
    operation_id: str = ""
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)
    version: int = 1

    @classmethod
    def create(
        cls, name: str, trigger_type: CRMAutomationTrigger, action_type: CRMAutomationAction,
        *, trigger_config: dict | None = None, action_config: dict | None = None,
        description: str = "", created_by_user_id: str = "", operation_id: str = "",
    ) -> "CRMAutomationRule":
        if not name or not name.strip():
            raise InvalidCRMAutomationRuleError("name es obligatorio")
        if not isinstance(trigger_type, CRMAutomationTrigger):
            raise InvalidCRMAutomationRuleError(f"trigger_type inválido: {trigger_type!r}")
        if not isinstance(action_type, CRMAutomationAction):
            raise InvalidCRMAutomationRuleError(f"action_type inválido: {action_type!r}")
        return cls(
            id=new_uuid(), name=name.strip(), trigger_type=trigger_type, action_type=action_type,
            trigger_config=dict(trigger_config or {}), action_config=dict(action_config or {}),
            description=description.strip(), created_by_user_id=created_by_user_id,
            operation_id=operation_id,
        )

    def activate(self) -> None:
        self.active = True
        self.version += 1
        self.updated_at = _utcnow()

    def deactivate(self) -> None:
        self.active = False
        self.version += 1
        self.updated_at = _utcnow()

    def update_config(self, *, trigger_config: dict | None = None,
                      action_config: dict | None = None) -> None:
        if trigger_config is not None:
            self.trigger_config = dict(trigger_config)
        if action_config is not None:
            self.action_config = dict(action_config)
        self.version += 1
        self.updated_at = _utcnow()
