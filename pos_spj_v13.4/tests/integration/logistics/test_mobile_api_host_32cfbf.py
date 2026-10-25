"""Integración Logística 32cfbf, Fase G: host de producción de la API + PWA de
Logística (`spj_api.exe`, servicio local OPCIONAL por decisión del usuario).

Antes `create_app()` sólo montaba rutas: sin sesión ni flujo inyectados la API
respondía 503, el único `CredentialVerifier` era un doble de prueba y nada la
empaquetaba ni la registraba en el instalador.
"""

from __future__ import annotations

import importlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.api import service_host
from backend.api.mobile_credentials import DatabaseMobileCredentialVerifier
from backend.api.mobile_session import MobileIdentity
from backend.application.logistics.authorization import LogisticsPermissions
from backend.application.logistics.mobile_workflow import MobileOriginPurchaseWorkflow
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema
from backend.security.credentials.password_hasher import BcryptPasswordHasher
from backend.security.credentials.password_policy import PasswordPolicy
from backend.security.provisioning.installation_repository import SqliteInstallationRepository
from backend.security.provisioning.provision_installation_use_case import (
    ProvisionInstallationUseCase,
)
from backend.security.provisioning.recovery_code_repository import SqliteRecoveryCodeRepository
from backend.application.logistics.permissions import ALL_LOGISTICS_PERMISSIONS
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db

ROOT = Path(__file__).parents[3]
PASSWORD = "Correct-Horse-9!"
T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


class _Secrets:
    def __init__(self):
        self.values = {}

    def get_secret(self, key):
        return self.values.get(key)

    def set_secret(self, key, value):
        self.values[key] = value


def _db(*, seed_logistics=True, purchase_warehouse=True):
    conn = make_db()
    ProvisionInstallationUseCase(
        conn, installation_repository=SqliteInstallationRepository(conn),
        recovery_code_repository=SqliteRecoveryCodeRepository(conn),
        password_hasher=BcryptPasswordHasher(), password_policy=PasswordPolicy(),
    ).execute(company_name="SPJ", branch_name="Centro", owner_username="duena",
              workstation_name="Caja 1", owner_password=PASSWORD,
              owner_full_name="Duena Prueba", now=T0)
    if seed_logistics:
        importlib.import_module(
            "migrations.standalone.283_seed_compras_logistica_role_permissions").run(conn)
    create_inventory_schema(conn)
    if purchase_warehouse:
        branch_id = conn.execute(
            "SELECT sucursal_id FROM usuarios WHERE usuario='duena'").fetchone()[0]
        conn.execute(
            "INSERT INTO warehouses (id, code, name, branch_id, warehouse_type,"
            " allow_purchase_receipt, created_at, updated_at)"
            " VALUES (?, 'ALM-C', 'Almacén de compras', ?, 'MAIN', 1, 'x', 'x')",
            (new_uuid(), branch_id))
    conn.commit()
    # La API atiende desde el pool de hilos de FastAPI, igual que el host real
    # (`check_same_thread=False`).
    shared = sqlite3.connect(":memory:", check_same_thread=False)
    conn.backup(shared)
    conn.close()
    shared.row_factory = sqlite3.Row
    return shared


def test_real_user_logs_in_with_branch_and_purchase_warehouse():
    conn = _db()
    identity = DatabaseMobileCredentialVerifier(conn).authenticate_mobile(
        "duena", PASSWORD, "tel-1")
    assert identity is not None
    assert identity.display_name and identity.branch_name == "Centro"
    assert identity.warehouse_name == "Almacén de compras"
    assert identity.device_id == "tel-1"
    # Grafía canónica (la consulta de permisos normaliza a MAYÚSCULAS).
    assert "LOGISTICA.embarque.ver" in identity.permissions
    assert LogisticsPermissions.SHIPMENT_CREATE in identity.permissions
    assert all(p.upper().startswith("LOGISTICA") for p in identity.permissions)


def test_mobile_workflow_permission_check_ignores_case():
    """Antes las identidades llegaban en MAYÚSCULAS y `_require` comparaba
    exacto: toda acción del teléfono respondía 403."""
    upper = MobileIdentity("u", "U", "b", "B", "w", "W", "d",
                           (LogisticsPermissions.SHIPMENT_CREATE.upper(),))
    MobileOriginPurchaseWorkflow._require(upper, LogisticsPermissions.SHIPMENT_CREATE)
    with pytest.raises(HTTPException):
        MobileOriginPurchaseWorkflow._require(upper, LogisticsPermissions.CONTAINER_SCAN)


def test_wrong_password_gets_no_session():
    conn = _db()
    assert DatabaseMobileCredentialVerifier(conn).authenticate_mobile(
        "duena", "otra-clave", "tel-1") is None


def test_owner_has_full_access_on_the_phone_even_without_the_logistics_seed():
    """Auditoría de permisos 968e0bc: el dueño es acceso total. Antes su
    identidad móvil llegaba con CERO acciones (filtro por prefijo sobre `*`)."""
    conn = _db(seed_logistics=False)
    identity = DatabaseMobileCredentialVerifier(conn).authenticate_mobile(
        "duena", PASSWORD, "tel-1")
    assert identity is not None
    assert set(identity.permissions) == set(ALL_LOGISTICS_PERMISSIONS)


def test_no_logistics_permission_means_no_mobile_session():
    conn = _db(seed_logistics=False)
    conn.execute("UPDATE usuarios SET rol='cajero' WHERE usuario='duena'")
    conn.commit()
    assert DatabaseMobileCredentialVerifier(conn).authenticate_mobile(
        "duena", PASSWORD, "tel-1") is None


def test_session_endpoint_works_end_to_end_with_the_real_composition(tmp_path):
    secrets = _Secrets()
    app = service_host.build_app(_db(), secret_store=secrets, photos_dir=tmp_path)
    api = TestClient(app)
    ok = api.post("/api/mobile/session",
                  json={"username": "duena", "password": PASSWORD, "deviceId": "tel-1"})
    assert ok.status_code == 200, ok.text
    token = ok.json()["accessToken"]
    me = api.get("/api/mobile/session/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["branchName"] == "Centro"
    bad = api.post("/api/mobile/session",
                   json={"username": "duena", "password": "x", "deviceId": "tel-1"})
    assert bad.status_code == 401
    # El secreto de los tokens se genera una vez y se reutiliza.
    secret = secrets.values[service_host.SESSION_SECRET_KEY]
    service_host.build_app(_db(), secret_store=secrets, photos_dir=tmp_path)
    assert secrets.values[service_host.SESSION_SECRET_KEY] == secret


def test_without_a_purchase_warehouse_the_login_is_refused(tmp_path):
    app = service_host.build_app(_db(purchase_warehouse=False), secret_store=_Secrets(),
                                 photos_dir=tmp_path)
    r = TestClient(app).post("/api/mobile/session",
                             json={"username": "duena", "password": PASSWORD, "deviceId": "t"})
    assert r.status_code == 401


def test_default_bind_is_loopback_and_env_file_is_read(tmp_path, monkeypatch):
    for key in ("SPJ_API_BIND_HOST", "SPJ_API_PORT", "SPJ_API_SSL_CERTFILE",
                "SPJ_API_SSL_KEYFILE"):
        monkeypatch.delenv(key, raising=False)
    defaults = service_host.load_settings(tmp_path / "no_existe.env")
    assert defaults["SPJ_API_BIND_HOST"] == "127.0.0.1"
    assert defaults["SPJ_API_PORT"] == str(service_host.DEFAULT_PORT)
    env = tmp_path / "mobile_api.env"
    env.write_text("# red local\nSPJ_API_BIND_HOST=192.168.1.20\nSPJ_API_PORT=9000\n",
                   encoding="utf-8")
    cfg = service_host.load_settings(env)
    assert cfg["SPJ_API_BIND_HOST"] == "192.168.1.20" and cfg["SPJ_API_PORT"] == "9000"
    monkeypatch.setenv("SPJ_API_PORT", "9100")
    assert service_host.load_settings(env)["SPJ_API_PORT"] == "9100"


def test_photo_gateway_stores_under_a_new_id(tmp_path):
    gateway = service_host.FilePhotoGateway(tmp_path / "fotos")
    photo_id = gateway.save(content=b"jpg", file_name="a.jpg", content_type="image/jpeg",
                            actor_user_id="u", operation_id="op")
    assert (tmp_path / "fotos" / f"{photo_id}.jpg").read_bytes() == b"jpg"


def test_installer_packages_and_registers_the_optional_service():
    spec = (ROOT / "installer/windows/spj.spec").read_text(encoding="utf-8")
    iss = (ROOT / "installer/windows/spj_setup.iss").read_text(encoding="utf-8")
    assert 'name="spj_api"' in spec and "api_exe, api.binaries, api.datas" in spec
    assert 'Name: "mobile_api"' in iss
    # Opcional: sólo se registra con el componente y en alcance de máquina.
    assert "Components: mobile_api; Check: IsMachineScope" in iss
    assert 'RunOnceId: "RemoveMobileAPI"' in iss
    # Sin credenciales por omisión: ni en el host ni en el instalador.
    host = (ROOT / "backend/api/service_host.py").read_text(encoding="utf-8")
    assert "password" not in host.lower().replace("contraseña", "")
