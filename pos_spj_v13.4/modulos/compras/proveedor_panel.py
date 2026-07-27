# modulos/compras/proveedor_panel.py — SPJ POS v13.4
"""
ProveedorPanel — standalone QWidget for provider selection in the purchase form.

Signals:
    proveedor_seleccionado(int, str)  — (id, nombre) when a provider is confirmed

Usage:
    panel = ProveedorPanel(prov_repo=container._prov_repo, parent=self)
    panel.proveedor_seleccionado.connect(self._on_proveedor)
"""
from __future__ import annotations
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QFrame,
)
from PyQt5.QtCore import Qt, QStringListModel, pyqtSignal
from PyQt5.QtWidgets import QCompleter
from modulos.design_tokens import Colors, Spacing, Typography, Borders
from modulos.ui_components import create_secondary_button, create_input


class ProveedorPanel(QWidget):
    """
    Provider search panel: inline completer (no popup window),
    read-only info fields, and CxP alert banner.

    Does NO SQL — all data queries go through the injected repository.
    """
    proveedor_seleccionado = pyqtSignal(int, str)

    def __init__(self, prov_repo=None, parent=None):
        super().__init__(parent)
        self._repo = prov_repo
        self._proveedores: list[dict] = []
        self._prov_id: int | None = None
        self._build_ui()

    def set_repo(self, repo) -> None:
        self._repo = repo

    def cargar_proveedores(self) -> None:
        if not self._repo:
            return
        self._proveedores = self._repo.get_activos()
        self._model.setStringList([p["nombre"] for p in self._proveedores])

    def get_proveedor_id(self) -> int | None:
        return self._prov_id

    def clear_selection(self) -> None:
        self._prov_id = None
        self.txt_proveedor.clear()
        self._lbl_status.setText("Sin proveedor seleccionado")
        self._lbl_status.setStyleSheet(f"color:{Colors.WARNING_BASE};")
        self._lbl_info.hide()
        self.alert_bar.hide()

    def set_proveedor(self, prov_id: int, nombre: str) -> None:
        self._prov_id = prov_id
        self.txt_proveedor.setText(nombre)
        self._lbl_status.setText(f"✔ {nombre}")
        self._lbl_status.setStyleSheet(f"color:{Colors.SUCCESS_BASE};")
        self._load_info(prov_id)

    def show_cxp_alert(self, count: int, monto: float) -> None:
        if count > 0:
            self.alert_bar.setText(
                f"⚠  Este proveedor tiene {count} compra(s) pendiente(s) "
                f"por ${monto:,.2f} — verifica antes de continuar."
            )
            self.alert_bar.show()
        else:
            self.alert_bar.hide()

    # ── Private ───────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(Spacing.XS)

        # Search row
        search_row = QHBoxLayout()
        search_row.setSpacing(Spacing.XS)
        self.txt_proveedor = create_input(self, "Buscar proveedor…")
        self._model = QStringListModel(self)
        self._completer = QCompleter(self._model, self)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchContains)
        self._completer.setCompletionMode(QCompleter.InlineCompletion)
        self.txt_proveedor.setCompleter(self._completer)
        self._completer.activated[str].connect(self._on_activated)
        self.txt_proveedor.editingFinished.connect(self._resolve_from_text)

        btn_nuevo = create_secondary_button(self, "Nuevo +", "Registrar nuevo proveedor")
        btn_nuevo.setFixedHeight(28)
        btn_nuevo.setMaximumWidth(72)
        search_row.addWidget(self.txt_proveedor, 1)
        search_row.addWidget(btn_nuevo)
        root.addLayout(search_row)

        self._lbl_status = QLabel("Sin proveedor seleccionado")
        self._lbl_status.setObjectName("caption")
        self._lbl_status.setStyleSheet(f"color:{Colors.WARNING_BASE};")
        root.addWidget(self._lbl_status)

        self._lbl_info = QLabel("")
        self._lbl_info.setObjectName("caption")
        self._lbl_info.setWordWrap(True)
        self._lbl_info.setStyleSheet(f"color:{Colors.NEUTRAL.SLATE_600};background:transparent;")
        self._lbl_info.hide()
        root.addWidget(self._lbl_info)

        self.alert_bar = QLabel("")
        self.alert_bar.setWordWrap(True)
        self.alert_bar.setObjectName("caption")
        self.alert_bar.setStyleSheet(
            f"background:{Colors.WARNING_BASE}18;"
            f"border:1px solid {Colors.WARNING_BASE}60;"
            f"border-radius:{Borders.RADIUS_SM}px;padding:5px 10px;"
            f"color:{Colors.WARNING_BASE};"
        )
        self.alert_bar.hide()
        root.addWidget(self.alert_bar)

    def _on_activated(self, nombre: str) -> None:
        for p in self._proveedores:
            if p["nombre"] == nombre:
                self.set_proveedor(p["id"], nombre)
                self.proveedor_seleccionado.emit(p["id"], nombre)
                return

    def _resolve_from_text(self) -> None:
        txt = (self.txt_proveedor.text() or "").strip().lower()
        for p in self._proveedores:
            if p["nombre"].strip().lower() == txt:
                self.set_proveedor(p["id"], p["nombre"])
                self.proveedor_seleccionado.emit(p["id"], p["nombre"])
                return
        self._prov_id = None
        self._lbl_status.setText("⚠ Proveedor no reconocido" if txt else "Sin proveedor seleccionado")
        self._lbl_status.setStyleSheet(
            f"color:{Colors.DANGER_BASE};" if txt else f"color:{Colors.WARNING_BASE};"
        )
        self._lbl_info.hide()

    def _load_info(self, prov_id: int) -> None:
        if not self._repo:
            return
        data = self._repo.get_by_id(prov_id)
        if not data:
            self._lbl_info.hide()
            return

        def _k(*keys):
            for k in keys:
                v = data.get(k)
                if v is not None:
                    return str(v).strip()
            return ""

        parts = []
        if rfc := _k("rfc"):         parts.append(f"RFC: {rfc}")
        if dirs := _k("direccion"):   parts.append(dirs[:48])
        if tel := _k("telefono"):     parts.append(f"Tel: {tel}")
        if cond := _k("condicion_pago", "condiciones_pago"):
            parts.append(cond)
        if parts:
            self._lbl_info.setText("  ·  ".join(parts))
            self._lbl_info.show()
        else:
            self._lbl_info.hide()
