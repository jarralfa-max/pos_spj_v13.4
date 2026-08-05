"""LOSS-20 KPI and chart page; metrics and export come from its presenter."""
from pathlib import Path
from PyQt5.QtWidgets import QFileDialog,QHBoxLayout,QMessageBox,QVBoxLayout,QWidget
from frontend.desktop.components import HtmlChartView,KPIBar,PageHeader,create_secondary_button
class LossAnalyticsPage(QWidget):
    def __init__(self,presenter,parent=None):
        super().__init__(parent);self._presenter=presenter;self._loaded=False
        root=QVBoxLayout(self);root.addWidget(PageHeader(title="BI de mermas y pérdidas",subtitle="KPI, Pareto y tendencias de los últimos 30 días.",parent=self))
        actions=QHBoxLayout();actions.addStretch(1);refresh=create_secondary_button(text="Actualizar");export=create_secondary_button(text="Exportar CSV");refresh.clicked.connect(self.refresh);export.clicked.connect(self._export);actions.addWidget(refresh);actions.addWidget(export);root.addLayout(actions)
        self.kpis=KPIBar(cards=[]);root.addWidget(self.kpis);self.charts=[HtmlChartView(self) for _ in range(3)]
        for chart in self.charts:root.addWidget(chart,stretch=1)
    def ensure_loaded(self):
        if not self._loaded:self.refresh();self._loaded=True
    def refresh(self):
        try:dashboard=self._presenter.dashboard()
        except Exception as exc:QMessageBox.warning(self,"BI de mermas",str(exc));return
        self.kpis.set_cards(self._presenter.kpi_cards(dashboard))
        for view,dto in zip(self.charts,dashboard.charts):view.set_chart(dto)
    def _export(self):
        target,_=QFileDialog.getSaveFileName(self,"Exportar análisis de mermas","losses_analytics.csv","CSV (*.csv)")
        if not target:return
        try:Path(target).write_text(self._presenter.export_csv(),encoding="utf-8-sig")
        except Exception as exc:QMessageBox.warning(self,"Exportación",str(exc));return
        QMessageBox.information(self,"Exportación","El archivo CSV se generó correctamente.")
