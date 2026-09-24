"""Configuración del módulo de Precios y Costos.

POR QUÉ ESTA PANTALLA NO TIENE CAMPOS EDITABLES
------------------------------------------------
`pricing_settings` estaba declarada en la navegación desde PRC-7 y `build_page`
no la resolvía, así que la sección abría con "Esta sección aún no está
construida": una ruta que existe, se ve ordenada y no hace nada.

Precios no tiene tabla de configuración, y no se inventó una. Sus parámetros no
son interruptores guardados aparte — son consecuencia de los datos: qué lista
rige, en qué moneda se cobra, con qué método se costea, cuántos productos tienen
precio mínimo. Inventar una tabla de ajustes habría producido controles que no
gobiernan nada, que es peor que no tener la pantalla: el usuario cambiaría un
valor y el módulo seguiría comportándose igual.

Lo que sí hacía falta era poder VER esos parámetros, porque hasta ahora no se
podían consultar desde ninguna pantalla, y dos de ellos —ninguna lista base
activa, varias monedas conviviendo— son configuraciones rotas que no se
manifiestan como error sino como cifras que no cuadran.

Sólo presentación: todo pasa por el presentador.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components import ColumnSpec, PageHeader, StandardTable
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

        # El segundo posicional de `ColumnSpec` es `kind` y sólo acepta
        # 'text'|'numeric'|'date'|'status'; aquí las tres columnas son texto.
        self.table = StandardTable(columns=[
            ColumnSpec("Parámetro", key="parameter", preferred_width=240),
            ColumnSpec("Valor", key="value", preferred_width=240),
            ColumnSpec("Nota", key="note", preferred_width=420, stretch=True),
        ])
        layout.addWidget(self.table, 1)
        self.refresh()

    def refresh(self) -> None:
        vm = self._presenter.settings()
        self.table.load_rows(vm.rows, row_ids=vm.row_ids)
