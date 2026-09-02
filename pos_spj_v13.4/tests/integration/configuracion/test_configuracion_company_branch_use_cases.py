"""SET-5 follow-up — real CRUD for "Empresa y sucursales": get-or-create
the company profile, register a branch profile for an existing sucursal,
and edit it. Against a real (in-memory) SQLite born-clean schema.
"""

from __future__ import annotations

from datetime import time

import pytest

from backend.application.use_cases.configuracion.company_branch_use_cases import (
    RegisterBranchProfileUseCase,
    SaveCompanyProfileUseCase,
    UpdateBranchProfileUseCase,
)
from backend.domain.settings.exceptions import BranchProfileNotFoundError
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
def branch_id(conn):
    existing = conn.execute("SELECT id FROM sucursales LIMIT 1").fetchone()
    if existing:
        return existing[0]
    branch_id = new_uuid()
    conn.execute("INSERT INTO sucursales (id, nombre) VALUES (?, ?)", (branch_id, "Sucursal Test"))
    conn.commit()
    return branch_id


class TestSaveCompanyProfileUseCase:
    def _base_kwargs(self, **overrides):
        kwargs = dict(
            legal_name="Super Junior de Chihuahua SA de CV", default_currency="MXN",
            default_timezone="America/Chihuahua", default_locale="es-MX",
        )
        kwargs.update(overrides)
        return kwargs

    def test_creates_when_none_exists(self, conn):
        use_case = SaveCompanyProfileUseCase(conn)
        company = use_case.execute(**self._base_kwargs())
        assert company.legal_name == "Super Junior de Chihuahua SA de CV"
        fetched = SqliteCompanyProfileRepository(conn).get(company.id)
        assert fetched.default_currency == "MXN"

    def test_second_save_updates_the_same_row_not_a_new_one(self, conn):
        use_case = SaveCompanyProfileUseCase(conn)
        first = use_case.execute(**self._base_kwargs())
        second = use_case.execute(**self._base_kwargs(legal_name="Nombre actualizado", default_currency="usd"))
        assert second.id == first.id
        assert second.legal_name == "Nombre actualizado"
        assert second.default_currency == "USD"

        all_companies = SqliteCompanyProfileRepository(conn).list_active()
        assert len(all_companies) == 1

    def test_saves_logo_asset_reference(self, conn):
        asset_id = new_uuid()
        use_case = SaveCompanyProfileUseCase(conn)
        company = use_case.execute(**self._base_kwargs(logo_asset_id=asset_id))
        assert company.logo_asset.asset_id == asset_id

        updated = use_case.execute(**self._base_kwargs(logo_asset_id=""))
        assert updated.logo_asset is None


class TestRegisterBranchProfileUseCase:
    def test_registers_a_profile_for_an_existing_branch(self, conn, branch_id):
        use_case = RegisterBranchProfileUseCase(conn)
        profile = use_case.execute(
            branch_id=branch_id, code="SUC-01", name="Sucursal San Bartolo",
            timezone="America/Chihuahua", locale="es-MX", opening_time=time(9, 0),
            closing_time=time(20, 0), operation_days=("MON", "TUE"),
        )
        assert profile.branch_id == branch_id
        assert profile.opening_time == time(9, 0)
        fetched = SqliteBranchProfileRepository(conn).get(branch_id)
        assert fetched.code == "SUC-01"

    def test_rejects_unknown_branch_id_format(self, conn):
        use_case = RegisterBranchProfileUseCase(conn)
        with pytest.raises(ValueError):
            use_case.execute(branch_id="not-a-uuid", code="X", name="X")


class TestUpdateBranchProfileUseCase:
    def test_updates_name_hours_and_ticket_texts(self, conn, branch_id):
        RegisterBranchProfileUseCase(conn).execute(branch_id=branch_id, code="SUC-01", name="Original")
        use_case = UpdateBranchProfileUseCase(conn)
        updated = use_case.execute(
            branch_id=branch_id, name="Renombrada", timezone="America/Chihuahua", locale="es-MX",
            opening_time=time(8, 0), closing_time=time(21, 0), operation_days=("MON",),
            ticket_header="Bienvenido", ticket_footer="Gracias",
        )
        assert updated.name == "Renombrada"
        assert updated.opening_time == time(8, 0)
        assert updated.ticket_header == "Bienvenido"

    def test_unknown_branch_raises(self, conn):
        use_case = UpdateBranchProfileUseCase(conn)
        with pytest.raises(BranchProfileNotFoundError):
            use_case.execute(branch_id=new_uuid(), name="X")
