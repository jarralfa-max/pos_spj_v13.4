"""PROD-8 — perfiles de calidad, vida útil y logística.

Antes de esta fase, `ProfileRepository` (shelf-life/quality/logistics,
Decimal-correct, save+get completos) tenía sólo consumidores de LECTURA
(`integration_query_services.py`, `slaughter_config_query_service.py`) — nada
podía FIJAR el perfil de un producto real. Estos tests prueban la escritura
de punta a punta para los tres perfiles.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_profile_commands import (
    SetLogisticsProfileCommand,
    SetQualityProfileCommand,
    SetShelfLifeProfileCommand,
)
from backend.application.products.permissions import ProductPermissions
from backend.application.products.use_cases.product_profile_use_cases import (
    SetLogisticsProfileUseCase,
    SetQualityProfileUseCase,
    SetShelfLifeProfileUseCase,
)
from backend.domain.products.exceptions import ProductPermissionDeniedError
from backend.infrastructure.db.repositories.products.profile_repository import (
    ProfileRepository,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema

_P = ProductPermissions


class _Checker:
    def __init__(self, granted):
        self._granted = set(granted)

    def has_permission(self, user_id, code):
        return code in self._granted


_ALL = ProductsAuthorizationPolicy(_Checker({_P.EDIT}))


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    c.commit()
    yield c
    c.close()


class TestShelfLifeProfile:
    def test_set_shelf_life(self, conn):
        r = SetShelfLifeProfileUseCase(conn, _ALL).execute(SetShelfLifeProfileCommand(
            operation_id="op", product_id="prod-1", shelf_life_days=21,
            minimum_remaining_for_receipt=5, minimum_remaining_for_sale=2,
            storage_condition="CHILLED", user_id="u1"))
        assert r.success
        p = ProfileRepository(conn).get_shelf_life("prod-1")
        assert p.shelf_life_days == 21 and p.storage_condition == "CHILLED"

    def test_receipt_minimum_cannot_exceed_total(self, conn):
        r = SetShelfLifeProfileUseCase(conn, _ALL).execute(SetShelfLifeProfileCommand(
            operation_id="op", product_id="prod-1", shelf_life_days=5,
            minimum_remaining_for_receipt=10, user_id="u1"))
        assert not r.success

    def test_requires_permission(self, conn):
        no_perm = ProductsAuthorizationPolicy(_Checker(set()))
        with pytest.raises(ProductPermissionDeniedError):
            SetShelfLifeProfileUseCase(conn, no_perm).execute(SetShelfLifeProfileCommand(
                operation_id="op", product_id="prod-1", shelf_life_days=10))

    def test_writes_audit_entry(self, conn):
        SetShelfLifeProfileUseCase(conn, _ALL).execute(SetShelfLifeProfileCommand(
            operation_id="op", product_id="prod-1", shelf_life_days=10, user_id="u1"))
        row = conn.execute(
            "SELECT action FROM product_audit_log WHERE entity_id='prod-1'").fetchone()
        assert row["action"] == "PRODUCT_SHELF_LIFE_PROFILE_SET"


class TestQualityProfile:
    def test_set_quality_profile(self, conn):
        r = SetQualityProfileUseCase(conn, _ALL).execute(SetQualityProfileCommand(
            operation_id="op", product_id="prod-1", inspection_required=True,
            fat_pct_min="10", fat_pct_max="25", quarantine_required=True,
            user_id="u1"))
        assert r.success
        p = ProfileRepository(conn).get_quality("prod-1")
        assert p.inspection_required and p.fat_pct_min == Decimal("10")
        assert p.quarantine_required

    def test_fat_band_min_over_max_rejected(self, conn):
        r = SetQualityProfileUseCase(conn, _ALL).execute(SetQualityProfileCommand(
            operation_id="op", product_id="prod-1", fat_pct_min="30",
            fat_pct_max="10", user_id="u1"))
        assert not r.success


class TestLogisticsProfile:
    def test_set_logistics_profile_with_cold_chain(self, conn):
        r = SetLogisticsProfileUseCase(conn, _ALL).execute(SetLogisticsProfileCommand(
            operation_id="op", product_id="prod-1", gross_weight="1.2",
            net_weight="1.0", frozen=True,
            storage_temp_min="-18", storage_temp_max="-15", user_id="u1"))
        assert r.success
        p = ProfileRepository(conn).get_logistics("prod-1")
        # frozen ⇒ cadena de frío forzada por el propio entity (§18)
        assert p.requires_cold_chain is True
        assert p.storage_temperature.minimum == Decimal("-18")

    def test_net_weight_cannot_exceed_gross(self, conn):
        r = SetLogisticsProfileUseCase(conn, _ALL).execute(SetLogisticsProfileCommand(
            operation_id="op", product_id="prod-1", gross_weight="1.0",
            net_weight="2.0", user_id="u1"))
        assert not r.success

    def test_no_cold_chain_when_not_frozen_or_chilled(self, conn):
        r = SetLogisticsProfileUseCase(conn, _ALL).execute(SetLogisticsProfileCommand(
            operation_id="op", product_id="prod-1", gross_weight="1.0", user_id="u1"))
        assert r.success
        p = ProfileRepository(conn).get_logistics("prod-1")
        assert p.requires_cold_chain is False
