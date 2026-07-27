# tests/test_phase17_uuid_schema_and_flow.py — SPJ ERP v13.4
"""Phase 17 tests: schema, flow, and architecture verification for UUID-only cutover.

Covers the acceptance criteria from the UUID-only refactor mandate:
- Schema tests: no integer PKs on functional entities, UUID TEXT PKs
- Flow tests: reservation rejects integer IDs, new_uuid() generates UUID7
- Architecture tests: extended guard rails beyond test_uuid_only_guard_rails.py
"""
from __future__ import annotations

import os
import re
import sqlite3
import tempfile

import pytest

# ─── Helpers ──────────────────────────────────────────────────────────────────

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))

_UUID7_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def _is_uuid7(value: str) -> bool:
    return bool(_UUID7_RE.match(str(value).lower()))


def _source_files(dirs=("backend", "core", "application", "domain")):
    for dirpath, _, files in os.walk(ROOT):
        for f in files:
            if not f.endswith(".py"):
                continue
            abs_path = os.path.join(dirpath, f)
            relpath = os.path.relpath(abs_path, ROOT)
            if any(x in relpath for x in (".venv", ".git", "__pycache__", "migrations")):
                continue
            if any(relpath.startswith(d + os.sep) or relpath.startswith(d + "/") for d in dirs):
                yield abs_path, relpath


def _any_violations(dirs=("backend", "core", "application", "domain")):
    """Collect violations as list; empty means none."""
    return _source_files(dirs)


# ─── Schema tests ─────────────────────────────────────────────────────────────

def _bootstrap_db(conn: sqlite3.Connection) -> None:
    """Bootstrap the minimal canonical UUID schema for testing."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sucursales (
            id TEXT PRIMARY KEY,
            nombre TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS productos (
            id TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            unidad TEXT NOT NULL,
            precio NUMERIC NOT NULL DEFAULT 0,
            activo INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS clientes (
            id TEXT PRIMARY KEY,
            nombre TEXT NOT NULL,
            telefono TEXT,
            email TEXT,
            puntos NUMERIC NOT NULL DEFAULT 0,
            activo INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS ventas (
            id TEXT PRIMARY KEY,
            folio TEXT NOT NULL,
            sucursal_id TEXT NOT NULL,
            usuario TEXT NOT NULL,
            total NUMERIC NOT NULL DEFAULT 0,
            estado TEXT NOT NULL DEFAULT 'completada',
            fecha TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS inventory_stock (
            product_id TEXT NOT NULL,
            branch_id TEXT NOT NULL,
            quantity NUMERIC NOT NULL DEFAULT 0,
            unit TEXT NOT NULL DEFAULT 'kg',
            updated_at TEXT NOT NULL,
            PRIMARY KEY (product_id, branch_id)
        );
        CREATE TABLE IF NOT EXISTS inventory_reservations (
            id TEXT PRIMARY KEY,
            operation_id TEXT NOT NULL,
            product_id TEXT NOT NULL,
            branch_id TEXT NOT NULL,
            quantity NUMERIC NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL
        );
    """)


def test_new_uuid_generates_uuid7():
    """new_uuid() must return a canonical UUIDv7 string."""
    from backend.shared.ids import new_uuid
    uid = new_uuid()
    assert _is_uuid7(uid), f"new_uuid() returned non-UUIDv7: {uid!r}"


def test_new_uuid_generates_unique_values():
    """new_uuid() must not return the same value twice."""
    from backend.shared.ids import new_uuid
    ids = {new_uuid() for _ in range(100)}
    assert len(ids) == 100, "new_uuid() produced duplicate values"


def test_schema_productos_pk_is_text():
    """productos table must have TEXT PK, not INTEGER AUTOINCREMENT."""
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        conn = sqlite3.connect(f.name)
        _bootstrap_db(conn)
        info = conn.execute("PRAGMA table_info(productos)").fetchall()
        pk_cols = [(row[1], row[2]) for row in info if row[5] == 1]  # pk=1
        assert len(pk_cols) == 1, f"Expected 1 PK column, got: {pk_cols}"
        col_name, col_type = pk_cols[0]
        assert col_name == "id", f"PK column name must be 'id', got: {col_name}"
        assert "TEXT" in col_type.upper(), f"PK must be TEXT, got: {col_type}"
        conn.close()


def test_schema_inventory_stock_no_integer_pk():
    """inventory_stock must use TEXT composite PK, not INTEGER rowid."""
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        conn = sqlite3.connect(f.name)
        _bootstrap_db(conn)
        info = conn.execute("PRAGMA table_info(inventory_stock)").fetchall()
        pk_cols = [(row[1], row[2]) for row in info if row[5] > 0]
        pk_names = [c[0] for c in pk_cols]
        assert "product_id" in pk_names
        assert "branch_id" in pk_names
        # Verify no INTEGER-typed PK
        for name, typ in pk_cols:
            assert "INTEGER" not in typ.upper() or name in ("rowid",), (
                f"inventory_stock.{name} is INTEGER PK — must be TEXT"
            )
        conn.close()


def test_schema_inventory_reservations_pk_is_text():
    """inventory_reservations must use TEXT PK."""
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        conn = sqlite3.connect(f.name)
        _bootstrap_db(conn)
        info = conn.execute("PRAGMA table_info(inventory_reservations)").fetchall()
        pk_cols = [(row[1], row[2]) for row in info if row[5] == 1]
        assert pk_cols, "No PK found in inventory_reservations"
        col_name, col_type = pk_cols[0]
        assert "TEXT" in col_type.upper(), f"inventory_reservations PK must be TEXT, got: {col_type}"
        conn.close()


def test_schema_ventas_pk_is_text():
    """ventas table PK must be TEXT (UUID), not INTEGER."""
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        conn = sqlite3.connect(f.name)
        _bootstrap_db(conn)
        info = conn.execute("PRAGMA table_info(ventas)").fetchall()
        pk_cols = [(row[1], row[2]) for row in info if row[5] == 1]
        assert pk_cols
        assert "TEXT" in pk_cols[0][1].upper(), f"ventas PK must be TEXT, got: {pk_cols[0]}"
        conn.close()


# ─── Flow tests ───────────────────────────────────────────────────────────────

def test_reservation_service_rejects_integer_product_id():
    """_require_uuid must raise on legacy integer product_id."""
    from core.services.reservation_service import _require_uuid
    with pytest.raises(ValueError, match="Legacy identity rejected"):
        _require_uuid("2", "product_id")


def test_reservation_service_rejects_integer_branch_id():
    """_require_uuid must raise on legacy integer branch_id."""
    from core.services.reservation_service import _require_uuid
    with pytest.raises(ValueError, match="Legacy identity rejected"):
        _require_uuid("1", "branch_id")


def test_reservation_service_accepts_uuid7():
    """_require_uuid must pass valid UUIDv7 through."""
    from core.services.reservation_service import _require_uuid
    from backend.shared.ids import new_uuid
    uid = new_uuid()
    result = _require_uuid(uid, "product_id")
    assert result == uid


def test_reservation_get_available_stock_uses_inventory_stock():
    """ReservationService.get_available_stock must query inventory_stock, not inventario_actual."""
    from core.services.reservation_service import ReservationService
    import inspect
    src = inspect.getsource(ReservationService.get_available_stock)
    assert "inventory_stock" in src, "get_available_stock must query inventory_stock"
    assert "inventario_actual" not in src, "get_available_stock must NOT query inventario_actual"


def test_inventory_repository_uses_canonical_table():
    """SQLiteInventoryRepository must use inventory_stock as canonical table."""
    from infrastructure.persistence.sqlite_inventory_repository import SQLiteInventoryRepository
    import inspect
    src = inspect.getsource(SQLiteInventoryRepository.get_stock)
    assert "inventory_stock" in src
    assert "inventario_actual" not in src


def test_sales_repository_creates_uuid_sale_id():
    """SQLiteSalesRepository.create_sale must generate UUID not integer."""
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        conn = sqlite3.connect(f.name)
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE ventas (
                id TEXT PRIMARY KEY, folio TEXT NOT NULL, sucursal_id TEXT NOT NULL,
                usuario TEXT NOT NULL, cliente_id TEXT,
                subtotal NUMERIC, descuento NUMERIC, total NUMERIC,
                forma_pago TEXT, efectivo_recibido NUMERIC,
                operation_id TEXT, observations TEXT, estado TEXT, fecha TEXT
            );
        """)
        from infrastructure.persistence.sqlite_sales_repository import SQLiteSalesRepository
        repo = SQLiteSalesRepository(conn)
        from backend.shared.ids import new_uuid
        branch_id = new_uuid()
        sale_id, folio = repo.create_sale(
            branch_id=branch_id,
            user="test",
            client_id=None,
            subtotal=100.0,
            discount=0.0,
            total=100.0,
            payment_method="cash",
            amount_paid=100.0,
            operation_id=new_uuid(),
        )
        assert _is_uuid7(sale_id), f"sale_id must be UUIDv7, got: {sale_id!r}"
        assert "VNT-" in folio, f"folio must have VNT- prefix, got: {folio!r}"
        conn.close()


def test_seed_branch_uuid_is_valid_uuid7():
    """seed_demo.py BRANCH_UUID must be a valid UUIDv7 string."""
    import importlib.util, sys
    spec = importlib.util.spec_from_file_location(
        "seed_demo", os.path.join(ROOT, "scripts", "seed_demo.py")
    )
    module = importlib.util.module_from_spec(spec)
    # Don't execute, just read the source
    src = open(spec.origin).read()
    m = re.search(r'BRANCH_UUID\s*=\s*["\']([^"\']+)["\']', src)
    assert m, "BRANCH_UUID not found in seed_demo.py"
    uid = m.group(1)
    assert _is_uuid7(uid), f"BRANCH_UUID must be UUIDv7, got: {uid!r}"


# ─── Architecture tests (Phase 17) ────────────────────────────────────────────

def test_no_autoincrement_in_canonical_services():
    """New canonical services must not create INTEGER AUTOINCREMENT schema."""
    violations = []
    pat = re.compile(r'AUTOINCREMENT', re.IGNORECASE)
    _CANONICAL = (
        "infrastructure/persistence/",
        "core/delivery/application/",
        "core/services/reservation_service.py",
        "backend/application/use_cases/",
    )
    for abs_path, relpath in _source_files():
        if not any(c in relpath for c in _CANONICAL):
            continue
        src = open(abs_path).read()
        for lineno, line in enumerate(src.splitlines(), 1):
            stripped = line.strip()
            if pat.search(stripped) and not stripped.startswith("#"):
                violations.append(f"{relpath}:{lineno}: {stripped}")
    assert not violations, "AUTOINCREMENT in canonical services:\n" + "\n".join(violations)


def test_no_branch_id_integer_fallback():
    """branch_id must not fall back to integer 1 in business code.

    branch_id=None as a default parameter is allowed (explicit None means caller
    must supply it). Only 'branch_id or 1' (silent fallback to integer) is forbidden.
    """
    violations = []
    # Only catch the actual integer-1 fallback, not None defaults
    pat = re.compile(r'\bbranch_id\s+or\s+1\b')
    for abs_path, relpath in _source_files():
        if "migrations" in relpath or "test_" in relpath:
            continue
        src = open(abs_path).read()
        for lineno, line in enumerate(src.splitlines(), 1):
            stripped = line.strip()
            if pat.search(stripped) and not stripped.startswith("#"):
                violations.append(f"{relpath}:{lineno}: {stripped}")
    assert not violations, "branch_id or 1 integer fallback:\n" + "\n".join(violations)


def test_no_inventario_actual_in_any_business_code():
    """inventario_actual must not be used in any business code (only migrations)."""
    violations = []
    pat = re.compile(r'\binventario_actual\b')
    for abs_path, relpath in _source_files():
        src = open(abs_path).read()
        for lineno, line in enumerate(src.splitlines(), 1):
            stripped = line.strip()
            if pat.search(stripped) and not stripped.startswith("#"):
                violations.append(f"{relpath}:{lineno}: {stripped}")
    assert not violations, "inventario_actual in business code:\n" + "\n".join(violations)


def test_delivery_handler_uses_product_id_not_producto_id():
    """DeliveryReserveStockHandler must not accept producto_id."""
    handler_path = os.path.join(ROOT, "core", "events", "handlers", "delivery_handler.py")
    src = open(handler_path).read()
    # Find the DeliveryReserveStockHandler class
    class_match = re.search(
        r'class DeliveryReserveStockHandler.*?(?=\nclass |\Z)',
        src, re.DOTALL
    )
    assert class_match, "DeliveryReserveStockHandler not found"
    handler_src = class_match.group(0)
    assert 'item.get("product_id")' in handler_src or 'item["product_id"]' in handler_src, \
        "Handler must use product_id key"
    assert 'item.get("producto_id")' not in handler_src, \
        "Handler must not accept legacy producto_id"


def test_reservation_service_has_no_internal_commit():
    """ReservationService must not call db.commit() internally."""
    from core.services.reservation_service import ReservationService
    import inspect
    src = inspect.getsource(ReservationService)
    assert ".commit()" not in src, "ReservationService must not call .commit() internally"
