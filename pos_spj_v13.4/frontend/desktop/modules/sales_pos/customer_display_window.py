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
from decimal import Decimal, InvalidOperation

from PyQt5.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QGuiApplication, QPixmap
from PyQt5.QtWidgets import (
    QLabel,
    QFrame,
    QHBoxLayout,
    QSizePolicy,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from backend.domain.customer_display.enums import CustomerDisplayMode, CustomerDisplaySectionCode
from backend.domain.customer_display.gateway_ports import CustomerDisplayGatewayPort
from frontend.desktop.themes.tokens import Spacing, Typography
from frontend.desktop.components import IconProvider, Icons

def _font(pixel_size: int) -> QFont:
    """Sizing via `QFont`, not `setStyleSheet(...)` — the theme QSS is the
    only place allowed to style widgets under `sales_pos`
    (`tests/unit/test_sales_pos_visual_validation.py::
    TestThemeValidation::test_no_component_sets_an_inline_stylesheet`)."""
    font = QFont()
    font.setPixelSize(pixel_size)
    return font


def _money(value) -> str:
    try:
        amount = Decimal(str(value))
        return f"${amount:,.2f}" if amount.is_finite() else "—"
    except (ValueError, InvalidOperation):
        return "—"


_SECTION_LABELS = {
    CustomerDisplaySectionCode.SUBTOTAL.value: "Subtotal",
    CustomerDisplaySectionCode.DISCOUNT.value: "Descuento",
    CustomerDisplaySectionCode.TOTAL.value: "Total",
    CustomerDisplaySectionCode.TAX.value: "Impuestos",
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

    closed = pyqtSignal()

    def __init__(self, parent=None, *, preferences=None) -> None:
        super().__init__(parent, Qt.Window)
        self.setObjectName("customerDisplayWindow")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setWindowTitle("Pantalla del cliente")
        self._preferences = preferences or {}
        self._mode = "IDLE"

        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.XXL, Spacing.XXL, Spacing.XXL, Spacing.XXL)
        root.setSpacing(Spacing.LG)

        self._header = QWidget(self)
        top = QHBoxLayout(self._header)
        top.setContentsMargins(0, 0, 0, 0)
        self._header_brand = QLabel("", self._header)
        self._header_brand.setTextFormat(Qt.PlainText)
        self._header_brand.setProperty("role", "displayBody")
        top.addWidget(self._header_brand, 1)
        self._status_label = QLabel("", self._header)
        self._status_label.setObjectName("customerDisplayStatus")
        top.addWidget(self._status_label)
        root.addWidget(self._header)

        self._body_region = QWidget(self)
        self._regions = QHBoxLayout(self._body_region)
        self._regions.setContentsMargins(0, 0, 0, 0)
        self._regions.setSpacing(Spacing.XXL)
        self._cart_region = QWidget(self._body_region)
        self._cart_layout = QVBoxLayout(self._cart_region)
        self._cart_layout.setContentsMargins(0, 0, 0, 0)
        self._cart_layout.setSpacing(Spacing.SM)
        self._cart_title = QLabel("Tu compra", self._cart_region)
        self._cart_title.setProperty("role", "displayTitle")
        self._cart_layout.addWidget(self._cart_title)
        self._customer_name_label = QLabel("", self)
        self._customer_name_label.setTextFormat(Qt.PlainText)
        self._customer_name_label.setObjectName("customerDisplayCustomerName")
        self._customer_name_label.setFont(_font(Typography.SIZE_TITLE_LG))
        self._cart_layout.addWidget(self._customer_name_label)

        self._items_area = QScrollArea(self)
        self._items_area.setWidgetResizable(True)
        self._items_container = QWidget(self._items_area)
        self._items_layout = QVBoxLayout(self._items_container)
        self._items_layout.setSpacing(Spacing.XS)
        self._items_layout.setContentsMargins(0, 0, 0, 0)
        self._items_layout.setAlignment(Qt.AlignTop)
        self._items_area.setWidget(self._items_container)
        self._cart_layout.addWidget(self._items_area, 1)
        self._regions.addWidget(self._cart_region, stretch=3)
        root.addWidget(self._body_region, stretch=1)

        self._completion = QWidget(self)
        self._completion_layout = QVBoxLayout(self._completion)
        self._completion_layout.setSpacing(Spacing.LG)
        self._completion_layout.addStretch(1)
        self._confirmation_icon = QLabel("", self._completion)
        self._confirmation_icon.setPixmap(IconProvider.pixmap(
            Icons.SUCCESS, size=Typography.SIZE_DISPLAY, state="warning", theme="dark",
            device_pixel_ratio=self.devicePixelRatioF()))
        self._confirmation_icon.setAccessibleName("Pago confirmado")
        self._confirmation_icon.setObjectName("customerDisplayConfirmation")
        self._confirmation_icon.setAlignment(Qt.AlignCenter)
        self._completion_layout.addWidget(self._confirmation_icon)
        root.addWidget(self._completion, 1)

        self._totals_labels: dict[str, QLabel] = {}
        for code, caption in _SECTION_LABELS.items():
            label = QLabel("", self)
            label.setObjectName(f"customerDisplay_{code}")
            label.setProperty("role", "displayTitle" if code == "TOTAL" else "displayBody")
            label.setFont(_font(Typography.SIZE_SUBTITLE))
            self._totals_labels[code] = label
            self._cart_layout.addWidget(label)

        self._message_label = QLabel("", self)
        self._message_label.setTextFormat(Qt.PlainText)
        self._message_label.setObjectName("customerDisplayMessage")
        self._message_label.setProperty("role", "displayTitle")
        self._message_label.setAlignment(Qt.AlignCenter)
        self._message_label.setFont(_font(Typography.SIZE_DISPLAY))
        self._message_label.setWordWrap(True)
        self._completion_layout.addWidget(self._message_label)
        self._scale_label = QLabel("", self)
        self._scale_label.setObjectName("customerDisplayScale")
        self._points_label = QLabel("", self)
        self._points_label.setObjectName("customerDisplayPoints")
        self._payment_label = QLabel("", self)
        self._payment_label.setObjectName("customerDisplayPayment")
        self._payment_label.setProperty("role", "displayBody")
        self._payment_label.setFont(_font(Typography.SIZE_TITLE_LG))
        self._payment_label.setWordWrap(True)
        self._brand_label = QLabel("", self)
        self._brand_label.setAlignment(Qt.AlignCenter)
        self._brand_label.setFont(_font(Typography.SIZE_TITLE_LG))
        self._logo_label = QLabel("", self)
        self._logo_label.setAlignment(Qt.AlignCenter)
        for label in (self._scale_label, self._points_label, self._payment_label,
                      self._brand_label, self._logo_label):
            label.setProperty("role", "displayBody")
            label.setTextFormat(Qt.PlainText)
            label.hide()
        self._metrics_region = QWidget(self._cart_region)
        self._metrics_layout = QHBoxLayout(self._metrics_region)
        self._metrics_layout.setContentsMargins(0, 0, 0, 0)
        self._metrics_layout.setSpacing(Spacing.SM)
        for label in (self._scale_label, self._points_label):
            label.setWordWrap(True)
            label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            self._metrics_layout.addWidget(label, 1)
        self._cart_layout.addWidget(self._metrics_region)
        self._completion_layout.addWidget(self._logo_label)
        self._completion_layout.addWidget(self._brand_label)
        divider = QFrame(self._completion)
        divider.setFrameShape(QFrame.HLine)
        divider.setObjectName("customerDisplayDivider")
        self._completion_layout.addWidget(divider)
        self._completion_layout.addWidget(self._payment_label)
        self._farewell_label = QLabel("", self._completion)
        self._farewell_label.setTextFormat(Qt.PlainText)
        self._farewell_label.setProperty("role", "displayBody")
        self._farewell_label.setAlignment(Qt.AlignCenter)
        self._farewell_label.setWordWrap(True)
        self._completion_layout.addWidget(self._farewell_label)
        self._completion_layout.addStretch(1)
        self._completion.hide()

        self._ad_label = QLabel("", self)
        self._ad_label.setTextFormat(Qt.PlainText)
        self._ad_label.setObjectName("customerDisplayAd")
        self._ad_label.setAlignment(Qt.AlignCenter)
        self._ad_label.setFont(_font(Typography.SIZE_TITLE_LG))
        self._ad_label.setWordWrap(True)
        # La imagen se adapta al espacio; nunca al revés. Sin esto, un QLabel con
        # imagen pide el tamaño de la imagen, la ventana crece, y como la imagen
        # se reescala al redimensionar, crecería sin fin.
        self._ad_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self._ad_label.setVisible(False)
        self._media_region = QWidget(self)
        self._media_region.setObjectName("customerDisplayMedia")
        self._media_layout = QVBoxLayout(self._media_region)
        self._media_layout.setContentsMargins(0, 0, 0, 0)
        self._media_layout.addWidget(self._ad_label, stretch=1)
        self._regions.addWidget(self._media_region, stretch=2)
        self._media_region.hide()
        self._video_widget = None
        self._video_player = None
        self._ad_pixmap = None

        close_button = QPushButton("Cerrar", self._header)
        close_button.clicked.connect(self.close)
        top.addWidget(close_button)

        self._open_on_best_screen()
        QGuiApplication.instance().screenAdded.connect(self._screen_changed)
        QGuiApplication.instance().screenRemoved.connect(self._screen_changed)

    def _screen_changed(self, *_):
        if self.isVisible():
            self._open_on_best_screen()

    def _open_on_best_screen(self) -> None:
        screens = QGuiApplication.screens()
        name = self._preferences.get("screen_name")
        selected = next((s for s in screens if name and s.name() == name), None)
        if selected is not None:
            self.setGeometry(selected.geometry())
            self.showFullScreen() if self._preferences.get("fullscreen") else self.showMaximized()
            return
        if len(screens) > 1:
            self.setGeometry(screens[1].geometry())
            self.showFullScreen() if self._preferences.get("fullscreen") else self.showMaximized()
        else:
            self.resize(800, 600)
            self.show()

    def render_content(self, mode: str, content: dict) -> None:
        keep_media = mode == self._mode and mode in ("CART", "IDLE")
        self._mode = mode
        if self.property("displayMode") != mode:
            self.setProperty("displayMode", mode)
            for widget in (self, *self.findChildren(QWidget)):
                widget.style().unpolish(widget)
                widget.style().polish(widget)
            self.update()
        self._header.setVisible(mode in ("CART", "IDLE"))
        self._status_label.setText("Venta en curso" if mode == "CART" else "Bienvenido")
        self._cart_region.setVisible(mode == "CART")
        self._completion.setVisible(mode != "CART")
        self._confirmation_icon.setVisible(mode == "THANK_YOU")
        ordered = ((self._points_label, self._totals_labels["TOTAL"]) if mode == "CART"
                   else (self._totals_labels["TOTAL"], self._points_label))
        for widget in ordered:
            if mode == "CART":
                target = self._metrics_layout if widget is self._points_label else self._cart_layout
                target.removeWidget(widget)
                target.addWidget(widget, 1 if widget is self._points_label else 0)
                widget.setAlignment(Qt.AlignLeft)
            else:
                self._completion_layout.removeWidget(widget)
                self._completion_layout.insertWidget(self._completion_layout.indexOf(self._farewell_label), widget)
                widget.setAlignment(Qt.AlignCenter)
        self._body_region.setVisible((mode == "CART" and "ITEMS" in content)
                                     or (keep_media and not self._media_region.isHidden()))
        if not keep_media:
            self._media_region.hide()
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
                row = QWidget(self._items_container)
                row.setObjectName("customerDisplayLine")
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, Spacing.SM, 0, Spacing.SM)
                line = QLabel(
                    f"{item.get('name', '')} · {item.get('quantity', '')} {item.get('unit', '')}"
                    + (f" · {_money(item['unit_price'])} / {item.get('unit', '')}" if 'unit_price' in item else "")
                    + (f" · Descuento {_money(item['discount_total'])}" if item.get('discount_total') not in (None, '0', '0.00') else ""), row,
                )
                line.setTextFormat(Qt.PlainText)
                line.setProperty("role", "displayBody")
                line.setWordWrap(True)
                line.setFont(_font(Typography.SIZE_SUBTITLE))
                row_layout.addWidget(line, 1)
                amount = QLabel(_money(item.get('line_total', '')), row)
                amount.setProperty("role", "displayBody")
                amount.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                row_layout.addWidget(amount)
                self._items_layout.addWidget(row)

        for code, label in self._totals_labels.items():
            if code in content:
                label.setText(f"{_SECTION_LABELS[code]}: {_money(content[code])}")
                label.setVisible(True)
            else:
                label.setText("")
                label.setVisible(False)

        message = str(content.get(CustomerDisplaySectionCode.MESSAGE.value, "") or "")
        heading, _, farewell = message.partition("\n") if mode == "THANK_YOU" else (message, "", "")
        self._message_label.setText(heading)
        self._farewell_label.setText(farewell)
        self._farewell_label.setVisible(bool(farewell))
        for key, label in (("SCALE", self._scale_label), ("POINTS", self._points_label),
                           ("PAYMENT", self._payment_label)):
            label.setText(str(content.get(key) or ""))
            label.setVisible(bool(label.text()))
        brand = content.get("BRANDING") or {}
        self._brand_label.setText("\n".join(filter(None, (brand.get("name"), brand.get("tagline")))))
        self._header_brand.setText(self._brand_label.text())
        self._brand_label.setVisible(bool(brand) and mode in ("THANK_YOU", "IDLE"))
        logo = QPixmap(brand.get("logo_path") or "")
        self._logo_label.setVisible(not logo.isNull() and mode in ("THANK_YOU", "IDLE"))
        if not logo.isNull():
            self._logo_label.setPixmap(logo.scaled(240, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self._items_area.setVisible(mode == "CART" and "ITEMS" in content)
        self._customer_name_label.setVisible(mode == "CART" and bool(self._customer_name_label.text()))
        if mode == "PAYMENT_PENDING" and "TOTAL" in content:
            self._totals_labels["TOTAL"].setText(f"TOTAL A PAGAR: {_money(content['TOTAL'])}")
        if mode == "THANK_YOU" and "TOTAL" in content:
            self._totals_labels["TOTAL"].setText(f"Pago confirmado · {_money(content['TOTAL'])}")
        self._scale_label.setVisible(mode == "CART" and bool(content.get("SCALE")))
        if mode == "IDLE":
            for label in self._totals_labels.values():
                label.hide()

    def render_scale(self, text):
        self._scale_label.setText(text)

    def render_idle_ad(self, content_type: str, title: str, body: str,
                       media_path: str | None = None, *, during_sale=False) -> None:
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
        self._media_region.show()
        self._body_region.show()
        if not during_sale:
            self._cart_region.hide()
            self._completion.hide()
            self._set_sale_widgets_visible(False)
            for label in self._totals_labels.values():
                label.hide()
            for label in (self._points_label, self._payment_label, self._brand_label, self._logo_label):
                label.hide()
        if content_type == "TEXT":
            self._ad_label.setText(body)
        elif content_type == "IMAGE" and media_path:
            pixmap = QPixmap(media_path)
            if pixmap.isNull():
                self._ad_label.setText(f"{title} (no se pudo abrir la imagen)")
            else:
                self._ad_pixmap = pixmap
                self._fit_ad_pixmap()
                QTimer.singleShot(0, self._fit_ad_pixmap)
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
            self._video_player.error.connect(self._video_failed)
            self._media_layout.addWidget(self._video_widget, 1)
        previous = self._video_player.playlist()
        self._video_player.setPlaylist(None)
        if previous is not None:
            previous.deleteLater()
        playlist = QMediaPlaylist(self._video_player)
        playlist.addMedia(QMediaContent(QUrl.fromLocalFile(media_path)))
        playlist.setPlaybackMode(QMediaPlaylist.Loop)
        self._video_player.setPlaylist(playlist)
        self._video_widget.setVisible(True)
        self._video_player.play()
        return True

    def _video_failed(self, *_):
        self._stop_video()
        self._ad_label.setText("Contenido no disponible")
        self._ad_label.show()

    def closeEvent(self, event):
        self._stop_video()
        self.closed.emit()
        super().closeEvent(event)

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
        self._scale_enabled = False

    def push(self, *, display_id: str, mode: CustomerDisplayMode, content: dict) -> None:
        self._scale_enabled = "SCALE" in content
        self._window.render_content(mode.value, content)

    def update_scale(self, text):
        if self._scale_enabled:
            self._window.render_scale(text)
