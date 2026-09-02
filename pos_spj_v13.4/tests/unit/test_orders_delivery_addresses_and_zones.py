"""ORD-7 — OrderAddress, DeliveryZone, DeliveryFeePolicy (§20-22)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.orders_delivery.address import OrderAddress
from backend.domain.orders_delivery.delivery_zone import DeliveryZone
from backend.domain.orders_delivery.enums import GeocodingStatus
from backend.domain.orders_delivery.exceptions import (
    DeliveryZoneNotAvailableError,
    InvalidAddressError,
)
from backend.domain.orders_delivery.policies.delivery_fee_policy import DeliveryFeePolicy
from backend.shared.ids import new_uuid


class TestOrderAddress:
    def test_create_requires_recipient_name(self):
        with pytest.raises(InvalidAddressError):
            OrderAddress.create(
                order_id=new_uuid(), recipient_name="", recipient_phone="555",
                street="Calle 1", exterior_number="10")

    def test_create_requires_phone(self):
        with pytest.raises(InvalidAddressError):
            OrderAddress.create(
                order_id=new_uuid(), recipient_name="Juan", recipient_phone="",
                street="Calle 1", exterior_number="10")

    def test_geocoding_lifecycle(self):
        address = OrderAddress.create(
            order_id=new_uuid(), recipient_name="Juan", recipient_phone="555",
            street="Calle 1", exterior_number="10")
        assert address.geocoding_status == GeocodingStatus.NOT_REQUESTED
        address.mark_geocoded(latitude=19.4, longitude=-99.1)
        assert address.geocoding_status == GeocodingStatus.GEOCODED

    def test_manual_address_is_a_valid_terminal_state(self):
        """§20: geocoding never blocks the order when manual is sufficient."""
        address = OrderAddress.create(
            order_id=new_uuid(), recipient_name="Juan", recipient_phone="555",
            street="Calle 1", exterior_number="10")
        address.mark_manual()
        assert address.geocoding_status == GeocodingStatus.MANUAL

    def test_assign_zone(self):
        address = OrderAddress.create(
            order_id=new_uuid(), recipient_name="Juan", recipient_phone="555",
            street="Calle 1", exterior_number="10")
        zone_id = new_uuid()
        address.assign_zone(zone_id)
        assert address.delivery_zone_id == zone_id


class TestDeliveryZone:
    def test_create_requires_name(self):
        with pytest.raises(InvalidAddressError):
            DeliveryZone.create(branch_id=new_uuid(), name="")

    def test_covers_postal_code(self):
        zone = DeliveryZone.create(
            branch_id=new_uuid(), name="Centro", postal_codes=("06000", "06010"))
        assert zone.covers_postal_code("06000")
        assert not zone.covers_postal_code("99999")

    def test_fee_waived_above_threshold(self):
        zone = DeliveryZone.create(
            branch_id=new_uuid(), name="Centro", delivery_fee=Decimal("50"),
            free_delivery_threshold=Decimal("500"))
        assert zone.fee_for_order_total(Decimal("600")) == Decimal("0")
        assert zone.fee_for_order_total(Decimal("100")) == Decimal("50")

    def test_deactivate(self):
        zone = DeliveryZone.create(branch_id=new_uuid(), name="Centro")
        zone.deactivate()
        assert zone.active is False


class TestDeliveryFeePolicy:
    def test_resolve_zone_finds_matching_active_zone(self):
        zone = DeliveryZone.create(branch_id=new_uuid(), name="Centro", postal_codes=("06000",))
        resolved = DeliveryFeePolicy.resolve_zone([zone], postal_code="06000")
        assert resolved.id == zone.id

    def test_resolve_zone_ignores_inactive_zone(self):
        zone = DeliveryZone.create(branch_id=new_uuid(), name="Centro", postal_codes=("06000",))
        zone.deactivate()
        with pytest.raises(DeliveryZoneNotAvailableError):
            DeliveryFeePolicy.resolve_zone([zone], postal_code="06000")

    def test_resolve_zone_raises_when_no_match(self):
        zone = DeliveryZone.create(branch_id=new_uuid(), name="Centro", postal_codes=("06000",))
        with pytest.raises(DeliveryZoneNotAvailableError):
            DeliveryFeePolicy.resolve_zone([zone], postal_code="99999")

    def test_calculate_fee_enforces_minimum_order(self):
        zone = DeliveryZone.create(
            branch_id=new_uuid(), name="Centro", postal_codes=("06000",),
            minimum_order=Decimal("200"), delivery_fee=Decimal("30"))
        with pytest.raises(DeliveryZoneNotAvailableError):
            DeliveryFeePolicy.calculate_fee(zone, order_subtotal=Decimal("50"))

    def test_calculate_fee_returns_zone_fee(self):
        zone = DeliveryZone.create(
            branch_id=new_uuid(), name="Centro", postal_codes=("06000",),
            minimum_order=Decimal("0"), delivery_fee=Decimal("30"))
        assert DeliveryFeePolicy.calculate_fee(zone, order_subtotal=Decimal("100")) == Decimal("30")
