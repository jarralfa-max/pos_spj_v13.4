from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class BrandingProfile:
    logo_b64: str = ""
    brand_name: str = "SPJ POS"
    address: str = ""
    phone: str = ""
    slogan: str = ""
    rfc: str = ""
    regimen_fiscal: str = ""


class BrandingService:
    """Source of truth for ticket branding from system config with legacy fallback."""

    def __init__(self, config_service=None, db_conn=None):
        self._config_service = config_service
        self._db_conn = db_conn

    def _get(self, key: str, default: str = "") -> str:
        try:
            if self._config_service is not None:
                v = self._config_service.get(key, default)
                return v if v not in (None, "") else default
            if self._db_conn is not None:
                row = self._db_conn.execute(
                    "SELECT valor FROM configuraciones WHERE clave=?", (key,)
                ).fetchone()
                if row and row[0] not in (None, ""):
                    return str(row[0])
        except Exception:
            return default
        return default

    def get_ticket_branding(self) -> BrandingProfile:
        # Global first, legacy ticket_* as fallback only.
        logo = self._get("brand_logo_b64", "") or self._get("logo_b64", "") or self._get("ticket_logo_b64", "")
        brand_name = self._get("brand_name", "") or self._get("nombre_empresa", "SPJ POS")
        address = self._get("brand_address", "") or self._get("direccion", "")
        phone = self._get("brand_phone", "") or self._get("telefono_empresa", "")
        slogan = self._get("brand_slogan", "") or self._get("eslogan", "")
        rfc = self._get("brand_rfc", "") or self._get("rfc", "")
        regimen = self._get("brand_regimen_fiscal", "") or self._get("regimen_fiscal", "")
        return BrandingProfile(
            logo_b64=logo,
            brand_name=brand_name,
            address=address,
            phone=phone,
            slogan=slogan,
            rfc=rfc,
            regimen_fiscal=regimen,
        )

    def enrich_legacy_ticket_data(self, ticket_data: Dict[str, Any]) -> Dict[str, Any]:
        profile = self.get_ticket_branding()
        ticket_data.setdefault("empresa", profile.brand_name)
        ticket_data.setdefault("direccion", profile.address)
        ticket_data.setdefault("telefono", profile.phone)
        return ticket_data
