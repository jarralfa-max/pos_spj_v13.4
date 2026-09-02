"""CompanyProfile — SET-5 (§15).

Genuinely new: unlike `BranchProfile`, there is no pre-existing "empresa"
table to reconcile with — the legacy schema only ever stored `rfc_empresa`
scattered per-branch on `sucursales` (confirmed in the SET-0 audit).
Today's installations are effectively single-company; the schema doesn't
assume that (§ "multiempresa futuro"), but nothing here enforces a
singleton — that stays a repository/application-layer concern.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.settings.exceptions import ConfigurationInvalidValueError
from backend.domain.settings.value_objects.asset_reference import AssetReference
from backend.shared.ids import new_uuid

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")
_LOCALE_PATTERN = re.compile(r"^[a-z]{2}-[A-Z]{2}$")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _validate_currency(default_currency: str) -> str:
    currency = default_currency.strip().upper()
    if not _CURRENCY_PATTERN.match(currency):
        raise ConfigurationInvalidValueError(
            f"default_currency debe ser un código ISO 4217 de 3 letras, recibido {default_currency!r}"
        )
    return currency


def _validate_locale(default_locale: str) -> str:
    locale = default_locale.strip()
    if not _LOCALE_PATTERN.match(locale):
        raise ConfigurationInvalidValueError(
            f"default_locale debe tener forma 'xx-XX' (p. ej. 'es-MX'), recibido {default_locale!r}"
        )
    return locale


@dataclass(slots=True)
class CompanyProfile:
    id: str
    legal_name: str
    default_currency: str
    default_timezone: str
    default_locale: str
    commercial_name: str = ""
    tax_id: str = ""
    business_name: str = ""
    logo_asset: AssetReference | None = None
    address: str = ""
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    social_networks: dict[str, str] = field(default_factory=dict)
    fiscal_regime_reference: str | None = None
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    # construction ------------------------------------------------------------
    @classmethod
    def create(
        cls, *, legal_name: str, default_currency: str, default_timezone: str,
        default_locale: str, commercial_name: str = "", tax_id: str = "",
        business_name: str = "", logo_asset: AssetReference | None = None,
        address: str = "", phone: str | None = None, email: str | None = None,
        website: str | None = None, social_networks: dict[str, str] | None = None,
        fiscal_regime_reference: str | None = None,
    ) -> "CompanyProfile":
        if not legal_name.strip():
            raise ConfigurationInvalidValueError("legal_name es obligatorio")
        currency = _validate_currency(default_currency)
        if not default_timezone.strip():
            raise ConfigurationInvalidValueError("default_timezone es obligatorio (IANA, p. ej. 'America/Mexico_City')")
        locale = _validate_locale(default_locale)
        if email is not None and email.strip() and not _EMAIL_PATTERN.match(email.strip()):
            raise ConfigurationInvalidValueError(f"email inválido: {email!r}")
        if website is not None and website.strip() and not website.strip().lower().startswith(("http://", "https://")):
            raise ConfigurationInvalidValueError(f"website debe iniciar con http:// o https://, recibido {website!r}")

        return cls(
            id=new_uuid(), legal_name=legal_name.strip(), default_currency=currency,
            default_timezone=default_timezone.strip(), default_locale=locale,
            commercial_name=commercial_name.strip(), tax_id=tax_id.strip(),
            business_name=business_name.strip(), logo_asset=logo_asset, address=address.strip(),
            phone=phone, email=email.strip() if email else None,
            website=website.strip() if website else None,
            social_networks=dict(social_networks or {}),
            fiscal_regime_reference=(fiscal_regime_reference.strip() if fiscal_regime_reference else None),
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    # behavior ------------------------------------------------------------------
    def update_identity(
        self, *, legal_name: str, default_currency: str, default_timezone: str, default_locale: str,
        commercial_name: str = "", tax_id: str = "", business_name: str = "",
        fiscal_regime_reference: str | None = None,
    ) -> None:
        """SET-25 follow-up: `create()` validated these 8 fields but
        there was no way to change any of them afterward — every other
        field had an update method except the identity/locale ones. Same
        validation `create()` already applies, factored into
        `_validate_currency`/`_validate_locale` so both stay in sync."""
        if not legal_name.strip():
            raise ConfigurationInvalidValueError("legal_name es obligatorio")
        currency = _validate_currency(default_currency)
        if not default_timezone.strip():
            raise ConfigurationInvalidValueError("default_timezone es obligatorio (IANA, p. ej. 'America/Mexico_City')")
        locale = _validate_locale(default_locale)
        self.legal_name = legal_name.strip()
        self.default_currency = currency
        self.default_timezone = default_timezone.strip()
        self.default_locale = locale
        self.commercial_name = commercial_name.strip()
        self.tax_id = tax_id.strip()
        self.business_name = business_name.strip()
        self.fiscal_regime_reference = fiscal_regime_reference.strip() if fiscal_regime_reference else None
        self._touch()

    def update_contact_info(
        self, *, address: str | None = None, phone: str | None = None,
        email: str | None = None, website: str | None = None,
    ) -> None:
        if email is not None and email.strip() and not _EMAIL_PATTERN.match(email.strip()):
            raise ConfigurationInvalidValueError(f"email inválido: {email!r}")
        if address is not None:
            self.address = address.strip()
        if phone is not None:
            self.phone = phone
        if email is not None:
            self.email = email.strip() or None
        if website is not None:
            self.website = website.strip() or None
        self._touch()

    def replace_logo(self, logo_asset: AssetReference | None) -> None:
        self.logo_asset = logo_asset
        self._touch()

    def set_social_network(self, platform: str, url: str) -> None:
        if not platform.strip() or not url.strip():
            raise ConfigurationInvalidValueError("platform y url son obligatorios")
        self.social_networks[platform.strip().lower()] = url.strip()
        self._touch()

    def activate(self) -> None:
        self.active = True
        self._touch()

    def deactivate(self) -> None:
        self.active = False
        self._touch()
