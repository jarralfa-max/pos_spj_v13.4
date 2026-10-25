"""Migración 345 (contrato born-clean de Finanzas), corregida en la auditoría
enterprise N05: nunca pide borrar la base.

Regla del usuario que se conserva: el esquema financiero no se CONVIERTE ni se
rescatan datos. Lo vacío se recrea con el DDL canónico; lo que tiene datos
detiene la migración sin tocar nada.
"""

from __future__ import annotations

import importlib
import sqlite3

import pytest

from backend.domain.finance.exceptions import FinanceSchemaContractError
from backend.infrastructure.db.schema.finance_schema import (
    create_finance_schema,
    finance_schema_differences,
)

_345 = importlib.import_module("migrations.standalone.345_finance_born_clean_contract")


def _base(*, tabla_vieja: bool = False, con_datos: bool = False):
    c = sqlite3.connect(":memory:")
    create_finance_schema(c)
    if tabla_vieja:
        # `budgets` con el contrato anterior: le faltan columnas del vigente.
        c.execute("DROP TABLE budgets")
        c.execute("CREATE TABLE budgets (id TEXT NOT NULL PRIMARY KEY, name TEXT,"
                  " fiscal_year INTEGER)")
        if con_datos:
            c.execute("INSERT INTO budgets VALUES ('01a00000-0000-7000-8000-000000000001',"
                      " 'Presupuesto 2026', 2026)")
    c.commit()
    return c


def test_a_conforming_schema_is_left_alone():
    c = _base()
    _345.run(c)
    assert finance_schema_differences(c) == {}


def test_an_empty_table_from_an_older_contract_is_recreated():
    c = _base(tabla_vieja=True)
    assert "budgets" in finance_schema_differences(c)
    _345.run(c)
    assert finance_schema_differences(c) == {}


def test_absent_tables_are_created():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE configuraciones (clave TEXT PRIMARY KEY, valor TEXT)")
    _345.run(c)
    assert finance_schema_differences(c) == {}


def test_an_older_table_with_data_stops_without_touching_anything():
    c = _base(tabla_vieja=True, con_datos=True)
    with pytest.raises(FinanceSchemaContractError) as error:
        _345.run(c)
    mensaje = str(error.value)
    assert "budgets (1 filas)" in mensaje and "No se modificó nada" in mensaje
    # Nunca más: «elimine data/spj_pos_database.db».
    assert "elimine" not in mensaje.lower() and ".db" not in mensaje
    assert c.execute("SELECT name FROM budgets").fetchone()[0] == "Presupuesto 2026"
    assert [r[1] for r in c.execute("PRAGMA table_info(budgets)")] == [
        "id", "name", "fiscal_year"]
