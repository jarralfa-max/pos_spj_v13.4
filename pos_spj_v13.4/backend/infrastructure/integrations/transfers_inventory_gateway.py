"""Inventario detrás de Transferencias (integración Logística 32cfbf).

`CanonicalInventoryTransferGateway` existía con sus puertos, pero ninguna
implementación los llenaba: una transferencia no podía reservar, despachar ni
recibir. Aquí están, cada una delegando en el caso de uso de Inventario con la
concesión `transfers` (`integration_grants.py`) y uniéndose a la transacción del
caso de uso de Transferencias (`owns_transaction=False`): el movimiento, el
estado de la transferencia y el embarque/recepción se confirman juntos.

- RESERVAR: por renglón, lo aprobado que aún no está reservado, de los lotes
  que Inventario elige (`ReserveStockForTransferUseCase`, origen TRANSFER).
- DESPACHAR: lo despachado que aún no se ha posteado sale como
  `TRANSFER_DISPATCH` desde los saldos reservados (lote y ubicación exactos) y
  después se cumplen esas reservas (misma regla que la venta: primero la salida).
- RECIBIR: lo observado entra como `TRANSFER_RECEIPT` en el almacén destino,
  con los lotes que salieron del origen; lo aceptado a disponible (o a
  inspección si Calidad lo pide), lo rechazado a cuarentena. Lo que no llegó no
  entra: queda como diferencia de la transferencia.

Una transferencia NUNCA pasa por Compras: no hay recepción comercial ni CxP.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.inventory.integration_grants import (
    inventory_policy_for,
    inventory_scope_for,
)
from backend.application.transfers.integrations.inventory_gateway import (
    CanonicalInventoryTransferGateway,
    InventoryTransferRequest,
)
from backend.shared.ids import new_uuid

SOURCE_MODULE = "transfers"
_LINE_DOCUMENT = "TRANSFER_LINE"
ZERO = Decimal("0")


class TransferInventoryError(RuntimeError):
    """Inventario rechazó el movimiento; el mensaje es para el operador."""


def resolve_branch_warehouse(connection, branch_id: str, purpose: str) -> str:
    """Almacén de la sucursal para la transferencia: el ACTIVO marcado para el
    propósito; si no hay, el único activo; varios sin marcar → se pide elegir."""
    from backend.application.logistics.warehouse_directory import (
        WarehouseDirectoryQueryService,
    )
    directorio = WarehouseDirectoryQueryService(connection)
    marcados = directorio.warehouses_for_purpose(branch_id, purpose)
    if len(marcados) == 1:
        return marcados[0]
    activos = [r[0] for r in connection.execute(
        "SELECT id FROM warehouses WHERE branch_id=? AND status='ACTIVE'", (branch_id,))]
    if len(activos) == 1:
        return activos[0]
    raise TransferInventoryError(
        "La sucursal no tiene un almacén claro para la transferencia: marca uno en "
        "Inventario → Almacenes (venta para el origen, compra/recepción para el destino).")


class _Base:
    def __init__(self, connection) -> None:
        self._conn = connection

    def _policy(self, actor_id: str):
        return inventory_policy_for(SOURCE_MODULE, actor_id)[0]

    def _scope(self, actor_id: str, branch_id: str, warehouse_id: str):
        return inventory_scope_for(actor_user_id=actor_id, branch_id=branch_id,
                                   warehouse_id=warehouse_id)

    def _origin(self, transfer):
        branch = transfer.origin_node.branch_id
        return branch, (transfer.origin_node.warehouse_id
                        or resolve_branch_warehouse(self._conn, branch, "SALES"))

    def _destination(self, transfer):
        branch = transfer.destination_node.branch_id
        return branch, (transfer.destination_node.warehouse_id
                        or resolve_branch_warehouse(self._conn, branch, "PURCHASE"))

    def _active_reservations(self, line_id: str):
        from backend.infrastructure.db.repositories.inventory.unit_of_work import (
            InventoryUnitOfWork,
        )
        from backend.domain.inventory.enums import ReservationSource
        return [r for r in InventoryUnitOfWork(self._conn).reservations
                .list_active_for_source_document(line_id)
                if r.source is ReservationSource.TRANSFER]

    def _posted(self, line_id: str, movement_type: str) -> list[tuple]:
        """(lote, cantidad, peso, ubicación) ya posteados para el renglón."""
        return [tuple(r) for r in self._conn.execute(
            "SELECT l.lot_id, l.quantity, l.weight, COALESCE(l.from_location_id, l.to_location_id)"
            " FROM inventory_ledger m JOIN inventory_ledger_lines l ON l.movement_id=m.id"
            " WHERE m.source_document_type=? AND m.source_document_id=? AND m.movement_type=?"
            " AND m.status='POSTED'", (_LINE_DOCUMENT, line_id, movement_type))]

    def _post(self, movement, *, actor_id: str, branch: str, warehouse: str) -> None:
        from backend.application.inventory.use_cases.post_inventory_movement import (
            PostInventoryMovementUseCase,
        )
        r = PostInventoryMovementUseCase(self._policy(actor_id)).execute(
            self._conn, movement, actor_user_id=actor_id, owns_transaction=False,
            context=self._scope(actor_id, branch, warehouse))
        if not r.success:
            raise TransferInventoryError(r.message or "Inventario rechazó el movimiento")


class TransferReserveAdapter(_Base):
    def execute(self, request: InventoryTransferRequest) -> None:
        from backend.application.inventory.use_cases.sale_reservation_use_cases import (
            ReserveStockForTransferUseCase,
        )
        transfer, actor = request.transfer, request.actor_id
        branch, warehouse = self._origin(transfer)
        for line in transfer.lines:
            ya = sum((r.quantity for r in self._active_reservations(line.id)), ZERO)
            faltante = Decimal(str(line.reserved_quantity)) - ya
            if faltante <= 0:
                continue
            r = ReserveStockForTransferUseCase(self._policy(actor)).execute(
                self._conn, product_id=line.product_id, branch_id=branch,
                warehouse_id=warehouse, quantity=faltante, source_document_id=line.id,
                operation_id=new_uuid(), actor_user_id=actor,
                lot_required=bool(line.lot_required),
                context=self._scope(actor, branch, warehouse), owns_transaction=False)
            if not r.success:
                raise TransferInventoryError(r.message)


class TransferAllocateAdapter(_Base):
    """La reserva ya asigna lotes (Inventario elige el saldo exacto)."""

    def execute(self, request: InventoryTransferRequest) -> None:
        return None


class TransferDispatchAdapter(_Base):
    def execute(self, request: InventoryTransferRequest) -> None:
        from backend.application.inventory.use_cases.reservation_use_cases import (
            FulfillReservationUseCase,
        )
        from backend.domain.inventory.entities.inventory_movement import (
            InventoryMovement,
            InventoryMovementLine,
        )
        from backend.domain.inventory.enums import InventoryStatus, MovementType
        transfer, actor = request.transfer, request.actor_id
        branch, warehouse = self._origin(transfer)
        for line in transfer.lines:
            posteado = sum((Decimal(q) for _l, q, _w, _loc in self._posted(
                line.id, MovementType.TRANSFER_DISPATCH.value)), ZERO)
            pendiente = Decimal(str(line.dispatched_quantity)) - posteado
            if pendiente <= 0:
                continue
            reservas = self._active_reservations(line.id)
            if sum((r.quantity for r in reservas), ZERO) < pendiente:
                raise TransferInventoryError(
                    "Lo despachado excede lo reservado en Inventario: vuelve a preparar la "
                    "transferencia.")
            lineas, cumplir, resto = [], [], pendiente
            for reserva in reservas:
                if resto <= 0:
                    break
                toma = min(resto, reserva.quantity)
                lineas.append(InventoryMovementLine.create(
                    product_id=line.product_id, quantity=toma, lot_id=reserva.lot_id,
                    from_location_id=reserva.location_id,
                    from_status=InventoryStatus.AVAILABLE, reason_code="TRANSFER"))
                cumplir.append(reserva.id)
                resto -= toma
            self._post(InventoryMovement.create(
                movement_type=MovementType.TRANSFER_DISPATCH, branch_id=branch,
                warehouse_id=warehouse, source_module=SOURCE_MODULE,
                source_document_type=_LINE_DOCUMENT, source_document_id=line.id,
                operation_id=new_uuid(), created_by_user_id=actor, lines=lineas),
                actor_id=actor, branch=branch, warehouse=warehouse)
            for reservation_id in cumplir:
                r = FulfillReservationUseCase(self._policy(actor)).execute(
                    self._conn, reservation_id=reservation_id, operation_id=new_uuid(),
                    actor_user_id=actor, owns_transaction=False,
                    context=self._scope(actor, branch, warehouse))
                if not r.success:
                    raise TransferInventoryError(r.message)


class TransferReceiptAdapter(_Base):
    def execute(self, request: InventoryTransferRequest) -> None:
        from backend.application.inventory.queries.stock_location_resolver import (
            StockLocationResolver,
        )
        from backend.domain.inventory.entities.inventory_movement import (
            InventoryMovement,
            InventoryMovementLine,
        )
        from backend.domain.inventory.enums import InventoryStatus, MovementType
        transfer, receipt, actor = request.transfer, request.receipt, request.actor_id
        branch, warehouse = self._destination(transfer)
        lineas_transfer = {line.id: line for line in transfer.lines}
        resolver = StockLocationResolver(self._conn)
        lineas = []
        for observado in receipt.lines:
            cantidad = Decimal(str(observado.observed_quantity))
            if cantidad <= 0:
                continue
            line = lineas_transfer[observado.transfer_line_id]
            calidad = getattr(observado.quality_status, "value", observado.quality_status)
            if not observado.accepted:
                estado = InventoryStatus.QUARANTINED
            elif calidad and calidad != "AVAILABLE":
                estado = InventoryStatus.PENDING_INSPECTION
            else:
                estado = InventoryStatus.AVAILABLE
            destino = resolver.available_location(product_id=line.product_id,
                                                  branch_id=branch, warehouse_id=warehouse)
            # Los lotes con que salió del origen, en orden; lo ya recibido antes se descuenta.
            despachado = self._posted(line.id, MovementType.TRANSFER_DISPATCH.value)
            recibido = sum((Decimal(q) for _l, q, _w, _loc in self._posted(
                line.id, MovementType.TRANSFER_RECEIPT.value)), ZERO)
            resto = cantidad
            for lot_id, q, _w, _loc in despachado:
                disponible = Decimal(q) - recibido
                recibido = max(ZERO, recibido - Decimal(q))
                if disponible <= 0 or resto <= 0:
                    continue
                toma = min(resto, disponible)
                lineas.append(InventoryMovementLine.create(
                    product_id=line.product_id, quantity=toma,
                    lot_id=observado.lot_id or lot_id, to_location_id=destino,
                    to_status=estado, reason_code="TRANSFER"))
                resto -= toma
            if resto > 0:
                lineas.append(InventoryMovementLine.create(
                    product_id=line.product_id, quantity=resto, lot_id=observado.lot_id,
                    to_location_id=destino, to_status=estado, reason_code="TRANSFER"))
            self._post(InventoryMovement.create(
                movement_type=MovementType.TRANSFER_RECEIPT, branch_id=branch,
                warehouse_id=warehouse, source_module=SOURCE_MODULE,
                source_document_type=_LINE_DOCUMENT, source_document_id=line.id,
                operation_id=new_uuid(), created_by_user_id=actor, lines=lineas),
                actor_id=actor, branch=branch, warehouse=warehouse)
            lineas = []


class TransferReturnNotWired:
    """Las devoluciones de transferencia no tienen pantalla todavía."""

    def dispatch(self, request) -> None:
        raise TransferInventoryError("Las devoluciones de transferencia no están disponibles.")

    def receive(self, request) -> None:
        raise TransferInventoryError("Las devoluciones de transferencia no están disponibles.")


def build_transfer_inventory_gateway(connection) -> CanonicalInventoryTransferGateway:
    return CanonicalInventoryTransferGateway(
        reserve=TransferReserveAdapter(connection), allocate=TransferAllocateAdapter(connection),
        dispatch=TransferDispatchAdapter(connection), receipt=TransferReceiptAdapter(connection),
        transfer_return=TransferReturnNotWired())


def reserved_pick_lines(connection, transfer) -> dict[str, list[tuple[str | None, str | None, Decimal]]]:
    """Por renglón: (ubicación, lote, cantidad) que Inventario reservó. Es lo
    que el surtido confirma como escaneado al preparar en una sola acción."""
    base = _Base(connection)
    return {line.id: [(r.location_id, r.lot_id, r.quantity)
                      for r in base._active_reservations(line.id)]
            for line in transfer.lines}
