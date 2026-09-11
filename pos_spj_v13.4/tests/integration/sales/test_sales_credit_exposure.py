"""Una venta a crédito suma a la exposición del cliente — y por tanto cuenta
contra su límite.

Este es el agujero que la reconstrucción dejó abierto sin que se viera: la
exposición se calculaba leyendo `cuentas_por_cobrar`, y desde que desapareció
el `CustomerCreditService` legacy nadie escribe esa tabla. Resultado: la
exposición de cualquier cliente daba cero y toda venta a crédito resultaba
elegible por mucho que el cliente ya debiera.

No lanzaba ningún error. Sólo se aprobaba de más.
"""
from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from backend.application.customer_credit.queries.customer_accounts_receivable_summary_query import (
    CustomerAccountsReceivableSummaryQuery,
)
from backend.infrastructure.db.schema.finance_schema import create_finance_schema
from backend.infrastructure.integrations.sales_credit_client import SalesCreditClient
from backend.shared.ids import new_uuid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_finance_schema(c)
    # Tabla legacy: ya nadie la escribe, pero una instalación en marcha guarda
    # ahí deuda real que sigue debiéndose.
    c.execute(
        """
        CREATE TABLE cuentas_por_cobrar (
            id TEXT PRIMARY KEY, cliente_id TEXT, saldo_pendiente REAL,
            fecha TEXT, fecha_pago TEXT, estado TEXT
        )
        """
    )
    c.commit()
    yield c
    c.close()


def _summary(conn, customer_id: str):
    return CustomerAccountsReceivableSummaryQuery(conn).get_summary(customer_id)


def _register_credit_sale(conn, *, customer_id: str, amount: str, sale_id: str | None = None):
    sale_id = sale_id or new_uuid()
    SalesCreditClient(conn, actor_user_id=new_uuid()).register(
        customer_id=customer_id, sale_id=sale_id, folio=f"F-{sale_id[:8]}",
        amount=Decimal(amount), branch_id=new_uuid())
    return sale_id


def test_a_credit_sale_increases_the_customer_exposure(conn):
    """Lo que no ocurría: sin esto el límite de crédito no se aplica."""
    customer_id = new_uuid()
    assert _summary(conn, customer_id).current_exposure == Decimal("0")

    _register_credit_sale(conn, customer_id=customer_id, amount="250.00")
    conn.commit()

    assert _summary(conn, customer_id).current_exposure == Decimal("250.00")


def test_exposure_adds_up_across_several_credit_sales(conn):
    customer_id = new_uuid()
    _register_credit_sale(conn, customer_id=customer_id, amount="100.00")
    _register_credit_sale(conn, customer_id=customer_id, amount="50.50")
    conn.commit()

    assert _summary(conn, customer_id).current_exposure == Decimal("150.50")


def test_registering_the_same_sale_twice_does_not_double_the_debt(conn):
    """Reintentar el cobro no puede cobrarle dos veces al cliente."""
    customer_id = new_uuid()
    sale_id = _register_credit_sale(conn, customer_id=customer_id, amount="80.00")
    _register_credit_sale(conn, customer_id=customer_id, amount="80.00", sale_id=sale_id)
    conn.commit()

    assert _summary(conn, customer_id).current_exposure == Decimal("80.00")


def test_historical_legacy_debt_still_counts(conn):
    """Dejar de leer la tabla legacy pondría a cero a quien ya debe.

    Esa deuda es real: son saldos que el cliente sigue debiendo aunque el
    servicio que los escribía ya no exista.
    """
    customer_id = new_uuid()
    conn.execute(
        "INSERT INTO cuentas_por_cobrar (id, cliente_id, saldo_pendiente, fecha, estado)"
        " VALUES (?,?,?,?,?)",
        (new_uuid(), customer_id, 300.0, date.today().isoformat(), "pendiente"))
    conn.commit()

    assert _summary(conn, customer_id).current_exposure == Decimal("300")


def test_legacy_and_canonical_debt_add_up(conn):
    customer_id = new_uuid()
    conn.execute(
        "INSERT INTO cuentas_por_cobrar (id, cliente_id, saldo_pendiente, fecha, estado)"
        " VALUES (?,?,?,?,?)",
        (new_uuid(), customer_id, 300.0, date.today().isoformat(), "pendiente"))
    _register_credit_sale(conn, customer_id=customer_id, amount="200.00")
    conn.commit()

    assert _summary(conn, customer_id).current_exposure == Decimal("500")


def test_settled_debt_stops_counting(conn):
    """Una cuenta liquidada ya no consume límite."""
    customer_id = new_uuid()
    _register_credit_sale(conn, customer_id=customer_id, amount="120.00")
    conn.execute("UPDATE receivables SET status='SETTLED' WHERE customer_id=?", (customer_id,))
    conn.commit()

    assert _summary(conn, customer_id).current_exposure == Decimal("0")


def test_a_partially_collected_debt_counts_only_what_is_left(conn):
    customer_id = new_uuid()
    _register_credit_sale(conn, customer_id=customer_id, amount="120.00")
    conn.execute(
        "UPDATE receivables SET status='PARTIALLY_COLLECTED', outstanding_amount='45.00'"
        " WHERE customer_id=?", (customer_id,))
    conn.commit()

    assert _summary(conn, customer_id).current_exposure == Decimal("45.00")


def test_another_customers_debt_is_not_counted(conn):
    mine, other = new_uuid(), new_uuid()
    _register_credit_sale(conn, customer_id=other, amount="900.00")
    conn.commit()

    assert _summary(conn, mine).current_exposure == Decimal("0")


def test_the_summary_survives_a_database_without_the_legacy_table(conn):
    """Una instalación nueva no tiene `cuentas_por_cobrar`; no debe reventar."""
    conn.execute("DROP TABLE cuentas_por_cobrar")
    customer_id = new_uuid()
    _register_credit_sale(conn, customer_id=customer_id, amount="70.00")
    conn.commit()

    assert _summary(conn, customer_id).current_exposure == Decimal("70.00")
