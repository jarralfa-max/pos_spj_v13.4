# migrations/standalone/114_security_lock_and_canonical_kpi_schema.py
"""
114 — Deltas de schema para bases existentes (features nuevas, NO rescate):

  1. usuarios: locked_reason / updated_at / intentos_fallidos / bloqueado_hasta
     (flujo administrativo de desbloqueo con auditoría).
  2. usuario_permisos / usuario_sucursal_permisos: overrides RBAC por UUID.
  3. anticipos: tabla canónica UUIDv7 (antes la creaba la API con
     AUTOINCREMENT — prohibido).
  4. historico_puntos: saldo_actual / usuario (contrato real de escritores).
  5. loyalty_snapshots: forma checkpoint (puntos_actuales, nivel, visitas,
     importe_total, ultimo_evento_id TEXT UUID). Si existe la forma vieja
     diaria (visitas_dia…) se reconstruye: era una tabla sin lectores y el
     snapshot es 100% derivable — el scheduler la repuebla en el siguiente
     ciclo desde historico_puntos.
  6. cuentas_por_cobrar: índice único por venta_id (idempotencia de CxC).

Las bases born-clean ya nacen así desde m000; esta migración alinea las
bases de desarrollo existentes sin resetear.
"""
from __future__ import annotations

import sqlite3

DESCRIPTION = "Seguridad de usuarios (lock/unlock), RBAC overrides, anticipos, loyalty checkpoint, CxC única"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return bool(row)


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    except Exception:
        return set()


def _ensure_column(conn: sqlite3.Connection, table: str, col_def: str) -> None:
    col = col_def.split()[0]
    if _table_exists(conn, table) and col not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")


def run(conn: sqlite3.Connection) -> None:
    # ── 1. usuarios: columnas de bloqueo/desbloqueo ──────────────────────────
    _ensure_column(conn, "usuarios", "intentos_fallidos INTEGER DEFAULT 0")
    _ensure_column(conn, "usuarios", "bloqueado_hasta DATETIME")
    _ensure_column(conn, "usuarios", "locked_reason TEXT")
    _ensure_column(conn, "usuarios", "updated_at DATETIME")

    # ── 2. Overrides RBAC (usuario_id / sucursal_id UUID TEXT) ───────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS usuario_permisos (
            id         TEXT PRIMARY KEY,
            usuario_id TEXT NOT NULL,
            modulo     TEXT NOT NULL,
            accion     TEXT NOT NULL,
            permitido  INTEGER DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS usuario_sucursal_permisos (
            id          TEXT PRIMARY KEY,
            usuario_id  TEXT NOT NULL,
            sucursal_id TEXT NOT NULL,
            modulo      TEXT NOT NULL,
            accion      TEXT NOT NULL,
            permitido   INTEGER DEFAULT 1
        )
    """)

    # ── 3. anticipos canónica ────────────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS anticipos (
            id          TEXT PRIMARY KEY,
            venta_id    TEXT NOT NULL,
            monto       REAL NOT NULL,
            metodo      TEXT DEFAULT 'mercadopago',
            estado      TEXT DEFAULT 'pendiente',
            referencia  TEXT DEFAULT '',
            fecha       TEXT DEFAULT (datetime('now')),
            fecha_pago  TEXT
        )
    """)

    # ── 4. historico_puntos: contrato real de escritores ─────────────────────
    _ensure_column(conn, "historico_puntos", "saldo_actual REAL DEFAULT 0")
    _ensure_column(conn, "historico_puntos", "usuario TEXT")

    # ── 5. loyalty_snapshots: forma checkpoint (UUID) ────────────────────────
    if _table_exists(conn, "loyalty_snapshots") and \
            "ultimo_evento_id" not in _columns(conn, "loyalty_snapshots"):
        # Forma vieja diaria sin lectores: se reconstruye; el scheduler
        # repuebla el checkpoint desde historico_puntos (fuente de verdad).
        conn.execute("DROP TABLE loyalty_snapshots")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS loyalty_snapshots (
            id              TEXT PRIMARY KEY,
            cliente_id      TEXT NOT NULL UNIQUE,
            puntos_actuales INTEGER NOT NULL DEFAULT 0,
            nivel           TEXT    NOT NULL DEFAULT 'Bronce',
            visitas         INTEGER NOT NULL DEFAULT 0,
            importe_total   REAL    NOT NULL DEFAULT 0,
            ultimo_evento_id TEXT,
            fecha_snapshot  DATETIME DEFAULT (datetime('now'))
        )
    """)

    # ── 6. CxC idempotente por venta ─────────────────────────────────────────
    if _table_exists(conn, "cuentas_por_cobrar"):
        # Dev DBs pueden traer duplicados históricos del handler viejo:
        # conservar la fila más antigua por venta antes de crear el índice.
        try:
            conn.execute("""
                DELETE FROM cuentas_por_cobrar
                WHERE venta_id IS NOT NULL AND rowid NOT IN (
                    SELECT MIN(rowid) FROM cuentas_por_cobrar
                    WHERE venta_id IS NOT NULL GROUP BY venta_id
                )
            """)
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_cxc_venta_unica "
                "ON cuentas_por_cobrar(venta_id) WHERE venta_id IS NOT NULL"
            )
        except Exception:
            # No bloquear el arranque: el guard INSERT OR IGNORE + rowcount
            # del servicio sigue protegiendo la idempotencia.
            pass

    conn.commit()
