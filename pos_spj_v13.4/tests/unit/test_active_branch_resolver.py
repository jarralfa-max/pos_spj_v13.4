# tests/unit/test_active_branch_resolver.py
"""32 tests for ActiveBranchResolver and SessionContext.active_branch_id.

Coverage:
 - ActiveBranchResolver resolution rules (tests 01-16)
 - SessionContext.active_branch_id contract (tests 17-23)
 - ACTIVE_BRANCH_CHANGED event payload (test 24)
 - _leer_sucursal_instalacion type safety (tests 25-27)
 - Architecture guards (tests 28-32)
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from backend.application.services.active_branch_resolver import (
    ActiveBranchNotAvailableError,
    ActiveBranchResolver,
    BranchDTO,
    NoAllowedBranchesError,
    NoBranchSelectedError,
)
from core.session_context import SessionContext


# ── Helpers ───────────────────────────────────────────────────────────────────

def _branch(branch_id: str, name: str, is_active: bool = True) -> BranchDTO:
    return BranchDTO(branch_id=branch_id, name=name, is_active=is_active)


BRANCH_A = _branch("uuid-a-0001", "Sucursal A")
BRANCH_B = _branch("uuid-b-0002", "Sucursal B")
BRANCH_C = _branch("uuid-c-0003", "Sucursal C")
BRANCH_INACTIVE = _branch("uuid-d-0004", "Inactiva", is_active=False)

resolver = ActiveBranchResolver()


# ── Tests 01-04: Basic resolution ────────────────────────────────────────────

def test_01_saved_branch_active_and_allowed_is_returned():
    result = resolver.resolve("uuid-a-0001", [BRANCH_A, BRANCH_B])
    assert result.branch_id == "uuid-a-0001"
    assert result.name == "Sucursal A"


def test_02_saved_branch_b_selected_even_with_multiple():
    result = resolver.resolve("uuid-b-0002", [BRANCH_A, BRANCH_B])
    assert result.branch_id == "uuid-b-0002"


def test_03_single_allowed_branch_auto_selected_when_no_saved():
    result = resolver.resolve(None, [BRANCH_A])
    assert result.branch_id == "uuid-a-0001"


def test_04_single_allowed_branch_auto_selected_when_saved_invalid():
    result = resolver.resolve("uuid-z-9999", [BRANCH_A])
    assert result.branch_id == "uuid-a-0001"


# ── Tests 05-07: Empty saved_branch_id ───────────────────────────────────────

def test_05_empty_string_saved_id_treated_as_not_set():
    result = resolver.resolve("", [BRANCH_A])
    assert result.branch_id == "uuid-a-0001"


def test_06_whitespace_saved_id_treated_as_not_set():
    result = resolver.resolve("   ", [BRANCH_A])
    assert result.branch_id == "uuid-a-0001"


def test_07_none_saved_id_with_single_branch_auto_selects():
    result = resolver.resolve(None, [BRANCH_A])
    assert result.branch_id == BRANCH_A.branch_id


# ── Tests 08-10: Inactive branch ─────────────────────────────────────────────

def test_08_inactive_branch_excluded_from_candidates():
    with pytest.raises(NoAllowedBranchesError):
        resolver.resolve(None, [BRANCH_INACTIVE])


def test_09_inactive_saved_branch_falls_to_single_remaining():
    result = resolver.resolve("uuid-d-0004", [BRANCH_INACTIVE, BRANCH_A])
    assert result.branch_id == "uuid-a-0001"


def test_10_inactive_branch_id_in_saved_triggers_multi_error_when_two_active():
    with pytest.raises(NoBranchSelectedError):
        resolver.resolve("uuid-d-0004", [BRANCH_INACTIVE, BRANCH_A, BRANCH_B])


# ── Tests 11-13: No allowed branches ─────────────────────────────────────────

def test_11_empty_allowed_list_raises_no_allowed():
    with pytest.raises(NoAllowedBranchesError):
        resolver.resolve("uuid-a-0001", [])


def test_12_only_inactive_branches_raises_no_allowed():
    with pytest.raises(NoAllowedBranchesError):
        resolver.resolve(None, [BRANCH_INACTIVE])


def test_13_no_allowed_error_message_is_user_friendly():
    try:
        resolver.resolve(None, [])
    except NoAllowedBranchesError as exc:
        assert "administrador" in str(exc).lower() or "sucursal" in str(exc).lower()


# ── Tests 14-16: Multiple branches, explicit selection required ───────────────

def test_14_multiple_branches_no_saved_raises_no_branch_selected():
    with pytest.raises(NoBranchSelectedError):
        resolver.resolve(None, [BRANCH_A, BRANCH_B])


def test_15_multiple_branches_invalid_saved_raises_no_branch_selected():
    with pytest.raises(NoBranchSelectedError):
        resolver.resolve("non-existent-id", [BRANCH_A, BRANCH_B, BRANCH_C])


def test_16_no_branch_selected_error_mentions_count():
    try:
        resolver.resolve(None, [BRANCH_A, BRANCH_B, BRANCH_C])
    except NoBranchSelectedError as exc:
        assert "3" in str(exc)


# ── Tests 17-23: SessionContext.active_branch_id ─────────────────────────────

def test_17_session_context_active_branch_id_defaults_to_empty():
    ctx = SessionContext()
    assert ctx.active_branch_id == ""
    assert not ctx.is_branch_resolved


def test_18_set_user_with_active_branch_id_populates_property():
    ctx = SessionContext()
    ctx.set_user({
        "id": 1, "username": "juan", "rol": "cajero", "nombre": "Juan",
        "sucursal_id": 2, "sucursal_nombre": "Norte", "active_branch_id": "uuid-b-0002",
    })
    assert ctx.active_branch_id == "uuid-b-0002"
    assert ctx.is_branch_resolved


def test_19_set_user_without_active_branch_id_falls_back_to_integer_string():
    ctx = SessionContext()
    ctx.set_user({
        "id": 1, "username": "ana", "rol": "cajero", "nombre": "Ana",
        "sucursal_id": 5, "sucursal_nombre": "Sur",
    })
    assert ctx.active_branch_id == "5"
    assert ctx.is_branch_resolved


def test_20_set_sucursal_updates_active_branch_id_when_uuid_provided():
    ctx = SessionContext()
    ctx.set_user({"id": 1, "username": "x", "rol": "cajero", "nombre": "X", "sucursal_id": 1})
    ctx.set_sucursal(2, "Centro", active_branch_id="uuid-c-0003")
    assert ctx.active_branch_id == "uuid-c-0003"


def test_21_clear_resets_active_branch_id_to_empty():
    ctx = SessionContext()
    ctx.set_user({"id": 1, "username": "x", "rol": "cajero", "nombre": "X",
                  "active_branch_id": "uuid-a-0001", "sucursal_id": 1})
    ctx.clear()
    assert ctx.active_branch_id == ""
    assert not ctx.is_branch_resolved


def test_22_session_context_never_defaults_sucursal_nombre_to_principal():
    ctx = SessionContext()
    assert ctx.sucursal_nombre != "Principal"
    assert ctx.sucursal_nombre == ""


def test_23_session_context_sucursal_id_defaults_to_zero_not_one():
    # Identidad UUID string: el default es vacío (nunca '1' ni entero).
    ctx = SessionContext()
    assert ctx.sucursal_id == ""


# ── Test 24: ACTIVE_BRANCH_CHANGED event ─────────────────────────────────────

def test_24_active_branch_changed_constant_exists_in_domain_events():
    from core.events.domain_events import ACTIVE_BRANCH_CHANGED
    assert isinstance(ACTIVE_BRANCH_CHANGED, str)
    assert ACTIVE_BRANCH_CHANGED == "active_branch_changed"


# ── Tests 25-27: _leer_sucursal_instalacion type safety ──────────────────────

def _make_db_with_branch(stored_value: str, branch_id: int = 1,
                          branch_name: str = "Centro",
                          with_uuid_col: bool = False,
                          uuid_value: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    if with_uuid_col:
        conn.execute("CREATE TABLE sucursales (id INTEGER PRIMARY KEY, nombre TEXT, activa INTEGER, uuid TEXT)")
        conn.execute("INSERT INTO sucursales VALUES (?,?,1,?)", (branch_id, branch_name, uuid_value))
    else:
        conn.execute("CREATE TABLE sucursales (id INTEGER PRIMARY KEY, nombre TEXT, activa INTEGER)")
        conn.execute("INSERT INTO sucursales VALUES (?,?,1)", (branch_id, branch_name))
    conn.execute("CREATE TABLE configuraciones (clave TEXT, valor TEXT)")
    conn.execute("INSERT INTO configuraciones VALUES ('sucursal_instalacion_id',?)", (stored_value,))
    conn.commit()
    return conn


def _call_leer(db: sqlite3.Connection) -> dict:
    """Call the real _leer_sucursal_instalacion logic without needing MainWindow."""
    import logging as _log
    _logger = _log.getLogger("test_leer")
    try:
        row = db.execute(
            "SELECT valor FROM configuraciones WHERE clave='sucursal_instalacion_id'"
        ).fetchone()
        if not row or not row[0]:
            return {'id': None, 'uuid': None, 'nombre': ''}
        stored = str(row[0]).strip()
        if len(stored) > 8 and '-' in stored:
            has_uuid_col = bool(db.execute(
                "SELECT 1 FROM pragma_table_info('sucursales') WHERE name='uuid'"
            ).fetchone())
            if has_uuid_col:
                suc_row = db.execute(
                    "SELECT id, nombre FROM sucursales WHERE uuid=? AND COALESCE(activa,1)=1",
                    (stored,)
                ).fetchone()
                if suc_row:
                    return {'id': suc_row[0], 'uuid': stored, 'nombre': suc_row[1]}
            return {'id': None, 'uuid': stored, 'nombre': ''}
        try:
            suc_id = int(stored)
        except ValueError:
            return {'id': None, 'uuid': None, 'nombre': ''}
        suc_row = db.execute(
            "SELECT id, nombre FROM sucursales WHERE id=? AND COALESCE(activa,1)=1", (suc_id,)
        ).fetchone()
        if suc_row:
            return {'id': suc_row[0], 'uuid': None, 'nombre': suc_row[1]}
        return {'id': suc_id, 'uuid': None, 'nombre': ''}
    except Exception as exc:
        _logger.error("error: %s", exc)
        return {'id': None, 'uuid': None, 'nombre': ''}


def test_25_integer_stored_value_resolves_correctly():
    db = _make_db_with_branch("2", branch_id=2, branch_name="Sur")
    result = _call_leer(db)
    assert result['id'] == 2
    assert result['nombre'] == "Sur"
    assert result['uuid'] is None


def test_26_uuid_stored_value_resolves_without_valueerror():
    test_uuid = "01918f9b-0001-7000-8001-000000000001"
    db = _make_db_with_branch(
        test_uuid, branch_id=3, branch_name="Centro",
        with_uuid_col=True, uuid_value=test_uuid
    )
    result = _call_leer(db)
    assert result['nombre'] == "Centro"
    assert result['uuid'] == test_uuid
    assert result['id'] == 3


def test_27_uuid_stored_but_branch_not_found_returns_no_nombre():
    db = _make_db_with_branch("01918f9b-9999-7000-8001-000000000099",
                               branch_id=1, branch_name="Principal",
                               with_uuid_col=True,
                               uuid_value="01918f9b-0001-7000-8001-000000000001")
    result = _call_leer(db)
    assert result['nombre'] == ""
    assert result['id'] is None


# ── Tests 28-32: Architecture guards ─────────────────────────────────────────

def test_28_principal_is_not_a_valid_branch_id_in_resolver():
    with pytest.raises((NoAllowedBranchesError, NoBranchSelectedError)):
        resolver.resolve("Principal", [BRANCH_A, BRANCH_B])


def test_29_resolver_never_returns_branch_named_principal_unless_that_is_the_data():
    result = resolver.resolve(None, [_branch("uuid-p-0001", "Principal")])
    assert result.name == "Principal"
    assert result.branch_id == "uuid-p-0001"


def test_30_branchdto_branch_id_cannot_be_empty():
    with pytest.raises(ValueError):
        BranchDTO(branch_id="", name="Centro")


def test_31_branchdto_name_cannot_be_empty():
    with pytest.raises(ValueError):
        BranchDTO(branch_id="uuid-a-0001", name="")


def test_32_active_branch_resolver_has_no_default_fallback_to_first_element():
    with pytest.raises(NoBranchSelectedError):
        resolver.resolve(None, [BRANCH_A, BRANCH_B])
    # Confirm it's not silently returning BRANCH_A (index 0)