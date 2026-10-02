"""Configuración del módulo de Precios y Costos.

POR QUÉ CASI TODO ES DE SÓLO LECTURA
------------------------------------
`pricing_settings` estaba declarada en la navegación desde PRC-7 y `build_page`
no la resolvía, así que la sección abría con "Esta sección aún no está
construida": una ruta que existe, se ve ordenada y no hace nada.

Precios no tiene tabla de configuración, y no se inventó una. Sus parámetros no
son interruptores guardados aparte — son consecuencia de los datos: qué lista
rige, en qué moneda se cobra, con qué método se costea, cuántos productos tienen
precio mínimo. Esos se MUESTRAN, porque dos de ellos —ninguna lista base activa,
varias monedas conviviendo— son configuraciones rotas que no se manifiestan como
error sino como cifras que no cuadran.

La excepción es la POLÍTICA DE COSTO (§32): ésa sí gobierna algo —qué costo se
reporta, el de empresa o el de cada sucursal— y se guarda en `configuraciones`
(no en una tabla nueva). Es el único control editable de la pantalla.

Sólo presentación: todo pasa por el presentador.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from frontend.desktop.components import (
    ColumnSpec,
    PageHeader,
    SearchableComboBox,
    SectionCard,
    StandardTable,
    create_primary_button,
)
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


class PricingSettingsPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("pricingSettingsPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Configuración",
            subtitle="Parámetros con los que opera hoy el módulo de precios y costos.",
            icon=getattr(Icons, "SETTINGS", None), compact=True)
        layout.addWidget(self.header)

        layout.addWidget(self._build_cost_policy())

        # El segundo posicional de `ColumnSpec` es `kind` y sólo acepta
        # 'text'|'numeric'|'date'|'status'; aquí las tres columnas son texto.
        self.table = StandardTable(columns=[
            ColumnSpec("Parámetro", key="parameter", preferred_width=240),
            ColumnSpec("Valor", key="value", preferred_width=240),
            ColumnSpec("Nota", key="note", preferred_width=420, stretch=True),
        ])
        layout.addWidget(self.table, 1)
        self.refresh()

    def _build_cost_policy(self) -> QWidget:
        card = SectionCard(title="Política de costo")
        explanation = QLabel(
            "Global: un solo costo promedio para toda la empresa. Por sucursal: cada "
            "sucursal usa el promedio de lo que ella compró y tiene en existencia (si aún "
            "no tiene historia, se usa el de empresa). Los dos se calculan siempre, así "
            "que el cambio aplica de inmediato. Nunca se cambia el precio de venta.", self)
        explanation.setWordWrap(True)
        explanation.setProperty("role", "muted")
        card.add(explanation)
        row = QHBoxLayout()
        self.cost_policy = SearchableComboBox(placeholder="Política de costo")
        self.cost_policy.set_options(self._presenter.cost_policy_options())
        self.save_cost_policy = create_primary_button(self, "Guardar política")
        self.save_cost_policy.clicked.connect(self._save_cost_policy)
        editable = bool(getattr(self._presenter, "can_manage_cost_policy", False))
        self.cost_policy.setEnabled(editable)
        self.save_cost_policy.setVisible(editable)
        row.addWidget(self.cost_policy, 1)
        row.addWidget(self.save_cost_policy)
        wrapper = QWidget(self)
        wrapper.setLayout(row)
        card.add(wrapper)
        self.cost_policy_notice = QLabel("", self)
        self.cost_policy_notice.setProperty("role", "banner")
        self.cost_policy_notice.setWordWrap(True)
        self.cost_policy_notice.hide()
        card.add(self.cost_policy_notice)
        return card

    def _save_cost_policy(self, *_) -> None:
        ok, message, _data = self._presenter.set_cost_policy(self.cost_policy.current_id() or "")
        self.cost_policy_notice.setProperty("state", "success" if ok else "error")
        self.cost_policy_notice.style().unpolish(self.cost_policy_notice)
        self.cost_policy_notice.style().polish(self.cost_policy_notice)
        self.cost_policy_notice.setText(message)
        self.cost_policy_notice.show()
        self.refresh()

    def refresh(self) -> None:
        self.cost_policy.set_current_id(self._presenter.current_cost_policy())
        vm = self._presenter.settings()
        self.table.load_rows(vm.rows, row_ids=vm.row_ids)
