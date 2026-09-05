"""Use cases del catálogo de unidades, conversiones y peso variable (PROD-5).

Hasta esta fase, `UnitOfMeasure`/`ProductUnitConversion`/`CatchWeightConfiguration`
tenían entidades de dominio validadas (Decimal-only, factor positivo, rango
mínimo/máximo, tolerancia 0-100%), `UnitRepository` completo y
`unit_conversion_policy.detect_cycle`/`convert` (grafo de conversión con
detección de ciclos multi-hop) — pero CERO casos de uso reales los llamaban
(confirmado por grep: `UnitRepository(` y `detect_cycle` no tenían ningún
consumidor fuera de sus propios archivos). Las unidades sólo llegaban por
semilla de migración (155); no existía ninguna vía de alta de unidades,
conversiones o configuración de peso variable. Cada mutación exige su permiso
granular (fail-closed) y corre las policies de dominio existentes — la
detección de ciclos corre contra TODAS las conversiones activas (globales +
las propias del producto) antes de guardar una nueva.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from decimal import Decimal

from backend.application.products.audit import record_product_audit_entry
from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_unit_commands import (
    CreateUnitCommand,
    CreateUnitConversionCommand,
    SetCatchWeightConfigCommand,
    SetUnitActiveCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.domain.products.entities.product_unit_conversion import (
    ProductUnitConversion,
)
from backend.domain.products.entities.unit_of_measure import UnitOfMeasure
from backend.domain.products.events import ProductEvents
from backend.domain.products.exceptions import ProductsDomainError
from backend.domain.products.policies.unit_conversion_policy import detect_cycle
from backend.domain.products.value_objects.catch_weight_configuration import (
    CatchWeightConfiguration,
)
from backend.infrastructure.db.repositories.products.unit_repository import (
    UnitRepository,
)

logger = logging.getLogger("spj.products.unit_use_cases")


@dataclass(frozen=True)
class UnitResult:
    success: bool
    entity_id: str | None
    message: str


class _Base:
    def __init__(self, connection,
                 authorization: ProductsAuthorizationPolicy | None = None) -> None:
        self._conn = connection
        self._repo = UnitRepository(connection)
        self._auth = authorization or ProductsAuthorizationPolicy.permissive_for_tests()

    def _rollback(self) -> None:
        rb = getattr(self._conn, "rollback", None)
        if rb is not None:
            rb()


# ── unidades ─────────────────────────────────────────────────────────────
class CreateUnitUseCase(_Base):
    name = "CreateUnitUseCase"

    def execute(self, command: CreateUnitCommand) -> UnitResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.UNITS_MANAGE)
        code = (command.code or "").strip().upper()
        existing = [u for u in self._repo.list_units() if u.code == code]
        if existing:
            return UnitResult(False, None, f"El código '{code}' ya existe")
        try:
            unit = UnitOfMeasure(code=code, name=command.name,
                                 dimension=command.dimension)
        except ProductsDomainError as exc:
            return UnitResult(False, None, str(exc))
        try:
            self._repo.save_unit(unit)
            record_product_audit_entry(
                self._conn, action="UNIT_CREATED", entity_id=unit.id,
                user_id=command.user_id, operation_id=command.operation_id,
                after={"code": code, "dimension": unit.dimension.value})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("create unit failed op=%s", command.operation_id)
            raise
        return UnitResult(True, unit.id, "UNIT_CREATED")


class SetUnitActiveUseCase(_Base):
    name = "SetUnitActiveUseCase"

    def execute(self, command: SetUnitActiveCommand) -> UnitResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.UNITS_MANAGE)
        unit = self._repo.get_unit(command.unit_id)
        if unit is None:
            return UnitResult(False, None, "La unidad no existe")
        unit.active = bool(command.active)
        try:
            self._repo.save_unit(unit)
            record_product_audit_entry(
                self._conn, action="UNIT_UPDATED", entity_id=command.unit_id,
                user_id=command.user_id, operation_id=command.operation_id,
                after={"active": command.active})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("set-active unit failed op=%s", command.operation_id)
            raise
        return UnitResult(True, command.unit_id, "UNIT_UPDATED")


# ── conversiones ─────────────────────────────────────────────────────────
class CreateUnitConversionUseCase(_Base):
    name = "CreateUnitConversionUseCase"

    def execute(self, command: CreateUnitConversionCommand) -> UnitResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.CONVERSIONS_MANAGE)
        if self._repo.get_unit(command.from_unit_id) is None:
            return UnitResult(False, None, "La unidad origen no existe")
        if self._repo.get_unit(command.to_unit_id) is None:
            return UnitResult(False, None, "La unidad destino no existe")
        try:
            conv = ProductUnitConversion(
                from_unit_id=command.from_unit_id, to_unit_id=command.to_unit_id,
                factor=command.factor, product_id=command.product_id,
                rounding_scale=command.rounding_scale,
                effective_from=command.effective_from,
                effective_to=command.effective_to)
        except ProductsDomainError as exc:
            return UnitResult(False, None, str(exc))
        # §16: la nueva arista no debe crear un ciclo en el grafo de conversión
        # (globales + las propias del producto, si aplica).
        existing = self._repo.list_conversions(product_id=command.product_id)
        try:
            detect_cycle([*existing, conv])
        except ProductsDomainError as exc:
            return UnitResult(False, None, str(exc))
        try:
            self._repo.save_conversion(conv)
            record_product_audit_entry(
                self._conn, action="UNIT_CONVERSION_CREATED", entity_id=conv.id,
                user_id=command.user_id, operation_id=command.operation_id,
                after={"from_unit_id": conv.from_unit_id, "to_unit_id": conv.to_unit_id,
                      "factor": str(conv.factor), "product_id": command.product_id})
            _emit(self._conn, ProductEvents.PRODUCT_UNIT_CONVERSION_UPDATED, command,
                 conv.id, {"product_id": command.product_id})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("create conversion failed op=%s", command.operation_id)
            raise
        return UnitResult(True, conv.id, "UNIT_CONVERSION_CREATED")


# ── peso variable ────────────────────────────────────────────────────────
class SetCatchWeightConfigUseCase(_Base):
    name = "SetCatchWeightConfigUseCase"

    def execute(self, command: SetCatchWeightConfigCommand) -> UnitResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.UNITS_MANAGE)
        try:
            cfg = CatchWeightConfiguration(
                enabled=bool(command.enabled),
                nominal_unit_id=command.nominal_unit_id or "",
                weight_unit_id=command.weight_unit_id or "",
                minimum_weight=(Decimal(command.minimum_weight)
                               if command.minimum_weight is not None else Decimal("0")),
                maximum_weight=(Decimal(command.maximum_weight)
                               if command.maximum_weight is not None else Decimal("0")),
                average_weight=(Decimal(command.average_weight)
                                if command.average_weight is not None else None),
                tolerance_pct=Decimal(command.tolerance_pct),
                price_basis=command.price_basis,
                label_required=bool(command.label_required),
                scale_barcode_enabled=bool(command.scale_barcode_enabled))
        except ProductsDomainError as exc:
            return UnitResult(False, None, str(exc))
        try:
            self._repo.save_catch_weight(command.product_id, cfg)
            record_product_audit_entry(
                self._conn, action="PRODUCT_CATCH_WEIGHT_CONFIGURED",
                entity_id=command.product_id, user_id=command.user_id,
                operation_id=command.operation_id,
                after={"enabled": cfg.enabled, "price_basis": cfg.price_basis.value})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("set catch-weight config failed op=%s", command.operation_id)
            raise
        return UnitResult(True, command.product_id, "PRODUCT_CATCH_WEIGHT_CONFIGURED")


def _emit(conn, event_name: str, command, entity_id: str, extra: dict) -> None:
    from backend.shared.ids import new_uuid
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND "
                    "name='product_outbox'").fetchone() is None:
        return
    event_id = new_uuid()
    payload = {"event_id": event_id, "event_name": event_name,
              "operation_id": command.operation_id, "entity_id": entity_id}
    payload.update(extra)
    conn.execute(
        "INSERT OR IGNORE INTO product_outbox (id, event_id, event_name, operation_id, "
        "entity_id, payload) VALUES (?,?,?,?,?,?)",
        (new_uuid(), event_id, event_name, command.operation_id, entity_id,
         json.dumps(payload)))
