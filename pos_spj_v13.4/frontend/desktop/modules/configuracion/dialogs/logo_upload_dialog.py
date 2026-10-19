"""Cargar el logo de la empresa o de una sucursal (comparativa de tickets, 2026-10-16).

Antes la pantalla pedía teclear «el UUID de un asset de otro sistema» que no
existía. Aquí se elige la imagen y se ve ANTES y DESPUÉS: con «Quitar fondo» el
fondo conectado al borde se vuelve papel (el mismo removedor local de Productos)
y la tolerancia se ajusta (0 = automática); sin él se conserva el fondo. El
original nunca se destruye. «Usar el de la empresa» (sólo sucursales) quita el
logo propio y vuelve a heredar.
"""

from __future__ import annotations

import tempfile

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget

from frontend.desktop.components import (
    StandardCheckBox,
    create_primary_button,
    create_secondary_button,
)
from frontend.desktop.components.dialogs import StandardDialog

_PREVIEW_SIDE = 260


class LogoUploadDialog(StandardDialog):
    def __init__(self, presenter, *, title: str, branch_scope: bool = False,
                 parent=None) -> None:
        super().__init__(parent, title=title, width=640)
        self.setObjectName("logoUploadDialog")
        self._presenter = presenter
        self._source: str | None = None
        self._tmp = tempfile.mkdtemp(prefix="logo_")
        self.source_path: str | None = None
        self.remove_background = False
        self.tolerance = 0
        self.use_company_logo = False

        pick = create_secondary_button(self, "Elegir imagen…")
        pick.clicked.connect(self._pick)
        self.content_layout().addWidget(pick)

        self._remove = StandardCheckBox("Quitar fondo (el fondo se vuelve papel)", self)
        self._remove.toggled.connect(lambda _v: self._refresh())
        self.content_layout().addWidget(self._remove)
        row = QHBoxLayout()
        row.addWidget(QLabel("Tolerancia del fondo:", self))
        self._tolerance = QSlider(Qt.Horizontal, self)
        self._tolerance.setRange(0, 120)
        self._tolerance.setValue(0)
        self._tolerance.setAccessibleName("Tolerancia del fondo")
        self._tolerance.sliderReleased.connect(self._refresh)
        row.addWidget(self._tolerance, stretch=1)
        self._tolerance_label = QLabel("automática", self)
        self._tolerance.valueChanged.connect(self._on_tolerance)
        row.addWidget(self._tolerance_label)
        self.content_layout().addLayout(row)

        previews = QHBoxLayout()
        self._before = self._preview_box(previews, "Original")
        self._after = self._preview_box(previews, "Como se imprimirá")
        self.content_layout().addLayout(previews)
        self._message = QLabel("Elige una imagen PNG o JPG.", self)
        self._message.setWordWrap(True)
        self.content_layout().addWidget(self._message)

        footer = QWidget(self)
        actions = QHBoxLayout(footer)
        actions.setContentsMargins(0, 0, 0, 0)
        if branch_scope:
            inherit = create_secondary_button(self, "Usar el de la empresa")
            inherit.clicked.connect(self._inherit)
            actions.addWidget(inherit)
        actions.addStretch(1)
        cancel = create_secondary_button(self, "Cancelar")
        cancel.clicked.connect(self.reject)
        actions.addWidget(cancel)
        self._save = create_primary_button(self, "Guardar logo")
        self._save.setEnabled(False)
        self._save.clicked.connect(self._accept)
        actions.addWidget(self._save)
        self.add_footer_widget(footer)
        self._set_tolerance_enabled()

    def _preview_box(self, layout, caption: str) -> QLabel:
        box = QVBoxLayout()
        box.addWidget(QLabel(caption, self))
        label = QLabel(self)
        label.setFixedSize(_PREVIEW_SIDE, _PREVIEW_SIDE)
        label.setAlignment(Qt.AlignCenter)
        label.setProperty("role", "imagePreview")
        box.addWidget(label)
        layout.addLayout(box)
        return label

    def _on_tolerance(self, value: int) -> None:
        self._tolerance_label.setText("automática" if value == 0 else str(value))

    def _set_tolerance_enabled(self) -> None:
        self._tolerance.setEnabled(self._remove.isChecked())

    def _pick(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Logo", "", "Imágenes (*.png *.jpg *.jpeg *.bmp)")
        if path:
            self.set_source(path)

    def set_source(self, path: str) -> None:
        self._source = path
        self._refresh()

    def _refresh(self) -> None:
        self._set_tolerance_enabled()
        if not self._source:
            return
        preview, error = self._presenter.logo_preview(
            source_path=self._source, remove_background=self._remove.isChecked(),
            tolerance=self._tolerance.value(), preview_dir=self._tmp)
        if error:
            self._message.setText(error)
            self._save.setEnabled(False)
            return
        for label, path in ((self._before, preview.original_path),
                            (self._after, preview.print_path)):
            pixmap = QPixmap(path)
            label.setPixmap(pixmap.scaled(_PREVIEW_SIDE, _PREVIEW_SIDE, Qt.KeepAspectRatio,
                                          Qt.SmoothTransformation))
        self._message.setText("En el ticket se imprime en blanco y negro, al tamaño que "
                              "fije el diseño del ticket.")
        self._save.setEnabled(True)

    def _inherit(self) -> None:
        self.use_company_logo = True
        self.accept()

    def _accept(self) -> None:
        self.source_path = self._source
        self.remove_background = self._remove.isChecked()
        self.tolerance = self._tolerance.value()
        self.accept()
