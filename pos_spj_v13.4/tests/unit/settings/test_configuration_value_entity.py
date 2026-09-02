"""SET-2 — ConfigurationValue entity lifecycle (§10). Pure domain — no DB."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.domain.settings.enums import ConfigurationValueStatus, ScopeType
from backend.domain.settings.entities.configuration_value import ConfigurationValue
from backend.domain.settings.exceptions import (
    ConfigurationActivationNotAllowedError,
    ConfigurationInvalidValueError,
    ConfigurationRollbackNotAllowedError,
)
from backend.domain.settings.value_objects.configuration_scope import ConfigurationScope
from backend.domain.settings.value_objects.effective_period import EffectivePeriod
from backend.shared.ids import is_uuidv7, new_uuid

_NOW = datetime.now(timezone.utc)


def _value(*, effective_from=None, effective_to=None, **overrides) -> ConfigurationValue:
    kwargs = dict(
        definition_id=new_uuid(),
        scope=ConfigurationScope.create(ScopeType.BRANCH, new_uuid()),
        value=Decimal("7.5"),
        effective_period=EffectivePeriod.create(effective_from or _NOW - timedelta(days=1), effective_to),
        created_by_user_id="creator-1",
    )
    kwargs.update(overrides)
    return ConfigurationValue.create(**kwargs)


class TestCreate:
    def test_mints_uuidv7_and_starts_draft(self):
        value = _value()
        assert is_uuidv7(value.id)
        assert value.status is ConfigurationValueStatus.DRAFT
        assert value.version.value == 1

    def test_requires_definition_id(self):
        with pytest.raises(ConfigurationInvalidValueError):
            _value(definition_id="")


class TestApprovalFlow:
    def test_full_happy_path(self):
        value = _value()
        value.submit_for_approval()
        assert value.status is ConfigurationValueStatus.PENDING_APPROVAL
        value.approve("approver-1")
        assert value.status is ConfigurationValueStatus.APPROVED
        assert value.approved_by_user_id == "approver-1"
        value.activate("activator-1", at=_NOW)
        assert value.status is ConfigurationValueStatus.ACTIVE
        assert value.activated_by_user_id == "activator-1"

    def test_cannot_approve_without_submitting_first(self):
        value = _value()
        with pytest.raises(ConfigurationActivationNotAllowedError):
            value.approve("approver-1")

    def test_reject_requires_reason(self):
        value = _value()
        value.submit_for_approval()
        with pytest.raises(ConfigurationInvalidValueError):
            value.reject("   ")

    def test_reject_from_pending_approval(self):
        value = _value()
        value.submit_for_approval()
        value.reject("no cumple política")
        assert value.status is ConfigurationValueStatus.REJECTED
        assert value.reason == "no cumple política"

    def test_auto_approve_skips_pending(self):
        value = _value()
        value.auto_approve("approver-1")
        assert value.status is ConfigurationValueStatus.APPROVED

    def test_auto_approve_requires_draft(self):
        value = _value()
        value.submit_for_approval()
        with pytest.raises(ConfigurationActivationNotAllowedError):
            value.auto_approve("approver-1")


class TestCancellation:
    @pytest.mark.parametrize("prepare", [
        lambda v: None,
        lambda v: v.submit_for_approval(),
        lambda v: (v.submit_for_approval(), v.approve("a1")),
    ])
    def test_cancel_from_pre_active_states(self, prepare):
        value = _value()
        prepare(value)
        value.cancel()
        assert value.status is ConfigurationValueStatus.CANCELLED

    def test_cannot_cancel_active_value(self):
        value = _value()
        value.auto_approve("a1")
        value.activate("a1", at=_NOW)
        with pytest.raises(ConfigurationActivationNotAllowedError):
            value.cancel()


class TestActivation:
    def test_activate_requires_approved_or_scheduled(self):
        value = _value()
        with pytest.raises(ConfigurationActivationNotAllowedError):
            value.activate("a1", at=_NOW)

    def test_activate_lands_on_scheduled_for_future_period(self):
        value = _value(effective_from=_NOW + timedelta(days=5))
        value.auto_approve("a1")
        value.activate("a1", at=_NOW)
        assert value.status is ConfigurationValueStatus.SCHEDULED

    def test_activate_again_moves_scheduled_to_active_once_due(self):
        value = _value(effective_from=_NOW + timedelta(days=5))
        value.auto_approve("a1")
        value.activate("a1", at=_NOW)
        assert value.status is ConfigurationValueStatus.SCHEDULED
        value.activate("a1", at=_NOW + timedelta(days=6))
        assert value.status is ConfigurationValueStatus.ACTIVE

    def test_activate_requires_actor(self):
        value = _value()
        value.auto_approve("a1")
        with pytest.raises(ConfigurationInvalidValueError):
            value.activate("", at=_NOW)


class TestExpiry:
    def test_expire_requires_active(self):
        value = _value()
        with pytest.raises(ConfigurationActivationNotAllowedError):
            value.expire(at=_NOW)

    def test_expire_requires_effective_to_reached(self):
        value = _value(effective_to=_NOW + timedelta(days=10))
        value.auto_approve("a1")
        value.activate("a1", at=_NOW)
        with pytest.raises(ConfigurationActivationNotAllowedError):
            value.expire(at=_NOW + timedelta(days=1))

    def test_expire_once_effective_to_reached(self):
        value = _value(effective_to=_NOW + timedelta(days=1))
        value.auto_approve("a1")
        value.activate("a1", at=_NOW)
        value.expire(at=_NOW + timedelta(days=2))
        assert value.status is ConfigurationValueStatus.EXPIRED


class TestRollback:
    def test_only_active_or_expired_can_roll_back(self):
        value = _value()
        with pytest.raises(ConfigurationRollbackNotAllowedError):
            value.mark_rolled_back()

    def test_active_can_roll_back(self):
        value = _value()
        value.auto_approve("a1")
        value.activate("a1", at=_NOW)
        value.mark_rolled_back()
        assert value.status is ConfigurationValueStatus.ROLLED_BACK


class TestNextVersionAndEffectiveness:
    def test_create_next_version_chains_and_increments(self):
        value = _value()
        next_value = value.create_next_version(
            value=Decimal("9.0"), effective_period=EffectivePeriod.create(_NOW),
            created_by_user_id="creator-2", reason="ajuste de política",
        )
        assert next_value.previous_version_id == value.id
        assert next_value.version.value == value.version.value + 1
        assert next_value.status is ConfigurationValueStatus.DRAFT
        assert next_value.id != value.id

    def test_is_effective_only_when_active_and_within_period(self):
        value = _value()
        assert value.is_effective(_NOW) is False  # still DRAFT
        value.auto_approve("a1")
        value.activate("a1", at=_NOW)
        assert value.is_effective(_NOW) is True
        assert value.is_effective(_NOW - timedelta(days=5)) is False
