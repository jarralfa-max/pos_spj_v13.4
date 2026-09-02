"""SET-14 cutover — NetworkLabelPrintGateway: the first real
`InventoryPrintGateway` implementation, against a real (in-memory) SQLite
schema combining Inventory (INV-26) with the born-clean Device
Management/Document Output schema. `PrintTransport.send` is monkeypatched
to capture the resolved (transport, destination, baud) rather than
opening a real socket/serial port — no physical printer is available in
this environment; what's verified here is that routing/rendering/delivery
wiring is correct, the same boundary `core/ticket_escpos_renderer.py`
already operates under for tickets.
"""

from __future__ import annotations

import pytest

from backend.application.inventory.labels.gateway import PrintDeliveryError
from backend.application.inventory.labels.print_service import InventoryLabelPrintService
from backend.application.inventory.labels.renderers import render_lot_label
from backend.domain.device_management.entities.device import Device
from backend.domain.device_management.entities.device_profile import DeviceProfile
from backend.domain.device_management.entities.print_route import PrintRoute
from backend.domain.device_management.enums import ConnectionType, DeviceType
from backend.domain.device_management.value_objects.connection_profile import ConnectionProfile
from backend.domain.device_management.value_objects.network_endpoint import NetworkEndpoint
from backend.domain.device_management.value_objects.serial_port_profile import SerialPortProfile
from backend.domain.inventory.enums import LabelFormat
from backend.infrastructure.db.repositories.device_management.device_profile_repository import (
    SqliteDeviceProfileRepository,
)
from backend.infrastructure.db.repositories.device_management.device_repository import SqliteDeviceRepository
from backend.infrastructure.db.repositories.device_management.print_route_repository import (
    SqlitePrintRouteRepository,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.infrastructure.hardware.label_rendering.network_label_gateway import NetworkLabelPrintGateway
from backend.shared.ids import new_uuid
from core.services import printer_service
from tests.integration._born_clean_db import make_db


@pytest.fixture
def conn():
    connection = make_db()
    create_inventory_schema(connection)
    connection.commit()
    yield connection
    connection.close()


def _existing_branch_id(conn) -> str:
    branch_id = new_uuid()
    conn.execute("INSERT INTO sucursales (id, nombre) VALUES (?, ?)", (branch_id, "Sucursal de prueba"))
    return branch_id


def _network_label_printer(conn, *, host="10.0.0.50", port=9100) -> Device:
    branch_id = _existing_branch_id(conn)
    profile = DeviceProfile.create(
        name="Zebra ZT230", device_type=DeviceType.LABEL_PRINTER,
        connection_profile=ConnectionProfile.create(
            ConnectionType.NETWORK, network_endpoint=NetworkEndpoint.create(host=host, port=port)),
    )
    SqliteDeviceProfileRepository(conn).save(profile)
    device = Device.create(branch_id=branch_id, profile_id=profile.id, code=f"LBL-{new_uuid()}", name="Zebra")
    SqliteDeviceRepository(conn).save(device)
    conn.commit()
    return device


def _serial_label_printer(conn, *, port="COM4", baud_rate=19200) -> Device:
    branch_id = _existing_branch_id(conn)
    profile = DeviceProfile.create(
        name="TSC TE244", device_type=DeviceType.LABEL_PRINTER,
        connection_profile=ConnectionProfile.create(
            ConnectionType.SERIAL, serial_port=SerialPortProfile.create(port=port, baud_rate=baud_rate)),
    )
    SqliteDeviceProfileRepository(conn).save(profile)
    device = Device.create(branch_id=branch_id, profile_id=profile.id, code=f"LBL-{new_uuid()}", name="TSC")
    SqliteDeviceRepository(conn).save(device)
    conn.commit()
    return device


def _configure_route(conn, device: Device, document_type: str = "LOT_LABEL") -> None:
    route = PrintRoute.create(document_type=document_type, primary_device_id=device.id)
    SqlitePrintRouteRepository(conn).save(route)
    conn.commit()


def _label_document():
    return render_lot_label(product_id="p1", product_name="Bistec", lot_code="L-01", lot_id="lot1")


class TestResolutionAndDelivery:
    def test_no_route_configured_raises_print_delivery_error(self, conn):
        gateway = NetworkLabelPrintGateway(conn)
        with pytest.raises(PrintDeliveryError):
            gateway.print(document=_label_document(), printer_ref="default", label_format=LabelFormat.ZPL, copies=1)

    def test_routes_to_network_device_and_sends_over_tcp(self, conn, monkeypatch):
        device = _network_label_printer(conn, host="10.0.0.50", port=9100)
        _configure_route(conn, device)
        captured = {}

        def _fake_send(data, transport, destination, baud=9600):
            captured["data"] = data
            captured["transport"] = transport
            captured["destination"] = destination
            captured["baud"] = baud
            return True

        monkeypatch.setattr(printer_service.PrintTransport, "send", staticmethod(_fake_send))
        gateway = NetworkLabelPrintGateway(conn)
        gateway.print(document=_label_document(), printer_ref="default", label_format=LabelFormat.ZPL, copies=1)

        assert captured["transport"] == printer_service.TransportType.NETWORK
        assert captured["destination"] == "10.0.0.50:9100"
        assert captured["data"].startswith(b"^XA")

    def test_routes_to_serial_device_with_its_real_baud_rate(self, conn, monkeypatch):
        device = _serial_label_printer(conn, port="COM4", baud_rate=19200)
        _configure_route(conn, device)
        captured = {}

        def _fake_send(data, transport, destination, baud=9600):
            captured.update(transport=transport, destination=destination, baud=baud)
            return True

        monkeypatch.setattr(printer_service.PrintTransport, "send", staticmethod(_fake_send))
        gateway = NetworkLabelPrintGateway(conn)
        gateway.print(document=_label_document(), printer_ref="default", label_format=LabelFormat.ZPL, copies=1)

        assert captured["transport"] == printer_service.TransportType.SERIAL
        assert captured["destination"] == "COM4"
        assert captured["baud"] == 19200

    def test_explicit_device_code_override_skips_routing(self, conn, monkeypatch):
        routed = _network_label_printer(conn, host="10.0.0.50", port=9100)
        _configure_route(conn, routed)
        override = _network_label_printer(conn, host="10.0.0.99", port=9100)
        captured = {}
        monkeypatch.setattr(
            printer_service.PrintTransport, "send",
            staticmethod(lambda data, transport, destination, baud=9600: captured.setdefault("dest", destination) or True),
        )
        gateway = NetworkLabelPrintGateway(conn)
        gateway.print(
            document=_label_document(), printer_ref=override.code, label_format=LabelFormat.ZPL, copies=1)
        assert captured["dest"] == "10.0.0.99:9100"

    def test_unknown_explicit_device_code_raises(self, conn):
        gateway = NetworkLabelPrintGateway(conn)
        with pytest.raises(PrintDeliveryError):
            gateway.print(
                document=_label_document(), printer_ref="NOPE-1", label_format=LabelFormat.ZPL, copies=1)

    def test_inactive_device_via_route_raises_no_available_printer(self, conn):
        device = _network_label_printer(conn)
        device.enter_maintenance()
        SqliteDeviceRepository(conn).save(device)
        conn.commit()
        _configure_route(conn, device)
        gateway = NetworkLabelPrintGateway(conn)
        with pytest.raises(PrintDeliveryError):
            gateway.print(document=_label_document(), printer_ref="default", label_format=LabelFormat.ZPL, copies=1)

    def test_transport_failure_is_wrapped_as_print_delivery_error(self, conn, monkeypatch):
        device = _network_label_printer(conn)
        _configure_route(conn, device)

        def _raise(*a, **kw):
            raise OSError("connection refused")

        monkeypatch.setattr(printer_service.PrintTransport, "send", staticmethod(_raise))
        gateway = NetworkLabelPrintGateway(conn)
        with pytest.raises(PrintDeliveryError):
            gateway.print(document=_label_document(), printer_ref="default", label_format=LabelFormat.ZPL, copies=1)

    def test_transport_returning_false_is_a_print_delivery_error(self, conn, monkeypatch):
        device = _network_label_printer(conn)
        _configure_route(conn, device)
        monkeypatch.setattr(
            printer_service.PrintTransport, "send",
            staticmethod(lambda *a, **kw: False),
        )
        gateway = NetworkLabelPrintGateway(conn)
        with pytest.raises(PrintDeliveryError):
            gateway.print(document=_label_document(), printer_ref="default", label_format=LabelFormat.ZPL, copies=1)

    def test_unsupported_connection_type_raises(self, conn):
        branch_id = _existing_branch_id(conn)
        profile = DeviceProfile.create(
            name="Impresora Bluetooth", device_type=DeviceType.LABEL_PRINTER,
            connection_profile=ConnectionProfile.create(ConnectionType.BLUETOOTH),
        )
        SqliteDeviceProfileRepository(conn).save(profile)
        device = Device.create(branch_id=branch_id, profile_id=profile.id, code="LBL-BT", name="BT")
        SqliteDeviceRepository(conn).save(device)
        conn.commit()
        _configure_route(conn, device)

        gateway = NetworkLabelPrintGateway(conn)
        with pytest.raises(PrintDeliveryError):
            gateway.print(document=_label_document(), printer_ref="default", label_format=LabelFormat.ZPL, copies=1)

    def test_unsupported_label_format_raises(self, conn):
        device = _network_label_printer(conn)
        _configure_route(conn, device)
        gateway = NetworkLabelPrintGateway(conn)
        with pytest.raises(PrintDeliveryError):
            gateway.print(document=_label_document(), printer_ref="default", label_format="BOGUS", copies=1)


class TestThroughInventoryLabelPrintService:
    """End-to-end through the same entry point the live composition root
    calls — confirms the wiring, not just the gateway in isolation."""

    def test_configured_route_prints_successfully_and_audits(self, conn, monkeypatch):
        device = _network_label_printer(conn)
        _configure_route(conn, device)
        monkeypatch.setattr(
            printer_service.PrintTransport, "send", staticmethod(lambda *a, **kw: True))

        service = InventoryLabelPrintService(conn, gateway=NetworkLabelPrintGateway(conn))
        result = service.print_label(_label_document(), actor_user_id="u1")

        assert result.success is True
        row = conn.execute(
            "SELECT label_type FROM inventory_label_print_log WHERE id=?", (result.entity_id,)).fetchone()
        assert row["label_type"] == "LOT"

    def test_unconfigured_route_fails_cleanly_and_audits_the_failure(self, conn):
        service = InventoryLabelPrintService(conn, gateway=NetworkLabelPrintGateway(conn))
        result = service.print_label(_label_document(), actor_user_id="u1")

        assert result.success is False
        assert result.error_code == "PRINT_DELIVERY_FAILED"
        row = conn.execute(
            "SELECT reason FROM inventory_label_print_log ORDER BY created_at DESC LIMIT 1").fetchone()
        assert row["reason"]  # a real, non-empty failure reason was recorded
