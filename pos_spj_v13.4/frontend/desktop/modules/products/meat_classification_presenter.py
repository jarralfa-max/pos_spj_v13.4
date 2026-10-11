"""Presenter de la clasificación cárnica (PROD-22, §11).

Especies, regiones anatómicas y cortes jerárquicos por especie. El backend
(PROD-3: entidades, políticas, casos de uso con auditoría y outbox) existía
completo, pero ninguna pantalla lo alcanzaba: en la base real había 12 especies
sembradas y CERO regiones y cortes, porque no había dónde capturarlos.

Sólo traduce: lee de los QueryServices, arma los comandos y devuelve
``(ok, mensaje)`` para que la página lo muestre. La autorización la revalida
cada caso de uso; aquí sólo se decide qué botones habilitar.
"""

from __future__ import annotations

import logging

from backend.application.products.permissions import ProductPermissions

logger = logging.getLogger("spj.products.meat_presenter")

CUT_LEVEL_ES = {
    "CARCASS": "Canal", "PRIMARY": "Corte primario",
    "SECONDARY": "Corte secundario", "PORTION": "Porcionado",
}
BONE_STATUS_ES = {"BONE_IN": "Con hueso", "BONELESS": "Sin hueso",
                  "NOT_APPLICABLE": "No aplica"}
FAT_CLASS_ES = {"LEAN": "Magro", "MEDIUM": "Medio", "FATTY": "Graso",
                "NOT_APPLICABLE": "No aplica"}
MEAT_CATEGORY_ES = {
    "LIVE": "Animal vivo", "CARCASS": "Canal", "HALF_CARCASS": "Media canal",
    "QUARTER": "Cuarto", "BONE_IN": "Con hueso", "BONELESS": "Sin hueso",
    "OFFAL": "Vísceras / menudencias", "TRIM": "Recorte", "GROUND": "Molido",
    "PROCESSED": "Procesado", "MARINATED": "Marinado", "FROZEN": "Congelado",
    "CHILLED": "Refrigerado", "COOKED": "Cocido", "BY_PRODUCT": "Subproducto",
    "WASTE": "Residuo",
}
PRICE_BASIS_ES = {
    "PER_KILOGRAM": "Por kilogramo", "PER_GRAM": "Por gramo", "PER_POUND": "Por libra",
    "PER_PIECE_WITH_ACTUAL_WEIGHT": "Por pieza con peso real",
}


class MeatClassificationPresenter:
    def __init__(self, *, read_factory, write_factory=None, has_permission=None,
                 session=None, product_read_factory=None) -> None:
        self._read = read_factory
        self._product_read = product_read_factory
        self._write = write_factory
        self._has = has_permission
        self._session = session

    # ── permisos (sólo habilitan botones) ──────────────────────────────────
    def _allowed(self, code: str) -> bool:
        if self._write is None:
            return False
        return True if self._has is None else bool(self._has(code))

    @property
    def can_manage_species(self) -> bool:
        return self._allowed(ProductPermissions.SPECIES_MANAGE)

    @property
    def can_manage_regions(self) -> bool:
        return self._allowed(ProductPermissions.MEAT_CLASSIFICATION_MANAGE)

    @property
    def can_manage_cuts(self) -> bool:
        return self._allowed(ProductPermissions.CUTS_MANAGE)

    @property
    def can_classify_products(self) -> bool:
        return self._allowed(ProductPermissions.MEAT_CLASSIFICATION_MANAGE)

    @property
    def can_manage_catch_weight(self) -> bool:
        return self._allowed(ProductPermissions.UNITS_MANAGE)

    # ── UN producto: clasificación y peso variable (PROD-22) ───────────────
    def product_classification(self, product_id: str) -> dict:
        _species_qs, meat_qs = self._read()
        return meat_qs.product_classification(product_id)

    def catch_weight(self, product_id: str) -> dict | None:
        if self._product_read is None:
            return None
        profiles_qs, _units_qs = self._product_read()
        return profiles_qs.catch_weight(product_id)

    def unit_options(self, dimension: str | None = None) -> list[dict]:
        if self._product_read is None:
            return []
        _profiles_qs, units_qs = self._product_read()
        return units_qs.list_units(dimension=dimension)

    def classify_product(self, *, product_id: str, meat_category: str | None,
                         anatomical_region_id: str | None,
                         cut_classification_id: str | None,
                         reason: str | None = None) -> tuple[bool, str]:
        from backend.application.products.commands.product_meat_classification_commands import (
            ClassifyMeatProductCommand,
        )
        return self._run("classify_product", lambda op, user: ClassifyMeatProductCommand(
            operation_id=op, product_id=product_id, meat_category=meat_category,
            anatomical_region_id=anatomical_region_id,
            cut_classification_id=cut_classification_id, reason=reason, user_id=user))

    def save_catch_weight(self, *, product_id: str, **fields) -> tuple[bool, str]:
        from backend.application.products.commands.product_unit_commands import (
            SetCatchWeightConfigCommand,
        )
        return self._run("catch_weight", lambda op, user: SetCatchWeightConfigCommand(
            operation_id=op, product_id=product_id, user_id=user, **fields))

    # ── lecturas ───────────────────────────────────────────────────────────
    def species(self) -> list[dict]:
        species_qs, _meat_qs = self._read()
        return species_qs.list_species(active_only=False)

    def regions(self, species_id: str) -> list[dict]:
        if not species_id:
            return []
        _species_qs, meat_qs = self._read()
        return meat_qs.list_regions(species_id, active_only=False)

    def cuts(self, species_id: str) -> list[dict]:
        if not species_id:
            return []
        _species_qs, meat_qs = self._read()
        return meat_qs.list_cuts(species_id, active_only=False)

    # ── mutaciones ─────────────────────────────────────────────────────────
    def create_species(self, *, code: str, name: str) -> tuple[bool, str]:
        from backend.application.products.commands.product_meat_classification_commands import (
            CreateSpeciesCommand,
        )
        return self._run("create_species", lambda op, user: CreateSpeciesCommand(
            operation_id=op, code=code, name=name, user_id=user))

    def set_species_active(self, species_id: str, active: bool) -> tuple[bool, str]:
        from backend.application.products.commands.product_meat_classification_commands import (
            SetSpeciesActiveCommand,
        )
        return self._run("set_species_active", lambda op, user: SetSpeciesActiveCommand(
            operation_id=op, species_id=species_id, active=active, user_id=user))

    def create_region(self, *, species_id: str, code: str, name: str) -> tuple[bool, str]:
        from backend.application.products.commands.product_meat_classification_commands import (
            CreateAnatomicalRegionCommand,
        )
        return self._run("create_region", lambda op, user: CreateAnatomicalRegionCommand(
            operation_id=op, species_id=species_id, code=code, name=name, user_id=user))

    def set_region_active(self, region_id: str, active: bool) -> tuple[bool, str]:
        from backend.application.products.commands.product_meat_classification_commands import (
            SetAnatomicalRegionActiveCommand,
        )
        return self._run("set_region_active", lambda op, user: SetAnatomicalRegionActiveCommand(
            operation_id=op, region_id=region_id, active=active, user_id=user))

    def create_cut(self, *, species_id: str, anatomical_region_id: str, code: str,
                   name: str, cut_level: str, bone_status: str = "NOT_APPLICABLE",
                   fat_class: str = "NOT_APPLICABLE", quality_grade: str | None = None,
                   parent_cut_id: str | None = None) -> tuple[bool, str]:
        from backend.application.products.commands.product_meat_classification_commands import (
            CreateCutClassificationCommand,
        )
        return self._run("create_cut", lambda op, user: CreateCutClassificationCommand(
            operation_id=op, species_id=species_id,
            anatomical_region_id=anatomical_region_id, code=code, name=name,
            cut_level=cut_level, bone_status=bone_status, fat_class=fat_class,
            quality_grade=quality_grade or None, parent_cut_id=parent_cut_id or None,
            user_id=user))

    def set_cut_active(self, cut_id: str, active: bool) -> tuple[bool, str]:
        from backend.application.products.commands.product_meat_classification_commands import (
            SetCutClassificationActiveCommand,
        )
        return self._run("set_cut_active", lambda op, user: SetCutClassificationActiveCommand(
            operation_id=op, cut_id=cut_id, active=active, user_id=user))

    def _run(self, action: str, build) -> tuple[bool, str]:
        if self._write is None:
            return False, "Sin permisos para modificar la clasificación cárnica"
        from backend.shared.ids import new_uuid
        user_id = getattr(self._session, "user_id", None)
        try:
            command = build(new_uuid(), user_id)
            result = self._write()[action].execute(command)
        except Exception as exc:  # noqa: BLE001 — se muestra en la pantalla
            logger.exception("Clasificación cárnica: %s falló", action)
            return False, f"Error: {exc}"
        return bool(result.success), result.message
