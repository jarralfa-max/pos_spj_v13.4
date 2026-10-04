"""TotalsCard — subtotal, descuento, fidelidad, impuestos y TOTAL (§27), más
el mini panel de puntos a ganar (§29).

Todo valor viene ya calculado por el agregado (`SaleDTO`): esta tarjeta no
suma nada. El TOTAL usa el énfasis de monto del sistema de diseño
(`role="amount"`), sin QSS propio.

"Puntos a ganar" (§29) lo estima Fidelidad con sus Ajustes (1 punto por cada
$10 de inicio, 2026-10-02). Hasta entonces no había regla de acumulación y la
fila lo decía en vez de inventar un número — el legacy pintaba `int(total)`.
Si Fidelidad no responde, vuelve a decirlo.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from frontend.desktop.components import apply_tooltip
from frontend.desktop.themes.tokens import Spacing

NO_ACCRUAL_RULE = "No disponible"


def _row(parent, label_text: str) -> tuple[QHBoxLayout, QLabel]:
    row = QHBoxLayout()
    label = QLabel(label_text, parent)
    value = QLabel("$0.00", parent)
    row.addWidget(label)
    row.addStretch(1)
    row.addWidget(value)
    return row, value


def _minus(amount) -> str:
    """Lo que RESTA al total, con signo sólo cuando resta algo."""
    return f"-${amount:,.2f}" if amount else "$0.00"


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

        # Sólo aparece si la venta trae cupón: no le quita altura al cobro.
        self._coupon_row = QWidget(self)
        row_coupon, self._coupon_value = _row(self._coupon_row, "Cupones")
        row_coupon.setContentsMargins(0, 0, 0, 0)
        self._coupon_row.setLayout(row_coupon)
        self._coupon_value.setObjectName("posCouponTotal")
        self._coupon_row.setVisible(False)
        root.addWidget(self._coupon_row)

        row_loyalty, self._loyalty_value = _row(self, "Fidelidad")
        root.addLayout(row_loyalty)

        row_tax, self._tax_value = _row(self, "Impuestos")
        root.addLayout(row_tax)

        divider = QFrame(self)
        divider.setFrameShape(QFrame.HLine)
        root.addWidget(divider)

        row_total = QHBoxLayout()
        points_box = QVBoxLayout()
        points_title = QLabel("Puntos a ganar", self)
        points_title.setProperty("role", "muted")
        points_box.addWidget(points_title)
        self._points_value = QLabel(NO_ACCRUAL_RULE, self)
        self._points_value.setObjectName("posPointsToEarn")
        apply_tooltip(self._points_value,
                      "Lo que darán las reglas de Fidelidad (Programas → Reglas de "
                      "acumulación). Se acreditan al cobrar.")
        points_box.addWidget(self._points_value)
        row_total.addLayout(points_box)
        row_total.addStretch(1)
        total_label = QLabel("TOTAL", self)
        total_label.setObjectName("posTotalsLabel")
        total_label.setProperty("role", "sectionTitle")
        row_total.addWidget(total_label)
        self._total_value = QLabel("$0.00", self)
        self._total_value.setObjectName("posTotalsValue")
        self._total_value.setProperty("role", "amount")
        row_total.addWidget(self._total_value)
        root.addLayout(row_total)

    def set_totals(self, sale) -> None:
        self._subtotal_value.setText(f"${sale.gross_subtotal:,.2f}")
        self._discount_value.setText(_minus(sale.discount_total))
        self._loyalty_value.setText(_minus(sale.loyalty_total))
        self._coupon_value.setText(_minus(getattr(sale, "coupon_total", 0)))
        self._coupon_row.setVisible(bool(getattr(sale, "coupon_total", 0)))
        codigos = ", ".join(c["code"] for c in getattr(sale, "coupons", ()) or ())
        self._coupon_value.setToolTip(codigos)
        self._tax_value.setText(f"${sale.tax_total:,.2f}")
        self._total_value.setText(f"${sale.total:,.2f}")

    def set_points_to_earn(self, text: str | None) -> None:
        self._points_value.setText(text or NO_ACCRUAL_RULE)
