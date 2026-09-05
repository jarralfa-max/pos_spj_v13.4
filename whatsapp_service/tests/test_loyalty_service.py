# tests/test_loyalty_service.py — WA-15
from __future__ import annotations

import asyncio

import pytest

from application.loyalty_service import LoyaltyService
from domain.whatsapp.erp_ports import LoyaltySummaryRef


class _FakeLoyalty:
    def __init__(self, summary):
        self._summary = summary
        self.calls = []

    async def get_summary(self, customer_id):
        self.calls.append(customer_id)
        return self._summary


class _FakeRoot:
    def __init__(self, loyalty):
        self.loyalty = loyalty


def _run(coro):
    return asyncio.run(coro)


class TestGetSummary:
    def test_delegates_to_loyalty_client_with_customer_external_id(self):
        summary = LoyaltySummaryRef(customer_id="cliente-1", enrolled=True, points=100, tier="Plata", visits=5)
        loyalty = _FakeLoyalty(summary)
        service = LoyaltyService(_FakeRoot(loyalty))

        result = _run(service.get_summary(customer_external_id="cliente-1"))

        assert result is summary
        assert loyalty.calls == ["cliente-1"]
