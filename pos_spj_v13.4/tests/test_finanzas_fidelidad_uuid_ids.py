# tests/test_finanzas_fidelidad_uuid_ids.py
"""REGLA CERO — finanzas/fidelidad no deben castear identidades de dominio a int.

Antes, la UI hacía int(row["id"]) sobre rifas (raffles.id TEXT/UUID) e
int(str(combo).split(...)) sobre tercero_id (cliente/proveedor UUID). En el
esquema born-clean eso REVIENTA (ValueError al int() de un UUID). Aquí:
1) se verifica que ya no quedan esos casts de id en el código UI, y
2) que los métodos de rifas aceptan un raffle_id str (UUID) sin crashear.
"""
import re
import sqlite3
from pathlib import Path

import pytest

from backend.shared.ids import new_uuid

ROOT = Path(__file__).resolve().parents[1]


def test_ui_no_castea_ids_de_dominio_a_int():
    finanzas = (ROOT / "modulos/finanzas_unificadas.py").read_text(encoding="utf-8")
    fidelidad = (ROOT / "modulos/fidelidad_config.py").read_text(encoding="utf-8")
    # Patrones prohibidos (identidad de dominio → int)
    assert "int(row[\"id\"])" not in fidelidad
    assert "int(row['id'])" not in fidelidad
    assert not re.search(r"int\(\s*winner\.get\(", fidelidad)
    assert not re.search(r"int\(str\(seleccionado\)\.split", finanzas)
    assert not re.search(r"int\(str\(sel\)\.split", finanzas)
    assert not re.search(r"get_proveedor\(\s*int\(", finanzas)


def _raffle_service():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    from core.services.loyalty_service import LoyaltyService
    svc = LoyaltyService(db, sucursal_id=1)
    svc._app.repo.ensure_raffle_tables()
    return svc, db


def _seed_raffle(db) -> str:
    rid = new_uuid()
    db.execute(
        "INSERT INTO raffles(id,nombre,premio,monto_por_boleto,max_boletos_por_cliente,"
        "estado,financial_status,fecha_inicio,fecha_fin,sucursal_id) "
        "VALUES(?,'Navidad','Canasta',100,99,'borrador','pendiente',"
        "'2026-01-01 00:00:00','2026-12-31 23:59:59','1')",
        (rid,),
    )
    db.commit()
    return rid


def test_metodos_de_rifa_aceptan_raffle_id_uuid_str():
    """El raffle_id es un UUID (str). Los métodos no deben castear a int ni crashear."""
    svc, db = _raffle_service()
    rid = _seed_raffle(db)
    assert isinstance(rid, str)
    # Lecturas/operaciones con id str no deben lanzar (antes la UI hacía int(rid))
    tickets = svc.list_raffle_tickets(rid, limit=10)
    assert isinstance(tickets, list)
    # reserve_raffle_budget acepta el id str y devuelve algo booleano-compatible
    ok = svc.reserve_raffle_budget(rid, 500.0, "tester", f"ui:reserve:{rid}")
    assert ok in (True, False)
