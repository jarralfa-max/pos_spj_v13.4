"""Shared platform-selection factory for `SecretStoreGateway`.

Single source of truth for "which gateway backs secrets on this machine":
the Windows Credential Manager vault when available, falling back to the
cross-platform encrypted-local store otherwise. Used both by the new DI
composition root (`backend/bootstrap/wiring/shared_wiring.py`) and by
legacy `AppContainer`-based code (`core/services/configuration_settings_service.py`)
so neither has to duplicate the platform check.
"""
from __future__ import annotations

import sys

from backend.security.secrets.secret_store_gateway import SecretStoreGateway
from backend.shared.app_paths import AppPaths


def build_default_secret_store(app_paths: AppPaths | None = None) -> SecretStoreGateway:
    """Return the Windows Credential Manager gateway when usable, else the
    encrypted-local fallback."""
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
