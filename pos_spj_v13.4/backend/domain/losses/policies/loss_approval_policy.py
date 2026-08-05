from dataclasses import dataclass
from decimal import Decimal

from backend.domain.losses.entities._validation import decimal_value
from backend.domain.losses.exceptions import LossInvariantError


@dataclass(frozen=True)
class LossApprovalPolicy:
    """Config-driven approval threshold; callers must provide the setting."""

    approval_limit: Decimal

    def __post_init__(self) -> None:
        value = decimal_value(self.approval_limit, "approval_limit")
        if value < 0:
            raise LossInvariantError("El límite de aprobación no puede ser negativo")
        object.__setattr__(self, "approval_limit", value)

    def requires_approval(self, net_loss_value) -> bool:
        return decimal_value(net_loss_value, "net_loss_value") > self.approval_limit
