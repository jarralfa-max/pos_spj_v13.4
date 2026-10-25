"""Unidad organizacional (auditoría enterprise, Fase 1).

La empresa NO es una sucursal, una planta NO es una sucursal y un almacén NO es
una planta: cada unidad tiene su tipo, su lugar en la jerarquía y sus
capacidades explícitas.

* **Sitio de operación.** Las unidades donde se opera (sucursal, planta, centro
  de distribución, almacén independiente, oficina corporativa, operación
  logística) tienen además su fila en `sucursales` con el MISMO id: así cada
  `branch_id` que ya usan Inventario, Caja, Finanzas… sigue siendo válido sin
  renombrar nada (`branch_id` = id del sitio de operación). Una REGIÓN sólo
  agrupa: no opera y no tiene sitio.
* **Capacidades.** SALES, POS, CASH, INVENTORY… se conceden por unidad, nunca se
  deducen del nombre del tipo. Al crear una unidad se proponen las de su tipo;
  cualquier cambio posterior exige motivo.
* **Ciclo.** ACTIVE ⇄ INACTIVE → CLOSED (definitivo, con fecha). Una unidad con
  hijas activas no se cierra; una unidad cerrada o inactiva no recibe hijas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from backend.shared.ids import new_uuid


class OrgUnitError(ValueError):
    """La operación viola una regla de la estructura organizacional."""


class OrgUnitType(str, Enum):
    RETAIL_BRANCH = "RETAIL_BRANCH"
    PRODUCTION_PLANT = "PRODUCTION_PLANT"
    DISTRIBUTION_CENTER = "DISTRIBUTION_CENTER"
    WAREHOUSE = "WAREHOUSE"
    CORPORATE_OFFICE = "CORPORATE_OFFICE"
    LOGISTICS_OPERATION = "LOGISTICS_OPERATION"
    REGION = "REGION"

    @property
    def is_operating_site(self) -> bool:
        return self is not OrgUnitType.REGION

    @property
    def label(self) -> str:
        return _TYPE_LABELS[self]


_TYPE_LABELS = {
    OrgUnitType.RETAIL_BRANCH: "Sucursal", OrgUnitType.PRODUCTION_PLANT: "Planta",
    OrgUnitType.DISTRIBUTION_CENTER: "Centro de distribución",
    OrgUnitType.WAREHOUSE: "Almacén", OrgUnitType.CORPORATE_OFFICE: "Oficina corporativa",
    OrgUnitType.LOGISTICS_OPERATION: "Operación logística", OrgUnitType.REGION: "Región",
}


class OrgUnitStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    CLOSED = "CLOSED"


class Capability(str, Enum):
    SALES = "SALES"
    POS = "POS"
    CASH = "CASH"
    INVENTORY = "INVENTORY"
    PURCHASING = "PURCHASING"
    RECEIVING = "RECEIVING"
    PRODUCTION = "PRODUCTION"
    LOGISTICS = "LOGISTICS"
    FINANCE = "FINANCE"
    CRM = "CRM"
    BI = "BI"


#: Lo que se PROPONE al crear una unidad de cada tipo. Es sólo un punto de
#: partida: lo que rige son las capacidades guardadas de la unidad.
SUGGESTED_CAPABILITIES: dict[OrgUnitType, frozenset[Capability]] = {
    OrgUnitType.RETAIL_BRANCH: frozenset({
        Capability.SALES, Capability.POS, Capability.CASH, Capability.INVENTORY,
        Capability.PURCHASING, Capability.RECEIVING, Capability.CRM, Capability.FINANCE,
        Capability.BI}),
    OrgUnitType.PRODUCTION_PLANT: frozenset({
        Capability.INVENTORY, Capability.PRODUCTION, Capability.RECEIVING,
        Capability.PURCHASING, Capability.LOGISTICS, Capability.FINANCE, Capability.BI}),
    OrgUnitType.DISTRIBUTION_CENTER: frozenset({
        Capability.INVENTORY, Capability.RECEIVING, Capability.LOGISTICS,
        Capability.PURCHASING, Capability.FINANCE, Capability.BI}),
    OrgUnitType.WAREHOUSE: frozenset({Capability.INVENTORY, Capability.RECEIVING}),
    OrgUnitType.CORPORATE_OFFICE: frozenset({
        Capability.FINANCE, Capability.PURCHASING, Capability.CRM, Capability.BI}),
    OrgUnitType.LOGISTICS_OPERATION: frozenset({Capability.LOGISTICS, Capability.INVENTORY}),
    OrgUnitType.REGION: frozenset({Capability.BI}),
}

#: Capacidades que sólo tienen sentido donde se opera físicamente: una región
#: agrupa (puede consolidar Finanzas/BI) pero no vende, no cobra ni guarda stock.
SITE_ONLY_CAPABILITIES = frozenset({
    Capability.SALES, Capability.POS, Capability.CASH, Capability.INVENTORY,
    Capability.RECEIVING, Capability.PRODUCTION, Capability.LOGISTICS})

#: Una capacidad que exige otra: el punto de venta vende y cobra.
_REQUIRES: dict[Capability, frozenset[Capability]] = {
    Capability.POS: frozenset({Capability.SALES, Capability.CASH}),
}


def check_capabilities(unit_type: OrgUnitType, capabilities: frozenset[Capability]) -> None:
    """Valida un conjunto COMPLETO de capacidades para una unidad de ese tipo."""
    if not unit_type.is_operating_site:
        sobran = sorted(c.value for c in capabilities & SITE_ONLY_CAPABILITIES)
        if sobran:
            raise OrgUnitError(f"Un(a) {unit_type.label.lower()} no opera: no puede tener "
                               f"{', '.join(sobran)}")
    for capacidad, requeridas in _REQUIRES.items():
        faltan = requeridas - capabilities
        if capacidad in capabilities and faltan:
            raise OrgUnitError(f"{capacidad.value} requiere "
                               f"{', '.join(sorted(c.value for c in faltan))}")


#: Qué tipo puede colgar de qué tipo. Raíz (sin padre) se permite para todos.
_ALLOWED_PARENTS: dict[OrgUnitType, frozenset[OrgUnitType]] = {
    OrgUnitType.REGION: frozenset({OrgUnitType.REGION, OrgUnitType.CORPORATE_OFFICE}),
    OrgUnitType.CORPORATE_OFFICE: frozenset({OrgUnitType.CORPORATE_OFFICE}),
    OrgUnitType.RETAIL_BRANCH: frozenset({OrgUnitType.REGION, OrgUnitType.CORPORATE_OFFICE}),
    OrgUnitType.PRODUCTION_PLANT: frozenset({OrgUnitType.REGION, OrgUnitType.CORPORATE_OFFICE}),
    OrgUnitType.DISTRIBUTION_CENTER: frozenset({OrgUnitType.REGION,
                                                OrgUnitType.CORPORATE_OFFICE}),
    OrgUnitType.LOGISTICS_OPERATION: frozenset({OrgUnitType.REGION,
                                                OrgUnitType.CORPORATE_OFFICE,
                                                OrgUnitType.DISTRIBUTION_CENTER}),
    # Un almacén independiente puede pertenecer a una planta, un CEDIS o una sucursal.
    OrgUnitType.WAREHOUSE: frozenset({OrgUnitType.REGION, OrgUnitType.CORPORATE_OFFICE,
                                      OrgUnitType.PRODUCTION_PLANT,
                                      OrgUnitType.DISTRIBUTION_CENTER,
                                      OrgUnitType.RETAIL_BRANCH}),
}

_CODE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{1,23}$")


def suggest_code(name: str, taken: set[str]) -> str:
    """Código válido derivado del nombre («Corregidora» → CORREGIDORA), único
    frente a `taken`."""
    import unicodedata
    plano = "".join(c for c in unicodedata.normalize("NFKD", str(name or ""))
                    if not unicodedata.combining(c))
    base = re.sub(r"[^A-Z0-9]+", "-", plano.upper()).strip("-")[:20].strip("-")
    if len(base) < 2:
        base = f"U-{base}" if base else "UNIDAD"
    candidato, n = base, 2
    while candidato in taken:
        sufijo = f"-{n}"
        candidato = base[:24 - len(sufijo)] + sufijo
        n += 1
    return candidato


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class OrgUnit:
    id: str
    company_id: str
    unit_type: OrgUnitType
    code: str
    name: str
    parent_id: str | None = None
    status: OrgUnitStatus = OrgUnitStatus.ACTIVE
    created_by: str | None = None
    closed_at: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        self.code = str(self.code or "").strip().upper()
        self.name = str(self.name or "").strip()
        if not _CODE.match(self.code):
            raise OrgUnitError("El código va en MAYÚSCULAS, 2 a 24 caracteres (letras, "
                               "números, guion)")
        if not self.name:
            raise OrgUnitError("La unidad necesita un nombre")
        if self.parent_id == self.id:
            raise OrgUnitError("Una unidad no puede ser su propia superior")

    # ── construcción ─────────────────────────────────────────────────────
    @classmethod
    def create(cls, *, company_id: str, unit_type: OrgUnitType, code: str, name: str,
               parent: "OrgUnit | None" = None, created_by: str | None = None,
               unit_id: str | None = None) -> "OrgUnit":
        unidad = cls(id=unit_id or new_uuid(), company_id=company_id, unit_type=unit_type,
                     code=code, name=name, created_by=created_by)
        if parent is not None:
            unidad._check_parent(parent)
            unidad.parent_id = parent.id
        return unidad

    # ── reglas ───────────────────────────────────────────────────────────
    def _check_parent(self, parent: "OrgUnit") -> None:
        if parent.status is not OrgUnitStatus.ACTIVE:
            raise OrgUnitError(f"«{parent.name}» no está activa: no puede recibir unidades")
        if parent.company_id != self.company_id:
            raise OrgUnitError("La unidad superior es de otra empresa")
        if parent.unit_type not in _ALLOWED_PARENTS[self.unit_type]:
            raise OrgUnitError(f"Un(a) {self.unit_type.label.lower()} no puede depender de "
                               f"un(a) {parent.unit_type.label.lower()}")

    def move_under(self, parent: "OrgUnit | None", *, ancestors_of_parent: set[str]) -> None:
        """Reubicar en la jerarquía. `ancestors_of_parent`: ids de la cadena hacia
        arriba del nuevo superior (para impedir ciclos)."""
        self._require_open()
        if parent is None:
            self.parent_id = None
        else:
            if parent.id == self.id or self.id in ancestors_of_parent:
                raise OrgUnitError("Ese movimiento crearía un ciclo en la jerarquía")
            self._check_parent(parent)
            self.parent_id = parent.id
        self._touch()

    def rename(self, *, name: str, code: str | None = None) -> None:
        self._require_open()
        nombre = str(name or "").strip()
        if not nombre:
            raise OrgUnitError("La unidad necesita un nombre")
        if code is not None:
            nuevo = str(code).strip().upper()
            if not _CODE.match(nuevo):
                raise OrgUnitError("Código inválido")
            self.code = nuevo
        self.name = nombre
        self._touch()

    def deactivate(self, *, active_children: int) -> None:
        self._require_open()
        if active_children:
            raise OrgUnitError(f"Tiene {active_children} unidad(es) activa(s) dependiente(s): "
                               "desactívelas o reubíquelas primero")
        self.status = OrgUnitStatus.INACTIVE
        self._touch()

    def reactivate(self) -> None:
        if self.status is OrgUnitStatus.CLOSED:
            raise OrgUnitError("Una unidad cerrada no se reabre; cree una nueva")
        self.status = OrgUnitStatus.ACTIVE
        self._touch()

    def close(self, *, active_children: int) -> None:
        self._require_open()
        if active_children:
            raise OrgUnitError(f"Tiene {active_children} unidad(es) activa(s) dependiente(s): "
                               "reubíquelas o ciérrelas primero")
        self.status = OrgUnitStatus.CLOSED
        self.closed_at = _utcnow()
        self._touch()

    def _require_open(self) -> None:
        if self.status is OrgUnitStatus.CLOSED:
            raise OrgUnitError("La unidad está cerrada")

    def _touch(self) -> None:
        self.updated_at = _utcnow()


__all__ = ["Capability", "OrgUnit", "OrgUnitError", "OrgUnitStatus", "OrgUnitType",
           "SITE_ONLY_CAPABILITIES", "SUGGESTED_CAPABILITIES", "check_capabilities",
           "suggest_code"]
