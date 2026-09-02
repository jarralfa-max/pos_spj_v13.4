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

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QGuiApplication
from PyQt5.QtWidgets import (
    QLabel,
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
        self._ad_label.setVisible(False)
        root.addWidget(self._ad_label, stretch=1)

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

    def render_idle_ad(self, content_type: str, title: str, body: str) -> None:
        """Renders one resolved advertising placement while the register
        is idle. `TEXT` content renders `body` for real; `IMAGE`/`VIDEO`/
        `HTML` render an honest placeholder — no real image/video/HTML
        rendering infrastructure exists anywhere in this repo (confirmed
        repeatedly across this track), so pretending to paint one would
        be fabricated, not real."""
        if content_type == "TEXT":
            self._ad_label.setText(body)
        else:
            self._ad_label.setText(f"{title} ({content_type})")
        self._ad_label.setVisible(True)

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
