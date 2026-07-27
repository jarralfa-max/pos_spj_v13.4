# tests/test_loyalty_card_designer_service.py
"""Remediación F — Red de seguridad para LoyaltyCardDesignerService.

Caracteriza los efectos en BD del SQL extraído de modulos/loyalty_card_designer.py:
plantilla, pregeneración de tarjetas, lotes PDF, lookup de clientes e historial.
Incluye el bugfix de identidad born-clean de lotes_tarjetas_pdf.

Nota: varias operaciones de administración (ajustar_puntos, cambiar_nivel,
bloquear_tarjeta, asignar_tarjeta_nueva, listar_tarjetas, listar_tarjetas_
pregeneradas) referencian columnas legacy (`codigo`/`puntos`) inexistentes en el
esquema born-clean y ya fallaban en runtime antes de esta extracción. El servicio
preserva ese SQL verbatim; aquí se documenta el comportamiento (levantan
OperationalError) en vez de asumir que funcionan.
"""
import json
import sqlite3

import pytest


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    from migrations import engine
    engine.up(conn)
    conn.commit()
    return conn


def _svc(db):
    from core.services.loyalty_card_designer_service import LoyaltyCardDesignerService
    return LoyaltyCardDesignerService(db)


def test_plantilla_roundtrip(db):
    svc = _svc(db)
    assert svc.obtener_plantilla() is None
    svc.guardar_plantilla(json.dumps({"color": "oro"}))
    row = svc.obtener_plantilla()
    assert row is not None and json.loads(row[0])["color"] == "oro"
    # INSERT OR REPLACE sobrescribe
    svc.guardar_plantilla(json.dumps({"color": "plata"}))
    assert json.loads(svc.obtener_plantilla()[0])["color"] == "plata"


def test_generar_tarjetas_pregeneradas(db):
    """La variante 1 del INSERT usa `codigo` (inexistente) → cae al fallback que
    inserta con codigo_qr; deben quedar N tarjetas con id UUID no nulo."""
    svc = _svc(db)
    cards = svc.generar_tarjetas_pregeneradas(3, "Oro")
    assert len(cards) == 3
    rows = db.execute(
        "SELECT id, codigo_qr, nivel, es_pregenerada FROM tarjetas_fidelidad"
    ).fetchall()
    assert len(rows) == 3
    for r in rows:
        assert r["id"] is not None           # identidad born-clean
        assert r["codigo_qr"] and r["codigo_qr"].startswith("SPJ")
        assert r["nivel"] == "Oro"
        assert r["es_pregenerada"] == 1


def test_registrar_lote_genera_id(db):
    """Bugfix: antes el INSERT omitía id (TEXT PK) → id=NULL."""
    svc = _svc(db)
    lote_id = svc.registrar_lote(50, "Bronce", "/tmp/x.pdf", json.dumps({"a": 1}), "ana")
    assert lote_id and isinstance(lote_id, str)
    hist = svc.listar_historial_lotes()
    assert len(hist) == 1
    # columnas: created_at, cantidad, nivel, ruta_pdf, id
    assert hist[0][1] == 50 and hist[0][2] == "Bronce" and hist[0][4] == lote_id
    # id realmente persistido, no NULL
    assert db.execute("SELECT id FROM lotes_tarjetas_pdf").fetchone()[0] == lote_id


def test_listar_clientes_lookup(db):
    svc = _svc(db)
    db.execute("INSERT INTO clientes (id,nombre,activo) VALUES ('c1','Ana',1)")
    db.execute("INSERT INTO clientes (id,nombre,activo) VALUES ('c2','Beto',0)")
    db.commit()
    rows = svc.listar_clientes_lookup()
    assert [r[1] for r in rows] == ["Ana"]   # sólo activos


def test_metodos_con_columnas_legacy_fallan_como_antes(db):
    """Documenta la deuda preexistente: estas operaciones referencian `codigo`/
    `puntos` inexistentes en born-clean y levantan OperationalError (la UI las
    envuelve en try/except, por eso nunca reventaron visiblemente)."""
    svc = _svc(db)
    for call in (
        lambda: svc.ajustar_puntos("SPJ1", 10),
        lambda: svc.cambiar_nivel("SPJ1", "Oro"),
        lambda: svc.bloquear_tarjeta("SPJ1"),
        lambda: svc.listar_tarjetas(),
        lambda: svc.listar_tarjetas_pregeneradas("Todos", False, 5),
    ):
        with pytest.raises(sqlite3.OperationalError):
            call()
