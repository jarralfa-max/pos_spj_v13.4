from fastapi.testclient import TestClient

from backend.api.main import create_app
from backend.api.mobile_session import MobileIdentity, MobileSessionTokenService
from backend.shared.ids import new_uuid


class Verifier:
    def authenticate_mobile(self, username, password, device_id):
        if password != "secret": return None
        return MobileIdentity(
            new_uuid(), username, new_uuid(), "Centro", new_uuid(), "Almacén", device_id,
            ("logistics.shipment.create", "logistics.container.scan"))


class Workflow:
    def __init__(self): self.calls = []
    def list_documents(self, identity, query): return {"items": []}
    def list_products(self, identity, document_id, query): return {"items": []}
    def resolve_container(self, identity, token): return {"containerId": new_uuid(), "containerCode": "C-1", "typeName": "Caja"}
    def get_shipment(self, identity, shipment_id): return {"shipmentId": shipment_id, "version": 0}
    def create_shipment(self, identity, operation_id, expected_version, command):
        self.calls.append((operation_id, expected_version, command)); return {"shipmentId": command["shipmentId"], "version": 0}
    def attach_node(self, *args): return {"version": 1}
    def assign_content(self, *args): return {"version": 2}
    def attach_photo(self, *args): return {"version": 2}
    def seal_node(self, *args): return {"version": 3}
    def dispatch(self, *args): return {"version": 4, "status": "DISPATCHED"}


def client():
    app = create_app(); workflow = Workflow()
    app.state.mobile_session_service = MobileSessionTokenService(b"m" * 32, Verifier())
    app.state.origin_purchase_workflow = workflow
    return TestClient(app), workflow


def authenticated():
    api, workflow = client()
    response = api.post("/api/mobile/session", json={"username": "buyer", "password": "secret", "deviceId": "tablet"})
    return api, workflow, {"Authorization": f"Bearer {response.json()['accessToken']}"}


def test_mobile_api_requires_session_and_serves_pwa():
    api, _ = client()
    assert api.get("/api/procurement/mobile/documents").status_code == 401
    page = api.get("/mobile/logistics/")
    assert page.status_code == 200 and "Carga en origen" in page.text


def test_mutation_requires_uuidv7_idempotency_and_if_match():
    api, workflow, headers = authenticated()
    command = {"shipmentId": new_uuid(), "documentType": "PURCHASE_ORDER",
               "documentId": new_uuid(), "supplierId": new_uuid()}
    invalid = api.post("/api/logistics/mobile/shipments", json=command,
                       headers={**headers, "Idempotency-Key": "bad", "If-Match": "0"})
    assert invalid.status_code == 422
    operation_id = new_uuid()
    response = api.post("/api/logistics/mobile/shipments", json=command,
                        headers={**headers, "Idempotency-Key": operation_id, "If-Match": "0"})
    assert response.status_code == 200
    assert workflow.calls == [(operation_id, 0, command)]
