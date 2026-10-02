"""CustomerPanel — el cliente de la venta (§21), entre el carrito y los totales.

Venta de mostrador por omisión ("Público en general"); buscar y asignar con el
buscador estándar (`CustomerSearchBox`), crear cliente rápido, quitar el
cliente, y mostrar nivel y puntos que reporta Fidelidad (§23). "Canjear"
aparece cuando el cliente tiene puntos y la venta aún no tiene canje (§38).

Re-auditoría POS (2026-10-01): al asignar un cliente el panel seguía diciendo
"Público en general" — nada le pasaba el cliente asignado — y la lista de
resultados vacía ocupaba casi la mitad del panel. Ahora el panel pinta el
`CustomerSummary` que el presentador arma (Clientes + Fidelidad) y la lista se
oculta mientras no haya resultados.
"""

from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from frontend.desktop.components import (
    CustomerSearchBox,
    IconProvider,
    Icons,
    StatusBadge,
    create_ghost_button,
    create_secondary_button,
)
from frontend.desktop.themes.tokens import Spacing

WALK_IN_LABEL = "Público en general"


class CustomerPanel(QFrame):
    customer_selected = pyqtSignal(str)  # customer_id
    clear_requested = pyqtSignal()
    redeem_requested = pyqtSignal()

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("posClientFrame")
        self._presenter = presenter

        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        root.setSpacing(Spacing.XS)

        title = QLabel("CLIENTE", self)
        title.setObjectName("posClientSectionLabel")
        title.setProperty("role", "sectionTitle")
        root.addWidget(title)

        info_row = QHBoxLayout()
        self._display = QLabel(WALK_IN_LABEL, self)
        self._display.setObjectName("posClientName")
        info_row.addWidget(self._display, stretch=1)
        self._tier = StatusBadge("", self, status="neutral")
        self._tier.setVisible(False)
        info_row.addWidget(self._tier)
        self._btn_clear = create_ghost_button(self, "Quitar", tooltip="Volver a venta de mostrador")
        self._btn_clear.setVisible(False)
        self._btn_clear.clicked.connect(self.clear_requested)
        info_row.addWidget(self._btn_clear)
        self._btn_redeem = create_secondary_button(
            self, "Canjear", tooltip="Pagar parte del ticket con puntos del cliente")
        self._btn_redeem.setObjectName("posRedeemPointsButton")
        self._btn_redeem.setVisible(False)
        self._btn_redeem.clicked.connect(self.redeem_requested)
        info_row.addWidget(self._btn_redeem)
        self._btn_quick_create = create_secondary_button(
            self, "Nuevo", tooltip="Registrar un cliente con nombre y teléfono")
        IconProvider.bind(self._btn_quick_create, Icons.ADD)
        info_row.addWidget(self._btn_quick_create)
        root.addLayout(info_row)

        self._details = QLabel("", self)
        self._details.setObjectName("posClientDetails")
        self._details.setProperty("role", "muted")
        self._details.setVisible(False)
        root.addWidget(self._details)

        self._search = CustomerSearchBox(self, provider=self._search_provider,
                                         collapse_when_empty=True)
        self._search.selected.connect(self._on_selected)
        root.addWidget(self._search)

    def set_customer(self, summary, *, can_redeem: bool = True) -> None:
        """`summary`: `CustomerSummary` del presentador, o None (mostrador).
        `can_redeem`: False si la venta ya tiene un canje aplicado."""
        if summary is None:
            self._display.setText(WALK_IN_LABEL)
            self._details.setVisible(False)
            self._tier.setVisible(False)
            self._btn_clear.setVisible(False)
            self._btn_redeem.setVisible(False)
            return
        self._btn_redeem.setVisible(bool(can_redeem and summary.points))
        self._display.setText(summary.name)
        detalles = []
        if summary.phone:
            detalles.append(summary.phone)
        if summary.points is not None:
            detalles.append(f"{summary.points} puntos")
        self._details.setText("  ·  ".join(detalles))
        self._details.setVisible(bool(detalles))
        self._tier.setText(summary.tier or "")
        self._tier.setVisible(bool(summary.tier))
        self._btn_clear.setVisible(True)
        self._search.clear()

    def redeem_button(self):
        return self._btn_redeem

    def quick_create_button(self):
        return self._btn_quick_create

    def _search_provider(self, query: str):
        from frontend.desktop.components.search_selector import SearchOption

        if not query:
            return []
        return [
            SearchOption(id=result.customer_id, label=result.display_name,
                         subtitle=result.phone_e164 or "")
            for result in self._presenter.search_customers(query)
        ]

    def _on_selected(self, option) -> None:
        self.customer_selected.emit(option.id)
