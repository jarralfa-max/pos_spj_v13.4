import importlib.util
import sqlite3
from pathlib import Path

from backend.application.logistics.authorization import LogisticsAuthorizationPolicy
from backend.application.logistics.origin_purchase_workspace import OriginPurchaseWorkspaceService
from backend.application.logistics.queries import LogisticsShipmentQueryService
from backend.application.logistics.service import LogisticsApplicationService
from backend.domain.logistics.entities import (
    ContainerType, LogisticsShipment, PhysicalContainer, ShipmentContentAssignment,
)
from backend.domain.logistics.enums import ContainerCategory, ContainerOwnerType, SourceDocumentType
from backend.domain.logistics.qr_identity import PermanentContainerQrService
from backend.infrastructure.db.schema.procurement_schema import create_procurement_schema
from backend.infrastructure.db.repositories.logistics_repository import LogisticsRepository


class Allow:
    def has_permission(self, _user, _permission):
        return True


def _connection():
    connection = sqlite3.connect(":memory:")
    create_procurement_schema(connection)
    connection.execute("CREATE TABLE proveedores(id TEXT PRIMARY KEY,nombre TEXT,activo INTEGER)")
    path = Path(__file__).parents[3] / "migrations/standalone/171_logistics_bounded_context_schema.py"
    spec = importlib.util.spec_from_file_location("migration_171_workspace", path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    module.run(connection)
    auth_path = Path(__file__).parents[3] / "migrations/standalone/172_logistics_loading_authorizations.py"
    auth_spec = importlib.util.spec_from_file_location("migration_172_workspace", auth_path)
    auth_module = importlib.util.module_from_spec(auth_spec); auth_spec.loader.exec_module(auth_module)
    auth_module.run(connection)
    return connection


def test_document_to_tree_differences_seal_dispatch_and_mobile_handoff():
    connection = _connection()
    connection.execute("INSERT INTO proveedores VALUES ('supplier','Proveedor Norte',1)")
    connection.execute(
        "INSERT INTO purchase_orders(id,document_number,supplier_id,branch_id,warehouse_id,status,total,"
        "created_by_user_id,operation_id,created_at,updated_at) VALUES "
        "('po','PO-100','supplier','branch','warehouse','APPROVED','100','buyer','op','2026-01-01','2026-01-01')")
    connection.execute(
        "INSERT INTO purchase_order_lines(id,purchase_order_id,product_id,description,"
        "ordered_quantity,unit_price,purchase_nature) VALUES "
        "('line','po','product','Producto','10','10','INVENTORY')")
    logistics = LogisticsApplicationService(
        connection, LogisticsAuthorizationPolicy(Allow()), PermanentContainerQrService(b"q" * 32))
    queries = LogisticsShipmentQueryService(connection, LogisticsRepository(connection))
    workspace = OriginPurchaseWorkspaceService(logistics, queries)
    document = workspace.documents(branch_id="branch", warehouse_id="warehouse")[0]
    detail = workspace.create_shipment(actor_user_id="buyer", branch_id="branch",
                                       warehouse_id="warehouse", document=document)
    assert detail["status"] == "DRAFT"
    handoff = workspace.mobile_handoff(detail["id"])
    assert handoff["requires_login"] and detail["id"] in handoff["url"]

    ctype = ContainerType.create(code="BOX", name="Caja", category=ContainerCategory.PLASTIC_BOX)
    logistics.register_type(actor_user_id="buyer", item=ctype)
    container = PhysicalContainer.create(container_code="BX-1", container_type_id=ctype.id,
                                         owner_type=ContainerOwnerType.COMPANY)
    logistics.register_container(actor_user_id="buyer", container=container, operation_id="reg")
    node = logistics.attach_container(actor_user_id="buyer", shipment_id=detail["id"],
                                      container_id=container.id, operation_id="attach")
    assignment = ShipmentContentAssignment.create(
        shipment_node_id=node.id, source_document_type=SourceDocumentType.PURCHASE_ORDER,
        source_document_id="po", source_line_id="line", product_id="product",
        declared_quantity="10", declared_net_weight="8", purchase_unit="PZA",
        inventory_unit="PZA", conversion_factor="1", unit_cost="10",
        currency_code="MXN", operation_id="assign")
    logistics.assign_content(actor_user_id="buyer", shipment_id=detail["id"], assignment=assignment)
    loaded = workspace.open(detail["id"])
    assert loaded["container_count"] == 1 and loaded["differences"] == []
    sealed = workspace.seal_root(actor_user_id="buyer", shipment_id=detail["id"],
                                 node_id=node.id, seal_code="S-1")
    assert sealed["can_dispatch"]
    dispatched = workspace.dispatch(actor_user_id="buyer", shipment_id=detail["id"])
    assert dispatched["status"] == "DISPATCHED"
    connection.close()


def test_overage_or_cost_variance_is_blocking_authorization():
    connection = _connection()
    connection.execute("INSERT INTO proveedores VALUES ('supplier','Proveedor Norte',1)")
    connection.execute(
        "INSERT INTO purchase_orders(id,document_number,supplier_id,branch_id,warehouse_id,status,total,"
        "created_by_user_id,operation_id,created_at,updated_at) VALUES "
        "('po','PO-200','supplier','branch','warehouse','APPROVED','100','buyer','op','2026-01-01','2026-01-01')")
    connection.execute(
        "INSERT INTO purchase_order_lines(id,purchase_order_id,product_id,description,"
        "ordered_quantity,unit_price,purchase_nature) VALUES "
        "('line','po','product','Producto','10','10','INVENTORY')")
    logistics = LogisticsApplicationService(
        connection, LogisticsAuthorizationPolicy(Allow()), PermanentContainerQrService(b"q" * 32))
    shipment = LogisticsShipment.create(
        shipment_number="SHIP", origin_type="SUPPLIER", origin_location="Proveedor Norte",
        origin_supplier_id="supplier", destination_branch_id="branch",
        destination_warehouse_id="warehouse", buyer_user_id="buyer", operation_id="ship")
    shipment.add_source(SourceDocumentType.PURCHASE_ORDER, "po")
    logistics.create_shipment(actor_user_id="buyer", shipment=shipment)
    ctype = ContainerType.create(code="BOX", name="Caja", category=ContainerCategory.PLASTIC_BOX)
    logistics.register_type(actor_user_id="buyer", item=ctype)
    container = PhysicalContainer.create(container_code="BX", container_type_id=ctype.id,
                                         owner_type=ContainerOwnerType.COMPANY)
    logistics.register_container(actor_user_id="buyer", container=container, operation_id="reg")
    node = logistics.attach_container(actor_user_id="buyer", shipment_id=shipment.id,
                                      container_id=container.id, operation_id="attach")
    logistics.assign_content(actor_user_id="buyer", shipment_id=shipment.id,
        assignment=ShipmentContentAssignment.create(
            shipment_node_id=node.id, source_document_type=SourceDocumentType.PURCHASE_ORDER,
            source_document_id="po", source_line_id="line", product_id="product",
            declared_quantity="11", declared_net_weight="8", purchase_unit="PZA",
            inventory_unit="PZA", conversion_factor="1", unit_cost="12",
            currency_code="MXN", operation_id="assign"))
    query = LogisticsShipmentQueryService(connection, LogisticsRepository(connection))
    detail = query.workspace(shipment.id)
    assert detail["pending_authorizations"] and not detail["can_seal"]
    workspace = OriginPurchaseWorkspaceService(logistics, query)
    authorized = workspace.authorize_variance(
        actor_user_id="supervisor", shipment_id=shipment.id,
        source_line_id="line", reason="Exceso validado con proveedor")
    assert authorized["pending_authorizations"] == [] and authorized["can_seal"]
    assert connection.execute("SELECT authorized_by_user_id FROM logistics_loading_authorizations").fetchone()[0] == "supervisor"
    connection.close()
