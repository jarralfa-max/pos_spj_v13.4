"""Para qué sirve cada almacén (Fase 10): venta, compra, producción, cuarentena.

Decisión del usuario: casillas en Inventario → Almacenes, un estándar único
para todos los módulos. Ventas descuenta del almacén marcado «Venta», Cárnico
despieza en el de «Producción». Antes las casillas existían en el dominio pero
NINGUNA pantalla las escribía: Cárnico no podía ni crear una orden porque la
sucursal no tenía almacén de producción y la sesión no trae uno.
"""
from __future__ import annotations

import sqlite3

import pytest

from backend.application.inventory.use_cases.warehouse_use_cases import (
    CreateWarehouseUseCase,
    UpdateWarehouseUseCase,
)
from backend.application.logistics.warehouse_directory import (
    WarehouseDirectoryQueryService,
)
from backend.domain.inventory.enums import WarehouseType
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.shared.ids import new_uuid

SUCURSAL, ACTOR = new_uuid(), new_uuid()


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    try:
        yield c
    finally:
        c.close()


def _crear(conn, code, **usos):
    r = CreateWarehouseUseCase().execute(
        conn, code=code, name=code, branch_id=SUCURSAL,
        warehouse_type=WarehouseType.STORE, actor_user_id=ACTOR, **usos)
    assert r.success, r.message
    return r.entity_id


class TestAltaConUsos:
    def test_las_casillas_del_alta_llegan_hasta_la_tabla(self, conn):
        wid = _crear(conn, "PLANTA", allow_production=True, allow_sales_allocation=False)
        fila = conn.execute("SELECT allow_production, allow_sales_allocation FROM warehouses"
                            " WHERE id=?", (wid,)).fetchone()
        assert fila[0] == 1 and fila[1] == 0

    def test_sin_casillas_manda_el_valor_del_dominio(self, conn):
        wid = _crear(conn, "TIENDA")
        fila = conn.execute(
            "SELECT allow_sales_allocation, allow_purchase_receipt, allow_production,"
            " allow_quarantine FROM warehouses WHERE id=?", (wid,)).fetchone()
        assert tuple(fila) == (1, 1, 0, 0)

    def test_la_edicion_puede_marcar_produccion_despues(self, conn):
        wid = _crear(conn, "CADENAS")
        assert UpdateWarehouseUseCase().execute(
            conn, warehouse_id=wid, actor_user_id=ACTOR, allow_production=True).success
        assert conn.execute("SELECT allow_production FROM warehouses WHERE id=?",
                            (wid,)).fetchone()[0] == 1

    def test_la_edicion_sin_usos_no_los_pisa(self, conn):
        wid = _crear(conn, "PLANTA", allow_production=True)
        assert UpdateWarehouseUseCase().execute(
            conn, warehouse_id=wid, actor_user_id=ACTOR, name="Planta Norte").success
        fila = conn.execute("SELECT name, allow_production FROM warehouses WHERE id=?",
                            (wid,)).fetchone()
        assert fila[0] == "Planta Norte" and fila[1] == 1


class TestResolucionPorUso:
    def test_un_solo_almacen_marcado_se_resuelve(self, conn):
        wid = _crear(conn, "PLANTA", allow_production=True)
        assert WarehouseDirectoryQueryService(conn).resolve_for_purpose(
            SUCURSAL, "PRODUCTION") == (wid, None)

    def test_sin_almacen_marcado_dice_donde_marcarlo(self, conn):
        _crear(conn, "TIENDA")
        almacen, motivo = WarehouseDirectoryQueryService(conn).resolve_for_purpose(
            SUCURSAL, "PRODUCTION")
        assert almacen is None
        assert "Almacenes" in motivo and "Producción" in motivo

    def test_con_varios_marcados_no_adivina(self, conn):
        _crear(conn, "PLANTA-A", allow_production=True)
        _crear(conn, "PLANTA-B", allow_production=True)
        almacen, motivo = WarehouseDirectoryQueryService(conn).resolve_for_purpose(
            SUCURSAL, "PRODUCTION")
        assert almacen is None and "varios" in motivo

    def test_un_almacen_inactivo_no_cuenta(self, conn):
        wid = _crear(conn, "PLANTA", allow_production=True)
        conn.execute("UPDATE warehouses SET status='INACTIVE' WHERE id=?", (wid,))
        conn.commit()
        assert WarehouseDirectoryQueryService(conn).resolve_for_purpose(
            SUCURSAL, "PRODUCTION")[0] is None

    def test_cada_uso_mira_su_propia_casilla(self, conn):
        planta = _crear(conn, "PLANTA", allow_production=True,
                        allow_sales_allocation=False, allow_purchase_receipt=False)
        tienda = _crear(conn, "TIENDA")
        svc = WarehouseDirectoryQueryService(conn)
        assert svc.resolve_for_purpose(SUCURSAL, "PRODUCTION")[0] == planta
        assert svc.resolve_for_purpose(SUCURSAL, "SALES")[0] == tienda
        assert svc.resolve_for_purpose(SUCURSAL, "PURCHASE")[0] == tienda

    def test_otra_sucursal_no_se_cruza(self, conn):
        _crear(conn, "PLANTA", allow_production=True)
        assert WarehouseDirectoryQueryService(conn).resolve_for_purpose(
            new_uuid(), "PRODUCTION")[0] is None
