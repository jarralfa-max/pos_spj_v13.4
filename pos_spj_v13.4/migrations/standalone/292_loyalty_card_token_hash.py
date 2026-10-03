"""292 — el QR de las tarjetas deja de guardarse en claro (LOY-29, §32).

`loyalty_card_tokens.token` guardaba el token del QR tal cual, y la proyección
digital lo copiaba en `qr_token`. Quien exportara o sincronizara esas tablas se
llevaba todos los QR válidos.

Desde ahora:
* `loyalty_card_tokens` guarda `token_hash` (SHA-256), `token_prefix` (6
  caracteres, para soporte) y `token_version`. El token se deriva con HMAC del
  secreto de la instalación (`loyalty_card_secrets`) y del id del registro.
* `loyalty_digital_card_projections` guarda `token_id`; el QR se deriva al leer.

Filas existentes: su token aleatorio NO se puede derivar, así que se conservan
como huella con `token_version = 0` — siguen resolviendo al escanearse, pero para
reimprimirlas hay que rotar el QR. (En la base real no había ninguna.)

SQLite no permite borrar una columna UNIQUE: ambas tablas se reconstruyen con
copia de datos. Idempotente: si ya tienen la forma nueva, no hace nada.

`RENAME` con `legacy_alter_table=ON`: en modo moderno SQLite revalida TODAS las
vistas al renombrar, y la base real trae una vista legacy rota
(`v_negative_inventory` → `branch_inventory_old`, inexistente) que hacía fallar
esta migración — y con ella el arranque completo. Ninguna vista ni trigger
referencia estas dos tablas, así que no hay nada que reescribir.
"""

from __future__ import annotations

import hashlib
import logging

logger = logging.getLogger("spj.migrations.292")


def _columnas(conn, tabla: str) -> set[str]:
    return {fila[1] for fila in conn.execute(f'PRAGMA table_info("{tabla}")')}


def _rename(conn, origen: str, destino: str) -> None:
    previo = conn.execute("PRAGMA legacy_alter_table").fetchone()[0]
    conn.execute("PRAGMA legacy_alter_table=ON")
    try:
        conn.execute(f'ALTER TABLE "{origen}" RENAME TO "{destino}"')
    finally:
        conn.execute(f"PRAGMA legacy_alter_table={'ON' if previo else 'OFF'}")


def _rebuild_tokens(conn) -> int:
    conn.execute("""
        CREATE TABLE loyalty_card_tokens__new (
            id TEXT NOT NULL PRIMARY KEY,
            card_id TEXT NOT NULL REFERENCES loyalty_cards(id),
            token_hash TEXT NOT NULL UNIQUE,
            token_prefix TEXT NOT NULL,
            token_version INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            created_at TEXT NOT NULL,
            rotated_at TEXT,
            revoked_at TEXT
        )""")
    filas = conn.execute(
        "SELECT id, card_id, token, status, created_at, rotated_at, revoked_at"
        " FROM loyalty_card_tokens").fetchall()
    for id_, card_id, token, status, creado, rotado, revocado in filas:
        conn.execute(
            "INSERT INTO loyalty_card_tokens__new (id, card_id, token_hash, token_prefix,"
            " token_version, status, created_at, rotated_at, revoked_at)"
            " VALUES (?,?,?,?,0,?,?,?,?)",
            (id_, card_id, hashlib.sha256(str(token).encode("utf-8")).hexdigest(),
             str(token)[:6], status, creado, rotado, revocado))
    conn.execute("DROP TABLE loyalty_card_tokens")
    _rename(conn, "loyalty_card_tokens__new", "loyalty_card_tokens")
    return len(filas)


def _rebuild_projections(conn) -> int:
    conn.execute("""
        CREATE TABLE loyalty_digital_card_projections__new (
            id TEXT NOT NULL PRIMARY KEY,
            card_id TEXT NOT NULL UNIQUE REFERENCES loyalty_cards(id),
            customer_id TEXT NOT NULL,
            card_number TEXT NOT NULL,
            token_id TEXT NOT NULL,
            display_fields_json TEXT NOT NULL DEFAULT '{}',
            last_refreshed_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
    filas = conn.execute(
        "SELECT p.id, p.card_id, p.customer_id, p.card_number,"
        " COALESCE((SELECT t.id FROM loyalty_card_tokens t WHERE t.card_id = p.card_id"
        "           AND t.status = 'ACTIVE' LIMIT 1), ''),"
        " p.display_fields_json, p.last_refreshed_at, p.created_at"
        " FROM loyalty_digital_card_projections p").fetchall()
    for fila in filas:
        conn.execute("INSERT INTO loyalty_digital_card_projections__new VALUES (?,?,?,?,?,?,?,?)",
                     fila)
    conn.execute("DROP TABLE loyalty_digital_card_projections")
    _rename(conn, "loyalty_digital_card_projections__new", "loyalty_digital_card_projections")
    return len(filas)


def run(conn) -> None:
    from backend.infrastructure.db.schema.loyalty_cards_schema import create_loyalty_cards_schema

    tokens = proyecciones = 0
    if "token" in _columnas(conn, "loyalty_card_tokens"):
        tokens = _rebuild_tokens(conn)
    if "qr_token" in _columnas(conn, "loyalty_digital_card_projections"):
        proyecciones = _rebuild_projections(conn)
    # Crea `loyalty_card_secrets` y vuelve a crear los índices de las tablas
    # reconstruidas (todo es IF NOT EXISTS).
    create_loyalty_cards_schema(conn)
    conn.commit()
    logger.info("292: tokens migrados a huella: %s; proyecciones: %s", tokens, proyecciones)


up = run
