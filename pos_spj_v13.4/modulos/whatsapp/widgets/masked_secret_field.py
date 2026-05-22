# modulos/whatsapp/widgets/masked_secret_field.py
"""
MaskedSecretField — campo de contraseña/token con patrón "Reemplazar".

Nunca muestra el token completo existente.
El usuario solo puede ingresar un nuevo valor (modo reemplazo).
"""
from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget

from modulos.design_tokens import Colors, Spacing, Typography, Borders
from modulos.spj_styles import spj_btn


class MaskedSecretField(QWidget):
    """
    Campo para secretos/tokens con las siguientes reglas:
    - Si hay valor almacenado, muestra "•••••• (configurado)"
    - Botón "Reemplazar" activa la edición
    - Botón "Cancelar" revierte al estado original
    - Nunca expone el token completo en la UI
    """

    value_changed = pyqtSignal(str)

    def __init__(self, placeholder: str = "Ingresa el nuevo valor", parent=None) -> None:
        super().__init__(parent)
        self._has_stored = False
        self._is_editing = False
        self._placeholder = placeholder

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(Spacing.SM)

        # Label de estado (cuando no está editando)
        self._lbl_status = QLabel("No configurado")
        self._lbl_status.setStyleSheet(
            f"color: {Colors.NEUTRAL.SLATE_400};"
            f"font-size: {Typography.SIZE_MD};"
            f"font-style: italic;"
        )

        # Input de nuevo valor
        self._inp = QLineEdit()
        self._inp.setPlaceholderText(self._placeholder)
        self._inp.setEchoMode(QLineEdit.Password)
        self._inp.setStyleSheet(
            f"QLineEdit {{"
            f"  border: 1px solid {Colors.NEUTRAL.SLATE_300};"
            f"  border-radius: {Borders.RADIUS_LG}px;"
            f"  padding: {Spacing.XS}px {Spacing.SM}px;"
            f"  font-size: {Typography.SIZE_MD};"
            f"}}"
            f"QLineEdit:focus {{ border-color: {Colors.PRIMARY.BASE}; }}"
        )
        self._inp.setVisible(False)
        self._inp.textChanged.connect(self._on_text_changed)

        # Botones
        self._btn_replace = QPushButton("Reemplazar")
        self._btn_cancel = QPushButton("Cancelar")
        spj_btn(self._btn_replace, "warning")
        spj_btn(self._btn_cancel, "secondary")
        self._btn_cancel.setVisible(False)

        self._btn_replace.clicked.connect(self._start_edit)
        self._btn_cancel.clicked.connect(self._cancel_edit)

        lay.addWidget(self._lbl_status, 1)
        lay.addWidget(self._inp, 1)
        lay.addWidget(self._btn_replace)
        lay.addWidget(self._btn_cancel)

    # ── API pública ───────────────────────────────────────────────────────────

    def set_has_value(self, has_value: bool) -> None:
        """Indica si hay un valor almacenado (sin mostrarlo)."""
        self._has_stored = has_value
        self._cancel_edit()
        if has_value:
            self._lbl_status.setText("•••••• (configurado)")
            self._lbl_status.setStyleSheet(
                f"color: {Colors.NEUTRAL.SLATE_600};"
                f"font-size: {Typography.SIZE_MD};"
            )
        else:
            self._lbl_status.setText("No configurado")
            self._lbl_status.setStyleSheet(
                f"color: {Colors.NEUTRAL.SLATE_400};"
                f"font-size: {Typography.SIZE_MD};"
                f"font-style: italic;"
            )

    def set_new_value(self, value: str) -> None:
        """Activa edición y coloca un nuevo valor programáticamente.

        Útil para generar secretos desde la UI sin exponer los valores guardados.
        """
        self._start_edit()
        self._inp.setText(value or "")
        self.value_changed.emit(value or "")

    def get_new_value(self) -> str | None:
        """Retorna el nuevo valor ingresado, o None si no se modificó."""
        if self._is_editing:
            v = self._inp.text().strip()
            return v if v else None
        return None

    def is_changed(self) -> bool:
        return self._is_editing and bool(self._inp.text().strip())

    def clear_edit(self) -> None:
        self._cancel_edit()

    # ── Slots privados ────────────────────────────────────────────────────────

    def _start_edit(self) -> None:
        self._is_editing = True
        self._lbl_status.setVisible(False)
        self._inp.setVisible(True)
        self._inp.clear()
        self._inp.setFocus()
        self._btn_replace.setVisible(False)
        self._btn_cancel.setVisible(True)

    def _cancel_edit(self) -> None:
        self._is_editing = False
        self._inp.clear()
        self._inp.setVisible(False)
        self._lbl_status.setVisible(True)
        self._btn_replace.setVisible(True)
        self._btn_cancel.setVisible(False)

    def _on_text_changed(self, text: str) -> None:
        if self._is_editing:
            self.value_changed.emit(text)
