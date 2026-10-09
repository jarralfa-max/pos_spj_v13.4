"""Tolerancias de rendimiento de Cárnico (Fase 10, 2026-09-19).

Decisión del usuario: tolerancia GLOBAL, igual para todos los cortes,
configurable en Cárnico → Configuración. Se aplican a la diferencia de cada
corte contra lo esperado de su despiece (aviso ≤ tolerancia ≤ crítico, en %).
Son parámetros gobernados de Configuración (catálogo `meat_processing.yield.*`):
se leen con `ConfigurationReader` y se cambian con `GovernedSettingsWriter`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from backend.application.meat_processing.permissions import MeatProcessingPermissions
from backend.application.settings.configuration_reader import ConfigurationReader
from backend.application.settings.governance import GovernedSettingsWriter
from backend.domain.settings.enums import ScopeType
from backend.domain.settings.exceptions import ConfigurationDomainError
from backend.shared.ids import new_uuid

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
        reader = ConfigurationReader(self._conn)
        return YieldTolerances(**{nombre: reader.get(clave) for nombre, clave in KEYS.items()})


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
        writer = GovernedSettingsWriter(connection)
        try:
            writer.stage({KEYS[nombre]: valor for nombre, valor in nuevos.items()},
                         actor_user_id=actor_user_id, operation_id=new_uuid(),
                         reason="Cárnico → Configuración")
            connection.commit()
        except ConfigurationDomainError as exc:
            connection.rollback()
            return False, str(exc)
        writer.publish()
        return True, "Tolerancias de rendimiento guardadas"


# ── resolución jerárquica de la tolerancia (§17) ───────────────────────────
#: La tolerancia por nivel es el mismo parámetro gobernado afinado por ámbito
#: (Configuración → Parámetros), resuelto con la ÚNICA regla de herencia del
#: gobierno, que respeta la precedencia de §17: producto → proceso → especie →
#: categoría → centro de trabajo → área → planta → sucursal → empresa → global.
#: Antes había un mecanismo propio con claves `...@NIVEL:ref` en
#: `configuraciones`; la migración 303 las pasó a valores por ámbito.
_SCOPE_LABEL = {
    ScopeType.PRODUCT: "PRODUCT", ScopeType.PROCESS: "PROCESS", ScopeType.SPECIES: "SPECIES",
    ScopeType.PRODUCT_CATEGORY: "CATEGORY", ScopeType.WORK_CENTER: "WORK_CENTER",
    ScopeType.PRODUCTION_AREA: "AREA", ScopeType.PLANT: "PLANT", ScopeType.BRANCH: "BRANCH",
    ScopeType.COMPANY: "COMPANY",
}


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

    def configuration_context(self) -> dict[ScopeType, str]:
        return {scope_type: ref for scope_type, ref in (
            (ScopeType.PRODUCT, self.product_id), (ScopeType.PROCESS, self.process_type),
            (ScopeType.SPECIES, self.species_id), (ScopeType.PRODUCT_CATEGORY, self.category_id),
            (ScopeType.WORK_CENTER, self.work_center_id),
            (ScopeType.PRODUCTION_AREA, self.production_area_id),
            (ScopeType.PLANT, self.plant_id), (ScopeType.BRANCH, self.branch_id),
            (ScopeType.COMPANY, self.company_id)) if ref}


@dataclass(frozen=True)
class ResolvedTolerance:
    tolerances: YieldTolerances
    source: str


class YieldToleranceResolver:
    """La tolerancia que aplica a una salida.

    1. El perfil de rendimiento de Productos, si trae tolerancia (nivel producto).
    2. La tolerancia afinada por ámbito en Configuración → Parámetros.
    3. La tolerancia global (la que ya existía).

    Sólo se sustituye la tolerancia; aviso y crítico globales se ajustan para
    que siempre se cumpla aviso ≤ tolerancia ≤ crítico.
    """

    def __init__(self, connection) -> None:
        self._conn = connection
        self._global = YieldToleranceSettingsQueryService(connection)

    def resolve(self, scope: ToleranceScope, *,
                profile_tolerance_pct: Decimal | None = None) -> ResolvedTolerance:
        base = self._global.get()
        tolerancia, origen = None, "GLOBAL"
        if profile_tolerance_pct is not None and profile_tolerance_pct > 0:
            tolerancia, origen = Decimal(str(profile_tolerance_pct)), "YIELD_PROFILE"
        else:
            efectiva = ConfigurationReader(self._conn).resolve(
                KEYS["tolerance_pct"], context=scope.configuration_context())
            nivel = ScopeType(efectiva.source_scope_type) if efectiva.source_scope_type else None
            if nivel in _SCOPE_LABEL:
                tolerancia, origen = efectiva.value, _SCOPE_LABEL[nivel]
        if tolerancia is None:
            return ResolvedTolerance(base, origen)
        return ResolvedTolerance(YieldTolerances(
            warning_pct=min(base.warning_pct, tolerancia), tolerance_pct=tolerancia,
            critical_pct=max(base.critical_pct, tolerancia)), origen)
