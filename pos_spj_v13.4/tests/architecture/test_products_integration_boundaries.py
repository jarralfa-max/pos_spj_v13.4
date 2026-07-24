"""PROD-17 guardrails (§30, §37) — Products no lee balances ni fija precio.

Los QueryServices de integración exponen configuración del maestro por product_id,
pero Productos nunca consulta tablas de existencia/balance de Inventario ni devuelve
un precio final (eso es Pricing). El escaneo usa AST para inspeccionar sólo el SQL
(literales con SELECT/FROM) y los nombres de campo de los DTOs — no la prosa de los
docstrings.
"""

import ast
import pathlib

BASE = pathlib.Path(__file__).resolve().parents[1].parent
QUERIES = BASE / "backend/application/products/queries"
INTEG = QUERIES / "integration_query_services.py"
DTOS = QUERIES / "integration_dtos.py"

_BALANCE_TABLES = ("inventory_balances", "inventory_ledger", "inventario_actual",
                   "inventory_stock", "stock_reservas")
_PRICE_COLUMNS = ("unit_price", "sale_price", "list_price", "precio_venta", "precio_local")
_FORBIDDEN_FIELDS = ("price", "precio", "existencia", "on_hand", "balance",
                     "stock_qty", "available_qty")


def _sql_literals(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            low = node.value.lower()
            if "select" in low or "from " in low or "update " in low:
                out.append(low)
    return out


def _dataclass_field_names(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    names.append(stmt.target.id.lower())
    return names


def test_integration_queries_do_not_read_inventory_balances():
    for sql in _sql_literals(INTEG):
        for table in _BALANCE_TABLES:
            assert table not in sql, f"SQL de Productos lee balance de inventario: {table}"


def test_integration_queries_do_not_select_price():
    for sql in _sql_literals(INTEG):
        for col in _PRICE_COLUMNS:
            assert col not in sql, f"SQL de Productos selecciona precio: {col}"


def test_dtos_have_no_price_or_stock_fields():
    for name in _dataclass_field_names(DTOS):
        for token in _FORBIDDEN_FIELDS:
            assert token not in name, f"Campo de DTO prohibido: {name}"
