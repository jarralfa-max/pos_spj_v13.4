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


# ── resolución jerárquica de la tolerancia (§17) ───────────────────────────
#: Precedencia, del más específico al más general. Cada nivel es un DATO que
#: se configura (`configuraciones`), nunca una rama de código por especie.
PRECEDENCE = ("PRODUCT", "PROCESS", "SPECIES", "CATEGORY", "WORK_CENTER", "AREA",
              "PLANT", "BRANCH", "COMPANY")
OVERRIDE_KEY = "meat_processing.yield.tolerance_pct@{scope}:{ref}"


@dataclass(frozen=True)
class ToleranceScope:
    product_id: str | None = None
    process_type: str | None = None
    species_id: str | None = None
    category_id: str | None = None
    work_center_id: str | None = None
    production_area_id: str | None = None
    plant_id: str | None = None
    branch_id: str | None = None
    company_id: str | None = None

    def references(self) -> list[tuple[str, str]]:
        valores = (self.product_id, self.process_type, self.species_id, self.category_id,
                   self.work_center_id, self.production_area_id, self.plant_id,
                   self.branch_id, self.company_id)
        return [(nivel, ref) for nivel, ref in zip(PRECEDENCE, valores) if ref]


@dataclass(frozen=True)
class ResolvedTolerance:
    tolerances: YieldTolerances
    source: str


class YieldToleranceResolver:
    """La tolerancia que aplica a una salida.

    1. El perfil de rendimiento de Productos, si trae tolerancia (nivel producto).
    2. Un ajuste por nivel, en `PRECEDENCE`.
    3. La tolerancia global (la que ya existía).

    Sólo se sustituye la tolerancia; aviso y crítico globales se ajustan para
    que siempre se cumpla aviso ≤ tolerancia ≤ crítico.
    """

    def __init__(self, connection) -> None:
        self._conn = connection
        self._global = YieldToleranceSettingsQueryService(connection)

    def _override(self, nivel: str, ref: str) -> Decimal | None:
        try:
            fila = self._conn.execute("SELECT valor FROM configuraciones WHERE clave=?",
                                      (OVERRIDE_KEY.format(scope=nivel, ref=ref),)).fetchone()
        except Exception:  # noqa: BLE001 — sin tabla: no hay ajustes
            return None
        valor = _dec(fila[0]) if fila else None
        return valor if valor is not None and valor >= 0 else None

    def resolve(self, scope: ToleranceScope, *,
                profile_tolerance_pct: Decimal | None = None) -> ResolvedTolerance:
        base = self._global.get()
        tolerancia, origen = None, "GLOBAL"
        if profile_tolerance_pct is not None and profile_tolerance_pct > 0:
            tolerancia, origen = Decimal(str(profile_tolerance_pct)), "YIELD_PROFILE"
        else:
            for nivel, ref in scope.references():
                valor = self._override(nivel, ref)
                if valor is not None:
                    tolerancia, origen = valor, nivel
                    break
        if tolerancia is None:
            return ResolvedTolerance(base, origen)
        return ResolvedTolerance(YieldTolerances(
            warning_pct=min(base.warning_pct, tolerancia), tolerance_pct=tolerancia,
            critical_pct=max(base.critical_pct, tolerancia)), origen)
