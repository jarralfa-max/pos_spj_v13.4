"""294 — Fidelidad, vales, cupones y sorteos llegan a contabilidad (2026-10-03).

Decisión del usuario: "contabiliza los puntos, cupones, vales, boletos y
cualquier programa de fidelidad". El puente
(`backend/application/loyalty/integrations/finance_posting.py`) necesita:

* Las tablas de estado del puente (`loyalty_finance_links`, acumulaciones y
  consumos FIFO de puntos).
* El tipo de instrumento `SWEEPSTAKES_PRIZE` en `commercial_obligations`. Su
  CHECK enumera los tipos y SQLite no altera un CHECK: la tabla se reconstruye
  (llaves foráneas desactivadas, `legacy_alter_table=ON` por la vista legacy
  rota de la base real — ver la 292 — y verificación al final).
* La cuenta 2136 "Provisión de premios de sorteos" y el perfil contable
  `SWEEPSTAKES_PRIZE` en un catálogo ya sembrado (la siembra de Finanzas se
  salta entera si el catálogo existe). Si Finanzas aún no se sembró, no hace
  nada: la siembra completa ya los incluye.

Idempotente.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.294")

_TIPO = "SWEEPSTAKES_PRIZE"


def _obligations_sql(conn) -> str | None:
    fila = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='commercial_obligations'"
    ).fetchone()
    return fila[0] if fila else None


def _rebuild_obligations(conn, sql: str) -> None:
    viejo = "'CUSTOMER_WALLET','THIRD_PARTY_VOUCHER')"
    if viejo not in sql:
        raise RuntimeError("294: el CHECK de commercial_obligations no tiene la forma esperada")
    nuevo = sql.replace(viejo, f"'CUSTOMER_WALLET','THIRD_PARTY_VOUCHER','{_TIPO}')", 1)
    nuevo = nuevo.replace("commercial_obligations", "commercial_obligations__new", 1)
    columnas = ", ".join(f[1] for f in conn.execute("PRAGMA table_info(commercial_obligations)"))
    conn.commit()
    fk_previo = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    legacy_previo = conn.execute("PRAGMA legacy_alter_table").fetchone()[0]
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("PRAGMA legacy_alter_table=ON")
    try:
        conn.execute(nuevo)
        conn.execute(f"INSERT INTO commercial_obligations__new ({columnas})"
                     f" SELECT {columnas} FROM commercial_obligations")
        conn.execute("DROP TABLE commercial_obligations")
        conn.execute("ALTER TABLE commercial_obligations__new RENAME TO commercial_obligations")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_obligations_instrument"
                     " ON commercial_obligations (instrument_type, status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_obligations_customer"
                     " ON commercial_obligations (customer_id)")
        problemas = conn.execute("PRAGMA foreign_key_check").fetchall()
        if problemas:
            raise RuntimeError(f"294: llaves foráneas rotas tras reconstruir: {problemas[:5]}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.execute(f"PRAGMA legacy_alter_table={'ON' if legacy_previo else 'OFF'}")
        conn.execute(f"PRAGMA foreign_keys={'ON' if fk_previo else 'OFF'}")


def run(conn) -> None:
    from backend.application.services.finance.finance_bootstrap import (
        ensure_finance_catalog_additions,
    )
    from backend.infrastructure.db.schema.loyalty_finance_schema import (
        create_loyalty_finance_tables,
    )

    sql = _obligations_sql(conn)
    reconstruida = False
    if sql is not None and _TIPO not in sql:
        _rebuild_obligations(conn, sql)
        reconstruida = True
    create_loyalty_finance_tables(conn)
    conn.commit()
    catalogo = ensure_finance_catalog_additions(conn) if sql is not None else False
    logger.info("294: puente Fidelidad→Finanzas listo (obligaciones %s; catálogo %s).",
                "reconstruidas" if reconstruida else "sin cambios",
                "completado" if catalogo else "aún sin sembrar")


up = run
