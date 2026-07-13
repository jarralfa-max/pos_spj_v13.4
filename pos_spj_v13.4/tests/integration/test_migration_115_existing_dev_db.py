"""Migración 115: alinea bases de desarrollo existentes con el schema nuevo.

Regresión del bug reportado en validación manual: en una DB existente el
engine salta m000 (_already_run) y el desbloqueo fallaba con
`no such column: locked_reason`.
"""
from __future__ import annotations

import importlib
import sqlite3

from backend.shared.ids import new_uuid

MIG = importlib.import_module(
    "migrations.standalone.115_security_lock_and_canonical_kpi_schema"
)


def _old_dev_db() -> sqlite3.Connection:
    """Simula una DB de desarrollo previa (sin las columnas/tablas nuevas)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE usuarios (
            id TEXT PRIMARY KEY, nombre TEXT, usuario TEXT UNIQUE,
            password_hash TEXT, rol TEXT, sucursal_id TEXT, activo INTEGER DEFAULT 1
        );
        CREATE TABLE historico_puntos (
            id TEXT PRIMARY KEY, cliente_id TEXT, tipo TEXT, puntos INTEGER,
            descripcion TEXT, venta_id TEXT, fecha DATETIME
        );
        CREATE TABLE loyalty_snapshots (
            id TEXT PRIMARY KEY, cliente_id TEXT NOT NULL, fecha DATE NOT NULL,
            visitas_dia INTEGER DEFAULT 0, importe_dia REAL DEFAULT 0,
            margen_dia REAL DEFAULT 0, visitas_acum INTEGER DEFAULT 0,
            importe_acum REAL DEFAULT 0, margen_acum REAL DEFAULT 0,
            score_calculado REAL DEFAULT 0
        );
        CREATE TABLE cuentas_por_cobrar (
            id TEXT PRIMARY KEY, cliente_id TEXT, venta_id TEXT, folio TEXT,
            monto_original REAL, saldo_pendiente REAL, estado TEXT,
            sucursal_id TEXT, fecha DATETIME
        );
        CREATE TABLE audit_logs (
            id TEXT PRIMARY KEY, accion TEXT, modulo TEXT, entidad TEXT,
            entidad_id TEXT, usuario TEXT, sucursal_id TEXT, valor_antes TEXT,
            valor_despues TEXT, detalles TEXT, ip TEXT,
            fecha DATETIME DEFAULT (datetime('now'))
        );
    """)
    return conn


def test_115_adds_lock_columns_and_unlock_works():
    conn = _old_dev_db()
    uid = new_uuid()
    conn.execute(
        "INSERT INTO usuarios (id, nombre, usuario, password_hash, rol) "
        "VALUES (?, 'Ana', 'ana', 'x', 'cajero')",
        (uid,),
    )

    MIG.run(conn)
    MIG.run(conn)   # idempotente

    cols = {r[1] for r in conn.execute("PRAGMA table_info(usuarios)")}
    assert {"intentos_fallidos", "bloqueado_hasta", "locked_reason", "updated_at"} <= cols

    # El flujo de desbloqueo ya funciona sobre la DB migrada
    from backend.application.services.user_security_service import UserSecurityService

    conn.execute(
        "UPDATE usuarios SET intentos_fallidos=5, "
        "bloqueado_hasta=datetime('now','+15 minutes') WHERE id=?",
        (uid,),
    )
    svc = UserSecurityService(conn, permission_checker=lambda code: True)
    assert svc.unlock_user(uid, operation_id=new_uuid(), actor_id=new_uuid())["ok"]
    row = conn.execute(
        "SELECT intentos_fallidos, bloqueado_hasta FROM usuarios WHERE id=?", (uid,)
    ).fetchone()
    assert row[0] == 0 and row[1] is None


def test_115_creates_rbac_tables():
    conn = _old_dev_db()
    MIG.run(conn)
    for tabla in ("usuario_permisos", "usuario_sucursal_permisos"):
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabla,)
        ).fetchone(), f"falta tabla {tabla}"


def test_114_creates_anticipos_table():
    conn = _old_dev_db()
    mig114 = importlib.import_module("migrations.standalone.114_anticipos_schema")
    mig114.run(conn)
    assert conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='anticipos'"
    ).fetchone()


def test_115_rebuilds_loyalty_snapshots_to_checkpoint_shape():
    conn = _old_dev_db()
    MIG.run(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(loyalty_snapshots)")}
    assert "ultimo_evento_id" in cols and "puntos_actuales" in cols
    assert "visitas_dia" not in cols

    # historico_puntos ganó el contrato de escritores
    cols_hp = {r[1] for r in conn.execute("PRAGMA table_info(historico_puntos)")}
    assert {"saldo_actual", "usuario"} <= cols_hp


def test_115_dedupes_cxc_and_creates_unique_index():
    conn = _old_dev_db()
    venta = new_uuid()
    for _ in range(2):  # duplicado histórico del handler viejo
        conn.execute(
            "INSERT INTO cuentas_por_cobrar (id, cliente_id, venta_id, monto_original, "
            " saldo_pendiente, estado) VALUES (?, ?, ?, 100, 100, 'pendiente')",
            (new_uuid(), new_uuid(), venta),
        )
    MIG.run(conn)
    n = conn.execute(
        "SELECT COUNT(*) FROM cuentas_por_cobrar WHERE venta_id=?", (venta,)
    ).fetchone()[0]
    assert n == 1
    idx = {r[1] for r in conn.execute("PRAGMA index_list(cuentas_por_cobrar)")}
    assert "idx_cxc_venta_unica" in idx
