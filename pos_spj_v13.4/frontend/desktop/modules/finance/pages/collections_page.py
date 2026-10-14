"""Historial de cobros (auditoría de CxC).

Auditoría d9f2bca F23: antes esta pantalla mostraba la DEUDA abierta, así que un
cobro desaparecía en cuanto su factura quedaba liquidada. Ahora lista cada cobro
registrado — fecha, recibo, factura, cliente, importe, moneda, cuenta que lo
recibió y asiento — y permanece aunque la factura esté saldada.
"""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.finance.pages._page_base import FinancePage


class CollectionsPage(FinancePage):
    title = "Cobros"
    subtitle = "Historial de cobros aplicados a cuentas por cobrar"
    searchable = True
    columns = [
        ColumnSpec("Fecha", "date"),
        ColumnSpec("Recibo", "date"),
        ColumnSpec("Factura", "date"),
        ColumnSpec("Cliente"),
        ColumnSpec("Importe", "numeric"),
        ColumnSpec("Moneda", "status"),
        ColumnSpec("Cuenta"),
        ColumnSpec("Asiento", "date"),
        ColumnSpec("Estado de la CxC", "status"),
    ]

    def _load(self) -> None:
        self.set_table(self._presenter.collection_history(search=self._search.query()))
