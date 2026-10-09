"""Impresora resuelta por Document Output y entrega de bytes ya renderizados.

Extraído de `SalesTicketPrinter` (CASH-26 bloque 2, 2026-10-07) para que Caja
imprima sus cortes por la MISMA vía que el ticket de venta en vez de duplicar
la resolución: ruta de impresión por tipo de documento y sucursal
(`DocumentOutputPrintRoutingClient`), perfil de conexión del dispositivo y
`PrintTransport`. Nada de puertos escritos a mano (§18).

Todo lo que impide imprimir sale como `PrintTargetUnavailable` con un motivo
legible; cada consumidor lo traduce a su propio error de dominio.
"""

from __future__ import annotations

import re
import sqlite3


class PrintTargetUnavailable(Exception):
    """No hay impresora utilizable o no recibió los datos. El mensaje es para el operador."""


def resolve_routed_device(connection, document_type: str, *, branch_id: str | None,
                          workstation_id: str | None, module: str | None,
                          no_printer_message: str):
    """Dispositivo y perfil que Document Output asigna a ese documento."""
    from backend.domain.device_management.exceptions import (
        NoAvailablePrinterError,
        PrintRouteNotFoundError,
    )
    from backend.infrastructure.db.repositories.device_management.device_repository import (
        SqliteDeviceRepository,
    )
    from backend.infrastructure.db.repositories.device_management.print_route_repository import (  # noqa: E501
        SqlitePrintRouteRepository,
    )
    from backend.infrastructure.integrations.document_output_print_routing_client import (
        DocumentOutputPrintRoutingClient,
    )

    devices = SqliteDeviceRepository(connection)
    try:
        resolution = DocumentOutputPrintRoutingClient(
            SqlitePrintRouteRepository(connection), devices).resolve(
            document_type, branch_id=branch_id, workstation_id=workstation_id, module=module)
    except (PrintRouteNotFoundError, NoAvailablePrinterError, sqlite3.OperationalError) as exc:
        raise PrintTargetUnavailable(no_printer_message) from exc
    return load_device(connection, resolution.printer_device_id,
                       no_printer_message=no_printer_message)


def load_device(connection, device_id: str, *, no_printer_message: str):
    from backend.infrastructure.db.repositories.device_management.device_profile_repository import (  # noqa: E501
        SqliteDeviceProfileRepository,
    )
    from backend.infrastructure.db.repositories.device_management.device_repository import (
        SqliteDeviceRepository,
    )

    device = SqliteDeviceRepository(connection).get(device_id)
    if device is None:
        raise PrintTargetUnavailable(no_printer_message)
    profile = SqliteDeviceProfileRepository(connection).get(device.profile_id)
    if profile is None:
        raise PrintTargetUnavailable(
            f"La impresora {device.code} no tiene perfil de conexión en Dispositivos.")
    return device, profile


def connection_target(device, profile) -> tuple[object, str, int]:
    """(transporte, destino, baudios) del perfil de conexión del dispositivo."""
    from backend.domain.device_management.enums import ConnectionType
    from backend.infrastructure.printing.transport import TransportType

    conexion = profile.connection_profile
    tipo = conexion.connection_type
    if tipo in (ConnectionType.NETWORK, ConnectionType.HTTP):
        endpoint = conexion.network_endpoint
        if endpoint is None:
            raise PrintTargetUnavailable(f"La impresora {device.code} no tiene dirección de red.")
        return TransportType.NETWORK, f"{endpoint.host}:{endpoint.port}", 9600
    if tipo is ConnectionType.SERIAL:
        serie = conexion.serial_port
        if serie is None:
            raise PrintTargetUnavailable(f"La impresora {device.code} no tiene puerto serie.")
        return TransportType.SERIAL, serie.port, serie.baud_rate
    if tipo in (ConnectionType.USB, ConnectionType.SYSTEM):
        # La cola de Windows del perfil (`driver_name`); vacío = la
        # predeterminada de Windows. Antes SIEMPRE era la predeterminada, así
        # que una térmica USB que no fuera la predeterminada nunca recibía nada.
        return TransportType.USB_WIN32, str(profile.driver_name or "").strip(), 9600
    raise PrintTargetUnavailable(f"Tipo de conexión no soportado para tickets: {tipo.value}")


def paper_width_mm(profile) -> int:
    """`paper_profile` del perfil ("58mm", "80 mm"...); sin él, 80 mm."""
    encontrado = re.search(r"(58|80)", str(getattr(profile, "paper_profile", "") or ""))
    return int(encontrado.group(1)) if encontrado else 80


def send(device, profile, data: bytes, *, what: str = "el documento") -> None:
    """Entrega los bytes al dispositivo; cualquier fallo es `PrintTargetUnavailable`."""
    from backend.infrastructure.printing.transport import PrintTransport

    transport, destination, baud = connection_target(device, profile)
    try:
        ok = PrintTransport.send(data, transport, destination, baud=baud)
    except Exception as exc:  # noqa: BLE001 - un transporte roto es un documento no impreso
        raise PrintTargetUnavailable(f"No se pudo enviar {what} a {device.code}: {exc}") from exc
    if not ok:
        raise PrintTargetUnavailable(
            f"La impresora {device.code} no recibió {what} (¿apagada o sin papel?).")


def probe(device, profile) -> tuple[bool, str]:
    """¿Responde el dispositivo? Sin imprimir nada (prueba no invasiva, §21)."""
    from backend.infrastructure.printing.transport import PrintTransport

    transport, destination, baud = connection_target(device, profile)
    return PrintTransport.probe(transport, destination, baud=baud)
