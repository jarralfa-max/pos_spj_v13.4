"""NetworkLabelPrintGateway — SET-14 cutover: the first real
`InventoryPrintGateway` (`backend/application/inventory/labels/gateway.py`)
implementation. INV-26's pipeline (permission-gated, audited) has existed
since that phase but was always wired with `InMemoryPrintGateway` in the
live composition root (`frontend/desktop/modules/inventory/composition.py`)
— printing a label recorded success and physically printed nothing. This
gateway makes it real:

1. Resolves a real printer via the SAME `PrintRoute`/device_management
   routing SET-12 already wired for Sales tickets
   (`DocumentOutputPrintRoutingClient`) — reused unchanged, not
   reimplemented. `printer_ref` is an optional explicit-device-code
   override; the default `"default"` value takes the routed path.
2. Renders real bytes per `label_format` (ZPL/ESC-POS/plain text —
   `zpl_renderer.py`/`escpos_label_renderer.py`/`text_label_renderer.py`).
3. Delivers via `core.services.printer_service.PrintTransport` — the
   same real, already-relied-upon transport layer ticket printing uses.

Never validated against physical hardware (none available in this
environment). `PrintDeliveryError` is the only exception this gateway
raises — `InventoryLabelPrintService.print_label()` already catches it,
audits the failure, and never crashes (see that file's own docstring).
A genuinely honest behavior change from today's always-succeeds stub:
printing without a configured route+device now fails clearly instead of
silently pretending to succeed.
"""

from __future__ import annotations

from backend.application.inventory.labels.gateway import PrintDeliveryError
from backend.domain.device_management.entities.device import Device
from backend.domain.device_management.entities.device_profile import DeviceProfile
from backend.domain.device_management.enums import ConnectionType, DeviceStatus
from backend.domain.device_management.exceptions import NoAvailablePrinterError, PrintRouteNotFoundError
from backend.domain.document_output.enums import DocumentType
from backend.domain.inventory.enums import LabelFormat, LabelType
from backend.domain.inventory.value_objects.label_document import LabelDocument
from backend.infrastructure.db.repositories.device_management.device_profile_repository import (
    SqliteDeviceProfileRepository,
)
from backend.infrastructure.db.repositories.device_management.device_repository import SqliteDeviceRepository
from backend.infrastructure.db.repositories.device_management.print_route_repository import (
    SqlitePrintRouteRepository,
)
from backend.infrastructure.hardware.label_rendering.escpos_label_renderer import render_escpos_label
from backend.infrastructure.hardware.label_rendering.text_label_renderer import render_text_label
from backend.infrastructure.hardware.label_rendering.zpl_renderer import render_zpl
from backend.infrastructure.integrations.document_output_print_routing_client import (
    DocumentOutputPrintRoutingClient,
)

_LABEL_TYPE_TO_DOCUMENT_TYPE = {
    LabelType.LOT: DocumentType.LOT_LABEL,
    LabelType.WEIGHT: DocumentType.WEIGHT_LABEL,
    LabelType.TRANSFER: DocumentType.TRANSFER_LABEL,
    LabelType.COUNT: DocumentType.COUNT_LABEL,
    LabelType.ADJUSTMENT: DocumentType.ADJUSTMENT_LABEL,
    LabelType.PRODUCT: DocumentType.PRODUCT_LABEL,
}

_RENDERERS = {
    LabelFormat.ZPL: lambda doc, copies: render_zpl(doc, copies=copies),
    LabelFormat.ESCPOS: lambda doc, copies: render_escpos_label(doc, copies=copies),
    LabelFormat.TEXT: lambda doc, copies: render_text_label(doc, copies=copies),
}

_NETWORK_TYPES = {ConnectionType.NETWORK, ConnectionType.HTTP}
_USB_TYPES = {ConnectionType.USB, ConnectionType.SYSTEM}


class NetworkLabelPrintGateway:
    def __init__(self, connection) -> None:
        self._connection = connection
        self._devices = SqliteDeviceRepository(connection)
        self._profiles = SqliteDeviceProfileRepository(connection)

    def print(
        self, *, document: LabelDocument, printer_ref: str, label_format: LabelFormat, copies: int,
    ) -> None:
        device = self._resolve_device(document, printer_ref)
        profile = self._profiles.get(device.profile_id)
        if profile is None:
            raise PrintDeliveryError(f"Dispositivo {device.code} no tiene un perfil de conexión válido")

        renderer = _RENDERERS.get(label_format)
        if renderer is None:
            raise PrintDeliveryError(f"Formato de etiqueta no soportado: {label_format}")
        data = renderer(document, copies)

        transport, destination, baud = self._connection_target(profile)

        from core.services.printer_service import PrintTransport

        try:
            ok = PrintTransport.send(data, transport, destination, baud=baud)
        except Exception as exc:  # noqa: BLE001 - any transport failure becomes a real delivery failure
            raise PrintDeliveryError(f"Fallo de entrega a {device.code} ({destination}): {exc}") from exc
        if not ok:
            raise PrintDeliveryError(f"El transporte no pudo entregar la etiqueta a {device.code}")

    # internals -----------------------------------------------------------------
    def _resolve_device(self, document: LabelDocument, printer_ref: str) -> Device:
        if printer_ref and printer_ref != "default":
            device = self._devices.get_by_code(printer_ref)
            if device is None or device.status is not DeviceStatus.ACTIVE:
                raise PrintDeliveryError(f"Dispositivo {printer_ref!r} no existe o no está activo")
            return device

        document_type = _LABEL_TYPE_TO_DOCUMENT_TYPE.get(document.label_type)
        if document_type is None:
            raise PrintDeliveryError(f"Tipo de etiqueta sin ruta soportada: {document.label_type}")

        resolver = DocumentOutputPrintRoutingClient(
            SqlitePrintRouteRepository(self._connection), SqliteDeviceRepository(self._connection))
        try:
            resolution = resolver.resolve(document_type.value)
        except (PrintRouteNotFoundError, NoAvailablePrinterError) as exc:
            raise PrintDeliveryError(
                f"Sin impresora de etiquetas configurada para {document_type.value}: {exc}") from exc

        device = self._devices.get(resolution.printer_device_id)
        if device is None:
            raise PrintDeliveryError(f"Dispositivo resuelto {resolution.printer_device_id} ya no existe")
        return device

    @staticmethod
    def _connection_target(profile: DeviceProfile):
        from core.services.printer_service import TransportType

        connection_type = profile.connection_profile.connection_type
        if connection_type in _NETWORK_TYPES:
            endpoint = profile.connection_profile.network_endpoint
            if endpoint is None:
                raise PrintDeliveryError("Perfil de conexión de red sin network_endpoint")
            return TransportType.NETWORK, f"{endpoint.host}:{endpoint.port}", 9600
        if connection_type is ConnectionType.SERIAL:
            serial = profile.connection_profile.serial_port
            if serial is None:
                raise PrintDeliveryError("Perfil de conexión serial sin serial_port")
            return TransportType.SERIAL, serial.port, serial.baud_rate
        if connection_type in _USB_TYPES:
            return TransportType.USB_WIN32, "", 9600
        raise PrintDeliveryError(
            f"Tipo de conexión no soportado para entrega real: {connection_type.value}")
