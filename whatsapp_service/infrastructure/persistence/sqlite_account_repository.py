# infrastructure/persistence/sqlite_account_repository.py — WA-4
"""Implementación SQLite de `WhatsAppAccountRepository` y
`WhatsAppProviderConfigurationRepository` (domain/whatsapp/repository_ports.py)
contra `whatsapp_business_accounts`/`whatsapp_provider_configurations`
(migración 243)."""
from __future__ import annotations

import json
from datetime import datetime
from typing import List, Optional

from domain.whatsapp.entities.business_account import (
    WhatsAppBusinessAccount,
    WhatsAppProviderConfiguration,
)
from domain.whatsapp.enums import AccountStatus, WhatsAppProvider

_ACCOUNT_COLUMNS = (
    "id, provider, business_account_external_id, display_name, status, "
    "secret_reference_id, created_at, updated_at"
)


def _account_from_row(row) -> WhatsAppBusinessAccount:
    return WhatsAppBusinessAccount(
        id=row[0],
        provider=WhatsAppProvider(row[1]),
        business_account_external_id=row[2],
        display_name=row[3],
        status=AccountStatus(row[4]),
        secret_reference_id=row[5],
        created_at=datetime.fromisoformat(row[6]),
        updated_at=datetime.fromisoformat(row[7]),
    )


class SqliteWhatsAppAccountRepository:
    """Implementa `WhatsAppAccountRepository`."""

    def __init__(self, conn) -> None:
        self._conn = conn

    def get_by_id(self, account_id: str) -> Optional[WhatsAppBusinessAccount]:
        row = self._conn.execute(
            f"SELECT {_ACCOUNT_COLUMNS} FROM whatsapp_business_accounts WHERE id=?",
            (account_id,),
        ).fetchone()
        return _account_from_row(row) if row else None

    def get_by_external_id(self, external_id: str) -> Optional[WhatsAppBusinessAccount]:
        row = self._conn.execute(
            f"SELECT {_ACCOUNT_COLUMNS} FROM whatsapp_business_accounts "
            "WHERE business_account_external_id=?",
            (external_id,),
        ).fetchone()
        return _account_from_row(row) if row else None

    def list_active(self) -> List[WhatsAppBusinessAccount]:
        rows = self._conn.execute(
            f"SELECT {_ACCOUNT_COLUMNS} FROM whatsapp_business_accounts "
            "WHERE status IN ('ACTIVE','DEGRADED') ORDER BY created_at"
        ).fetchall()
        return [_account_from_row(row) for row in rows]

    def save(self, account: WhatsAppBusinessAccount) -> None:
        self._conn.execute(
            "INSERT INTO whatsapp_business_accounts "
            f"({_ACCOUNT_COLUMNS}) VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "provider=excluded.provider, "
            "business_account_external_id=excluded.business_account_external_id, "
            "display_name=excluded.display_name, "
            "status=excluded.status, "
            "secret_reference_id=excluded.secret_reference_id, "
            "updated_at=excluded.updated_at",
            (
                account.id,
                account.provider.value,
                account.business_account_external_id,
                account.display_name,
                account.status.value,
                account.secret_reference_id,
                account.created_at.isoformat(),
                account.updated_at.isoformat(),
            ),
        )
        self._conn.commit()


_CONFIG_COLUMNS = (
    "id, account_id, provider, api_version, extra_settings_json, created_at, updated_at"
)


def _configuration_from_row(row) -> WhatsAppProviderConfiguration:
    return WhatsAppProviderConfiguration(
        id=row[0],
        account_id=row[1],
        provider=WhatsAppProvider(row[2]),
        api_version=row[3],
        extra_settings=json.loads(row[4]) if row[4] else {},
        created_at=datetime.fromisoformat(row[5]),
        updated_at=datetime.fromisoformat(row[6]),
    )


class SqliteWhatsAppProviderConfigurationRepository:
    """Implementa `WhatsAppProviderConfigurationRepository`."""

    def __init__(self, conn) -> None:
        self._conn = conn

    def get_by_account_id(self, account_id: str) -> Optional[WhatsAppProviderConfiguration]:
        row = self._conn.execute(
            f"SELECT {_CONFIG_COLUMNS} FROM whatsapp_provider_configurations WHERE account_id=?",
            (account_id,),
        ).fetchone()
        return _configuration_from_row(row) if row else None

    def save(self, configuration: WhatsAppProviderConfiguration) -> None:
        self._conn.execute(
            "INSERT INTO whatsapp_provider_configurations "
            f"({_CONFIG_COLUMNS}) VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "provider=excluded.provider, "
            "api_version=excluded.api_version, "
            "extra_settings_json=excluded.extra_settings_json, "
            "updated_at=excluded.updated_at",
            (
                configuration.id,
                configuration.account_id,
                configuration.provider.value,
                configuration.api_version,
                json.dumps(configuration.extra_settings, ensure_ascii=False),
                configuration.created_at.isoformat(),
                configuration.updated_at.isoformat(),
            ),
        )
        self._conn.commit()
