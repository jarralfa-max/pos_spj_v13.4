# modulos/whatsapp/panels/numbers_panel.py
"""Panel Números y Canales — CRUD de líneas WhatsApp por sucursal."""
from __future__ import annotations

import logging

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from modulos.design_tokens import Colors, Spacing, Typography, Borders
from modulos.spj_styles import spj_btn, apply_object_names
from modulos.whatsapp.panels._panel_styles import info_banner_style, input_style
from modulos.spj_phone_widget import PhoneWidget
from modulos.whatsapp.widgets import EmptyState, ErrorPanel

logger = logging.getLogger("spj.ui.wa.numbers_panel")


def _group_hdr_style() -> str:
    return (
        f"font-size: {Typography.SIZE_XXL};"
        f"font-weight: {Typography.WEIGHT_SEMIBOLD};"
    )


class NumbersPanel(QWidget):
    """Lista y administración de números/canales WhatsApp registrados."""

    def __init__(self, svc, cred_svc, parent=None) -> None:
        super().__init__(parent)
        self._svc  = svc
        self._cred = cred_svc
        self._build_ui()
        apply_object_names(self)
        self._load()

    # ── Construcción UI ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        root.setSpacing(Spacing.MD)

        # Header
        hdr = QHBoxLayout()
        lbl = QLabel("Números y canales")
        lbl.setStyleSheet(_group_hdr_style())
        hdr.addWidget(lbl)
        hdr.addStretch()

        self._btn_add  = QPushButton("Agregar número")
        self._btn_edit = QPushButton("Editar")
        self._btn_del  = QPushButton("Eliminar")
        btn_ref = QPushButton("Actualizar")
        spj_btn(self._btn_add, "success")
        spj_btn(self._btn_edit, "warning")
        spj_btn(self._btn_del, "danger")
        spj_btn(btn_ref, "secondary")
        self._btn_add.clicked.connect(lambda: self._dialogo_numero(editar=False))
        self._btn_edit.clicked.connect(lambda: self._dialogo_numero(editar=True))
        self._btn_del.clicked.connect(self._eliminar)
        btn_ref.clicked.connect(self._load)
        for b in (btn_ref, self._btn_del, self._btn_edit, self._btn_add):
            hdr.addWidget(b)
        root.addLayout(hdr)

        # Info contextual
        info = QLabel(
            "Configura un número por sucursal. "
            "El campo 'token' se almacena cifrado — usa 'Reemplazar' al editar."
        )
        info.setWordWrap(True)
        info.setStyleSheet(info_banner_style("neutral"))
        root.addWidget(info)

        self._err = ErrorPanel()
        root.addWidget(self._err)

        # Tabla
        self._tbl = QTableWidget()
        self._tbl.setColumnCount(6)
        self._tbl.setHorizontalHeaderLabels(
            ["ID", "Sucursal", "Canal", "Número", "Proveedor", "Activo"]
        )
        hh = self._tbl.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        for i in (0, 2, 4, 5):
            hh.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self._tbl.setColumnHidden(0, True)
        self._tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl.setAlternatingRowColors(True)
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setStyleSheet(
            f"QTableWidget {{ font-size: {Typography.SIZE_MD}; }}"
        )
        root.addWidget(self._tbl)

        self._empty = EmptyState(
            "📵",
            "Sin números configurados",
            "Agrega al menos un número de WhatsApp Business.",
            "Agregar número",
        )
        self._empty.action_triggered.connect(lambda: self._dialogo_numero(editar=False))
        self._empty.setVisible(False)
        root.addWidget(self._empty)

    # ── Datos ─────────────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            self._err.clear()
            rows = self._svc.list_numeros()
            self._tbl.setRowCount(0)
            for i, r in enumerate(rows):
                self._tbl.insertRow(i)
                vals = [
                    r.get("id", ""),
                    r.get("nombre_sucursal", "Global"),
                    r.get("canal", ""),
                    r.get("numero_negocio", ""),
                    r.get("proveedor", ""),
                    r.get("activo", 0),
                ]
                for j, v in enumerate(vals):
                    cell = QTableWidgetItem(
                        ("✅" if v else "❌") if j == 5 else str(v) if v is not None else ""
                    )
                    self._tbl.setItem(i, j, cell)
            has_rows = bool(rows)
            self._tbl.setVisible(has_rows)
            self._empty.setVisible(not has_rows)
        except Exception as exc:
            logger.debug("NumbersPanel._load: %s", exc)
            self._err.set_error(f"Error cargando números: {exc}")

    def _dialogo_numero(self, editar: bool = False) -> None:
        row_id = None
        existing = None
        if editar:
            row = self._tbl.currentRow()
            if row < 0:
                QMessageBox.warning(self, "Aviso", "Selecciona un número primero.")
                return
            item = self._tbl.item(row, 0)
            if item:
                row_id = int(item.text())
                existing = self._svc.get_numero(row_id)

        dlg = _NumberDialog(self._svc, existing, self)
        if dlg.exec_() != QDialog.Accepted:
            return

        data = dlg.get_data()
        ok = self._cred.save_credentials(
            sucursal_id=data["sucursal_id"],
            canal=data["canal"],
            proveedor=data["proveedor"],
            numero=data["numero"],
            meta_token=data["meta_token"],
            meta_phone_id=data["meta_phone_id"],
            twilio_sid=data["twilio_sid"],
            rasa_url=data["rasa_url"],
            rasa_activo=data["rasa_activo"],
            activo=data["activo"],
            nombre_sucursal=data.get("nombre_sucursal"),
            row_id=row_id,
        )
        if ok:
            self._load()
            QMessageBox.information(self, "Guardado", "Número guardado correctamente.")
        else:
            QMessageBox.critical(self, "Error", "No se pudo guardar el número.")

    def _eliminar(self) -> None:
        row = self._tbl.currentRow()
        if row < 0:
            return
        item = self._tbl.item(row, 0)
        if not item:
            return
        rid = int(item.text())
        if QMessageBox.question(
            self, "Confirmar", "¿Eliminar este número de WhatsApp?",
            QMessageBox.Yes | QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        if self._svc.delete_numero(rid):
            self._load()


class _NumberDialog(QDialog):
    """Diálogo modal para agregar/editar un número WhatsApp."""

    def __init__(self, svc, existing: dict | None, parent=None) -> None:
        super().__init__(parent)
        self._svc = svc
        self._existing = existing or {}
        self.setWindowTitle(
            "Editar número WhatsApp" if existing else "Agregar número WhatsApp"
        )
        self.setMinimumWidth(500)
        self._build()

    def _build(self) -> None:
        from modulos.whatsapp.widgets import MaskedSecretField
        lay = QVBoxLayout(self)
        lay.setSpacing(Spacing.MD)
        lay.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)

        form = QFormLayout()
        form.setSpacing(Spacing.SM)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._cmb_suc = QComboBox()
        self._cmb_suc.addItem("Global (todas las sucursales)", None)
        for s in self._svc.list_sucursales():
            self._cmb_suc.addItem(s["nombre"], s["id"])

        self._cmb_canal = QComboBox()
        self._cmb_canal.addItems(["todos", "clientes", "rrhh", "alertas"])
        self._cmb_prov = QComboBox()
        self._cmb_prov.addItems(["meta", "twilio", "wppconnect", "baileys"])

        self._txt_numero   = PhoneWidget(default_country="+52")
        self._txt_phone_id = QLineEdit()
        self._txt_phone_id.setPlaceholderText("Meta Phone Number ID")

        self._fld_token = MaskedSecretField("Nuevo Access Token de Meta")
        if self._existing:
            self._fld_token.set_has_value(bool(self._existing.get("meta_token")))

        self._txt_sid  = QLineEdit()
        self._txt_sid.setPlaceholderText("Twilio Account SID")
        self._txt_rasa = QLineEdit()
        self._txt_rasa.setPlaceholderText("http://localhost:5005")
        self._chk_rasa   = QCheckBox("Habilitar Rasa")
        self._chk_activo = QCheckBox("Activo")
        self._chk_activo.setChecked(True)

        form.addRow("Sucursal:", self._cmb_suc)
        form.addRow("Canal:", self._cmb_canal)
        form.addRow("Proveedor:", self._cmb_prov)
        form.addRow("Número:", self._txt_numero)
        form.addRow("Phone ID (Meta):", self._txt_phone_id)
        form.addRow("Token/Secret:", self._fld_token)
        form.addRow("Account SID:", self._txt_sid)
        form.addRow("URL Rasa:", self._txt_rasa)
        form.addRow("", self._chk_rasa)
        form.addRow("", self._chk_activo)
        lay.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

        if self._existing:
            self._prefill()

    def _prefill(self) -> None:
        ex = self._existing
        for i in range(self._cmb_suc.count()):
            if self._cmb_suc.itemData(i) == ex.get("sucursal_id"):
                self._cmb_suc.setCurrentIndex(i)
                break
        idx_c = self._cmb_canal.findText(ex.get("canal") or "todos")
        if idx_c >= 0:
            self._cmb_canal.setCurrentIndex(idx_c)
        idx_p = self._cmb_prov.findText(ex.get("proveedor") or "meta")
        if idx_p >= 0:
            self._cmb_prov.setCurrentIndex(idx_p)
        self._txt_numero.set_phone(ex.get("numero_negocio") or "")
        self._txt_phone_id.setText(ex.get("meta_phone_id") or "")
        self._txt_sid.setText(ex.get("twilio_sid") or "")
        self._txt_rasa.setText(ex.get("rasa_url") or "http://localhost:5005")
        self._chk_rasa.setChecked(bool(ex.get("rasa_activo")))
        self._chk_activo.setChecked(bool(ex.get("activo", 1)))

    def get_data(self) -> dict:
        new_token = self._fld_token.get_new_value()
        # Si es edición y no se reemplazó token, preservar el existente
        if self._existing and not new_token:
            new_token = self._existing.get("meta_token") or ""
        return {
            "sucursal_id":    self._cmb_suc.currentData(),
            "nombre_sucursal": self._cmb_suc.currentText() if self._cmb_suc.currentData() else None,
            "canal":          self._cmb_canal.currentText(),
            "proveedor":      self._cmb_prov.currentText(),
            "numero":         self._txt_numero.get_e164().strip(),
            "meta_phone_id":  self._txt_phone_id.text().strip(),
            "meta_token":     new_token or "",
            "twilio_sid":     self._txt_sid.text().strip(),
            "rasa_url":       self._txt_rasa.text().strip() or "http://localhost:5005",
            "rasa_activo":    self._chk_rasa.isChecked(),
            "activo":         self._chk_activo.isChecked(),
        }
