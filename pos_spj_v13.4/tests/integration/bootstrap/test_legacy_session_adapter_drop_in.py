"""Proves `LegacySessionAdapter` is a real drop-in replacement for
`container.session` in SHELL-16-migrated modules — not just a plausible
shape on paper. Reuses two already-migrated modules' own real composition
functions (`transfers`, `purchasing`) against a real SQLite connection,
passing a `LegacySessionAdapter` wrapping a real `ApplicationContext`
instead of the fake `_Session`/`_FakeSession` test doubles those modules'
own test suites use.
"""
from __future__ import annotations

import os
import sqlite3

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from backend.bootstrap.application_context import ApplicationContext, FeatureContext  # noqa: E402
from backend.bootstrap.legacy_session_adapter import LegacySessionAdapter  # noqa: E402
from backend.infrastructure.db.schema.procurement_schema import create_procurement_schema  # noqa: E402
from backend.infrastructure.db.schema.transfers_schema import create_transfers_schema  # noqa: E402
from frontend.desktop.modules.purchasing.enterprise_view import EnterprisePurchasingView  # noqa: E402
from frontend.desktop.modules.purchasing.shell_registration import create_purchasing_view  # noqa: E402
from frontend.desktop.modules.transfers.shell_registration import create_transfers_view  # noqa: E402
from frontend.desktop.modules.transfers.transfers_view import TransfersView  # noqa: E402


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


def _context(*, permissions) -> ApplicationContext:
    return ApplicationContext(
        installation_id="install-1", company_id="company-1", branch_id="b1",
        branch_name="Matriz", workstation_id="ws-1", workstation_type="pos",
        user_id="u1", user_name="Almacenista", roles=("almacenista",),
        permissions=frozenset(permissions), feature_context=FeatureContext(),
        session_id="session-1",
    )


def test_adapter_drives_the_real_transfers_composition(app):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    create_transfers_schema(conn)
    conn.execute("CREATE TABLE sucursales (id TEXT PRIMARY KEY, nombre TEXT, activa INTEGER)")
    conn.execute("INSERT INTO sucursales VALUES ('b1', 'Matriz', 1), ('b2', 'Sucursal Centro', 1)")
    conn.execute("CREATE TABLE products (id TEXT PRIMARY KEY, base_unit_id TEXT)")
    conn.execute("INSERT INTO products VALUES ('p1', 'unit-kg')")
    conn.commit()

    # The sidebar is gated by transfers' own granular permission scheme
    # (`backend.application.transfers.permissions.TransferPermissions`,
    # e.g. "TRANSFERS_DASHBOARD_VIEW") — a different set of codes than the
    # route-level "TRANSFERENCIAS.ver" catalog code. Granting one of those
    # here proves the adapter's tiene_permiso() really flows through to the
    # real UI, not just that it exists without erroring.
    adapter = LegacySessionAdapter(_context(permissions={"TRANSFERS_DASHBOARD_VIEW"}))
    view = create_transfers_view(conn, adapter)
    assert isinstance(view, TransfersView)
    assert view.sidebar.count() > 0


def test_adapter_denies_permissions_the_context_does_not_grant(app):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    create_transfers_schema(conn)
    conn.execute("CREATE TABLE sucursales (id TEXT PRIMARY KEY, nombre TEXT, activa INTEGER)")
    conn.execute("INSERT INTO sucursales VALUES ('b1', 'Matriz', 1)")
    conn.execute("CREATE TABLE products (id TEXT PRIMARY KEY, base_unit_id TEXT)")
    conn.commit()

    adapter = LegacySessionAdapter(_context(permissions=frozenset()))
    view = create_transfers_view(conn, adapter)
    assert view.sidebar.count() == 0


def test_adapter_drives_the_real_purchasing_composition(app):
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    create_procurement_schema(conn)

    adapter = LegacySessionAdapter(_context(permissions={"COMPRAS.VER"}))
    view = create_purchasing_view(conn, adapter)
    assert isinstance(view, EnterprisePurchasingView)
