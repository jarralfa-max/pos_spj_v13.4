"""«Probar conexión» de una integración: prueba real con la credencial guardada.

Antes la salud sólo se registraba a mano, así que podía decir "éxito" con un
token vencido. Aquí el verificador es falso: ninguna prueba sale a la red.
"""

from __future__ import annotations

import pytest

from backend.application.dto.diagnostics import DiagnosticResult
from backend.application.use_cases.configuracion.integration_management_use_cases import (
    CreateIntegrationDefinitionUseCase,
    CreateIntegrationInstanceUseCase,
    SetIntegrationInstanceCredentialUseCase,
    TestIntegrationConnectionUseCase,
)
from backend.domain.integrations.enums import IntegrationCategory
from backend.domain.integrations.exceptions import (
    IntegrationsInvalidValueError,
    MissingCredentialError,
)
from tests.integration._born_clean_db import make_db

TOKEN = "APP_USR-secreto-que-no-debe-salir"


class _Store:
    def __init__(self, secrets) -> None:
        self._secrets = secrets

    def get_secret(self, name):
        return self._secrets.get(name)

    def set_secret(self, name, value):
        self._secrets[name] = value


@pytest.fixture
def conn():
    c = make_db()
    yield c
    c.close()


def _mp_instance(conn, code="mercadopago", with_credential=True):
    definition = CreateIntegrationDefinitionUseCase(conn).execute(
        code=code, name="Proveedor", category=IntegrationCategory.PAYMENTS,
        required_credential_names=("mp_access_token",))
    instance = CreateIntegrationInstanceUseCase(conn).execute(
        definition_id=definition.id, name="Producción")
    if with_credential:  # el camino real: la referencia se fija al guardar la credencial
        SetIntegrationInstanceCredentialUseCase(conn, _Store({})).execute(
            instance_id=instance.id, credential_name="mp_access_token",
            secret_name="mp_access_token")
    return instance


def _use_case(conn, *, ok=True, seen=None, secrets=None):
    def verify(token):
        if seen is not None:
            seen.append(token)
        return DiagnosticResult.success("Token válido") if ok else DiagnosticResult.failure("Token inválido")
    return TestIntegrationConnectionUseCase(
        conn, _Store({"mp_access_token": TOKEN} if secrets is None else secrets),
        verifiers={"MERCADOPAGO": ("mp_access_token", verify)})


def test_a_valid_token_is_recorded_as_a_successful_check(conn):
    instance = _mp_instance(conn)
    seen = []
    check = _use_case(conn, seen=seen).execute(instance_id=instance.id)
    assert check.success and seen == [TOKEN]
    assert TOKEN not in check.message


def test_a_rejected_token_is_recorded_as_a_failure(conn):
    check = _use_case(conn, ok=False).execute(instance_id=_mp_instance(conn).id)
    assert not check.success and "inválido" in check.message


def test_providers_without_a_verifier_say_so(conn):
    instance = _mp_instance(conn, code="otro_banco")
    with pytest.raises(IntegrationsInvalidValueError, match="a mano"):
        _use_case(conn).execute(instance_id=instance.id)


def test_an_instance_without_the_credential_reference_is_refused(conn):
    instance = _mp_instance(conn, with_credential=False)
    with pytest.raises(MissingCredentialError):
        _use_case(conn).execute(instance_id=instance.id)
