"""Caja registra las ventas del turno (fuente única + hora local).

Bug reportado: los KPIs de caja no mostraban nada y el efectivo esperado del
corte Z siempre era 0. Causa: la apertura del turno se escribía en UTC
(datetime('now') de SQLite) mientras las ventas escriben hora local
(datetime.now() de Python) — en husos negativos la apertura quedaba en el
futuro y ninguna venta entraba al filtro `fecha >= fecha_apertura`. Además
había dos implementaciones de turno/corte (FinanceService y
CajaApplicationService): ahora hay UNA (CajaApplicationService) y
FinanceService solo delega.
"""
from __future__ import annotations

from datetime import datetime

from application.services.caja_application_service import CajaApplicationService
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


def _venta_local(conn, sucursal_id: str, total: float, forma: str = "Efectivo",
                 estado: str = "completada", **extra_cols) -> str:
    """Inserta una venta como lo hace el POS real: fecha en HORA LOCAL."""
    vid = new_uuid()
    cols = ["id", "folio", "sucursal_id", "total", "forma_pago", "estado", "fecha"]
    vals = [vid, f"F-{vid[:6]}", sucursal_id, total, forma, estado,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
    for k, v in extra_cols.items():
        cols.append(k)
        vals.append(v)
    conn.execute(
        f"INSERT INTO ventas ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
        vals,
    )
    return vid


def test_apertura_de_turno_queda_en_hora_local():
    conn = make_db()
    svc = CajaApplicationService(conn)
    suc = new_uuid()
    svc.abrir_turno(suc, "cajera", 100.0)
    row = conn.execute(
        "SELECT fecha_apertura <= datetime('now','localtime') FROM turnos_caja"
        " WHERE sucursal_id=? AND estado='abierto'",
        (suc,),
    ).fetchone()
    assert row[0] == 1, "la apertura no puede quedar en el futuro local (era UTC)"


def test_kpis_acumulan_ventas_locales_del_turno():
    conn = make_db()
    svc = CajaApplicationService(conn)
    suc = new_uuid()
    svc.abrir_turno(suc, "cajera", 100.0)
    _venta_local(conn, suc, 250.0, "Efectivo")
    _venta_local(conn, suc, 80.0, "Tarjeta")
    kpi = svc.get_caja_kpis(suc, "cajera")
    assert kpi["fondo_inicial"] == 100.0
    assert kpi["total_ventas_turno"] == 330.0
    assert kpi["total_efectivo_turno"] == 250.0


def test_corte_z_efectivo_esperado_incluye_ventas_y_mixto():
    conn = make_db()
    svc = CajaApplicationService(conn)
    suc = new_uuid()
    turno_id = svc.abrir_turno(suc, "cajera", 100.0)
    _venta_local(conn, suc, 200.0, "Efectivo")
    _venta_local(conn, suc, 150.0, "Tarjeta")
    # Pago mixto: $90 total, recibió $60 en efectivo y dio $10 de cambio
    _venta_local(conn, suc, 90.0, "Pago Mixto",
                 efectivo_recibido=60.0, cambio=10.0)
    res = svc.generar_corte_z(
        turno_id=turno_id, sucursal_id=suc, usuario="cajera",
        efectivo_fisico=350.0,
    )
    # esperado = fondo 100 + efectivo 200 + porción mixto (60-10)=50 → 350
    assert res["efectivo_esperado"] == 350.0
    assert res["diferencia"] == 0.0
    assert res["total_ventas"] == 440.0


def test_corte_z_es_idempotente_por_turno():
    conn = make_db()
    svc = CajaApplicationService(conn)
    suc = new_uuid()
    turno_id = svc.abrir_turno(suc, "cajera", 50.0)
    _venta_local(conn, suc, 100.0, "Efectivo")
    r1 = svc.generar_corte_z(turno_id=turno_id, sucursal_id=suc,
                             usuario="cajera", efectivo_fisico=150.0)
    r2 = svc.generar_corte_z(turno_id=turno_id, sucursal_id=suc,
                             usuario="cajera", efectivo_fisico=150.0)
    assert r1["cierre_id"] == r2["cierre_id"]
    n = conn.execute(
        "SELECT COUNT(*) FROM cierres_caja WHERE turno_id=?", (turno_id,)
    ).fetchone()[0]
    assert n == 1


def test_finance_service_delega_sin_logica_duplicada():
    """FinanceService no reimplementa turnos: delega en CajaApplicationService."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[2] / "core" / "services" /
           "enterprise" / "finance_service.py").read_text(encoding="utf-8")
    assert "INSERT INTO turnos_caja" not in src
    assert "INSERT INTO cierres_caja" not in src
    assert "CajaApplicationService" in src
    # register_income (log VENTA por venta) es una función distinta y se queda;
    # lo prohibido es reimplementar turnos/corte.
    assert "def abrir_turno" in src and "self.caja_app.abrir_turno" in src
    assert "def generar_corte_z" in src and "self.caja_app.generar_corte_z" in src


def test_migracion_117_remienda_apertura_utc_existente():
    """Turno abierto con apertura UTC (futuro local) queda contando ventas.

    Reproduce el huso real del reporte (México, UTC-6): fija TZ y siembra la
    apertura con datetime('now') — exactamente lo que escribía el código viejo.
    """
    import importlib
    import os
    import time

    import pytest

    if not hasattr(time, "tzset"):
        pytest.skip("tzset no disponible en esta plataforma")

    tz_original = os.environ.get("TZ")
    os.environ["TZ"] = "America/Mexico_City"
    time.tzset()
    try:
        conn = make_db()
        suc = new_uuid()
        turno_id = new_uuid()
        # Fila vieja: apertura UTC (queda ~6 h en el futuro local)
        conn.execute(
            "INSERT INTO turnos_caja (id, sucursal_id, cajero, fondo_inicial,"
            " estado, fecha_apertura) VALUES (?,?,?,?, 'abierto', datetime('now'))",
            (turno_id, suc, "cajera", 100.0),
        )
        futuro = conn.execute(
            "SELECT fecha_apertura > datetime('now','localtime') FROM turnos_caja"
            " WHERE id=?", (turno_id,),
        ).fetchone()[0]
        assert futuro == 1, "precondición: la apertura UTC debe estar en el futuro local"

        mig = importlib.import_module(
            "migrations.standalone.117_caja_localtime_normalization"
        )
        mig.run(conn)
        row = conn.execute(
            "SELECT fecha_apertura <= datetime('now','localtime') FROM turnos_caja"
            " WHERE id=?", (turno_id,),
        ).fetchone()
        assert row[0] == 1

        # Idempotente: segunda corrida no vuelve a desplazar
        antes = conn.execute(
            "SELECT fecha_apertura FROM turnos_caja WHERE id=?", (turno_id,)
        ).fetchone()[0]
        mig.run(conn)
        despues = conn.execute(
            "SELECT fecha_apertura FROM turnos_caja WHERE id=?", (turno_id,)
        ).fetchone()[0]
        assert antes == despues

        # Y con la apertura remendada, las ventas locales SÍ cuentan
        svc = CajaApplicationService(conn)
        _venta_local(conn, suc, 120.0, "Efectivo")
        kpi = svc.get_caja_kpis(suc, "cajera")
        assert kpi["total_ventas_turno"] == 120.0
    finally:
        if tz_original is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = tz_original
        time.tzset()
