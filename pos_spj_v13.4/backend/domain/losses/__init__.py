"""Loss management domain primitives."""

from backend.domain.losses.entities import LossCase, LossClassification, LossLine, LossReason
from backend.domain.losses.enums import LossClassificationCode, LossOrigin, LossStatus
from backend.domain.losses.value_objects.authorization_grant import LossAuthorizationGrant

__all__ = [
    "LossAuthorizationGrant", "LossCase", "LossClassification", "LossLine",
    "LossReason", "LossClassificationCode", "LossOrigin", "LossStatus",
]
