"""First installation must have no usable identity until provisioning commits."""
import importlib
import sqlite3

import pytest

from backend.security.provisioning.installation import ProvisioningStatus
from backend.security.provisioning.installation_repository import SqliteInstallationRepository
from backend.security.provisioning.installation_status_query import InstallationStatusQuery
from tests.integration._born_clean_db import make_db
from tests.integration.security.test_provision_installation_use_case import _build_use_case, _execute


def test_born_clean_has_no_default_password():
    conn = make_db()
    try:
        importlib.import_module("migrations.standalone.047_v13_schema").up(conn)
        assert conn.execute("SELECT usuario FROM usuarios").fetchall() == []
        assert InstallationStatusQuery(SqliteInstallationRepository(conn)).current_status() is ProvisioningStatus.UNINITIALIZED
    finally:
        conn.close()


def test_provisioning_commits_before_reporting_success():
    conn = make_db()
    try:
        result = _execute(_build_use_case(conn))
        assert not conn.in_transaction
        conn.rollback()
        assert SqliteInstallationRepository(conn).get().provisioned_by_user_id == result.owner_user_id
    finally:
        conn.close()


@pytest.mark.parametrize("autocommit", [False, True])
def test_failed_provisioning_rolls_back_every_write(autocommit):
    conn = make_db()
    if autocommit:
        conn.isolation_level = None
    tables = ("usuarios", "sucursales", "configuraciones", "installation", "installation_recovery_codes")
    before = {table: conn.execute(f"SELECT * FROM {table}").fetchall() for table in tables}

    def fail_on_completion(event, payload):
        if event == "INSTALLATION_PROVISIONED":
            raise RuntimeError("audit unavailable")

    try:
        with pytest.raises(RuntimeError, match="audit unavailable"):
            _execute(_build_use_case(conn, audit_sink=fail_on_completion))
        assert not conn.in_transaction
        assert {table: conn.execute(f"SELECT * FROM {table}").fetchall() for table in tables} == before
        assert InstallationStatusQuery(SqliteInstallationRepository(conn)).requires_setup_wizard()
    finally:
        conn.close()


@pytest.mark.parametrize("field", ["company_name", "branch_name", "workstation_name"])
def test_provisioning_requires_installation_details(field):
    conn = make_db()
    try:
        with pytest.raises(ValueError):
            _execute(_build_use_case(conn), **{field: "  "})
        assert not conn.in_transaction
    finally:
        conn.close()


def test_provisioned_branch_is_the_runtime_installation_branch():
    conn = make_db()
    try:
        result = _execute(_build_use_case(conn))
        branch = conn.execute("SELECT valor FROM configuraciones WHERE clave='sucursal_instalacion_id'").fetchone()[0]
        assert branch == result.installation.initial_branch_id
    finally:
        conn.close()
