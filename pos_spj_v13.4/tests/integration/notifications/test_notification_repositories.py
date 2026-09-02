"""SET-20 — SqliteNotificationAccountRepository +
SqliteNotificationTemplateRepository + SqliteNotificationRouteRepository
against a real (in-memory) SQLite born-clean schema (migration 220).
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.domain.notifications.entities.notification_account import NotificationAccount
from backend.domain.notifications.entities.notification_route import NotificationRoute
from backend.domain.notifications.entities.notification_template import NotificationTemplate
from backend.domain.notifications.enums import NotificationChannel
from backend.domain.notifications.policies.notification_routing_policy import resolve_route
from backend.domain.notifications.policies.template_parameter_policy import assert_params_satisfied
from backend.infrastructure.db.repositories.notifications.notification_account_repository import (
    SqliteNotificationAccountRepository,
)
from backend.infrastructure.db.repositories.notifications.notification_route_repository import (
    SqliteNotificationRouteRepository,
)
from backend.infrastructure.db.repositories.notifications.notification_template_repository import (
    SqliteNotificationTemplateRepository,
)
from tests.integration._born_clean_db import make_db


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


@pytest.fixture
def account_repo(conn):
    return SqliteNotificationAccountRepository(conn)


@pytest.fixture
def template_repo(conn):
    return SqliteNotificationTemplateRepository(conn)


@pytest.fixture
def route_repo(conn):
    return SqliteNotificationRouteRepository(conn)


class TestNotificationAccountRepository:
    def test_save_get_roundtrip(self, conn, account_repo):
        account = NotificationAccount.create(
            channel=NotificationChannel.WHATSAPP, name="Número principal",
            credential_reference="whatsapp/access_token",
        )
        account_repo.save(account)
        conn.commit()

        fetched = account_repo.get(account.id)
        assert fetched.channel is NotificationChannel.WHATSAPP
        assert fetched.credential_reference == "whatsapp/access_token"

    def test_list_by_channel_and_list_active(self, conn, account_repo):
        whatsapp = NotificationAccount.create(channel=NotificationChannel.WHATSAPP, name="WA")
        email = NotificationAccount.create(channel=NotificationChannel.EMAIL, name="SMTP")
        inactive = NotificationAccount.create(channel=NotificationChannel.WHATSAPP, name="Inactiva")
        inactive.deactivate()
        for a in (whatsapp, email, inactive):
            account_repo.save(a)
        conn.commit()

        whatsapp_accounts = account_repo.list_by_channel(NotificationChannel.WHATSAPP)
        assert {a.id for a in whatsapp_accounts} == {whatsapp.id, inactive.id}

        active = account_repo.list_active()
        assert whatsapp.id in {a.id for a in active}
        assert inactive.id not in {a.id for a in active}


class TestNotificationTemplateRepository:
    def test_save_get_roundtrip_preserves_parameter_names(self, conn, template_repo):
        template = NotificationTemplate.create(
            code="pedido_confirmado", channel=NotificationChannel.WHATSAPP, language="es_MX",
            parameter_names=["folio", "total"],
        )
        template_repo.save(template)
        conn.commit()

        fetched = template_repo.get(template.id)
        assert fetched.parameter_names == ("folio", "total")

    def test_get_by_code(self, conn, template_repo):
        template = NotificationTemplate.create(
            code="pedido_confirmado", channel=NotificationChannel.WHATSAPP, language="es_MX",
        )
        template_repo.save(template)
        conn.commit()
        assert template_repo.get_by_code("pedido_confirmado").id == template.id

    def test_code_and_channel_pair_is_unique(self, conn, template_repo):
        template_repo.save(NotificationTemplate.create(
            code="pedido_confirmado", channel=NotificationChannel.WHATSAPP, language="es_MX",
        ))
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            template_repo.save(NotificationTemplate.create(
                code="pedido_confirmado", channel=NotificationChannel.WHATSAPP, language="en_US",
            ))
            conn.commit()
        conn.rollback()

    def test_repository_round_trip_composes_with_parameter_policy(self, conn, template_repo):
        template = NotificationTemplate.create(
            code="pedido_confirmado", channel=NotificationChannel.WHATSAPP, language="es_MX",
            parameter_names=["folio", "total"],
        )
        template_repo.save(template)
        conn.commit()

        fetched = template_repo.get(template.id)
        assert_params_satisfied(fetched, {"folio": "VNT-1", "total": "245.00"})  # does not raise


class TestNotificationRouteRepository:
    def _saved_template_and_account(self, conn, template_repo, account_repo):
        template = NotificationTemplate.create(
            code="pedido_confirmado", channel=NotificationChannel.WHATSAPP, language="es_MX",
            parameter_names=["folio"],
        )
        account = NotificationAccount.create(channel=NotificationChannel.WHATSAPP, name="Número principal")
        template_repo.save(template)
        account_repo.save(account)
        conn.commit()
        return template, account

    def test_save_get_roundtrip(self, conn, template_repo, account_repo, route_repo):
        template, account = self._saved_template_and_account(conn, template_repo, account_repo)
        route = NotificationRoute.create(
            event_code="pedido_confirmado", channel=NotificationChannel.WHATSAPP, template_id=template.id,
            account_id=account.id,
        )
        route_repo.save(route)
        conn.commit()

        fetched = route_repo.get(route.id)
        assert fetched.event_code == "pedido_confirmado"
        assert fetched.template_id == template.id
        assert fetched.account_id == account.id

    def test_unique_index_blocks_two_active_routes_for_same_event(self, conn, template_repo, account_repo, route_repo):
        template, account = self._saved_template_and_account(conn, template_repo, account_repo)
        first = NotificationRoute.create(
            event_code="pedido_confirmado", channel=NotificationChannel.WHATSAPP, template_id=template.id,
            account_id=account.id,
        )
        second = NotificationRoute.create(
            event_code="pedido_confirmado", channel=NotificationChannel.WHATSAPP, template_id=template.id,
            account_id=account.id,
        )
        route_repo.save(first)
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            route_repo.save(second)
            conn.commit()
        conn.rollback()

    def test_composes_with_routing_policy_end_to_end(self, conn, template_repo, account_repo, route_repo):
        template, account = self._saved_template_and_account(conn, template_repo, account_repo)
        route = NotificationRoute.create(
            event_code="pedido_confirmado", channel=NotificationChannel.WHATSAPP, template_id=template.id,
            account_id=account.id,
        )
        route_repo.save(route)
        conn.commit()

        candidates = route_repo.list_by_event_code("pedido_confirmado")
        resolved = resolve_route(candidates, "pedido_confirmado")
        assert resolved.id == route.id

    def test_list_active(self, conn, template_repo, account_repo, route_repo):
        template, account = self._saved_template_and_account(conn, template_repo, account_repo)
        route = NotificationRoute.create(
            event_code="pedido_confirmado", channel=NotificationChannel.WHATSAPP, template_id=template.id,
            account_id=account.id,
        )
        route_repo.save(route)
        conn.commit()
        assert [r.id for r in route_repo.list_active()] == [route.id]
