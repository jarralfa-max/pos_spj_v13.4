"""CARACTERIZACIÓN (SDLC-CORE-012): recepción por el camino de la pantalla, tal como
funciona HOY (`TransferCycleService.receive`).

Estas pruebas no dicen que el comportamiento sea correcto: lo fijan para que el
cambio se haga a propósito. `CAMBIA: <ítem>` indica qué ítem debe actualizarlas.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.application.inventory.use_cases.ensure_technical_locations import (
    EnsureTechnicalLocationsUseCase,
)
from backend.application.meat_processing.queries.direct_transformation_query_service import (
    DirectTransformationQueryService,
)
from backend.application.transfers.commands.transfer_request_commands import (
    CreateTransferRequestCommand,
    TransferRequestLineCommand,
)
from backend.domain.transfers.enums import TransferNodeType, TransferType
from backend.domain.transfers.value_objects.transfer_node import TransferNode
from backend.infrastructure.db.schema.transfers_schema import create_transfers_schema
from backend.shared.ids import new_uuid
from tests.integration._reversible_cutting import active_yield_profile
from tests.integration.meat_processing._generic_plant import KG, Planta, build_db
from tests.integration.transfers.test_transfer_full_cycle_32cfbf import _ciclo, _saldo


@pytest.fixture
def mundo():
    conn = build_db()
    create_transfers_schema(conn)
    origen, destino = Planta(conn), Planta(conn)
    pollo = origen.producto("Pollo Entero")
    origen.existencia(pollo, "50", lote="L-ORIGEN")
    yield conn, origen, destino, pollo
    conn.close()


def _en_transito(conn, origen, destino, pollo, kg="12"):
    f, ciclo = _ciclo(conn)
    pide, aprueba, prepara, despacha, verifica = (new_uuid() for _ in range(5))
    tid = f.create_transfer_request().execute(CreateTransferRequestCommand(
        requested_by_user_id=pide, operation_id=new_uuid(),
        transfer_type=TransferType.BRANCH_TO_BRANCH,
        origin_node=TransferNode(TransferNodeType.BRANCH, branch_id=origen.branch),
        destination_node=TransferNode(TransferNodeType.BRANCH, branch_id=destino.branch),
        lines=(TransferRequestLineCommand(product_id=pollo, unit_id=KG,
                                          requested_quantity=Decimal(kg)),))).transfer_id
    assert ciclo.submit(tid, pide)[0]
    assert ciclo.approve(tid, aprueba)[0]
    assert ciclo.prepare(tid, prepara)[0]
    assert ciclo.dispatch(tid, despacha, verifier_user_id=verifica)[0]
    (envio,) = ciclo.detail(tid)["shipments"]
    return ciclo, tid, envio["shipment_id"], envio["pending_lines"][0]["line_id"]


def _entradas(conn, pollo) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM inventory_ledger m"
        " JOIN inventory_ledger_lines l ON l.movement_id = m.id"
        " WHERE m.movement_type = 'TRANSFER_RECEIPT' AND l.product_id = ?", (pollo,)).fetchone()[0]


class _Espia:
    def __init__(self, real) -> None:
        self.real, self.comandos = real, []

    def execute(self, comando):
        self.comandos.append(comando)
        return self.real.execute(comando)


def test_the_screen_path_drops_weight_pieces_lot_and_temperature(mundo):
    """CARACTERIZACIÓN — CAMBIA: SDLC-TRF-001 (defecto conocido). Aunque la pantalla
    mandara esos datos, `receive` sólo arma renglón, cantidad y aceptado."""
    conn, origen, destino, pollo = mundo
    ciclo, tid, envio, linea = _en_transito(conn, origen, destino, pollo)
    espia = _Espia(ciclo._uc["receive"])
    ciclo._uc["receive"] = espia

    ok, mensaje, _ = ciclo.receive(tid, new_uuid(), envio, [{
        "line_id": linea, "quantity": "12", "accepted": True, "weight": "11.8",
        "pieces": "6", "lot_id": "L-CAPTURADO", "temperature": "3.5",
        "expires_on": "2099-01-01"}])

    assert ok, mensaje
    (renglon,) = espia.comandos[0].lines
    assert renglon.observed_quantity == Decimal("12") and renglon.accepted is True
    assert Decimal(str(renglon.observed_weight)) == 0
    assert Decimal(str(renglon.observed_pieces)) == 0
    assert renglon.lot_id is None and renglon.temperature is None
    assert renglon.expires_on is None


def test_an_accepted_receipt_posts_exactly_one_entry(mundo):
    """CARACTERIZACIÓN — la conserva SDLC-TRF-001: recibir una vez, una entrada."""
    conn, origen, destino, pollo = mundo
    ciclo, tid, envio, linea = _en_transito(conn, origen, destino, pollo)

    ok, mensaje, _ = ciclo.receive(tid, new_uuid(), envio, [
        {"line_id": linea, "quantity": "12", "accepted": True}])

    assert ok, mensaje
    assert _entradas(conn, pollo) == 1
    assert _saldo(conn, pollo, destino.branch) == Decimal("12")
    assert ciclo.detail(tid)["status"] == "RECEIVED"


def test_receiving_a_second_time_posts_no_second_entry(mundo):
    """CARACTERIZACIÓN — la conserva SDLC-TRF-001."""
    conn, origen, destino, pollo = mundo
    ciclo, tid, envio, linea = _en_transito(conn, origen, destino, pollo)
    renglones = [{"line_id": linea, "quantity": "12", "accepted": True}]
    assert ciclo.receive(tid, new_uuid(), envio, renglones)[0]

    ok, _mensaje, _ = ciclo.receive(tid, new_uuid(), envio, renglones)

    assert ok is False
    assert _entradas(conn, pollo) == 1
    assert _saldo(conn, pollo, destino.branch) == Decimal("12")


def test_a_receipt_without_a_destination_warehouse_never_reaches_direct_transformation(mundo):
    """CARACTERIZACIÓN — CAMBIA: SDLC-TRF-003 (defecto conocido). Sin almacén destino,
    entra al almacén de compras; el despiece sólo lista almacenes de producción."""
    conn, origen, destino, pollo = mundo
    produccion = new_uuid()
    conn.execute(
        "INSERT INTO warehouses (id, code, name, branch_id, warehouse_type, status,"
        " allow_sales_allocation, allow_purchase_receipt, allow_production, allow_quarantine,"
        " created_at, updated_at) VALUES (?,?,?,?,'STORE','ACTIVE',0,0,1,0,'x','x')",
        (produccion, f"PROD-{produccion[-6:]}", "Producción", destino.branch))
    EnsureTechnicalLocationsUseCase().execute(conn, warehouse_id=produccion)
    conn.execute("UPDATE warehouses SET allow_production=0 WHERE id=?", (destino.warehouse,))
    active_yield_profile(conn, product_id=pollo, outputs=[
        {"product_id": new_uuid(), "output_type": "MAIN_PRODUCT", "expected_yield_pct": "100",
         "unit_id": KG}])
    conn.commit()
    ciclo, tid, envio, linea = _en_transito(conn, origen, destino, pollo)

    assert ciclo.receive(tid, new_uuid(), envio, [
        {"line_id": linea, "quantity": "12", "accepted": True}])[0]

    almacenes = {fila[0] for fila in conn.execute(
        "SELECT warehouse_id FROM inventory_balances WHERE product_id=? AND branch_id=?",
        (pollo, destino.branch))}
    assert almacenes == {destino.warehouse}
    assert DirectTransformationQueryService(conn).lots(destino.branch) == []
