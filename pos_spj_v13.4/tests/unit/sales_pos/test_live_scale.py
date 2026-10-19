from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from backend.application.sales.scale_reading_service import ScaleReadingService
from backend.domain.inventory.value_objects.catch_weight import WeightReading
from backend.infrastructure.hardware.scale_gateway import StubScaleGateway


def test_stability_zero_tare_and_stale_are_independent_of_cart():
    gateway = StubScaleGateway([WeightReading(Decimal("1.050"), tare=Decimal(".200")) for _ in range(2)])
    service = ScaleReadingService(gateway)
    assert service.poll().status == "UNSTABLE"
    assert "0.850 kg" in service.poll().text
    assert service.accepted_weight(unit="KG") == Decimal(".850")
    gateway.queue(WeightReading(Decimal("0")))
    gateway.queue(WeightReading(Decimal("0")))
    service.poll()
    assert "0.000 kg" in service.poll().text
    old = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
    gateway.queue(WeightReading(Decimal(".850"), captured_at=old))
    assert service.poll().status == "STALE"
    with pytest.raises(ValueError):
        service.accepted_weight(unit="KG")


def test_disconnect_cannot_reuse_last_weight():
    service = ScaleReadingService(StubScaleGateway([WeightReading(Decimal(".85")) for _ in range(2)]))
    service.poll()
    service.poll()
    service.invalidate("DISCONNECTED", "desconectada")
    assert service.current().reading is None
    assert service.current().last_valid.net == Decimal(".85")
    with pytest.raises(ValueError):
        service.accepted_weight(unit="KG")


def test_rhino_usb_uses_p_and_rejects_price_or_malformed_frames():
    from backend.infrastructure.hardware.scale_gateway import RhinoBar8RsScaleGateway
    gateway = RhinoBar8RsScaleGateway(None)
    assert gateway.request == b"P"
    assert gateway._decode(b" 0.850kg\r\n") == (Decimal(".850"), "KG", True)
    assert gateway._decode(b"US,NT, 1.250 kg\r\n")[2] is False
    for invalid in (b"0.850 95.00 80.75", b"NaN kg", b"garbage 0.850 kg", b"1,250 kg"):
        with pytest.raises(ValueError):
            gateway._decode(invalid)


@pytest.mark.parametrize("at,stable", [
    ((datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat(), True),
    (datetime.now().isoformat(), True),
    (datetime.now(timezone.utc).isoformat(), False),
])
def test_capture_rejects_future_naive_or_unstable_readings(at, stable):
    from backend.application.sales.scale_reading_service import LiveScaleState
    state = LiveScaleState("STABLE", WeightReading(Decimal(".85"), stable=stable, captured_at=at))
    with pytest.raises(ValueError):
        ScaleReadingService.validate_capture(state, quantity=Decimal(".85"), unit="KG")


def test_invalidation_discards_an_inflight_sample():
    class Gateway:
        def read(self):
            service.invalidate("DISCONNECTED", "desconectada")
            return WeightReading(Decimal(".85"))
    service = ScaleReadingService(Gateway())
    assert service.poll().status == "DISCONNECTED"
    assert service.current().reading is None
