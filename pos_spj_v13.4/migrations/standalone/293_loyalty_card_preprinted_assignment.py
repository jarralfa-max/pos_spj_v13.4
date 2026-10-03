"""293 — tarjetas preimpresas y su asignación (LOY-29, §44-45).

Una tarjeta preimpresa nace con número y QR pero SIN cliente ni membresía
(estado `UNASSIGNED`); se asigna después y sólo entonces se activa. Para eso:

* `loyalty_cards.customer_id` y `membership_id` pasan a admitir NULL. SQLite no
  permite quitar un NOT NULL con ALTER, así que la tabla se reconstruye con el
  procedimiento documentado: llaves foráneas desactivadas, tabla nueva, copia,
  DROP y RENAME (con `legacy_alter_table=ON`, porque la base real trae una vista
  legacy rota que el RENAME moderno revalidaría — ver la 292), y verificación de
  llaves foráneas al final.
* Nueva `loyalty_card_assignments`: quién asignó cada tarjeta, cuándo, dónde y
  por qué (una por tarjeta, idempotente por `operation_id`).

Idempotente: si `customer_id` ya admite NULL no reconstruye nada.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.293")

_NUEVA = """
    CREATE TABLE loyalty_cards__new (
        id TEXT NOT NULL PRIMARY KEY,
        card_number TEXT NOT NULL UNIQUE,
        card_type TEXT NOT NULL,
        customer_id TEXT,
        membership_id TEXT,
        status TEXT NOT NULL DEFAULT 'ISSUED',
        issued_at TEXT NOT NULL,
        activated_at TEXT,
        blocked_at TEXT,
        block_reason TEXT,
        replaces_card_id TEXT REFERENCES loyalty_cards(id),
        replaced_by_card_id TEXT REFERENCES loyalty_cards(id),
        cancelled_at TEXT,
        cancel_reason TEXT,
        expires_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )"""

_COLUMNAS = ("id, card_number, card_type, customer_id, membership_id, status, issued_at,"
             " activated_at, blocked_at, block_reason, replaces_card_id, replaced_by_card_id,"
             " cancelled_at, cancel_reason, expires_at, created_at, updated_at")


def _customer_is_not_null(conn) -> bool:
    for fila in conn.execute("PRAGMA table_info(loyalty_cards)"):
        if fila[1] == "customer_id":
            return bool(fila[3])
    return False


def run(conn) -> None:
    from backend.infrastructure.db.schema.loyalty_cards_schema import create_loyalty_cards_schema

    reconstruida = False
    if _customer_is_not_null(conn):
        conn.commit()
        fk_previo = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        legacy_previo = conn.execute("PRAGMA legacy_alter_table").fetchone()[0]
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("PRAGMA legacy_alter_table=ON")
        try:
            conn.execute(_NUEVA)
            conn.execute(f"INSERT INTO loyalty_cards__new ({_COLUMNAS})"
                         f" SELECT {_COLUMNAS} FROM loyalty_cards")
            conn.execute("DROP TABLE loyalty_cards")
            conn.execute("ALTER TABLE loyalty_cards__new RENAME TO loyalty_cards")
            problemas = conn.execute("PRAGMA foreign_key_check").fetchall()
            if problemas:
                raise RuntimeError(f"293: llaves foráneas rotas tras reconstruir: {problemas[:5]}")
            conn.commit()
            reconstruida = True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.execute(f"PRAGMA legacy_alter_table={'ON' if legacy_previo else 'OFF'}")
            conn.execute(f"PRAGMA foreign_keys={'ON' if fk_previo else 'OFF'}")
    # Índices de la tabla reconstruida y la tabla de asignaciones (IF NOT EXISTS).
    create_loyalty_cards_schema(conn)
    conn.commit()
    logger.info("293: loyalty_cards %s; asignaciones listas.",
                "reconstruida" if reconstruida else "ya admitía tarjetas sin asignar")


up = run
