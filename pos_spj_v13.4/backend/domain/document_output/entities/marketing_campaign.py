"""MarketingCampaign — SET-13 "Campaigns": a configurable ticket message
(loyalty/FOMO/CTA), generalizing the legacy hardcoded messages in
`core/tickets/ticket_message_engine.py::TicketMessageEngine.build_messages`
(e.g. "Estás a {remaining} compras de tu recompensa.") into persisted,
rule-gated data an admin can manage instead of code that needs a
deployment to change.

`rules` (`CampaignRule`, SET-13 "Rules") are ANDed: a campaign only
matches a context when every one of its rules evaluates true against that
context, and — for `requires_customer=True` — the context reports a
customer is actually present. A campaign with a FOMO category and zero
rules would print unconditionally on every ticket forever, which is
exactly the irresponsible/manipulative pattern
`policies/marketing_claim_validation_policy.py` exists to reject.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.document_output.enums import MarketingMessageCategory
from backend.domain.document_output.exceptions import DocumentInvalidValueError
from backend.domain.document_output.value_objects.campaign_rule import CampaignRule
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class MarketingCampaign:
    id: str
    code: str
    category: MarketingMessageCategory
    message_template: str
    priority: int = 0
    requires_customer: bool = False
    rules: tuple[CampaignRule, ...] = ()
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, *, code: str, category: MarketingMessageCategory, message_template: str, priority: int = 0,
        requires_customer: bool = False, rules: tuple[CampaignRule, ...] | list[CampaignRule] = (),
    ) -> "MarketingCampaign":
        if not code.strip():
            raise DocumentInvalidValueError("code es obligatorio")
        if not message_template.strip():
            raise DocumentInvalidValueError("message_template es obligatorio")
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise DocumentInvalidValueError(f"priority debe ser un entero, recibido {priority!r}")
        return cls(
            id=new_uuid(), code=code.strip(), category=category, message_template=message_template.strip(),
            priority=priority, requires_customer=bool(requires_customer), rules=tuple(rules),
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def update_details(
        self, *, message_template: str, priority: int = 0, requires_customer: bool = False,
        rules: tuple[CampaignRule, ...] | list[CampaignRule] = (),
    ) -> None:
        if not message_template.strip():
            raise DocumentInvalidValueError("message_template es obligatorio")
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise DocumentInvalidValueError(f"priority debe ser un entero, recibido {priority!r}")
        self.message_template = message_template.strip()
        self.priority = priority
        self.requires_customer = bool(requires_customer)
        self.rules = tuple(rules)
        self._touch()

    def activate(self) -> None:
        self.active = True
        self._touch()

    def deactivate(self) -> None:
        self.active = False
        self._touch()

    def matches(self, context: dict) -> bool:
        """§ SET-13 "Rules": true only when every rule passes AND, if
        this campaign requires a customer, the context reports one."""
        if not self.active:
            return False
        if self.requires_customer and not context.get("has_customer", False):
            return False
        for rule in self.rules:
            value = context.get(rule.metric)
            if value is None or not rule.evaluate(_as_decimal(value)):
                return False
        return True

    def render_message(self, context: dict) -> str:
        return self.message_template.format(**context)


def _as_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise DocumentInvalidValueError(f"Valor de contexto no puede ser bool para comparación numérica: {value!r}")
    if isinstance(value, int):
        return Decimal(value)
    raise DocumentInvalidValueError(f"Valor de contexto debe ser Decimal o int, recibido {value!r}")
