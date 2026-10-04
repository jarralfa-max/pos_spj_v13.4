"""DeviceHealthQueryService — el estado de dispositivos de la barra del cajero
(§49-51: báscula, terminal, impresora, escáner, cajón, pantalla del cliente).

QUÉ CAMBIÓ (re-auditoría POS, 2026-10-01)
-----------------------------------------
Leía la tabla legacy `hardware_config`, que NO tiene ningún escritor en el
código vivo: el registro de dispositivos que Configuración → Dispositivos
mantiene es el de Device Management (`devices` + `device_profiles`, y las rutas
de impresión `print_routes`). Así que reportaba "sin configurar" para todo,
siempre, aunque el usuario hubiera dado de alta su impresora.

Ahora responde desde ese registro canónico: un tipo está "configurado" si la
sucursal tiene un dispositivo ACTIVO de ese tipo (perfil activo). La impresora
de tickets además necesita una ruta de impresión ``SALE_TICKET`` que la
resuelva: sin ruta, el ticket no sale aunque la impresora exista.

Sigue sin hacer ping a ningún puerto (§51: "La UI no prueba hardware
directamente"; una consulta tampoco): "configurado" no es "encendido".
"""

from __future__ import annotations

import logging
import sqlite3

from backend.application.sales.authorization import SalesAuthorizationPolicy
from backend.application.sales.dto import DeviceHealthDTO
from backend.application.sales.permissions import SalesPermissions

logger = logging.getLogger("spj.sales.device_health")

#: Lo que el POS usa, en el orden de la barra del cajero, con los tipos
#: canónicos de Device Management que cuentan para cada uno.
_DEVICE_KINDS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("scale", "Báscula", ("SCALE",)),
    ("printer", "Impresora de tickets", ("THERMAL_PRINTER", "DOCUMENT_PRINTER")),
    ("payment_terminal", "Terminal de pago", ("PAYMENT_TERMINAL",)),
    ("scanner", "Escáner", ("BARCODE_SCANNER", "QR_SCANNER")),
    ("cash_drawer", "Cajón de dinero", ("CASH_DRAWER",)),
    ("customer_display", "Pantalla del cliente", ("CUSTOMER_DISPLAY",)),
)


class DeviceHealthQueryService:
    def __init__(self, connection, authorization: SalesAuthorizationPolicy | None = None) -> None:
        self._connection = connection
        self._auth = authorization or SalesAuthorizationPolicy()

    def check_all(self, *, requester_user_id: str,
                  branch_id: str | None = None) -> tuple[DeviceHealthDTO, ...]:
        self._auth.require(requester_user_id, SalesPermissions.DEVICE_DIAGNOSTICS_VIEW)
        activos = self._active_types(branch_id)
        resultados = []
        for kind, label, types in _DEVICE_KINDS:
            configured = any(t in activos for t in types)
            detail = f"{label}: {'configurado' if configured else 'sin configurar en Dispositivos'}"
            if kind == "printer" and configured and not self._ticket_route_exists(branch_id):
                configured = False
                detail = f"{label}: falta la ruta de impresión «Ticket de venta»"
            resultados.append(DeviceHealthDTO(
                device_type=kind, configured=configured, enabled=configured, detail=detail))
        return tuple(resultados)

    def _active_types(self, branch_id: str | None) -> set[str]:
        """Tipos con al menos un dispositivo ACTIVO (de perfil activo) en la
        sucursal, o sin sucursal asignada (vale para todas)."""
        try:
            rows = self._connection.execute(
                "SELECT p.device_type FROM devices d JOIN device_profiles p ON p.id = d.profile_id"
                " WHERE d.status = 'ACTIVE' AND COALESCE(p.active, 1) = 1"
                " AND (? IS NULL OR d.branch_id = ? OR COALESCE(d.branch_id, '') = '')",
                (branch_id, branch_id)).fetchall()
        except sqlite3.OperationalError:
            logger.info("Sin registro de dispositivos en esta base")
            return set()
        return {str(row[0]) for row in rows}

    def _ticket_route_exists(self, branch_id: str | None) -> bool:
        try:
            from backend.infrastructure.db.repositories.device_management.device_repository import (
                SqliteDeviceRepository,
            )
            from backend.infrastructure.db.repositories.device_management.print_route_repository import (  # noqa: E501
                SqlitePrintRouteRepository,
            )
            from backend.domain.device_management.enums import PrintRouteModule
            from backend.infrastructure.integrations.document_output_print_routing_client import (
                DocumentOutputPrintRoutingClient,
            )

            DocumentOutputPrintRoutingClient(
                SqlitePrintRouteRepository(self._connection),
                SqliteDeviceRepository(self._connection)).resolve(
                "SALE_TICKET", branch_id=branch_id, module=PrintRouteModule.SALES.value)
            return True
        except Exception:  # noqa: BLE001 - sin ruta resoluble = el ticket no saldría
            return False
