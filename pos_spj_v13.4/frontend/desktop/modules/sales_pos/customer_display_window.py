"""CustomerDisplayWindow / QtCustomerDisplayGateway — SET-17 "Gateway": a
real, fully-testable `CustomerDisplayGatewayPort` implementation. Unlike
SET-14's label printers, `CustomerDisplayGatewayPort`'s own docstring
names a real second-screen window as sufficient validation — no
hardware/byte-protocol boundary blocks this.

`render_content()` only updates widgets for keys present in `content` —
mirrors `display_state_push_policy.push_state()`'s own "layout governs
what's sent" filtering: this window never fabricates content for a
section the layout disabled/omitted.
"""

from __future__ import annotations

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QFont, QGuiApplication, QPixmap
from PyQt5.QtWidgets import (
    QLabel,
    QSizePolicy,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from backend.domain.customer_display.enums import CustomerDisplayMode, CustomerDisplaySectionCode
from backend.domain.customer_display.gateway_ports import CustomerDisplayGatewayPort
from frontend.desktop.themes.tokens import Spacing, Typography

def _font(pixel_size: int) -> QFont:
    """Sizing via `QFont`, not `setStyleSheet(...)` — the theme QSS is the
    only place allowed to style widgets under `sales_pos`
    (`tests/unit/test_sales_pos_visual_validation.py::
    TestThemeValidation::test_no_component_sets_an_inline_stylesheet`)."""
    font = QFont()
    font.setPixelSize(pixel_size)
    return font


_SECTION_LABELS = {
    CustomerDisplaySectionCode.SUBTOTAL.value: "Subtotal",
    CustomerDisplaySectionCode.DISCOUNT.value: "Descuento",
    CustomerDisplaySectionCode.TOTAL.value: "Total",
}


class CustomerDisplayWindow(QWidget):
    """A customer-facing second screen. Opens maximized on a second
    monitor when one is connected, else a normal window — never blocks
    the feature on missing hardware.

    **Real bug found and fixed while smoke-testing SET-18's ad
    rotation**: `SalesPosWorkspace` constructs this with itself as
    `parent` (for Qt-managed lifetime — destroyed with the workspace,
    never leaked) — but a plain `QWidget(parent)` is an ordinary EMBEDDED
    child by default, not a real top-level window (`isWindow()` is
    `False`), so it would never actually appear as an independent OS
    window, and any child's `isVisible()` would report `False` whenever
    its parent isn't itself visible. Passing the `Qt.Window` flag keeps
    the parent-for-lifetime relationship while making this a genuine
    top-level window, exactly like `QDialog` already does implicitly for
    every other secondary window in this codebase."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, Qt.Window)
        self.setObjectName("customerDisplayWindow")
        self.setWindowTitle("Pantalla del cliente")

        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.XXL, Spacing.XXL, Spacing.XXL, Spacing.XXL)
        root.setSpacing(Spacing.LG)

        top = QVBoxLayout()
        self._customer_name_label = QLabel("", self)
        self._customer_name_label.setObjectName("customerDisplayCustomerName")
        self._customer_name_label.setFont(_font(Typography.SIZE_TITLE_LG))
        top.addWidget(self._customer_name_label)
        root.addLayout(top)

        self._items_area = QScrollArea(self)
        self._items_area.setWidgetResizable(True)
        self._items_container = QWidget(self._items_area)
        self._items_layout = QVBoxLayout(self._items_container)
        self._items_layout.setSpacing(Spacing.XS)
        self._items_area.setWidget(self._items_container)
        root.addWidget(self._items_area, stretch=1)

        self._totals_labels: dict[str, QLabel] = {}
        for code, caption in _SECTION_LABELS.items():
            label = QLabel("", self)
            label.setObjectName(f"customerDisplay_{code}")
            label.setFont(_font(Typography.SIZE_SUBTITLE))
            self._totals_labels[code] = label
            root.addWidget(label)

        self._message_label = QLabel("", self)
        self._message_label.setObjectName("customerDisplayMessage")
        self._message_label.setAlignment(Qt.AlignCenter)
        self._message_label.setFont(_font(Typography.SIZE_DISPLAY))
        self._message_label.setWordWrap(True)
        root.addWidget(self._message_label)

        self._ad_label = QLabel("", self)
        self._ad_label.setObjectName("customerDisplayAd")
        self._ad_label.setAlignment(Qt.AlignCenter)
        self._ad_label.setFont(_font(Typography.SIZE_TITLE_LG))
        self._ad_label.setWordWrap(True)
        # La imagen se adapta al espacio; nunca al revés. Sin esto, un QLabel con
        # imagen pide el tamaño de la imagen, la ventana crece, y como la imagen
        # se reescala al redimensionar, crecería sin fin.
        self._ad_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self._ad_label.setVisible(False)
        root.addWidget(self._ad_label, stretch=1)
        self._video_widget = None
        self._video_player = None
        self._ad_pixmap = None

        close_button = QPushButton("Cerrar", self)
        close_button.clicked.connect(self.close)
        root.addWidget(close_button, alignment=Qt.AlignRight)

        self._open_on_best_screen()

    def _open_on_best_screen(self) -> None:
        screens = QGuiApplication.screens()
        if len(screens) > 1:
            self.setGeometry(screens[1].geometry())
            self.showMaximized()
        else:
            self.resize(800, 600)
            self.show()

    def render_content(self, mode: str, content: dict) -> None:
        self._ad_label.setVisible(False)
        self._ad_pixmap = None
        self._stop_video()
        self._set_sale_widgets_visible(True)
        self._clear_items()
        if CustomerDisplaySectionCode.CUSTOMER_NAME.value in content:
            self._customer_name_label.setText(str(content[CustomerDisplaySectionCode.CUSTOMER_NAME.value] or ""))
        else:
            self._customer_name_label.setText("")

        if CustomerDisplaySectionCode.ITEMS.value in content:
            for item in content[CustomerDisplaySectionCode.ITEMS.value]:
                line = QLabel(
                    f"{item.get('quantity', '')} x {item.get('name', '')} — {item.get('line_total', '')}",
                    self._items_container,
                )
                self._items_layout.addWidget(line)

        for code, label in self._totals_labels.items():
            if code in content:
                label.setText(f"{_SECTION_LABELS[code]}: {content[code]}")
                label.setVisible(True)
            else:
                label.setText("")
                label.setVisible(False)

        self._message_label.setText(str(content.get(CustomerDisplaySectionCode.MESSAGE.value, "") or ""))

    def render_idle_ad(self, content_type: str, title: str, body: str,
                       media_path: str | None = None) -> None:
        """Una pieza de publicidad mientras la caja está en reposo.

        TEXT muestra el texto; IMAGE la imagen escalada a la pantalla; VIDEO lo
        reproduce en silencio y en bucle. Un archivo que ya no está o un video
        sin reproductor disponible se dicen en pantalla, no se inventan.
        HTML sigue sin renderizarse (no hay motor para HTML aquí).
        """
        self._stop_video()
        self._ad_label.clear()
        self._ad_pixmap = None
        # En reposo no hay venta: la publicidad ocupa la pantalla completa.
        self._set_sale_widgets_visible(False)
        if content_type == "TEXT":
            self._ad_label.setText(body)
        elif content_type == "IMAGE" and media_path:
            pixmap = QPixmap(media_path)
            if pixmap.isNull():
                self._ad_label.setText(f"{title} (no se pudo abrir la imagen)")
            else:
                self._ad_pixmap = pixmap
                self._fit_ad_pixmap()
        elif content_type == "VIDEO" and media_path and self._play_video(media_path):
            self._ad_label.setVisible(False)
            return
        elif content_type in ("IMAGE", "VIDEO"):
            self._ad_label.setText(f"{title} (el archivo ya no está disponible)")
        else:
            self._ad_label.setText(f"{title} ({content_type})")
        self._ad_label.setVisible(True)

    def _set_sale_widgets_visible(self, visible: bool) -> None:
        for widget in (self._customer_name_label, self._items_area, self._message_label):
            widget.setVisible(visible)

    def _fit_ad_pixmap(self) -> None:
        """Escala la imagen al área disponible de la ventana (no al tamaño
        momentáneo de la etiqueta, que oculta mide 0×0) y conserva proporción."""
        if self._ad_pixmap is None:
            return
        destino = self._ad_label.contentsRect().size()
        if destino.width() < 16 or destino.height() < 16:  # aún sin acomodar
            margen = Spacing.XXL * 2
            destino = QSize(max(self.width() - margen, 1), max(int(self.height() * 0.6), 1))
        self._ad_label.setPixmap(self._ad_pixmap.scaled(
            destino, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self._ad_label.setVisible(True)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_ad_pixmap()

    def _play_video(self, media_path: str) -> bool:
        try:
            from PyQt5.QtCore import QUrl
            from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer, QMediaPlaylist
            from PyQt5.QtMultimediaWidgets import QVideoWidget
        except ImportError:
            return False
        if self._video_widget is None:
            self._video_widget = QVideoWidget(self)
            self._video_player = QMediaPlayer(self, QMediaPlayer.VideoSurface)
            self._video_player.setVideoOutput(self._video_widget)
            self._video_player.setMuted(True)
            self.layout().insertWidget(self.layout().indexOf(self._ad_label), self._video_widget, 1)
        playlist = QMediaPlaylist(self._video_player)
        playlist.addMedia(QMediaContent(QUrl.fromLocalFile(media_path)))
        playlist.setPlaybackMode(QMediaPlaylist.Loop)
        self._video_player.setPlaylist(playlist)
        self._video_widget.setVisible(True)
        self._video_player.play()
        return True

    def _stop_video(self) -> None:
        if self._video_player is not None:
            self._video_player.stop()
        if self._video_widget is not None:
            self._video_widget.setVisible(False)

    def _clear_items(self) -> None:
        while self._items_layout.count():
            item = self._items_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()


class QtCustomerDisplayGateway(CustomerDisplayGatewayPort):
    def __init__(self, window: CustomerDisplayWindow) -> None:
        self._window = window

    def push(self, *, display_id: str, mode: CustomerDisplayMode, content: dict) -> None:
        self._window.render_content(mode.value, content)
