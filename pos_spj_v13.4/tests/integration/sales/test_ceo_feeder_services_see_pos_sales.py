"""Los cinco servicios que alimentan el dashboard CEO leen la fuente unificada.

`CEODashboard` recibe inyectados `decision_engine`, `alert_engine`,
`actionable_forecast` y `financial_simulator`; `franchise_manager` sirve la
comparativa entre sucursales. Los cinco consultan ventas, y mientras leyeran
`ventas`/`detalles_venta` no veían NADA de lo cobrado en el POS.

Son 33 consultas repartidas en literales que ya interpolan otras piezas, así
que se resuelven con el mismo reescritor que `AnalyticsEngine`: un marcador sin
llaves y una envoltura de conexión que lo sustituye en un único punto. Lo que
se prueba aquí no es cada consulta una por una —eso sería fijar SQL— sino las
dos cosas que pueden romperse en silencio: que el marcador NO llegue nunca al
SQL ejecutado, y que la fuente resuelta sea la vista cuando existe.
"""
from __future__ import annotations

import ast
import importlib
import sqlite3
from pathlib import Path

import pytest

from backend.infrastructure.db.sales_read_source import (
    SALE_LINES_PLACEHOLDER,
    SALES_PLACEHOLDER,
)

ROOT = Path(__file__).resolve().parents[3]

SERVICIOS = (
    ("core.services.decision_engine", "DecisionEngine"),
    ("core.services.alert_engine", "AlertEngine"),
    ("core.services.actionable_forecast", "ActionableForecastService"),
    ("core.services.financial_simulator", "FinancialSimulator"),
    ("core.services.franchise_manager", "FranchiseManager"),
)

ARCHIVOS = tuple(f"core/services/{m.rsplit('.', 1)[1]}.py" for m, _ in SERVICIOS)


class _Spy:
    """`sqlite3.Connection.execute` es de sólo lectura: se envuelve, no se
    parchea."""

    def __init__(self, inner, registro):
        self._inner = inner
        self._registro = registro

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def execute(self, sql, *args, **kwargs):
        if isinstance(sql, str):
            self._registro.append(sql)
        return self._inner.execute(sql, *args, **kwargs)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(
        """
        CREATE TABLE usuarios (id TEXT PRIMARY KEY, nombre TEXT, usuario TEXT,
                               password_hash TEXT);
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
    create_sales_schema(c)
    for mod in ("256_sales_unified_read_view", "257_sale_lines_unified_read_view"):
        importlib.import_module(f"migrations.standalone.{mod}").run(c)
    c.commit()
    yield c
    c.close()


def _instancia(module_name, class_name, connection):
    return getattr(importlib.import_module(module_name), class_name)(connection)


@pytest.mark.parametrize("module_name, class_name", SERVICIOS)
def test_resolves_to_the_unified_view_when_it_exists(conn, module_name, class_name):
    servicio = _instancia(module_name, class_name, conn)
    assert servicio.db._rewrite(
        f"SELECT 1 FROM {SALES_PLACEHOLDER} v JOIN {SALE_LINES_PLACEHOLDER} dv"
    ) == "SELECT 1 FROM v_ventas_unificada v JOIN v_detalles_venta_unificada dv"


@pytest.mark.parametrize("module_name, class_name", SERVICIOS)
def test_falls_back_to_legacy_without_the_views(conn, module_name, class_name):
    conn.execute("DROP VIEW v_ventas_unificada")
    conn.execute("DROP VIEW v_detalles_venta_unificada")
    servicio = _instancia(module_name, class_name, conn)
    assert servicio.db._rewrite(
        f"SELECT 1 FROM {SALES_PLACEHOLDER}") == "SELECT 1 FROM ventas"


@pytest.mark.parametrize("module_name, class_name", SERVICIOS)
def test_no_marker_reaches_the_executed_sql(conn, module_name, class_name):
    """Un marcador sin resolver produce SQL inválido, y estos servicios tragan
    sus excepciones: la pantalla mostraría cero sin avisar."""
    ejecutado: list[str] = []
    servicio = _instancia(module_name, class_name, _Spy(conn, ejecutado))

    for nombre in dir(servicio):
        if nombre.startswith("_"):
            continue
        metodo = getattr(servicio, nombre)
        if not callable(metodo):
            continue
        try:
            metodo()
        except Exception:
            continue  # firma con argumentos: no es lo que se mide aquí

    filtrados = [s for s in ejecutado
                 if SALES_PLACEHOLDER in s or SALE_LINES_PLACEHOLDER in s]
    assert not filtrados, filtrados


def test_no_service_names_the_legacy_table_directly():
    """Guardrail sobre el AST: los comentarios citan la tabla legacy al
    explicar el cambio, y un `in source` los daría por vivos."""
    offenders = []
    for relative in ARCHIVOS:
        tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            for legacy in ("FROM ventas", "JOIN ventas",
                           "FROM detalles_venta", "JOIN detalles_venta"):
                if legacy in node.value:
                    offenders.append(f"{relative}:{node.lineno} -> {legacy}")
    assert not offenders, "\n".join(offenders)


def test_no_marker_was_written_with_braces():
    """Con llaves colisiona con los f-strings y `.format()` que estas mismas
    consultas ya usan — el error que costó un KeyError real en el motor de BI."""
    for relative in ARCHIVOS:
        source = (ROOT / relative).read_text(encoding="utf-8")
        for braced in ("{_SRC_H}", "{_SRC_L}", "{{_SRC_H}}", "{{_SRC_L}}"):
            assert braced not in source, f"{relative}: marcador con llaves"
