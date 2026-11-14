"""Shared platform-selection factory for `SecretStoreGateway`.

Single source of truth for "which gateway backs secrets on this machine":
the Windows Credential Manager vault when available, falling back to the
cross-platform encrypted-local store otherwise. Used both by the new DI
composition root (`backend/bootstrap/wiring/shared_wiring.py`) and by
legacy `AppContainer`-based code (`core/services/configuration_settings_service.py`)
so neither has to duplicate the platform check.

A machine-wide installation uses the encrypted-local store instead: Credential
Manager is one vault per Windows user, and a station has several users plus a
service account. Secrets saved earlier live in the vault of whoever saved them:
each Windows user's are copied ONCE, without overwriting and without emptying the
vault, which keeps them available if the station goes back to a previous version.
"""
from __future__ import annotations

import getpass
import hashlib
import logging
import sys

from backend.security.secrets.secret_store_gateway import SecretStoreGateway
from backend.shared.app_paths import AppPaths
from backend.shared.install_config import InstallConfigError

logger = logging.getLogger("spj.security.secrets")


def current_windows_user() -> str:
    return getpass.getuser()


def _import_user_vault(store: SecretStoreGateway, paths: AppPaths) -> None:
    from backend.security.secrets.windows_credential_manager_secret_store import (
        WindowsCredentialManagerSecretStore,
    )

    user = hashlib.sha256(current_windows_user().encode("utf-8")).hexdigest()[:16]
    marker = paths.user_data_dir / "secrets" / f"vault-imported-{user}"
    if marker.exists():
        return
    try:
        vault = WindowsCredentialManagerSecretStore()
        for reference in vault.list_references():
            name = reference.reference_id
            value = vault.get_secret(name)
            if value and store.describe(name) is None:
                store.set_secret(name, value)
    except Exception:
        logger.exception("No se pudieron traer los secretos del Administrador de credenciales.")
        return  # se reintenta en el siguiente arranque
    marker.write_text("imported", encoding="utf-8")


def _machine_wide(app_paths: AppPaths | None) -> AppPaths | None:
    try:
        paths = app_paths or AppPaths.from_environment()
    except InstallConfigError:
        return None
    return paths if paths.machine_scope else None


def build_default_secret_store(app_paths: AppPaths | None = None) -> SecretStoreGateway:
    """The shared encrypted-local store on a machine-wide installation;
    otherwise the Windows Credential Manager gateway when usable, else the
    encrypted-local fallback."""
    machine_paths = _machine_wide(app_paths)
    if machine_paths is not None:
        from backend.security.secrets.encrypted_local_secret_store import EncryptedLocalSecretStore

        store = EncryptedLocalSecretStore(app_paths=machine_paths)
        if sys.platform == "win32":
            _import_user_vault(store, machine_paths)
        return store

    if sys.platform == "win32":
        try:
            from backend.security.secrets.windows_credential_manager_secret_store import (
                WindowsCredentialManagerSecretStore,
            )

            return WindowsCredentialManagerSecretStore()
        except Exception:
            pass  # fall through to the cross-platform encrypted-local store

    from backend.security.secrets.encrypted_local_secret_store import EncryptedLocalSecretStore

    return EncryptedLocalSecretStore(app_paths=app_paths or AppPaths.from_environment())
