"""BranchProfile — SET-5 (§16).

Scope note (honest, not a full cutover): the legacy `sucursales` table
already is the live, canonical branch identity referenced by FKs across
~20 other bounded contexts (sales, inventory, cash, hr, ...) — replacing
it is a dedicated cross-cutting migration, out of scope for a Settings
SET. `BranchProfile` is this bounded context's own governance record: it
carries fields `sucursales` never had (ticket_header/footer, social
links, map reference, warehouse_ids, default_workstation_profile) and is
persisted in its own new table, addressed by the *same* UUIDv7 branch id
`sucursales.id` already uses (see `backend/infrastructure/db/schema/settings_schema.py`'s
`branch_profiles.branch_id` FK) — not a competing identity.

"Las sucursales pueden sobreescribir configuraciones permitidas" (§16) is
not a field here — a branch override is just a `ConfigurationValue` at
`ScopeType.BRANCH` with this branch's id as `scope_id` (SET-2/SET-4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timezone

from backend.domain.settings.exceptions import ConfigurationInvalidValueError
from backend.domain.settings.value_objects.map_reference import MapReference
from backend.shared.ids import validate_uuidv7

_OPERATION_DAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize_operation_days(days: tuple[str, ...] | None) -> tuple[str, ...]:
    if not days:
        return ()
    normalized = tuple(dict.fromkeys(day.strip().upper() for day in days))
    invalid = [day for day in normalized if day not in _OPERATION_DAYS]
    if invalid:
        raise ConfigurationInvalidValueError(f"Días de operación inválidos: {invalid}")
    return normalized


def _normalize_uuid_tuple(values: tuple[str, ...] | None, *, field_name: str) -> tuple[str, ...]:
    if not values:
        return ()
    return tuple(validate_uuidv7(value) for value in dict.fromkeys(values))


@dataclass(slots=True)
class BranchProfile:
    id: str
    branch_id: str
    code: str
    name: str
    address: str = ""
    phone: str | None = None
    timezone: str = ""
    locale: str = ""
    opening_time: time | None = None
    closing_time: time | None = None
    operation_days: tuple[str, ...] = ()
    warehouse_ids: tuple[str, ...] = ()
    default_workstation_profile_id: str | None = None
    ticket_header: str = ""
    ticket_footer: str = ""
    social_links: dict[str, str] = field(default_factory=dict)
    map_reference: MapReference = field(default_factory=MapReference)
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    # construction ------------------------------------------------------------
    @classmethod
    def create(
        cls, *, branch_id: str, code: str, name: str, address: str = "",
        phone: str | None = None, timezone: str = "", locale: str = "",
        opening_time: time | None = None, closing_time: time | None = None,
        operation_days: tuple[str, ...] | None = None, warehouse_ids: tuple[str, ...] | None = None,
        default_workstation_profile_id: str | None = None, ticket_header: str = "",
        ticket_footer: str = "", social_links: dict[str, str] | None = None,
        map_reference: MapReference | None = None,
    ) -> "BranchProfile":
        validated_branch_id = validate_uuidv7(branch_id)
        if not code.strip():
            raise ConfigurationInvalidValueError("code es obligatorio")
        if not name.strip():
            raise ConfigurationInvalidValueError("name es obligatorio")
        if (opening_time is None) != (closing_time is None):
            raise ConfigurationInvalidValueError(
                "opening_time y closing_time deben especificarse juntos"
            )
        if opening_time is not None and closing_time is not None and closing_time <= opening_time:
            raise ConfigurationInvalidValueError("closing_time debe ser posterior a opening_time")

        return cls(
            id=validated_branch_id, branch_id=validated_branch_id, code=code.strip(),
            name=name.strip(), address=address.strip(), phone=phone,
            timezone=timezone.strip(), locale=locale.strip(),
            opening_time=opening_time, closing_time=closing_time,
            operation_days=_normalize_operation_days(operation_days),
            warehouse_ids=_normalize_uuid_tuple(warehouse_ids, field_name="warehouse_ids"),
            default_workstation_profile_id=(
                validate_uuidv7(default_workstation_profile_id)
                if default_workstation_profile_id else None
            ),
            ticket_header=ticket_header.strip(), ticket_footer=ticket_footer.strip(),
            social_links=dict(social_links or {}), map_reference=map_reference or MapReference(),
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    # behavior ------------------------------------------------------------------
    def update_profile(
        self, *, name: str | None = None, address: str | None = None,
        phone: str | None = None, timezone: str | None = None, locale: str | None = None,
    ) -> None:
        if name is not None:
            if not name.strip():
                raise ConfigurationInvalidValueError("name no puede quedar vacío")
            self.name = name.strip()
        if address is not None:
            self.address = address.strip()
        if phone is not None:
            self.phone = phone
        if timezone is not None:
            self.timezone = timezone.strip()
        if locale is not None:
            self.locale = locale.strip()
        self._touch()

    def set_operating_hours(
        self, opening_time: time | None, closing_time: time | None,
        operation_days: tuple[str, ...] | None = None,
    ) -> None:
        if (opening_time is None) != (closing_time is None):
            raise ConfigurationInvalidValueError(
                "opening_time y closing_time deben especificarse juntos"
            )
        if opening_time is not None and closing_time is not None and closing_time <= opening_time:
            raise ConfigurationInvalidValueError("closing_time debe ser posterior a opening_time")
        self.opening_time = opening_time
        self.closing_time = closing_time
        self.operation_days = _normalize_operation_days(operation_days)
        self._touch()

    def set_ticket_texts(self, *, header: str = "", footer: str = "") -> None:
        self.ticket_header = header.strip()
        self.ticket_footer = footer.strip()
        self._touch()

    def set_social_link(self, platform: str, url: str) -> None:
        if not platform.strip() or not url.strip():
            raise ConfigurationInvalidValueError("platform y url son obligatorios")
        self.social_links[platform.strip().lower()] = url.strip()
        self._touch()

    def set_map_reference(self, map_reference: MapReference) -> None:
        self.map_reference = map_reference
        self._touch()

    def assign_warehouses(self, warehouse_ids: tuple[str, ...]) -> None:
        self.warehouse_ids = _normalize_uuid_tuple(warehouse_ids, field_name="warehouse_ids")
        self._touch()

    def set_default_workstation_profile(self, workstation_profile_id: str | None) -> None:
        self.default_workstation_profile_id = (
            validate_uuidv7(workstation_profile_id) if workstation_profile_id else None
        )
        self._touch()

    def activate(self) -> None:
        self.active = True
        self._touch()

    def deactivate(self) -> None:
        self.active = False
        self._touch()
