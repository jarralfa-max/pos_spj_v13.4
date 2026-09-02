"""SET-15 cutover — the real capabilities `LoyaltyService`'s raffle
methods already had, proven to work with real UUIDv7 string identity
(not just the legacy integer ids `tests/test_raffle_rules_engine.py`
exercises) — this is the exact claim the original SET-15 audit disputed
and this round's own audit disproved by reading the code. Also covers
the two new methods this cutover adds:
`LoyaltyRepository.get_tickets_for_venta()` and
`LoyaltyService.get_printable_tickets_for_sale()`.
"""

import sqlite3

from backend.shared.ids import new_uuid
from core.services.loyalty_service import LoyaltyService


def _db():
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE configuraciones(clave TEXT PRIMARY KEY, valor TEXT)')
    return db


def _svc(sucursal_id="branch-1"):
    return LoyaltyService(_db(), sucursal_id=sucursal_id)


def _mk_raffle(svc, sucursal_id="branch-1", **rules):
    return svc.create_raffle_with_rules(
        {
            "nombre": "Rifa UUID", "premio": "Refrigerador", "premio_costo_estimado": 10,
            "presupuesto_maximo": 20, "ventas_objetivo": 20, "monto_por_boleto": 10,
            "estado": "activa", "financial_status": "reservada",
            "fecha_inicio": "2026-01-01 00:00:00", "fecha_fin": "2026-12-31 23:59:59",
            "sucursal_id": sucursal_id,
        },
        rules, [{"nombre": "P1", "cantidad": 1, "costo_estimado": 10, "orden": 1}],
        {"branches": [sucursal_id]},
    )


class TestRaffleMethodsWorkWithRealUuidv7Identity:
    """Disproves the original SET-15 audit's stated blocker: these
    methods never join against a legacy table by venta_id — every id is
    an opaque string throughout."""

    def test_process_raffles_for_sale_issues_a_ticket_with_uuidv7_ids(self):
        svc = _svc(sucursal_id="branch-1")
        _mk_raffle(svc, sucursal_id="branch-1", ticket_strategy="per_sale", tickets_per_sale=1)
        sale_id, customer_id = new_uuid(), new_uuid()

        out = svc.process_raffles_for_sale(
            sale_id, customer_id, "F-0001", 120, "branch-1", sale_datetime="2026-06-01 10:00:00")

        assert len(out) == 1
        assert out[0]["numero_boleto"]

    def test_branch_eligibility_matches_on_string_identity(self):
        svc = _svc(sucursal_id="branch-1")
        _mk_raffle(svc, sucursal_id="branch-1")
        out = svc.process_raffles_for_sale(
            new_uuid(), new_uuid(), "F", 100, "branch-2", sale_datetime="2026-06-01 10:00:00")
        assert out == []

    def test_no_legacy_table_row_is_required_for_the_sale_id(self):
        """The sale never needs to exist in any legacy table — venta_id
        is purely an opaque tracking string in raffle_tickets."""
        svc = _svc(sucursal_id="branch-1")
        _mk_raffle(svc, sucursal_id="branch-1", ticket_strategy="per_sale", tickets_per_sale=1)
        sale_id = new_uuid()
        out = svc.process_raffles_for_sale(
            sale_id, new_uuid(), "F", 120, "branch-1", sale_datetime="2026-06-01 10:00:00")
        assert len(out) == 1
        tickets = svc._app.repo.get_tickets_for_venta(str(sale_id))
        assert len(tickets) == 1
        assert tickets[0]["venta_id"] == str(sale_id)


class TestGetTicketsForVenta:
    def test_returns_tickets_across_multiple_raffles_for_one_sale(self):
        svc = _svc(sucursal_id="branch-1")
        rid1 = _mk_raffle(svc, sucursal_id="branch-1", ticket_strategy="per_sale", tickets_per_sale=1)
        rid2 = _mk_raffle(svc, sucursal_id="branch-1", ticket_strategy="per_sale", tickets_per_sale=1)
        sale_id = new_uuid()
        svc.generate_tickets_for_sale(rid1, str(sale_id), new_uuid(), "F", 100, "branch-1", ticket_count=1)
        svc.generate_tickets_for_sale(rid2, str(sale_id), new_uuid(), "F", 100, "branch-1", ticket_count=1)

        tickets = svc._app.repo.get_tickets_for_venta(str(sale_id))
        assert {t["raffle_id"] for t in tickets} == {rid1, rid2}

    def test_excludes_other_sales_tickets(self):
        svc = _svc(sucursal_id="branch-1")
        rid = _mk_raffle(svc, sucursal_id="branch-1", ticket_strategy="per_sale", tickets_per_sale=1)
        sale_a, sale_b = new_uuid(), new_uuid()
        svc.generate_tickets_for_sale(rid, str(sale_a), new_uuid(), "F", 100, "branch-1", ticket_count=1)
        svc.generate_tickets_for_sale(rid, str(sale_b), new_uuid(), "F", 100, "branch-1", ticket_count=1)

        tickets = svc._app.repo.get_tickets_for_venta(str(sale_a))
        assert len(tickets) == 1
        assert tickets[0]["venta_id"] == str(sale_a)

    def test_excludes_cancelled_tickets(self):
        svc = _svc(sucursal_id="branch-1")
        rid = _mk_raffle(svc, sucursal_id="branch-1", ticket_strategy="per_sale", tickets_per_sale=1)
        sale_id = new_uuid()
        svc.generate_tickets_for_sale(rid, str(sale_id), new_uuid(), "F", 100, "branch-1", ticket_count=1)
        svc.cancel_tickets_for_sale(str(sale_id), "prueba")

        assert svc._app.repo.get_tickets_for_venta(str(sale_id)) == []

    def test_no_tickets_returns_empty_list(self):
        svc = _svc()
        assert svc._app.repo.get_tickets_for_venta(new_uuid()) == []


class TestGetPrintableTicketsForSale:
    def test_returns_real_print_payloads_for_issued_tickets(self):
        svc = _svc(sucursal_id="branch-1")
        _mk_raffle(svc, sucursal_id="branch-1", ticket_strategy="per_sale", tickets_per_sale=1)
        sale_id = new_uuid()
        svc.process_raffles_for_sale(
            sale_id, new_uuid(), "F-0001", 120, "branch-1", sale_datetime="2026-06-01 10:00:00")

        payloads = svc.get_printable_tickets_for_sale(sale_id)

        assert len(payloads) == 1
        payload = payloads[0]
        assert payload["ticket_type"] == "raffle_ticket"
        assert payload["numero_boleto"]
        assert payload["raffle_name"] == "Rifa UUID"
        assert payload["venta_id"] == str(sale_id)
        assert payload["qr_content"]

    def test_multiple_raffles_are_all_resolved(self):
        svc = _svc(sucursal_id="branch-1")
        rid1 = _mk_raffle(svc, sucursal_id="branch-1", ticket_strategy="per_sale", tickets_per_sale=1)
        rid2 = _mk_raffle(svc, sucursal_id="branch-1", ticket_strategy="per_sale", tickets_per_sale=1)
        sale_id = new_uuid()
        svc.generate_tickets_for_sale(rid1, str(sale_id), new_uuid(), "F", 100, "branch-1", ticket_count=1)
        svc.generate_tickets_for_sale(rid2, str(sale_id), new_uuid(), "F", 100, "branch-1", ticket_count=1)

        payloads = svc.get_printable_tickets_for_sale(sale_id)
        assert len(payloads) == 2
        assert {p["raffle_id"] for p in payloads} == {rid1, rid2}

    def test_empty_when_nothing_issued(self):
        svc = _svc()
        assert svc.get_printable_tickets_for_sale(new_uuid()) == []
