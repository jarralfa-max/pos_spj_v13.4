from decimal import Decimal

import pytest

from backend.domain.logistics.entities import (
    ContainerType, ContainerTypeCompatibility, LogisticsShipment, PhysicalContainer,
    ShipmentContentAssignment,
)
from backend.domain.logistics.enums import (
    ContainerCategory, ContainerOwnerType, SourceDocumentType,
)
from backend.domain.logistics.exceptions import (
    ContainerCapacityError, InvalidContainerHierarchyError,
    InvalidLogisticsStateError,
)
from backend.domain.logistics.qr_identity import PermanentContainerQrService
from backend.application.logistics.authorization import (
    LogisticsAuthorizationPolicy, LogisticsPermissionDeniedError,
)


def ctype(code, category, *, children=False, depth=0, net="100", gross="200"):
    return ContainerType.create(
        code=code, name=code, category=category, allows_children=children,
        maximum_children=5, maximum_depth_below=depth,
        maximum_net_weight=net, maximum_gross_weight=gross)


def container(code, type_id, tare="1"):
    return PhysicalContainer.create(
        container_code=code, container_type_id=type_id,
        owner_type=ContainerOwnerType.COMPANY, tare_weight=tare)


def shipment():
    return LogisticsShipment.create(
        shipment_number="S-1", origin_type="SUPPLIER", origin_location="Origen",
        destination_branch_id="branch", destination_warehouse_id="warehouse",
        buyer_user_id="buyer", operation_id="shipment-op")


def test_recursive_master_pallet_box_tray_and_aggregate_weight():
    master = ctype("MASTER", ContainerCategory.MASTER_CONTAINER, children=True, depth=4)
    pallet = ctype("PALLET", ContainerCategory.PALLET, children=True, depth=3)
    box = ctype("BOX", ContainerCategory.PLASTIC_BOX, children=True, depth=2)
    tray = ctype("TRAY", ContainerCategory.TRAY)
    containers = [container("MC", master.id), container("P", pallet.id),
                  container("B", box.id), container("T", tray.id)]
    sh = shipment()
    root = sh.attach_container(container=containers[0], container_type=master,
                               actor_user_id="u", operation_id="n1")
    n2 = sh.attach_container(
        container=containers[1], container_type=pallet, actor_user_id="u",
        operation_id="n2", parent_node_id=root.id, parent_type=master,
        compatibility=ContainerTypeCompatibility.create(master.id, pallet.id, allowed=True))
    n3 = sh.attach_container(
        container=containers[2], container_type=box, actor_user_id="u",
        operation_id="n3", parent_node_id=n2.id, parent_type=pallet,
        compatibility=ContainerTypeCompatibility.create(pallet.id, box.id, allowed=True))
    n4 = sh.attach_container(
        container=containers[3], container_type=tray, actor_user_id="u",
        operation_id="n4", parent_node_id=n3.id, parent_type=box,
        compatibility=ContainerTypeCompatibility.create(box.id, tray.id, allowed=True))
    assignment = ShipmentContentAssignment.create(
        shipment_node_id=n4.id, source_document_type=SourceDocumentType.PURCHASE_ORDER,
        source_document_id="po", source_line_id="line", product_id="product",
        declared_quantity="5", declared_net_weight="8", purchase_unit="PZA",
        inventory_unit="PZA", conversion_factor="1", unit_cost="10",
        currency_code="MXN", operation_id="content")
    sh.assign_content(assignment, container_type=tray)
    assert n2.parent_node_id == root.id and n3.parent_node_id == n2.id
    assert sh.aggregate_net_weight(root.id) == Decimal("8")
    assert sh.gross_weight(root.id, {c.id: c for c in containers}) == Decimal("12")


def test_hierarchy_rejects_incompatible_self_cycle_and_sealed_parent():
    parent_type = ctype("PARENT", ContainerCategory.PALLET, children=True, depth=2)
    child_type = ctype("CHILD", ContainerCategory.PLASTIC_BOX)
    parent = container("P", parent_type.id)
    child = container("C", child_type.id)
    sh = shipment()
    root = sh.attach_container(container=parent, container_type=parent_type,
                               actor_user_id="u", operation_id="root")
    with pytest.raises(InvalidContainerHierarchyError):
        sh.attach_container(
            container=child, container_type=child_type, actor_user_id="u",
            operation_id="bad", parent_node_id=root.id, parent_type=parent_type,
            compatibility=ContainerTypeCompatibility.create(
                parent_type.id, child_type.id, allowed=False))
    node = sh.attach_container(
        container=child, container_type=child_type, actor_user_id="u",
        operation_id="child", parent_node_id=root.id, parent_type=parent_type,
        compatibility=ContainerTypeCompatibility.create(
            parent_type.id, child_type.id, allowed=True))
    with pytest.raises(InvalidContainerHierarchyError):
        sh.move_node(root.id, node.id, actor_user_id="u", operation_id="cycle")
    node.status = node.status.SEALED
    with pytest.raises(InvalidContainerHierarchyError):
        sh.move_node(node.id, None, actor_user_id="u", operation_id="move")


def test_content_capacity_and_hierarchical_sealing():
    parent_type = ctype("PARENT", ContainerCategory.PALLET, children=True, depth=1)
    child_type = ctype("CHILD", ContainerCategory.PLASTIC_BOX, net="5")
    parent, child = container("P", parent_type.id), container("C", child_type.id)
    sh = shipment()
    root = sh.attach_container(container=parent, container_type=parent_type,
                               actor_user_id="u", operation_id="root")
    node = sh.attach_container(
        container=child, container_type=child_type, actor_user_id="u", operation_id="child",
        parent_node_id=root.id, parent_type=parent_type,
        compatibility=ContainerTypeCompatibility.create(parent_type.id, child_type.id, allowed=True))
    too_heavy = ShipmentContentAssignment.create(
        shipment_node_id=node.id, source_document_type=SourceDocumentType.DIRECT_PURCHASE,
        source_document_id="dp", source_line_id="line", product_id="p",
        declared_quantity="1", declared_net_weight="6", purchase_unit="PZA",
        inventory_unit="PZA", conversion_factor="1", unit_cost="1", currency_code="MXN",
        operation_id="heavy")
    with pytest.raises(ContainerCapacityError):
        sh.assign_content(too_heavy, container_type=child_type)
    with pytest.raises(InvalidLogisticsStateError):
        sh.seal_node(root.id, seal_code="S1", seal_type="BOLT", actor_user_id="u",
                     operation_id="seal-root", containers={parent.id: parent, child.id: child},
                     container_types={parent_type.id: parent_type, child_type.id: child_type})


def test_permanent_qr_signature_rotation_and_no_commercial_payload():
    item_type = ctype("BOX", ContainerCategory.PLASTIC_BOX)
    item = container("BOX-1", item_type.id)
    qr = PermanentContainerQrService(b"x" * 32)
    token = qr.issue(item)
    assert qr.validate(token, item)
    assert all(secret not in token for secret in ("supplier", "price", "product", "weight"))
    item.rotate_qr()
    assert not qr.validate(token, item)


def test_logistics_authorization_fails_closed():
    with pytest.raises(LogisticsPermissionDeniedError):
        LogisticsAuthorizationPolicy().require("user", "LOGISTICA.embarque.crear")
