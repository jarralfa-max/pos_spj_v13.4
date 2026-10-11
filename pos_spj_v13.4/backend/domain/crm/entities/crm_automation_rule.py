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

from backend.domain.crm.enums import (
    ACTION_TARGET_ENTITIES,
    DAY_THRESHOLD_TRIGGERS,
    TRIGGER_TARGET_ENTITY,
    CRMAutomationAction,
    CRMAutomationTrigger,
    LeadPriority,
)
from backend.domain.crm.exceptions import InvalidCRMAutomationRuleError
from backend.shared.ids import new_uuid

_TARGET_NOUN = {"LEAD": "prospectos", "OPPORTUNITY": "oportunidades", "CASE": "casos",
                "CUSTOMER": "clientes"}
_ACTION_NOUN = {
    CRMAutomationAction.CREATE_TASK: "Crear tarea",
    CRMAutomationAction.ASSIGN_OWNER: "Asignar responsable",
    CRMAutomationAction.SEND_NOTIFICATION: "Enviar aviso",
    CRMAutomationAction.CHANGE_PRIORITY: "Cambiar prioridad",
    CRMAutomationAction.ESCALATE_CASE: "Escalar caso",
    CRMAutomationAction.ADD_TAG: "Agregar etiqueta",
    CRMAutomationAction.ADD_TO_SEGMENT: "Agregar a segmento",
}
_CASE_PRIORITIES = frozenset({"LOW", "NORMAL", "HIGH", "URGENT", "CRITICAL"})


def threshold_days(trigger_config: dict) -> int | None:
    """Los días del umbral (``days``; ``idle_days`` en reglas anteriores a CRM-43)."""
    raw = trigger_config.get("days", trigger_config.get("idle_days"))
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return None
    return days if days > 0 else None


def validate_rule_config(trigger_type: CRMAutomationTrigger, action_type: CRMAutomationAction,
                         trigger_config: dict, action_config: dict) -> None:
    """CRM-43: una regla que no puede ejecutarse no se guarda. Antes se aceptaba
    cualquier combinación y el fallo aparecía después como ejecución OMITIDA."""
    target = TRIGGER_TARGET_ENTITY[trigger_type]
    if target not in ACTION_TARGET_ENTITIES[action_type]:
        raise InvalidCRMAutomationRuleError(
            f"«{_ACTION_NOUN[action_type]}» no aplica a {_TARGET_NOUN[target]}.")
    if trigger_type in DAY_THRESHOLD_TRIGGERS and threshold_days(trigger_config) is None:
        raise InvalidCRMAutomationRuleError("Indica después de cuántos días se dispara la regla.")
    required = {
        CRMAutomationAction.ASSIGN_OWNER: ("assignee_user_id", "Elige a quién se asigna."),
        CRMAutomationAction.ESCALATE_CASE: ("escalated_to_user_id", "Elige a quién se escala."),
        CRMAutomationAction.ADD_TAG: ("tag_id", "Elige la etiqueta."),
        CRMAutomationAction.ADD_TO_SEGMENT: ("segment_id", "Elige el segmento."),
        CRMAutomationAction.CHANGE_PRIORITY: ("priority", "Elige la prioridad nueva."),
    }.get(action_type)
    if required and not action_config.get(required[0]):
        raise InvalidCRMAutomationRuleError(required[1])
    if action_type is CRMAutomationAction.CHANGE_PRIORITY:
        allowed = ({p.value for p in LeadPriority} if target == "LEAD" else _CASE_PRIORITIES)
        if action_config["priority"] not in allowed:
            raise InvalidCRMAutomationRuleError(
                f"Los {_TARGET_NOUN[target]} no tienen la prioridad {action_config['priority']}.")
    if action_type is CRMAutomationAction.SEND_NOTIFICATION:
        if not action_config.get("recipient_user_id") and not action_config.get("notify_responsible"):
            raise InvalidCRMAutomationRuleError(
                "Elige quién recibe el aviso (una persona o el responsable del registro).")


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
        validate_rule_config(trigger_type, action_type, dict(trigger_config or {}),
                             dict(action_config or {}))
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
        validate_rule_config(
            self.trigger_type, self.action_type,
            dict(self.trigger_config if trigger_config is None else trigger_config),
            dict(self.action_config if action_config is None else action_config))
        if trigger_config is not None:
            self.trigger_config = dict(trigger_config)
        if action_config is not None:
            self.action_config = dict(action_config)
        self.version += 1
        self.updated_at = _utcnow()
