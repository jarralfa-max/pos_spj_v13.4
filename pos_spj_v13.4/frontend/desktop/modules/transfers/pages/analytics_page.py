from frontend.desktop.components.cards import ChartCard
from frontend.desktop.components.chart_view import HtmlChartView

from .workspace_pages import AnalyticsPage as _AnalyticsPage


class AnalyticsPage(_AnalyticsPage):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(presenter, parent)
        card = ChartCard(self)
        self.chart = HtmlChartView(card)
        self.chart.setAccessibleName("Gráfica de desempeño de transferencias")
        card.add(self.chart)
        self.layout().insertWidget(2, card)

    def reload(self, search: str = "") -> None:
        model = self._presenter.load_page(self.page_id, search)
        if model.chart is not None:
            self.chart.set_chart(model.chart)
        rows = [[row.reference, row.origin, row.destination, row.status,
                 row.updated_at] for row in model.rows]
        self.table.load_rows(rows, row_ids=[row.entity_id for row in model.rows])
        self.empty_label.setText(model.empty_message if not rows else "")
        self.empty_label.setVisible(not rows)
        self._loaded = True

__all__ = ["AnalyticsPage"]
