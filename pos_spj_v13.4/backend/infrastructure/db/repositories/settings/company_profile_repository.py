"""SqliteCompanyProfileRepository — persists `CompanyProfile` (SET-5).
Implements
`backend.domain.settings.repository_ports.CompanyProfileRepositoryPort`.
"""

from __future__ import annotations

import json

from backend.domain.settings.entities.company_profile import CompanyProfile
from backend.domain.settings.value_objects.asset_reference import AssetReference
from backend.infrastructure.db.repositories.settings.base import SettingsRepositoryBase

_COLS = (
    "id, legal_name, commercial_name, tax_id, business_name, logo_asset_id, address,"
    " phone, email, website, social_networks_json, default_currency, default_timezone,"
    " default_locale, fiscal_regime_reference, active, created_at, updated_at"
)


class SqliteCompanyProfileRepository(SettingsRepositoryBase):
    def save(self, profile: CompanyProfile) -> None:
        self._execute(
            f"INSERT INTO company_profiles ({_COLS})"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET"
            " legal_name=excluded.legal_name, commercial_name=excluded.commercial_name,"
            " tax_id=excluded.tax_id, business_name=excluded.business_name,"
            " logo_asset_id=excluded.logo_asset_id, address=excluded.address,"
            " phone=excluded.phone, email=excluded.email, website=excluded.website,"
            " social_networks_json=excluded.social_networks_json,"
            " default_currency=excluded.default_currency,"
            " default_timezone=excluded.default_timezone, default_locale=excluded.default_locale,"
            " fiscal_regime_reference=excluded.fiscal_regime_reference, active=excluded.active,"
            " updated_at=excluded.updated_at",
            self._params(profile),
        )

    def get(self, profile_id: str) -> CompanyProfile | None:
        row = self._query_one(f"SELECT {_COLS} FROM company_profiles WHERE id=?", (profile_id,))
        return self._hydrate(row) if row else None

    def list_active(self) -> list[CompanyProfile]:
        rows = self._query(f"SELECT {_COLS} FROM company_profiles WHERE active=1 ORDER BY legal_name")
        return [self._hydrate(row) for row in rows]

    # helpers -----------------------------------------------------------------
    @staticmethod
    def _params(profile: CompanyProfile) -> tuple:
        return (
            profile.id, profile.legal_name, profile.commercial_name, profile.tax_id,
            profile.business_name, profile.logo_asset.asset_id if profile.logo_asset else None,
            profile.address, profile.phone, profile.email, profile.website,
            json.dumps(profile.social_networks), profile.default_currency,
            profile.default_timezone, profile.default_locale, profile.fiscal_regime_reference,
            int(profile.active), profile.created_at, profile.updated_at,
        )

    @staticmethod
    def _hydrate(row: dict) -> CompanyProfile:
        return CompanyProfile(
            id=row["id"], legal_name=row["legal_name"], commercial_name=row["commercial_name"] or "",
            tax_id=row["tax_id"] or "", business_name=row["business_name"] or "",
            logo_asset=AssetReference(row["logo_asset_id"]) if row["logo_asset_id"] else None,
            address=row["address"] or "", phone=row["phone"], email=row["email"],
            website=row["website"], social_networks=json.loads(row["social_networks_json"] or "{}"),
            default_currency=row["default_currency"], default_timezone=row["default_timezone"],
            default_locale=row["default_locale"], fiscal_regime_reference=row["fiscal_regime_reference"],
            active=bool(row["active"]), created_at=row["created_at"], updated_at=row["updated_at"],
        )
