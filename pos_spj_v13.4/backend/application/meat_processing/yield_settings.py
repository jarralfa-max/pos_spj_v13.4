"""Tolerancias de rendimiento de Cárnico (Fase 10, 2026-09-19).

Decisión del usuario: tolerancia GLOBAL, igual para todos los cortes,
configurable en Cárnico → Configuración. Se aplican a la diferencia de cada
corte contra lo esperado de su despiece (aviso ≤ tolerancia ≤ crítico, en %).
Viven en `configuraciones` (sembradas por la migración 270).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from backend.application.meat_processing.permissions import MeatProcessingPermissions

KEYS = {
    "warning_pct": "meat_processing.yield.warning_pct",
    "tolerance_pct": "meat_processing.yield.tolerance_pct",
    "critical_pct": "meat_processing.yield.critical_pct",
}
DEFAULTS = {"warning_pct": Decimal("2"), "tolerance_pct": Decimal("5"),
            "critical_pct": Decimal("10")}


@dataclass(frozen=True)
class YieldTolerances:
    warning_pct: Decimal
    tolerance_pct: Decimal
    critical_pct: Decimal


def _dec(value) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


class YieldToleranceSettingsQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def get(self) -> YieldTolerances:
        valores = dict(DEFAULTS)
        try:
            filas = self._conn.execute(
                "SELECT clave, valor FROM configuraciones WHERE clave IN (?,?,?)",
                tuple(KEYS.values())).fetchall()
        except Exception:
            filas = []
        inverso = {v: k for k, v in KEYS.items()}
        for clave, valor in filas:
            d = _dec(valor)
            if d is not None and d >= 0:
                valores[inverso[clave]] = d
        return YieldTolerances(**valores)


class UpdateYieldTolerancesUseCase:
    def __init__(self, authorization) -> None:
        self._auth = authorization

    def execute(self, connection, *, actor_user_id: str, warning_pct, tolerance_pct,
                critical_pct) -> tuple[bool, str]:
        try:
            self._auth.require(actor_user_id, MeatProcessingPermissions.SETTINGS_MANAGE)
        except Exception as exc:  # noqa: BLE001 — permiso denegado, se informa
            return False, str(exc)
        nuevos = {"warning_pct": _dec(warning_pct), "tolerance_pct": _dec(tolerance_pct),
                  "critical_pct": _dec(critical_pct)}
        if any(v is None or v < 0 for v in nuevos.values()):
            return False, "Las tolerancias deben ser porcentajes mayores o iguales a cero."
        if not (nuevos["warning_pct"] <= nuevos["tolerance_pct"] <= nuevos["critical_pct"]):
            return False, "Debe cumplirse: aviso ≤ tolerancia ≤ crítico."
        for nombre, valor in nuevos.items():
            clave = KEYS[nombre]
            actualizadas = connection.execute(
                "UPDATE configuraciones SET valor=? WHERE clave=?", (str(valor), clave)).rowcount
            if not actualizadas:
                connection.execute("INSERT INTO configuraciones (clave, valor) VALUES (?,?)",
                                   (clave, str(valor)))
        connection.commit()
        return True, "Tolerancias de rendimiento guardadas"
