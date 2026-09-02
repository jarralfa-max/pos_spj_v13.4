"""SET-9 — ScaleProfilePolicy + ReaderProfilePolicy (§22, "puertos" and
"protocolos" applied through the existing SerialPortProfile/DeviceProfile
from SET-7). Pure domain — no DB.
"""

from __future__ import annotations

import pytest

from backend.domain.device_management.entities.device_profile import DeviceProfile
from backend.domain.device_management.enums import (
    READER_DEVICE_TYPES,
    SCALE_DEVICE_TYPES,
    ConnectionType,
    DeviceCapabilityCode,
    DeviceType,
    ScaleProtocol,
)
from backend.domain.device_management.exceptions import InvalidReaderProfileError, InvalidScaleProfileError
from backend.domain.device_management.policies.reader_profile_policy import assert_valid_reader_profile
from backend.domain.device_management.policies.scale_profile_policy import assert_valid_scale_profile
from backend.domain.device_management.value_objects.connection_profile import ConnectionProfile
from backend.domain.device_management.value_objects.device_capability import DeviceCapability
from backend.domain.device_management.value_objects.serial_port_profile import SerialPortProfile

_USB = ConnectionProfile.create(ConnectionType.USB)


def _scale_profile(**overrides) -> DeviceProfile:
    kwargs = dict(
        name="Toledo 8217", device_type=DeviceType.SCALE, connection_profile=_USB,
        capabilities=(DeviceCapability.create(DeviceCapabilityCode.WEIGH),),
    )
    kwargs.update(overrides)
    return DeviceProfile.create(**kwargs)


def _reader_profile(**overrides) -> DeviceProfile:
    kwargs = dict(
        name="Honeywell 1900", device_type=DeviceType.BARCODE_SCANNER, connection_profile=_USB,
        capabilities=(DeviceCapability.create(DeviceCapabilityCode.SCAN_1D),),
    )
    kwargs.update(overrides)
    return DeviceProfile.create(**kwargs)


class TestScaleProfilePolicy:
    def test_valid_scale_profile_passes(self):
        assert_valid_scale_profile(_scale_profile())

    def test_uses_serial_port_profile_for_ports_baud_parity_bits(self):
        # §22 "puertos": reuses SET-7's SerialPortProfile rather than a
        # new scale-specific VO.
        profile = _scale_profile(
            connection_profile=ConnectionProfile.create(
                ConnectionType.SERIAL,
                serial_port=SerialPortProfile.create(port="COM4", baud_rate=4800, parity="E", data_bits=7),
            ),
        )
        assert_valid_scale_profile(profile)
        assert profile.connection_profile.serial_port.baud_rate == 4800

    @pytest.mark.parametrize("device_type", [t for t in DeviceType if t not in SCALE_DEVICE_TYPES])
    def test_non_scale_device_types_rejected(self, device_type):
        with pytest.raises(InvalidScaleProfileError):
            assert_valid_scale_profile(_scale_profile(device_type=device_type))

    def test_every_canonical_scale_protocol_accepted(self):
        for protocol in ScaleProtocol:
            assert_valid_scale_profile(_scale_profile(protocol=protocol.value))

    def test_non_canonical_protocol_rejected(self):
        with pytest.raises(InvalidScaleProfileError):
            assert_valid_scale_profile(_scale_profile(protocol="MORSE_CODE"))

    def test_missing_weigh_capability_rejected(self):
        profile = DeviceProfile.create(name="Sin WEIGH", device_type=DeviceType.SCALE, connection_profile=_USB)
        with pytest.raises(InvalidScaleProfileError):
            assert_valid_scale_profile(profile)


class TestReaderProfilePolicy:
    def test_valid_barcode_scanner_passes(self):
        assert_valid_reader_profile(_reader_profile())

    def test_valid_qr_scanner_passes(self):
        profile = _reader_profile(
            device_type=DeviceType.QR_SCANNER,
            capabilities=(DeviceCapability.create(DeviceCapabilityCode.SCAN_2D),),
        )
        assert_valid_reader_profile(profile)

    @pytest.mark.parametrize("device_type", [t for t in DeviceType if t not in READER_DEVICE_TYPES])
    def test_non_reader_device_types_rejected(self, device_type):
        with pytest.raises(InvalidReaderProfileError):
            assert_valid_reader_profile(_reader_profile(device_type=device_type))

    def test_barcode_scanner_without_scan_1d_rejected(self):
        profile = DeviceProfile.create(name="Sin SCAN_1D", device_type=DeviceType.BARCODE_SCANNER, connection_profile=_USB)
        with pytest.raises(InvalidReaderProfileError):
            assert_valid_reader_profile(profile)

    def test_qr_scanner_with_only_scan_1d_is_not_enough(self):
        # A barcode-only capability doesn't satisfy a QR reader's
        # requirement — the two scan capabilities are not interchangeable.
        profile = DeviceProfile.create(
            name="Solo 1D", device_type=DeviceType.QR_SCANNER, connection_profile=_USB,
            capabilities=(DeviceCapability.create(DeviceCapabilityCode.SCAN_1D),),
        )
        with pytest.raises(InvalidReaderProfileError):
            assert_valid_reader_profile(profile)
