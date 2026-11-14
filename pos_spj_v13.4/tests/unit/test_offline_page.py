"""SET-23 repegado — `OfflinePage` widget smoke tests, against the REAL
`build_configuracion_view()` factory and real (in-memory) SQLite —
mirrors the "verified end-to-end through the real factory" discipline
every prior Configuración CRUD round in this track used. The Cache
diagnostic card is verified to have NO create/edit/status buttons —
deliberately read-only (see `offline_page.py`'s module docstring).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

QtWidgets = pytest.importorskip(
    "PyQt5.QtWidgets", reason="PyQt5 desktop runtime unavailable", exc_type=ImportError)
QApplication = QtWidgets.QApplication

from backend.application.configuracion.permissions import ConfiguracionPermissions  # noqa: E402
from backend.application.use_cases.configuracion.offline_management_use_cases import (  # noqa: E402
    CreateCacheExpirationPolicyUseCase,
)
from backend.domain.offline.entities.offline_cache_entry import OfflineCacheEntry  # noqa: E402
from backend.domain.settings.entities.workstation import Workstation  # noqa: E402
from backend.domain.settings.enums import WorkstationType  # noqa: E402
from backend.infrastructure.db.repositories.offline.offline_cache_entry_repository import (  # noqa: E402
    SqliteOfflineCacheEntryRepository,
)
from backend.infrastructure.db.repositories.settings.workstation_repository import (  # noqa: E402
    SqliteWorkstationRepository,
)
from backend.shared.ids import new_uuid  # noqa: E402
from frontend.desktop.modules.configuracion.configuracion_routes import (  # noqa: E402
    build_configuracion_view,
)
from tests.integration._born_clean_db import make_db  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _FakeSession:
    def __init__(self, permissions=()) -> None:
        self.user_id = new_uuid()
        self.is_active = True
        self.active_branch_id = "branch-1"
        self._permissions = set(permissions)

    def tiene_permiso(self, code: str) -> bool:
        return code in self._permissions

    def es_admin(self) -> bool:
        return False


def _all_permissions() -> set:
    return {p for p in vars(ConfiguracionPermissions).values() if isinstance(p, str)}


def _view(app, conn):
    class _FakeContainer:
        db = conn
        session = _FakeSession(_all_permissions())

    return build_configuracion_view(connection=_FakeContainer.db, session_context=_FakeContainer.session)


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


def _seed_workstation(conn) -> str:
    branch_id = new_uuid()
    conn.execute("INSERT INTO sucursales (id, nombre) VALUES (?, ?)", (branch_id, "Sucursal de prueba"))
    workstation = Workstation.create(
        branch_id=branch_id, code="POS-01", name="Caja 1", workstation_type=WorkstationType.POS)
    SqliteWorkstationRepository(conn).save(workstation)
    conn.commit()
    return workstation.id


class TestOfflinePageStructure:
    def test_builds_via_the_real_route(self, app, conn):
        view = _view(app, conn)
        view.show_route("config_offline")
        page = view._pages["config_offline"]

        assert page.table.accessibleName() == "Listado de Offline"
        assert page.cache_table.accessibleName() == "Entradas de caché por estación"

    def test_policy_buttons_present_and_cache_card_has_none(self, app, conn):
        view = _view(app, conn)
        view.show_route("config_offline")
        page = view._pages["config_offline"]

        assert page.new_policy_button.text() == "Nueva política"
        assert page.edit_policy_button.text() == "Editar"
        assert not hasattr(page, "new_cache_button")
        assert not hasattr(page, "edit_cache_button")


def _conflicto(conn) -> str:
    """Un sobre en CONFLICTO, como lo deja el motor de replicación."""
    import importlib

    importlib.import_module("migrations.standalone.350_replication_engine").run(conn)
    estacion, sobre = new_uuid(), new_uuid()
    conn.execute("INSERT INTO replication_stations (id, branch_id, created_at, updated_at)"
                 " VALUES (?,?,'t','t')", (estacion, new_uuid()))
    conn.execute(
        "INSERT INTO replication_envelopes (id, station_id, source, source_row_id, event_id,"
        " event_type, operation_id, aggregate_type, aggregate_id, sequence_no,"
        " aggregate_version, content_hash, envelope_json, state, last_error, created_at)"
        " VALUES (?,?,'sales',?,?,'SALE_COMPLETED',?,'sales.sale',?,1,1,'h','{}','CONFLICT',"
        "'AGGREGATE_VERSION_REGRESSION','t')",
        (sobre, estacion, new_uuid(), new_uuid(), new_uuid(), new_uuid()))
    conn.commit()
    return sobre


class TestOfflinePageConflicts:
    def test_pending_conflicts_are_visible_and_resolved_with_a_reason(self, app, conn, monkeypatch):
        from frontend.desktop.modules.configuracion import pages as _pages  # noqa: F401
        from frontend.desktop.modules.configuracion.pages import offline_page

        sobre = _conflicto(conn)
        view = _view(app, conn)
        view.show_route("config_offline")
        page = view._pages["config_offline"]
        assert page.conflicts_table.rowCount() == 1
        page.conflicts_table.selectRow(0)
        assert page.conflicts_table.selected_row_id() == sobre

        class _Dialogo:
            def __init__(self, *a, **k):
                pass

            def exec_(self):
                return offline_page.QDialog.Accepted

            def values(self):
                return {"reason": "El central ya lo tiene"}

        monkeypatch.setattr(offline_page, "ResolveReplicationConflictDialog", _Dialogo)
        monkeypatch.setattr(offline_page.MessageDialog, "information", lambda *a, **k: None)
        monkeypatch.setattr(offline_page.MessageDialog, "warning", lambda *a, **k: None)
        page.accept_remote_button.click()

        estado = conn.execute("SELECT state FROM replication_envelopes").fetchone()[0]
        assert estado == "SYNCED"
        assert page.conflicts_table.rowCount() == 0

    def test_no_conflicts_shows_the_empty_state(self, app, conn):
        view = _view(app, conn)
        view.show_route("config_offline")
        page = view._pages["config_offline"]
        assert page.conflicts_empty is not None
        assert not page.accept_remote_button.isEnabled()


class TestOfflinePageLoadsRealData:
    def test_policies_table_loads_all_policies_including_inactive(self, app, conn):
        CreateCacheExpirationPolicyUseCase(conn).execute(entity_type="customer", ttl_seconds=3600)
        inactive = CreateCacheExpirationPolicyUseCase(conn).execute(entity_type="product", ttl_seconds=1800)
        inactive.deactivate()
        from backend.infrastructure.db.repositories.offline.cache_expiration_policy_repository import (
            SqliteCacheExpirationPolicyRepository,
        )
        SqliteCacheExpirationPolicyRepository(conn).save(inactive)
        conn.commit()

        view = _view(app, conn)
        view.show_route("config_offline")
        page = view._pages["config_offline"]

        assert page.table.rowCount() == 2

    def test_cache_card_lists_a_seeded_entry_read_only(self, app, conn):
        workstation_id = _seed_workstation(conn)
        entry = OfflineCacheEntry.create(
            entity_type="product", entity_id=new_uuid(), workstation_id=workstation_id,
            payload_json='{"name": "Coca-Cola 600ml"}', source_version="7",
        )
        SqliteOfflineCacheEntryRepository(conn).save(entry)
        conn.commit()

        view = _view(app, conn)
        view.show_route("config_offline")
        page = view._pages["config_offline"]

        assert page.cache_table.rowCount() == 1


class TestOfflinePageFullLoop:
    def test_create_edit_deactivate_reactivate_policy(self, app, conn):
        view = _view(app, conn)
        view.show_route("config_offline")
        page = view._pages["config_offline"]
        presenter = page._presenter

        ok, message = presenter.create_cache_expiration_policy(entity_type="branch", ttl_seconds=3600)
        assert ok is True, message
        page.reload()
        assert page.table.rowCount() == 1

        policy = presenter.list_cache_expiration_policies()[0]

        ok, message = presenter.update_cache_expiration_policy(policy_id=policy.entity_id, ttl_seconds=7200)
        assert ok is True, message

        ok, message = presenter.change_cache_expiration_policy_status(
            policy_id=policy.entity_id, action="DEACTIVATE")
        assert ok is True, message

        ok, message = presenter.change_cache_expiration_policy_status(
            policy_id=policy.entity_id, action="ACTIVATE")
        assert ok is True, message

        updated = presenter.list_cache_expiration_policies()[0]
        assert updated.ttl_seconds == 7200
        assert updated.active is True
