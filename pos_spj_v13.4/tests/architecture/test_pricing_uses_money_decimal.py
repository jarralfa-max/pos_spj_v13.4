"""PRC-9 audit — Pricing/Costing es Money/Decimal-only (sin float, sin REAL).

- El esquema `pricing_schema` no declara ninguna columna REAL (los montos son TEXT
  Decimal + `*_currency`); se verifica creando el schema y leyendo PRAGMA.
- El VO `Money` rechaza float en construcción y aritmética.
- El código de dominio/aplicación/repositorio de pricing no usa `float(` sobre
  montos (heurística AST: sin llamadas `float(...)` en esas capas).
"""

from __future__ import annotations

import ast
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from backend.domain.pricing.exceptions import InvalidMoneyError
from backend.domain.pricing.value_objects.money import Money
from backend.infrastructure.db.schema.pricing_schema import (
    PRICING_TABLES,
    create_pricing_schema,
)

_ROOT = Path(__file__).resolve().parents[2]
_SCAN_DIRS = (
    _ROOT / "backend" / "domain" / "pricing",
    _ROOT / "backend" / "application" / "pricing",
    _ROOT / "backend" / "infrastructure" / "db" / "repositories" / "pricing",
)


def test_pricing_schema_has_no_real_columns():
    conn = sqlite3.connect(":memory:")
    create_pricing_schema(conn)
    offenders = []
    for table in PRICING_TABLES:
        for r in conn.execute(f"PRAGMA table_info({table})").fetchall():
            if str(r[2]).upper() == "REAL":
                offenders.append(f"{table}.{r[1]}")
    conn.close()
    assert not offenders, f"Columnas REAL en pricing (usa TEXT Decimal): {offenders}"


def test_money_rejects_float():
    with pytest.raises(InvalidMoneyError):
        Money(3.5)
    with pytest.raises(InvalidMoneyError):
        Money(Decimal("10")).multiply(1.5)


def test_pricing_code_has_no_float_casts():
    offenders = []
    for base in _SCAN_DIRS:
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == "float"):
                    offenders.append(f"{path.relative_to(_ROOT)}:{node.lineno}")
    assert not offenders, f"float() en el contexto Pricing (usa Decimal/Money): {offenders}"
