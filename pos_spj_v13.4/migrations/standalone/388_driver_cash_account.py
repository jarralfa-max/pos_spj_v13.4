"""388 — cuenta y perfil para el efectivo en poder de repartidores (SDLC-ORD-001).

`finance_bootstrap` no toca un catálogo ya sembrado, así que una base existente
no recibiría la cuenta 1104 ni el perfil DRIVER_CASH. Sin ellos, los cobros de
repartidor quedarían pendientes en `orders_delivery_outbox`.

Sólo agrega, e idempotente. Si el catálogo aún no está sembrado no hace nada:
`finance_bootstrap` lo crea completo al arrancar.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from backend.shared.ids import new_uuid


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def run(conn) -> None:
    if not (_table_exists(conn, "accounts") and _table_exists(conn, "posting_profiles")):
        return
    padre = conn.execute("SELECT id FROM accounts WHERE code='1100'").fetchone()
    if padre is None:
        return
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute(
        "INSERT OR IGNORE INTO accounts (id, code, name, account_type, normal_balance,"
        " parent_account_id, posting_allowed, reconciliation_required, currency_code,"
        " cash_flow_category, active, created_at, updated_at)"
        " VALUES (?,'1104','Efectivo en poder de repartidores','ASSET','DEBIT',?,1,0,'MXN',"
        "'OPERATING',1,?,?)",
        (new_uuid(), padre[0], ahora, ahora))
    cuenta = conn.execute("SELECT id FROM accounts WHERE code='1104'").fetchone()[0]
    if conn.execute("SELECT 1 FROM posting_profiles WHERE profile_key='DRIVER_CASH'"
                    ).fetchone() is None:
        desde = conn.execute("SELECT MIN(effective_from) FROM posting_profiles").fetchone()[0]
        conn.execute(
            "INSERT INTO posting_profiles (id, profile_key, description, accounts_json,"
            " effective_from, active, created_at, updated_at)"
            " VALUES (?,'DRIVER_CASH','Efectivo en poder de repartidores',?,?,1,?,?)",
            (new_uuid(), json.dumps({"driver_cash_account_id": cuenta}),
             desde or ahora[:10], ahora, ahora))
    conn.commit()
