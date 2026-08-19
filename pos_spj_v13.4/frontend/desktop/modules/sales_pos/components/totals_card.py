"""TotalsCard (POS-19) — structural equivalent of the legacy `totals_card`
(subtotal/descuento/IVA/total rows, `docs/refactor/sales_pos_layout_inventory.md`
§1), backed by `SaleDTO.totals`-derived fields (SALES-3/8/13/14/16) instead
of the legacy widget's own float math.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from frontend.desktop.themes.tokens import Spacing


def _row(parent, label_text: str) -> tuple[QHBoxLayout, QLabel]:
    row = QHBoxLayout()
    label = QLabel(label_text, parent)
    value = QLabel("$0.00", parent)
    row.addWidget(label)
    row.addStretch(1)
    row.addWidget(value)
    return row, value


class TotalsCard(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("posTotalsCard")

        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        root.setSpacing(Spacing.XS)

        row_sub, self._subtotal_value = _row(self, "Subtotal")
        root.addLayout(row_sub)

        row_disc, self._discount_value = _row(self, "Descuento")
        root.addLayout(row_disc)

        row_loyalty, self._loyalty_value = _row(self, "Fidelidad")
        root.addLayout(row_loyalty)

        row_tax, self._tax_value = _row(self, "Impuestos")
        root.addLayout(row_tax)

        divider = QFrame(self)
        divider.setFrameShape(QFrame.HLine)
        root.addWidget(divider)

        row_total = QHBoxLayout()
        total_label = QLabel("TOTAL", self)
        total_label.setObjectName("posTotalsLabel")
        self._total_value = QLabel("$0.00", self)
        self._total_value.setObjectName("posTotalsValue")
        row_total.addWidget(total_label)
        row_total.addStretch(1)
        row_total.addWidget(self._total_value)
        root.addLayout(row_total)

    def set_totals(self, sale) -> None:
        self._subtotal_value.setText(f"${sale.gross_subtotal:.2f}")
        self._discount_value.setText(f"${sale.discount_total:.2f}")
        self._loyalty_value.setText(f"${sale.loyalty_total:.2f}")
        self._tax_value.setText(f"${sale.tax_total:.2f}")
        self._total_value.setText(f"${sale.total:.2f}")
