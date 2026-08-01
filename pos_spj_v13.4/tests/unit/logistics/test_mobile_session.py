import pytest
from fastapi import HTTPException

from backend.api.mobile_session import (
    MobileIdentity, MobileSessionTokenService,
)


class Verifier:
    def authenticate_mobile(self, username, password, device_id):
        if (username, password) != ("buyer", "secret"):
            return None
        return MobileIdentity(
            "01900000-0000-7000-8000-000000000001", "Comprador",
            "01900000-0000-7000-8000-000000000002", "Centro",
            "01900000-0000-7000-8000-000000000003", "Almacén",
            device_id, ("logistics.shipment.create", "logistics.container.scan"))


def test_mobile_session_is_signed_and_contains_canonical_context():
    service = MobileSessionTokenService(b"s" * 32, Verifier())
    token, identity = service.login("buyer", "secret", "device")
    assert service.verify(token) == identity
    with pytest.raises(HTTPException):
        service.verify(token[:-1] + ("a" if token[-1] != "a" else "b"))


def test_mobile_login_rejects_invalid_credentials():
    service = MobileSessionTokenService(b"s" * 32, Verifier())
    with pytest.raises(HTTPException) as error:
        service.login("buyer", "wrong", "device")
    assert error.value.status_code == 401
