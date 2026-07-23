"""Slaughter-preparation contract query services (§25).

Read-only services the future slaughter/production module consults to learn the
technical model defined by Products:

* ``AnimalInputConfigurationQueryService`` — the live-animal input product config;
* ``CarcassProductConfigurationQueryService`` — the carcass output product config;
* ``ActiveYieldProfileQueryService`` — the ACTIVE yield profile for an input;
* ``ActiveCuttingSchemeQueryService`` — the ACTIVE cutting scheme for an input;
* ``SlaughterOutputDefinitionQueryService`` — the union of expected outputs.

These services ONLY read. Products never records real execution (live/carcass
weight, mortality, condemnation, real yield, slaughter lot); that is the
operational module's job. There are deliberately no write/execute methods here.
"""

from __future__ import annotations

from backend.application.products.queries.slaughter_config_dtos import (
    ActiveCuttingSchemeDTO,
    ActiveYieldProfileDTO,
    AnimalInputConfigurationDTO,
    CarcassProductConfigurationDTO,
    CuttingOutputDTO,
    SlaughterOutputDefinitionDTO,
    YieldOutputDTO,
)
from backend.domain.products.enums import MEAT_PRODUCT_TYPES, ProductType
from backend.infrastructure.db.repositories.products.cutting_scheme_repository import (
    CuttingSchemeRepository,
)
from backend.infrastructure.db.repositories.products.profile_repository import (
    ProfileRepository,
)
from backend.infrastructure.db.repositories.products.yield_repository import (
    YieldRepository,
)


def _product_row(conn, product_id: str):
    return conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()


class AnimalInputConfigurationQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def get(self, product_id: str) -> AnimalInputConfigurationDTO | None:
        row = _product_row(self._conn, product_id)
        if row is None or row["product_type"] != ProductType.LIVE_ANIMAL.value:
            return None
        return AnimalInputConfigurationDTO(
            product_id=row["id"], product_type=row["product_type"],
            species_id=row["species_id"], base_unit_id=row["base_unit_id"],
            catch_weight_enabled=bool(row["catch_weight_enabled"]),
            lot_controlled=bool(row["lot_controlled"]),
            traceability_required=bool(row["traceability_required"]),
            quality_controlled=bool(row["quality_controlled"]))


class CarcassProductConfigurationQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._profiles = ProfileRepository(connection)

    def get(self, product_id: str) -> CarcassProductConfigurationDTO | None:
        row = _product_row(self._conn, product_id)
        carcass_types = {ProductType.CARCASS.value, ProductType.HALF_CARCASS.value,
                         ProductType.QUARTER.value}
        if row is None or row["product_type"] not in carcass_types:
            return None
        shelf = self._profiles.get_shelf_life(product_id)
        logistics = self._profiles.get_logistics(product_id)
        quality = self._profiles.get_quality(product_id)
        return CarcassProductConfigurationDTO(
            product_id=row["id"], product_type=row["product_type"],
            species_id=row["species_id"], base_unit_id=row["base_unit_id"],
            shelf_life_days=shelf.shelf_life_days if shelf else None,
            requires_cold_chain=bool(logistics.requires_cold_chain) if logistics else False,
            inspection_required=bool(quality.inspection_required) if quality else False,
            quarantine_required=bool(quality.quarantine_required) if quality else False)


class ActiveYieldProfileQueryService:
    def __init__(self, connection) -> None:
        self._yields = YieldRepository(connection)

    def get_for_input(self, input_product_id: str) -> ActiveYieldProfileDTO | None:
        version = self._yields.active_version_for_input(input_product_id)
        if version is None:
            return None
        profile = self._yields.get_profile(version.yield_profile_id)
        outputs = tuple(
            YieldOutputDTO(
                product_id=o.product_id, output_type=o.output_type,
                expected_yield_pct=o.expected_yield_pct,
                minimum_yield_pct=o.minimum_yield_pct,
                maximum_yield_pct=o.maximum_yield_pct, unit_id=o.unit_id,
                cost_allocation_weight=o.cost_allocation_weight)
            for o in version.outputs)
        return ActiveYieldProfileDTO(
            yield_profile_id=version.yield_profile_id, version_id=version.id,
            version_number=version.version_number,
            species_id=profile.species_id if profile else None,
            input_product_id=input_product_id, tolerance_pct=version.tolerance_pct,
            outputs=outputs)


class ActiveCuttingSchemeQueryService:
    def __init__(self, connection) -> None:
        self._cutting = CuttingSchemeRepository(connection)

    def get_for_input(self, input_product_id: str) -> ActiveCuttingSchemeDTO | None:
        version = self._cutting.active_version_for_input(input_product_id)
        if version is None:
            return None
        scheme = self._cutting.get_scheme(version.cutting_scheme_id)
        outputs = tuple(
            CuttingOutputDTO(
                product_id=o.product_id, output_type=o.output_type,
                measure_kind=o.measure_kind.value, quantity=o.quantity,
                unit_id=o.unit_id, bone_status=o.bone_status.value,
                cut_level=o.cut_level.value if o.cut_level else None)
            for o in version.outputs)
        return ActiveCuttingSchemeDTO(
            cutting_scheme_id=version.cutting_scheme_id, version_id=version.id,
            version_number=version.version_number,
            species_id=scheme.species_id if scheme else "",
            input_product_id=input_product_id,
            cut_level=scheme.cut_level.value if scheme else "PRIMARY",
            outputs=outputs)


class SlaughterOutputDefinitionQueryService:
    """Union of expected outputs (yield + cutting) for an input product (§25)."""

    def __init__(self, connection) -> None:
        self._conn = connection
        self._yield_qs = ActiveYieldProfileQueryService(connection)
        self._cutting_qs = ActiveCuttingSchemeQueryService(connection)

    def get_for_input(self, input_product_id: str) -> SlaughterOutputDefinitionDTO:
        row = _product_row(self._conn, input_product_id)
        species_id = row["species_id"] if row else None
        yp = self._yield_qs.get_for_input(input_product_id)
        cs = self._cutting_qs.get_for_input(input_product_id)
        return SlaughterOutputDefinitionDTO(
            input_product_id=input_product_id, species_id=species_id,
            yield_output_product_ids=tuple(o.product_id for o in yp.outputs) if yp else (),
            cutting_output_product_ids=tuple(o.product_id for o in cs.outputs) if cs else ())

    def is_meat_input(self, input_product_id: str) -> bool:
        row = _product_row(self._conn, input_product_id)
        return bool(row) and ProductType(row["product_type"]) in MEAT_PRODUCT_TYPES
