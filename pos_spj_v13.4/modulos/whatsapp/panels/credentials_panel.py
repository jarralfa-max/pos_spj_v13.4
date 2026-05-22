# modulos/whatsapp/panels/credentials_panel.py
"""Panel Meta/Credenciales — configuración segura de tokens y números."""
from __future__ import annotations

import logging
import secrets

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from modulos.design_tokens import Spacing
from modulos.spj_styles import spj_btn, apply_object_names
from modulos.whatsapp.panels._panel_styles import group_box_style, info_banner_style, input_style
from modulos.whatsapp.widgets import ErrorPanel, MaskedSecretField

logger = logging.getLogger("spj.ui.wa.credentials_panel")


class CredentialsPanel(QWidget):
    """
    Administración de credenciales Meta Cloud API y seguridad interna.

    Reglas de seguridad:
    - Los tokens nunca se muestran completos
    - Se usa MaskedSecretField para todos los campos sensibles
    - Todos los cambios se delegan a WhatsAppAdminService
    - Sin SQL directo en esta capa
    """

    def __init__(self, cred_svc, svc, parent=None) -> None:
        super().__init__(parent)
        self._cred = cred_svc
        self._svc = svc
        self._build_ui()
        apply_object_names(self)
        self._load()

    # ── Construcción UI ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        root.setSpacing(Spacing.LG)

        # Alerta informativa
        info = QLabel(
            "Configura aquí las credenciales de Meta y la conexión segura entre "
            "el ERP y el microservicio WhatsApp. Los secretos existentes nunca "
            "se muestran completos."
        )
        info.setWordWrap(True)
        info.setStyleSheet(info_banner_style("info"))
        root.addWidget(info)

        self._err = ErrorPanel()
        root.addWidget(self._err)

        # ── Grupo: Meta Cloud API ─────────────────────────────────────────────
        grp_meta = QGroupBox("Meta Cloud API")
        grp_meta.setStyleSheet(group_box_style())
        fm = QFormLayout(grp_meta)
        fm.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        fm.setSpacing(Spacing.MD)
        fm.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._inp_phone_id = QLineEdit()
        self._inp_phone_id.setPlaceholderText("ej. 123456789012345")
        self._inp_phone_id.setStyleSheet(self._input_style())

        self._fld_token = MaskedSecretField("Nuevo Access Token de Meta")
        self._fld_verify = MaskedSecretField("Nuevo verify token del webhook")

        self._inp_waba_id = QLineEdit()
        self._inp_waba_id.setPlaceholderText("WhatsApp Business Account ID (opcional)")
        self._inp_waba_id.setStyleSheet(self._input_style())

        fm.addRow("Phone Number ID:", self._inp_phone_id)
        fm.addRow("Access Token:", self._fld_token)
        fm.addRow("Verify Token:", self._fld_verify)
        fm.addRow("WABA ID:", self._inp_waba_id)
        root.addWidget(grp_meta)

        # ── Grupo: Microservicio WhatsApp ─────────────────────────────────────
        grp_ms = QGroupBox("Microservicio WhatsApp (conexión interna)")
        grp_ms.setStyleSheet(group_box_style())
        fms = QFormLayout(grp_ms)
        fms.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        fms.setSpacing(Spacing.MD)
        fms.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._inp_ms_url = QLineEdit()
        self._inp_ms_url.setPlaceholderText("http://localhost:8000")
        self._inp_ms_url.setStyleSheet(self._input_style())

        self._fld_internal_key = MaskedSecretField("Clave interna ERP ↔ WhatsApp")
        self._btn_generate_internal_key = QPushButton("Generar clave segura")
        spj_btn(self._btn_generate_internal_key, "info")
        self._btn_generate_internal_key.clicked.connect(self._generate_internal_key)

        internal_row = QWidget()
        internal_lay = QHBoxLayout(internal_row)
        internal_lay.setContentsMargins(0, 0, 0, 0)
        internal_lay.setSpacing(Spacing.SM)
        internal_lay.addWidget(self._fld_internal_key, 1)
        internal_lay.addWidget(self._btn_generate_internal_key)

        help_internal = QLabel(
            "Esta clave protege las llamadas ERP → microservicio. Se genera aquí; "
            "el usuario no necesita editar archivos .env ni conocer programación."
        )
        help_internal.setWordWrap(True)
        help_internal.setStyleSheet(info_banner_style("warning"))

        fms.addRow("URL microservicio:", self._inp_ms_url)
        fms.addRow("Clave interna:", internal_row)
        fms.addRow("", help_internal)
        root.addWidget(grp_ms)

        # ── Botones de acción ─────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(Spacing.SM)
        self._btn_save = QPushButton("Guardar credenciales")
        btn_cancel = QPushButton("Descartar cambios")
        spj_btn(self._btn_save, "success")
        spj_btn(btn_cancel, "secondary")
        self._btn_save.clicked.connect(self._save)
        btn_cancel.clicked.connect(self._load)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(self._btn_save)
        root.addLayout(btn_row)
        root.addStretch()

    # ── Datos ─────────────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            self._err.clear()
            cfg = self._svc.get_config if hasattr(self._svc, "get_config") else lambda k, d="": d

            phone_id = cfg("meta_phone_id", "")
            self._inp_phone_id.setText(phone_id)

            # Mostrar si hay token almacenado, sin revelar su valor
            has_token = bool(cfg("meta_token", "") or cfg("wa_token", ""))
            has_verify = bool(cfg("verify_token", ""))
            has_internal_key = bool(cfg("internal_api_key", ""))
            self._fld_token.set_has_value(has_token)
            self._fld_verify.set_has_value(has_verify)
            self._fld_internal_key.set_has_value(has_internal_key)

            self._inp_waba_id.setText(cfg("waba_id", ""))
            self._inp_ms_url.setText(cfg("microservicio_url", "http://localhost:8000"))
        except Exception as exc:
            logger.debug("CredentialsPanel._load: %s", exc)
            self._err.set_error(f"Error cargando configuración: {exc}")

    def _save(self) -> None:
        try:
            self._err.clear()
            changes: dict = {}

            phone_id = self._inp_phone_id.text().strip()
            if phone_id:
                changes["meta_phone_id"] = phone_id

            waba_id = self._inp_waba_id.text().strip()
            if waba_id:
                changes["waba_id"] = waba_id

            ms_url = self._inp_ms_url.text().strip()
            if ms_url:
                changes["microservicio_url"] = ms_url

            new_token = self._fld_token.get_new_value()
            if new_token:
                changes["meta_token"] = new_token

            new_verify = self._fld_verify.get_new_value()
            if new_verify:
                changes["verify_token"] = new_verify

            new_internal_key = self._fld_internal_key.get_new_value()
            if new_internal_key:
                changes["internal_api_key"] = new_internal_key

            if not changes:
                QMessageBox.information(self, "Sin cambios", "No hay cambios para guardar.")
                return

            self._svc.save_bot_config(changes)
            self._fld_token.clear_edit()
            self._fld_verify.clear_edit()
            self._fld_internal_key.clear_edit()
            self._load()
            QMessageBox.information(self, "Guardado", "Credenciales actualizadas correctamente.")
        except Exception as exc:
            logger.warning("CredentialsPanel._save: %s", exc)
            self._err.set_error("No se pudieron guardar las credenciales.", str(exc), show_retry=False)
            QMessageBox.critical(self, "Error", f"No se pudieron guardar las credenciales:\n{exc}")

    def _generate_internal_key(self) -> None:
        """Genera una clave interna fuerte sin que el usuario toque .env."""
        try:
            generated = secrets.token_hex(32)
            if hasattr(self._fld_internal_key, "set_new_value"):
                self._fld_internal_key.set_new_value(generated)
            else:
                # Compatibilidad con versiones previas de MaskedSecretField
                self._fld_internal_key._start_edit()  # noqa: SLF001
                self._fld_internal_key._inp.setText(generated)  # noqa: SLF001
            QMessageBox.information(
                self,
                "Clave generada",
                "Se generó una clave interna segura. Presiona 'Guardar credenciales' para aplicarla.",
            )
        except Exception as exc:
            logger.warning("_generate_internal_key: %s", exc)
            self._err.set_error("No se pudo generar la clave interna.", str(exc), show_retry=False)

    @staticmethod
    def _input_style() -> str:
        return input_style()
