"""Búsqueda de cliente por lo que trae el escáner.

Reemplaza `repositories/cliente_repository.py::get_by_scanner`. Un escáner de
mostrador puede leer cosas muy distintas —el id de una credencial, un teléfono,
un QR, un código de fidelidad— y el cajero no sabe cuál es cuál: se prueban
todas con el mismo texto.

El caso que de verdad importa es la columna OPCIONAL: `codigo_fidelidad` sólo
existe a partir de cierta migración. Nombrarla sin comprobar haría fallar la
consulta ENTERA en una base que no la tenga, y el escáner dejaría de encontrar
a nadie — ni por teléfono ni por QR.
"""
from __future__ import annotations

import sqlite3

import pytest

from backend.infrastructure.integrations.sales_customer_client import SalesCustomerClient

_BASE_COLUMNS = "id TEXT PRIMARY KEY, nombre TEXT, telefono TEXT, codigo_qr TEXT, activo INTEGER"


def _conn(*, with_loyalty_code: bool) -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    columnas = _BASE_COLUMNS + (", codigo_fidelidad TEXT" if with_loyalty_code else "")
    c.execute(f"CREATE TABLE clientes ({columnas})")
    return c


@pytest.fixture
def conn():
    c = _conn(with_loyalty_code=True)
    c.execute(
        "INSERT INTO clientes (id, nombre, telefono, codigo_qr, codigo_fidelidad, activo)"
        " VALUES ('7', 'Ana Ruiz', '5551234567', 'QR-ANA', 'FID-ANA', 1)")
    c.commit()
    yield c
    c.close()


def _lookup(conn, code: str):
    return SalesCustomerClient(conn).lookup_by_card(code)


@pytest.mark.parametrize("codigo", ["7", "5551234567", "QR-ANA", "FID-ANA"])
def test_the_scanner_finds_the_customer_by_any_of_its_codes(conn, codigo):
    """El cajero escanea; no elige por qué campo buscar."""
    assert _lookup(conn, codigo)["nombre"] == "Ana Ruiz"


def test_an_unknown_code_returns_nothing(conn):
    assert _lookup(conn, "NO-EXISTE") is None


def test_an_inactive_customer_is_not_found(conn):
    """Una credencial dada de baja no debe abrir una venta a su nombre."""
    conn.execute("UPDATE clientes SET activo=0 WHERE id='7'")
    conn.commit()
    assert _lookup(conn, "QR-ANA") is None


def test_the_row_comes_back_as_a_plain_dict(conn):
    """Quien llama lo pasa por el puente de identidad, no lo usa como entidad."""
    fila = _lookup(conn, "7")
    assert isinstance(fila, dict)
    assert fila["id"] == "7"


# ── la columna opcional ─────────────────────────────────────────────────────
def test_a_database_without_the_loyalty_column_still_scans():
    """Sin comprobar la columna, la consulta entera falla y el escáner deja de
    encontrar a NADIE — ni por teléfono ni por QR, no sólo por fidelidad."""
    conn = _conn(with_loyalty_code=False)
    conn.execute(
        "INSERT INTO clientes (id, nombre, telefono, codigo_qr, activo)"
        " VALUES ('9', 'Beto', '5559999999', 'QR-BETO', 1)")
    conn.commit()

    assert _lookup(conn, "QR-BETO")["nombre"] == "Beto"
    assert _lookup(conn, "5559999999")["nombre"] == "Beto"
    assert _lookup(conn, "FID-BETO") is None
    conn.close()
