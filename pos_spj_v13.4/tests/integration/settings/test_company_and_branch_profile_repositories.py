"""SET-5 — CompanyProfile / BranchProfile infrastructure repositories
against a real (in-memory) SQLite born-clean schema.
"""

from __future__ import annotations

import sqlite3
from datetime import time
from decimal import Decimal

import pytest

from backend.domain.settings.entities.branch_profile import BranchProfile
from backend.domain.settings.entities.company_profile import CompanyProfile
from backend.domain.settings.value_objects.asset_reference import AssetReference
from backend.domain.settings.value_objects.map_reference import MapReference
from backend.infrastructure.db.repositories.settings.branch_profile_repository import (
    SqliteBranchProfileRepository,
)
from backend.infrastructure.db.repositories.settings.company_profile_repository import (
    SqliteCompanyProfileRepository,
)
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


@pytest.fixture
def company_repo(conn):
    return SqliteCompanyProfileRepository(conn)


@pytest.fixture
def branch_repo(conn):
    return SqliteBranchProfileRepository(conn)


def _existing_branch_id(conn) -> str:
    """BranchProfile.branch_id FKs to `sucursales` — insert the minimal
    row a profile can legally extend."""
    branch_id = new_uuid()
    conn.execute("INSERT INTO sucursales (id, nombre) VALUES (?, ?)", (branch_id, "Sucursal de prueba"))
    return branch_id


class TestCompanyProfileRepository:
    def test_round_trips_all_fields(self, conn, company_repo):
        asset = AssetReference.create(new_uuid())
        company = CompanyProfile.create(
            legal_name="Super Junior de Chihuahua SA de CV", default_currency="MXN",
            default_timezone="America/Chihuahua", default_locale="es-MX",
            commercial_name="Super Junior", tax_id="SJC010101AAA",
            logo_asset=asset, address="Av. Universidad 100", phone="+5216141234567",
            email="ventas@sjc.mx", website="https://sjc.mx",
            social_networks={"facebook": "https://facebook.com/sjc"},
            fiscal_regime_reference="601",
        )
        company_repo.save(company)
        conn.commit()

        fetched = company_repo.get(company.id)
        assert fetched.legal_name == company.legal_name
        assert fetched.logo_asset.asset_id == asset.asset_id
        assert fetched.social_networks == {"facebook": "https://facebook.com/sjc"}
        assert fetched.default_currency == "MXN"
        assert fetched.fiscal_regime_reference == "601"

    def test_update_via_save_upsert(self, conn, company_repo):
        company = CompanyProfile.create(
            legal_name="SJC", default_currency="MXN", default_timezone="America/Chihuahua",
            default_locale="es-MX",
        )
        company_repo.save(company)
        conn.commit()

        company.update_contact_info(address="Nueva Dirección")
        company_repo.save(company)
        conn.commit()

        fetched = company_repo.get(company.id)
        assert fetched.address == "Nueva Dirección"

    def test_list_active_excludes_inactive(self, conn, company_repo):
        active = CompanyProfile.create(
            legal_name="Activa", default_currency="MXN", default_timezone="America/Chihuahua",
            default_locale="es-MX",
        )
        inactive = CompanyProfile.create(
            legal_name="Inactiva", default_currency="MXN", default_timezone="America/Chihuahua",
            default_locale="es-MX",
        )
        inactive.deactivate()
        company_repo.save(active)
        company_repo.save(inactive)
        conn.commit()

        results = company_repo.list_active()
        assert [profile.legal_name for profile in results] == ["Activa"]

    def test_without_logo_round_trips_none(self, conn, company_repo):
        company = CompanyProfile.create(
            legal_name="Sin Logo", default_currency="MXN", default_timezone="America/Chihuahua",
            default_locale="es-MX",
        )
        company_repo.save(company)
        conn.commit()
        assert company_repo.get(company.id).logo_asset is None


class TestBranchProfileRepository:
    def test_round_trips_all_fields(self, conn, branch_repo):
        branch_id = _existing_branch_id(conn)
        warehouse_id = new_uuid()
        workstation_profile_id = new_uuid()
        branch = BranchProfile.create(
            branch_id=branch_id, code="SUC-01", name="Sucursal San Bartolo",
            address="Calle Falsa 123", phone="+5216141234567", timezone="America/Chihuahua",
            locale="es-MX", opening_time=time(8, 0), closing_time=time(20, 0),
            operation_days=("mon", "tue", "wed", "thu", "fri", "sat"),
            warehouse_ids=(warehouse_id,), default_workstation_profile_id=workstation_profile_id,
            ticket_header="Bienvenido", ticket_footer="Gracias por su compra",
            social_links={"instagram": "https://instagram.com/sjc"},
            map_reference=MapReference.create(
                latitude=Decimal("28.632996"), longitude=Decimal("-106.069099"), place_id="ChIJxyz",
            ),
        )
        branch_repo.save(branch)
        conn.commit()

        fetched = branch_repo.get(branch_id)
        assert fetched.id == branch_id
        assert fetched.code == "SUC-01"
        assert fetched.opening_time == time(8, 0)
        assert fetched.closing_time == time(20, 0)
        assert fetched.operation_days == ("MON", "TUE", "WED", "THU", "FRI", "SAT")
        assert fetched.warehouse_ids == (warehouse_id,)
        assert fetched.default_workstation_profile_id == workstation_profile_id
        assert fetched.ticket_header == "Bienvenido"
        assert fetched.social_links == {"instagram": "https://instagram.com/sjc"}
        assert fetched.map_reference.latitude == Decimal("28.632996")
        assert fetched.map_reference.place_id == "ChIJxyz"

    def test_branch_id_must_reference_existing_sucursal(self, conn, branch_repo):
        orphan = BranchProfile.create(branch_id=new_uuid(), code="SUC-99", name="Fantasma")
        with pytest.raises(sqlite3.IntegrityError):
            branch_repo.save(orphan)
            conn.commit()
        conn.rollback()

    def test_code_uniqueness_enforced(self, conn, branch_repo):
        branch_id_a, branch_id_b = _existing_branch_id(conn), _existing_branch_id(conn)
        branch_repo.save(BranchProfile.create(branch_id=branch_id_a, code="SUC-01", name="A"))
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            branch_repo.save(BranchProfile.create(branch_id=branch_id_b, code="SUC-01", name="B"))
            conn.commit()
        conn.rollback()

    def test_saving_the_same_branch_id_again_upserts_rather_than_duplicates(self, conn, branch_repo):
        # BranchProfile.id IS branch_id (see the entity's docstring) — two
        # `.create()` calls for the same branch_id therefore produce the
        # same row id, and `save()`'s ON CONFLICT(id) DO UPDATE makes this
        # an upsert, not a collision. `UNIQUE(branch_id)` in the schema is
        # intentionally redundant with the `id` PK — it documents the
        # invariant even though it can never actually fire.
        branch_id = _existing_branch_id(conn)
        branch_repo.save(BranchProfile.create(branch_id=branch_id, code="SUC-01", name="A"))
        conn.commit()
        branch_repo.save(BranchProfile.create(branch_id=branch_id, code="SUC-02", name="B"))
        conn.commit()

        fetched = branch_repo.get(branch_id)
        assert fetched.code == "SUC-02"
        assert len(branch_repo.list_active()) == 1

    def test_get_by_code(self, conn, branch_repo):
        branch_id = _existing_branch_id(conn)
        branch_repo.save(BranchProfile.create(branch_id=branch_id, code="SUC-01", name="A"))
        conn.commit()
        assert branch_repo.get_by_code("SUC-01").branch_id == branch_id
        assert branch_repo.get_by_code("MISSING") is None

    def test_without_opening_hours_or_map_round_trips_none(self, conn, branch_repo):
        branch_id = _existing_branch_id(conn)
        branch_repo.save(BranchProfile.create(branch_id=branch_id, code="SUC-01", name="A"))
        conn.commit()
        fetched = branch_repo.get(branch_id)
        assert fetched.opening_time is None
        assert fetched.closing_time is None
        assert fetched.map_reference.latitude is None
        assert fetched.map_reference.is_set() is False

    def test_list_active_excludes_inactive(self, conn, branch_repo):
        branch_id_active, branch_id_inactive = _existing_branch_id(conn), _existing_branch_id(conn)
        active = BranchProfile.create(branch_id=branch_id_active, code="SUC-01", name="Activa")
        inactive = BranchProfile.create(branch_id=branch_id_inactive, code="SUC-02", name="Inactiva")
        inactive.deactivate()
        branch_repo.save(active)
        branch_repo.save(inactive)
        conn.commit()
        results = branch_repo.list_active()
        assert [profile.code for profile in results] == ["SUC-01"]

    def test_update_via_save_upsert(self, conn, branch_repo):
        branch_id = _existing_branch_id(conn)
        branch = BranchProfile.create(branch_id=branch_id, code="SUC-01", name="A")
        branch_repo.save(branch)
        conn.commit()

        branch.set_ticket_texts(header="Nuevo encabezado")
        branch_repo.save(branch)
        conn.commit()

        assert branch_repo.get(branch_id).ticket_header == "Nuevo encabezado"
