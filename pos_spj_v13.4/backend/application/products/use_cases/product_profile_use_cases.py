"""Use cases de perfiles de calidad, vida útil y logística (PROD-8).

`ProfileRepository` (shelf-life/quality/logistics, Decimal-correct, full
save+get) existía completo desde antes de esta fase, pero sus únicos
consumidores eran dos QueryServices de sólo lectura
(`integration_query_services.py`, `slaughter_config_query_service.py`) —
ningún caso de uso real podía FIJAR el perfil de un producto. Cada mutación
exige ``PRODUCTS_EDIT`` (mismo permiso que edita el maestro — estos perfiles
son datos extendidos del producto, sin un permiso granular propio en §38).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from backend.application.products.audit import record_product_audit_entry
from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_profile_commands import (
    SetLogisticsProfileCommand,
    SetQualityProfileCommand,
    SetShelfLifeProfileCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.domain.products.entities.product_logistics_profile import (
    ProductLogisticsProfile,
)
from backend.domain.products.entities.product_quality_profile import (
    ProductQualityProfile,
)
from backend.domain.products.entities.product_shelf_life_profile import (
    ProductShelfLifeProfile,
)
from backend.domain.products.exceptions import ProductsDomainError
from backend.domain.products.value_objects.temperature_range import TemperatureRange
from backend.infrastructure.db.repositories.products.profile_repository import (
    ProfileRepository,
)

logger = logging.getLogger("spj.products.profile_use_cases")


@dataclass(frozen=True)
class ProfileResult:
    success: bool
    product_id: str | None
    message: str


class _Base:
    def __init__(self, connection,
                 authorization: ProductsAuthorizationPolicy | None = None) -> None:
        self._conn = connection
        self._repo = ProfileRepository(connection)
        self._auth = authorization or ProductsAuthorizationPolicy.permissive_for_tests()

    def _rollback(self) -> None:
        rb = getattr(self._conn, "rollback", None)
        if rb is not None:
            rb()


class SetShelfLifeProfileUseCase(_Base):
    name = "SetShelfLifeProfileUseCase"

    def execute(self, command: SetShelfLifeProfileCommand) -> ProfileResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.EDIT)
        try:
            profile = ProductShelfLifeProfile(
                product_id=command.product_id,
                shelf_life_days=command.shelf_life_days,
                minimum_remaining_for_receipt=command.minimum_remaining_for_receipt,
                minimum_remaining_for_sale=command.minimum_remaining_for_sale,
                storage_condition=command.storage_condition,
                opened_shelf_life_days=command.opened_shelf_life_days,
                frozen_shelf_life_days=command.frozen_shelf_life_days,
                thawed_shelf_life_days=command.thawed_shelf_life_days,
                effective_from=command.effective_from,
                effective_to=command.effective_to)
        except ProductsDomainError as exc:
            return ProfileResult(False, None, str(exc))
        try:
            self._repo.save_shelf_life(profile)
            record_product_audit_entry(
                self._conn, action="PRODUCT_SHELF_LIFE_PROFILE_SET",
                entity_id=command.product_id, user_id=command.user_id,
                operation_id=command.operation_id,
                after={"shelf_life_days": profile.shelf_life_days})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("set shelf-life profile failed op=%s", command.operation_id)
            raise
        return ProfileResult(True, command.product_id, "PRODUCT_SHELF_LIFE_PROFILE_SET")


class SetQualityProfileUseCase(_Base):
    name = "SetQualityProfileUseCase"

    def execute(self, command: SetQualityProfileCommand) -> ProfileResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.EDIT)
        try:
            profile = ProductQualityProfile(
                product_id=command.product_id,
                inspection_required=command.inspection_required,
                temperature_required=command.temperature_required,
                weight_check_required=command.weight_check_required,
                organoleptic_check_required=command.organoleptic_check_required,
                microbiological_test_required=command.microbiological_test_required,
                fat_pct_min=command.fat_pct_min, fat_pct_max=command.fat_pct_max,
                moisture_pct_min=command.moisture_pct_min,
                moisture_pct_max=command.moisture_pct_max,
                color_requirement=command.color_requirement,
                odor_requirement=command.odor_requirement,
                packaging_requirement=command.packaging_requirement,
                documentation_requirement=command.documentation_requirement,
                quarantine_required=command.quarantine_required)
        except ProductsDomainError as exc:
            return ProfileResult(False, None, str(exc))
        try:
            self._repo.save_quality(profile)
            record_product_audit_entry(
                self._conn, action="PRODUCT_QUALITY_PROFILE_SET",
                entity_id=command.product_id, user_id=command.user_id,
                operation_id=command.operation_id,
                after={"inspection_required": profile.inspection_required,
                      "quarantine_required": profile.quarantine_required})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("set quality profile failed op=%s", command.operation_id)
            raise
        return ProfileResult(True, command.product_id, "PRODUCT_QUALITY_PROFILE_SET")


class SetLogisticsProfileUseCase(_Base):
    name = "SetLogisticsProfileUseCase"

    def execute(self, command: SetLogisticsProfileCommand) -> ProfileResult:
        command.validate()
        self._auth.require(command.user_id or "", ProductPermissions.EDIT)
        try:
            storage_temp = (TemperatureRange(
                Decimal(command.storage_temp_min), Decimal(command.storage_temp_max),
                command.storage_temp_unit)
                if command.storage_temp_min is not None
                and command.storage_temp_max is not None else None)
            transport_temp = (TemperatureRange(
                Decimal(command.transport_temp_min), Decimal(command.transport_temp_max),
                command.transport_temp_unit)
                if command.transport_temp_min is not None
                and command.transport_temp_max is not None else None)
            profile = ProductLogisticsProfile(
                product_id=command.product_id, gross_weight=command.gross_weight,
                net_weight=command.net_weight, weight_unit=command.weight_unit,
                dimensions=command.dimensions, storage_temperature=storage_temp,
                transport_temperature=transport_temp, fragile=command.fragile,
                perishable=command.perishable, frozen=command.frozen,
                chilled=command.chilled, stackable=command.stackable,
                shelf_life_days=command.shelf_life_days,
                open_package_shelf_life_days=command.open_package_shelf_life_days)
        except ProductsDomainError as exc:
            return ProfileResult(False, None, str(exc))
        try:
            self._repo.save_logistics(profile)
            record_product_audit_entry(
                self._conn, action="PRODUCT_LOGISTICS_PROFILE_SET",
                entity_id=command.product_id, user_id=command.user_id,
                operation_id=command.operation_id,
                after={"requires_cold_chain": profile.requires_cold_chain})
            self._conn.commit()
        except Exception:
            self._rollback()
            logger.exception("set logistics profile failed op=%s", command.operation_id)
            raise
        return ProfileResult(True, command.product_id, "PRODUCT_LOGISTICS_PROFILE_SET")
