"""Dialogs for the "Campañas de marketing" card on the Documentos
section — SET-13 cutover. Built entirely on `FormDialog`, same convention
as every other dialog in this package.

There's no repeatable-row widget in this component library yet, so rules
are entered as comma-separated `metric<comparator>threshold` triples
(e.g. `points_balance<=50, subtotal>=100`) — same open-ended-list-as-text
convention `print_route_dialogs.py::_FallbackCodesField` already
established for the fallback device chain, applied here to a different
shape. Only the 3 metrics `SalesMarketingClient` actually supplies at
print time are useful: `subtotal`, `total`, `points_balance`.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PyQt5.QtWidgets import QCheckBox

from backend.domain.document_output.enums import RuleComparator
from backend.domain.document_output.value_objects.campaign_rule import CampaignRule
from frontend.desktop.components import FormDialog, SearchableComboBox, StandardLineEdit, apply_tooltip

_CATEGORIES = (("LOYALTY", "Fidelidad"), ("FOMO", "Urgencia (FOMO)"), ("CTA", "Llamado a la acción"))

_COMPARATOR_SYMBOLS = {
    "<": RuleComparator.LESS_THAN, "<=": RuleComparator.LESS_THAN_OR_EQUAL,
    ">": RuleComparator.GREATER_THAN, ">=": RuleComparator.GREATER_THAN_OR_EQUAL,
    "=": RuleComparator.EQUAL,
}
_SYMBOL_BY_COMPARATOR = {v: k for k, v in _COMPARATOR_SYMBOLS.items()}


def rules_to_text(rules) -> str:
    """Inverse of `_RulesField._parsed_rules` — pre-fills the edit
    dialog's rules field from a `MarketingCampaign.rules` tuple."""
    return ", ".join(
        f"{rule.metric}{_SYMBOL_BY_COMPARATOR[rule.comparator]}{rule.threshold}" for rule in rules
    )


_RULES_TOOLTIP = (
    "Opcional. Reglas separadas por coma: métrica, comparador (<, <=, >, >=, =) y umbral. "
    "Ej. «points_balance<=50, subtotal>=100». Métricas disponibles: subtotal, total, "
    "points_balance. Una campaña de categoría Urgencia (FOMO) requiere al menos una regla."
)


class _RulesField:
    def _build_rules_field(self) -> None:
        self.rules = StandardLineEdit(self)
        self.rules.setAccessibleName("Reglas de la campaña")
        apply_tooltip(self.rules, _RULES_TOOLTIP)
        self.form.addRow("Reglas (opcional):", self.rules)

    def _parsed_rules(self) -> tuple[CampaignRule, ...]:
        rules = []
        for entry in [e.strip() for e in self.rules.text().split(",") if e.strip()]:
            symbol = next((s for s in sorted(_COMPARATOR_SYMBOLS, key=len, reverse=True) if s in entry), None)
            if symbol is None:
                continue
            metric, _, threshold_text = entry.partition(symbol)
            try:
                threshold = Decimal(threshold_text.strip())
            except InvalidOperation:
                continue
            if not metric.strip():
                continue
            rules.append(CampaignRule.create(
                metric=metric.strip(), comparator=_COMPARATOR_SYMBOLS[symbol], threshold=threshold))
        return tuple(rules)


class MarketingCampaignCreateDialog(FormDialog, _RulesField):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Nueva campaña de marketing")
        self.code = StandardLineEdit(self)
        self.code.setAccessibleName("Código de la campaña")
        self.form.addRow("Código:", self.code)

        self.category = SearchableComboBox(self, placeholder="Selecciona una categoría…")
        self.category.set_options(_CATEGORIES)
        self.category.setAccessibleName("Categoría")
        self.form.addRow("Categoría:", self.category)

        self.message_template = StandardLineEdit(self)
        self.message_template.setAccessibleName("Plantilla del mensaje")
        apply_tooltip(self.message_template, "Ej. «¡Te faltan {points_balance} puntos para tu recompensa!».")
        self.form.addRow("Mensaje:", self.message_template)

        self.priority = StandardLineEdit(self)
        self.priority.setText("0")
        self.priority.setAccessibleName("Prioridad")
        apply_tooltip(self.priority, "Entero. Mayor prioridad se muestra primero dentro de su categoría.")
        self.form.addRow("Prioridad:", self.priority)

        self.requires_customer = QCheckBox("Requiere cliente asignado a la venta", self)
        self.form.addRow("", self.requires_customer)

        self._build_rules_field()

        self.add_button_box(ok_text="Crear campaña")

    def values(self) -> dict:
        try:
            priority = int(self.priority.text().strip() or "0")
        except ValueError:
            priority = 0
        return {
            "code": self.code.text().strip(), "category": self.category.current_id(),
            "message_template": self.message_template.text().strip(), "priority": priority,
            "requires_customer": self.requires_customer.isChecked(), "rules": self._parsed_rules(),
        }


class MarketingCampaignEditDialog(FormDialog, _RulesField):
    """Edits message/priority/requires_customer/rules — never `code` or
    `category` (a campaign's identity), same boundary
    `DocumentTemplateEditDialog` draws around `document_type`."""

    def __init__(
        self, parent=None, *, message_template: str = "", priority: int = 0,
        requires_customer: bool = False, rules_text: str = "",
    ) -> None:
        super().__init__(parent, title="Editar campaña de marketing")
        self.message_template = StandardLineEdit(self)
        self.message_template.setText(message_template)
        self.message_template.setAccessibleName("Plantilla del mensaje")
        self.form.addRow("Mensaje:", self.message_template)

        self.priority = StandardLineEdit(self)
        self.priority.setText(str(priority))
        self.priority.setAccessibleName("Prioridad")
        self.form.addRow("Prioridad:", self.priority)

        self.requires_customer = QCheckBox("Requiere cliente asignado a la venta", self)
        self.requires_customer.setChecked(requires_customer)
        self.form.addRow("", self.requires_customer)

        self._build_rules_field()
        self.rules.setText(rules_text)

        self.add_button_box(ok_text="Guardar")

    def values(self) -> dict:
        try:
            priority = int(self.priority.text().strip() or "0")
        except ValueError:
            priority = 0
        return {
            "message_template": self.message_template.text().strip(), "priority": priority,
            "requires_customer": self.requires_customer.isChecked(), "rules": self._parsed_rules(),
        }
