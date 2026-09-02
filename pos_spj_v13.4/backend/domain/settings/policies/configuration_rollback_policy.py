"""ConfigurationRollbackPolicy — may this value be rolled back, and what
would the replacement DRAFT look like? (§10, §63).

Rollback never resurrects the old row in place — it marks the current
version ROLLED_BACK and hands the caller (application layer) a fresh
DRAFT `ConfigurationValue` carrying the previous version's value, chained
via `previous_version_id`, ready to go through approval/activation again.
"""

from __future__ import annotations

from backend.domain.settings.exceptions import ConfigurationInvalidValueError, ConfigurationRollbackNotAllowedError
from backend.domain.settings.value_objects.effective_period import EffectivePeriod


def assert_can_roll_back(value) -> None:
    from backend.domain.settings.enums import ConfigurationValueStatus
    if value.status not in (ConfigurationValueStatus.ACTIVE, ConfigurationValueStatus.EXPIRED):
        raise ConfigurationRollbackNotAllowedError(
            f"Solo se puede hacer rollback de valores ACTIVE o EXPIRED, no {value.status.value}"
        )


def build_rollback_draft(current_value, target_value, *, effective_period: EffectivePeriod, requested_by_user_id: str, reason: str):
    """Roll `current_value` back to `target_value`'s content: mark
    `current_value` ROLLED_BACK and return a new DRAFT chained to it,
    carrying `target_value`'s value. Caller persists both."""
    assert_can_roll_back(current_value)
    if not reason.strip():
        raise ConfigurationInvalidValueError("El rollback requiere un motivo auditable")
    current_value.mark_rolled_back()
    return current_value.create_next_version(
        value=target_value.value, effective_period=effective_period,
        created_by_user_id=requested_by_user_id, reason=reason.strip(),
    )
