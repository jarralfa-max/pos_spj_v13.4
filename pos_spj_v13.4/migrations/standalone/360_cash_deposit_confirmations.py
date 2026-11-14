"""360 — confirmación del depósito por Tesorería (SDLC-CASH-002).

`TreasuryCashDepositConfirmedHandler` (Dr banco / Cr caja) existía sin nadie que
publicara su evento. Tesorería confirma ahora el depósito con su ticket
(respuesta del responsable): una confirmación por depósito. La tabla es de
Tesorería; Caja sólo prepara el paquete. Sólo agrega. Idempotente.
"""

from __future__ import annotations

_DDL = """
CREATE TABLE IF NOT EXISTS cash_deposit_confirmations (
    id TEXT NOT NULL PRIMARY KEY,
    deposit_id TEXT NOT NULL UNIQUE REFERENCES cash_deposit_preparations(id),
    branch_id TEXT NOT NULL,
    amount TEXT NOT NULL CHECK(CAST(amount AS NUMERIC)>0),
    ticket_reference TEXT NOT NULL CHECK(trim(ticket_reference)<>''),
    confirmed_by TEXT NOT NULL,
    operation_id TEXT NOT NULL UNIQUE,
    confirmed_at TEXT NOT NULL
)
"""


def _tabla_existe(conn, nombre: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nombre,)
    ).fetchone() is not None


def run(conn) -> None:
    if _tabla_existe(conn, "cash_deposit_preparations"):
        conn.execute(_DDL)
    conn.commit()


up = run
