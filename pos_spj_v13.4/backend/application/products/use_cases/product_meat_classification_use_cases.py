"""Use cases del catálogo de clasificación cárnica (PROD-3).

Especies, regiones anatómicas y cortes son *catálogos configurables* (nunca
hardcodeados a una sola especie, §11) — hasta esta fase existían como entidades
de dominio validadas pero sin ningún caso de uso real que las persistiera (las
especies sólo llegaban por semilla de migración; regiones y cortes no tenían
ninguna vía de alta). Cada mutación exige su permiso granular
(``SPECIES_MANAGE``/``MEAT_CLASSIFICATION_MANAGE``/``CUTS_MANAGE``, fail-closed)
y corre las policies de dominio existentes: ``validate_region_species`` (una
región debe pertenecer a la especie indicada) y
``CutClassification.validate_under_parent`` (un corte hijo debe ser de la misma
especie y de nivel estrictamente inferior al padre — nunca un ciclo). El caso de
uso es dueño de la transacción.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from backend.application.products.audit import record_product_audit_entry
from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_meat_classification_commands import (
    ClassifyMeatProductCommand,
    CreateAnatomicalRegionCommand,
    CreateCutClassificationCommand,
    CreateSpeciesCommand,
    SetAnatomicalRegionActiveCommand,
    SetCutClassificationActiveCommand,
    SetSpeciesActiveCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.domain.products.entities.anatomical_region import AnatomicalRegion
from backend.domain.products.entities.cut_classification import CutClassification
from backend.domain.products.entities.species import Species
from backend.domain.products.enums import LifecycleStatus
from backend.domain.products.events import ProductEvents
from backend.domain.products.exceptions import ProductsDomainError
from backend.domain.products.enums import ProductType
from backend.domain.products.meat_enums import MeatCategory
from backend.domain.products.policies.meat_product_classification_policy import (
    requires_classification,
    validate_product_classification,
    validate_region_species,
)
from backend.infrastructure.db.repositories.products.meat_classification_repository import (
    MeatClassificationRepository,
)

logger = logging.getLogger("spj.products.meat_classification_use_cases")


@dataclass(frozen=True)
class MeatClassificationResult:
    success: bool
    entity_id: str | None
    message: str


class _Base:
    def __init__(self, connection,
                 authorization: ProductsAuthorizationPolicy | None = None) -> None:
        self._conn = connection
        self._repo = MeatClassificationRepository(connection)
        self._auth = authorization or ProductsAuthorizationPolicy.permissive_for_tests()

    def _rollback(self) -> None:
        rb = getattr(self._conn, "rollback", None)
        if rb is not None:
            rb()


# ── especies ──────────────────────────────────────────────────────────────
class CreateSpeciesUseCase(_Base):
    name = "CreateSpeciesUseCase"

    def execute(self, command: CreateSpeciesCommand) -> MeatClassificationResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.SPECIES_MANAGE)
        code = (command.code or "").strip().upper()
        if self._repo.species_code_exists(code):
            return MeatClassificationResult(False, None, f"El código '{code}' ya existe")
        try:
            species = Species(code=code, name=command.name)
        except ProductsDomainError as exc:
            return MeatClassificationResult(False, None, str(exc))
        try:
            self._repo.save_species(species)
            record_product_audit_entry(
                self._conn, action="SPECIES_CREATED", entity_id=species.id,
                user_id=command.user_id, operation_id=command.operation_id,
                after={"code": code, "name": command.name})
            _emit(self._conn, ProductEvents.SPECIES_CREATED, command, species.id,
                 {"code": code, "name": command.name})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("create species failed op=%s", command.operation_id)
            raise
        return MeatClassificationResult(True, species.id, "SPECIES_CREATED")


class SetSpeciesActiveUseCase(_Base):
    name = "SetSpeciesActiveUseCase"

    def execute(self, command: SetSpeciesActiveCommand) -> MeatClassificationResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.SPECIES_MANAGE)
        if self._repo.get_species(command.species_id) is None:
            return MeatClassificationResult(False, None, "La especie no existe")
        try:
            self._repo.set_species_active(command.species_id, command.active)
            event = (ProductEvents.SPECIES_CREATED if command.active
                    else ProductEvents.SPECIES_DEACTIVATED)
            record_product_audit_entry(
                self._conn, action=event, entity_id=command.species_id,
                user_id=command.user_id, operation_id=command.operation_id,
                after={"active": command.active})
            _emit(self._conn, event, command, command.species_id,
                 {"active": command.active})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("set-active species failed op=%s", command.operation_id)
            raise
        return MeatClassificationResult(True, command.species_id, "SPECIES_UPDATED")


# ── regiones anatómicas ──────────────────────────────────────────────────
class CreateAnatomicalRegionUseCase(_Base):
    name = "CreateAnatomicalRegionUseCase"

    def execute(self, command: CreateAnatomicalRegionCommand) -> MeatClassificationResult:
        command.validate()
        self._auth.require(command.user_id or "",
                           ProductPermissions.MEAT_CLASSIFICATION_MANAGE)
        if self._repo.get_species(command.species_id) is None:
            return MeatClassificationResult(False, None, "La especie no existe")
        code = (command.code or "").strip().upper()
        if self._repo.region_code_exists(command.species_id, code):
            return MeatClassificationResult(
                False, None, f"El código '{code}' ya existe para esta especie")
        try:
            region = AnatomicalRegion(species_id=command.species_id, code=code,
                                      name=command.name)
        except ProductsDomainError as exc:
            return MeatClassificationResult(False, None, str(exc))
        try:
            self._repo.save_region(region)
            record_product_audit_entry(
                self._conn, action="ANATOMICAL_REGION_CREATED", entity_id=region.id,
                user_id=command.user_id, operation_id=command.operation_id,
                after={"species_id": command.species_id, "code": code})
            _emit(self._conn, ProductEvents.ANATOMICAL_REGION_CREATED, command,
                 region.id, {"species_id": command.species_id, "code": code})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("create region failed op=%s", command.operation_id)
            raise
        return MeatClassificationResult(True, region.id, "ANATOMICAL_REGION_CREATED")


class SetAnatomicalRegionActiveUseCase(_Base):
    name = "SetAnatomicalRegionActiveUseCase"

    def execute(self, command: SetAnatomicalRegionActiveCommand) \
            -> MeatClassificationResult:
        command.validate()
        self._auth.require(command.user_id or "",
                           ProductPermissions.MEAT_CLASSIFICATION_MANAGE)
        if self._repo.get_region(command.region_id) is None:
            return MeatClassificationResult(False, None, "La región no existe")
        try:
            self._repo.set_region_active(command.region_id, command.active)
            event = (ProductEvents.ANATOMICAL_REGION_CREATED if command.active
                    else ProductEvents.ANATOMICAL_REGION_DEACTIVATED)
            record_product_audit_entry(
                self._conn, action=event, entity_id=command.region_id,
                user_id=command.user_id, operation_id=command.operation_id,
                after={"active": command.active})
            _emit(self._conn, event, command, command.region_id,
                 {"active": command.active})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("set-active region failed op=%s", command.operation_id)
            raise
        return MeatClassificationResult(True, command.region_id,
                                        "ANATOMICAL_REGION_UPDATED")


# ── cortes ────────────────────────────────────────────────────────────────
class CreateCutClassificationUseCase(_Base):
    name = "CreateCutClassificationUseCase"

    def execute(self, command: CreateCutClassificationCommand) \
            -> MeatClassificationResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.CUTS_MANAGE)
        species = self._repo.get_species(command.species_id)
        if species is None:
            return MeatClassificationResult(False, None, "La especie no existe")
        region = self._repo.get_region(command.anatomical_region_id)
        if region is None:
            return MeatClassificationResult(False, None, "La región anatómica no existe")
        code = (command.code or "").strip().upper()
        if self._repo.cut_code_exists(command.species_id, code):
            return MeatClassificationResult(
                False, None, f"El código '{code}' ya existe para esta especie")
        try:
            validate_region_species(region, species)
            cut = CutClassification(
                species_id=command.species_id,
                anatomical_region_id=command.anatomical_region_id, code=code,
                name=command.name, cut_level=command.cut_level,
                bone_status=command.bone_status, fat_class=command.fat_class,
                quality_grade=command.quality_grade,
                parent_cut_id=command.parent_cut_id)
            if command.parent_cut_id:
                parent = self._repo.get_cut(command.parent_cut_id)
                if parent is None:
                    return MeatClassificationResult(
                        False, None, "El corte padre no existe")
                cut.validate_under_parent(parent)
        except ProductsDomainError as exc:
            return MeatClassificationResult(False, None, str(exc))
        try:
            self._repo.save_cut(cut)
            record_product_audit_entry(
                self._conn, action="CUT_CLASSIFICATION_CREATED", entity_id=cut.id,
                user_id=command.user_id, operation_id=command.operation_id,
                after={"species_id": command.species_id, "code": code,
                      "cut_level": cut.cut_level.value,
                      "parent_cut_id": cut.parent_cut_id})
            _emit(self._conn, ProductEvents.CUT_CLASSIFICATION_CREATED, command,
                 cut.id, {"species_id": command.species_id, "code": code,
                         "cut_level": cut.cut_level.value})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("create cut failed op=%s", command.operation_id)
            raise
        return MeatClassificationResult(True, cut.id, "CUT_CLASSIFICATION_CREATED")


class SetCutClassificationActiveUseCase(_Base):
    name = "SetCutClassificationActiveUseCase"

    def execute(self, command: SetCutClassificationActiveCommand) \
            -> MeatClassificationResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.CUTS_MANAGE)
        if self._repo.get_cut(command.cut_id) is None:
            return MeatClassificationResult(False, None, "El corte no existe")
        status = LifecycleStatus.ACTIVE if command.active else LifecycleStatus.INACTIVE
        try:
            self._repo.set_cut_status(command.cut_id, status)
            event = (ProductEvents.CUT_CLASSIFICATION_CREATED if command.active
                    else ProductEvents.CUT_CLASSIFICATION_DEACTIVATED)
            record_product_audit_entry(
                self._conn, action=event, entity_id=command.cut_id,
                user_id=command.user_id, operation_id=command.operation_id,
                after={"status": status.value})
            _emit(self._conn, event, command, command.cut_id,
                 {"active": command.active})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("set-active cut failed op=%s", command.operation_id)
            raise
        return MeatClassificationResult(True, command.cut_id,
                                        "CUT_CLASSIFICATION_UPDATED")


# ── clasificación de UN producto (PROD-22) ─────────────────────────────────
class ClassifyMeatProductUseCase(_Base):
    """Categoría cárnica, región anatómica y corte de un producto cárnico.

    La política de dominio (`validate_product_classification`) existía desde
    PROD-3 y nadie la llamaba: no había dónde guardar la clasificación. Exige
    especie en el producto, que región y corte sean de esa especie y que el
    corte cuelgue de la región elegida. Reclasificar exige motivo (§39).
    """

    name = "ClassifyMeatProductUseCase"

    def execute(self, command: ClassifyMeatProductCommand) -> MeatClassificationResult:
        command.validate()
        self._auth.require(command.user_id or "",
                           ProductPermissions.MEAT_CLASSIFICATION_MANAGE)
        product = self._repo.product_core(command.product_id)
        if product is None:
            return MeatClassificationResult(False, None, "El producto no existe")
        try:
            product_type = ProductType(product["product_type"])
        except ValueError:
            return MeatClassificationResult(False, None, "Tipo de producto desconocido")
        if not requires_classification(product_type):
            return MeatClassificationResult(
                False, None, "Sólo los productos cárnicos llevan clasificación cárnica")
        meat_category = (command.meat_category or "").strip() or None
        if meat_category is not None:
            try:
                meat_category = MeatCategory(meat_category).value
            except ValueError:
                return MeatClassificationResult(False, None, "Categoría cárnica inválida")
        species = self._repo.get_species(product["species_id"]) if product["species_id"] else None
        region = (self._repo.get_region(command.anatomical_region_id)
                  if command.anatomical_region_id else None)
        cut = (self._repo.get_cut(command.cut_classification_id)
               if command.cut_classification_id else None)
        if command.anatomical_region_id and region is None:
            return MeatClassificationResult(False, None, "La región anatómica no existe")
        if command.cut_classification_id and cut is None:
            return MeatClassificationResult(False, None, "El corte no existe")
        try:
            validate_product_classification(product_type=product_type, species=species,
                                            cut=cut, region=region)
            if region is not None and species is not None:
                validate_region_species(region, species)
        except ProductsDomainError as exc:
            return MeatClassificationResult(False, None, str(exc))
        before = self._repo.get_product_classification(command.product_id)
        after = {"meat_category": meat_category,
                 "anatomical_region_id": region.id if region else None,
                 "cut_classification_id": cut.id if cut else None}
        if before == after:
            return MeatClassificationResult(True, command.product_id,
                                            "La clasificación no cambió")
        changing = before is not None and any(before.values())
        reason = (command.reason or "").strip() or None
        if changing and reason is None:
            return MeatClassificationResult(
                False, None, "Cambiar la clasificación cárnica requiere un motivo")
        try:
            self._repo.save_product_classification(
                command.product_id, classified_by=command.user_id, **after)
            record_product_audit_entry(
                self._conn,
                action=("MEAT_PRODUCT_CLASSIFICATION_CHANGED" if changing
                        else "MEAT_PRODUCT_CLASSIFIED"),
                entity_id=command.product_id, user_id=command.user_id or "",
                operation_id=command.operation_id, before=before, after=after,
                reason=reason)
            _emit(self._conn,
                  (ProductEvents.MEAT_PRODUCT_CLASSIFICATION_CHANGED if changing
                   else ProductEvents.MEAT_PRODUCT_CLASSIFIED),
                  command, command.product_id, after)
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("classify meat product failed op=%s", command.operation_id)
            raise
        return MeatClassificationResult(
            True, command.product_id,
            "MEAT_PRODUCT_CLASSIFICATION_CHANGED" if changing else "MEAT_PRODUCT_CLASSIFIED")


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
