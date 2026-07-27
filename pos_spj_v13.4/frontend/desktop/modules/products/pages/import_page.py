"""Importación de productos CSV/XLSX — página con vista previa y aprobación.

UI only: elegir archivo → se crea un batch en vista previa (staging validado); el
usuario revisa las filas (válidas/ inválidas con su error), **aprueba** (segundo
usuario, segregación) y **ejecuta** (crea los productos). Toda mutación pasa por el
presenter → use cases canónicos. Sin SQL ni lógica de negocio.
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from frontend.desktop.components import ColumnSpec, PageHeader, StandardTable
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing

_STATUS_ES = {"VALID": "Válida", "INVALID": "Inválida", "CREATED": "Creada"}
_JOB_ES = {"PREVIEWED": "Vista previa", "APPROVED": "Aprobado",
           "EXECUTED": "Ejecutado", "FAILED": "Fallido"}


class ProductImportPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("productImportPage")
        self._presenter = presenter
        self._job_id: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Importar productos",
            subtitle="Carga un CSV o XLSX, revisa la vista previa, aprueba y ejecuta.",
            icon=getattr(Icons, "CATALOG", None), compact=True)
        layout.addWidget(self.header)

        toolbar = QHBoxLayout()
        self.btn_choose = QPushButton("Elegir archivo…")
        self.btn_approve = QPushButton("Aprobar")
        self.btn_execute = QPushButton("Ejecutar")
        can_import = bool(getattr(self._presenter, "can_import", False))
        self.btn_choose.setEnabled(can_import)
        self.btn_approve.setEnabled(
            bool(getattr(self._presenter, "can_approve_import", False)))
        self.btn_execute.setEnabled(can_import)
        for b in (self.btn_choose, self.btn_approve, self.btn_execute):
            toolbar.addWidget(b)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)
        self.btn_choose.clicked.connect(self._on_choose)
        self.btn_approve.clicked.connect(self._on_approve)
        self.btn_execute.clicked.connect(self._on_execute)

        self._summary = QLabel("Sin importación activa.")
        self._summary.setObjectName("textMuted")
        layout.addWidget(self._summary)

        self.table = StandardTable(columns=[
            ColumnSpec("#", "row"),
            ColumnSpec("Código", "code"),
            ColumnSpec("Nombre", "name"),
            ColumnSpec("Tipo", "product_type"),
            ColumnSpec("Estado", "status"),
            ColumnSpec("Detalle", "error"),
        ])
        layout.addWidget(self.table, 1)

        self._error = QLabel()
        self._error.setObjectName("textDanger")
        self._error.setWordWrap(True)
        layout.addWidget(self._error)

    # ── acciones ───────────────────────────────────────────────────────────
    def _on_choose(self) -> None:
        self._error.setText("")
        path, _ = QFileDialog.getOpenFileName(
            self, "Elegir archivo", "",
            "Datos (*.csv *.xlsx);;Todos los archivos (*)")
        if not path:
            return
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError as exc:
            self._error.setText(f"No se pudo leer el archivo: {exc}")
            return
        filename = path.rsplit("/", 1)[-1]
        ok, message, job_id = self._presenter.create_import_batch(
            filename=filename, data=data)
        if ok:
            self._job_id = job_id
            self._refresh()
        else:
            self._error.setText(message)

    def _on_approve(self) -> None:
        self._error.setText("")
        if not self._job_id:
            return
        ok, message, _ = self._presenter.approve_import_batch(self._job_id)
        if ok:
            self._refresh()
        else:
            self._error.setText(message)

    def _on_execute(self) -> None:
        self._error.setText("")
        if not self._job_id:
            return
        ok, message, _ = self._presenter.execute_import_batch(self._job_id)
        if ok:
            self._refresh()
        else:
            self._error.setText(message)

    def _refresh(self) -> None:
        if not self._job_id:
            return
        rows = self._presenter.import_preview(self._job_id)
        table_rows = []
        for r in rows:
            p = r.get("payload", {})
            table_rows.append([str(r["row_number"]), p.get("code") or "",
                               p.get("name") or "", p.get("product_type") or "",
                               _STATUS_ES.get(r["status"], r["status"]),
                               r.get("error") or ""])
        self.table.load_rows(table_rows, row_ids=[str(r["row_number"]) for r in rows])
        job = next((j for j in self._presenter.list_import_jobs()
                    if j["id"] == self._job_id), None)
        if job:
            self._summary.setText(
                f"{job['filename']} — {_JOB_ES.get(job['status'], job['status'])} · "
                f"{job['total_rows']} filas · {job['valid_rows']} válidas · "
                f"{job['invalid_rows']} inválidas · {job['created_rows']} creadas")
