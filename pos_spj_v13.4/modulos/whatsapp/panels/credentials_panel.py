# modulos/whatsapp/panels/credentials_panel.py
"""Panel Meta/Credenciales — configuración segura de tokens y números."""
from __future__ import annotations

import logging

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from modulos.design_tokens import Colors, Spacing, Typography, Borders
from modulos.spj_styles import spj_btn, apply_object_names
from modulos.whatsapp.widgets import ErrorPanel, MaskedSecretField

logger = logging.getLogger("spj.ui.wa.credentials_panel")


def _group_style() -> str:
    return (
        f"QGroupBox {{"
        f"  border: 1px solid {Colors.NEUTRAL.SLATE_200};"
        f"  border-radius: {Borders.RADIUS_XL}px;"
        f"  margin-top: {Spacing.SM}px;"
        f"  padding-top: {Spacing.SM}px;"
        f"  background: {Colors.NEUTRAL.WHITE};"
        f"}}"
        f"QGroupBox::title {{"
        f"  subcontrol-origin: margin;"
        f"  subcontrol-position: top left;"
        f"  padding: 0 {Spacing.SM}px;"
        f"  color: {Colors.NEUTRAL.SLATE_600};"
        f"  font-size: {Typography.SIZE_MD};"
        f"  font-weight: {Typography.WEIGHT_SEMIBOLD};"
        f"}}"
    )


class CredentialsPanel(QWidget):
    """
    Administración de credenciales Meta Cloud API.

    Reglas de seguridad:
    - Los tokens nunca se muestran completos
    - Se usa MaskedSecretField para todos los campos sensibles
    - Todos los cambios se delegan a WhatsAppCredentialService
    - Sin SQL directo en esta capa
    """

    def __init__(self, cred_svc, svc, parent=None) -> None:
        super().__init__(parent)
        self._cred = cred_svc
        self._svc  = svc
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
            "Los tokens se almacenan cifrados. Usa 'Reemplazar' para actualizar "
            "un valor — los tokens existentes nunca se muestran completos."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            f"background: {Colors.INFO.BG_SOFT};"
            f"color: {Colors.INFO.BASE};"
            f"border: 1px solid {Colors.INFO.BORDER};"
            f"border-radius: {Borders.RADIUS_LG}px;"
            f"padding: {Spacing.SM}px {Spacing.MD}px;"
            f"font-size: {Typography.SIZE_MD};"
        )
        root.addWidget(info)

        self._err = ErrorPanel()
        root.addWidget(self._err)

        # ── Grupo: Meta Cloud API ─────────────────────────────────────────────
        grp_meta = QGroupBox("Meta Cloud API")
        grp_meta.setStyleSheet(_group_style())
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
        grp_ms = QGroupBox("Microservicio WhatsApp (URL interna)")
        grp_ms.setStyleSheet(_group_style())
        fms = QFormLayout(grp_ms)
        fms.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        fms.setSpacing(Spacing.MD)
        fms.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._inp_ms_url = QLineEdit()
        self._inp_ms_url.setPlaceholderText("http://localhost:8000")
        self._inp_ms_url.setStyleSheet(self._input_style())

        fms.addRow("URL microservicio:", self._inp_ms_url)
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
            has_token  = bool(cfg("meta_token", "") or cfg("wa_token", ""))
            has_verify = bool(cfg("verify_token", ""))
            self._fld_token.set_has_value(has_token)
            self._fld_verify.set_has_value(has_verify)

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

            if not changes:
                QMessageBox.information(self, "Sin cambios", "No hay cambios para guardar.")
                return

            self._svc.save_bot_config(changes)
            self._fld_token.clear_edit()
            self._fld_verify.clear_edit()
            self._load()
            QMessageBox.information(self, "Guardado", "Credenciales actualizadas correctamente.")
        except Exception as exc:
            logger.warning("CredentialsPanel._save: %s", exc)
            self._err.set_error("No se pudieron guardar las credenciales.", str(exc), show_retry=False)
            QMessageBox.critical(self, "Error", f"No se pudieron guardar las credenciales:\n{exc}")

    @staticmethod
    def _input_style() -> str:
        return (
            f"QLineEdit {{"
            f"  border: 1px solid {Colors.NEUTRAL.SLATE_300};"
            f"  border-radius: {Borders.RADIUS_LG}px;"
            f"  padding: {Spacing.XS}px {Spacing.SM}px;"
            f"  font-size: {Typography.SIZE_MD};"
            f"  background: {Colors.NEUTRAL.WHITE};"
            f"}}"
            f"QLineEdit:focus {{"
            f"  border-color: {Colors.PRIMARY.BASE};"
            f"}}"
        )
