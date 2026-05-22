# modulos/whatsapp/panels/webhook_panel.py
"""Panel Webhook / Microservicio — control del servidor de webhooks."""
from __future__ import annotations

import logging

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from modulos.design_tokens import Colors, Spacing, Typography, Borders
from modulos.spj_styles import spj_btn, apply_object_names
from modulos.whatsapp.panels._panel_styles import group_box_style, input_style
from modulos.whatsapp.widgets import ConnectionBadge, ErrorPanel

logger = logging.getLogger("spj.ui.wa.webhook_panel")


class WebhookPanel(QWidget):
    """Configuración y control del servidor webhook de Meta."""

    def __init__(self, svc, cred_svc, container=None, parent=None) -> None:
        super().__init__(parent)
        self._svc       = svc
        self._cred      = cred_svc
        self._container = container
        self._build_ui()
        apply_object_names(self)
        self._load()

    # ── Construcción UI ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        root.setSpacing(Spacing.LG)

        # Estado
        self._err = ErrorPanel()
        root.addWidget(self._err)

        grp_status = QGroupBox("Estado del webhook")
        grp_status.setStyleSheet(group_box_style())
        lay_st = QVBoxLayout(grp_status)
        lay_st.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)

        self._badge_wh = ConnectionBadge("Sin verificar")
        lay_st.addWidget(self._badge_wh)
        root.addWidget(grp_status)

        # Configuración local
        grp_cfg = QGroupBox("Servidor webhook local (Meta → ERP)")
        grp_cfg.setStyleSheet(group_box_style())
        fm = QFormLayout(grp_cfg)
        fm.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        fm.setSpacing(Spacing.MD)
        fm.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._inp_puerto = QLineEdit("8767")
        self._inp_puerto.setStyleSheet(self._input_style())
        self._inp_puerto.setMaximumWidth(120)

        self._inp_verify = QLineEdit()
        self._inp_verify.setPlaceholderText("spj_verify")
        self._inp_verify.setEchoMode(QLineEdit.Password)
        self._inp_verify.setStyleSheet(self._input_style())

        fm.addRow("Puerto:", self._inp_puerto)
        fm.addRow("Verify token:", self._inp_verify)
        root.addWidget(grp_cfg)

        # Acciones
        grp_act = QGroupBox("Acciones")
        grp_act.setStyleSheet(group_box_style())
        btn_lay = QHBoxLayout(grp_act)
        btn_lay.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        btn_lay.setSpacing(Spacing.SM)

        self._btn_start = QPushButton("Iniciar webhook")
        self._btn_stop  = QPushButton("Detener webhook")
        btn_test        = QPushButton("Test Meta handshake")
        btn_save_tok    = QPushButton("Guardar verify token")
        spj_btn(self._btn_start, "success")
        spj_btn(self._btn_stop, "danger")
        spj_btn(btn_test, "secondary")
        spj_btn(btn_save_tok, "info")

        self._btn_start.clicked.connect(self._iniciar)
        self._btn_stop.clicked.connect(self._detener)
        btn_test.clicked.connect(self._test_handshake)
        btn_save_tok.clicked.connect(self._save_verify_token)

        btn_lay.addWidget(self._btn_start)
        btn_lay.addWidget(self._btn_stop)
        btn_lay.addWidget(btn_test)
        btn_lay.addWidget(btn_save_tok)
        btn_lay.addStretch()
        root.addWidget(grp_act)

        # Info Meta
        grp_meta_info = QGroupBox("Configuración en Meta for Developers")
        grp_meta_info.setStyleSheet(group_box_style())
        lay_mi = QVBoxLayout(grp_meta_info)
        lay_mi.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        tip = QLabel(
            "En Meta for Developers → WhatsApp → Configuración → Webhook, registra:\n"
            "  • Callback URL: <b>https://tu-dominio.com/webhook</b> (requiere HTTPS/ngrok)\n"
            "  • Verify token: el valor configurado arriba\n"
            "  • Suscríbete a: <b>messages</b>, <b>message_deliveries</b>, <b>message_reads</b>"
        )
        tip.setWordWrap(True)
        tip.setStyleSheet(
            f"color: {Colors.NEUTRAL.SLATE_600};"
            f"font-size: {Typography.SIZE_SM};"
            f"line-height: 1.6;"
        )
        lay_mi.addWidget(tip)
        root.addWidget(grp_meta_info)
        root.addStretch()

    # ── Datos ─────────────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            self._err.clear()
            cfg = self._svc.get_config if hasattr(self._svc, "get_config") else lambda k, d="": d
            puerto = cfg("webhook_puerto", "8767")
            self._inp_puerto.setText(str(puerto))
            # No pre-llenar verify token (campo sensible)
            has_verify = bool(cfg("verify_token", ""))
            self._inp_verify.setPlaceholderText(
                "•••••• (configurado)" if has_verify else "spj_verify"
            )
            self._refresh_status()
        except Exception as exc:
            logger.debug("WebhookPanel._load: %s", exc)

    def _refresh_status(self) -> None:
        wa_hook = getattr(self._container, "whatsapp_webhook", None) if self._container else None
        running = wa_hook and getattr(wa_hook, "_running", False)
        if running:
            self._badge_wh.set_connected(True, "Webhook activo — escuchando mensajes entrantes")
        else:
            self._badge_wh.set_connected(False, "Webhook detenido — mensajes no se procesarán")

    def _iniciar(self) -> None:
        try:
            self._err.clear()
            puerto = int(self._inp_puerto.text() or "8767")
            verify = self._inp_verify.text().strip() or "spj_verify"

            if self._inp_verify.text().strip():
                val = self._cred.validate_webhook_token(verify)
                if not val.get("valid", True):
                    QMessageBox.warning(self, "Token inválido", val.get("error", ""))
                    return

            wa_hook = getattr(self._container, "whatsapp_webhook", None) if self._container else None
            if wa_hook:
                wa_hook._port = puerto
                wa_hook.start()
                if self._inp_verify.text().strip():
                    self._svc.save_bot_config({"verify_token": verify,
                                               "webhook_puerto": str(puerto)})
                self._refresh_status()
                QMessageBox.information(self, "OK", f"Webhook iniciado en puerto {puerto}.")
            else:
                QMessageBox.warning(
                    self, "Aviso",
                    "WhatsAppWebhookServer no está disponible en el contenedor."
                )
        except Exception as exc:
            self._err.set_error("Error al iniciar webhook.", str(exc))

    def _detener(self) -> None:
        try:
            wa_hook = getattr(self._container, "whatsapp_webhook", None) if self._container else None
            if wa_hook and hasattr(wa_hook, "stop"):
                wa_hook.stop()
                self._refresh_status()
        except Exception as exc:
            self._err.set_error("Error al detener webhook.", str(exc))

    def _test_handshake(self) -> None:
        try:
            import urllib.request
            puerto = self._inp_puerto.text() or "8767"
            verify = self._inp_verify.text().strip() or "spj_verify"
            url = (
                f"http://127.0.0.1:{puerto}/webhook"
                f"?hub.mode=subscribe"
                f"&hub.verify_token={verify}"
                f"&hub.challenge=test_spj_123"
            )
            resp = urllib.request.urlopen(url, timeout=3)
            body = resp.read().decode()
            if "test_spj_123" in body:
                QMessageBox.information(self, "Test OK",
                    "El webhook responde correctamente al handshake de Meta.")
            else:
                QMessageBox.warning(self, "Respuesta inesperada", f"Respuesta: {body}")
        except Exception as exc:
            QMessageBox.warning(
                self, "Sin respuesta",
                f"No se pudo conectar al webhook:\n{exc}\n\n"
                "Asegúrate de haberlo iniciado primero."
            )

    def _save_verify_token(self) -> None:
        verify = self._inp_verify.text().strip()
        if not verify:
            QMessageBox.warning(self, "Aviso", "Ingresa un verify token primero.")
            return
        try:
            self._svc.save_bot_config({"verify_token": verify})
            self._inp_verify.clear()
            self._inp_verify.setPlaceholderText("•••••• (configurado)")
            QMessageBox.information(self, "Guardado", "Verify token guardado.")
        except Exception as exc:
            self._err.set_error("No se pudo guardar el verify token.", str(exc))

    @staticmethod
    def _input_style() -> str:
        return input_style()
