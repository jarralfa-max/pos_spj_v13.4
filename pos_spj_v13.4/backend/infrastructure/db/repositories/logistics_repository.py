"""SQLite/PostgreSQL-neutral repository for the Logistics aggregate."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from backend.domain.logistics.entities import (
    ContainerSeal, ContainerType, ContainerTypeCompatibility, LogisticsShipment,
    PhysicalContainer, ShipmentContainerNode, ShipmentContentAssignment,
    ShipmentSourceDocument,
)
from backend.domain.logistics.enums import (
    ContainerCategory, ContainerOwnerType, ContainerStatus, ShipmentNodeStatus,
    ShipmentStatus, SourceDocumentType,
)


class LogisticsRepository:
    def __init__(self, connection) -> None:
        self.connection = connection

    def save_type(self, item: ContainerType) -> None:
        self.connection.execute(
            "INSERT INTO logistics_container_types VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (item.id, item.code, item.name, item.category.value, int(item.reusable),
             int(item.requires_permanent_qr), int(item.allows_children), item.maximum_children,
             item.maximum_depth_below, str(item.default_tare_weight),
             str(item.maximum_gross_weight) if item.maximum_gross_weight is not None else None,
             str(item.maximum_net_weight) if item.maximum_net_weight is not None else None,
             str(item.maximum_volume) if item.maximum_volume is not None else None,
             int(item.stackable), int(item.seal_required), int(item.temperature_controlled),
             int(item.active), item.version))

    def get_type(self, type_id: str) -> ContainerType | None:
        row = self.connection.execute(
            "SELECT * FROM logistics_container_types WHERE id=?", (type_id,)).fetchone()
        if not row:
            return None
        return ContainerType(
            row[0], row[1], row[2], ContainerCategory(row[3]), bool(row[4]), bool(row[5]),
            bool(row[6]), row[7], row[8], Decimal(row[9]),
            Decimal(row[10]) if row[10] is not None else None,
            Decimal(row[11]) if row[11] is not None else None,
            Decimal(row[12]) if row[12] is not None else None,
            bool(row[13]), bool(row[14]), bool(row[15]), bool(row[16]), row[17])

    def save_compatibility(self, item: ContainerTypeCompatibility) -> None:
        self.connection.execute(
            "INSERT INTO logistics_container_type_compatibility VALUES (?,?,?,?,?,?)",
            (item.id, item.parent_type_id, item.child_type_id, int(item.allowed),
             item.maximum_quantity, item.conditions))

    def get_compatibility(self, parent_type_id: str,
                          child_type_id: str) -> ContainerTypeCompatibility | None:
        row = self.connection.execute(
            "SELECT * FROM logistics_container_type_compatibility"
            " WHERE parent_type_id=? AND child_type_id=?",
            (parent_type_id, child_type_id)).fetchone()
        return (ContainerTypeCompatibility(row[0], row[1], row[2], bool(row[3]), row[4], row[5])
                if row else None)

    def save_container(self, item: PhysicalContainer) -> None:
        self.connection.execute(
            "INSERT INTO logistics_physical_containers VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET current_location_id=excluded.current_location_id,"
            " current_custodian_id=excluded.current_custodian_id,status=excluded.status,"
            " condition=excluded.condition,qr_version=excluded.qr_version,"
            " qr_signature=excluded.qr_signature,last_inspection_at=excluded.last_inspection_at,"
            " retired_at=excluded.retired_at",
            (item.id, item.container_code, item.container_type_id, item.serial_number,
             str(item.tare_weight),
             str(item.capacity_weight) if item.capacity_weight is not None else None,
             str(item.capacity_volume) if item.capacity_volume is not None else None,
             item.owner_type.value, item.owner_supplier_id, item.current_location_id,
             item.current_custodian_id, item.status.value, item.condition, item.qr_version,
             item.qr_signature, item.created_at, item.last_inspection_at, item.retired_at))

    def get_container(self, container_id: str) -> PhysicalContainer | None:
        row = self.connection.execute(
            "SELECT * FROM logistics_physical_containers WHERE id=?", (container_id,)).fetchone()
        return PhysicalContainer(
            row[0], row[1], row[2], row[3], Decimal(row[4]),
            Decimal(row[5]) if row[5] is not None else None,
            Decimal(row[6]) if row[6] is not None else None,
            ContainerOwnerType(row[7]), row[8], row[9], row[10], ContainerStatus(row[11]),
            row[12], row[13], row[14], row[15], row[16], row[17]) if row else None

    def container_in_active_shipment(self, container_id: str) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM logistics_shipment_nodes n JOIN logistics_shipments s"
            " ON s.id=n.shipment_id WHERE n.container_id=? AND n.detached_at IS NULL"
            " AND s.status NOT IN ('CANCELLED','CLOSED','RECEIVED') LIMIT 1",
            (container_id,)).fetchone()
        return row is not None

    def save_shipment(self, shipment: LogisticsShipment) -> None:
        self.connection.execute(
            "INSERT INTO logistics_shipments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET status=excluded.status,sealed_at=excluded.sealed_at,"
            " dispatched_at=excluded.dispatched_at,arrived_at=excluded.arrived_at,"
            " closed_at=excluded.closed_at,version=excluded.version",
            (shipment.id, shipment.shipment_number, shipment.origin_type,
             shipment.origin_supplier_id, shipment.origin_location,
             shipment.destination_branch_id, shipment.destination_warehouse_id,
             shipment.buyer_user_id, shipment.vehicle_id, shipment.status.value,
             shipment.operation_id, shipment.version, shipment.started_at, shipment.sealed_at,
             shipment.dispatched_at, shipment.arrived_at, shipment.closed_at))
        for source in shipment.sources:
            self.connection.execute(
                "INSERT OR IGNORE INTO logistics_shipment_sources VALUES (?,?,?,?)",
                (source.id, source.shipment_id, source.source_document_type.value,
                 source.source_document_id))
        for node in shipment.nodes:
            self.connection.execute(
                "INSERT INTO logistics_shipment_nodes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(id) DO UPDATE SET parent_node_id=excluded.parent_node_id,"
                " depth=excluded.depth,sequence=excluded.sequence,status=excluded.status,"
                " detached_at=excluded.detached_at,detached_by_user_id=excluded.detached_by_user_id,"
                " operation_id=excluded.operation_id",
                (node.id, node.shipment_id, node.container_id, node.parent_node_id,
                 node.depth, node.sequence, node.position_code, node.status.value,
                 node.attached_at, node.attached_by_user_id, node.detached_at,
                 node.detached_by_user_id, node.operation_id))
        for content in shipment.contents:
            self.connection.execute(
                "INSERT OR IGNORE INTO logistics_shipment_contents VALUES"
                " (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (content.id, content.shipment_node_id, content.source_document_type.value,
                 content.source_document_id, content.source_line_id, content.product_id,
                 str(content.declared_quantity), str(content.declared_net_weight),
                 content.purchase_unit, content.inventory_unit, str(content.conversion_factor),
                 content.lot_number,
                 content.expiration_date.isoformat() if content.expiration_date else None,
                 str(content.unit_cost), content.currency_code,
                 str(content.temperature) if content.temperature is not None else None,
                 content.notes, content.operation_id))
        for seal in shipment.seals:
            self.connection.execute(
                "INSERT INTO logistics_container_seals VALUES (?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(id) DO UPDATE SET broken_by=excluded.broken_by,"
                " broken_at=excluded.broken_at,break_reason=excluded.break_reason",
                (seal.id, seal.seal_code, seal.seal_type, seal.shipment_node_id,
                 seal.applied_by, seal.applied_at, seal.broken_by, seal.broken_at,
                 seal.break_reason, seal.photo_id, seal.operation_id))

    def get_shipment_by_operation(self, operation_id: str) -> LogisticsShipment | None:
        row = self.connection.execute(
            "SELECT id FROM logistics_shipments WHERE operation_id=?", (operation_id,)).fetchone()
        return self.get_shipment(row[0]) if row else None

    def get_shipment(self, shipment_id: str) -> LogisticsShipment | None:
        row = self.connection.execute(
            "SELECT * FROM logistics_shipments WHERE id=?", (shipment_id,)).fetchone()
        if not row:
            return None
        shipment = LogisticsShipment(
            row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8],
            ShipmentStatus(row[9]), row[10], row[11], started_at=row[12], sealed_at=row[13],
            dispatched_at=row[14], arrived_at=row[15], closed_at=row[16])
        shipment.sources = [ShipmentSourceDocument(
            source[0], source[1], SourceDocumentType(source[2]), source[3])
            for source in self.connection.execute(
                "SELECT * FROM logistics_shipment_sources WHERE shipment_id=?", (shipment_id,))]
        shipment.nodes = [ShipmentContainerNode(
            node[0], node[1], node[2], node[3], node[4], node[5], node[6],
            ShipmentNodeStatus(node[7]), node[8], node[9], node[12], node[10], node[11])
            for node in self.connection.execute(
                "SELECT * FROM logistics_shipment_nodes WHERE shipment_id=? ORDER BY sequence",
                (shipment_id,))]
        node_ids = [node.id for node in shipment.nodes]
        if node_ids:
            placeholders = ",".join("?" for _ in node_ids)
            shipment.contents = [ShipmentContentAssignment(
                content[0], content[1], SourceDocumentType(content[2]), content[3],
                content[4], content[5], Decimal(content[6]), Decimal(content[7]),
                content[8], content[9], Decimal(content[10]), content[11],
                date.fromisoformat(content[12]) if content[12] else None,
                Decimal(content[13]), content[14],
                Decimal(content[15]) if content[15] else None, content[16], content[17])
                for content in self.connection.execute(
                    f"SELECT * FROM logistics_shipment_contents WHERE shipment_node_id IN ({placeholders})",
                    node_ids)]
            shipment.seals = [ContainerSeal(
                seal[0], seal[1], seal[2], seal[3], seal[4], seal[5], seal[10],
                seal[6], seal[7], seal[8], seal[9])
                for seal in self.connection.execute(
                    f"SELECT * FROM logistics_container_seals WHERE shipment_node_id IN ({placeholders})",
                    node_ids)]
        return shipment
