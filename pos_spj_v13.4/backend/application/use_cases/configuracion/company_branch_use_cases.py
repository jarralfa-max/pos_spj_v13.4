"""Use cases for the "Empresa y sucursales" section of the Configuración
workspace — 5th real CRUD section (SET-5 follow-up). Thin orchestration
over `backend/domain/settings/` (SET-5): construct/mutate the entities,
persist.

`SaveCompanyProfileUseCase` deliberately treats `CompanyProfile` as a
UI-level singleton — get-or-create, never a second row — even though the
domain itself doesn't enforce that (`company_profile.py`'s own docstring:
"nothing here enforces a singleton — that stays a repository/
application-layer concern"). This IS that application-layer concern.

`RegisterBranchProfileUseCase` creates a governance record for an
EXISTING `sucursales` row — it does not create new physical branches
(that table is legacy-owned and out of scope for this SET, per
`branch_profile.py`'s own docstring).
"""

from __future__ import annotations

from datetime import time

from backend.domain.settings.entities.branch_profile import BranchProfile
from backend.domain.settings.entities.company_profile import CompanyProfile
from backend.domain.settings.exceptions import BranchProfileNotFoundError
from backend.domain.settings.value_objects.asset_reference import AssetReference
from backend.infrastructure.db.repositories.settings.branch_profile_repository import (
    SqliteBranchProfileRepository,
)
from backend.infrastructure.db.repositories.settings.company_profile_repository import (
    SqliteCompanyProfileRepository,
)


class SaveCompanyProfileUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._companies = SqliteCompanyProfileRepository(connection)

    def execute(
        self, *, legal_name: str, default_currency: str, default_timezone: str, default_locale: str,
        commercial_name: str = "", tax_id: str = "", business_name: str = "",
        fiscal_regime_reference: str = "", address: str = "", phone: str = "", email: str = "",
        website: str = "", logo_asset_id: str = "",
    ) -> CompanyProfile:
        existing = self._companies.list_active()
        if existing:
            profile = existing[0]
            profile.update_identity(
                legal_name=legal_name, default_currency=default_currency,
                default_timezone=default_timezone, default_locale=default_locale,
                commercial_name=commercial_name, tax_id=tax_id, business_name=business_name,
                fiscal_regime_reference=fiscal_regime_reference or None,
            )
            profile.update_contact_info(
                address=address, phone=phone or None, email=email or None, website=website or None,
            )
        else:
            profile = CompanyProfile.create(
                legal_name=legal_name, default_currency=default_currency,
                default_timezone=default_timezone, default_locale=default_locale,
                commercial_name=commercial_name, tax_id=tax_id, business_name=business_name,
                fiscal_regime_reference=fiscal_regime_reference or None, address=address,
                phone=phone or None, email=email or None, website=website or None,
            )

        profile.replace_logo(AssetReference.create(logo_asset_id) if logo_asset_id.strip() else None)
        self._companies.save(profile)
        self._conn.commit()
        return profile


class RegisterBranchProfileUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._branches = SqliteBranchProfileRepository(connection)

    def execute(
        self, *, branch_id: str, code: str, name: str, address: str = "", phone: str = "",
        timezone: str = "", locale: str = "", opening_time: time | None = None,
        closing_time: time | None = None, operation_days: tuple[str, ...] = (),
        ticket_header: str = "", ticket_footer: str = "",
    ) -> BranchProfile:
        profile = BranchProfile.create(
            branch_id=branch_id, code=code, name=name, address=address, phone=phone or None,
            timezone=timezone, locale=locale, opening_time=opening_time, closing_time=closing_time,
            operation_days=operation_days, ticket_header=ticket_header, ticket_footer=ticket_footer,
        )
        self._branches.save(profile)
        self._conn.commit()
        return profile


class UpdateBranchProfileUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._branches = SqliteBranchProfileRepository(connection)

    def execute(
        self, *, branch_id: str, name: str, address: str = "", phone: str = "", timezone: str = "",
        locale: str = "", opening_time: time | None = None, closing_time: time | None = None,
        operation_days: tuple[str, ...] = (), ticket_header: str = "", ticket_footer: str = "",
    ) -> BranchProfile:
        profile = self._branches.get(branch_id)
        if profile is None:
            raise BranchProfileNotFoundError(f"Perfil de sucursal {branch_id} no encontrado")
        profile.update_profile(
            name=name, address=address, phone=phone or None, timezone=timezone, locale=locale,
        )
        profile.set_operating_hours(opening_time, closing_time, operation_days)
        profile.set_ticket_texts(header=ticket_header, footer=ticket_footer)
        self._branches.save(profile)
        self._conn.commit()
        return profile
