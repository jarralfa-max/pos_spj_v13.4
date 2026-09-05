# tests/test_handoff_request_entity.py — WA-16
from __future__ import annotations

import pytest

from domain.whatsapp.entities.handoff_request import (
    HandoffRequest,
    HandoffRequestAlreadyFinalizedError,
)
from domain.whatsapp.enums import HandoffStatus


def _open(**overrides):
    kwargs = dict(conversation_id="conv-1", reason="No entendió el pedido")
    kwargs.update(overrides)
    return HandoffRequest.open(**kwargs)


class TestOpen:
    def test_starts_open(self):
        request = _open()
        assert request.status == HandoffStatus.OPEN
        assert request.assigned_to_phone is None

    def test_requires_conversation_id(self):
        with pytest.raises(ValueError):
            _open(conversation_id="")

    def test_requires_reason(self):
        with pytest.raises(ValueError):
            _open(reason="   ")


class TestTransitions:
    def test_assign_sets_staff_phone_and_status(self):
        request = _open()
        request.assign("+525500000000")
        assert request.status == HandoffStatus.ASSIGNED
        assert request.assigned_to_phone == "+525500000000"

    def test_resolve_sets_resolved_at(self):
        request = _open()
        request.resolve()
        assert request.status == HandoffStatus.RESOLVED
        assert request.resolved_at is not None
        assert request.is_terminal()

    def test_cancel_is_terminal(self):
        request = _open()
        request.cancel()
        assert request.status == HandoffStatus.CANCELLED
        assert request.is_terminal()

    def test_cannot_assign_a_resolved_request(self):
        request = _open()
        request.resolve()
        with pytest.raises(HandoffRequestAlreadyFinalizedError):
            request.assign("+525500000000")
