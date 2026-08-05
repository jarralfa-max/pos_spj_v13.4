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


<<<<<<< HEAD
def metadata(headers, operation_id):
    token = headers["Authorization"].split(" ", 1)[1]
    # Decode only the signed payload for test construction; verification remains server-side.
    import base64, json
    payload = token.split(".", 1)[0]
    payload += "=" * (-len(payload) % 4)
    identity = json.loads(base64.urlsafe_b64decode(payload))
    return {"clientOperationId": operation_id, "deviceId": identity["device_id"],
            "userId": identity["user_id"], "createdAt": "2026-08-01T00:00:00Z",
            "payloadVersion": 1}


=======
>>>>>>> f877b14564fe37c44b2caeab736af2048b371ae2
def test_mobile_api_requires_session_and_serves_pwa():
    api, _ = client()
    assert api.get("/api/procurement/mobile/documents").status_code == 401
    page = api.get("/mobile/logistics/")
    assert page.status_code == 200 and "Carga en origen" in page.text


def test_mutation_requires_uuidv7_idempotency_and_if_match():
    api, workflow, headers = authenticated()
<<<<<<< HEAD
    operation_id = new_uuid()
    command = {"shipmentId": new_uuid(), "documentType": "PURCHASE_ORDER",
               "documentId": new_uuid(), "supplierId": new_uuid(),
               **metadata(headers, operation_id)}
    invalid = api.post("/api/logistics/mobile/shipments", json=command,
                       headers={**headers, "Idempotency-Key": "bad", "If-Match": "0"})
    assert invalid.status_code == 422
=======
    command = {"shipmentId": new_uuid(), "documentType": "PURCHASE_ORDER",
               "documentId": new_uuid(), "supplierId": new_uuid()}
    invalid = api.post("/api/logistics/mobile/shipments", json=command,
                       headers={**headers, "Idempotency-Key": "bad", "If-Match": "0"})
    assert invalid.status_code == 422
    operation_id = new_uuid()
>>>>>>> f877b14564fe37c44b2caeab736af2048b371ae2
    response = api.post("/api/logistics/mobile/shipments", json=command,
                        headers={**headers, "Idempotency-Key": operation_id, "If-Match": "0"})
    assert response.status_code == 200
    assert workflow.calls == [(operation_id, 0, command)]
<<<<<<< HEAD


def test_mobile_command_identity_must_match_signed_session():
    api, _workflow, headers = authenticated()
    operation_id = new_uuid()
    command = {"shipmentId": new_uuid(), "documentType": "PURCHASE_ORDER",
               "documentId": new_uuid(), "supplierId": new_uuid(),
               **metadata(headers, operation_id), "userId": new_uuid()}
    response = api.post("/api/logistics/mobile/shipments", json=command,
                        headers={**headers, "Idempotency-Key": operation_id, "If-Match": "0"})
    assert response.status_code == 403
=======
>>>>>>> f877b14564fe37c44b2caeab736af2048b371ae2
