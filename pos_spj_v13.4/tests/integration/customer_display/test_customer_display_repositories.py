"""SET-17 — SqliteCustomerDisplayRepository + SqliteDisplayLayoutRepository
against a real (in-memory) SQLite born-clean schema (migration 217).
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.domain.customer_display.entities.customer_display import CustomerDisplay
from backend.domain.customer_display.entities.display_layout import DisplayLayout
from backend.domain.customer_display.enums import CustomerDisplayMode, CustomerDisplaySectionCode
from backend.domain.customer_display.value_objects.display_section import DisplaySection
from backend.domain.settings.entities.workstation import Workstation
from backend.domain.settings.enums import WorkstationType
from backend.infrastructure.db.repositories.customer_display.customer_display_repository import (
    SqliteCustomerDisplayRepository,
)
from backend.infrastructure.db.repositories.customer_display.display_layout_repository import (
    SqliteDisplayLayoutRepository,
)
from backend.infrastructure.db.repositories.settings.workstation_repository import (
    SqliteWorkstationRepository,
)
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


@pytest.fixture
def display_repo(conn):
    return SqliteCustomerDisplayRepository(conn)


@pytest.fixture
def layout_repo(conn):
    return SqliteDisplayLayoutRepository(conn)


def _existing_workstation_id(conn) -> str:
    branch_id = new_uuid()
    conn.execute("INSERT INTO sucursales (id, nombre) VALUES (?, ?)", (branch_id, "Sucursal de prueba"))
    workstation = Workstation.create(
        branch_id=branch_id, code="POS-01", name="Caja 1", workstation_type=WorkstationType.POS,
    )
    SqliteWorkstationRepository(conn).save(workstation)
    conn.commit()
    return workstation.id


def _section(**overrides) -> DisplaySection:
    kwargs = dict(code=CustomerDisplaySectionCode.MESSAGE, order=0)
    kwargs.update(overrides)
    return DisplaySection.create(**kwargs)


class TestCustomerDisplayRepository:
    def test_save_get_roundtrip(self, conn, display_repo):
        workstation_id = _existing_workstation_id(conn)
        display = CustomerDisplay.create(workstation_id=workstation_id, name="Pantalla Caja 1")
        display_repo.save(display)
        conn.commit()

        fetched = display_repo.get(display.id)
        assert fetched.workstation_id == workstation_id
        assert fetched.name == "Pantalla Caja 1"
        assert fetched.current_mode is CustomerDisplayMode.IDLE

    def test_upsert_persists_mode_change(self, conn, display_repo):
        workstation_id = _existing_workstation_id(conn)
        display = CustomerDisplay.create(workstation_id=workstation_id, name="Pantalla Caja 1")
        display_repo.save(display)
        conn.commit()

        display.set_mode(CustomerDisplayMode.CART)
        display_repo.save(display)
        conn.commit()

        assert display_repo.get(display.id).current_mode is CustomerDisplayMode.CART

    def test_list_by_workstation_and_list_active(self, conn, display_repo):
        workstation_id = _existing_workstation_id(conn)
        active = CustomerDisplay.create(workstation_id=workstation_id, name="Pantalla activa")
        inactive = CustomerDisplay.create(workstation_id=workstation_id, name="Pantalla inactiva")
        inactive.deactivate()
        display_repo.save(active)
        display_repo.save(inactive)
        conn.commit()

        by_workstation = display_repo.list_by_workstation(workstation_id)
        assert {d.id for d in by_workstation} == {active.id, inactive.id}

        active_only = display_repo.list_active()
        assert active.id in {d.id for d in active_only}
        assert inactive.id not in {d.id for d in active_only}


class TestDisplayLayoutRepository:
    def test_save_get_roundtrip_preserves_sections(self, conn, layout_repo):
        layout = DisplayLayout.create(mode=CustomerDisplayMode.CART, sections=[
            _section(code=CustomerDisplaySectionCode.CUSTOMER_NAME, order=0),
            _section(code=CustomerDisplaySectionCode.ITEMS, order=1, enabled=False),
        ])
        layout_repo.save(layout)
        conn.commit()

        fetched = layout_repo.get(layout.id)
        assert fetched.mode is CustomerDisplayMode.CART
        assert len(fetched.sections) == 2
        assert fetched.enabled_codes() == (CustomerDisplaySectionCode.CUSTOMER_NAME,)

    def test_list_by_mode(self, conn, layout_repo):
        cart = DisplayLayout.create(mode=CustomerDisplayMode.CART, sections=[_section()])
        idle = DisplayLayout.create(mode=CustomerDisplayMode.IDLE, sections=[_section()])
        layout_repo.save(cart)
        layout_repo.save(idle)
        conn.commit()

        assert [l.id for l in layout_repo.list_by_mode(CustomerDisplayMode.CART)] == [cart.id]

    def test_get_active_for_mode(self, conn, layout_repo):
        cart = DisplayLayout.create(mode=CustomerDisplayMode.CART, sections=[_section()])
        layout_repo.save(cart)
        conn.commit()
        assert layout_repo.get_active_for_mode(CustomerDisplayMode.CART).id == cart.id
        assert layout_repo.get_active_for_mode(CustomerDisplayMode.THANK_YOU) is None

    def test_unique_index_blocks_two_active_layouts_for_same_mode(self, conn, layout_repo):
        first = DisplayLayout.create(mode=CustomerDisplayMode.CART, sections=[_section()])
        second = DisplayLayout.create(mode=CustomerDisplayMode.CART, sections=[_section()])
        layout_repo.save(first)
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            layout_repo.save(second)
            conn.commit()
        conn.rollback()

    def test_deactivating_one_allows_activating_another_for_same_mode(self, conn, layout_repo):
        first = DisplayLayout.create(mode=CustomerDisplayMode.CART, sections=[_section()])
        layout_repo.save(first)
        conn.commit()

        first.deactivate()
        layout_repo.save(first)
        conn.commit()

        second = DisplayLayout.create(mode=CustomerDisplayMode.CART, sections=[_section()])
        layout_repo.save(second)
        conn.commit()

        assert layout_repo.get_active_for_mode(CustomerDisplayMode.CART).id == second.id
