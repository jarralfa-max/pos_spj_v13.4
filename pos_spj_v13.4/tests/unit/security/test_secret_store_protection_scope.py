"""SDLC-ARQ-INST-003 — la llave maestra nunca queda en claro, y su protección
corresponde al modo de instalación.

Las PCs de sucursal tienen varios usuarios de Windows: en una instalación de
máquina lo guardado por uno lo tiene que poder leer otro (y el servicio local).
DPAPI y Credential Manager son dobles que imitan esa regla por usuario.
"""
from __future__ import annotations

import sys
import types

from cryptography.fernet import Fernet
import pytest

from backend.security.secrets import default_secret_store, encrypted_local_secret_store as module
from backend.security.secrets.default_secret_store import build_default_secret_store
from backend.security.secrets.encrypted_local_secret_store import (
    CRYPTPROTECT_LOCAL_MACHINE,
    EncryptedLocalSecretStore,
)
from backend.security.secrets.errors import SecretStoreUnavailableError
from backend.security.secrets.secret_store_gateway import SecretReference
from backend.shared.app_paths import LAYOUT_INSTALLED, AppPaths
from backend.shared.install_config import DATA_SCOPE_MACHINE, DATA_SCOPE_USER, InstallConfig


class Dpapi:
    """Imita DPAPI: sin LOCAL_MACHINE, sólo descifra el usuario que cifró."""

    def __init__(self) -> None:
        self.user = "ana"
        self.flags: list[int] = []

    def module(self):
        fake = types.ModuleType("win32crypt")
        fake.CryptProtectData = self.protect
        fake.CryptUnprotectData = self.unprotect
        return fake

    def protect(self, data, description, entropy, reserved, prompt, flags):
        self.flags.append(flags)
        owner = "*" if flags & CRYPTPROTECT_LOCAL_MACHINE else self.user
        return b"DPAPI|" + owner.encode() + b"|" + data[::-1]

    def unprotect(self, blob, entropy, reserved, prompt, flags):
        marker, owner, data = blob.split(b"|", 2)
        if marker != b"DPAPI" or owner.decode() not in {"*", self.user}:
            raise OSError("no se puede descifrar")
        return "descripcion", data[::-1]


@pytest.fixture()
def dpapi(monkeypatch):
    fake = Dpapi()
    monkeypatch.setitem(sys.modules, "win32crypt", fake.module())
    monkeypatch.setattr(module.sys, "platform", "win32")
    return fake


def _paths(tmp_path, scope=DATA_SCOPE_MACHINE) -> AppPaths:
    return AppPaths(base_dir=tmp_path / "app", data_dir=tmp_path / "data",
                    layout=LAYOUT_INSTALLED, install_config=InstallConfig(data_scope=scope))


def _store(tmp_path, *, machine: bool) -> EncryptedLocalSecretStore:
    return EncryptedLocalSecretStore(store_dir=tmp_path / "s", machine_scope=machine)


# ── nunca en claro ─────────────────────────────────────────────────────────
def test_without_os_protection_the_key_is_never_written(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "win32crypt", None)
    monkeypatch.setattr(module.sys, "platform", "win32")
    with pytest.raises(SecretStoreUnavailableError):
        _store(tmp_path, machine=False)
    assert not (tmp_path / "s" / "master.key").exists()


def test_existing_key_is_not_used_without_os_protection(tmp_path, monkeypatch, dpapi):
    _store(tmp_path, machine=False)
    monkeypatch.setitem(sys.modules, "win32crypt", None)
    with pytest.raises(SecretStoreUnavailableError):
        _store(tmp_path, machine=False)


def test_key_left_in_clear_gets_protected_and_keeps_opening_the_secrets(tmp_path, dpapi):
    folder = tmp_path / "s"
    folder.mkdir()
    key = Fernet.generate_key()
    (folder / "master.key").write_bytes(key)
    (folder / "secret_store.enc.json").write_text(
        '{"pagos": {"ciphertext": "%s", "created_at": "x", "last_rotated_at": "x"}}'
        % Fernet(key).encrypt(b"sk_live").decode("ascii"), encoding="utf-8")

    store = _store(tmp_path, machine=False)

    assert store.get_secret("pagos") == "sk_live"
    assert key not in (folder / "master.key").read_bytes()


# ── ámbito ─────────────────────────────────────────────────────────────────
def test_machine_install_protects_for_the_machine(tmp_path, dpapi):
    _store(tmp_path, machine=True).set_secret("pagos", "sk_live")
    assert dpapi.flags == [CRYPTPROTECT_LOCAL_MACHINE]
    dpapi.user = "beto"
    assert _store(tmp_path, machine=True).get_secret("pagos") == "sk_live"


def test_user_install_protects_for_the_user(tmp_path, dpapi):
    _store(tmp_path, machine=False)
    assert dpapi.flags == [0]


def test_scope_comes_from_the_installation(tmp_path, dpapi):
    EncryptedLocalSecretStore(app_paths=_paths(tmp_path))
    EncryptedLocalSecretStore(app_paths=_paths(tmp_path / "u", DATA_SCOPE_USER))
    assert dpapi.flags == [CRYPTPROTECT_LOCAL_MACHINE, 0]


def test_key_of_one_user_is_opened_to_the_machine_when_that_user_starts(tmp_path, dpapi):
    _store(tmp_path, machine=False).set_secret("pagos", "sk_live")
    _store(tmp_path, machine=True)  # Ana abre la versión nueva
    assert dpapi.flags == [0, CRYPTPROTECT_LOCAL_MACHINE]
    _store(tmp_path, machine=True)
    assert len(dpapi.flags) == 2  # una sola vez
    dpapi.user = "beto"
    assert _store(tmp_path, machine=True).get_secret("pagos") == "sk_live"


def test_other_users_key_with_nothing_stored_is_replaced(tmp_path, dpapi):
    # La revisión de salud creaba una llave por usuario en cada estación.
    _store(tmp_path, machine=False)
    dpapi.user = "beto"
    store = _store(tmp_path, machine=True)
    store.set_secret("pagos", "sk_live")
    dpapi.user = "ana"
    assert _store(tmp_path, machine=True).get_secret("pagos") == "sk_live"


def test_other_users_key_with_secrets_fails_closed_and_is_kept(tmp_path, dpapi):
    _store(tmp_path, machine=False).set_secret("pagos", "sk_live")
    original = (tmp_path / "s" / "master.key").read_bytes()
    dpapi.user = "beto"
    with pytest.raises(SecretStoreUnavailableError):
        _store(tmp_path, machine=True)
    assert (tmp_path / "s" / "master.key").read_bytes() == original


# ── qué almacén le toca a cada instalación ─────────────────────────────────
class Vault:
    """Credential Manager: un cofre por usuario de Windows."""

    def __init__(self) -> None:
        self.by_user = {"ana": {"whatsapp": "wa_token", "pagos": "sk_viejo"}, "beto": {}}
        self.user = "ana"

    @property
    def mine(self) -> dict:
        return self.by_user[self.user]

    def list_references(self):
        return [SecretReference(name, "****", "", "ACTIVE") for name in self.mine]

    def get_secret(self, name):
        return self.mine.get(name)


@pytest.fixture()
def vault(monkeypatch, dpapi):
    fake = Vault()
    credential_manager = types.ModuleType("win32cred")
    monkeypatch.setitem(sys.modules, "win32cred", credential_manager)
    from backend.security.secrets import windows_credential_manager_secret_store as vault_module

    monkeypatch.setattr(vault_module, "WindowsCredentialManagerSecretStore", lambda: fake)
    monkeypatch.setattr(default_secret_store.sys, "platform", "win32")
    monkeypatch.setattr(default_secret_store, "current_windows_user", lambda: fake.user)
    return fake


def test_machine_install_shares_one_store_between_windows_users(tmp_path, vault, dpapi):
    paths = _paths(tmp_path)
    store = build_default_secret_store(paths)
    assert isinstance(store, EncryptedLocalSecretStore)
    store.set_secret("nuevo", "valor")

    vault.user = dpapi.user = "beto"
    assert build_default_secret_store(paths).get_secret("nuevo") == "valor"


def test_user_install_keeps_credential_manager(tmp_path, vault):
    assert build_default_secret_store(_paths(tmp_path, DATA_SCOPE_USER)) is vault


def test_secrets_saved_in_the_vault_are_not_lost_on_a_machine_install(tmp_path, vault, dpapi):
    paths = _paths(tmp_path)
    assert build_default_secret_store(paths).get_secret("whatsapp") == "wa_token"
    vault.user = dpapi.user = "beto"  # otro usuario ve lo que guardó Ana
    assert build_default_secret_store(paths).get_secret("whatsapp") == "wa_token"
    assert "whatsapp" in vault.by_user["ana"]  # el cofre no se vacía: permite volver atrás


def test_vault_import_does_not_overwrite_nor_resurrect(tmp_path, vault, dpapi):
    paths = _paths(tmp_path)
    store = build_default_secret_store(paths)
    store.set_secret("pagos", "sk_rotado")
    store.delete_secret("whatsapp")

    store = build_default_secret_store(paths)

    assert store.get_secret("pagos") == "sk_rotado"
    assert store.get_secret("whatsapp") is None


def test_each_windows_user_imports_their_own_vault(tmp_path, vault, dpapi):
    paths = _paths(tmp_path)
    build_default_secret_store(paths)
    vault.by_user["beto"] = {"mapbox": "pk_beto", "pagos": "sk_de_beto"}
    vault.user = dpapi.user = "beto"
    store = build_default_secret_store(paths)
    assert store.get_secret("mapbox") == "pk_beto"
    assert store.get_secret("pagos") == "sk_viejo"  # no pisa lo que ya estaba


def test_vault_failure_is_retried_on_the_next_start(tmp_path, vault):
    paths = _paths(tmp_path)
    good = vault.list_references
    vault.list_references = lambda: (_ for _ in ()).throw(OSError("cofre ocupado"))
    assert build_default_secret_store(paths).get_secret("whatsapp") is None
    vault.list_references = good
    assert build_default_secret_store(paths).get_secret("whatsapp") == "wa_token"
