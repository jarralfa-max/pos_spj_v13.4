"""Use cases for the "Notificaciones" section (Accounts/Templates/
Channels/Routing) — SET-20 cutover. Same shape as
`integration_management_use_cases.py`: thin orchestration over
`backend/domain/notifications/` (SET-20), construct/mutate the entity,
persist.

`CreateNotificationTemplateUseCase` checks `code`+`channel` occupancy
BEFORE inserting (never lets `UNIQUE(code, channel)` reach the UI as a
raw `IntegrityError`). `AssignNotificationRouteUseCase` (create) checks
`event_code` occupancy the same way — same discipline
`AssignCampaignPlacementUseCase` (SET-18) already established for
`ux_campaign_placements_slot_active`.
"""

from __future__ import annotations

from enum import Enum

from backend.domain.notifications.entities.notification_account import NotificationAccount
from backend.domain.notifications.entities.notification_route import NotificationRoute
from backend.domain.notifications.entities.notification_template import NotificationTemplate
from backend.domain.notifications.enums import NotificationChannel
from backend.domain.notifications.exceptions import (
    NotificationAccountNotFoundError,
    NotificationRouteEventCodeOccupiedError,
    NotificationRouteNotFoundError,
    NotificationTemplateCodeChannelOccupiedError,
    NotificationTemplateNotFoundError,
)
from backend.infrastructure.db.repositories.notifications.notification_account_repository import (
    SqliteNotificationAccountRepository,
)
from backend.infrastructure.db.repositories.notifications.notification_route_repository import (
    SqliteNotificationRouteRepository,
)
from backend.infrastructure.db.repositories.notifications.notification_template_repository import (
    SqliteNotificationTemplateRepository,
)


class NotificationAccountStatusAction(str, Enum):
    ACTIVATE = "ACTIVATE"
    DEACTIVATE = "DEACTIVATE"


class NotificationTemplateStatusAction(str, Enum):
    ACTIVATE = "ACTIVATE"
    DEACTIVATE = "DEACTIVATE"


class NotificationRouteStatusAction(str, Enum):
    ACTIVATE = "ACTIVATE"
    DEACTIVATE = "DEACTIVATE"


# ── NotificationAccount ──────────────────────────────────────────────────────

class CreateNotificationAccountUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._accounts = SqliteNotificationAccountRepository(connection)

    def execute(
        self, *, channel: NotificationChannel | str, name: str, credential_reference: str | None = None,
        integration_instance_id: str | None = None,
    ) -> NotificationAccount:
        account = NotificationAccount.create(
            channel=NotificationChannel(channel), name=name, credential_reference=credential_reference,
            integration_instance_id=integration_instance_id,
        )
        self._accounts.save(account)
        self._conn.commit()
        return account


class UpdateNotificationAccountUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._accounts = SqliteNotificationAccountRepository(connection)

    def execute(self, *, account_id: str, name: str, credential_reference: str | None = None) -> NotificationAccount:
        account = self._accounts.get(account_id)
        if account is None:
            raise NotificationAccountNotFoundError(f"Cuenta {account_id} no encontrada")
        account.update_details(name=name, credential_reference=credential_reference)
        self._accounts.save(account)
        self._conn.commit()
        return account


class ChangeNotificationAccountStatusUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._accounts = SqliteNotificationAccountRepository(connection)

    def execute(self, *, account_id: str, action: NotificationAccountStatusAction) -> NotificationAccount:
        account = self._accounts.get(account_id)
        if account is None:
            raise NotificationAccountNotFoundError(f"Cuenta {account_id} no encontrada")

        if action is NotificationAccountStatusAction.ACTIVATE:
            account.activate()
        elif action is NotificationAccountStatusAction.DEACTIVATE:
            account.deactivate()

        self._accounts.save(account)
        self._conn.commit()
        return account


# ── NotificationTemplate ─────────────────────────────────────────────────────

class CreateNotificationTemplateUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._templates = SqliteNotificationTemplateRepository(connection)

    def execute(
        self, *, code: str, channel: NotificationChannel | str, language: str,
        parameter_names: tuple[str, ...] | list[str] = (),
    ) -> NotificationTemplate:
        channel_enum = NotificationChannel(channel)
        existing = self._templates.get_by_code(code)
        if existing is not None and existing.channel is channel_enum:
            raise NotificationTemplateCodeChannelOccupiedError(
                f"Ya existe una plantilla {code!r} para el canal {channel_enum.value!r}"
            )
        template = NotificationTemplate.create(
            code=code, channel=channel_enum, language=language, parameter_names=parameter_names,
        )
        self._templates.save(template)
        self._conn.commit()
        return template


class UpdateNotificationTemplateUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._templates = SqliteNotificationTemplateRepository(connection)

    def execute(
        self, *, template_id: str, parameter_names: tuple[str, ...] | list[str] = (),
    ) -> NotificationTemplate:
        template = self._templates.get(template_id)
        if template is None:
            raise NotificationTemplateNotFoundError(f"Plantilla {template_id} no encontrada")
        template.update_parameter_names(parameter_names)
        self._templates.save(template)
        self._conn.commit()
        return template


class ChangeNotificationTemplateStatusUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._templates = SqliteNotificationTemplateRepository(connection)

    def execute(self, *, template_id: str, action: NotificationTemplateStatusAction) -> NotificationTemplate:
        template = self._templates.get(template_id)
        if template is None:
            raise NotificationTemplateNotFoundError(f"Plantilla {template_id} no encontrada")

        if action is NotificationTemplateStatusAction.ACTIVATE:
            template.activate()
        elif action is NotificationTemplateStatusAction.DEACTIVATE:
            template.deactivate()

        self._templates.save(template)
        self._conn.commit()
        return template


# ── NotificationRoute ────────────────────────────────────────────────────────

class CreateNotificationRouteUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._routes = SqliteNotificationRouteRepository(connection)
        self._templates = SqliteNotificationTemplateRepository(connection)
        self._accounts = SqliteNotificationAccountRepository(connection)

    def execute(
        self, *, event_code: str, channel: NotificationChannel | str, template_id: str, account_id: str,
    ) -> NotificationRoute:
        if self._templates.get(template_id) is None:
            raise NotificationTemplateNotFoundError(f"Plantilla {template_id} no encontrada")
        if self._accounts.get(account_id) is None:
            raise NotificationAccountNotFoundError(f"Cuenta {account_id} no encontrada")
        existing = [r for r in self._routes.list_by_event_code(event_code) if r.active]
        if existing:
            raise NotificationRouteEventCodeOccupiedError(
                f"El evento {event_code!r} ya tiene una ruta activa; desactívala primero"
            )
        route = NotificationRoute.create(
            event_code=event_code, channel=NotificationChannel(channel), template_id=template_id,
            account_id=account_id,
        )
        self._routes.save(route)
        self._conn.commit()
        return route


class ChangeNotificationRouteStatusUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._routes = SqliteNotificationRouteRepository(connection)

    def execute(self, *, route_id: str, action: NotificationRouteStatusAction) -> NotificationRoute:
        route = self._routes.get(route_id)
        if route is None:
            raise NotificationRouteNotFoundError(f"Ruta {route_id} no encontrada")

        if action is NotificationRouteStatusAction.ACTIVATE:
            occupant = next(
                (r for r in self._routes.list_by_event_code(route.event_code) if r.active and r.id != route.id),
                None,
            )
            if occupant is not None:
                raise NotificationRouteEventCodeOccupiedError(
                    f"El evento {route.event_code!r} ya tiene una ruta activa; desactívala primero"
                )
            route.activate()
        elif action is NotificationRouteStatusAction.DEACTIVATE:
            route.deactivate()

        self._routes.save(route)
        self._conn.commit()
        return route
