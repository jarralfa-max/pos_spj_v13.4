"""Fase 1: canonicaliza loyalty_ledger y recalcula snapshots de puntos."""
import sqlite3

def _table_exists(conn, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _column_exists(conn, table: str, col: str) -> bool:
    try:
        cols = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except Exception:
        return False
    return any((c[1] if isinstance(c, tuple) else c["name"]) == col for c in cols)


def run(conn):
    # Born-clean UUIDv7 (REGLA CERO): id TEXT, cliente_id/sucursal_id TEXT, sin DEFAULT 1.
    conn.execute("""CREATE TABLE IF NOT EXISTS loyalty_ledger (
        id TEXT NOT NULL PRIMARY KEY, cliente_id TEXT NOT NULL,
        tipo TEXT NOT NULL CHECK(tipo IN ('acumulacion','canje','reversa','ajuste')),
        puntos INTEGER NOT NULL, monto_equiv REAL DEFAULT 0, saldo_post INTEGER DEFAULT 0,
        referencia TEXT DEFAULT '', descripcion TEXT DEFAULT '', sucursal_id TEXT,
        usuario TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""")

    conn.execute("DROP TABLE IF EXISTS loyalty_ledger_new")
    conn.execute("""CREATE TABLE loyalty_ledger_new (
        id TEXT NOT NULL PRIMARY KEY, cliente_id TEXT NOT NULL,
        tipo TEXT NOT NULL CHECK(tipo IN ('acumulacion','canje','reversa','ajuste')),
        puntos INTEGER NOT NULL, monto_equiv REAL DEFAULT 0, saldo_post INTEGER DEFAULT 0,
        referencia TEXT DEFAULT '', descripcion TEXT DEFAULT '', sucursal_id TEXT,
        usuario TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(cliente_id, tipo, referencia)
    )""")

    conn.execute("""INSERT OR IGNORE INTO loyalty_ledger_new
    (cliente_id,tipo,puntos,monto_equiv,saldo_post,referencia,descripcion,sucursal_id,usuario,created_at)
    SELECT cliente_id,
           CASE WHEN tipo IN ('acumulacion','canje','reversa','ajuste') THEN tipo
                WHEN tipo IN ('earn','earned','acreditar') THEN 'acumulacion'
                WHEN tipo IN ('redeem','canjeado') THEN 'canje'
                WHEN tipo IN ('reverse','revertir') THEN 'reversa'
                ELSE 'ajuste' END,
           puntos, COALESCE(monto_equiv,0), COALESCE(saldo_post,0), COALESCE(referencia,''),
           COALESCE(descripcion,''), COALESCE(sucursal_id,1), COALESCE(usuario,''), COALESCE(created_at, datetime('now'))
    FROM loyalty_ledger""")

    if _table_exists(conn, 'growth_ledger') and _column_exists(conn, 'growth_ledger', 'puntos'):
        monto_expr = 'COALESCE(monto_equiv,0)' if _column_exists(conn, 'growth_ledger', 'monto_equiv') else '0'
        conn.execute(f"""INSERT OR IGNORE INTO loyalty_ledger_new
        (cliente_id,tipo,puntos,monto_equiv,referencia,descripcion,sucursal_id,usuario,created_at)
        SELECT cliente_id,
               CASE WHEN COALESCE(puntos,0) >= 0 THEN 'acumulacion' ELSE 'canje' END,
               puntos, {monto_expr}, COALESCE(referencia, CAST(id AS TEXT)),
               COALESCE(descripcion,'migrated growth_ledger'), COALESCE(sucursal_id,1),
               COALESCE(usuario,''), COALESCE(created_at, datetime('now'))
        FROM growth_ledger WHERE cliente_id IS NOT NULL""")

    try:
        conn.execute("DROP TABLE IF EXISTS loyalty_ledger_old")
        conn.execute("ALTER TABLE loyalty_ledger RENAME TO loyalty_ledger_old")
        conn.execute("ALTER TABLE loyalty_ledger_new RENAME TO loyalty_ledger")
        conn.execute("DROP TABLE IF EXISTS loyalty_ledger_old")
    except sqlite3.OperationalError:
        # Entornos legacy pueden traer vistas inválidas (p.ej. referenciando tablas *_old)
        # que bloquean ALTER/DROP con rollback global de migración.
        # Fallback seguro: conservar tabla actual e incorporar datos normalizados.
        conn.execute("DELETE FROM loyalty_ledger")
        conn.execute(
            """
            INSERT OR IGNORE INTO loyalty_ledger
            (cliente_id,tipo,puntos,monto_equiv,saldo_post,referencia,descripcion,sucursal_id,usuario,created_at)
            SELECT cliente_id,tipo,puntos,monto_equiv,saldo_post,referencia,descripcion,sucursal_id,usuario,created_at
            FROM loyalty_ledger_new
            """
        )
        conn.execute("DROP TABLE IF EXISTS loyalty_ledger_new")
        # UNIQUE lógico equivalente para idempotencia sin reescritura de tabla.
        try:
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_loyalty_ledger_cliente_tipo_ref ON loyalty_ledger(cliente_id,tipo,referencia)"
            )
        except sqlite3.IntegrityError:
            # Si hay datos legacy duplicados, mantener migración viva.
            # La deduplicación fuerte se aplicará cuando el entorno permita swap de tabla.
            pass
    conn.execute("CREATE INDEX IF NOT EXISTS idx_loyalty_ledger_cliente_created ON loyalty_ledger(cliente_id, created_at)")

    rows = conn.execute("SELECT id, cliente_id, puntos FROM loyalty_ledger ORDER BY cliente_id, created_at, id").fetchall()
    saldo = {}
    for r in rows:
        rid, cid, pts = (r[0], r[1], r[2]) if isinstance(r, tuple) else (r['id'], r['cliente_id'], r['puntos'])
        saldo[cid] = int(saldo.get(cid, 0)) + int(pts or 0)
        conn.execute("UPDATE loyalty_ledger SET saldo_post=? WHERE id=?", (saldo[cid], rid))

    if _table_exists(conn, 'clientes') and _column_exists(conn, 'clientes', 'puntos'):
        conn.execute("UPDATE clientes SET puntos=0")
        conn.execute("UPDATE clientes SET puntos = COALESCE((SELECT SUM(l.puntos) FROM loyalty_ledger l WHERE l.cliente_id=clientes.id),0)")

    if _table_exists(conn, 'tarjetas_fidelidad') and _column_exists(conn, 'tarjetas_fidelidad', 'puntos_actuales'):
        fk_col = None
        if _column_exists(conn, 'tarjetas_fidelidad', 'cliente_id'):
            fk_col = 'cliente_id'
        elif _column_exists(conn, 'tarjetas_fidelidad', 'id_cliente'):
            fk_col = 'id_cliente'
        conn.execute("UPDATE tarjetas_fidelidad SET puntos_actuales=0")
        if fk_col:
            conn.execute(
                f"UPDATE tarjetas_fidelidad SET puntos_actuales = COALESCE((SELECT SUM(l.puntos) FROM loyalty_ledger l WHERE l.cliente_id=tarjetas_fidelidad.{fk_col}),0) WHERE {fk_col} IS NOT NULL"
            )
