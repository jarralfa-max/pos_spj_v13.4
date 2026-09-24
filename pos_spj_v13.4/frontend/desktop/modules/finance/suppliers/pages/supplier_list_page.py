"""Supplier master list — PageHeader + KPIBar + FilterBar + StandardTable.

FASE SUP-4. UI only: delegates every read/mutation to the presenter. Backend
pagination; view states (loading/empty/error) instead of misleading zeros.
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from frontend.desktop.components import (
    ColumnSpec,
    KPIBar,
    KPIDTO,
    PageHeader,
    SearchInput,
    SearchableComboBox,
    StandardTable,
    ViewState,
    create_primary_button,
    create_secondary_button,
    create_state_widget,
    create_success_button,
    create_danger_button,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.finance.suppliers.dialogs.supplier_dialogs import (
    SupplierBlockDialog,
    SupplierFormDialog,
    SupplierReasonDialog,
)
from frontend.desktop.themes.tokens import Spacing

_STATUS_FILTER = [
    ("", "Todos los estados"), ("ACTIVE", "Activo"), ("PENDING_APPROVAL", "Pendiente"),
    ("BLOCKED", "Bloqueado"), ("SUSPENDED", "Suspendido"), ("INACTIVE", "Baja"),
]
_COLUMNS = [
    ColumnSpec("Código", "text"), ColumnSpec("Proveedor", "text"),
    ColumnSpec("RFC", "text"), ColumnSpec("Estado", "status"),
    ColumnSpec("Rating", "status"), ColumnSpec("Riesgo", "status"),
]


class SupplierListPage(QWidget):
    def __init__(self, presenter, parent=None, *, on_open_detail=None) -> None:
        super().__init__(parent)
        self.setObjectName("supplierListPage")
        self._presenter = presenter
        self._on_open_detail = on_open_detail
        self._page = 0
        self._total = 0
        self._loaded = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Proveedores",
            subtitle="Maestro, condiciones, desempeño, riesgo y cuentas por pagar.",
            icon=Icons.FINANCE, compact=True)
        new_btn = create_primary_button(self, "Nuevo proveedor")
        new_btn.clicked.connect(self._create)
        self.header.add_action(new_btn)
        refresh = create_secondary_button(self, "Actualizar")
        refresh.clicked.connect(self.reload)
        self.header.add_action(refresh)
        layout.addWidget(self.header)

        self._kpi_bar = KPIBar(cards=[])
        layout.addWidget(self._kpi_bar)

        filters = QHBoxLayout()
        filters.setSpacing(Spacing.SM)
        self._search = SearchInput(placeholder="Buscar por código, razón social, RFC…")
        self._search.search_changed.connect(self._on_filter_changed)
        self._status = SearchableComboBox(placeholder="Todos los estados")
        self._status.set_options(_STATUS_FILTER[1:])
        self._status.selection_changed.connect(lambda _v: self._on_filter_changed())
        filters.addWidget(self._search, stretch=1)
        filters.addWidget(self._status)
        layout.addLayout(filters)

        self._stack = QStackedWidget(self)
        self._table = StandardTable(_COLUMNS, self)
        self._table.doubleClicked.connect(lambda *_: self._open_selected())
        self._empty = create_state_widget(ViewState.EMPTY, self,
                                          message="No hay proveedores que coincidan")
        self._stack.addWidget(self._table)   # 0
        self._stack.addWidget(self._empty)   # 1
        layout.addWidget(self._stack, stretch=1)

        actions = QHBoxLayout()
        actions.setSpacing(Spacing.SM)
        view_btn = create_secondary_button(self, "Ver ficha")
        view_btn.clicked.connect(self._open_selected)
        # El ciclo de vida comercial completo. Antes esta barra sólo ofrecía
        # Aprobar y Bloquear: enviar a aprobación, activar, suspender y dar de
        # baja existían en el dominio pero no había por dónde ejecutarlas, así
        # que un proveedor sólo podía avanzar o bloquearse, nunca reactivarse
        # ni darse de baja.
        submit_btn = create_secondary_button(self, "Enviar a aprobación")
        submit_btn.clicked.connect(self._submit)
        approve_btn = create_success_button(self, "Aprobar")
        approve_btn.clicked.connect(self._approve)
        activate_btn = create_success_button(self, "Activar")
        activate_btn.clicked.connect(self._activate)
        suspend_btn = create_secondary_button(self, "Suspender")
        suspend_btn.clicked.connect(self._suspend)
        deactivate_btn = create_danger_button(self, "Dar de baja")
        deactivate_btn.clicked.connect(self._deactivate)
        block_btn = create_danger_button(self, "Bloquear")
        block_btn.clicked.connect(self._block)
        for btn in (view_btn, submit_btn, approve_btn, activate_btn,
                    suspend_btn, deactivate_btn, block_btn):
            actions.addWidget(btn)
        actions.addStretch(1)
        self._prev = create_secondary_button(self, "Anterior")
        self._prev.clicked.connect(self._prev_page)
        self._next = create_secondary_button(self, "Siguiente")
        self._next.clicked.connect(self._next_page)
        self._page_label = QLabel("")
        self._page_label.setProperty("role", "muted")
        actions.addWidget(self._page_label)
        actions.addWidget(self._prev)
        actions.addWidget(self._next)
        layout.addLayout(actions)

    # lifecycle ---------------------------------------------------------------
    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()

    def reload(self) -> None:
        try:
            self._kpi_bar.set_cards([
                KPIDTO(key=str(i), title=k.title, value=k.value, variant=k.variant)
                for i, k in enumerate(self._presenter.overview_kpis())])
            model = self._presenter.suppliers(
                search=self._search.text().strip(),
                status=self._status.current_id(), page=self._page)
            self._total = model.total
            self._table.load_rows(model.rows, row_ids=model.row_ids)
            if model.rows:
                self._stack.setCurrentWidget(self._table)
            else:
                # El motivo se pide SÓLO cuando hace falta: es una consulta más
                # y no tiene sentido pagarla en el camino normal.
                self._empty.message_label.setText(
                    self._presenter.suppliers_empty_reason(
                        search=self._search.text().strip(),
                        status=self._status.current_id()))
                self._stack.setCurrentWidget(self._empty)
            self._page_label.setText(self._page_text())
            self._loaded = True
        except Exception as exc:  # surface, never swallow
            QMessageBox.warning(self, "Proveedores", f"No fue posible cargar:\n{exc}")

    # filters / pagination ----------------------------------------------------
    def _on_filter_changed(self) -> None:
        self._page = 0
        self.reload()

    def _page_text(self) -> str:
        start = self._page * 50 + 1 if self._total else 0
        end = min((self._page + 1) * 50, self._total)
        return f"{start}–{end} de {self._total}"

    def _prev_page(self) -> None:
        if self._page > 0:
            self._page -= 1
            self.reload()

    def _next_page(self) -> None:
        if (self._page + 1) * 50 < self._total:
            self._page += 1
            self.reload()

    # actions -----------------------------------------------------------------
    def _selected_id(self) -> str | None:
        return self._table.selected_row_id()

    def _notify(self, ok: bool, message: str) -> None:
        if ok:
            QMessageBox.information(self, "Proveedores", message)
            self.reload()
        else:
            QMessageBox.warning(self, "Proveedores", message)

    def _create(self) -> None:
        dialog = SupplierFormDialog(self)
        if not dialog.exec_():
            return
        ok, msg, data = self._presenter.create_supplier(**dialog.values())
        if not ok and data.get("duplicates"):
            reasons = "; ".join(r["reasons"][0] for r in data["duplicates"])
            proceed = QMessageBox.question(
                self, "Posible duplicado",
                f"{msg}: {reasons}.\n¿Continuar con la autorización de todos modos?")
            if proceed == QMessageBox.Yes:
                ok, msg, _ = self._presenter.create_supplier(
                    allow_duplicate=True, **dialog.values())
        self._notify(ok, msg)

    def _open_selected(self) -> None:
        supplier_id = self._selected_id()
        if not supplier_id:
            self._notify(False, "Selecciona un proveedor.")
            return
        if self._on_open_detail:
            self._on_open_detail(supplier_id)

    def _approve(self) -> None:
        supplier_id = self._selected_id()
        if not supplier_id:
            self._notify(False, "Selecciona un proveedor.")
            return
        ok, msg, _ = self._presenter.approve(supplier_id)
        self._notify(ok, msg)

    def _submit(self) -> None:
        supplier_id = self._selected_id()
        if not supplier_id:
            self._notify(False, "Selecciona un proveedor.")
            return
        ok, msg, _ = self._presenter.submit_for_approval(supplier_id)
        self._notify(ok, msg)

    def _activate(self) -> None:
        """Activa o reactiva (suspendido, bloqueado o dado de baja)."""
        supplier_id = self._selected_id()
        if not supplier_id:
            self._notify(False, "Selecciona un proveedor.")
            return
        ok, msg, _ = self._presenter.activate(supplier_id)
        self._notify(ok, msg)

    def _suspend(self) -> None:
        self._with_reason("suspend", title="Suspender proveedor",
                          ok_text="Suspender")

    def _deactivate(self) -> None:
        self._with_reason("deactivate", title="Dar de baja al proveedor",
                          ok_text="Dar de baja")

    def _with_reason(self, action: str, *, title: str, ok_text: str) -> None:
        """Suspender y dar de baja EXIGEN motivo: una baja sin causa registrada
        es indistinguible de un error de captura cuando alguien la revisa
        después."""
        supplier_id = self._selected_id()
        if not supplier_id:
            self._notify(False, "Selecciona un proveedor.")
            return
        dialog = SupplierReasonDialog(self, title=title)
        if not dialog.exec_():
            return
        operation = getattr(self._presenter, action)
        ok, msg, _ = operation(supplier_id, dialog.reason())
        self._notify(ok, msg)

    def _block(self) -> None:
        supplier_id = self._selected_id()
        if not supplier_id:
            self._notify(False, "Selecciona un proveedor.")
            return
        dialog = SupplierBlockDialog(self)
        if dialog.exec_():
            values = dialog.values()
            ok, msg, _ = self._presenter.block(
                supplier_id, block_type=values["block_type"], reason=values["reason"])
            self._notify(ok, msg)
