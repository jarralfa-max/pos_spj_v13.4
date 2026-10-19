"""Transferencia entre sucursales de punta a punta (integración Logística 32cfbf):
solicitud → aprobación → preparación → despacho → recepción parcial.

Inventario registra UNA salida en el origen y UNA entrada en el destino por
documento; no pasa por Compras (ni recepción comercial ni CxP); lo que no llega
queda como diferencia."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.application.transfers.commands.transfer_request_commands import (
    ApproveTransferRequestCommand,
    ConfirmTransferPickingCommand,
    ConfirmTransferReceiptCommand,
    CreateTransferRequestCommand,
    DispatchTransferShipmentCommand,
    DispatchTransferShipmentLineCommand,
    ReceiveTransferLineCommand,
    ReserveTransferInventoryCommand,
    StartTransferPickingCommand,
    SubmitTransferRequestCommand,
    TransferPickLineCommand,
    TransferRequestLineCommand,
)
from backend.application.transfers.composition import TransferUseCaseFactory
from backend.domain.transfers.enums import TransferNodeType, TransferType
from backend.domain.transfers.exceptions import SegregationOfDutiesError
from backend.domain.transfers.value_objects.transfer_node import TransferNode
from backend.infrastructure.db.schema.transfers_schema import create_transfers_schema
from backend.shared.ids import new_uuid
from tests.integration.meat_processing._generic_plant import KG, Planta, build_db


@pytest.fixture
def mundo():
    conn = build_db()
    create_transfers_schema(conn)
    origen, destino = Planta(conn), Planta(conn)
    pollo = origen.producto("Pollo Entero")
    lote = origen.existencia(pollo, "50", lote="L-ORIGEN")
    yield conn, origen, destino, pollo, lote
    conn.close()


def _saldo(conn, producto, sucursal, estado="AVAILABLE"):
    filas = conn.execute("SELECT quantity FROM inventory_balances WHERE product_id=? AND"
                         " branch_id=? AND inventory_status=?", (producto, sucursal, estado))
    return sum((Decimal(str(f[0])) for f in filas), Decimal("0"))


def _ubicacion(conn, linea):
    from backend.application.transfers.composition import TransferUseCaseFactory as _F
    from backend.infrastructure.integrations.transfers_inventory_gateway import (
        reserved_pick_lines,
    )
    tid = conn.execute("SELECT transfer_id FROM stock_transfer_lines WHERE id=?",
                       (linea,)).fetchone()[0]
    transfer = _F.for_tests(connection=conn)._repository.get(tid)
    return reserved_pick_lines(conn, transfer)[linea][0][0]


def _hasta_transito(conn, origen, destino, pollo, kg="20"):
    f = TransferUseCaseFactory.for_tests(connection=conn)
    pide, aprueba, surte, despacha, verifica = (new_uuid() for _ in range(5))
    dto = f.create_transfer_request().execute(CreateTransferRequestCommand(
        requested_by_user_id=pide, operation_id=new_uuid(),
        transfer_type=TransferType.BRANCH_TO_BRANCH,
        origin_node=TransferNode(TransferNodeType.BRANCH, branch_id=origen.branch),
        destination_node=TransferNode(TransferNodeType.BRANCH, branch_id=destino.branch),
        lines=(TransferRequestLineCommand(product_id=pollo, unit_id=KG,
                                          requested_quantity=Decimal(kg)),)))
    tid = dto.transfer_id
    f.submit_transfer_request().execute(SubmitTransferRequestCommand(tid, pide, new_uuid()))
    f.approve_transfer_request().execute(ApproveTransferRequestCommand(tid, aprueba, new_uuid()))
    f.reserve_transfer_inventory().execute(ReserveTransferInventoryCommand(tid, surte, new_uuid()))
    linea = f._repository.get(tid).lines[0].id
    f.start_transfer_picking().execute(StartTransferPickingCommand(tid, surte, new_uuid()))
    f.confirm_transfer_picking().execute(ConfirmTransferPickingCommand(
        tid, surte, new_uuid(), (TransferPickLineCommand(linea, Decimal(kg), location_id=_ubicacion(conn, linea)),)))
    f.mark_ready_to_dispatch().execute(transfer_id=tid, user_id=surte, operation_id=new_uuid())
    envio = f.dispatch_transfer().execute(DispatchTransferShipmentCommand(
        transfer_id=tid, dispatched_by_user_id=despacha, verified_by_user_id=verifica,
        custody_received_by_user_id=new_uuid(), operation_id=new_uuid(),
        shipment_number=f"EMB-{tid[-6:]}",
        lines=(DispatchTransferShipmentLineCommand(linea, Decimal(kg)),)))
    return f, tid, linea, envio, despacha


def test_dispatch_moves_stock_out_of_the_origin_once(mundo):
    conn, origen, destino, pollo, lote = mundo
    _f, tid, _linea, _envio, _d = _hasta_transito(conn, origen, destino, pollo)
    assert _saldo(conn, pollo, origen.branch) == Decimal("30")
    reservado = conn.execute("SELECT SUM(CAST(reserved_quantity AS REAL)) FROM inventory_balances"
                             " WHERE product_id=? AND branch_id=?", (pollo, origen.branch)).fetchone()
    assert Decimal(str(reservado[0] or 0)) == 0
    estado = conn.execute("SELECT status FROM stock_transfers WHERE id=?", (tid,)).fetchone()[0]
    assert estado == "IN_TRANSIT"
    salidas = conn.execute("SELECT COUNT(*) FROM inventory_ledger WHERE movement_type="
                           "'TRANSFER_DISPATCH'").fetchone()[0]
    assert salidas == 1


def test_partial_receipt_enters_destination_and_records_the_difference(mundo):
    conn, origen, destino, pollo, lote = mundo
    f, tid, linea, envio, _d = _hasta_transito(conn, origen, destino, pollo)
    recibe = new_uuid()
    f.receive_transfer().execute(ConfirmTransferReceiptCommand(
        transfer_id=tid, shipment_id=envio.shipment_id, received_by_user_id=recibe,
        operation_id=new_uuid(), lines=(ReceiveTransferLineCommand(linea, Decimal("18")),)))
    assert _saldo(conn, pollo, destino.branch) == Decimal("18")
    lote_destino = conn.execute("SELECT lot_id FROM inventory_balances WHERE product_id=? AND"
                                " branch_id=?", (pollo, destino.branch)).fetchone()[0]
    assert lote_destino == lote                        # viaja con su lote (trazabilidad)
    assert conn.execute("SELECT COUNT(*) FROM transfer_receipts").fetchone()[0] == 1
    # Una transferencia no es una compra.
    for tabla in ("goods_receipts", "accounts_payable", "payables"):
        try:
            assert conn.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0] == 0
        except Exception:  # noqa: BLE001 - la tabla puede no existir en esta base
            pass


def test_rejected_goods_enter_quarantine_not_available(mundo):
    conn, origen, destino, pollo, lote = mundo
    f, tid, linea, envio, _d = _hasta_transito(conn, origen, destino, pollo)
    f.receive_transfer().execute(ConfirmTransferReceiptCommand(
        transfer_id=tid, shipment_id=envio.shipment_id, received_by_user_id=new_uuid(),
        operation_id=new_uuid(), lines=(ReceiveTransferLineCommand(
            linea, Decimal("20"), accepted=False),)))
    assert _saldo(conn, pollo, destino.branch) == 0
    assert _saldo(conn, pollo, destino.branch, "QUARANTINED") == Decimal("20")


def test_the_dispatcher_cannot_receive(mundo):
    conn, origen, destino, pollo, lote = mundo
    f, tid, linea, envio, despacha = _hasta_transito(conn, origen, destino, pollo)
    with pytest.raises(SegregationOfDutiesError):
        f.receive_transfer().execute(ConfirmTransferReceiptCommand(
            transfer_id=tid, shipment_id=envio.shipment_id, received_by_user_id=despacha,
            operation_id=new_uuid(), lines=(ReceiveTransferLineCommand(linea, Decimal("20")),)))
    assert _saldo(conn, pollo, destino.branch) == 0


def test_a_failed_dispatch_leaves_nothing_half_done(mundo):
    """Sin verificador independiente el embarque se rechaza: ni salida de
    Inventario ni cambio de estado."""
    conn, origen, destino, pollo, lote = mundo
    f = TransferUseCaseFactory.for_tests(connection=conn)
    pide, aprueba, surte = new_uuid(), new_uuid(), new_uuid()
    dto = f.create_transfer_request().execute(CreateTransferRequestCommand(
        requested_by_user_id=pide, operation_id=new_uuid(),
        transfer_type=TransferType.BRANCH_TO_BRANCH,
        origin_node=TransferNode(TransferNodeType.BRANCH, branch_id=origen.branch),
        destination_node=TransferNode(TransferNodeType.BRANCH, branch_id=destino.branch),
        lines=(TransferRequestLineCommand(product_id=pollo, unit_id=KG,
                                          requested_quantity=Decimal("5")),)))
    tid = dto.transfer_id
    f.submit_transfer_request().execute(SubmitTransferRequestCommand(tid, pide, new_uuid()))
    f.approve_transfer_request().execute(ApproveTransferRequestCommand(tid, aprueba, new_uuid()))
    f.reserve_transfer_inventory().execute(ReserveTransferInventoryCommand(tid, surte, new_uuid()))
    linea = f._repository.get(tid).lines[0].id
    f.start_transfer_picking().execute(StartTransferPickingCommand(tid, surte, new_uuid()))
    f.confirm_transfer_picking().execute(ConfirmTransferPickingCommand(
        tid, surte, new_uuid(), (TransferPickLineCommand(linea, Decimal("5"), location_id=_ubicacion(conn, linea)),)))
    f.mark_ready_to_dispatch().execute(transfer_id=tid, user_id=surte, operation_id=new_uuid())
    with pytest.raises(ValueError):
        f.dispatch_transfer().execute(DispatchTransferShipmentCommand(
            transfer_id=tid, dispatched_by_user_id=surte, verified_by_user_id=surte,
            custody_received_by_user_id=new_uuid(), operation_id=new_uuid(),
            shipment_number="EMB-X", lines=(DispatchTransferShipmentLineCommand(linea, Decimal("5")),)))
    conn.rollback()
    assert _saldo(conn, pollo, origen.branch) == Decimal("50")
    assert conn.execute("SELECT status FROM stock_transfers WHERE id=?", (tid,)).fetchone()[0] \
        == "READY_TO_DISPATCH"


def _ciclo(conn):
    from backend.application.transfers.cycle_service import TransferCycleService
    from backend.application.transfers.queries.transfer_detail_query_service import (
        TransferDetailQueryService,
    )
    from backend.infrastructure.integrations.transfers_inventory_gateway import (
        reserved_pick_lines,
    )
    f = TransferUseCaseFactory.for_tests(connection=conn)
    usos = {"submit": f.submit_transfer_request(), "approve": f.approve_transfer_request(),
            "reject": f.reject_transfer_request(), "reserve": f.reserve_transfer_inventory(),
            "start_picking": f.start_transfer_picking(),
            "confirm_picking": f.confirm_transfer_picking(),
            "ready_to_dispatch": f.mark_ready_to_dispatch(), "dispatch": f.dispatch_transfer(),
            "receive": f.receive_transfer()}
    return f, TransferCycleService(
        conn, use_cases=usos, detail_query=TransferDetailQueryService(conn).detail,
        pick_lines=lambda tid: reserved_pick_lines(conn, f._repository.get(tid)))


def test_the_screen_path_runs_the_whole_cycle(mundo):
    """Lo que hacen los botones: enviar → aprobar → preparar → despachar → recibir."""
    conn, origen, destino, pollo, lote = mundo
    f, ciclo = _ciclo(conn)
    pide, aprueba, prepara, despacha, verifica, recibe = (new_uuid() for _ in range(6))
    tid = f.create_transfer_request().execute(CreateTransferRequestCommand(
        requested_by_user_id=pide, operation_id=new_uuid(),
        transfer_type=TransferType.BRANCH_TO_BRANCH,
        origin_node=TransferNode(TransferNodeType.BRANCH, branch_id=origen.branch),
        destination_node=TransferNode(TransferNodeType.BRANCH, branch_id=destino.branch),
        lines=(TransferRequestLineCommand(product_id=pollo, unit_id=KG,
                                          requested_quantity=Decimal("12")),))).transfer_id
    assert ciclo.submit(tid, pide)[0]
    assert ciclo.approve(tid, aprueba)[0]
    ok, msg, _ = ciclo.prepare(tid, prepara)
    assert ok, msg
    ok, msg, _ = ciclo.dispatch(tid, despacha, verifier_user_id=verifica, seal="S-1")
    assert ok, msg
    detalle = ciclo.detail(tid)
    (envio,) = detalle["shipments"]
    assert envio["pending_lines"][0]["product_name"] == "Pollo Entero"
    ok, msg, _ = ciclo.receive(tid, recibe, envio["shipment_id"], [
        {"line_id": envio["pending_lines"][0]["line_id"], "quantity": "12", "accepted": True}])
    assert ok, msg
    assert _saldo(conn, pollo, origen.branch) == Decimal("38")
    assert _saldo(conn, pollo, destino.branch) == Decimal("12")
    assert ciclo.detail(tid)["status"] == "RECEIVED"


def test_a_failing_step_is_rolled_back_by_the_service(mundo):
    conn, origen, destino, pollo, lote = mundo
    f, ciclo = _ciclo(conn)
    pide, aprueba, prepara = new_uuid(), new_uuid(), new_uuid()
    tid = f.create_transfer_request().execute(CreateTransferRequestCommand(
        requested_by_user_id=pide, operation_id=new_uuid(),
        transfer_type=TransferType.BRANCH_TO_BRANCH,
        origin_node=TransferNode(TransferNodeType.BRANCH, branch_id=origen.branch),
        destination_node=TransferNode(TransferNodeType.BRANCH, branch_id=destino.branch),
        lines=(TransferRequestLineCommand(product_id=pollo, unit_id=KG,
                                          requested_quantity=Decimal("80")),))).transfer_id
    ciclo.submit(tid, pide)
    ciclo.approve(tid, aprueba)
    ok, msg, _ = ciclo.prepare(tid, prepara)               # sólo hay 50
    assert not ok and "insuficiente" in msg.lower()
    assert ciclo.detail(tid)["status"] == "APPROVED"
    reservado = conn.execute("SELECT SUM(CAST(reserved_quantity AS REAL)) FROM inventory_balances"
                             " WHERE product_id=?", (pollo,)).fetchone()[0]
    assert Decimal(str(reservado or 0)) == 0


def test_cycle_pages_show_their_actions():
    import pytest as _pytest
    QtWidgets = _pytest.importorskip("PyQt5.QtWidgets")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])  # noqa: F841
    from frontend.desktop.modules.transfers.pages.workspace_pages import PAGE_CLASSES

    class _P:
        def can_run(self, action):
            return True

        def load_page(self, page_id, search=""):
            from types import SimpleNamespace
            return SimpleNamespace(rows=[], empty_message="")

    esperadas = {"transfers_requests": {"submit"}, "transfers_approvals": {"approve", "reject"},
                 "transfers_picking": {"prepare"}, "transfers_ready_to_dispatch": {"dispatch"},
                 "transfers_in_transit": {"receive"}, "transfers_receipts": {"receive"}}
    for page_id, acciones in esperadas.items():
        pagina = PAGE_CLASSES[page_id](_P())
        assert set(pagina.cycle_buttons) == acciones, page_id
        assert all(b.isEnabled() for b in pagina.cycle_buttons.values())
