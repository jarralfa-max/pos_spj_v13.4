"""Aggregates and entities owned exclusively by Logistics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal

from backend.domain.logistics.enums import (
    ContainerCategory, ContainerOwnerType, ContainerStatus, CustodyAction,
    ShipmentNodeStatus, ShipmentStatus, SourceDocumentType,
)
from backend.domain.logistics.exceptions import (
    ContainerCapacityError, InvalidContainerHierarchyError, InvalidLogisticsStateError,
    LogisticsDomainError,
)
from backend.shared.ids import new_uuid


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def decimal(value) -> Decimal:
    if isinstance(value, float):
        raise LogisticsDomainError("No se permite float en cantidades, pesos o costos")
    return Decimal(str(value))


@dataclass(frozen=True, slots=True)
class ContainerType:
    id: str
    code: str
    name: str
    category: ContainerCategory
    reusable: bool
    requires_permanent_qr: bool
    allows_children: bool
    maximum_children: int | None
    maximum_depth_below: int
    default_tare_weight: Decimal
    maximum_gross_weight: Decimal | None
    maximum_net_weight: Decimal | None
    maximum_volume: Decimal | None
    stackable: bool
    seal_required: bool
    temperature_controlled: bool
    active: bool = True
    version: int = 1

    @classmethod
    def create(cls, *, code: str, name: str, category: ContainerCategory,
               reusable: bool = True, requires_permanent_qr: bool = True,
               allows_children: bool = False, maximum_children: int | None = None,
               maximum_depth_below: int = 0, default_tare_weight="0",
               maximum_gross_weight=None, maximum_net_weight=None,
               maximum_volume=None, stackable: bool = False,
               seal_required: bool = False,
               temperature_controlled: bool = False) -> "ContainerType":
        if not code.strip() or not name.strip() or maximum_depth_below < 0:
            raise LogisticsDomainError("Tipo de contenedor inválido")
        return cls(
            new_uuid(), code.strip().upper(), name.strip(), category, reusable,
            requires_permanent_qr, allows_children, maximum_children,
            maximum_depth_below, decimal(default_tare_weight),
            decimal(maximum_gross_weight) if maximum_gross_weight is not None else None,
            decimal(maximum_net_weight) if maximum_net_weight is not None else None,
            decimal(maximum_volume) if maximum_volume is not None else None,
            stackable, seal_required, temperature_controlled)


@dataclass(frozen=True, slots=True)
class ContainerTypeCompatibility:
    id: str
    parent_type_id: str
    child_type_id: str
    allowed: bool
    maximum_quantity: int | None = None
    conditions: str = ""

    @classmethod
    def create(cls, parent_type_id: str, child_type_id: str, *, allowed: bool,
               maximum_quantity: int | None = None,
               conditions: str = "") -> "ContainerTypeCompatibility":
        if parent_type_id == child_type_id:
            raise LogisticsDomainError("La compatibilidad requiere tipos distintos")
        return cls(new_uuid(), parent_type_id, child_type_id, allowed,
                   maximum_quantity, conditions)


@dataclass(slots=True)
class PhysicalContainer:
    id: str
    container_code: str
    container_type_id: str
    serial_number: str | None
    tare_weight: Decimal
    capacity_weight: Decimal | None
    capacity_volume: Decimal | None
    owner_type: ContainerOwnerType
    owner_supplier_id: str | None
    current_location_id: str | None
    current_custodian_id: str | None
    status: ContainerStatus = ContainerStatus.AVAILABLE
    condition: str = "GOOD"
    qr_version: int = 1
    qr_signature: str | None = None
    created_at: str = field(default_factory=utcnow)
    last_inspection_at: str | None = None
    retired_at: str | None = None

    @classmethod
    def create(cls, *, container_code: str, container_type_id: str,
               owner_type: ContainerOwnerType, tare_weight="0", serial_number=None,
               capacity_weight=None, capacity_volume=None, owner_supplier_id=None,
               current_location_id=None) -> "PhysicalContainer":
        if owner_type is ContainerOwnerType.SUPPLIER and not owner_supplier_id:
            raise LogisticsDomainError("Un contenedor del proveedor requiere supplier_id")
        return cls(new_uuid(), container_code.strip().upper(), container_type_id,
                   serial_number, decimal(tare_weight),
                   decimal(capacity_weight) if capacity_weight is not None else None,
                   decimal(capacity_volume) if capacity_volume is not None else None,
                   owner_type, owner_supplier_id, current_location_id, None)

    def rotate_qr(self) -> None:
        self.qr_version += 1
        self.qr_signature = None

    def mark_damaged(self) -> None:
        self.status = ContainerStatus.DAMAGED
        self.condition = "DAMAGED"

    def mark_lost(self) -> None:
        self.status = ContainerStatus.LOST

    def release(self, *, return_to_supplier: bool = False) -> None:
        if self.status is ContainerStatus.LOST:
            raise InvalidLogisticsStateError("Un contenedor perdido no puede liberarse")
        self.status = ContainerStatus.RELEASED
        self.current_custodian_id = self.owner_supplier_id if return_to_supplier else None


@dataclass(frozen=True, slots=True)
class ShipmentSourceDocument:
    id: str
    shipment_id: str
    source_document_type: SourceDocumentType
    source_document_id: str


@dataclass(slots=True)
class ShipmentContainerNode:
    id: str
    shipment_id: str
    container_id: str
    parent_node_id: str | None
    depth: int
    sequence: int
    position_code: str | None
    status: ShipmentNodeStatus
    attached_at: str
    attached_by_user_id: str
    operation_id: str
    detached_at: str | None = None
    detached_by_user_id: str | None = None


@dataclass(frozen=True, slots=True)
class ShipmentContentAssignment:
    id: str
    shipment_node_id: str
    source_document_type: SourceDocumentType
    source_document_id: str
    source_line_id: str
    product_id: str
    declared_quantity: Decimal
    declared_net_weight: Decimal
    purchase_unit: str
    inventory_unit: str
    conversion_factor: Decimal
    lot_number: str | None
    expiration_date: date | None
    unit_cost: Decimal
    currency_code: str
    temperature: Decimal | None
    notes: str
    operation_id: str

    @classmethod
    def create(cls, *, shipment_node_id: str, source_document_type: SourceDocumentType,
               source_document_id: str, source_line_id: str, product_id: str,
               declared_quantity, declared_net_weight, purchase_unit: str,
               inventory_unit: str, conversion_factor, unit_cost,
               currency_code: str, operation_id: str, lot_number=None,
               expiration_date=None, temperature=None, notes="") -> "ShipmentContentAssignment":
        quantity = decimal(declared_quantity)
        weight = decimal(declared_net_weight)
        if quantity <= 0 or weight < 0:
            raise LogisticsDomainError("Contenido declarado inválido")
        return cls(new_uuid(), shipment_node_id, source_document_type,
                   source_document_id, source_line_id, product_id, quantity, weight,
                   purchase_unit, inventory_unit, decimal(conversion_factor),
                   lot_number, expiration_date, decimal(unit_cost), currency_code,
                   decimal(temperature) if temperature is not None else None,
                   notes, operation_id)


@dataclass(slots=True)
class ContainerSeal:
    id: str
    seal_code: str
    seal_type: str
    shipment_node_id: str
    applied_by: str
    applied_at: str
    operation_id: str
    broken_by: str | None = None
    broken_at: str | None = None
    break_reason: str | None = None
    photo_id: str | None = None

    def break_seal(self, *, actor_user_id: str, reason: str) -> None:
        if self.broken_at or not reason.strip():
            raise InvalidLogisticsStateError("Ruptura de sello inválida")
        self.broken_by = actor_user_id
        self.broken_at = utcnow()
        self.break_reason = reason.strip()


@dataclass(frozen=True, slots=True)
class ContainerLabel:
    id: str
    container_id: str
    shipment_id: str | None
    label_type: str
    version: int
    token: str
    status: str
    created_at: str
    operation_id: str


@dataclass(slots=True)
class PrintJob:
    id: str
    label_id: str
    printer_id: str
    copies: int
    status: str
    operation_id: str
    requested_by_user_id: str
    requested_at: str
    reprint_reason: str | None = None
    completed_at: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ContainerCustodyEvent:
    id: str
    container_id: str
    action: CustodyAction
    from_custodian_id: str | None
    to_custodian_id: str | None
    location_id: str | None
    actor_user_id: str
    reason: str
    operation_id: str
    occurred_at: str


@dataclass(slots=True)
class LogisticsShipment:
    id: str
    shipment_number: str
    origin_type: str
    origin_supplier_id: str | None
    origin_location: str
    destination_branch_id: str
    destination_warehouse_id: str
    buyer_user_id: str
    vehicle_id: str | None
    status: ShipmentStatus
    operation_id: str
    version: int = 0
    sources: list[ShipmentSourceDocument] = field(default_factory=list)
    nodes: list[ShipmentContainerNode] = field(default_factory=list)
    contents: list[ShipmentContentAssignment] = field(default_factory=list)
    seals: list[ContainerSeal] = field(default_factory=list)
    started_at: str | None = None
    sealed_at: str | None = None
    dispatched_at: str | None = None
    arrived_at: str | None = None
    closed_at: str | None = None

    @classmethod
    def create(cls, *, shipment_number: str, origin_type: str,
               origin_location: str, destination_branch_id: str,
               destination_warehouse_id: str, buyer_user_id: str,
               operation_id: str, origin_supplier_id=None,
               vehicle_id=None, shipment_id: str | None = None) -> "LogisticsShipment":
        return cls(shipment_id or new_uuid(), shipment_number, origin_type, origin_supplier_id,
                   origin_location, destination_branch_id, destination_warehouse_id,
                   buyer_user_id, vehicle_id, ShipmentStatus.DRAFT, operation_id)

    def add_source(self, source_type: SourceDocumentType, source_id: str) -> None:
        if any(s.source_document_type is source_type and
               s.source_document_id == source_id for s in self.sources):
            return
        self.sources.append(ShipmentSourceDocument(new_uuid(), self.id, source_type, source_id))

    def touch(self) -> None:
        self.version += 1

    def attach_container(self, *, container: PhysicalContainer,
                         container_type: ContainerType, actor_user_id: str,
                         operation_id: str, parent_node_id: str | None = None,
                         parent_type: ContainerType | None = None,
                         compatibility: ContainerTypeCompatibility | None = None,
                         position_code: str | None = None,
                         node_id: str | None = None) -> ShipmentContainerNode:
        if self.status not in (ShipmentStatus.DRAFT, ShipmentStatus.LOADING):
            raise InvalidLogisticsStateError("El embarque no admite más contenedores")
        if any(n.container_id == container.id and not n.detached_at for n in self.nodes):
            raise InvalidContainerHierarchyError("El contenedor ya está en el embarque")
        depth = 0
        if parent_node_id:
            parent = self.node(parent_node_id)
            if parent.status is ShipmentNodeStatus.SEALED:
                raise InvalidContainerHierarchyError("No se agregan hijos a un nodo sellado")
            if parent.container_id == container.id:
                raise InvalidContainerHierarchyError("Un contenedor no puede contenerse a sí mismo")
            if parent_type is None or not parent_type.allows_children:
                raise InvalidContainerHierarchyError("El tipo padre no admite hijos")
            if compatibility is None or not compatibility.allowed or \
                    compatibility.parent_type_id != parent_type.id or \
                    compatibility.child_type_id != container_type.id:
                raise InvalidContainerHierarchyError("Tipos de contenedor incompatibles")
            children = [n for n in self.nodes if n.parent_node_id == parent.id and not n.detached_at]
            maximum = compatibility.maximum_quantity or parent_type.maximum_children
            if maximum is not None and len(children) >= maximum:
                raise InvalidContainerHierarchyError("Se excede el máximo de hijos")
            depth = parent.depth + 1
            if depth > parent_type.maximum_depth_below + parent.depth:
                raise InvalidContainerHierarchyError("Se excede la profundidad permitida")
        node = ShipmentContainerNode(
            node_id or new_uuid(), self.id, container.id, parent_node_id, depth,
            len(self.nodes) + 1, position_code, ShipmentNodeStatus.LOADING,
            utcnow(), actor_user_id, operation_id)
        self.nodes.append(node)
        self.status = ShipmentStatus.LOADING
        return node

    def move_node(self, node_id: str, new_parent_node_id: str | None,
                  *, actor_user_id: str, operation_id: str) -> None:
        node = self.node(node_id)
        if node.status is ShipmentNodeStatus.SEALED:
            raise InvalidContainerHierarchyError("No se mueve un nodo sellado")
        cursor = new_parent_node_id
        while cursor:
            if cursor == node_id:
                raise InvalidContainerHierarchyError("La operación produciría un ciclo")
            cursor = self.node(cursor).parent_node_id
        node.parent_node_id = new_parent_node_id
        node.depth = self.node(new_parent_node_id).depth + 1 if new_parent_node_id else 0
        node.attached_by_user_id = actor_user_id
        node.operation_id = operation_id

    def assign_content(self, assignment: ShipmentContentAssignment,
                       *, container_type: ContainerType) -> None:
        node = self.node(assignment.shipment_node_id)
        if node.status is ShipmentNodeStatus.SEALED:
            raise InvalidLogisticsStateError("No se carga contenido en un nodo sellado")
        if any(c.operation_id == assignment.operation_id for c in self.contents):
            return
        related_nodes = self._ancestors(node.id) | self._descendants(node.id)
        if any(c.shipment_node_id in related_nodes and
               c.source_line_id == assignment.source_line_id and
               c.product_id == assignment.product_id for c in self.contents):
            raise LogisticsDomainError(
                "El mismo contenido no puede declararse en padre y descendiente")
        projected = self.direct_net_weight(node.id) + assignment.declared_net_weight
        if container_type.maximum_net_weight is not None and projected > container_type.maximum_net_weight:
            raise ContainerCapacityError("Se excede el peso neto del contenedor")
        self.contents.append(assignment)

    def _ancestors(self, node_id: str) -> set[str]:
        result: set[str] = set()
        cursor = self.node(node_id).parent_node_id
        while cursor:
            result.add(cursor)
            cursor = self.node(cursor).parent_node_id
        return result

    def _descendants(self, node_id: str) -> set[str]:
        direct = {node.id for node in self.nodes
                  if node.parent_node_id == node_id and not node.detached_at}
        return direct | set().union(*(self._descendants(child) for child in direct)) \
            if direct else set()

    def direct_net_weight(self, node_id: str) -> Decimal:
        return sum((c.declared_net_weight for c in self.contents
                    if c.shipment_node_id == node_id), Decimal("0"))

    def aggregate_net_weight(self, node_id: str) -> Decimal:
        children = [n for n in self.nodes if n.parent_node_id == node_id and not n.detached_at]
        return self.direct_net_weight(node_id) + sum(
            (self.aggregate_net_weight(child.id) for child in children), Decimal("0"))

    def gross_weight(self, node_id: str, containers: dict[str, PhysicalContainer]) -> Decimal:
        node = self.node(node_id)
        children = [n for n in self.nodes if n.parent_node_id == node_id and not n.detached_at]
        return (containers[node.container_id].tare_weight + self.direct_net_weight(node_id)
                + sum((self.gross_weight(child.id, containers) for child in children),
                      Decimal("0")))

    def seal_node(self, node_id: str, *, seal_code: str, seal_type: str,
                  actor_user_id: str, operation_id: str,
                  containers: dict[str, PhysicalContainer],
                  container_types: dict[str, ContainerType]) -> ContainerSeal:
        node = self.node(node_id)
        children = [n for n in self.nodes if n.parent_node_id == node.id and not n.detached_at]
        if any(child.status is not ShipmentNodeStatus.SEALED for child in children):
            raise InvalidLogisticsStateError("Todos los hijos deben estar sellados")
        container = containers[node.container_id]
        ctype = container_types[container.container_type_id]
        gross = self.gross_weight(node.id, containers)
        if ctype.maximum_gross_weight is not None and gross > ctype.maximum_gross_weight:
            raise ContainerCapacityError("Se excede el peso bruto")
        seal = ContainerSeal(new_uuid(), seal_code, seal_type, node.id,
                             actor_user_id, utcnow(), operation_id)
        self.seals.append(seal)
        node.status = ShipmentNodeStatus.SEALED
        container.status = ContainerStatus.SEALED
        return seal

    def dispatch(self) -> None:
        roots = [n for n in self.nodes if n.parent_node_id is None and not n.detached_at]
        if not roots or any(n.status is not ShipmentNodeStatus.SEALED for n in roots):
            raise InvalidLogisticsStateError("Todos los contenedores raíz deben estar sellados")
        self.status = ShipmentStatus.DISPATCHED
        self.dispatched_at = utcnow()

    def node(self, node_id: str | None) -> ShipmentContainerNode:
        for node in self.nodes:
            if node.id == node_id and not node.detached_at:
                return node
        raise InvalidContainerHierarchyError("Nodo inexistente o separado")
