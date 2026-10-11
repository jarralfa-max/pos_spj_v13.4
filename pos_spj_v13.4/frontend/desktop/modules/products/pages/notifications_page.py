"""Notificaciones de Productos — historial de alertas enviadas (§35/§36, PROD-22).

UI only: cada alerta con su canal (campana o WhatsApp), destinatario (teléfono
enmascarado), severidad y resultado. Qué se avisa y a quién se decide en
Productos → Configuración.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from frontend.desktop.components import ColumnSpec, PageHeader, StandardTable
from frontend.desktop.components.buttons import create_secondary_button
from frontend.desktop.components.cards import SectionCard
from frontend.desktop.components.icons import Icons
from frontend.desktop.components.page_viewport import PageViewport
from frontend.desktop.modules.products.settings_presenter import (
    CHANNEL_ES,
    OUTBOX_STATUS_ES,
    SEVERITY_ES,
    STATUS_ES,
)
from frontend.desktop.themes.tokens import Spacing


class ProductNotificationsPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("productNotificationsPage")
        self._s = getattr(presenter, "settings", None)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.viewport = PageViewport(self)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)
        layout.addWidget(PageHeader(
            title="Notificaciones",
            subtitle="Alertas de datos de productos enviadas a la campana y por WhatsApp.",
            icon=getattr(Icons, "BELL", None), compact=True))
        self.state = QLabel("")
        self.state.setProperty("role", "muted")
        self.state.setWordWrap(True)
        layout.addWidget(self.state)
        self.table = StandardTable(columns=[
            ColumnSpec("Fecha", "date"), ColumnSpec("Severidad", "status"),
            ColumnSpec("Canal", "text"), ColumnSpec("Para", "text"),
            ColumnSpec("Producto", "text"), ColumnSpec("Mensaje", "text"),
            ColumnSpec("Resultado", "status")])
        layout.addWidget(self.table, 1)

        # PROD-22: cola de WhatsApp (se envía en segundo plano, con reintentos).
        queue = SectionCard(self, title="Cola de WhatsApp")
        bar = QHBoxLayout()
        self.queue_state = QLabel("")
        self.queue_state.setProperty("role", "muted")
        bar.addWidget(self.queue_state, 1)
        self.btn_retry = create_secondary_button(self, "Reintentar",
                                                 "Devuelve a la cola un mensaje que falló")
        self.btn_retry.clicked.connect(self._retry)
        bar.addWidget(self.btn_retry)
        queue.body().addLayout(bar)
        self.queue = StandardTable(columns=[
            ColumnSpec("Fecha", "date"), ColumnSpec("Para", "text"),
            ColumnSpec("Producto", "text"), ColumnSpec("Estado", "status"),
            ColumnSpec("Intentos", "numeric"), ColumnSpec("Último error", "text")])
        self.queue.setMinimumHeight(160)
        queue.add(self.queue)
        layout.addWidget(queue)
        self.viewport.set_page(body)
        outer.addWidget(self.viewport)
        self.refresh()

    def refresh(self) -> None:
        if self._s is None:
            self.state.setText("Las notificaciones no están disponibles.")
            return
        settings = self._s.current()
        self.state.setText(
            ("Alertas a la campana: activas. " if settings.alerts_enabled
             else "Alertas a la campana: apagadas (actívalas en Configuración). ")
            + ("WhatsApp: activo." if settings.whatsapp_enabled else "WhatsApp: apagado."))
        rows = self._s.notification_log()
        self.table.load_rows(
            [[(r["created_at"] or "")[:16].replace("T", " "),
              SEVERITY_ES.get(r["severity"], r["severity"]),
              CHANNEL_ES.get(r["channel"], r["channel"]), r["recipient"], r["product"],
              r["message"] or "",
              ("Encolada (ver cola abajo)" if r["channel"] == "WHATSAPP"
               and r["status"] == "SENT" else STATUS_ES.get(r["status"], r["status"]))]
             for r in rows],
            row_ids=[r["id"] for r in rows])
        self._queue_rows = self._s.whatsapp_queue()
        self.queue.load_rows(
            [[(r["created_at"] or "")[:16].replace("T", " "), r["recipient"], r["product"],
              OUTBOX_STATUS_ES.get(r["status"], r["status"]), str(r["attempts"]),
              r["last_error"]] for r in self._queue_rows],
            row_ids=[r["id"] for r in self._queue_rows])
        pending = sum(1 for r in self._queue_rows if r["status"] == "PENDING")
        failed = sum(1 for r in self._queue_rows if r["status"] == "FAILED")
        self.queue_state.setText(f"En cola: {pending} · Fallidos: {failed}")
        self.btn_retry.setEnabled(bool(failed) and self._s.can_edit_whatsapp)

    def _retry(self) -> None:
        message_id = self.queue.selected_row_id()
        if not message_id:
            self.queue_state.setText("Selecciona un mensaje de la cola.")
            return
        ok, message = self._s.retry_whatsapp(message_id)
        self.queue_state.setText(message)
        if ok:
            self.refresh()
