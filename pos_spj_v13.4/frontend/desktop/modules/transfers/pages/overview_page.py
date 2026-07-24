from frontend.desktop.components.kpi_bar import KPIBar
from frontend.desktop.components.kpi_card import KPIDTO

from .base_page import TransferWorkspacePage


class OverviewPage(TransferWorkspacePage):
    page_id = "transfers_overview"
    title = "Resumen de transferencias"
    subtitle = "Despacho, tránsito, recepción y diferencias en una sola vista."
    action_text = "Nueva solicitud"

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(presenter, parent)
        self.kpi_bar = KPIBar(self)
        self.layout().insertWidget(1, self.kpi_bar)

    def reload(self, search: str = "") -> None:
        model = self._presenter.load_page(self.page_id, search)
        self.kpi_bar.set_cards([
            KPIDTO(key=item.title, title=item.title, value=item.value,
                   variant=item.variant)
            for item in model.kpis[:6]
        ])
        rows = [[row.reference, row.origin, row.destination, row.status,
                 row.updated_at] for row in model.rows]
        self.table.load_rows(rows, row_ids=[row.entity_id for row in model.rows])
        self.empty_label.setText(model.empty_message if not rows else "")
        self.empty_label.setVisible(not rows)
        self._loaded = True
