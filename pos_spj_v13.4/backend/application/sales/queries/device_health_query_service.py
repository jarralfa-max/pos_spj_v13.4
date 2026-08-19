"""DeviceHealthQueryService — POS-12/§49-51's cashier-bar device-status
strip.

Master prompt §67 names a `DeviceHealthQueryService`; research for this
phase confirmed no such service, and nothing shaped like it
(`CashDeviceQueryService` is the nearest neighbor and answers a different
question — an admin's full device list, not a live cashier-bar summary),
exists anywhere in the repository. Rather than fabricate a live
connectivity ping this repository has no real transport to perform safely
from a query service (opening a serial port just to answer a status
question would itself be a side effect), this reads `hardware_config` —
the one real, canonical table every hardware driver in this repository
already reads from (`HardwareService.load_configs()`,
`PrinterService._load_configs()` via `HardwareConfigRepository`) — and
reports "configured" honestly: a row exists, is active, and has enough of a
destination (`puerto`/`driver`/a non-empty `configuraciones` blob) to be
usable. `terminal_pago` and `customer_display` are intentionally absent
from `hardware_config`'s own seeded defaults (confirmed by reading
`migrations/m050_hardware_config_canonical.py`/
`core/repositories/hardware_config_repository.py::DEFAULT_TYPES`) — this
service reports them as unconfigured, which is the truth, not a limitation
of this query.
"""

from __future__ import annotations

import json

from backend.application.sales.authorization import SalesAuthorizationPolicy
from backend.application.sales.dto import DeviceHealthDTO
from backend.application.sales.permissions import SalesPermissions

# tipo (hardware_config) -> human label. `terminal_pago`/`customer_display`
# have no seeded row anywhere in this repository — included here so their
# absence is reported explicitly rather than silently omitted.
_DEVICE_TYPES = {
    "scanner": "Escáner",
    "bascula": "Báscula",
    "cajon": "Cajón de dinero",
    "ticket": "Impresora de tickets",
    "terminal_pago": "Terminal de pago",
    "customer_display": "Pantalla de cliente",
}


class DeviceHealthQueryService:
    def __init__(self, connection, authorization: SalesAuthorizationPolicy | None = None) -> None:
        self._connection = connection
        self._auth = authorization or SalesAuthorizationPolicy()

    def check_all(self, *, requester_user_id: str) -> tuple[DeviceHealthDTO, ...]:
        self._auth.require(requester_user_id, SalesPermissions.DEVICE_DIAGNOSTICS_VIEW)
        rows = {}
        try:
            cursor = self._connection.execute(
                "SELECT tipo, driver, puerto, configuraciones, activo FROM hardware_config")
            columns = [c[0] for c in cursor.description]
            rows = {r["tipo"]: r for r in (dict(zip(columns, row)) for row in cursor.fetchall())}
        except Exception:  # noqa: BLE001 - hardware_config may not exist on an old/minimal DB
            rows = {}

        return tuple(self._evaluate(tipo, label, rows.get(tipo)) for tipo, label in _DEVICE_TYPES.items())

    @staticmethod
    def _evaluate(device_type: str, label: str, row: dict | None) -> DeviceHealthDTO:
        if row is None:
            return DeviceHealthDTO(device_type=device_type, configured=False, enabled=False,
                                    detail=f"{label}: sin fila en hardware_config")
        enabled = bool(row.get("activo", 1))
        has_destination = bool((row.get("puerto") or "").strip() or (row.get("driver") or "").strip())
        if not has_destination:
            try:
                cfg = json.loads(row.get("configuraciones") or "{}")
            except Exception:  # noqa: BLE001 - malformed JSON is "not configured", not a crash
                cfg = {}
            has_destination = bool(cfg)
        configured = enabled and has_destination
        detail = f"{label}: {'configurado' if configured else 'sin configuración de transporte'}"
        return DeviceHealthDTO(device_type=device_type, configured=configured, enabled=enabled, detail=detail)
