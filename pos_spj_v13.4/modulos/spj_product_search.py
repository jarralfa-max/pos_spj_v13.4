# modulos/spj_product_search.py — SPJ POS v13.2
"""
Widget universal de búsqueda de productos.
Busca por nombre, código interno o código de barras.
Acepta entrada de scanner HID (buffer de teclado).

USO:
    from modulos.spj_product_search import ProductSearchWidget

    self.buscador = ProductSearchWidget(db=container.db)
    self.buscador.producto_seleccionado.connect(self._on_producto)
    layout.addWidget(self.buscador)

    # En _on_producto(producto: dict):
    #   producto = {'id', 'nombre', 'codigo', 'codigo_barras',
    #               'precio', 'precio_compra', 'existencia', 'unidad'}
"""
from __future__ import annotations
import logging
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QLineEdit, QPushButton,
    QListWidget, QListWidgetItem,
    QFrame, QVBoxLayout, QLabel, QApplication
)
from PyQt5.QtCore import (
    Qt, QTimer, pyqtSignal, QStringListModel, QSize
)
from PyQt5.QtGui import QFont

logger = logging.getLogger("spj.product_search")


class ProductSearchWidget(QWidget):
    """
    Barra de búsqueda de productos con:
    - Autocompletado por nombre y código
    - Soporte de scanner HID (detecta entrada rápida de teclado)
    - Popup de resultados con precio y stock
    - Teclas: Enter para seleccionar, Esc para cerrar popup
    - Estilos heredados del tema global (sin hardcode)
    """
    producto_seleccionado = pyqtSignal(dict)   # emite el producto elegido

    def __init__(self, db=None, placeholder: str = "Buscar producto (nombre, código, barcode)…",
                 show_stock: bool = True, parent=None):
        super().__init__(parent)
        self.db = db
        self.show_stock = show_stock
        self._scanner_timer  = QTimer(self)
        self._scanner_timer.setSingleShot(True)
        self._scanner_timer.setInterval(80)   # 80ms = scanner timeout
        self._scanner_timer.timeout.connect(self._flush_scanner)
        self._last_key_ms: float = 0.0   # timestamp of last keystroke (ms)
        self._inter_key_ms: float = 9999.0  # ms between last two keystrokes
        self._last_results: list = []
        self._build_ui(placeholder)

    def set_db(self, db) -> None:
        self.db = db

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self, placeholder: str) -> None:
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText(placeholder)
        self.txt_search.setObjectName("inputField")  # usa el QSS global del tema
        self.txt_search.textChanged.connect(self._on_text_changed)
        self.txt_search.returnPressed.connect(self._on_enter)
        self.txt_search.installEventFilter(self)   # for scanner detection

        btn_search = QPushButton("🔍")
        btn_search.setFixedWidth(36)
        btn_search.setObjectName("secondaryBtn")
        btn_search.setCursor(Qt.PointingHandCursor)
        btn_search.clicked.connect(lambda: self._buscar(self.txt_search.text()))

        lay.addWidget(self.txt_search, 1)
        lay.addWidget(btn_search)

        # Popup de resultados (flotante) — hereda estilos del tema global
        self._popup = QFrame(self.window(), Qt.Popup | Qt.FramelessWindowHint)
        self._popup.setObjectName("productSearchPopup")
        self._popup.setAttribute(Qt.WA_StyledBackground, True)
        self._popup_lay = QVBoxLayout(self._popup)
        self._popup_lay.setContentsMargins(4, 4, 4, 4)
        self._popup_lay.setSpacing(2)
        self._popup_list = QListWidget()
        self._popup_list.setObjectName("productSearchPopupList")
        self._popup_list.itemClicked.connect(self._on_item_click)
        self._popup_list.setMaximumHeight(280)
        self._popup_lay.addWidget(self._popup_list)
        self._popup.hide()

        # Debounce timer for live search
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(250)
        self._search_timer.timeout.connect(lambda: self._buscar(self.txt_search.text()))

    # ── Events ───────────────────────────────────────────────────────────────

    def eventFilter(self, obj, event) -> bool:
        """Detect HID scanner (rapid sequential keystrokes)."""
        from PyQt5.QtCore import QEvent
        import time
        if obj is self.txt_search and event.type() == QEvent.KeyPress:
            key = event.key()
            if key == Qt.Key_Escape:
                self._popup.hide()
                return False
            # Scanner sends Enter at the end — flush immediately
            if key in (Qt.Key_Return, Qt.Key_Enter):
                text = self.txt_search.text().strip()
                if text:
                    self._flush_scanner_with(text)
                return True
            # Track inter-key timing to distinguish scanner (< 50ms) from human typing
            now_ms = time.monotonic() * 1000
            self._inter_key_ms = now_ms - self._last_key_ms
            self._last_key_ms = now_ms
            # Restart scanner timer on each keystroke
            self._scanner_timer.stop()
            self._scanner_timer.start()
        return super().eventFilter(obj, event)

    def _on_text_changed(self, text: str) -> None:
        if not text.strip():
            self._popup.hide()
            return
        self._search_timer.start()

    def _on_enter(self) -> None:
        text = self.txt_search.text().strip()
        if text:
            self._buscar(text)

    # ── Scanner ───────────────────────────────────────────────────────────────

    def _flush_scanner(self) -> None:
        """Called after scanner timeout. Only does exact barcode lookup if typing speed
        was scanner-like (< 50ms between keys). For normal human typing it falls through
        to the regular search, preventing single-char field clears."""
        text = self.txt_search.text().strip()
        if not text:
            return
        if self._inter_key_ms < 50:
            # Scanner input — try exact barcode match first
            self._buscar_exacto(text)
        else:
            # Human typing — just show normal search results
            self._buscar(text)

    def _flush_scanner_with(self, text: str) -> None:
        """Immediate barcode search (Enter received)."""
        self._buscar_exacto(text)

    def _buscar_exacto(self, codigo: str) -> None:
        """Search by exact barcode or internal code first."""
        if not self.db: return
        try:
            row = self.db.execute(
                """SELECT id, nombre, COALESCE(codigo,'') as codigo,
                          COALESCE(codigo_barras,'') as codigo_barras,
                          precio, COALESCE(precio_compra,0) as precio_compra,
                          COALESCE(existencia,0) as existencia,
                          COALESCE(unidad,'pz') as unidad
                   FROM productos
                   WHERE (COALESCE(codigo_barras,'')=? OR codigo=? OR CAST(id AS TEXT)=?)
                     AND COALESCE(oculto,0)=0 AND COALESCE(activo,1)=1
                   LIMIT 1""",
                (codigo, codigo, codigo)
            ).fetchone()
            if row:
                self._emit_product(dict(row))
                self.txt_search.clear()
                self._popup.hide()
                return
        except Exception as e:
            logger.debug("_buscar_exacto: %s", e)
        # Fallback to normal search
        self._buscar(codigo)

    # ── Search ────────────────────────────────────────────────────────────────

    def _buscar(self, text: str) -> None:
        if not text.strip() or not self.db:
            return
        try:
            rows = self.db.execute(
                """SELECT id, nombre,
                          COALESCE(codigo,'') as codigo,
                          COALESCE(codigo_barras,'') as codigo_barras,
                          precio,
                          COALESCE(precio_compra,0) as precio_compra,
                          COALESCE(existencia,0) as existencia,
                          COALESCE(unidad,'pz') as unidad
                   FROM productos
                   WHERE (
                       nombre          LIKE ?            -- nombre
                    OR COALESCE(codigo,'')      LIKE ?   -- código interno
                    OR COALESCE(codigo_barras,'') LIKE ? -- código de barras
                    OR CAST(id AS TEXT)          = ?     -- ID exacto
                   )
                   AND COALESCE(oculto,0)=0
                   AND COALESCE(activo,1)=1
                   ORDER BY
                     CASE WHEN COALESCE(codigo_barras,'')=? THEN 0
                          WHEN COALESCE(codigo,'')=?        THEN 1
                          WHEN CAST(id AS TEXT)=?           THEN 2
                          ELSE 3 END,
                     nombre
                   LIMIT 20""",
                (f"%{text}%", f"%{text}%", f"%{text}%", text,
                 text, text, text)
            ).fetchall()
        except Exception as e:
            logger.debug("_buscar: %s", e)
            return

        self._last_results = [dict(r) for r in rows]
        self._show_popup()

    def _show_popup(self) -> None:
        self._popup_list.clear()
        if not self._last_results:
            self._popup.hide()
            return

        for prod in self._last_results:
            stock_str = f"  📦{prod['existencia']:.1f}{prod['unidad']}" if self.show_stock else ""
            label = f"{prod['nombre']}  —  ${prod['precio']:.2f}{stock_str}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, prod)
            self._popup_list.addItem(item)

        # Position popup below the search bar
        pos = self.txt_search.mapToGlobal(
            self.txt_search.rect().bottomLeft())
        self._popup.move(pos)
        self._popup.resize(max(self.txt_search.width() + 40, 400),
                           min(len(self._last_results) * 36 + 16, 280))
        self._popup.show()
        self._popup_list.setCurrentRow(0)

    def _on_item_click(self, item: QListWidgetItem) -> None:
        prod = item.data(Qt.UserRole)
        if prod:
            self._emit_product(prod)
            self.txt_search.clear()
            self._popup.hide()

    def _emit_product(self, prod: dict) -> None:
        self.producto_seleccionado.emit(prod)

    # ── Public API ────────────────────────────────────────────────────────────

    def clear(self) -> None:
        self.txt_search.clear()
        self._popup.hide()

    def setFocus(self) -> None:
        self.txt_search.setFocus()

    def set_placeholder(self, text: str) -> None:
        self.txt_search.setPlaceholderText(text)
