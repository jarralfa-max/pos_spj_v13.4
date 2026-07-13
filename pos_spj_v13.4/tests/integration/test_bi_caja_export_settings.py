"""FASE 8/11 — sección Caja, configuración BI (umbrales) y exportación."""
from datetime import date

import pytest

from backend.application.dto.bi_dashboard_dto import DashboardFilters
from backend.application.queries.bi_dashboard_query_service import BiDashboardQueryService
from backend.application.services.bi_dashboard_service import BiDashboardService
from backend.application.services.bi_export_service import BiExportService
from backend.application.services.bi_settings_service import BiSettingsService
from backend.shared.ids import new_uuid
from tests.integration import bi_seed as S


@pytest.fixture
def conn():
    c = S.fresh_db()
    b = S.add_branch(c)
    p = S.add_product(c, "Pollo", "Aves", 18.0, branch_id=b)
    S.add_sale(c, b, [(p, 3, 30.0, 18.0)], when=S.this_month_day())
    # movimientos de caja
    hoy = S.this_month_day().isoformat()
    c.execute("INSERT INTO movimientos_caja (id,tipo,monto,descripcion,usuario,sucursal_id,fecha) "
              "VALUES (?,?,?,?,?,?,?)", (new_uuid(), "ingreso", 500.0, "venta efvo", "u", b, hoy))
    c.execute("INSERT INTO movimientos_caja (id,tipo,monto,descripcion,usuario,sucursal_id,fecha) "
              "VALUES (?,?,?,?,?,?,?)", (new_uuid(), "egreso", 120.0, "retiro", "u", b, hoy))
    c.commit()
    return c


def test_seccion_caja_ingresos_egresos_saldo(conn):
    svc = BiDashboardService(BiDashboardQueryService(conn))
    d = svc.section_data("caja", DashboardFilters(preset="month"))
    kpis = {k["title"]: k["value"] for k in d["kpis"]}
    assert kpis["Ingresos directos"] == 500.0
    assert kpis["Egresos directos"] == 120.0
    assert kpis["Saldo"] == 380.0


def test_settings_umbral_cambia_alertas(conn):
    settings = BiSettingsService()  # memoria
    # merma 0% (no hay merma) → sin alerta; bajamos umbral de margen para forzar
    settings.set("threshold_margen_bajo_pct", 90.0)   # margen real ~40% < 90 → alerta
    svc = BiDashboardService(BiDashboardQueryService(conn), settings=settings)
    pl = svc.build_dashboard(DashboardFilters(preset="month"))
    assert any(a["code"] == "margen_bajo" for a in pl.alerts)


def test_settings_persisten_en_store():
    store = {}
    class _S:
        def get(self, k, d=None): return store.get(k, d)
        def set(self, k, v): store[k] = v
    settings = BiSettingsService(_S())
    settings.set("threshold_merma_pct", 7.5)
    assert settings.get("threshold_merma_pct") == 7.5
    assert store["bi.threshold_merma_pct"] == 7.5
    # valor inválido cae al default
    settings.set("forecast_window_days", "abc")
    assert settings.get("forecast_window_days") == 30


def test_export_csv_incluye_meta_y_kpis(conn, tmp_path):
    svc = BiDashboardService(BiDashboardQueryService(conn))
    payload = svc.build_dashboard(DashboardFilters(preset="month")).to_dict()
    meta = {"usuario": "diego", "rango": "este mes", "sucursal": "San Bartolo"}
    ruta = str(tmp_path / "resumen.csv")
    escrito = BiExportService().export_summary(payload, meta, ruta, fmt="csv")
    contenido = open(escrito, encoding="utf-8-sig").read()
    assert "Resumen ejecutivo" in contenido
    assert "diego" in contenido and "San Bartolo" in contenido
    assert "Ventas netas" in contenido


def test_export_xlsx_o_csv_fallback(conn, tmp_path):
    svc = BiDashboardService(BiDashboardQueryService(conn))
    payload = svc.build_dashboard(DashboardFilters(preset="month")).to_dict()
    escrito = BiExportService().export_summary(payload, {}, str(tmp_path / "r.xlsx"), fmt="xlsx")
    assert escrito.endswith((".xlsx", ".csv"))
    import os
    assert os.path.exists(escrito)
