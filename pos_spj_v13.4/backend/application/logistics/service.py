"""Transactional application service for canonical Logistics operations."""

from __future__ import annotations

import json

from backend.application.logistics.authorization import (
    LogisticsAuthorizationPolicy, LogisticsPermissions,
)
from backend.domain.logistics.entities import (
    ContainerCustodyEvent, ContainerLabel, ContainerType, ContainerTypeCompatibility,
    LogisticsShipment, PhysicalContainer, PrintJob, ShipmentContentAssignment, utcnow,
)
from backend.domain.logistics.enums import ContainerStatus, CustodyAction
from backend.domain.logistics.qr_identity import PermanentContainerQrService
from backend.infrastructure.db.repositories.logistics_repository import LogisticsRepository
from backend.shared.ids import new_uuid


class LogisticsApplicationService:
    def __init__(self, connection, authorization: LogisticsAuthorizationPolicy,
                 qr_service: PermanentContainerQrService, printer_gateway=None) -> None:
        self._connection = connection
        self._repo = LogisticsRepository(connection)
        self._auth = authorization
        self._qr = qr_service
        self._printer = printer_gateway

    def register_type(self, *, actor_user_id: str, item: ContainerType) -> str:
        self._auth.require(actor_user_id, LogisticsPermissions.CONTAINER_MANAGE)
        with self._connection:
            self._repo.save_type(item)
        return item.id

    def register_compatibility(self, *, actor_user_id: str,
                               item: ContainerTypeCompatibility) -> str:
        self._auth.require(actor_user_id, LogisticsPermissions.CONTAINER_MANAGE)
        with self._connection:
            self._repo.save_compatibility(item)
        return item.id

    def register_container(self, *, actor_user_id: str,
                           container: PhysicalContainer, operation_id: str,
                           code_prefix: str | None = None) -> dict:
        """Alta del contenedor. Sin código (`container_code` vacío) el sistema
        asigna el siguiente de `code_prefix` DENTRO de la transacción; el código
        es UNIQUE, así que un choque con otra estación se reintenta."""
        import sqlite3

        self._auth.require(actor_user_id, LogisticsPermissions.CONTAINER_MANAGE)
        previous = self._operation_result(operation_id)
        if previous is not None:
            return previous
        token = self._qr.issue(container)
        automatico = not container.container_code
        for intento in range(5):
            try:
                with self._connection:
                    if automatico:
                        container.container_code = self._repo.next_container_code(
                            code_prefix or "CT")
                    result = {"container_id": container.id, "qr_url": token,
                              "code": container.container_code}
                    self._repo.save_container(container)
                    self._audit(actor_user_id, operation_id, "PhysicalContainer",
                                container.id, "CREATED", "")
                    self._record_operation(operation_id, "REGISTER_CONTAINER", container.id,
                                           result)
                return result
            except sqlite3.IntegrityError as exc:
                if not automatico or intento == 4 or "container_code" not in str(exc):
                    if "container_code" in str(exc):
                        raise ValueError(
                            f"Ya existe un contenedor con el código {container.container_code}"
                        ) from exc
                    raise
        raise RuntimeError("unreachable")

    def update_container(self, *, actor_user_id: str, container_id: str, operation_id: str,
                         tare_weight=None, capacity_weight=None, serial_number=None,
                         current_location_id=None) -> None:
        """Logística → Contenedores: datos editables (tara, capacidad, serie,
        ubicación). Auditado."""
        self._auth.require(actor_user_id, LogisticsPermissions.CONTAINER_MANAGE)
        if self._operation_result(operation_id) is not None:
            return
        container = self._required_container(container_id)
        container.update_details(tare_weight=tare_weight, capacity_weight=capacity_weight,
                                 serial_number=serial_number,
                                 current_location_id=current_location_id)
        with self._connection:
            self._repo.save_container(container)
            self._audit(actor_user_id, operation_id, "PhysicalContainer", container.id,
                        "UPDATED", "")
            self._record_operation(operation_id, "UPDATE_CONTAINER", container.id,
                                   {"container_id": container.id})

    def set_container_status(self, *, actor_user_id: str, container_id: str, status,
                             reason: str, operation_id: str) -> None:
        """Limpieza, mantenimiento, cuarentena, baja o disponible. No mientras
        el contenedor viaja en un embarque activo."""
        self._auth.require(actor_user_id, LogisticsPermissions.CONTAINER_MANAGE)
        if self._operation_result(operation_id) is not None:
            return
        if not (reason or "").strip():
            raise ValueError("Captura el motivo del cambio de estado")
        if self._repo.container_in_active_shipment(container_id):
            raise ValueError("El contenedor está en un embarque activo: libéralo del embarque "
                             "antes de cambiar su estado")
        container = self._required_container(container_id)
        anterior = container.status.value
        container.set_operational_status(status)
        with self._connection:
            self._repo.save_container(container)
            self._audit(actor_user_id, operation_id, "PhysicalContainer", container.id,
                        f"STATUS {anterior}->{container.status.value}", reason.strip())
            self._record_operation(operation_id, "SET_CONTAINER_STATUS", container.id,
                                   {"container_id": container.id})

    def create_shipment(self, *, actor_user_id: str,
                        shipment: LogisticsShipment) -> LogisticsShipment:
        self._auth.require(actor_user_id, LogisticsPermissions.SHIPMENT_CREATE)
        existing = self._repo.get_shipment_by_operation(shipment.operation_id)
        if existing:
            return existing
        with self._connection:
            self._repo.save_shipment(shipment)
            self._event("LOGISTICS_SHIPMENT_CREATED", shipment.id,
                        shipment.operation_id, {"shipment_id": shipment.id})
        return shipment

    def attach_container(self, *, actor_user_id: str, shipment_id: str,
                         container_id: str, operation_id: str,
                         parent_node_id: str | None = None,
                         node_id: str | None = None):
        self._auth.require(actor_user_id, LogisticsPermissions.CONTAINER_ATTACH)
        shipment = self._required_shipment(shipment_id)
        existing = next((node for node in shipment.nodes
                         if node.operation_id == operation_id), None)
        if existing:
            return existing
        container = self._required_container(container_id)
        if self._repo.container_in_active_shipment(container_id):
            raise ValueError("El contenedor ya pertenece a un embarque activo")
        ctype = self._repo.get_type(container.container_type_id)
        parent_type = compatibility = None
        if parent_node_id:
            parent = shipment.node(parent_node_id)
            parent_container = self._required_container(parent.container_id)
            parent_type = self._repo.get_type(parent_container.container_type_id)
            compatibility = self._repo.get_compatibility(parent_type.id, ctype.id)
        node = shipment.attach_container(
            container=container, container_type=ctype, actor_user_id=actor_user_id,
            operation_id=operation_id, parent_node_id=parent_node_id,
            parent_type=parent_type, compatibility=compatibility, node_id=node_id)
        shipment.touch()
        container.status = ContainerStatus.LOADING
        container.current_custodian_id = actor_user_id
        with self._connection:
            self._repo.save_container(container)
            self._repo.save_shipment(shipment)
            self._custody(container, actor_user_id, CustodyAction.ASSIGNED,
                          operation_id, "Asignado a embarque")
        return node

    def assign_content(self, *, actor_user_id: str, shipment_id: str,
                       assignment: ShipmentContentAssignment) -> ShipmentContentAssignment:
        self._auth.require(actor_user_id, LogisticsPermissions.CONTAINER_ATTACH)
        shipment = self._required_shipment(shipment_id)
        node = shipment.node(assignment.shipment_node_id)
        container = self._required_container(node.container_id)
        ctype = self._repo.get_type(container.container_type_id)
        shipment.assign_content(assignment, container_type=ctype)
        shipment.touch()
        with self._connection:
            self._repo.save_shipment(shipment)
        return assignment

    def move_node(self, *, actor_user_id: str, shipment_id: str, node_id: str,
                  new_parent_node_id: str | None, operation_id: str,
                  reason: str) -> None:
        self._auth.require(actor_user_id, LogisticsPermissions.CONTAINER_MOVE)
        if not reason.strip():
            raise ValueError("El movimiento requiere motivo")
        if self._connection.execute(
                "SELECT 1 FROM logistics_node_movements WHERE operation_id=?",
                (operation_id,)).fetchone():
            return
        shipment = self._required_shipment(shipment_id)
        node = shipment.node(node_id)
        old_parent = node.parent_node_id
        if new_parent_node_id:
            parent = shipment.node(new_parent_node_id)
            parent_container = self._required_container(parent.container_id)
            child_container = self._required_container(node.container_id)
            compatibility = self._repo.get_compatibility(
                parent_container.container_type_id, child_container.container_type_id)
            if compatibility is None or not compatibility.allowed:
                raise ValueError("Tipos de contenedor incompatibles")
        shipment.move_node(node_id, new_parent_node_id,
                           actor_user_id=actor_user_id, operation_id=operation_id)
        shipment.touch()
        with self._connection:
            self._repo.save_shipment(shipment)
            self._connection.execute(
                "INSERT INTO logistics_node_movements VALUES (?,?,?,?,?,?,?,?,?)",
                (new_uuid(), shipment_id, node_id, old_parent, new_parent_node_id,
                 actor_user_id, reason.strip(), operation_id, utcnow()))

    def seal(self, *, actor_user_id: str, shipment_id: str, node_id: str,
             seal_code: str, seal_type: str, operation_id: str):
        self._auth.require(actor_user_id, LogisticsPermissions.CONTAINER_SEAL)
        previous = self._operation_result(operation_id)
        if previous is not None:
            shipment = self._required_shipment(shipment_id)
            return next(item for item in shipment.seals
                        if item.id == previous["seal_id"])
        shipment = self._required_shipment(shipment_id)
        containers = {node.container_id: self._required_container(node.container_id)
                      for node in shipment.nodes}
        types = {container.container_type_id: self._repo.get_type(container.container_type_id)
                 for container in containers.values()}
        seal = shipment.seal_node(
            node_id, seal_code=seal_code, seal_type=seal_type,
            actor_user_id=actor_user_id, operation_id=operation_id,
            containers=containers, container_types=types)
        shipment.touch()
        with self._connection:
            for container in containers.values():
                self._repo.save_container(container)
            self._repo.save_shipment(shipment)
            self._record_operation(operation_id, "SEAL_CONTAINER", seal.id,
                                   {"seal_id": seal.id})
        return seal

    def dispatch(self, *, actor_user_id: str, shipment_id: str,
                 operation_id: str) -> LogisticsShipment:
        self._auth.require(actor_user_id, LogisticsPermissions.SHIPMENT_DISPATCH)
        if self._operation_result(operation_id) is not None:
            return self._required_shipment(shipment_id)
        shipment = self._required_shipment(shipment_id)
        shipment.dispatch()
        shipment.touch()
        with self._connection:
            self._repo.save_shipment(shipment)
            # Quién despachó: la recepción lo compara (segregación de funciones).
            self._audit(actor_user_id, operation_id, "LogisticsShipment", shipment.id,
                        "DISPATCHED", "")
            self._event("LOGISTICS_SHIPMENT_DISPATCHED", shipment.id, operation_id,
                        {"shipment_id": shipment.id})
            self._record_operation(operation_id, "DISPATCH_SHIPMENT", shipment.id,
                                   {"shipment_id": shipment.id})
        return shipment

    # ── lectura (para coordinadores; nunca el repositorio directo) ────────────
    def get_shipment(self, shipment_id: str):
        return self._repo.get_shipment(shipment_id)

    def get_container(self, container_id: str):
        return self._repo.get_container(container_id)

    def get_type(self, type_id: str):
        return self._repo.get_type(type_id)

    def next_container_code(self, prefix: str) -> str:
        return self._repo.next_container_code(prefix)

    def find_container(self, reference: str) -> PhysicalContainer | None:
        """Por el código impreso o por el QR escaneado (lector de escritorio o
        cámara del teléfono). Un QR rotado/ajeno es error, no «no existe»."""
        ref = (reference or "").strip()
        if not ref:
            return None
        if self._qr.looks_like_token(ref):
            return self._repo.get_container(self.resolve_qr(ref))
        return self._repo.get_container_by_code(ref)

    def resolve_qr(self, token: str) -> str:
        """Etiqueta VIGENTE → id. Compara con la firma guardada (válido desde
        cualquier usuario o proceso del equipo, p. ej. el servicio de la API)."""
        container_id, _version, _signature = self._qr.parse(token)
        container = self._repo.get_container(container_id)
        if container is None or not self._qr.matches(token, container):
            from backend.domain.logistics.exceptions import LogisticsDomainError
            raise LogisticsDomainError("QR revocado o de otro contenedor")
        return container_id

    # ── llegada y recepción (§28) ─────────────────────────────────────────────
    def mark_in_transit(self, *, actor_user_id: str, shipment_id: str,
                        operation_id: str) -> LogisticsShipment:
        self._auth.require(actor_user_id, LogisticsPermissions.SHIPMENT_DISPATCH)
        if self._operation_result(operation_id) is not None:
            return self._required_shipment(shipment_id)
        shipment = self._required_shipment(shipment_id)
        shipment.start_transit()
        shipment.touch()
        containers = [self._required_container(n.container_id) for n in shipment.nodes
                      if not n.detached_at]
        with self._connection:
            for container in containers:
                container.status = ContainerStatus.IN_TRANSIT
                self._repo.save_container(container)
            self._repo.save_shipment(shipment)
            self._event("LOGISTICS_SHIPMENT_IN_TRANSIT", shipment.id, operation_id,
                        {"shipment_id": shipment.id})
            self._record_operation(operation_id, "SHIPMENT_IN_TRANSIT", shipment.id,
                                   {"shipment_id": shipment.id})
        return shipment

    def register_arrival(self, *, actor_user_id: str, shipment_id: str,
                         operation_id: str) -> LogisticsShipment:
        self._auth.require(actor_user_id, LogisticsPermissions.SHIPMENT_RECEIVE)
        if self._operation_result(operation_id) is not None:
            return self._required_shipment(shipment_id)
        self._require_receiver_is_not_dispatcher(actor_user_id, shipment_id)
        shipment = self._required_shipment(shipment_id)
        shipment.arrive()
        shipment.touch()
        containers = [self._required_container(n.container_id) for n in shipment.nodes
                      if not n.detached_at]
        with self._connection:
            for container in containers:
                container.status = ContainerStatus.AT_DESTINATION
                self._repo.save_container(container)
            self._repo.save_shipment(shipment)
            self._event("LOGISTICS_SHIPMENT_ARRIVED", shipment.id, operation_id,
                        {"shipment_id": shipment.id})
            self._record_operation(operation_id, "SHIPMENT_ARRIVED", shipment.id,
                                   {"shipment_id": shipment.id})
        return shipment

    def record_count(self, *, actor_user_id: str, shipment_id: str, content_id: str,
                     received_quantity, accepted_quantity, received_net_weight="0",
                     piece_count=None, lot_number=None, expiration_date=None,
                     temperature=None, notes: str = "", operation_id: str) -> None:
        """Conteo/pesaje de UN contenido al llegar. Repetirlo lo corrige (una fila
        por contenido); lo aceptado nunca excede lo recibido."""
        from decimal import Decimal
        self._auth.require(actor_user_id, LogisticsPermissions.SHIPMENT_RECEIVE)
        shipment = self._required_shipment(shipment_id)
        if not any(c.id == content_id for c in shipment.contents):
            raise ValueError("El contenido no pertenece al embarque")
        received, accepted = Decimal(str(received_quantity)), Decimal(str(accepted_quantity))
        if received < 0 or accepted < 0 or accepted > received:
            raise ValueError("Lo aceptado no puede exceder lo recibido")
        shipment.start_receiving()
        shipment.touch()
        with self._connection:
            self._repo.save_shipment(shipment)
            self._connection.execute(
                "INSERT INTO logistics_arrival_counts (id, shipment_id, content_id,"
                " received_quantity, received_net_weight, accepted_quantity, rejected_quantity,"
                " piece_count, lot_number, expiration_date, temperature, notes,"
                " counted_by_user_id, counted_at, operation_id)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(content_id) DO UPDATE SET"
                " received_quantity=excluded.received_quantity,"
                " received_net_weight=excluded.received_net_weight,"
                " accepted_quantity=excluded.accepted_quantity,"
                " rejected_quantity=excluded.rejected_quantity,"
                " piece_count=excluded.piece_count, lot_number=excluded.lot_number,"
                " expiration_date=excluded.expiration_date, temperature=excluded.temperature,"
                " notes=excluded.notes, counted_by_user_id=excluded.counted_by_user_id,"
                " counted_at=excluded.counted_at, operation_id=excluded.operation_id",
                (new_uuid(), shipment_id, content_id, str(received),
                 str(Decimal(str(received_net_weight or "0"))), str(accepted),
                 str(received - accepted), piece_count, lot_number or None,
                 str(expiration_date) if expiration_date else None,
                 str(temperature) if temperature not in (None, "") else None,
                 notes or "", actor_user_id, utcnow(), operation_id))
            self._audit(actor_user_id, operation_id, "ShipmentContent", content_id,
                        "COUNTED", notes or "")

    def arrival_counts(self, shipment_id: str) -> dict[str, dict]:
        cursor = self._connection.execute(
            "SELECT * FROM logistics_arrival_counts WHERE shipment_id=?", (shipment_id,))
        columns = [c[0] for c in cursor.description]
        return {row[2]: dict(zip(columns, row)) for row in cursor.fetchall()}

    def close_shipment(self, *, actor_user_id: str, shipment_id: str,
                       operation_id: str) -> LogisticsShipment:
        """Cierra el embarque recibido y libera sus contenedores: los propios
        quedan DISPONIBLES para el siguiente viaje; los del proveedor, devueltos."""
        from backend.domain.logistics.enums import ContainerOwnerType
        self._auth.require(actor_user_id, LogisticsPermissions.SHIPMENT_RECEIVE)
        if self._operation_result(operation_id) is not None:
            return self._required_shipment(shipment_id)
        shipment = self._required_shipment(shipment_id)
        shipment.close()
        shipment.touch()
        with self._connection:
            for node in shipment.nodes:
                if node.detached_at:
                    continue
                container = self._required_container(node.container_id)
                supplier_owned = container.owner_type is ContainerOwnerType.SUPPLIER
                container.release(return_to_supplier=supplier_owned)
                if not supplier_owned:
                    container.status = ContainerStatus.AVAILABLE
                    container.current_custodian_id = None
                self._repo.save_container(container)
                # `logistics_custody_events.operation_id` es ÚNICO: cada evento
                # lleva su propio UUIDv7. El reintento lo cubre la operación del
                # cierre (`logistics_operations`), que es atómica con estos
                # eventos — no se deriva identidad concatenando (integración
                # Logística 32cfbf).
                self._custody(container, actor_user_id,
                              CustodyAction.RETURNED if supplier_owned else CustodyAction.RELEASED,
                              new_uuid(), "Embarque recibido y cerrado")
            self._repo.save_shipment(shipment)
            self._event("LOGISTICS_SHIPMENT_CLOSED", shipment.id, operation_id,
                        {"shipment_id": shipment.id})
            self._record_operation(operation_id, "SHIPMENT_CLOSED", shipment.id,
                                   {"shipment_id": shipment.id})
        return shipment

    def authorize_loading_variance(self, *, actor_user_id: str, shipment_id: str,
                                   source_line_id: str, reason: str,
                                   operation_id: str) -> None:
        self._auth.require(actor_user_id, LogisticsPermissions.SHIPMENT_OVERRIDE)
        if not reason.strip():
            raise ValueError("La autorización requiere motivo")
        self._required_shipment(shipment_id)
        with self._connection:
            self._connection.execute(
                "INSERT INTO logistics_loading_authorizations"
                " (id,shipment_id,source_line_id,authorized_by_user_id,reason,operation_id,created_at)"
                " VALUES (?,?,?,?,?,?,?) ON CONFLICT(shipment_id,source_line_id) DO NOTHING",
                (new_uuid(), shipment_id, source_line_id, actor_user_id, reason.strip(),
                 operation_id, utcnow()))
            self._audit(actor_user_id, operation_id, "LoadingVariance", source_line_id,
                        "AUTHORIZED", reason.strip())

    def break_seal(self, *, actor_user_id: str, shipment_id: str, seal_id: str,
                   operation_id: str, reason: str) -> None:
        self._auth.require(actor_user_id, LogisticsPermissions.CONTAINER_SEAL)
        if self._operation_result(operation_id) is not None:
            return
        shipment = self._required_shipment(shipment_id)
        seal = next((item for item in shipment.seals if item.id == seal_id), None)
        if seal is None:
            raise LookupError("Sello inexistente")
        seal.break_seal(actor_user_id=actor_user_id, reason=reason)
        shipment.node(seal.shipment_node_id).status = shipment.node(
            seal.shipment_node_id).status.OPENED
        shipment.touch()
        with self._connection:
            self._repo.save_shipment(shipment)
            self._audit(actor_user_id, operation_id, "ContainerSeal", seal.id,
                        "BROKEN", reason)
            self._record_operation(operation_id, "BREAK_SEAL", seal.id,
                                   {"seal_id": seal.id})

    def mark_damaged_or_lost(self, *, actor_user_id: str, container_id: str,
                             operation_id: str, lost: bool, reason: str) -> None:
        self._auth.require(actor_user_id, LogisticsPermissions.CONTAINER_MANAGE)
        if self._operation_result(operation_id) is not None:
            return
        container = self._required_container(container_id)
        container.mark_lost() if lost else container.mark_damaged()
        with self._connection:
            self._repo.save_container(container)
            active = self._connection.execute(
                "SELECT shipment_id,id FROM logistics_shipment_nodes WHERE container_id=?"
                " AND detached_at IS NULL ORDER BY attached_at DESC LIMIT 1",
                (container_id,)).fetchone()
            if active:
                shipment = self._required_shipment(active[0])
                shipment.node(active[1]).status = (
                    shipment.node(active[1]).status.MISSING if lost
                    else shipment.node(active[1]).status.DAMAGED)
                shipment.touch()
                self._repo.save_shipment(shipment)
            self._custody(container, actor_user_id,
                          CustodyAction.LOST if lost else CustodyAction.DAMAGED,
                          operation_id, reason)
            self._record_operation(operation_id, "REPORT_CONTAINER_INCIDENT", container.id,
                                   {"container_id": container.id})

    def release_container(self, *, actor_user_id: str, container_id: str,
                          operation_id: str, return_to_supplier: bool,
                          reason: str) -> None:
        self._auth.require(actor_user_id, LogisticsPermissions.CONTAINER_RELEASE)
        if self._operation_result(operation_id) is not None:
            return
        container = self._required_container(container_id)
        old = container.current_custodian_id
        container.release(return_to_supplier=return_to_supplier)
        with self._connection:
            self._repo.save_container(container)
            active = self._connection.execute(
                "SELECT shipment_id,id FROM logistics_shipment_nodes WHERE container_id=?"
                " AND detached_at IS NULL ORDER BY attached_at DESC LIMIT 1",
                (container_id,)).fetchone()
            if active:
                shipment = self._required_shipment(active[0])
                node = shipment.node(active[1])
                node.status = node.status.RELEASED
                node.detached_at = utcnow()
                node.detached_by_user_id = actor_user_id
                shipment.touch()
                self._repo.save_shipment(shipment)
            self._custody(container, actor_user_id,
                          CustodyAction.RETURNED if return_to_supplier else CustodyAction.RELEASED,
                          operation_id, reason, from_custodian=old)
            self._record_operation(operation_id, "RELEASE_CONTAINER", container.id,
                                   {"container_id": container.id})

    def label_token(self, container_id: str) -> str:
        """Contenido del QR VIGENTE (firma guardada). Un contenedor anterior a
        la firma guardada recibe la suya aquí, una sola vez."""
        container = self._required_container(container_id)
        compacta = self._qr.is_compact_signature(container.qr_signature)
        if container.qr_signature and (compacta or self._label_printed(container_id)):
            return self._qr.token_for(container)
        # Sin firma, o con la firma larga anterior y SIN etiqueta impresa: se
        # emite la compacta (nadie tiene todavía la anterior en papel).
        token = self._qr.issue(container)
        with self._connection:
            self._repo.save_container(container)
        return token

    def _label_printed(self, container_id: str) -> bool:
        return self._connection.execute(
            "SELECT 1 FROM logistics_container_labels WHERE container_id=? LIMIT 1",
            (container_id,)).fetchone() is not None

    def create_label_and_print(self, *, actor_user_id: str, container_id: str,
                               printer_id: str, operation_id: str,
                               shipment_id: str | None = None, copies: int = 1,
                               reprint_reason: str | None = None,
                               printer=None) -> PrintJob:
        """Registra la etiqueta y su trabajo de impresión (auditoría y
        reimpresiones) y lo entrega a `printer` (por omisión, la impresora
        térmica enrutada; el PDF pasa un destino que sólo lo registra)."""
        self._auth.require(actor_user_id, LogisticsPermissions.LABEL_PRINT)
        gateway = printer or self._printer
        previous = self._operation_result(operation_id)
        if previous is not None:
            row = self._connection.execute(
                "SELECT * FROM logistics_print_jobs WHERE id=?",
                (previous["print_job_id"],)).fetchone()
            return PrintJob(*row) if row else None
        if gateway is None:
            raise RuntimeError("PrinterGateway no configurado")
        existing_row = self._connection.execute(
            "SELECT * FROM logistics_print_jobs WHERE operation_id=?", (operation_id,)).fetchone()
        if existing_row:
            existing = PrintJob(*existing_row)
            if existing.status == "COMPLETED":
                return existing
            token = self._connection.execute(
                "SELECT token FROM logistics_container_labels WHERE id=?",
                (existing.label_id,)).fetchone()[0]
            return self._submit_print(existing, token, gateway)
        container = self._required_container(container_id)
        token = self.label_token(container_id)
        label = ContainerLabel(new_uuid(), container.id, shipment_id,
                               "SHIPMENT" if shipment_id else "PERMANENT_QR",
                               container.qr_version, token, "ACTIVE", utcnow(), operation_id)
        job = PrintJob(new_uuid(), label.id, printer_id, copies, "PENDING",
                       operation_id, actor_user_id, utcnow(), reprint_reason)
        with self._connection:
            self._connection.execute(
                "INSERT INTO logistics_container_labels VALUES (?,?,?,?,?,?,?,?,?)",
                (label.id, label.container_id, label.shipment_id, label.label_type,
                 label.version, label.token, label.status, label.created_at, label.operation_id))
            self._connection.execute(
                "INSERT INTO logistics_print_jobs VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (job.id, job.label_id, job.printer_id, job.copies, job.status,
                 job.operation_id, job.requested_by_user_id, job.requested_at,
                 job.reprint_reason, job.completed_at, job.error))
        return self._submit_print(job, token, gateway)

    def _required_shipment(self, shipment_id: str) -> LogisticsShipment:
        item = self._repo.get_shipment(shipment_id)
        if item is None:
            raise LookupError("Embarque inexistente")
        return item

    def _required_container(self, container_id: str) -> PhysicalContainer:
        item = self._repo.get_container(container_id)
        if item is None:
            raise LookupError("Contenedor inexistente")
        return item

    def _custody(self, container, actor, action, operation, reason,
                 from_custodian=None) -> None:
        event = ContainerCustodyEvent(
            new_uuid(), container.id, action, from_custodian,
            container.current_custodian_id, container.current_location_id,
            actor, reason, operation, utcnow())
        self._connection.execute(
            "INSERT INTO logistics_custody_events VALUES (?,?,?,?,?,?,?,?,?,?)",
            (event.id, event.container_id, event.action.value, event.from_custodian_id,
             event.to_custodian_id, event.location_id, event.actor_user_id, event.reason,
             event.operation_id, event.occurred_at))

    def _require_receiver_is_not_dispatcher(self, actor_user_id: str, shipment_id: str) -> None:
        """Segregación (integración Logística 32cfbf): quien despachó el embarque
        no registra su llegada, salvo con `LOGISTICA.embarque.forzar`. Los
        embarques despachados antes de registrar al despachador no se bloquean."""
        fila = self._connection.execute(
            "SELECT actor_user_id FROM logistics_audit_log WHERE entity_id=?"
            " AND action='DISPATCHED' ORDER BY occurred_at DESC LIMIT 1",
            (shipment_id,)).fetchone()
        if fila is None or str(fila[0]) != str(actor_user_id):
            return
        if self._auth.allows(actor_user_id, LogisticsPermissions.SHIPMENT_OVERRIDE):
            return
        from backend.application.logistics.authorization import (
            LogisticsPermissionDeniedError,
        )
        raise LogisticsPermissionDeniedError(
            "Quien despachó el embarque no puede registrar su llegada: debe recibirlo "
            "otra persona (o alguien con permiso para forzar).")

    def _audit(self, actor, operation, entity_type, entity_id, action, reason) -> None:
        self._connection.execute(
            "INSERT INTO logistics_audit_log VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (new_uuid(), actor, None, None, None, None, operation, entity_type,
             entity_id, action, None, None, reason, utcnow(), new_uuid()))

    def _event(self, name, aggregate_id, operation_id, payload) -> None:
        event_id = new_uuid()
        correlation_id = new_uuid()
        self._connection.execute(
            "INSERT INTO logistics_outbox VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (new_uuid(), event_id, name, aggregate_id, operation_id, None,
             correlation_id, json.dumps(payload), "PENDING", 0, utcnow(), None, None))

    def _operation_result(self, operation_id: str):
        row = self._connection.execute(
            "SELECT result_json FROM logistics_operations WHERE operation_id=?",
            (operation_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def _record_operation(self, operation_id: str, operation_type: str,
                          entity_id: str, result: dict) -> None:
        self._connection.execute(
            "INSERT INTO logistics_operations VALUES (?,?,?,?,?)",
            (operation_id, operation_type, entity_id, json.dumps(result), utcnow()))

    def _submit_print(self, job: PrintJob, token: str, gateway=None) -> PrintJob:
        try:
            (gateway or self._printer).submit(job, token)
        except Exception as exc:
            job.status = "ERROR"
            job.error = str(exc)
            with self._connection:
                self._connection.execute(
                    "UPDATE logistics_print_jobs SET status=?,error=? WHERE id=?",
                    (job.status, job.error, job.id))
            raise
        job.status = "COMPLETED"
        job.completed_at = utcnow()
        job.error = None
        with self._connection:
            self._connection.execute(
                "UPDATE logistics_print_jobs SET status=?,completed_at=?,error=NULL WHERE id=?",
                (job.status, job.completed_at, job.id))
            if self._operation_result(job.operation_id) is None:
                self._record_operation(job.operation_id, "PRINT_LABEL", job.id,
                                       {"print_job_id": job.id})
        return job
