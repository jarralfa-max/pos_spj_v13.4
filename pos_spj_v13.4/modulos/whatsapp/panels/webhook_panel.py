# modulos/whatsapp/panels/webhook_panel.py
"""Panel Webhook / Microservicio — estado real del microservicio FastAPI."""
from __future__ import annotations

import logging
import urllib.parse
import urllib.request

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from modulos.design_tokens import Colors, Spacing, Typography
from modulos.spj_styles import spj_btn, apply_object_names
from modulos.whatsapp.panels._panel_styles import group_box_style, input_style, info_banner_style
from modulos.whatsapp.widgets import ConnectionBadge, ErrorPanel

logger = logging.getLogger("spj.ui.wa.webhook_panel")


class WebhookPanel(QWidget):
    """Configuración y diagnóstico del webhook oficial en FastAPI."""

    def __init__(self, svc, cred_svc, container=None, parent=None) -> None:
        super().__init__(parent)
        self._svc = svc
        self._cred = cred_svc
        self._container = container
        self._build_ui()
        apply_object_names(self)
        self._load()

    # ── Construcción UI ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        root.setSpacing(Spacing.LG)

        info = QLabel(
            "El webhook real de Meta vive en el microservicio WhatsApp FastAPI. "
            "Este panel ya no inicia ni detiene un servidor dentro del ERP; solo "
            "configura, valida y diagnostica la conexión."
        )
        info.setWordWrap(True)
        info.setStyleSheet(info_banner_style("info"))
        root.addWidget(info)

        self._err = ErrorPanel()
        root.addWidget(self._err)

        # Estado
        grp_status = QGroupBox("Estado del microservicio y webhook")
        grp_status.setStyleSheet(group_box_style())
        lay_st = QVBoxLayout(grp_status)
        lay_st.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        lay_st.setSpacing(Spacing.SM)

        self._badge_ms = ConnectionBadge("Microservicio sin verificar")
        self._badge_wh = ConnectionBadge("Webhook sin verificar")
        lay_st.addWidget(self._badge_ms)
        lay_st.addWidget(self._badge_wh)
        root.addWidget(grp_status)

        # Configuración
        grp_cfg = QGroupBox("Configuración FastAPI / Meta")
        grp_cfg.setStyleSheet(group_box_style())
        fm = QFormLayout(grp_cfg)
        fm.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        fm.setSpacing(Spacing.MD)
        fm.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._inp_ms_url = QLineEdit()
        self._inp_ms_url.setPlaceholderText("http://localhost:8000")
        self._inp_ms_url.setStyleSheet(self._input_style())

        self._inp_public_url = QLineEdit()
        self._inp_public_url.setPlaceholderText("https://xxxx.ngrok-free.app/webhook o https://tu-dominio.com/webhook")
        self._inp_public_url.setStyleSheet(self._input_style())

        self._inp_verify = QLineEdit()
        self._inp_verify.setPlaceholderText("•••••• (configurado) o nuevo verify token")
        self._inp_verify.setEchoMode(QLineEdit.Password)
        self._inp_verify.setStyleSheet(self._input_style())

        self._lbl_local_webhook = QLabel("http://localhost:8000/webhook")
        self._lbl_local_webhook.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._lbl_local_webhook.setStyleSheet(
            f"color: {Colors.NEUTRAL.SLATE_600}; font-size: {Typography.SIZE_SM};"
        )

        fm.addRow("URL microservicio:", self._inp_ms_url)
        fm.addRow("Webhook local:", self._lbl_local_webhook)
        fm.addRow("Callback público Meta:", self._inp_public_url)
        fm.addRow("Verify token:", self._inp_verify)
        root.addWidget(grp_cfg)

        # Acciones
        grp_act = QGroupBox("Diagnóstico")
        grp_act.setStyleSheet(group_box_style())
        btn_lay = QHBoxLayout(grp_act)
        btn_lay.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        btn_lay.setSpacing(Spacing.SM)

        btn_health = QPushButton("Probar /health")
        btn_test = QPushButton("Probar handshake local")
        btn_save = QPushButton("Guardar configuración")
        btn_copy = QPushButton("Copiar URL local")
        spj_btn(btn_health, "success")
        spj_btn(btn_test, "secondary")
        spj_btn(btn_save, "info")
        spj_btn(btn_copy, "secondary")

        btn_health.clicked.connect(self._test_health)
        btn_test.clicked.connect(self._test_handshake)
        btn_save.clicked.connect(self._save_config)
        btn_copy.clicked.connect(self._copy_local_url)

        btn_lay.addWidget(btn_health)
        btn_lay.addWidget(btn_test)
        btn_lay.addWidget(btn_save)
        btn_lay.addWidget(btn_copy)
        btn_lay.addStretch()
        root.addWidget(grp_act)

        # Info Meta
        grp_meta_info = QGroupBox("Configuración en Meta for Developers")
        grp_meta_info.setStyleSheet(group_box_style())
        lay_mi = QVBoxLayout(grp_meta_info)
        lay_mi.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        tip = QLabel(
            "En Meta for Developers → WhatsApp → Configuración → Webhook, registra:\n"
            "  • Callback URL: la URL pública HTTPS que apunte a <b>/webhook</b>\n"
            "  • Verify token: el mismo valor configurado en este módulo\n"
            "  • Suscripción recomendada: <b>messages</b>"
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
            ms_url = cfg("microservicio_url", "http://localhost:8000") or "http://localhost:8000"
            public_url = cfg("webhook_public_url", "")
            has_verify = bool(cfg("verify_token", ""))

            self._inp_ms_url.setText(ms_url)
            self._inp_public_url.setText(public_url)
            self._inp_verify.setPlaceholderText("•••••• (configurado)" if has_verify else "spj_verify")
            self._update_local_label()
            self._refresh_status()
        except Exception as exc:
            logger.debug("WebhookPanel._load: %s", exc)
            self._err.set_error("Error cargando configuración del webhook.", str(exc), show_retry=False)

    def _base_url(self) -> str:
        return (self._inp_ms_url.text().strip() or "http://localhost:8000").rstrip("/")

    def _local_webhook_url(self) -> str:
        return f"{self._base_url()}/webhook"

    def _get_config_verify_token(self) -> str:
        cfg = self._svc.get_config if hasattr(self._svc, "get_config") else lambda k, d="": d
        return cfg("verify_token", "") or ""

    def _active_verify_token(self) -> str:
        return self._inp_verify.text().strip() or self._get_config_verify_token()

    def _update_local_label(self) -> None:
        self._lbl_local_webhook.setText(self._local_webhook_url())

    def _refresh_status(self) -> None:
        """Actualiza estado usando el microservicio FastAPI, no el webhook legacy."""
        try:
            ok = self._probe_health(silent=True)
            if ok:
                self._badge_ms.set_connected(True, "Microservicio activo — FastAPI responde en /health")
                self._badge_wh.set_connected(True, "Webhook disponible en /webhook")
            else:
                self._badge_ms.set_connected(False, "Microservicio detenido o URL incorrecta")
                self._badge_wh.set_connected(False, "Webhook no disponible porque el microservicio no responde")
        except Exception:
            self._badge_ms.set_connected(False, "Microservicio sin respuesta")
            self._badge_wh.set_connected(False, "Webhook sin verificar")

    def _probe_health(self, silent: bool = False) -> bool:
        self._update_local_label()
        url = f"{self._base_url()}/health"
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                status = getattr(resp, "status", 200)
                body = resp.read().decode("utf-8", errors="ignore")
            ok = 200 <= int(status) < 300 and "whatsapp-service" in body
            if not silent:
                if ok:
                    QMessageBox.information(self, "Microservicio OK", "El microservicio WhatsApp respondió correctamente.")
                else:
                    QMessageBox.warning(self, "Respuesta inesperada", body[:500])
            return ok
        except Exception as exc:
            if not silent:
                QMessageBox.warning(self, "Sin respuesta", f"No se pudo conectar a {url}:\n{exc}")
            return False

    def _test_health(self) -> None:
        self._err.clear()
        ok = self._probe_health(silent=False)
        self._refresh_status()
        if not ok:
            self._err.set_error(
                "El microservicio WhatsApp no respondió.",
                "Verifica que uvicorn esté corriendo en la URL configurada.",
                show_retry=False,
            )

    def _test_handshake(self) -> None:
        try:
            self._err.clear()
            verify = self._active_verify_token()
            if not verify:
                QMessageBox.warning(self, "Verify token faltante", "Configura un verify token primero.")
                return
            challenge = "test_spj_123"
            url = (
                f"{self._local_webhook_url()}"
                f"?hub.mode=subscribe"
                f"&hub.verify_token={urllib.parse.quote(verify)}"
                f"&hub.challenge={challenge}"
            )
            with urllib.request.urlopen(url, timeout=4) as resp:
                body = resp.read().decode("utf-8", errors="ignore")
            if challenge in body:
                self._badge_wh.set_connected(True, "Webhook verificado — handshake local OK")
                QMessageBox.information(self, "Handshake OK", "El webhook FastAPI responde correctamente al handshake de Meta.")
            else:
                self._badge_wh.set_connected(False, "Webhook respondió, pero el challenge no coincidió")
                QMessageBox.warning(self, "Respuesta inesperada", f"Respuesta: {body}")
        except Exception as exc:
            self._badge_wh.set_connected(False, "Handshake falló")
            QMessageBox.warning(self, "Sin respuesta", f"No se pudo validar el webhook:\n{exc}")

    def _save_config(self) -> None:
        try:
            self._err.clear()
            changes = {}
            ms_url = self._inp_ms_url.text().strip()
            public_url = self._inp_public_url.text().strip()
            verify = self._inp_verify.text().strip()

            if ms_url:
                changes["microservicio_url"] = ms_url.rstrip("/")
            if public_url:
                changes["webhook_public_url"] = public_url
            if verify:
                val = self._cred.validate_webhook_token(verify)
                if not val.get("valid", True):
                    QMessageBox.warning(self, "Token inválido", val.get("error", ""))
                    return
                changes["verify_token"] = verify

            if not changes:
                QMessageBox.information(self, "Sin cambios", "No hay cambios para guardar.")
                return

            self._svc.save_bot_config(changes)
            self._inp_verify.clear()
            self._load()
            QMessageBox.information(self, "Guardado", "Configuración del webhook actualizada.")
        except Exception as exc:
            self._err.set_error("No se pudo guardar la configuración del webhook.", str(exc), show_retry=False)

    def _copy_local_url(self) -> None:
        try:
            from PyQt5.QtWidgets import QApplication
            QApplication.clipboard().setText(self._local_webhook_url())
            QMessageBox.information(self, "Copiado", "URL local del webhook copiada al portapapeles.")
        except Exception as exc:
            self._err.set_error("No se pudo copiar la URL.", str(exc), show_retry=False)

    # Compatibilidad con nombres anteriores llamados desde tests/scripts antiguos.
    def _iniciar(self) -> None:
        QMessageBox.information(
            self,
            "Microservicio externo",
            "El webhook se ejecuta en el microservicio FastAPI. Inícialo con uvicorn y usa 'Probar /health'.",
        )

    def _detener(self) -> None:
        QMessageBox.information(
            self,
            "Microservicio externo",
            "El ERP no detiene el microservicio FastAPI. Detén uvicorn desde la terminal o servicio del sistema.",
        )

    def _save_verify_token(self) -> None:
        self._save_config()

    @staticmethod
    def _input_style() -> str:
        return input_style()
