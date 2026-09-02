# tests/test_domain_whatsapp_identity.py — WA-2
"""WhatsAppIdentity."""
from __future__ import annotations

import pytest

from domain.whatsapp.entities.identity import WhatsAppIdentity
from domain.whatsapp.enums import IdentityStatus


def _identity(**overrides):
    defaults = dict(wa_id="wa-ext-1", raw_phone="5512345678")
    defaults.update(overrides)
    return WhatsAppIdentity.create(**defaults)


class TestWhatsAppIdentityCreate:
    def test_starts_unresolved(self):
        assert _identity().identity_status == IdentityStatus.UNRESOLVED

    def test_id_is_valid_uuidv7(self):
        from backend.shared.ids import is_uuidv7
        assert is_uuidv7(_identity().id)

    def test_phone_not_used_as_id(self):
        identity = _identity()
        assert identity.id != identity.normalized_phone.value

    def test_normalizes_phone(self):
        identity = _identity(raw_phone="5512345678")
        assert identity.normalized_phone.value == "+525512345678"

    def test_rejects_empty_wa_id(self):
        with pytest.raises(ValueError):
            _identity(wa_id="")

    def test_no_customer_linked_initially(self):
        assert _identity().customer_id is None


class TestWhatsAppIdentityLifecycle:
    def test_link_to_customer_resolves(self):
        identity = _identity()
        identity.link_to_customer("cust-1")
        assert identity.customer_id == "cust-1"
        assert identity.identity_status == IdentityStatus.RESOLVED

    def test_link_requires_customer_id(self):
        with pytest.raises(ValueError):
            _identity().link_to_customer("")

    def test_verify_requires_linked_customer(self):
        with pytest.raises(ValueError):
            _identity().verify()

    def test_verify_after_link_succeeds(self):
        identity = _identity()
        identity.link_to_customer("cust-1")
        identity.verify()
        assert identity.identity_status == IdentityStatus.VERIFIED

    def test_block_sets_blocked_and_timestamp(self):
        identity = _identity()
        identity.block()
        assert identity.identity_status == IdentityStatus.BLOCKED
        assert identity.blocked_at is not None
        assert identity.is_blocked() is True

    def test_unblock_without_customer_returns_to_unresolved(self):
        identity = _identity()
        identity.block()
        identity.unblock()
        assert identity.identity_status == IdentityStatus.UNRESOLVED
        assert identity.blocked_at is None

    def test_unblock_with_customer_returns_to_resolved(self):
        identity = _identity()
        identity.link_to_customer("cust-1")
        identity.block()
        identity.unblock()
        assert identity.identity_status == IdentityStatus.RESOLVED

    def test_unblock_when_not_blocked_is_noop(self):
        identity = _identity()
        identity.unblock()
        assert identity.identity_status == IdentityStatus.UNRESOLVED

    def test_touch_updates_last_seen(self):
        identity = _identity()
        before = identity.last_seen_at
        identity.touch()
        assert identity.last_seen_at >= before

    def test_merge_into_marks_merged(self):
        identity = _identity()
        identity.merge_into("other-id")
        assert identity.identity_status == IdentityStatus.MERGED

    def test_merge_into_self_rejected(self):
        identity = _identity()
        with pytest.raises(ValueError):
            identity.merge_into(identity.id)

    def test_merge_into_requires_target(self):
        with pytest.raises(ValueError):
            _identity().merge_into("")
