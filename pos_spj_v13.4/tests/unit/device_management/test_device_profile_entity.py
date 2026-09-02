"""SET-7 — DeviceProfile entity + ConnectionProfile/SerialPortProfile/
NetworkEndpoint/DeviceCapability value objects (§18-19, §23). Pure
domain — no DB.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.device_management.entities.device_profile import DeviceProfile
from backend.domain.device_management.enums import ConnectionType, DeviceCapabilityCode, DeviceType
from backend.domain.device_management.exceptions import DeviceInvalidValueError
from backend.domain.device_management.value_objects.connection_profile import ConnectionProfile
from backend.domain.device_management.value_objects.device_capability import DeviceCapability
from backend.domain.device_management.value_objects.network_endpoint import NetworkEndpoint
from backend.domain.device_management.value_objects.serial_port_profile import SerialPortProfile
from backend.shared.ids import is_uuidv7

_USB_PROFILE = ConnectionProfile.create(ConnectionType.USB)


def _profile(**overrides) -> DeviceProfile:
    kwargs = dict(name="Epson TM-T20III", device_type=DeviceType.THERMAL_PRINTER, connection_profile=_USB_PROFILE)
    kwargs.update(overrides)
    return DeviceProfile.create(**kwargs)


class TestSerialPortProfile:
    def test_requires_port(self):
        with pytest.raises(DeviceInvalidValueError):
            SerialPortProfile.create(port="  ", baud_rate=9600)

    def test_rejects_non_standard_baud_rate(self):
        with pytest.raises(DeviceInvalidValueError):
            SerialPortProfile.create(port="COM3", baud_rate=1234)

    def test_rejects_invalid_parity(self):
        with pytest.raises(DeviceInvalidValueError):
            SerialPortProfile.create(port="COM3", baud_rate=9600, parity="X")

    def test_rejects_float_timeout(self):
        with pytest.raises(DeviceInvalidValueError):
            SerialPortProfile.create(port="COM3", baud_rate=9600, read_timeout_seconds=2.0)

    def test_accepts_valid_profile(self):
        profile = SerialPortProfile.create(port="COM3", baud_rate=9600, read_timeout_seconds=Decimal("1.5"))
        assert profile.port == "COM3"
        assert profile.read_timeout_seconds == Decimal("1.5")


class TestNetworkEndpoint:
    def test_requires_host(self):
        with pytest.raises(DeviceInvalidValueError):
            NetworkEndpoint.create(host="  ", port=9100)

    def test_rejects_out_of_range_port(self):
        with pytest.raises(DeviceInvalidValueError):
            NetworkEndpoint.create(host="10.0.0.1", port=0)
        with pytest.raises(DeviceInvalidValueError):
            NetworkEndpoint.create(host="10.0.0.1", port=70000)

    def test_accepts_valid_endpoint(self):
        endpoint = NetworkEndpoint.create(host="10.0.0.1", port=9100, use_tls=True)
        assert endpoint.use_tls is True


class TestConnectionProfile:
    def test_serial_requires_serial_port(self):
        with pytest.raises(DeviceInvalidValueError):
            ConnectionProfile.create(ConnectionType.SERIAL)

    @pytest.mark.parametrize("connection_type", [ConnectionType.NETWORK, ConnectionType.HTTP, ConnectionType.WEBSOCKET])
    def test_network_addressed_types_require_endpoint(self, connection_type):
        with pytest.raises(DeviceInvalidValueError):
            ConnectionProfile.create(connection_type)

    @pytest.mark.parametrize("connection_type", [ConnectionType.USB, ConnectionType.BLUETOOTH, ConnectionType.SYSTEM, ConnectionType.VIRTUAL])
    def test_bus_types_do_not_require_endpoint_or_serial(self, connection_type):
        profile = ConnectionProfile.create(connection_type)
        assert profile.serial_port is None
        assert profile.network_endpoint is None

    @pytest.mark.parametrize("key", ["password", "api_token", "secret_key", "PRIVATE_KEY", "auth_header", "Credential"])
    def test_rejects_secret_looking_keys(self, key):
        with pytest.raises(DeviceInvalidValueError):
            ConnectionProfile.create(ConnectionType.USB, extra_parameters={key: "x"})

    def test_accepts_non_secret_keys(self):
        profile = ConnectionProfile.create(ConnectionType.USB, extra_parameters={"vendor_id": "04b8", "product_id": "0202"})
        assert profile.extra_parameters == {"vendor_id": "04b8", "product_id": "0202"}

    def test_credential_reference_is_a_name_not_a_secret(self):
        profile = ConnectionProfile.create(ConnectionType.NETWORK, network_endpoint=NetworkEndpoint.create(host="10.0.0.1", port=9100), credential_reference="printer_admin_token")
        assert profile.credential_reference == "printer_admin_token"


class TestDeviceProfileCreate:
    def test_mints_uuidv7(self):
        assert is_uuidv7(_profile().id)

    def test_requires_name(self):
        with pytest.raises(DeviceInvalidValueError):
            _profile(name="   ")

    def test_rejects_non_positive_timeout(self):
        with pytest.raises(DeviceInvalidValueError):
            _profile(timeout_seconds=0)

    def test_rejects_negative_retry_attempts(self):
        with pytest.raises(DeviceInvalidValueError):
            _profile(retry_max_attempts=-1)

    def test_all_device_types_are_constructible(self):
        for device_type in DeviceType:
            assert _profile(device_type=device_type).device_type is device_type


class TestDeviceProfileCapabilities:
    def test_has_capability(self):
        profile = _profile(capabilities=(DeviceCapability.create(DeviceCapabilityCode.CUT),))
        assert profile.has_capability(DeviceCapabilityCode.CUT)
        assert not profile.has_capability(DeviceCapabilityCode.DRAWER_PULSE)

    def test_add_capability(self):
        profile = _profile()
        profile.add_capability(DeviceCapability.create(DeviceCapabilityCode.CUT))
        assert profile.has_capability(DeviceCapabilityCode.CUT)

    def test_add_duplicate_capability_raises(self):
        profile = _profile(capabilities=(DeviceCapability.create(DeviceCapabilityCode.CUT),))
        with pytest.raises(DeviceInvalidValueError):
            profile.add_capability(DeviceCapability.create(DeviceCapabilityCode.CUT))

    def test_remove_capability(self):
        profile = _profile(capabilities=(DeviceCapability.create(DeviceCapabilityCode.CUT),))
        profile.remove_capability(DeviceCapabilityCode.CUT)
        assert not profile.has_capability(DeviceCapabilityCode.CUT)

    def test_remove_missing_capability_raises(self):
        profile = _profile()
        with pytest.raises(DeviceInvalidValueError):
            profile.remove_capability(DeviceCapabilityCode.CUT)

    def test_capability_can_carry_parameters(self):
        capability = DeviceCapability.create(DeviceCapabilityCode.WEIGH, {"max_weight_kg": "30"})
        assert capability.parameters == {"max_weight_kg": "30"}


class TestDeviceProfileBehavior:
    def test_replace_connection_profile(self):
        profile = _profile()
        new_connection = ConnectionProfile.create(ConnectionType.BLUETOOTH)
        profile.replace_connection_profile(new_connection)
        assert profile.connection_profile is new_connection

    def test_activate_deactivate(self):
        profile = _profile()
        profile.deactivate()
        assert profile.active is False
        profile.activate()
        assert profile.active is True
