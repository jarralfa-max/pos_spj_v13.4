"""Páginas de Logística (integración 32cfbf): Contenedores y Embarques.

Contenedores es el catálogo autónomo que faltaba: alta (también sin embarque
abierto), edición, estado operativo (limpieza, mantenimiento, cuarentena,
baja), historial y reimpresión del QR, con el motivo por el que uno no puede
cargarse. Sin SQL ni reglas: todo por el presentador."""

from __future__ import annotations

from PyQt5.QtWidgets import QAbstractItemView, QDialog, QHBoxLayout, QLabel

from frontend.desktop.components import (
    ColumnSpec,
    SearchInput,
    StandardPage,
    StandardTable,
    create_primary_button,
    create_secondary_button,
)


class _Page(StandardPage):
    def __init__(self, presenter, parent=None, *, title: str, subtitle: str) -> None:
        super().__init__(parent, title=title, subtitle=subtitle)
        self._presenter = presenter
        self._loaded = False
        self._layout = self.content_layout
        self.feedback = QLabel("", self)
        self.feedback.setWordWrap(True)
        self._layout.addWidget(self.feedback)

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self._loaded = True
            self.refresh()

    def refresh(self) -> None:  # pragma: no cover - cada página lo define
        raise NotImplementedError

    def _show(self, ok: bool, message: str) -> None:
        self.feedback.setObjectName("textSuccess" if ok else "textDanger")
        self.feedback.setText(message)
        self.feedback.style().unpolish(self.feedback)
        self.feedback.style().polish(self.feedback)


class ContainersPage(_Page):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(presenter, parent, title="Contenedores",
                         subtitle="Catálogo de contenedores físicos con su QR permanente, "
                                  "estado y custodia.")
        self.setObjectName("logisticsContainersPage")
        self._rows: list[dict] = []
        # La búsqueda en su propio renglón: compartido con cinco botones se
        # quedaba de ~20 px de ancho.
        self.search = SearchInput(placeholder="Buscar por código o tipo")
        self.search.search_changed.connect(lambda *_: self.refresh())
        self._layout.addWidget(self.search)
        barra = QHBoxLayout()
        self.new_button = create_primary_button(text="Registrar contenedores")
        self.new_button.clicked.connect(self._on_new)
        self.edit_button = create_secondary_button(text="Editar")
        self.edit_button.clicked.connect(self._on_edit)
        self.status_button = create_secondary_button(text="Cambiar estado")
        self.status_button.clicked.connect(self._on_status)
        self.history_button = create_secondary_button(text="Historial")
        self.history_button.clicked.connect(self._on_history)
        self.print_button = create_secondary_button(text="Etiquetas QR")
        self.print_button.setToolTip("Etiqueta con QR de los contenedores elegidos (se pueden "
                                     "elegir varios con Ctrl o Mayús): PDF o térmica.")
        self.print_button.clicked.connect(self._on_labels)
        for boton in (self.new_button, self.edit_button, self.status_button,
                      self.history_button, self.print_button):
            barra.addWidget(boton)
        barra.addStretch(1)
        self._layout.addLayout(barra)
        self.table = StandardTable(columns=[
            ColumnSpec("Código"), ColumnSpec("Tipo"), ColumnSpec("Estado", "status"),
            ColumnSpec("Tara kg", "numeric"), ColumnSpec("Capacidad kg", "numeric"),
            ColumnSpec("Ubicación"), ColumnSpec("¿Se puede cargar?")])
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._layout.addWidget(self.table, 1)
        puede = presenter.can_manage()
        for boton in (self.new_button, self.edit_button, self.status_button):
            boton.setEnabled(puede)
            if not puede:
                boton.setToolTip("Requiere el permiso «Gestionar contenedores».")
        self.print_button.setEnabled(presenter.can_print())

    def refresh(self) -> None:
        self._rows = self._presenter.containers(self.search.text().strip())
        self.table.load_rows([
            [r["code"], r["type_name"], r["status_label"], str(r["tare_weight"] or ""),
             str(r["capacity_weight"] or "—"), r["location_id"] or "—",
             "Sí" if r["loadable"] else r["not_loadable_reason"]] for r in self._rows],
            row_ids=[r["id"] for r in self._rows])
        if not self._rows:
            self._show(True, "No hay contenedores registrados. Al registrarlos el sistema "
                             "les asigna código y QR permanente; luego imprime sus etiquetas.")

    def _selected(self) -> dict | None:
        cid = self.table.selected_row_id()
        fila = next((r for r in self._rows if r["id"] == cid), None)
        if fila is None:
            self._show(False, "Selecciona un contenedor de la lista.")
        return fila

    def _after(self, ok: bool, message: str) -> None:
        self._show(ok, message)
        if ok:
            self.refresh()

    def _on_new(self) -> None:
        from frontend.desktop.modules.purchasing.dialogs.origin_dialogs import (
            ContainerRegisterDialog,
        )
        dialogo = ContainerRegisterDialog(self, type_options=self._presenter.container_types(),
                                          code_preview=self._presenter.next_code_preview)
        if dialogo.exec_() != QDialog.Accepted:
            return
        type_id = None
        if dialogo.creates_type():
            ok, mensaje, type_id = self._presenter.register_type(**dialogo.type_values())
            if not ok:
                self._show(False, mensaje)
                return
        ok, mensaje, resultado = self._presenter.register_container(
            **dialogo.container_values(type_id))
        self._after(ok, mensaje)
        if ok and resultado and self._presenter.can_print():
            self._open_labels(resultado["container_ids"], resultado["codes"])

    def _on_edit(self) -> None:
        from frontend.desktop.modules.logistics.dialogs import ContainerEditDialog
        fila = self._selected()
        if fila is None:
            return
        dialogo = ContainerEditDialog(self, container=fila)
        if dialogo.exec_() == QDialog.Accepted:
            ok, mensaje, _ = self._presenter.update_container(fila["id"], **dialogo.values())
            self._after(ok, mensaje)

    def _on_status(self) -> None:
        from frontend.desktop.modules.logistics.dialogs import ContainerStatusDialog
        fila = self._selected()
        if fila is None:
            return
        dialogo = ContainerStatusDialog(self, container=fila)
        if dialogo.exec_() == QDialog.Accepted:
            ok, mensaje, _ = self._presenter.set_status(
                fila["id"], dialogo.status.current_id(), dialogo.reason.text().strip())
            self._after(ok, mensaje)

    def _on_history(self) -> None:
        from frontend.desktop.modules.logistics.dialogs import ContainerHistoryDialog
        fila = self._selected()
        if fila is not None:
            ContainerHistoryDialog(self, container=fila,
                                   history=self._presenter.history(fila["id"])).exec_()

    def _on_labels(self) -> None:
        ids = self.table.selected_row_ids()
        if not ids:
            self._show(False, "Selecciona uno o varios contenedores de la lista.")
            return
        codigos = [r["code"] for r in self._rows if r["id"] in set(ids)]
        self._open_labels(ids, codigos)

    def _open_labels(self, ids: list[str], codes: list[str]) -> None:
        from frontend.desktop.modules.logistics.dialogs import ContainerLabelDialog
        dialogo = ContainerLabelDialog(
            self, codes=codes, formats=self._presenter.label_formats(),
            preview=lambda fmt: self._presenter.label_preview(ids[0], fmt),
            reprinted=self._presenter.reprint_codes(ids))
        if dialogo.exec_() != QDialog.Accepted:
            return
        valores = dialogo.values()
        if valores["fmt"] == "THERMAL_ROLL":
            ok, mensaje, _ = self._presenter.print_labels_thermal(
                ids, valores["copies"], valores["reason"])
            self._show(ok, mensaje)
            return
        sugerido = (f"etiqueta_{codes[0]}.pdf" if len(codes) == 1
                    else f"etiquetas_{codes[0]}_a_{codes[-1]}.pdf")
        ruta = self._ask_pdf_path(sugerido)
        if not ruta:
            return
        ok, mensaje, _ = self._presenter.export_labels_pdf(
            ids, valores["fmt"], valores["copies"], valores["reason"], ruta)
        self._show(ok, mensaje)
        if ok:
            self._open_file(ruta)

    def _ask_pdf_path(self, sugerido: str) -> str:
        from PyQt5.QtWidgets import QFileDialog
        ruta, _ = QFileDialog.getSaveFileName(self, "Guardar etiquetas en PDF", sugerido,
                                              "PDF (*.pdf)")
        return ruta

    def _open_file(self, ruta: str) -> None:
        """Abre el PDF en el visor del equipo para imprimirlo en la impresora de
        etiquetas o en hojas."""
        from PyQt5.QtCore import QUrl
        from PyQt5.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(ruta))


_SHIPMENT_STATUS = {
    "DRAFT": "Borrador", "PLANNED": "Planeado", "LOADING": "En carga", "SEALED": "Sellado",
    "DISPATCHED": "Despachado", "IN_TRANSIT": "En tránsito", "ARRIVED": "Llegó",
    "RECEIVING": "En recepción", "RECEIVED": "Recibido", "CLOSED": "Cerrado",
    "CANCELLED": "Cancelado",
}


class ShipmentsPage(_Page):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(presenter, parent, title="Embarques",
                         subtitle="Viajes con su estado, contenedores y fechas de despacho, "
                                  "llegada y cierre. La carga y la recepción se operan en "
                                  "«Compra en origen».")
        self.setObjectName("logisticsShipmentsPage")
        self.search = SearchInput(placeholder="Buscar por folio u origen")
        self.search.search_changed.connect(lambda *_: self.refresh())
        self._layout.addWidget(self.search)
        self.table = StandardTable(columns=[
            ColumnSpec("Folio"), ColumnSpec("Estado", "status"), ColumnSpec("Origen"),
            ColumnSpec("Contenedores", "numeric"), ColumnSpec("Despacho"),
            ColumnSpec("Llegada"), ColumnSpec("Cierre")])
        self._layout.addWidget(self.table, 1)

    def refresh(self) -> None:
        filas = self._presenter.shipments(self.search.text().strip())
        self.table.load_rows([
            [f["number"], _SHIPMENT_STATUS.get(f["status"], f["status"]), f["origin"],
             str(f["containers"]), f["dispatched_at"] or "—", f["arrived_at"] or "—",
             f["closed_at"] or "—"] for f in filas], row_ids=[f["id"] for f in filas])
        if not filas:
            self._show(True, "Aún no hay embarques.")


class UnavailablePage(StandardPage):
    """Ruta cuyo requisito no está (módulo no instalado o sin permiso): se dice
    qué falta en vez de dejar la pantalla vacía."""

    def __init__(self, title: str, message: str, parent=None) -> None:
        super().__init__(parent, title=title, subtitle=message)
        self.content_layout.addStretch(1)
