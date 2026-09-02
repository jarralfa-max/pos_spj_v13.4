"""Mobile origin-loading API; controllers delegate all mutations to a workflow."""

from __future__ import annotations

from typing import Protocol

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from backend.api.mobile_session import (
    MobileIdentity, command_payload, mobile_identity, mutation_headers,
)
from backend.api.schemas.mobile_logistics import (
    ContentAssignmentRequest, LoginRequest, NodeAttachRequest, PhotoUploadRequest,
    SealRequest, ShipmentCreateRequest, DispatchRequest,
)


class OriginPurchaseWorkflow(Protocol):
    def list_documents(self, identity: MobileIdentity, query: str) -> dict: ...
    def list_products(self, identity: MobileIdentity, document_id: str, query: str) -> dict: ...
    def resolve_container(self, identity: MobileIdentity, token: str) -> dict: ...
    def get_shipment(self, identity: MobileIdentity, shipment_id: str) -> dict: ...
    def create_shipment(self, identity: MobileIdentity, operation_id: str,
                        expected_version: int, command: dict) -> dict: ...
    def attach_node(self, identity: MobileIdentity, shipment_id: str, operation_id: str,
                    expected_version: int, command: dict) -> dict: ...
    def assign_content(self, identity: MobileIdentity, shipment_id: str, operation_id: str,
                       expected_version: int, command: dict) -> dict: ...
    def attach_photo(self, identity: MobileIdentity, shipment_id: str, operation_id: str,
                     expected_version: int, command: dict) -> dict: ...
    def seal_node(self, identity: MobileIdentity, shipment_id: str, node_id: str,
                  operation_id: str, expected_version: int, command: dict) -> dict: ...
    def dispatch(self, identity: MobileIdentity, shipment_id: str, operation_id: str,
                 expected_version: int) -> dict: ...


router = APIRouter(tags=["mobile-logistics"])


def workflow(request: Request) -> OriginPurchaseWorkflow:
    value = getattr(request.app.state, "origin_purchase_workflow", None)
    if value is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Workflow móvil no configurado")
    return value


@router.post("/mobile/session")
def login(command: LoginRequest, request: Request) -> dict:
    service = getattr(request.app.state, "mobile_session_service", None)
    if service is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Sesión móvil no configurada")
    token, user = service.login(command.username, command.password, command.deviceId)
    return {"accessToken": token, "userId": user.user_id, "displayName": user.display_name,
            "branchId": user.branch_id, "branchName": user.branch_name,
            "warehouseId": user.warehouse_id, "warehouseName": user.warehouse_name,
            "deviceId": user.device_id,
            "permissions": user.permissions}


@router.get("/mobile/session/me")
def current_session(user: MobileIdentity = Depends(mobile_identity)) -> dict:
    return {"userId": user.user_id, "displayName": user.display_name,
            "branchId": user.branch_id, "branchName": user.branch_name,
            "warehouseId": user.warehouse_id, "warehouseName": user.warehouse_name,
            "deviceId": user.device_id,
            "permissions": user.permissions}


@router.get("/procurement/mobile/documents")
def documents(q: str = Query("", max_length=120), user: MobileIdentity = Depends(mobile_identity),
              service: OriginPurchaseWorkflow = Depends(workflow)) -> dict:
    return service.list_documents(user, q)


@router.get("/procurement/mobile/documents/{document_id}/products")
def products(document_id: str, q: str = Query("", max_length=120),
             user: MobileIdentity = Depends(mobile_identity),
             service: OriginPurchaseWorkflow = Depends(workflow)) -> dict:
    return service.list_products(user, document_id, q)


@router.get("/logistics/containers/resolve")
def resolve_container(token: str = Query(min_length=20, max_length=1000),
                      user: MobileIdentity = Depends(mobile_identity),
                      service: OriginPurchaseWorkflow = Depends(workflow)) -> dict:
    return service.resolve_container(user, token)


@router.get("/logistics/shipments/{shipment_id}")
def shipment(shipment_id: str, user: MobileIdentity = Depends(mobile_identity),
             service: OriginPurchaseWorkflow = Depends(workflow)) -> dict:
    return service.get_shipment(user, shipment_id)


@router.post("/logistics/mobile/shipments")
def create_shipment(command: ShipmentCreateRequest,
                    headers: tuple[str, int] = Depends(mutation_headers),
                    user: MobileIdentity = Depends(mobile_identity),
                    service: OriginPurchaseWorkflow = Depends(workflow)) -> dict:
    return service.create_shipment(user, headers[0], headers[1],
                                   command_payload(command, user, headers[0]))


@router.post("/logistics/mobile/shipments/{shipment_id}/nodes")
def attach_node(shipment_id: str, command: NodeAttachRequest,
                headers: tuple[str, int] = Depends(mutation_headers),
                user: MobileIdentity = Depends(mobile_identity),
                service: OriginPurchaseWorkflow = Depends(workflow)) -> dict:
    return service.attach_node(user, shipment_id, headers[0], headers[1],
                               command_payload(command, user, headers[0]))


@router.post("/logistics/mobile/shipments/{shipment_id}/contents")
def assign_content(shipment_id: str, command: ContentAssignmentRequest,
                   headers: tuple[str, int] = Depends(mutation_headers),
                   user: MobileIdentity = Depends(mobile_identity),
                   service: OriginPurchaseWorkflow = Depends(workflow)) -> dict:
    return service.assign_content(user, shipment_id, headers[0], headers[1],
                                  command_payload(command, user, headers[0]))


@router.post("/logistics/mobile/shipments/{shipment_id}/photos")
def attach_photo(shipment_id: str, command: PhotoUploadRequest,
                 headers: tuple[str, int] = Depends(mutation_headers),
                 user: MobileIdentity = Depends(mobile_identity),
                 service: OriginPurchaseWorkflow = Depends(workflow)) -> dict:
    return service.attach_photo(user, shipment_id, headers[0], headers[1],
                                command_payload(command, user, headers[0]))


@router.post("/logistics/mobile/shipments/{shipment_id}/nodes/{node_id}/seal")
def seal_node(shipment_id: str, node_id: str, command: SealRequest,
              headers: tuple[str, int] = Depends(mutation_headers),
              user: MobileIdentity = Depends(mobile_identity),
              service: OriginPurchaseWorkflow = Depends(workflow)) -> dict:
    return service.seal_node(user, shipment_id, node_id, headers[0], headers[1],
                             command_payload(command, user, headers[0]))


@router.post("/logistics/mobile/shipments/{shipment_id}/dispatch")
def dispatch(shipment_id: str, command: DispatchRequest,
             headers: tuple[str, int] = Depends(mutation_headers),
             user: MobileIdentity = Depends(mobile_identity),
             service: OriginPurchaseWorkflow = Depends(workflow)) -> dict:
    command_payload(command, user, headers[0])
    return service.dispatch(user, shipment_id, headers[0], headers[1])
