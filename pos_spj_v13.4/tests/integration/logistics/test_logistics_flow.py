import importlib.util
import sqlite3
from pathlib import Path

import pytest

from backend.application.logistics.authorization import (
    LogisticsAuthorizationPolicy,
)
from backend.application.logistics.service import LogisticsApplicationService
from backend.application.logistics.wiring import wire_logistics
from backend.domain.logistics.entities import (
    ContainerType, ContainerTypeCompatibility, LogisticsShipment, PhysicalContainer,
    ShipmentContentAssignment,
)
from backend.domain.logistics.enums import (
    ContainerCategory, ContainerOwnerType, ContainerStatus, SourceDocumentType,
)
from backend.domain.logistics.qr_identity import PermanentContainerQrService


class Allow:
    def has_permission(self, user_id, permission):
        return True


class Printer:
    def __init__(self):
        self.jobs = []

    def submit(self, job, payload):
        self.jobs.append((job, payload))


@pytest.fixture
def connection():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys=ON")
    path = Path(__file__).parents[3] / "migrations/standalone/171_logistics_bounded_context_schema.py"
    spec = importlib.util.spec_from_file_location("migration_171", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.run(conn)
    yield conn
    conn.close()


def service(conn, printer=None):
    return LogisticsApplicationService(
        conn, LogisticsAuthorizationPolicy(Allow()),
        PermanentContainerQrService(b"q" * 32), printer)


def test_idempotent_shipment_tree_content_seals_dispatch_and_custody(connection):
    app = service(connection)
    master = ContainerType.create(
        code="MASTER", name="Maestro", category=ContainerCategory.MASTER_CONTAINER,
        allows_children=True, maximum_children=3, maximum_depth_below=2,
        maximum_gross_weight="100")
    box = ContainerType.create(
        code="BOX", name="Caja", category=ContainerCategory.PLASTIC_BOX,
        maximum_net_weight="20", maximum_gross_weight="25")
    app.register_type(actor_user_id="u", item=master)
    app.register_type(actor_user_id="u", item=box)
    app.register_compatibility(
        actor_user_id="u", item=ContainerTypeCompatibility.create(
            master.id, box.id, allowed=True, maximum_quantity=2))
    root_container = PhysicalContainer.create(
        container_code="MC-1", container_type_id=master.id,
        owner_type=ContainerOwnerType.COMPANY, tare_weight="5")
    child_container = PhysicalContainer.create(
        container_code="BX-1", container_type_id=box.id,
        owner_type=ContainerOwnerType.COMPANY, tare_weight="1")
    root_qr = app.register_container(
        actor_user_id="u", container=root_container, operation_id="register-root")
    retried_qr = app.register_container(
        actor_user_id="u", container=PhysicalContainer.create(
            container_code="IGNORED", container_type_id=master.id,
            owner_type=ContainerOwnerType.COMPANY), operation_id="register-root")
    assert retried_qr == root_qr
    app.register_container(actor_user_id="u", container=child_container,
                           operation_id="register-child")
    assert root_qr["qr_url"].startswith("https://app.spj.mx/c/")
    shipment = LogisticsShipment.create(
        shipment_number="SHIP-1", origin_type="SUPPLIER", origin_location="Proveedor",
        destination_branch_id="branch", destination_warehouse_id="warehouse",
        buyer_user_id="u", operation_id="create-shipment")
    shipment.add_source(SourceDocumentType.PURCHASE_ORDER, "po-1")
    first = app.create_shipment(actor_user_id="u", shipment=shipment)
    retry = app.create_shipment(actor_user_id="u", shipment=shipment)
    assert first.id == retry.id
    root = app.attach_container(
        actor_user_id="u", shipment_id=shipment.id, container_id=root_container.id,
        operation_id="attach-root")
    child = app.attach_container(
        actor_user_id="u", shipment_id=shipment.id, container_id=child_container.id,
        parent_node_id=root.id, operation_id="attach-child")
    assignment = ShipmentContentAssignment.create(
        shipment_node_id=child.id, source_document_type=SourceDocumentType.PURCHASE_ORDER,
        source_document_id="po-1", source_line_id="line-1", product_id="product",
        declared_quantity="10", declared_net_weight="10", purchase_unit="PZA",
        inventory_unit="PZA", conversion_factor="1", unit_cost="12.50",
        currency_code="MXN", operation_id="content-1")
    app.assign_content(actor_user_id="u", shipment_id=shipment.id, assignment=assignment)
    app.seal(actor_user_id="u", shipment_id=shipment.id, node_id=child.id,
             seal_code="SEAL-C", seal_type="TAPE", operation_id="seal-child")
    app.seal(actor_user_id="u", shipment_id=shipment.id, node_id=root.id,
             seal_code="SEAL-R", seal_type="BOLT", operation_id="seal-root")
    dispatched = app.dispatch(actor_user_id="u", shipment_id=shipment.id,
                              operation_id="dispatch")
    assert dispatched.status.value == "DISPATCHED"
    assert connection.execute("SELECT COUNT(*) FROM logistics_shipment_nodes").fetchone()[0] == 2
    assert connection.execute("SELECT COUNT(*) FROM logistics_custody_events").fetchone()[0] == 2
    assert connection.execute("SELECT COUNT(*) FROM logistics_outbox").fetchone()[0] == 2


def test_container_cannot_join_two_active_shipments_and_damage_release_print(connection):
    printer = Printer()
    app = service(connection, printer)
    ctype = ContainerType.create(code="TOTE", name="Tote", category=ContainerCategory.TOTE)
    app.register_type(actor_user_id="u", item=ctype)
    item = PhysicalContainer.create(
        container_code="T-1", container_type_id=ctype.id,
        owner_type=ContainerOwnerType.COMPANY)
    app.register_container(actor_user_id="u", container=item, operation_id="register")
    one = LogisticsShipment.create(
        shipment_number="ONE", origin_type="SUPPLIER", origin_location="A",
        destination_branch_id="b", destination_warehouse_id="w", buyer_user_id="u",
        operation_id="one")
    two = LogisticsShipment.create(
        shipment_number="TWO", origin_type="SUPPLIER", origin_location="A",
        destination_branch_id="b", destination_warehouse_id="w", buyer_user_id="u",
        operation_id="two")
    app.create_shipment(actor_user_id="u", shipment=one)
    app.create_shipment(actor_user_id="u", shipment=two)
    app.attach_container(actor_user_id="u", shipment_id=one.id, container_id=item.id,
                         operation_id="attach-one")
    with pytest.raises(ValueError):
        app.attach_container(actor_user_id="u", shipment_id=two.id, container_id=item.id,
                             operation_id="attach-two")
    app.mark_damaged_or_lost(actor_user_id="u", container_id=item.id,
                             operation_id="damage", lost=False, reason="Golpe")
    assert app._repo.get_container(item.id).status is ContainerStatus.DAMAGED
    app.release_container(actor_user_id="u", container_id=item.id,
                          operation_id="release", return_to_supplier=False,
                          reason="Inspeccionado")
    job = app.create_label_and_print(
        actor_user_id="u", container_id=item.id, printer_id="printer",
        operation_id="print", copies=1)
    assert job.id and len(printer.jobs) == 1
    retry = app.create_label_and_print(
        actor_user_id="u", container_id=item.id, printer_id="printer",
        operation_id="print", copies=1)
    assert retry.id == job.id and len(printer.jobs) == 1
    assert connection.execute("SELECT COUNT(*) FROM logistics_print_jobs").fetchone()[0] == 1


def test_runtime_wiring_creates_idempotent_shipment(connection):
    app = service(connection)

    class Bus:
        def __init__(self):
            self.handlers = {}

        def subscribe(self, name, handler, **kwargs):
            self.handlers[name] = handler

    bus = Bus()
    summary = wire_logistics(bus, app)
    payload = {
        "shipment_number": "WIRED", "origin_type": "SUPPLIER",
        "origin_location": "Origen", "destination_branch_id": "branch",
        "destination_warehouse_id": "warehouse", "actor_user_id": "u",
        "operation_id": "wired-operation", "sources": [{
            "source_document_type": "DIRECT_PURCHASE", "source_document_id": "dp"}],
    }
    bus.handlers["LOGISTICS_SHIPMENT_CREATE_REQUESTED"](payload)
    bus.handlers["LOGISTICS_SHIPMENT_CREATE_REQUESTED"](payload)
    assert summary["count"] == 1
    assert connection.execute(
        "SELECT COUNT(*) FROM logistics_shipments WHERE operation_id='wired-operation'"
    ).fetchone()[0] == 1
