"""CRM-43 — la campana ya tiene fuente y el supervisor de fondo ya corre algo.

* `NotificationInboxFeed` llena el cajón con la bandeja del usuario de la
  sesión (`notification_inbox`) y, al abrir un aviso, lo marca leído en la base.
* `PeriodicTaskService` corre su tarea al arrancar y no muere si una pasada falla.
"""
import sqlite3

from PyQt5.QtWidgets import QApplication

from backend.application.notifications.user_inbox_service import UserInboxService
from backend.infrastructure.notifications.in_app_inbox_repository import InAppInboxRepository
from frontend.desktop.shell.application_shell.notification_drawer import NotificationDrawer
from frontend.desktop.shell.application_shell.notification_center_dialog import (
    NotificationCenterDialog,
)
from frontend.desktop.shell.application_shell.notification_inbox_feed import (
    NotificationInboxFeed,
)
from frontend.desktop.shell.background.periodic_task_service import PeriodicTaskService


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE notification_inbox (
            id TEXT NOT NULL PRIMARY KEY, empleado_id TEXT NOT NULL, tipo TEXT NOT NULL,
            titulo TEXT NOT NULL, cuerpo TEXT DEFAULT '', datos TEXT DEFAULT '{}',
            sucursal_id TEXT, leido INTEGER DEFAULT 0, leido_at DATETIME,
            created_at DATETIME DEFAULT (datetime('now')), dedupe_key TEXT,
            severity TEXT DEFAULT 'info')""")
    conn.execute("CREATE UNIQUE INDEX ux ON notification_inbox(dedupe_key)"
                 " WHERE dedupe_key IS NOT NULL")
    return conn


def _deliver(conn, user, title, key=None):
    InAppInboxRepository(conn).deliver(recipient_user_id=user, kind="CRM", title=title,
                                       body="Prospecto: Fonda", dedupe_key=key)
    conn.commit()


def test_feed_shows_only_the_session_users_notifications():
    conn = _conn()
    _deliver(conn, "ana", "Recordatorio")
    _deliver(conn, "beto", "Ajeno")
    drawer = NotificationDrawer()
    feed = NotificationInboxFeed(UserInboxService(conn), "ana")
    feed.attach(drawer)

    feed.refresh()

    assert [n.title for n in drawer.all_notifications()] == ["Recordatorio"]
    assert drawer.unread_count() == 1


def test_activating_a_notification_marks_it_read_in_the_database():
    conn = _conn()
    _deliver(conn, "ana", "Recordatorio")
    drawer = NotificationDrawer()
    feed = NotificationInboxFeed(UserInboxService(conn), "ana")
    feed.attach(drawer)
    feed.refresh()
    notification_id = drawer.all_notifications()[0].notification_id

    drawer.notification_activated.emit(notification_id)
    feed.refresh()

    assert UserInboxService(conn).unread_count("ana") == 0
    assert drawer.unread_count() == 0


def test_dedupe_key_makes_delivery_idempotent():
    conn = _conn()
    _deliver(conn, "ana", "Recordatorio", key="crm-reminder:1")
    _deliver(conn, "ana", "Recordatorio", key="crm-reminder:1")
    assert len(UserInboxService(conn).recent("ana")) == 1


def test_notification_center_filters_and_marks_only_own_alerts_read():
    conn = _conn()
    _deliver(conn, "ana", "Stock bajo")
    _deliver(conn, "ana", "Recordatorio")
    _deliver(conn, "beto", "Ajeno")
    center = NotificationCenterDialog(UserInboxService(conn), "ana")
    assert len(center._rows) == 2
    center.search.setText("Stock bajo")
    center.refresh()
    assert len(center._rows) == 1
    center.table.selectRow(0)
    center._mark_selected()
    assert UserInboxService(conn).unread_count("ana") == 1
    assert UserInboxService(conn).unread_count("beto") == 1
    center.close()


def test_periodic_service_runs_on_start_and_survives_a_failing_pass():
    calls = []

    def task():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("pasada fallida")

    service = PeriodicTaskService(task, interval_ms=60_000)
    service.start()
    QApplication.processEvents()
    service.run_once()
    service.stop()
    service.run_once()

    assert len(calls) == 2
    assert service.is_active is False
