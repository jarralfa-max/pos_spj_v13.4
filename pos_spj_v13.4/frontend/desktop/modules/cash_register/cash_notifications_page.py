"""CASH-20 notification operations UI for Caja.

The page only renders notification state and delegates dispatch to the
presenter. Policies, recipients, retries, WhatsApp and audit live in backend
application/infrastructure services.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QMessageBox, QTabWidget, QVBoxLayout, QWidget

from backend.domain.cash_register.exceptions import CashRegisterError
from frontend.desktop.components.buttons import create_primary_button, create_secondary_button
from frontend.desktop.components.kpi_bar import KPIBar
from frontend.desktop.components.kpi_card import KPIDTO
from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.tables import ColumnSpec, StandardTable


class CashNotificationsPage(QWidget):
    def __init__(self, *, presenter, parent=None):
        super().__init__(parent)
        self._presenter = presenter
        root = QVBoxLayout(self)

        caps = presenter.capabilities()
        dispatch = create_primary_button(
            self,
            "Despachar pendientes",
            tooltip="Ejecuta la cola de notificaciones preparada por eventos de Caja.",
        )
        refresh = create_secondary_button(self, "Actualizar")
        dispatch.setEnabled(bool(caps.notification_manage))
        dispatch.clicked.connect(self._dispatch)
        refresh.clicked.connect(self.refresh)

        root.addWidget(PageHeader(
            self,
            title="Notificaciones y WhatsApp",
            subtitle="Policies, destinatarios, alertas in-app, WhatsApp, auditoria e idempotencia.",
            actions=[refresh, dispatch],
        ))
        self._kpis = KPIBar(self)
        root.addWidget(self._kpis)
        self._tabs = QTabWidget(self)
        self._alerts = StandardTable([
            ColumnSpec("Severidad", "status"),
            ColumnSpec("Titulo"),
            ColumnSpec("Detalle"),
            ColumnSpec("Creada", "date"),
        ], self)
        self._jobs = StandardTable([
            ColumnSpec("Canal", "status"),
            ColumnSpec("Destinatario"),
            ColumnSpec("Severidad", "status"),
            ColumnSpec("Estado", "status"),
            ColumnSpec("Intentos", "numeric"),
            ColumnSpec("Siguiente intento", "date"),
            ColumnSpec("Evento"),
            ColumnSpec("Error"),
        ], self)
        self._tabs.addTab(self._alerts, "Alertas in-app")
        self._tabs.addTab(self._jobs, "Cola")
        root.addWidget(self._tabs)
        self.refresh()

    def refresh(self) -> None:
        try:
            dashboard = self._presenter.cash_notifications_dashboard()
            alerts = self._presenter.cash_notification_alerts()
            jobs = self._presenter.cash_notification_jobs()
        except (CashRegisterError, RuntimeError, ValueError, LookupError) as exc:
            self._show_error(str(exc))
            self._kpis.set_cards([
                KPIDTO("unread", "No leidas", "0"),
                KPIDTO("pending", "Pendientes", "0"),
                KPIDTO("delivered", "Entregadas", "0"),
                KPIDTO("dead", "Dead letter", "0"),
            ])
            self._alerts.load_rows([])
            self._jobs.load_rows([])
            return
        self._kpis.set_cards([
            KPIDTO("unread", "No leidas", str(dashboard.get("unread", 0))),
            KPIDTO("pending", "Pendientes", str(dashboard.get("pending", 0))),
            KPIDTO("delivered", "Entregadas", str(dashboard.get("delivered", 0))),
            KPIDTO("dead", "Dead letter", str(dashboard.get("dead_letter", 0))),
        ])
        self._alerts.load_rows(
            [
                [
                    row.get("severity", ""),
                    row.get("title", ""),
                    row.get("body", ""),
                    row.get("created_at", ""),
                ]
                for row in alerts
            ],
            row_ids=[str(row.get("id", "")) for row in alerts],
        )
        self._jobs.load_rows(
            [
                [
                    row.get("channel", ""),
                    row.get("recipient", ""),
                    row.get("severity", ""),
                    row.get("status", ""),
                    row.get("attempt_count", ""),
                    row.get("next_attempt_at", ""),
                    row.get("event_name", ""),
                    row.get("last_error", ""),
                ]
                for row in jobs
            ],
            row_ids=[str(row.get("id", "")) for row in jobs],
        )

    def _dispatch(self) -> None:
        try:
            result = self._presenter.dispatch_cash_notifications()
        except (CashRegisterError, RuntimeError, ValueError, LookupError) as exc:
            self._show_error(str(exc))
            return
        self._show_result(
            f"Despacho ejecutado. Entregadas={result.delivered}, "
            f"reintentos={result.retries}, omitidas={result.skipped}."
        )
        self.refresh()

    def _show_result(self, message: str) -> None:
        QMessageBox.information(self, "Caja", message)

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Caja", message or "No fue posible completar la operacion.")
