"""Reimpresión con la FOTO del ticket (comparativa de tickets, 2026-10-16).

Decisión del usuario: la reimpresión sale idéntica al original, marcada. Antes
volvía a consultar diseño, puntos y campañas de HOY: un ticket viejo podía salir
con una promoción que no existía al vender.
"""

from __future__ import annotations

import importlib
import json
import os
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from backend.application.queries.document_output.ticket_design_query_service import (
    TicketDesignQueryService,
)
from backend.application.use_cases.configuracion.document_template_use_cases import (
    ChangeTemplateVersionStatusUseCase,
    CreateNextTemplateVersionUseCase,
    TemplateVersionAction,
)
from backend.domain.document_output.ticket_layout import TicketBlock, default_layout
from backend.infrastructure.db.schema.document_output_schema import create_document_output_schema
from frontend.desktop.modules.sales_pos.composition import build_sales_pos_presenter
from tests.integration.sales.test_sales_audit_cebf67a import (  # noqa: F401 - fixture
    _Session,
    _sale_in_checkout,
    conn,
)
from tests.integration._pos_ready import open_cash_shift, stock_product
from backend.shared.ids import new_uuid

_342 = importlib.import_module("migrations.standalone.342_ticket_design_branding")


class _Printer:
    def __init__(self):
        self.documents = []

    def print_document(self, document, on_success=None, on_error=None):
        self.documents.append(document)
        if on_success:
            on_success()
        return new_uuid()

    def print_raffle_ticket(self, payload):
        return new_uuid()


def _activate_custom(conn, text):
    version = TicketDesignQueryService(conn).active_layout("SALE_TICKET").template_version_id
    blocks = [TicketBlock(b.type, b.enabled, b.align,
                          {**b.options, **({"text": text} if b.type == "thanks" else {})})
              for b in default_layout().blocks]
    draft = CreateNextTemplateVersionUseCase(conn).execute(
        version_id=version, content=default_layout().with_blocks(blocks).to_json(),
        created_by_user_id="u-disena")
    uc = ChangeTemplateVersionStatusUseCase(conn)
    uc.execute(version_id=draft.id, action=TemplateVersionAction.SUBMIT_FOR_APPROVAL)
    uc.execute(version_id=draft.id, action=TemplateVersionAction.APPROVE, actor_user_id="u-aprueba")
    uc.execute(version_id=draft.id, action=TemplateVersionAction.ACTIVATE, actor_user_id="u-aprueba")
    return draft.id


def test_the_reprint_is_the_original_ticket_marked(conn):
    create_document_output_schema(conn)
    _342.run(conn)
    session = _Session()
    open_cash_shift(conn, branch_id=session.active_branch_id, cashier_user_id=session.user_id)
    product = new_uuid()
    stock_product(conn, product_id=product, branch_id=session.active_branch_id, quantity="10")
    printer = _Printer()
    presenter = build_sales_pos_presenter(conn, session_context=session, printer_service=printer)
    sale_id = _sale_in_checkout(presenter, product)
    presenter.record_payment(sale_id=sale_id, method="CASH", amount=Decimal("100.00"))
    assert presenter.checkout_sale(sale_id=sale_id).success
    original_version = _activate_custom(conn, "Ticket original")

    assert presenter.print_receipt(sale_id=sale_id).success
    original = printer.documents[-1]
    assert original["template_version_id"] == original_version
    assert json.loads(original["layout_json"])["blocks"][-1]["options"]["text"] == "Ticket original"

    _activate_custom(conn, "Diseño nuevo")
    assert presenter.reprint_receipt(sale_id=sale_id, reason="copia").success
    reprint = printer.documents[-1]

    assert reprint["layout_json"] == original["layout_json"]
    assert reprint["template_version_id"] == original_version
    assert reprint["payload"].pop("reimpresion") is True
    assert reprint["payload"] == original["payload"]
    assert conn.execute("SELECT COUNT(*) FROM sale_receipt_snapshots").fetchone()[0] == 1


def test_a_new_sale_after_the_change_uses_the_new_design(conn):
    create_document_output_schema(conn)
    _342.run(conn)
    _activate_custom(conn, "Diseño nuevo")
    session = _Session()
    open_cash_shift(conn, branch_id=session.active_branch_id, cashier_user_id=session.user_id)
    product = new_uuid()
    stock_product(conn, product_id=product, branch_id=session.active_branch_id, quantity="10")
    printer = _Printer()
    presenter = build_sales_pos_presenter(conn, session_context=session, printer_service=printer)
    sale_id = _sale_in_checkout(presenter, product)
    presenter.record_payment(sale_id=sale_id, method="CASH", amount=Decimal("100.00"))
    presenter.checkout_sale(sale_id=sale_id)
    presenter.print_receipt(sale_id=sale_id)
    assert "Diseño nuevo" in printer.documents[-1]["layout_json"]
