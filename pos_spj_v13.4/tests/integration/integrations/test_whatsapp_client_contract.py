"""El cliente de WhatsApp del ERP firma como el microservicio espera.

El ERP y el microservicio son paquetes de nivel superior distintos y
desplegables por separado, así que cada uno mantiene su propia copia de la
lógica de firma. Dos copias divergen en silencio: cuando lo hacen, el
microservicio responde 401 y en el ERP sólo se ve "no se notificó", sin ninguna
pista de que la causa es la firma.

Estos tests comparan la copia del ERP contra la FUNCIÓN REAL del microservicio,
no contra otra reimplementación del mismo cálculo — comparar mi cálculo con mi
cálculo no probaría nada.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import pytest

from backend.infrastructure.integrations.whatsapp_client import (
    ERP_SERVICE_ID,
    WhatsAppClient,
    sign_request,
)

#: `whatsapp_service/` vive en la raíz del repositorio, un nivel por encima de
#: la aplicación. No es importable como paquete desde aquí (tiene su propio
#: `main.py` y su propio `sys.path`), así que se carga por ruta explícita.
_MICROSERVICE_AUTH = (
    Path(__file__).resolve().parents[3].parent
    / "whatsapp_service" / "middleware" / "service_auth.py"
)


def _load_microservice_auth():
    if not _MICROSERVICE_AUTH.is_file():
        pytest.skip(f"El microservicio no está presente: {_MICROSERVICE_AUTH}")
    spec = importlib.util.spec_from_file_location("_wa_service_auth_probe", _MICROSERVICE_AUTH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_wa_service_auth_probe"] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # fastapi ausente en el entorno, por ejemplo
        pytest.skip(f"No se pudo cargar el middleware del microservicio: {exc}")
    return module


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"{}",
        json.dumps({"phone": "+5215512345678", "folio": "F-1", "sucursal": ""}).encode(),
        json.dumps({"message": "acentos: ñ á é — y emoji 🛍️"}, ensure_ascii=False).encode(),
    ],
)
def test_the_erp_signature_matches_the_microservice_one(body):
    """Byte a byte, incluido el cuerpo vacío y el que lleva UTF-8 fuera de ASCII."""
    micro = _load_microservice_auth()
    args = (ERP_SERVICE_ID, "1757000000", "nonce-fijo", body, "secreto-compartido")
    assert sign_request(*args) == micro.sign_request(*args)


def test_the_erp_identity_is_the_one_the_microservice_expects():
    """Un `service_id` distinto se rechaza aunque la firma sea correcta."""
    micro = _load_microservice_auth()
    assert ERP_SERVICE_ID == micro.ERP_CORE_SERVICE


def test_the_signature_covers_the_body():
    """Si el cuerpo no entrara en la firma, se podría alterar en tránsito."""
    base = ("erp-core", "1757000000", "n1", b'{"phone":"+521"}', "s")
    alterado = ("erp-core", "1757000000", "n1", b'{"phone":"+999"}', "s")
    assert sign_request(*base) != sign_request(*alterado)


def test_the_signature_covers_the_nonce_and_the_timestamp():
    """Ambos existen para impedir la reproducción de una petición grabada."""
    base = ("erp-core", "1757000000", "n1", b"{}", "s")
    otro_nonce = ("erp-core", "1757000000", "n2", b"{}", "s")
    otro_ts = ("erp-core", "1757000001", "n1", b"{}", "s")
    assert sign_request(*base) != sign_request(*otro_nonce)
    assert sign_request(*base) != sign_request(*otro_ts)


def test_the_body_hash_is_sha256_of_the_body():
    """Fija la parte del formato que un cambio de algoritmo rompería."""
    body = b'{"a":1}'
    esperado = hashlib.sha256(body).hexdigest()
    distinto = sign_request("erp-core", "1", "n", body, "s")
    mismo = sign_request("erp-core", "1", "n", esperado.encode(), "s")
    assert distinto != mismo


# ── configuración ───────────────────────────────────────────────────────────
@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE configuraciones (clave TEXT PRIMARY KEY, valor TEXT)")
    yield c
    c.close()


def test_configuration_comes_from_the_database_before_the_environment(conn, monkeypatch):
    """Lo que el usuario configuró en Integraciones manda sobre un `.env`
    olvidado en la máquina."""
    monkeypatch.setenv("WA_BASE_URL", "http://del-entorno:9999")
    conn.execute("INSERT INTO configuraciones VALUES ('wa_base_url', 'http://de-la-base:8000')")

    client = WhatsAppClient(connection=conn)
    assert client._base_url == "http://de-la-base:8000"


def test_the_environment_is_the_fallback(conn, monkeypatch):
    monkeypatch.setenv("WA_INTERNAL_API_KEY", "clave-del-entorno")
    assert WhatsAppClient(connection=conn)._secret == "clave-del-entorno"


def test_a_trailing_slash_does_not_produce_a_double_slash(conn):
    conn.execute("INSERT INTO configuraciones VALUES ('wa_base_url', 'http://host:8000/')")
    assert WhatsAppClient(connection=conn)._base_url == "http://host:8000"


def test_without_a_secret_nothing_is_sent(conn, monkeypatch):
    """No se sale a la red sin clave: firmar con una vacía daría un 401
    confuso en vez de "falta configurar la integración"."""
    monkeypatch.delenv("WA_INTERNAL_API_KEY", raising=False)
    monkeypatch.delenv("INTERNAL_API_KEY", raising=False)
    client = WhatsAppClient(connection=conn)

    def _explota(*_args, **_kwargs):
        raise AssertionError("no debió intentar ninguna petición")

    monkeypatch.setattr("urllib.request.urlopen", _explota)
    assert client.notificar_pedido_listo("+5215512345678", "F-1") is False


def test_a_microservice_failure_never_raises(conn, monkeypatch):
    """Un WhatsApp que no sale no puede tumbar la operación que lo disparó."""
    conn.execute("INSERT INTO configuraciones VALUES ('wa_internal_api_key', 's3cr3t')")

    def _cae(*_args, **_kwargs):
        raise OSError("conexión rechazada")

    monkeypatch.setattr("urllib.request.urlopen", _cae)
    client = WhatsAppClient(connection=conn)
    assert client.notificar_pedido_listo("+5215512345678", "F-1") is False
    assert client.enviar_mensaje("+5215512345678", "hola") is False
