# tests/test_delivery_request_entity.py — WA-13
from __future__ import annotations

import pytest

from domain.whatsapp.entities.delivery_request import (
    DeliveryRequest,
    DeliveryRequestAlreadyFinalizedError,
)
from domain.whatsapp.enums import DeliveryRequestStatus


def _start(**overrides):
    kwargs = dict(
        conversation_id="conv-1", order_external_id="order-1", address="Av. Siempre Viva 123",
    )
    kwargs.update(overrides)
    return DeliveryRequest.start(**kwargs)


class TestStart:
    def test_starts_in_requested_status(self):
        request = _start()
        assert request.status == DeliveryRequestStatus.REQUESTED
        assert request.failure_reason is None

    def test_requires_conversation_id(self):
        with pytest.raises(ValueError):
            _start(conversation_id="")

    def test_requires_order_external_id(self):
        with pytest.raises(ValueError):
            _start(order_external_id="")

    def test_requires_non_empty_address(self):
        with pytest.raises(ValueError):
            _start(address="   ")

    def test_strips_address(self):
        request = _start(address="  Av. Siempre Viva 123  ")
        assert request.address == "Av. Siempre Viva 123"


class TestTransitions:
    def test_mark_scheduled(self):
        request = _start()
        request.mark_scheduled()
        assert request.status == DeliveryRequestStatus.SCHEDULED
        assert request.is_terminal()

    def test_mark_failed_records_reason(self):
        request = _start()
        request.mark_failed("El ERP no respondió")
        assert request.status == DeliveryRequestStatus.FAILED
        assert request.failure_reason == "El ERP no respondió"
        assert request.is_terminal()

    def test_cannot_re_resolve_a_scheduled_request(self):
        request = _start()
        request.mark_scheduled()
        with pytest.raises(DeliveryRequestAlreadyFinalizedError):
            request.mark_scheduled()
        with pytest.raises(DeliveryRequestAlreadyFinalizedError):
            request.mark_failed("otro motivo")

    def test_cannot_re_resolve_a_failed_request(self):
        request = _start()
        request.mark_failed("motivo")
        with pytest.raises(DeliveryRequestAlreadyFinalizedError):
            request.mark_scheduled()
