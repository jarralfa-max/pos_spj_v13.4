"""INV-8 — variable weight (catch weight): VOs, policy, scale gateway, capture."""

from decimal import Decimal

import pytest

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.services.weight_capture_service import (
    WeightCaptureService,
)
from backend.domain.inventory.enums import WeightCaptureSource
from backend.domain.inventory.exceptions import (
    InvalidCatchWeightError,
    InventoryPermissionDeniedError,
    ManualWeightAuthorizationRequiredError,
    SegregationOfDutiesError,
)
from backend.domain.inventory.policies.catch_weight_policy import CatchWeightPolicy
from backend.domain.inventory.value_objects.catch_weight import (
    CatchWeightPosition,
    WeightReading,
)
from backend.infrastructure.hardware.scale_gateway import (
    ManualScaleGateway,
    StubScaleGateway,
)


class TestWeightReading:
    def test_net_is_gross_minus_tare(self):
        r = WeightReading(gross=Decimal("60.5"), tare=Decimal("2.5"))
        assert r.net == Decimal("58.0") and r.captured_at

    def test_rejects_float(self):
        with pytest.raises(InvalidCatchWeightError):
            WeightReading(gross=60.5)

    def test_tare_cannot_exceed_gross(self):
        with pytest.raises(InvalidCatchWeightError):
            WeightReading(gross=Decimal("2"), tare=Decimal("3"))


class TestCatchWeightPosition:
    def test_average(self):
        pos = CatchWeightPosition(pieces=Decimal("25"), weight=Decimal("58.750"))
        assert pos.average_weight == Decimal("2.35")

    def test_zero_pieces_no_average(self):
        assert CatchWeightPosition(pieces=Decimal("0"), weight=Decimal("0")).average_weight is None

    def test_rejects_float(self):
        with pytest.raises(InvalidCatchWeightError):
            CatchWeightPosition(pieces=2, weight=5.0)


class TestCatchWeightPolicy:
    def setup_method(self):
        self.pol = CatchWeightPolicy()

    def test_unstable_cannot_auto_add(self):
        with pytest.raises(InvalidCatchWeightError):
            self.pol.enforce_stable_for_auto(
                WeightReading(gross=Decimal("10"), stable=False))

    def test_in_range(self):
        self.pol.enforce_in_range(Decimal("5"), min_weight=Decimal("1"),
                                  max_weight=Decimal("10"))
        with pytest.raises(InvalidCatchWeightError):
            self.pol.enforce_in_range(Decimal("20"), max_weight=Decimal("10"))

    def test_average_tolerance(self):
        self.pol.enforce_average_within_tolerance(
            pieces=Decimal("10"), total_weight=Decimal("21"),
            expected_avg=Decimal("2"), tolerance_pct=Decimal("10"))  # avg 2.1 within 10%
        with pytest.raises(InvalidCatchWeightError):
            self.pol.enforce_average_within_tolerance(
                pieces=Decimal("10"), total_weight=Decimal("30"),
                expected_avg=Decimal("2"), tolerance_pct=Decimal("10"))  # avg 3.0

    def test_manual_capture_out_of_range_needs_authorization(self):
        self.pol.enforce_manual_capture(Decimal("5"), min_weight=Decimal("1"),
                                        max_weight=Decimal("10"))  # in range ok
        with pytest.raises(ManualWeightAuthorizationRequiredError):
            self.pol.enforce_manual_capture(Decimal("20"), max_weight=Decimal("10"))
        self.pol.enforce_manual_capture(Decimal("20"), max_weight=Decimal("10"),
                                        authorized=True)  # authorized ok


class TestScaleGateway:
    def test_stub_replays_and_empties(self):
        g = StubScaleGateway([WeightReading(gross=Decimal("10"))])
        assert g.read().net == Decimal("10")
        with pytest.raises(InvalidCatchWeightError):
            g.read()

    def test_manual_gateway_source(self):
        r = ManualScaleGateway(gross=Decimal("7"), tare=Decimal("1")).read()
        assert r.net == Decimal("6") and r.source is WeightCaptureSource.MANUAL_AUTHORIZED


class TestWeightCaptureService:
    def setup_method(self):
        self.svc = WeightCaptureService()

    def test_capture_from_scale_ok(self):
        g = StubScaleGateway([WeightReading(gross=Decimal("58.75"), stable=True)])
        r = self.svc.capture_from_scale(g, actor_user_id="u1",
                                        min_weight=Decimal("1"), max_weight=Decimal("100"))
        assert r.net == Decimal("58.75")

    def test_capture_from_scale_unstable_rejected(self):
        g = StubScaleGateway([WeightReading(gross=Decimal("58"), stable=False)])
        with pytest.raises(InvalidCatchWeightError):
            self.svc.capture_from_scale(g, actor_user_id="u1")

    def test_capture_from_scale_out_of_range_rejected(self):
        g = StubScaleGateway([WeightReading(gross=Decimal("200"), stable=True)])
        with pytest.raises(InvalidCatchWeightError):
            self.svc.capture_from_scale(g, actor_user_id="u1", max_weight=Decimal("100"))

    def test_capture_from_scale_permission_denied(self):
        class Deny:
            def has_permission(self, u, p):
                return False
        svc = WeightCaptureService(InventoryAuthorizationPolicy(Deny()))
        g = StubScaleGateway([WeightReading(gross=Decimal("10"), stable=True)])
        with pytest.raises(InventoryPermissionDeniedError):
            svc.capture_from_scale(g, actor_user_id="u1")

    def test_capture_manual_in_range_ok(self):
        r = self.svc.capture_manual(gross=Decimal("5"), actor_user_id="u1",
                                    min_weight=Decimal("1"), max_weight=Decimal("10"))
        assert r.net == Decimal("5")

    def test_capture_manual_out_of_range_needs_distinct_authorizer(self):
        with pytest.raises(InventoryPermissionDeniedError):
            self.svc.capture_manual(gross=Decimal("20"), actor_user_id="u1",
                                    max_weight=Decimal("10"))  # no authorizer
        with pytest.raises(SegregationOfDutiesError):
            self.svc.capture_manual(gross=Decimal("20"), actor_user_id="u1",
                                    authorizer_user_id="u1", max_weight=Decimal("10"))
        r = self.svc.capture_manual(gross=Decimal("20"), actor_user_id="u1",
                                    authorizer_user_id="boss", max_weight=Decimal("10"))
        assert r.net == Decimal("20")
