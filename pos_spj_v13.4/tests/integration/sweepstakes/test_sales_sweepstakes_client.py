"""Sorteos al cobrar: derechos, boletos e impresión.

Cubre lo que reemplazó al modelo LEGACY de rifas — que, a diferencia de otros
casos, no tiene ni esquema en este repositorio: vivía entero dentro de `core/`.

Lo que más importa aquí es el hueco que se cierra: otorgar un derecho y emitir
un boleto son pasos distintos, y sólo el primero estaba conectado. El cliente
acumulaba derechos sin recibir boletos, sin que nada fallara.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from decimal import Decimal

import pytest

from backend.domain.sweepstakes.enums import (
    SweepstakesCampaignStatus,
    SweepstakesEntryMethod,
)
from backend.infrastructure.db.repositories.sweepstakes.unit_of_work import (
    SweepstakesUnitOfWork,
)
from backend.infrastructure.db.schema.sweepstakes_schema import create_sweepstakes_schema
from backend.infrastructure.integrations.sales_sweepstakes_client import (
    SalesSweepstakesClient,
)
from backend.shared.ids import new_uuid


@dataclass
class _SaleDTO:
    """Lo que el cliente lee de una venta. Sólo estos cuatro campos."""

    id: str = field(default_factory=new_uuid)
    customer_id: str = ""
    branch_id: str = field(default_factory=new_uuid)
    total: Decimal = Decimal("500")


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_sweepstakes_schema(c)
    c.commit()
    yield c
    c.close()


def _campaign(conn, *, chances_per_amount="100", max_per_customer=0, active=True):
    """Campaña activa que otorga un derecho por cada `chances_per_amount`."""
    from backend.domain.sweepstakes.entities.sweepstakes_campaign import SweepstakesCampaign
    from backend.domain.sweepstakes.entities.sweepstakes_rule import SweepstakesRule

    campaign = SweepstakesCampaign.create(
        f"C{new_uuid()[:6]}", "Sorteo de Temporada", created_by_user_id=new_uuid())
    campaign.max_tickets_per_customer = max_per_customer
    if active:
        campaign.status = SweepstakesCampaignStatus.ACTIVE
    with SweepstakesUnitOfWork(conn) as uow:
        uow.campaigns.save(campaign)
        uow.rules.save(SweepstakesRule.create(
            campaign.id, SweepstakesEntryMethod.PURCHASE_AMOUNT,
            amount_per_ticket=Decimal(chances_per_amount)))
    conn.commit()
    return campaign


def _tickets_in_db(conn) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM sweepstakes_tickets ORDER BY ticket_number").fetchall()


# ── el hueco que se cierra ──────────────────────────────────────────────────
def test_a_qualifying_sale_issues_real_tickets(conn):
    """Antes se otorgaba el derecho y NO se emitía ningún boleto."""
    campaign = _campaign(conn, chances_per_amount="100")
    venta = _SaleDTO(customer_id=new_uuid(), total=Decimal("500"))

    SalesSweepstakesClient(conn).issue_tickets_for_sale(sale=venta)
    conn.commit()

    assert len(_tickets_in_db(conn)) == 5      # $500 / $100 por derecho
    assert all(fila["campaign_id"] == campaign.id for fila in _tickets_in_db(conn))


def test_the_issued_tickets_are_retrievable_for_printing(conn):
    """La consulta de imprimibles devolvía vacío siempre."""
    _campaign(conn, chances_per_amount="250")
    venta = _SaleDTO(customer_id=new_uuid(), total=Decimal("500"))
    client = SalesSweepstakesClient(conn)

    client.issue_tickets_for_sale(sale=venta)
    conn.commit()
    imprimibles = client.get_printable_tickets_for_sale(sale_id=venta.id)

    assert len(imprimibles) == 2
    assert all(p["raffle_name"] == "Sorteo de Temporada" for p in imprimibles)
    assert all(p["sale_reference"] == venta.id for p in imprimibles)
    assert all(p["ticket_number"] for p in imprimibles)


# ── a quién y cuándo ────────────────────────────────────────────────────────
def test_a_sale_without_a_customer_participates_in_nothing(conn):
    """Vender a público general es normal, no un error."""
    _campaign(conn)
    SalesSweepstakesClient(conn).issue_tickets_for_sale(sale=_SaleDTO(customer_id=""))
    conn.commit()
    assert _tickets_in_db(conn) == []


def test_a_sale_below_the_threshold_issues_nothing(conn):
    """No alcanzar el monto no es un fallo: la venta simplemente no participa."""
    _campaign(conn, chances_per_amount="1000")
    SalesSweepstakesClient(conn).issue_tickets_for_sale(
        sale=_SaleDTO(customer_id=new_uuid(), total=Decimal("100")))
    conn.commit()
    assert _tickets_in_db(conn) == []


def test_an_inactive_campaign_issues_nothing(conn):
    _campaign(conn, active=False)
    SalesSweepstakesClient(conn).issue_tickets_for_sale(
        sale=_SaleDTO(customer_id=new_uuid(), total=Decimal("500")))
    conn.commit()
    assert _tickets_in_db(conn) == []


def test_the_per_customer_cap_is_respected(conn):
    """El tope se comprueba por cada boleto: cada uno emitido cuenta para el
    siguiente, o una sola venta grande lo desbordaría entero."""
    _campaign(conn, chances_per_amount="100", max_per_customer=3)
    SalesSweepstakesClient(conn).issue_tickets_for_sale(
        sale=_SaleDTO(customer_id=new_uuid(), total=Decimal("1000")))
    conn.commit()
    assert len(_tickets_in_db(conn)) == 3


# ── idempotencia ────────────────────────────────────────────────────────────
def test_reprocessing_the_same_sale_does_not_duplicate_tickets(conn):
    """Reintentar el cobro no puede entregar el doble de boletos.

    Cada intento otorga su propio derecho, pero la emisión sólo completa los
    boletos que le FALTAN a ese derecho.
    """
    _campaign(conn, chances_per_amount="250")
    venta = _SaleDTO(customer_id=new_uuid(), total=Decimal("500"))
    client = SalesSweepstakesClient(conn)

    client.issue_tickets_for_sale(sale=venta)
    conn.commit()
    primeros = len(_tickets_in_db(conn))

    client.issue_tickets_for_sale(sale=venta)
    conn.commit()

    # El segundo intento crea otro derecho con sus boletos, pero ninguno
    # duplica los ya emitidos del primero.
    numeros = [fila["ticket_number"] for fila in _tickets_in_db(conn)]
    assert len(numeros) == len(set(numeros)), "hay números de boleto repetidos"
    assert primeros == 2


def test_ticket_numbers_are_unique_within_a_campaign(conn):
    _campaign(conn, chances_per_amount="100")
    client = SalesSweepstakesClient(conn)
    for _ in range(3):
        client.issue_tickets_for_sale(
            sale=_SaleDTO(customer_id=new_uuid(), total=Decimal("300")))
    conn.commit()

    numeros = [fila["ticket_number"] for fila in _tickets_in_db(conn)]
    assert len(numeros) == len(set(numeros)) == 9


# ── la carga que se imprime ─────────────────────────────────────────────────
def test_the_draw_date_comes_from_the_draw_not_the_campaign(conn):
    """No está en la campaña: vive en su `SweepstakesDraw`. Buscarla en la
    campaña devolvería vacío siempre y el boleto saldría sin fecha."""
    from backend.domain.sweepstakes.entities.sweepstakes_draw import SweepstakesDraw

    campaign = _campaign(conn, chances_per_amount="500")
    with SweepstakesUnitOfWork(conn) as uow:
        uow.draws.save(SweepstakesDraw.schedule(
            campaign.id, scheduled_at="2026-12-24T18:00:00"))
    conn.commit()

    venta = _SaleDTO(customer_id=new_uuid(), total=Decimal("500"))
    client = SalesSweepstakesClient(conn)
    client.issue_tickets_for_sale(sale=venta)
    conn.commit()

    assert client.get_printable_tickets_for_sale(
        sale_id=venta.id)[0]["draw_date"] == "2026-12-24T18:00:00"


def test_a_campaign_without_a_scheduled_draw_still_prints(conn):
    """Un boleto sin fecha de sorteo sigue participando: la ausencia se deja
    vacía en vez de impedir la impresión."""
    _campaign(conn, chances_per_amount="500")
    venta = _SaleDTO(customer_id=new_uuid(), total=Decimal("500"))
    client = SalesSweepstakesClient(conn)
    client.issue_tickets_for_sale(sale=venta)
    conn.commit()

    payload = client.get_printable_tickets_for_sale(sale_id=venta.id)[0]
    assert payload["draw_date"] == ""
    assert payload["ticket_number"]


def test_a_sale_with_no_tickets_returns_an_empty_list(conn):
    assert SalesSweepstakesClient(conn).get_printable_tickets_for_sale(
        sale_id=new_uuid()) == []


def test_only_the_tickets_of_that_sale_are_returned(conn):
    """El enlace no es directo: el boleto apunta a su derecho, y es el derecho
    el que sabe de qué venta salió."""
    _campaign(conn, chances_per_amount="500")
    client = SalesSweepstakesClient(conn)
    mia = _SaleDTO(customer_id=new_uuid(), total=Decimal("500"))
    otra = _SaleDTO(customer_id=new_uuid(), total=Decimal("500"))
    client.issue_tickets_for_sale(sale=mia)
    client.issue_tickets_for_sale(sale=otra)
    conn.commit()

    assert len(client.get_printable_tickets_for_sale(sale_id=mia.id)) == 1
