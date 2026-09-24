"""Tolerancias de rendimiento y siembra de permisos de Cárnico (Fase 10).

Tolerancia GLOBAL configurable (decisión del usuario) y el reparto de permisos
"almacén produce, gerente aprueba". La 271 cierra el mismo hueco que la 260 y
la 268: los permisos finos eran OTORGABLES pero nadie los tenía, así que sólo
admin operaba por comodín de rol.
"""
from __future__ import annotations

import importlib
import sqlite3
from decimal import Decimal

import pytest

from backend.application.meat_processing.authorization import (
    MeatProcessingAuthorizationPolicy,
)
from backend.application.meat_processing.permissions import (
    ALL_MEAT_PROCESSING_PERMISSIONS,
    MeatProcessingPermissions,
)
from backend.application.meat_processing.yield_settings import (
    UpdateYieldTolerancesUseCase,
    YieldToleranceSettingsQueryService,
)
from backend.shared.ids import new_uuid

m270 = importlib.import_module("migrations.standalone.270_meat_processing_execution")
m271 = importlib.import_module(
    "migrations.standalone.271_seed_meat_processing_role_permissions")

ACTOR = new_uuid()


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE configuraciones (clave TEXT PRIMARY KEY, valor TEXT)")
    m270.run(c)
    try:
        yield c
    finally:
        c.close()


class TestTolerancias:
    def test_valores_iniciales_sembrados_por_la_270(self, conn):
        t = YieldToleranceSettingsQueryService(conn).get()
        assert (t.warning_pct, t.tolerance_pct, t.critical_pct) == (
            Decimal("2"), Decimal("5"), Decimal("10"))

    def test_sin_tabla_de_configuraciones_usa_los_valores_del_dominio(self):
        vacia = sqlite3.connect(":memory:")
        t = YieldToleranceSettingsQueryService(vacia).get()
        assert t.tolerance_pct == Decimal("5")
        vacia.close()

    def test_guardar_cambia_lo_que_lee_el_orquestador(self, conn):
        ok, mensaje = UpdateYieldTolerancesUseCase(
            MeatProcessingAuthorizationPolicy.permissive_for_tests()).execute(
            conn, actor_user_id=ACTOR, warning_pct="1", tolerance_pct="3", critical_pct="8")
        assert ok, mensaje
        assert YieldToleranceSettingsQueryService(conn).get().tolerance_pct == Decimal("3")

    def test_el_orden_aviso_tolerancia_critico_es_obligatorio(self, conn):
        ok, mensaje = UpdateYieldTolerancesUseCase(
            MeatProcessingAuthorizationPolicy.permissive_for_tests()).execute(
            conn, actor_user_id=ACTOR, warning_pct="9", tolerance_pct="3", critical_pct="8")
        assert not ok and "aviso" in mensaje
        assert YieldToleranceSettingsQueryService(conn).get().tolerance_pct == Decimal("5")

    def test_un_porcentaje_negativo_o_basura_se_rechaza(self, conn):
        uc = UpdateYieldTolerancesUseCase(
            MeatProcessingAuthorizationPolicy.permissive_for_tests())
        assert not uc.execute(conn, actor_user_id=ACTOR, warning_pct="-1",
                              tolerance_pct="3", critical_pct="8")[0]
        assert not uc.execute(conn, actor_user_id=ACTOR, warning_pct="x",
                              tolerance_pct="3", critical_pct="8")[0]

    def test_sin_permiso_no_se_guarda(self, conn):
        class _Niega:
            def require(self, user_id, permission):
                raise PermissionError(f"Falta {permission}")

        ok, mensaje = UpdateYieldTolerancesUseCase(_Niega()).execute(
            conn, actor_user_id=ACTOR, warning_pct="1", tolerance_pct="3", critical_pct="8")
        assert not ok and MeatProcessingPermissions.SETTINGS_MANAGE in mensaje

    def test_la_270_no_pisa_un_valor_ya_fijado(self, conn):
        conn.execute("UPDATE configuraciones SET valor='7'"
                     " WHERE clave='meat_processing.yield.tolerance_pct'")
        m270.run(conn)
        assert YieldToleranceSettingsQueryService(conn).get().tolerance_pct == Decimal("7")


class TestSiembraDePermisos:
    def test_271_cubre_todo_el_vocabulario_de_carnico(self):
        assert {f"PRODUCCION.{a}" for a in m271._TODAS} == set(ALL_MEAT_PROCESSING_PERMISSIONS)

    def test_almacen_produce_y_gerente_aprueba(self):
        c = sqlite3.connect(":memory:")
        c.executescript("""
            CREATE TABLE roles (id TEXT PRIMARY KEY, nombre TEXT);
            CREATE TABLE rol_permisos (id TEXT, rol_id TEXT, modulo TEXT, accion TEXT,
                permitido INTEGER, UNIQUE(rol_id, modulo, accion));
            INSERT INTO roles VALUES ('r-alm', 'Almacen'), ('r-ger', 'gerente');
        """)
        m271.run(c)
        m271.run(c)  # idempotente

        def acciones(rol):
            return {f"{m}.{a}" for m, a in c.execute(
                "SELECT modulo, accion FROM rol_permisos WHERE rol_id=?", (rol,))}

        almacen, gerente = acciones("r-alm"), acciones("r-ger")
        assert {MeatProcessingPermissions.ORDER_CREATE,
                MeatProcessingPermissions.ORDER_START,
                MeatProcessingPermissions.CONSUMPTION_CAPTURE,
                MeatProcessingPermissions.OUTPUT_CAPTURE} <= almacen
        # quien produce NO se aprueba su propia orden ni sus propias excepciones
        assert not {MeatProcessingPermissions.ORDER_APPROVE,
                    MeatProcessingPermissions.CONSUMPTION_OVERRIDE,
                    MeatProcessingPermissions.YIELD_OVERRIDE} & almacen
        assert {MeatProcessingPermissions.ORDER_APPROVE,
                MeatProcessingPermissions.CONSUMPTION_OVERRIDE,
                MeatProcessingPermissions.YIELD_OVERRIDE} <= gerente
        # Roles ausentes (admin, system_owner) se omiten: nunca se crean.
        assert c.execute("SELECT COUNT(*) FROM roles").fetchone()[0] == 2
        c.close()

    def test_271_sin_tablas_de_roles_no_revienta(self):
        c = sqlite3.connect(":memory:")
        m271.run(c)
        c.close()

    def test_270_y_271_estan_registradas(self):
        from migrations.engine import MIGRATIONS
        versiones = {m.version for m in MIGRATIONS}
        assert {"270", "271"} <= versiones
