"""Supplier detail (ficha) — header + lazy-loaded tabs (FASE SUP-5).

Sections load on first activation (no eager loading). UI only: reads/mutations
go through the presenter.
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from frontend.desktop.components import (
    ColumnSpec,
    StandardTable,
    StatusBadge,
    create_primary_button,
    create_secondary_button,
    create_success_button,
)
from frontend.desktop.modules.finance.suppliers.dialogs.supplier_dialogs import (
    SupplierBankAccountDialog,
    SupplierContactDialog,
    SupplierEvaluationDialog,
    SupplierTermsDialog,
)
from frontend.desktop.modules.finance.suppliers.supplier_view_models import (
    RISK_VARIANT,
    STATUS_VARIANT,
)
from frontend.desktop.themes.tokens import DialogMetrics, Spacing


class SupplierDetailDialog(QDialog):
    def __init__(self, presenter, supplier_id: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("standardDialog")
        self._presenter = presenter
        self._supplier_id = supplier_id
        self._loaded_tabs: set[int] = set()
        self.setMinimumSize(DialogMetrics.WIDTH_LG, 520)

        root = QVBoxLayout(self)
        root.setContentsMargins(DialogMetrics.PADDING, DialogMetrics.PADDING,
                                DialogMetrics.PADDING, DialogMetrics.PADDING)
        root.setSpacing(Spacing.MD)

        self._header = QHBoxLayout()
        self._title = QLabel("")
        self._title.setProperty("role", "dialogTitle")
        self._status_badge = StatusBadge("—")
        self._risk_badge = StatusBadge("—")
        self._header.addWidget(self._title, stretch=1)
        self._header.addWidget(self._status_badge)
        self._header.addWidget(self._risk_badge)
        root.addLayout(self._header)

        self._tabs = QTabWidget(self)
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._build_tabs()
        root.addWidget(self._tabs, stretch=1)

        close = create_secondary_button(self, "Cerrar")
        close.clicked.connect(self.accept)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(close)
        root.addLayout(bottom)

        self._load_header()
        self._on_tab_changed(0)

    # tabs --------------------------------------------------------------------
    def _build_tabs(self) -> None:
        self._summary = QLabel("")
        self._summary.setWordWrap(True)
        self._tabs.addTab(self._wrap(self._summary), "Resumen")

        self._contacts_table = StandardTable([
            ColumnSpec("Nombre"), ColumnSpec("Área", "status"), ColumnSpec("Cargo"),
            ColumnSpec("Teléfono", "text"), ColumnSpec("Correo"), ColumnSpec("Principal", "status")])
        self._tabs.addTab(self._section(self._contacts_table, "Agregar contacto",
                                        self._add_contact), "Contactos")

        self._bank_table = StandardTable([
            ColumnSpec("Banco"), ColumnSpec("Titular"), ColumnSpec("CLABE", "text"),
            ColumnSpec("Moneda", "status"), ColumnSpec("Estado", "status")])
        bank_tab = self._section(self._bank_table, "Agregar cuenta", self._add_bank,
                                 extra_label="Verificar", extra_cb=self._verify_bank)
        self._tabs.addTab(bank_tab, "Banco")

        self._terms_label = QLabel("Sin condiciones registradas.")
        self._tabs.addTab(self._section(self._terms_label, "Editar condiciones",
                                        self._edit_terms), "Condiciones")

        self._products_table = StandardTable([
            ColumnSpec("Producto"), ColumnSpec("SKU"), ColumnSpec("Unidad", "status"),
            ColumnSpec("Costo", "numeric"), ColumnSpec("Preferido", "status")])
        self._tabs.addTab(self._wrap(self._products_table), "Productos")

        self._docs_table = StandardTable([
            ColumnSpec("Documento"), ColumnSpec("Estado", "status"),
            ColumnSpec("Emitido", "date"), ColumnSpec("Vence", "date")])
        self._tabs.addTab(self._wrap(self._docs_table), "Documentos")

        self._risk_label = QLabel("")
        self._risk_label.setWordWrap(True)
        eval_tab = self._section(self._risk_label, "Evaluar proveedor", self._evaluate)
        self._tabs.addTab(eval_tab, "Riesgo y evaluación")

    def _wrap(self, widget: QWidget) -> QWidget:
        holder = QWidget()
        lay = QVBoxLayout(holder)
        lay.setContentsMargins(0, Spacing.SM, 0, 0)
        lay.addWidget(widget)
        return holder

    def _section(self, widget: QWidget, action_label: str, action_cb,
                 *, extra_label: str | None = None, extra_cb=None) -> QWidget:
        holder = QWidget()
        lay = QVBoxLayout(holder)
        lay.setContentsMargins(0, Spacing.SM, 0, 0)
        lay.setSpacing(Spacing.SM)
        lay.addWidget(widget, stretch=1)
        row = QHBoxLayout()
        row.addStretch(1)
        if extra_label:
            extra = create_success_button(self, extra_label)
            extra.clicked.connect(extra_cb)
            row.addWidget(extra)
        btn = create_primary_button(self, action_label)
        btn.clicked.connect(action_cb)
        row.addWidget(btn)
        lay.addLayout(row)
        return holder

    # loading -----------------------------------------------------------------
    def _load_header(self) -> None:
        header = self._presenter.supplier_header(self._supplier_id)
        if header is None:
            self._title.setText("Proveedor no encontrado")
            return
        self._title.setText(f"{header['supplier_code']} — {header['legal_name']}")
        self._status_badge.setText(header["status_label"])
        self._status_badge.set_status(STATUS_VARIANT.get(header["status"], "neutral"))
        self._risk_badge.setText(header["risk_label"])
        self._risk_badge.set_status(RISK_VARIANT.get(header["risk_level"], "neutral"))
        counts = header.get("counts", {})
        self._summary.setText(
            f"Contactos: {counts.get('contacts', 0)}  ·  Direcciones: {counts.get('addresses', 0)}"
            f"  ·  Cuentas bancarias: {counts.get('bank_accounts', 0)}  ·  "
            f"Productos: {counts.get('products', 0)}  ·  Documentos: {counts.get('documents', 0)}")

    def _on_tab_changed(self, index: int) -> None:
        if index in self._loaded_tabs:
            return
        self._loaded_tabs.add(index)
        loaders = {
            1: lambda: self._fill(self._contacts_table, self._presenter.contacts(self._supplier_id)),
            2: lambda: self._fill(self._bank_table, self._presenter.bank_accounts(self._supplier_id)),
            3: self._load_terms,
            4: lambda: self._fill(self._products_table, self._presenter.products(self._supplier_id)),
            5: lambda: self._fill(self._docs_table, self._presenter.documents(self._supplier_id)),
            6: self._load_risk,
        }
        loader = loaders.get(index)
        if loader:
            loader()

    def _fill(self, table: StandardTable, model) -> None:
        table.load_rows(model.rows, row_ids=model.row_ids)

    def _load_terms(self) -> None:
        self._terms_label.setText("Edita las condiciones comerciales con el botón inferior.")

    def _load_risk(self) -> None:
        risk = self._presenter.risk(self._supplier_id)
        causes = "\n".join(f"• {c}" for c in risk["causes"]) or "Sin factores de riesgo."
        self._risk_label.setText(f"Nivel de riesgo: {risk['label']}\n\nCausas:\n{causes}")

    # mutations ---------------------------------------------------------------
    def _refresh_tab(self, index: int) -> None:
        self._loaded_tabs.discard(index)
        self._on_tab_changed(index)
        self._load_header()

    def _notify(self, ok, msg, tab_index=None):
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Proveedores", msg)
        if ok and tab_index is not None:
            self._refresh_tab(tab_index)

    def _add_contact(self) -> None:
        dialog = SupplierContactDialog(self)
        if dialog.exec_():
            ok, msg, _ = self._presenter.add_contact(
                supplier_id=self._supplier_id, **dialog.values())
            self._notify(ok, msg, 1)

    def _add_bank(self) -> None:
        dialog = SupplierBankAccountDialog(self)
        if dialog.exec_():
            ok, msg, _ = self._presenter.add_bank_account(
                supplier_id=self._supplier_id, **dialog.values())
            self._notify(ok, msg, 2)

    def _verify_bank(self) -> None:
        account_id = self._bank_table.selected_row_id()
        if not account_id:
            self._notify(False, "Selecciona una cuenta bancaria.")
            return
        ok, msg, _ = self._presenter.verify_bank_account(account_id)
        self._notify(ok, msg, 2)

    def _edit_terms(self) -> None:
        dialog = SupplierTermsDialog(self)
        if dialog.exec_():
            ok, msg, _ = self._presenter.update_terms(
                supplier_id=self._supplier_id, **dialog.values())
            self._notify(ok, msg, 3)

    def _evaluate(self) -> None:
        dialog = SupplierEvaluationDialog(self)
        if dialog.exec_():
            ok, msg, _ = self._presenter.evaluate(
                supplier_id=self._supplier_id, **dialog.values())
            self._notify(ok, msg, 6)
