"""SET-8 — PrinterProfilePolicy: printer-specific DeviceProfile
validation (§23). Pure domain — no DB.
"""

from __future__ import annotations

import pytest

from backend.domain.device_management.entities.device_profile import DeviceProfile
from backend.domain.device_management.enums import (
    PRINTER_DEVICE_TYPES,
    ConnectionType,
    DeviceType,
    PaperProfileType,
    PrinterProtocol,
)
from backend.domain.device_management.exceptions import InvalidPrinterProfileError
from backend.domain.device_management.policies.printer_profile_policy import assert_valid_printer_profile
from backend.domain.device_management.value_objects.connection_profile import ConnectionProfile

_USB = ConnectionProfile.create(ConnectionType.USB)


def _profile(**overrides) -> DeviceProfile:
    kwargs = dict(name="Epson TM-T20III", device_type=DeviceType.THERMAL_PRINTER, connection_profile=_USB)
    kwargs.update(overrides)
    return DeviceProfile.create(**kwargs)


class TestDeviceTypeGate:
    def test_every_printer_device_type_passes(self):
        for device_type in PRINTER_DEVICE_TYPES:
            assert_valid_printer_profile(_profile(device_type=device_type))

    @pytest.mark.parametrize("device_type", [
        t for t in DeviceType if t not in PRINTER_DEVICE_TYPES
    ])
    def test_non_printer_device_types_are_rejected(self, device_type):
        with pytest.raises(InvalidPrinterProfileError):
            assert_valid_printer_profile(_profile(device_type=device_type))


class TestPaperProfile:
    def test_none_is_allowed(self):
        assert_valid_printer_profile(_profile(paper_profile=None))

    def test_every_canonical_paper_profile_is_accepted(self):
        for paper in PaperProfileType:
            assert_valid_printer_profile(_profile(paper_profile=paper.value))

    def test_non_canonical_paper_profile_rejected(self):
        with pytest.raises(InvalidPrinterProfileError):
            assert_valid_printer_profile(_profile(paper_profile="LEGAL_SIZE"))


class TestProtocol:
    def test_empty_protocol_is_allowed(self):
        assert_valid_printer_profile(_profile(protocol=""))

    def test_every_canonical_protocol_is_accepted(self):
        for protocol in PrinterProtocol:
            assert_valid_printer_profile(_profile(protocol=protocol.value))

    def test_non_canonical_protocol_rejected(self):
        # §23: "No asumir que toda impresora es ESC/POS" — this also
        # means an unrecognized protocol must not be silently accepted
        # as if it were.
        with pytest.raises(InvalidPrinterProfileError):
            assert_valid_printer_profile(_profile(protocol="TELEPATHY"))
