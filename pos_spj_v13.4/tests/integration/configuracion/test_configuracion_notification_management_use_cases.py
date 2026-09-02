"""SET-20 cutover — real CRUD for the "Notificaciones" section
(Accounts/Templates/Routing). Against a real (in-memory) SQLite
born-clean schema.
"""

from __future__ import annotations

import pytest

from backend.application.use_cases.configuracion.notification_management_use_cases import (
    ChangeNotificationAccountStatusUseCase,
    ChangeNotificationRouteStatusUseCase,
    ChangeNotificationTemplateStatusUseCase,
    CreateNotificationAccountUseCase,
    CreateNotificationRouteUseCase,
    CreateNotificationTemplateUseCase,
    NotificationAccountStatusAction,
    NotificationRouteStatusAction,
    NotificationTemplateStatusAction,
    UpdateNotificationAccountUseCase,
    UpdateNotificationTemplateUseCase,
)
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
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


def _account(conn, **overrides):
    kwargs = dict(channel=NotificationChannel.WHATSAPP, name="WA principal", credential_reference="wa_token")
    kwargs.update(overrides)
    return CreateNotificationAccountUseCase(conn).execute(**kwargs)


def _template(conn, **overrides):
    kwargs = dict(
        code="pedido_confirmado", channel=NotificationChannel.WHATSAPP, language="es_MX",
        parameter_names=("folio", "total"),
    )
    kwargs.update(overrides)
    return CreateNotificationTemplateUseCase(conn).execute(**kwargs)


class TestNotificationAccountUseCases:
    def test_create_persists(self, conn):
        account = _account(conn)
        assert SqliteNotificationAccountRepository(conn).get(account.id) is not None

    def test_update_persists(self, conn):
        account = _account(conn)
        updated = UpdateNotificationAccountUseCase(conn).execute(
            account_id=account.id, name="Nuevo nombre", credential_reference="nuevo_token")
        assert updated.name == "Nuevo nombre"
        assert SqliteNotificationAccountRepository(conn).get(account.id).credential_reference == "nuevo_token"

    def test_update_unknown_raises(self, conn):
        with pytest.raises(NotificationAccountNotFoundError):
            UpdateNotificationAccountUseCase(conn).execute(account_id=new_uuid(), name="X")

    def test_change_status_activate_deactivate(self, conn):
        account = _account(conn)
        use_case = ChangeNotificationAccountStatusUseCase(conn)
        deactivated = use_case.execute(account_id=account.id, action=NotificationAccountStatusAction.DEACTIVATE)
        assert deactivated.active is False
        activated = use_case.execute(account_id=account.id, action=NotificationAccountStatusAction.ACTIVATE)
        assert activated.active is True


class TestNotificationTemplateUseCases:
    def test_create_persists(self, conn):
        template = _template(conn)
        assert SqliteNotificationTemplateRepository(conn).get(template.id) is not None

    def test_create_rejects_duplicate_code_and_channel(self, conn):
        _template(conn)
        with pytest.raises(NotificationTemplateCodeChannelOccupiedError):
            _template(conn)

    def test_create_allows_same_code_on_a_different_channel(self, conn):
        _template(conn, channel=NotificationChannel.WHATSAPP)
        template2 = _template(conn, channel=NotificationChannel.SMS)
        assert template2 is not None

    def test_update_persists(self, conn):
        template = _template(conn)
        updated = UpdateNotificationTemplateUseCase(conn).execute(
            template_id=template.id, parameter_names=("folio",))
        assert updated.parameter_names == ("folio",)
        assert SqliteNotificationTemplateRepository(conn).get(template.id).parameter_names == ("folio",)

    def test_update_unknown_raises(self, conn):
        with pytest.raises(NotificationTemplateNotFoundError):
            UpdateNotificationTemplateUseCase(conn).execute(template_id=new_uuid())

    def test_change_status_activate_deactivate(self, conn):
        template = _template(conn)
        use_case = ChangeNotificationTemplateStatusUseCase(conn)
        deactivated = use_case.execute(
            template_id=template.id, action=NotificationTemplateStatusAction.DEACTIVATE)
        assert deactivated.active is False
        activated = use_case.execute(
            template_id=template.id, action=NotificationTemplateStatusAction.ACTIVATE)
        assert activated.active is True


class TestNotificationRouteUseCases:
    def test_create_persists(self, conn):
        account = _account(conn)
        template = _template(conn)
        route = CreateNotificationRouteUseCase(conn).execute(
            event_code="pedido_confirmado", channel=NotificationChannel.WHATSAPP, template_id=template.id,
            account_id=account.id,
        )
        assert SqliteNotificationRouteRepository(conn).get(route.id) is not None

    def test_create_unknown_template_raises(self, conn):
        account = _account(conn)
        with pytest.raises(NotificationTemplateNotFoundError):
            CreateNotificationRouteUseCase(conn).execute(
                event_code="x", channel=NotificationChannel.WHATSAPP, template_id=new_uuid(),
                account_id=account.id,
            )

    def test_create_unknown_account_raises(self, conn):
        template = _template(conn)
        with pytest.raises(NotificationAccountNotFoundError):
            CreateNotificationRouteUseCase(conn).execute(
                event_code="x", channel=NotificationChannel.WHATSAPP, template_id=template.id,
                account_id=new_uuid(),
            )

    def test_create_rejects_a_second_active_route_for_the_same_event(self, conn):
        """Never lets the schema's partial-unique-index IntegrityError
        reach the UI — same discipline `AssignDeviceUseCase` (SET-7) and
        `AssignCampaignPlacementUseCase` (SET-18) already established."""
        account = _account(conn)
        template = _template(conn)
        CreateNotificationRouteUseCase(conn).execute(
            event_code="pedido_confirmado", channel=NotificationChannel.WHATSAPP, template_id=template.id,
            account_id=account.id,
        )
        with pytest.raises(NotificationRouteEventCodeOccupiedError):
            CreateNotificationRouteUseCase(conn).execute(
                event_code="pedido_confirmado", channel=NotificationChannel.WHATSAPP, template_id=template.id,
                account_id=account.id,
            )

    def test_deactivate_then_create_a_new_route_succeeds(self, conn):
        account = _account(conn)
        template = _template(conn)
        first = CreateNotificationRouteUseCase(conn).execute(
            event_code="pedido_confirmado", channel=NotificationChannel.WHATSAPP, template_id=template.id,
            account_id=account.id,
        )
        ChangeNotificationRouteStatusUseCase(conn).execute(
            route_id=first.id, action=NotificationRouteStatusAction.DEACTIVATE)
        second = CreateNotificationRouteUseCase(conn).execute(
            event_code="pedido_confirmado", channel=NotificationChannel.WHATSAPP, template_id=template.id,
            account_id=account.id,
        )
        assert SqliteNotificationRouteRepository(conn).get(first.id).active is False
        assert SqliteNotificationRouteRepository(conn).get(second.id).active is True

    def test_reactivating_an_old_route_while_a_new_one_is_active_is_rejected(self, conn):
        account = _account(conn)
        template = _template(conn)
        first = CreateNotificationRouteUseCase(conn).execute(
            event_code="pedido_confirmado", channel=NotificationChannel.WHATSAPP, template_id=template.id,
            account_id=account.id,
        )
        ChangeNotificationRouteStatusUseCase(conn).execute(
            route_id=first.id, action=NotificationRouteStatusAction.DEACTIVATE)
        CreateNotificationRouteUseCase(conn).execute(
            event_code="pedido_confirmado", channel=NotificationChannel.WHATSAPP, template_id=template.id,
            account_id=account.id,
        )
        with pytest.raises(NotificationRouteEventCodeOccupiedError):
            ChangeNotificationRouteStatusUseCase(conn).execute(
                route_id=first.id, action=NotificationRouteStatusAction.ACTIVATE)

    def test_change_status_unknown_route_raises(self, conn):
        with pytest.raises(NotificationRouteNotFoundError):
            ChangeNotificationRouteStatusUseCase(conn).execute(
                route_id=new_uuid(), action=NotificationRouteStatusAction.DEACTIVATE)
