# modulos/whatsapp/panels/status_panel.py
"""Panel de estado general — overview de conexión y métricas clave."""
from __future__ import annotations

import logging

from PyQt5.QtWidgets import (
    QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QPushButton, QVBoxLayout, QWidget,
)

from modulos.design_tokens import Colors, Spacing, Typography
from modulos.kpi_card import KPICard
from modulos.spj_styles import spj_btn, apply_object_names
from modulos.whatsapp.panels._panel_styles import group_box_style
from modulos.whatsapp.widgets import ConnectionBadge, StatusBadge

logger = logging.getLogger("spj.ui.wa.status_panel")


class StatusPanel(QWidget):
    """Panel resumen: estado de conexión + 6 KPIs clave."""

    def __init__(self, svc, parent=None) -> None:
        super().__init__(parent)
        self._svc = svc
        self._build_ui()
        apply_object_names(self)
        self.refresh()

    # ── Construcción UI ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        root.setSpacing(Spacing.LG)

        # ── Fila superior ─────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.setSpacing(Spacing.MD)

        lbl_section = QLabel("Estado del servicio WhatsApp")
        lbl_section.setStyleSheet(
            f"font-size: {Typography.SIZE_XXL};"
            f"font-weight: {Typography.WEIGHT_SEMIBOLD};"
        )
        hdr.addWidget(lbl_section)
        hdr.addStretch()

        btn_test = QPushButton("Probar conexión")
        btn_refresh = QPushButton("Actualizar")
        spj_btn(btn_test, "primary")
        spj_btn(btn_refresh, "secondary")
        btn_test.clicked.connect(self._test_connection)
        btn_refresh.clicked.connect(self.refresh)
        hdr.addWidget(btn_test)
        hdr.addWidget(btn_refresh)
        root.addLayout(hdr)

        # ── Tarjeta de estado de conexión ─────────────────────────────────────
        grp_conn = QGroupBox("Conexión WhatsApp Business")
        grp_conn.setStyleSheet(group_box_style())
        lay_conn = QVBoxLayout(grp_conn)
        lay_conn.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        lay_conn.setSpacing(Spacing.SM)

        self._badge_conn = ConnectionBadge("Sin verificar")
        self._badge_wa   = StatusBadge("Sin estado", "neutral")
        self._badge_ms   = StatusBadge("Microservicio", "neutral")

        row_badges = QHBoxLayout()
        row_badges.setSpacing(Spacing.SM)
        row_badges.addWidget(self._badge_conn)
        row_badges.addStretch()
        row_badges.addWidget(QLabel("API Meta:"))
        row_badges.addWidget(self._badge_wa)
        row_badges.addWidget(QLabel("Microservicio:"))
        row_badges.addWidget(self._badge_ms)

        lay_conn.addLayout(row_badges)

        self._lbl_detail = QLabel("")
        self._lbl_detail.setWordWrap(True)
        self._lbl_detail.setStyleSheet(
            f"color: {Colors.NEUTRAL.SLATE_500};"
            f"font-size: {Typography.SIZE_SM};"
        )
        lay_conn.addWidget(self._lbl_detail)
        root.addWidget(grp_conn)

        # ── Grid de KPIs — mismo patrón que módulo inventario ─────────────────
        grp_metrics = QGroupBox("Métricas de actividad")
        grp_metrics.setStyleSheet(group_box_style())
        grid = QGridLayout(grp_metrics)
        grid.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        grid.setSpacing(Spacing.MD)

        self._card_hoy     = KPICard("Mensajes hoy",    "—", "💬", "primary")
        self._card_total   = KPICard("Total histórico", "—", "📊", "info")
        self._card_pedidos = KPICard("Pedidos WA",      "—", "🛒", "success")
        self._card_cola    = KPICard("Cola pendiente",  "—", "⏳", "warning")
        self._card_sesion  = KPICard("Sesiones activas","—", "👥", "info")
        self._card_valor   = KPICard("Valor generado",  "—", "💰", "success")

        for col, card in enumerate([
            self._card_hoy, self._card_total, self._card_pedidos
        ]):
            grid.addWidget(card, 0, col)
        for col, card in enumerate([
            self._card_cola, self._card_sesion, self._card_valor
        ]):
            grid.addWidget(card, 1, col)

        root.addWidget(grp_metrics)

        # ── Estado del bot ────────────────────────────────────────────────────
        grp_bot = QGroupBox("Estado del bot")
        grp_bot.setStyleSheet(group_box_style())
        lay_bot = QHBoxLayout(grp_bot)
        lay_bot.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        lay_bot.setSpacing(Spacing.LG)

        self._badge_bot  = StatusBadge("Bot", "neutral")
        self._badge_rasa = StatusBadge("Rasa", "neutral")
        self._badge_cot  = StatusBadge("Cotizaciones", "neutral")
        self._badge_rrhh = StatusBadge("Notif. RRHH", "neutral")
        self._lbl_bot_name = QLabel("")
        self._lbl_bot_name.setStyleSheet(
            f"color: {Colors.NEUTRAL.SLATE_600};"
            f"font-size: {Typography.SIZE_MD};"
        )

        lay_bot.addWidget(self._lbl_bot_name)
        lay_bot.addStretch()
        lay_bot.addWidget(self._badge_bot)
        lay_bot.addWidget(self._badge_rasa)
        lay_bot.addWidget(self._badge_cot)
        lay_bot.addWidget(self._badge_rrhh)
        root.addWidget(grp_bot)
        root.addStretch()

    # ── Acciones ──────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        try:
            m = self._svc.get_metrics()
            self._card_hoy.set_valor(str(m.get("mensajes_hoy", m.get("pedidos_hoy", "—"))))
            self._card_total.set_valor(str(m.get("total_mensajes", m.get("total_pedidos", "—"))))
            self._card_pedidos.set_valor(str(m.get("pedidos_hoy", "—")))
            self._card_cola.set_valor(str(m.get("cola_pendiente", m.get("pendientes", "—"))))
            self._card_sesion.set_valor(str(m.get("sesiones_activas", "—")))
            valor = m.get("valor_total", 0)
            self._card_valor.set_valor(f"${float(valor):,.0f}" if valor else "—")

            bot_activo = m.get("bot_activo", False)
            rasa_activo = bool(
                m.get("rasa_url") and m.get("rasa_url") != "http://localhost:5005"
            )
            self._badge_bot.set_status(
                "Bot activo" if bot_activo else "Bot inactivo",
                "ok" if bot_activo else "neutral",
            )
            self._badge_rasa.set_status(
                "Rasa activo" if rasa_activo else "Rasa inactivo",
                "ok" if rasa_activo else "neutral",
            )
            self._badge_cot.set_status(
                "Cotizaciones ✅" if m.get("cotizaciones") else "Cotizaciones ❌",
                "ok" if m.get("cotizaciones") else "neutral",
            )
            self._badge_rrhh.set_status(
                "RRHH ✅" if m.get("rrhh_notif") else "RRHH ❌",
                "ok" if m.get("rrhh_notif") else "neutral",
            )
            bot_nombre = m.get("bot_nombre", "")
            self._lbl_bot_name.setText(f"Bot: {bot_nombre}" if bot_nombre else "")
        except Exception as exc:
            logger.debug("StatusPanel.refresh: %s", exc)

    def _test_connection(self) -> None:
        from PyQt5.QtWidgets import QMessageBox
        self._badge_conn.set_loading("Verificando…")
        try:
            ok = self._svc.test_connection()
            if ok:
                self._badge_conn.set_connected(True, "Conectado")
                self._badge_wa.set_status("API Meta OK", "ok")
                QMessageBox.information(
                    self, "Conexión OK", "WhatsApp Business conectado correctamente.")
            else:
                self._badge_conn.set_connected(False, "Sin conexión")
                self._badge_wa.set_status("Sin respuesta", "error")
                QMessageBox.warning(
                    self, "Sin conexión",
                    "No se pudo verificar la conexión.\n\n"
                    "Verifica las credenciales en la pestaña Meta / Credenciales.")
        except Exception as exc:
            self._badge_conn.set_connected(False, "Error")
            self._badge_wa.set_status("Error", "error")
            self._lbl_detail.setText(str(exc))
