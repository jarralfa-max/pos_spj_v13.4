"""Regresión de bugs del módulo BI (reportes_bi_v2).

Bug 1 — Rentabilidad: 'Costo Total' y 'Unidades' salían en cero, y el nombre
        aparecía como 'Prod <id>'. AnalyticsEngine.product_profitability_detail
        ahora devuelve nombre, categoría, unidades y costo real.
Bug 2 — Motor de sugerencias: _suggest_hr consultaba la tabla inexistente
        'empleados' (born-clean usa 'personal'); el costo ignoraba costo_promedio.
Bug 3 — Franquicias: ranking_sucursales devuelve ingresos/tickets/margen_pct/
        posicion (la UI leía llaves equivocadas) y el margen ahora es bruto (COGS).
"""
import sqlite3

import pytest

from backend.shared.ids import new_uuid


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    from migrations import engine
    engine.up(conn)
    conn.commit()
    return conn


def _producto(db, nombre, precio, costo_col, costo_val, categoria="General"):
    pid = new_uuid()
    cols = "id,nombre,precio,categoria,unidad,activo," + costo_col
    db.execute(
        f"INSERT INTO productos ({cols}) VALUES (?,?,?,?,?,1,?)",
        (pid, nombre, precio, categoria, "pz", costo_val),
    )
    return pid


def _venta(db, sucursal_id, total, cliente_id="c1", estado="completada"):
    vid = new_uuid()
    db.execute(
        "INSERT INTO ventas (id,folio,total,estado,fecha,sucursal_id,cliente_id) "
        "VALUES (?,?,?,?,datetime('now'),?,?)",
        (vid, f"F{total}", total, estado, sucursal_id, cliente_id),
    )
    return vid


def _detalle(db, vid, pid, cantidad, precio_unit, costo_real=0):
    db.execute(
        "INSERT INTO detalles_venta "
        "(id,venta_id,producto_id,cantidad,precio_unitario,subtotal,costo_unitario_real,nombre) "
        "VALUES (?,?,?,?,?,?,?,(SELECT nombre FROM productos WHERE id=?))",
        (new_uuid(), vid, pid, cantidad, precio_unit, cantidad * precio_unit, costo_real, pid),
    )


# ── Bug 1 ────────────────────────────────────────────────────────────────────

def test_rentabilidad_detalle_incluye_unidades_nombre_y_costo(db):
    from core.services.analytics.analytics_engine import AnalyticsEngine
    suc = new_uuid()
    # costo del producto en columna 'precio_compra' (no 'costo')
    pid = _producto(db, "Pechuga", 100.0, "precio_compra", 60.0)
    vid = _venta(db, suc, 200.0)
    _detalle(db, vid, pid, cantidad=2, precio_unit=100.0)  # sin costo_real → usa producto
    db.commit()

    rows = AnalyticsEngine(db).product_profitability_detail(
        "2000-01-01", "2099-01-01", suc)
    assert len(rows) == 1
    r = rows[0]
    assert r["nombre"] == "Pechuga"          # no "Prod <id>"
    assert r["categoria"] == "General"
    assert r["unidades"] == 2.0              # ya no es 0
    assert r["ingresos"] == 200.0
    assert r["costo"] == 120.0               # 2 * 60 (ya no 0)
    assert r["margen"] == 80.0


def test_rentabilidad_usa_costo_real_de_linea(db):
    from core.services.analytics.analytics_engine import AnalyticsEngine
    suc = new_uuid()
    pid = _producto(db, "Combo", 50.0, "costo", 0.0)   # producto sin costo
    vid = _venta(db, suc, 50.0)
    _detalle(db, vid, pid, cantidad=1, precio_unit=50.0, costo_real=18.0)  # costo capturado
    db.commit()
    rows = AnalyticsEngine(db).product_profitability_detail(
        "2000-01-01", "2099-01-01", suc)
    assert rows[0]["costo"] == 18.0


# ── Bug 2 ────────────────────────────────────────────────────────────────────

def test_suggest_hr_usa_tabla_personal(db):
    from core.services.decision_engine import DecisionEngine
    # personal activo + ventas bajas → debe disparar sugerencia HR
    db.execute("INSERT INTO personal (id,nombre,activo) VALUES (?,?,1)",
               (new_uuid(), "Juan"))
    _venta(db, new_uuid(), 500.0)  # ingresos bajos por empleado
    db.commit()
    eng = DecisionEngine(db, module_config=None)
    sugs = eng._suggest_hr()
    assert any(s.tipo == "hr" for s in sugs)


def test_pricing_detecta_costo_en_costo_promedio(db):
    from core.services.decision_engine import DecisionEngine
    # costo sólo en costo_promedio; precio por debajo del umbral
    _producto(db, "Refresco", 10.0, "costo_promedio", 9.5)
    db.commit()
    eng = DecisionEngine(db, module_config=None)
    sugs = eng._suggest_pricing()
    assert any(s.tipo == "pricing" for s in sugs)


def test_sugerencias_sin_costos_produce_insights_de_ventas(db):
    """El motor debe entregar insights aunque los productos no tengan costo."""
    from core.services.decision_engine import DecisionEngine
    suc = new_uuid()
    db.execute("INSERT INTO sucursales (id,nombre,activa) VALUES (?,?,1)",
               (suc, "San Bartolo"))
    pid = _producto(db, "Pechuga", 100.0, "costo", 0.0, categoria="Aves")  # sin costo
    for _ in range(4):
        vid = _venta(db, suc, 200.0)
        _detalle(db, vid, pid, cantidad=2, precio_unit=100.0)
    db.commit()
    sugs = DecisionEngine(db, module_config=None).generar_sugerencias(sucursal_id=suc)
    titulos = " | ".join(s["titulo"] for s in sugs)
    assert sugs, "debe haber al menos un insight"
    assert "San Bartolo" in titulos      # sucursal líder
    assert "Aves" in titulos             # categoría líder


def test_persist_decision_log_usa_columnas_correctas(db):
    """_persist inserta en decision_log con id UUID y columnas reales del schema."""
    from core.services.decision_engine import DecisionEngine, Suggestion
    eng = DecisionEngine(db, module_config=None)
    eng._persist(Suggestion(tipo="pricing", prioridad="alta", titulo="X",
                            impacto_estimado="Y"), sucursal_id="suc-1")
    row = db.execute(
        "SELECT id, tipo, impacto_est, accion, sucursal_id FROM decision_log"
    ).fetchone()
    assert row is not None
    assert row["id"] and len(str(row["id"])) >= 32   # UUID explícito
    assert row["impacto_est"] == "Y"
    assert row["sucursal_id"] == "suc-1"


# ── Bug 3 ────────────────────────────────────────────────────────────────────

def test_franchise_ranking_keys_y_margen_bruto(db):
    from core.services.franchise_manager import FranchiseManager
    suc = new_uuid()
    db.execute("INSERT INTO sucursales (id,nombre,activa) VALUES (?,?,1)",
               (suc, "Centro"))
    pid = _producto(db, "Pan", 20.0, "precio_compra", 8.0)
    vid = _venta(db, suc, 40.0)
    _detalle(db, vid, pid, cantidad=2, precio_unit=20.0)
    db.commit()

    ranking = FranchiseManager(db).ranking_sucursales()
    r = next(x for x in ranking if x["sucursal_id"] == suc)
    # Llaves que la UI consume ahora
    assert r["ingresos"] == 40.0
    assert r["tickets"] == 1
    assert r["ticket_promedio"] == 40.0
    assert r["posicion"] == 1
    # Margen bruto = (40 - 16) / 40 = 60%
    assert r["costo_ventas"] == 16.0
    assert r["margen_pct"] == 60.0
