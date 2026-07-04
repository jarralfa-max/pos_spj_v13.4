"""Protection tests — TARJETAS_FIDELIDAD born-clean (UUIDv7).

Capturan el comportamiento del subsistema de tarjetas tras el corte born-clean:
identidad UUIDv7 (sin autoincrement, sin doble identidad `uuid`), motor
CardBatchEngine y repositorio TarjetaRepository funcionando sobre el esquema
TEXT, y registros de historial con id propio.
"""
import sqlite3

import pytest

import migrations.m000_base_schema as base
from migrations import engine as migrator
from core.services.card_batch_engine import CardBatchEngine
from repositories.tarjetas import TarjetaRepository
from backend.shared.ids import new_uuid


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    base.up(conn)
    conn.commit()
    migrator.up(conn)
    conn.commit()
    return conn


def _is_uuid(v) -> bool:
    return isinstance(v, str) and len(v) == 36 and v.count("-") == 4


# ── CardBatchEngine ──────────────────────────────────────────────────────────

def test_crear_lote_mints_uuid_ids_for_batch_and_cards():
    conn = _db()
    eng = CardBatchEngine(conn, usuario="qa")
    batch = eng.crear_lote("Lote QA", prefijo="QA", cantidad=4)

    assert _is_uuid(batch.id)
    assert not hasattr(batch, "uuid")  # doble identidad eliminada
    ids = [r[0] for r in conn.execute("SELECT id FROM tarjetas_fidelidad WHERE batch_id=?", (batch.id,))]
    assert len(ids) == 4
    assert all(_is_uuid(i) for i in ids)
    # card_batches ya no tiene columna uuid paralela
    cols = {r[1] for r in conn.execute("PRAGMA table_info(card_batches)").fetchall()}
    assert "uuid" not in cols


def test_asignar_bloquear_flow_and_history_have_uuid_ids():
    conn = _db()
    eng = CardBatchEngine(conn, usuario="qa")
    batch = eng.crear_lote("Lote QA", prefijo="QA", cantidad=2)
    eng.marcar_impreso(batch.id)
    eng.liberar_lote(batch.id)

    libres = eng.tarjetas_libres(batch.id)
    assert len(libres) == 2
    card = libres[0]

    ok = eng.asignar_tarjeta(card.id, "cliente-1")
    assert ok.exito is True
    assert eng._load_tarjeta(card.id).estado == "asignada"

    blk = eng.bloquear_tarjeta(card.id, motivo="extraviada")
    assert blk.exito is True
    assert eng._load_tarjeta(card.id).estado == "bloqueada"

    hist = eng.historial_tarjeta(card.id)
    assert len(hist) >= 2  # asignacion + bloqueo
    hid = conn.execute("SELECT id FROM card_assignment_history LIMIT 1").fetchone()[0]
    assert _is_uuid(hid)


# ── TarjetaRepository ────────────────────────────────────────────────────────

def test_repository_create_and_pregeneradas_mint_uuid_ids():
    conn = _db()
    repo = TarjetaRepository(conn)

    cid = repo.create({"estado": "disponible", "puntos": 0, "nivel": "Bronce"})
    assert _is_uuid(cid)

    gen = repo.generate_pregeneradas(3, "qa")
    assert len(gen) == 3
    assert all(_is_uuid(g["id"]) for g in gen)


def test_repository_history_rows_have_uuid_id():
    conn = _db()
    cli_id = new_uuid()
    conn.execute("INSERT INTO clientes (id, nombre, activo, puntos) VALUES (?,'Ana',1,5)", (cli_id,))
    conn.commit()

    repo = TarjetaRepository(conn)
    cid = repo.create({"estado": "disponible", "puntos": 0})
    repo.assign_to_client(cid, cli_id, "qa")

    hist = repo.get_historial(cid)
    assert len(hist) >= 1
    hid = conn.execute("SELECT id FROM historico_tarjetas LIMIT 1").fetchone()[0]
    assert _is_uuid(hid)
