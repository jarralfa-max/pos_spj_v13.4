"""ImageGalleryDialog — galería de imágenes de un producto (P1).

UI-only: lista las imágenes del producto, permite agregar (elige archivo), marcar la
principal y eliminar. Muestra una vista previa de la imagen seleccionada. Delega en
el presenter → use cases canónicos. No copia binarios: guarda la ruta/URI elegida.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from frontend.desktop.components import ColumnSpec, StandardTable


class ImageGalleryDialog(QDialog):
    def __init__(self, presenter, *, product_id: str, product_name: str,
                 parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._product_id = product_id
        self.setObjectName("imageGalleryDialog")
        self.setWindowTitle(f"Imágenes de «{product_name}»")
        self.setMinimumSize(560, 400)

        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        self.btn_add = QPushButton("Agregar…")
        self.btn_primary = QPushButton("Marcar principal")
        self.btn_remove = QPushButton("Eliminar")
        can_manage = bool(getattr(self._presenter, "can_manage_images", False))
        for b in (self.btn_add, self.btn_primary, self.btn_remove):
            b.setEnabled(can_manage)
            toolbar.addWidget(b)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)
        self.btn_add.clicked.connect(self._on_add)
        self.btn_primary.clicked.connect(self._on_primary)
        self.btn_remove.clicked.connect(self._on_remove)

        body = QHBoxLayout()
        self.table = StandardTable(columns=[
            ColumnSpec("Imagen", "uri"),
            ColumnSpec("Principal", "principal"),
        ])
        self.table.itemSelectionChanged.connect(self._update_preview)
        body.addWidget(self.table, 2)
        self.preview = QLabel("Sin selección")
        self.preview.setObjectName("imagePreview")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumWidth(200)
        body.addWidget(self.preview, 1)
        layout.addLayout(body, 1)

        self._error = QLabel()
        self._error.setObjectName("textDanger")
        self._error.setWordWrap(True)
        layout.addWidget(self._error)

        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.button(QDialogButtonBox.Close).setText("Cerrar")
        close.rejected.connect(self.reject)
        close.accepted.connect(self.accept)
        layout.addWidget(close)
        self.refresh()

    def refresh(self) -> None:
        self._images = self._presenter.list_images(self._product_id)
        rows = [[img["uri"], "★" if img["is_primary"] else ""]
                for img in self._images]
        self.table.load_rows(rows, row_ids=[img["id"] for img in self._images])

    def _selected(self):
        image_id = self.table.selected_row_id()
        if not image_id:
            return None
        return next((i for i in self._images if i["id"] == image_id), None)

    def _update_preview(self) -> None:
        img = self._selected()
        if img is None:
            self.preview.setText("Sin selección")
            self.preview.setPixmap(QPixmap())
            return
        pix = QPixmap(img["uri"])
        if pix.isNull():
            self.preview.setText(img.get("alt_text") or "Vista previa no disponible")
        else:
            self.preview.setPixmap(pix.scaled(
                200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _on_add(self) -> None:
        self._error.setText("")
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar imagen", "",
            "Imágenes (*.png *.jpg *.jpeg *.webp *.gif);;Todos los archivos (*)")
        if not path:
            return
        ok, message = self._presenter.add_image(product_id=self._product_id, uri=path)
        if ok:
            self.refresh()
        else:
            self._error.setText(message)

    def _on_primary(self) -> None:
        img = self._selected()
        if img is None:
            return
        ok, message = self._presenter.set_primary_image(img["id"])
        if ok:
            self.refresh()
        else:
            self._error.setText(message)

    def _on_remove(self) -> None:
        img = self._selected()
        if img is None:
            return
        ok, message = self._presenter.remove_image(img["id"])
        if ok:
            self.refresh()
        else:
            self._error.setText(message)
