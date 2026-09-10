"""`AnalyticsEngine` — el motor que sirve la pantalla VIVA de Inteligencia de
Negocios (`modulos/reportes_bi_v2.py`, slot INTELIGENCIA_BI de `MainWindow`).

Sus 21 consultas leían `ventas`/`detalles_venta`, así que el BI que el usuario
abre no mostraba NINGUNA venta del POS: desde SALES-19..22 nacen en el agregado
canónico `sales` y no pasan por la tabla legacy. Este es el lector de mayor
impacto de todo el tramo 1, porque es el único de la lista que un usuario ve.

El fixture contiene UNA venta y es canónica: cualquier consulta que siguiera en
la tabla legacy devuelve cero.
"""
from __future__ import annotations

import importlib
import sqlite3

import pytest

from backend.infrastructure.db.sales_read_source import (
    SALE_LINES_PLACEHOLDER,
    SALES_PLACEHOLDER,
    SalesSourceRewritingConnection,
)
from core.services.analytics.analytics_engine import AnalyticsEngine

FECHA = "2026-06-01"


def _schema(conn):
    conn.executescript(
        """
        CREATE TABLE usuarios (id TEXT PRIMARY KEY, nombre TEXT, usuario TEXT,
                               password_hash TEXT);
        INSERT INTO usuarios VALUES ('u-1','Ana','cajera1','x');
        CREATE TABLE sucursales (id TEXT PRIMARY KEY, nombre TEXT, activa INTEGER
                                 DEFAULT 1);
        INSERT INTO sucursales VALUES ('b1','Matriz',1);
        CREATE TABLE productos (id TEXT PRIMARY KEY, nombre TEXT, categoria TEXT,
                                costo REAL, precio_compra REAL, costo_promedio REAL);
        INSERT INTO productos VALUES ('p-1','Pollo','Aves',40.0,40.0,40.0);
        CREATE TABLE clientes (id TEXT PRIMARY KEY, nombre TEXT);
        INSERT INTO clientes VALUES ('c-1','Cliente Uno');
        CREATE TABLE ventas (
            id TEXT PRIMARY KEY, folio TEXT, sucursal_id TEXT, usuario TEXT,
            cliente_id TEXT, subtotal REAL, descuento REAL, total REAL,
            forma_pago TEXT, estado TEXT, fecha DATETIME);
        CREATE TABLE detalles_venta (
            id TEXT PRIMARY KEY, venta_id TEXT, producto_id TEXT, cantidad REAL,
            precio_unitario REAL, descuento REAL, subtotal REAL, unidad TEXT,
            comentarios TEXT, batch_id TEXT, costo_unitario_real REAL,
            margen_real REAL, nombre TEXT);
        """
    )
    from backend.infrastructure.db.schema.sales_schema import create_sales_schema
    create_sales_schema(conn)
    for mod in ("256_sales_unified_read_view", "257_sale_lines_unified_read_view"):
        importlib.import_module(f"migrations.standalone.{mod}").run(conn)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    _schema(c)
    stamp = f"{FECHA} 12:00:00"
    c.execute(
        "INSERT INTO sales (id,branch_id,cashier_user_id,operation_id,status,"
        "sale_number,customer_id,channel,currency_code,gross_subtotal,"
        "discount_total,promotion_total,coupon_total,loyalty_total,tax_total,"
        "rounding_adjustment,total,sale_level_discount,loyalty_redeemed_amount,"
        "version,created_at) VALUES ('s-pos','b1','u-1','op-1','COMPLETED',"
        "'F-1','c-1','POS','MXN','200.0','0','0','0','0','0','0','200.0','0',"
        "'0',1,?)", (stamp,))
    c.execute(
        "INSERT INTO sale_lines (id,sale_id,product_id,product_snapshot,quantity,"
        "quantity_unit,unit_price,discount_total,tax_total,created_at,updated_at)"
        " VALUES ('l-1','s-pos','p-1','{\"name\":\"Pollo\"}','2.0','kg','100.0',"
        "'0','0',?,?)", (stamp, stamp))
    c.commit()
    yield c
    c.close()



def test_no_placeholder_survives_into_executed_sql(conn):
    """Si un marcador llegara sin resolver, SQLite fallaría con un error de
    sintaxis y el motor lo tragaría devolviendo vacío. Se comprueba el texto
    que realmente se ejecuta."""
    executed: list[str] = []

    class _Spy:
        """`sqlite3.Connection.execute` es de sólo lectura, así que el espía
        envuelve la conexión en vez de parchearla."""

        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def execute(self, sql, *args, **kwargs):
            executed.append(sql)
            return self._inner.execute(sql, *args, **kwargs)

    engine = AnalyticsEngine(_Spy(conn))
    engine.product_profitability(FECHA, FECHA, "b1")
    engine.inventory_intelligence(sucursal_id="b1")

    assert executed, "no se ejecutó ninguna consulta"
    leaked = [s for s in executed
              if SALES_PLACEHOLDER in s or SALE_LINES_PLACEHOLDER in s]
    assert not leaked, leaked
    assert any("v_ventas_unificada" in s for s in executed)


def test_the_wrapper_only_rewrites_and_delegates_everything_else(conn):
    wrapper = SalesSourceRewritingConnection(conn)
    assert wrapper.row_factory is conn.row_factory
    assert callable(wrapper.commit)
    # Una consulta sin marcadores pasa intacta.
    assert wrapper._rewrite("SELECT 1 FROM productos") == "SELECT 1 FROM productos"
    assert wrapper._rewrite(None) is None


def test_no_marker_is_written_with_braces():
    """Guardrail del error que YO introduje al marcar las 21 consultas.

    El primer marcador fue `{_SRC_H}`, con llaves, y eso colisiona por DOS
    vías con las consultas de este motor, que ya interpolan otras piezas:

      * dentro de un f-string, `{_SRC_H}` no es texto sino la interpolación
        del nombre `_SRC_H` -> NameError;
      * dentro de un `.format()`, es un campo desconocido -> KeyError
        (ocurrió de verdad en `product_profitability`).

    Ambos quedaban tapados por el `except` del motor: la pantalla mostraba
    cero en silencio. El marcador actual no lleva llaves, y esta prueba impide
    que alguien las reintroduzca "por claridad".
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    source = (root / "core/services/analytics/analytics_engine.py").read_text(
        encoding="utf-8")
    for braced in ("{_SRC_H}", "{_SRC_L}", "{{_SRC_H}}", "{{_SRC_L}}"):
        assert braced not in source, (
            f"marcador con llaves ({braced}): colisiona con f-string/.format()")
    assert SALES_PLACEHOLDER in source and SALE_LINES_PLACEHOLDER in source


def test_every_sales_query_carries_a_resolvable_marker():
    """Ninguna consulta de ventas puede haber quedado apuntando a la tabla
    legacy por nombre fijo: o usa el marcador, o el corte se revierte solo."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    source = (root / "core/services/analytics/analytics_engine.py").read_text(
        encoding="utf-8")
    for legacy in ("FROM ventas", "JOIN ventas",
                   "FROM detalles_venta", "JOIN detalles_venta"):
        assert legacy not in source, f"volvió a nombrar la tabla legacy: {legacy}"


def test_the_engine_has_no_unreachable_query_methods():
    """§27: al medir la superficie real del motor aparecieron 8 métodos de 19
    sin ningún llamador. Cinco no los usaba NADIE (ni una prueba) y se
    eliminaron; los otros tres sólo los ejercitan pruebas y quedan anotados.

    Esta prueba impide que la superficie muerta vuelva a crecer: cualquier
    método público nuevo debe tener llamador, o entrar en la lista de los
    conocidos con su razón.
    """
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    engine_path = root / "core/services/analytics/analytics_engine.py"
    tree = ast.parse(engine_path.read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    public = {n.name for n in cls.body
              if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")}

    # Llamados desde fuera (`reportes_bi_v2`, `app_container`, `wiring`).
    live_entrypoints = {"wire"}
    # Alcanzables desde `wire()` o desde `get_dashboard_data()`.
    reachable_internally = {"update_sales", "update_yield"}
    # Sin llamador en producción; sólo pruebas los ejercitan. Se conservan
    # porque borrarlos exige borrar también esas pruebas, que cubren el corte
    # canónico de inventario y el respaldo de costo.
    test_only = {"product_profitability", "inventory_intelligence", "invalidar_cache"}

    # `get_ranking_cajeros` y `product_profitability_detail` YA NO están:
    # su consulta se movió a `BiSalesQueryService.cashier_ranking` /
    # `.profitability_by_product` y la pantalla llama allí.
    for movido in ("get_ranking_cajeros", "product_profitability_detail",
                   "get_dashboard_data", "get_ventas_por_hora",
                   "get_ranking_productos", "get_clientes_recurrentes"):
        assert movido not in public, f"{movido} debía haberse movido al backend"

    unaccounted = public - live_entrypoints - reachable_internally - test_only
    assert not unaccounted, (
        "métodos públicos sin llamador conocido — o se cablean, o se borran, o "
        f"se documentan aquí: {sorted(unaccounted)}")


def test_the_remaining_projections_write_tables_nobody_reads():
    """Lo que le queda al motor son DOS CALLEJONES SIN SALIDA. Medido, no supuesto.

    `wire()` suscribe `update_sales` a SALE_CREATED y `update_yield` a
    PRODUCTION_EXECUTED, que escriben `bi_sales_daily` y `bi_transformations`.
    Hoy:

      * NINGÚN archivo productivo LEE esas dos tablas. Su último lector era el
        atajo de `get_dashboard_data`, que desapareció al mover el tablero a
        `BiDashboardQueryService.operational_dashboard`;
      * `SALE_CREATED` es alias de `VENTA_COMPLETADA`, y el ÚNICO que la
        publica es `core/services/sales_service.py` — el servicio legacy que
        sirve la API REST. El POS canónico emite `SALE_COMPLETED` a
        `sales_outbox`, otro canal. Es decir, `bi_sales_daily` nunca contuvo
        ventas del POS, y el atajo que la leía devolvía KPIs incompletos.

    Por eso NO se construyó un equivalente canónico de estas proyecciones:
    sería backend nuevo sin consumidor (§27). Esta prueba deja la medición
    escrita para que la próxima sesión no lo reconstruya por error, y falla si
    alguien le da un lector — momento en que habrá que decidir de verdad si la
    proyección debe existir y sobre qué evento.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    productivos = ("api", "backend", "core", "frontend", "infrastructure",
                   "integrations", "interfaz", "modulos", "repositories", "sync")
    lectores = []
    for carpeta in productivos:
        base = root / carpeta
        if not base.is_dir():
            continue
        for archivo in base.rglob("*.py"):
            if "__pycache__" in archivo.parts:
                continue
            texto = archivo.read_text(encoding="utf-8", errors="ignore")
            for tabla in ("bi_sales_daily", "bi_transformations"):
                if f"FROM {tabla}" in texto or f"JOIN {tabla}" in texto:
                    lectores.append(f"{archivo.relative_to(root).as_posix()} -> {tabla}")
    assert not lectores, (
        "alguien volvió a leer una tabla de proyección BI; revisa si la "
        f"proyección debe existir y sobre qué evento:\n  " + "\n  ".join(lectores))
