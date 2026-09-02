"""ConfigurationApprovalPolicy — does this definition require approval,
and may this actor approve their own change? (§9, §59 segregation of
duties: "quien crea una configuración crítica no debe aprobarla").
"""

from __future__ import annotations

from backend.domain.settings.exceptions import ConfigurationApprovalRequiredError


def requires_approval(definition) -> bool:
    return bool(definition.approval_required)


def assert_can_approve(value, *, approver_user_id: str) -> None:
    """Segregation of duties: the user who created a value cannot also be
    the one who approves it."""
    if value.created_by_user_id and value.created_by_user_id == approver_user_id:
        raise ConfigurationApprovalRequiredError(
            "Quien crea un cambio de configuración no puede aprobarlo — se requiere un "
            "segundo usuario (segregación de funciones, §59)."
        )
