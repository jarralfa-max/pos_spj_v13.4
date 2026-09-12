"""Alta rápida de cliente con tarjeta de fidelidad.

DOS FALLOS QUE VIVÍAN AQUÍ, Y NINGUNA PRUEBA LOS CUBRÍA
--------------------------------------------------------
`CreateCustomerUseCase` escribía en `tarjetas_fidelidad` nombrando columnas que
NO EXISTEN (`codigo`, `fecha_emision`; las reales son `codigo_qr` y
`fecha_creacion`) y omitiendo `id`, que es la clave primaria TEXT de la tabla.

Lo grave no era perder la tarjeta. El caso de uso envuelve todo en un `except`
que hace `rollback()` y vuelve a lanzar, así que **dar un código de fidelidad
perdía la creación entera del cliente** — y el error que llegaba arriba hablaba
de una columna, no de una tarjeta.

El segundo fallo era mudo del todo: `find_customer_by_loyalty_code` consultaba
`t.codigo` y su `except` devuelve `None`. Escanear una tarjeta no encontraba
nunca al cliente, y eso se lee exactamente igual que "tarjeta no registrada".

Los encontró una guardia de arquitectura al exigir que ningún INSERT omita el
`id` — no una prueba de clientes, porque no había ninguna.
"""
from __future__ import annotations

import sqlite3

import pytest

from backend.application.use_cases.create_customer_use_case import (
    CreateCustomerCommand,
    CreateCustomerUseCase,
)
from backend.shared.ids import is_uuidv7


@pytest.fixture
def conn():
    import migrations.m000_base_schema as base
    from migrations import engine as migrator

    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    base.up(c)
    c.commit()
    migrator.up(c)
    c.commit()
    yield c
    c.close()


def _crear(conn, **kwargs):
    return CreateCustomerUseCase(conn).execute(CreateCustomerCommand(**kwargs))


# ── el fallo caro ───────────────────────────────────────────────────────────
def test_a_customer_with_a_loyalty_code_is_actually_created(conn):
    """Era el caso que se perdía entero por el rollback."""
    resultado = _crear(conn, name="Ana Ruiz", phone="5551234567", loyalty_code="FID-ANA")

    assert resultado["ok"] is True
    fila = conn.execute("SELECT nombre FROM clientes WHERE id=?",
                        (resultado["id"],)).fetchone()
    assert fila is not None, "el cliente no llegó a guardarse"
    assert fila["nombre"] == "Ana Ruiz"


def test_the_loyalty_card_is_written_with_its_own_uuid(conn):
    """La tarjeta tiene clave primaria TEXT: sin `id` la fila nace sin
    identidad, y eso sólo se nota al relacionarla."""
    resultado = _crear(conn, name="Ana Ruiz", loyalty_code="FID-ANA")

    tarjeta = conn.execute(
        "SELECT id, codigo_qr, id_cliente, nivel, activa FROM tarjetas_fidelidad "
        "WHERE id_cliente=?", (resultado["id"],)).fetchone()
    assert tarjeta is not None, "no se creó la tarjeta"
    assert is_uuidv7(tarjeta["id"])
    assert tarjeta["codigo_qr"] == "FID-ANA"
    assert tarjeta["nivel"] == "Bronce"
    assert tarjeta["activa"] == 1


def test_a_customer_without_a_loyalty_code_gets_no_card(conn):
    """Sin código no hay tarjeta: crear una vacía dejaría credenciales
    fantasma que el escáner encontraría."""
    resultado = _crear(conn, name="Beto Lara")
    assert conn.execute("SELECT COUNT(*) FROM tarjetas_fidelidad WHERE id_cliente=?",
                        (resultado["id"],)).fetchone()[0] == 0


# ── el fallo mudo ───────────────────────────────────────────────────────────
def test_scanning_the_card_finds_the_customer(conn):
    """Devolvía `None` siempre, y eso se lee igual que "tarjeta no registrada":
    el cajero la daría por no existente y crearía un cliente duplicado."""
    caso = CreateCustomerUseCase(conn)
    creado = caso.execute(CreateCustomerCommand(name="Ana Ruiz", loyalty_code="FID-ANA"))

    encontrado = caso.find_customer_by_loyalty_code("FID-ANA")
    assert encontrado is not None, "la búsqueda por tarjeta no encontró al cliente"
    assert encontrado["id"] == creado["id"]
    assert encontrado["name"] == "Ana Ruiz"


def test_an_unknown_card_finds_nothing(conn):
    assert CreateCustomerUseCase(conn).find_customer_by_loyalty_code("NO-EXISTE") is None


def test_an_inactive_card_finds_nothing(conn):
    """Una credencial dada de baja no puede abrir una venta a su nombre."""
    caso = CreateCustomerUseCase(conn)
    caso.execute(CreateCustomerCommand(name="Ana Ruiz", loyalty_code="FID-ANA"))
    conn.execute("UPDATE tarjetas_fidelidad SET activa=0 WHERE codigo_qr='FID-ANA'")
    conn.commit()

    assert caso.find_customer_by_loyalty_code("FID-ANA") is None


# ── idempotencia ────────────────────────────────────────────────────────────
def test_reusing_a_card_code_does_not_duplicate_the_card(conn):
    """El INSERT es `OR IGNORE`: reintentar el alta no puede dejar dos tarjetas
    con el mismo código, porque la búsqueda devolvería una cualquiera."""
    caso = CreateCustomerUseCase(conn)
    caso.execute(CreateCustomerCommand(name="Ana Ruiz", loyalty_code="FID-ANA"))
    caso.execute(CreateCustomerCommand(name="Ana Ruiz Duplicada", loyalty_code="FID-ANA"))

    assert conn.execute(
        "SELECT COUNT(*) FROM tarjetas_fidelidad WHERE codigo_qr='FID-ANA'"
    ).fetchone()[0] == 1
