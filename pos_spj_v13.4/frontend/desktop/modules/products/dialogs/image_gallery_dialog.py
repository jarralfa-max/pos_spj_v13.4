"""ImageGalleryDialog — galería de imágenes de un producto (P1 + PROD-21).

UI-only: lista las imágenes del producto, permite agregar (elige archivo), marcar
la principal, eliminar, quitar el fondo y restaurar el original. Muestra una
vista previa de la imagen seleccionada. Delega en el presenter → use cases
canónicos (el caso de uso copia el archivo a la carpeta de la aplicación).

La imagen principal es la que aparece en las tarjetas del POS; se indica en el
texto de ayuda para que el usuario sepa qué efecto tiene cada acción.
"""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

from frontend.desktop.components import ColumnSpec, StandardTable
from frontend.desktop.components.buttons import (
    create_danger_button,
    create_primary_button,
    create_secondary_button,
)
from frontend.desktop.components.dialogs import StandardDialog
from frontend.desktop.components.image_thumbnail import ImageThumbnail
from frontend.desktop.themes.tokens import DialogMetrics

PREVIEW_SIZE = 220


class ImageGalleryDialog(StandardDialog):
    def __init__(self, presenter, *, product_id: str, product_name: str,
                 parent=None) -> None:
        super().__init__(parent, title=f"Imágenes de «{product_name}»",
                         width=DialogMetrics.WIDTH_LG)
        self._presenter = presenter
        self._product_id = product_id
        self._product_name = product_name
        self._images: list[dict] = []
        self.setObjectName("imageGalleryDialog")
        self.setMinimumSize(760, 560)

        layout = self.content_layout()
        hint = QLabel("La imagen principal es la que se muestra en las tarjetas del POS. "
                      "«Quitar fondo» funciona mejor con el producto completo sobre un "
                      "fondo liso.")
        hint.setProperty("role", "muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        toolbar = QHBoxLayout()
        self.btn_add = create_primary_button(self, "Agregar…")
        self.btn_primary = create_secondary_button(self, "Marcar principal")
        self.btn_remove_bg = create_secondary_button(
            self, "Quitar fondo", "Deja el producto sobre fondo transparente")
        self.btn_restore_bg = create_secondary_button(
            self, "Restaurar original", "Vuelve a la foto con su fondo")
        self.btn_remove = create_danger_button(self, "Eliminar")
        self._can_manage = bool(getattr(self._presenter, "can_manage_images", False))
        for b in (self.btn_add, self.btn_primary, self.btn_remove_bg,
                  self.btn_restore_bg, self.btn_remove):
            toolbar.addWidget(b)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)
        self.btn_add.clicked.connect(self._on_add)
        self.btn_primary.clicked.connect(self._on_primary)
        self.btn_remove_bg.clicked.connect(self._on_remove_background)
        self.btn_restore_bg.clicked.connect(self._on_restore_background)
        self.btn_remove.clicked.connect(self._on_remove)

        body = QHBoxLayout()
        self.table = StandardTable(columns=[
            ColumnSpec("Imagen", "text", min_width=120, preferred_width=200, stretch=True),
            ColumnSpec("Principal", "status", min_width=80, preferred_width=90),
            ColumnSpec("Fondo", "status", min_width=80, preferred_width=90),
        ])
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        body.addWidget(self.table, 2)
        preview_box = QVBoxLayout()
        self.preview = ImageThumbnail(self, width=PREVIEW_SIZE, height=PREVIEW_SIZE)
        self.preview.setObjectName("imagePreview")
        preview_box.addWidget(self.preview, 0, Qt.AlignTop | Qt.AlignHCenter)
        self.preview_caption = QLabel("Sin selección")
        self.preview_caption.setProperty("role", "muted")
        self.preview_caption.setAlignment(Qt.AlignCenter)
        self.preview_caption.setWordWrap(True)
        preview_box.addWidget(self.preview_caption)
        preview_box.addStretch(1)
        body.addLayout(preview_box, 1)
        layout.addLayout(body, 1)

        self._error = QLabel()
        self._error.setWordWrap(True)
        self._error.setProperty("role", "banner")
        self._error.setProperty("state", "error")
        self._error.hide()
        layout.addWidget(self._error)

        close = QDialogButtonBox(QDialogButtonBox.Close, self)
        close.button(QDialogButtonBox.Close).setText("Cerrar")
        close.rejected.connect(self.reject)
        layout.addWidget(close)
        self.refresh()

    # ── datos ──────────────────────────────────────────────────────────────
    def refresh(self, select_id: str | None = None) -> None:
        self._images = self._presenter.list_images(self._product_id)
        rows = [[img.get("alt_text") or f"Imagen {index}",
                 "Principal" if img["is_primary"] else "",
                 "Sin fondo" if img.get("background_removed") else "Original"]
                for index, img in enumerate(self._images, start=1)]
        self.table.load_rows(rows, row_ids=[img["id"] for img in self._images])
        if select_id is None and self._images:
            select_id = self._images[0]["id"]
        if select_id:
            for row, img in enumerate(self._images):
                if img["id"] == select_id:
                    self.table.selectRow(row)
                    break
        self._on_selection_changed()

    def _selected(self):
        image_id = self.table.selected_row_id()
        if not image_id:
            return None
        return next((i for i in self._images if i["id"] == image_id), None)

    def _on_selection_changed(self) -> None:
        img = self._selected()
        manage = self._can_manage
        self.btn_add.setEnabled(manage)
        self.btn_primary.setEnabled(manage and img is not None and not img["is_primary"])
        self.btn_remove.setEnabled(manage and img is not None)
        removed = bool(img and img.get("background_removed"))
        self.btn_remove_bg.setEnabled(manage and img is not None and not removed)
        self.btn_restore_bg.setEnabled(manage and removed)
        if img is None:
            self.preview.set_image(None, placeholder=self._product_name)
            self.preview_caption.setText("Sin selección")
            return
        shown = self.preview.set_image(img["uri"], placeholder=self._product_name,
                                       accessible_name=f"Vista previa de {self._product_name}")
        self.preview_caption.setText(
            ("Sin fondo" if removed else "Foto original") if shown
            else "El archivo de esta imagen no está en este equipo")

    # ── acciones ───────────────────────────────────────────────────────────
    def _set_error(self, message: str) -> None:
        self._error.setText(message)
        self._error.setVisible(bool(message))

    def _apply(self, ok: bool, message: str, select_id: str | None = None) -> None:
        if ok:
            self._set_error("")
            self.refresh(select_id)
        else:
            self._set_error(message)

    def _on_add(self) -> None:
        self._set_error("")
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar imagen", "",
            "Imágenes (*.png *.jpg *.jpeg *.webp *.gif *.bmp);;Todos los archivos (*)")
        if not path:
            return
        # El archivo se copia con nombre UUID; el nombre original queda como
        # texto alternativo para reconocerlo en la lista.
        ok, message = self._presenter.add_image(product_id=self._product_id, uri=path,
                                                alt_text=Path(path).name)
        self._apply(ok, message)

    def _on_primary(self) -> None:
        img = self._selected()
        if img is not None:
            self._apply(*self._presenter.set_primary_image(img["id"]), select_id=img["id"])

    def _on_remove(self) -> None:
        img = self._selected()
        if img is not None:
            self._apply(*self._presenter.remove_image(img["id"]))

    def _on_remove_background(self) -> None:
        img = self._selected()
        if img is None:
            return
        self._set_error("")
        self.preview_caption.setText("Quitando el fondo…")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            QApplication.processEvents()
            ok, message = self._presenter.remove_image_background(img["id"])
        finally:
            QApplication.restoreOverrideCursor()
        self._apply(ok, message, select_id=img["id"])
        if not ok:
            self._on_selection_changed()

    def _on_restore_background(self) -> None:
        img = self._selected()
        if img is not None:
            self._apply(*self._presenter.restore_image_background(img["id"]),
                        select_id=img["id"])
