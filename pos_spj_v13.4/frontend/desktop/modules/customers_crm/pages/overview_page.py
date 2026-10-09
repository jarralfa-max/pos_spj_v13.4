"""CustomersCrmOverviewPage (CRM-15, §90) — the Clientes y CRM dashboard:
KPIs, pipeline chart, alerts, recent overdue activity.

UI only: every number/DTO comes from ``presenter.dashboard()`` (backed by
``CustomerDashboardQueryService``, CRM-15's own pure-composition backend
service) — "La UI no calcula KPIs" (§90). This page never sums, filters by
date, or decides what counts as overdue/breached; it only renders what the
presenter hands it.

Mirrors ``frontend/desktop/modules/purchasing/pages/procurement_dashboard_page.py``'s
``ensure_loaded()``/``reload()`` lifecycle and its ``AlertsBar`` pattern
(``frontend/desktop/modules/purchasing/purchasing_module_shell.py``) — the
closest existing "KPIs + chart + alerts" precedent in the repo.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from backend.application.dto.charts.chart_data import ChartDataDTO, ChartType, series_from
from frontend.desktop.components import (
    AlertCard,
    ChartCard,
    ColumnSpec,
    DashboardGrid,
    HtmlChartView,
    KPIBar,
    KPIDTO,
    StandardTable,
)
from frontend.desktop.themes.tokens import Spacing


class _AlertsBar(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("customersCrmAlertsBar")
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(Spacing.SM)

    def set_alerts(self, alerts: list[tuple[str, str, str]]) -> None:
        """``alerts`` is a list of (variant, message, help_text) tuples the
        page already decided — this widget only renders them."""
        while self._row.count():
            item = self._row.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        for variant, message, _help_text in alerts:
            card = AlertCard(self, variant=variant)
            label = QLabel(message, card)
            label.setWordWrap(True)
            card.add(label)
            self._row.addWidget(card, stretch=1)
        self.setVisible(bool(alerts))


class CustomersCrmOverviewPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("customersCrmOverviewPage")
        self._presenter = presenter
        self._loaded = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.MD)

        self._status = QLabel("", self)
        self._status.setObjectName("customersCrmOverviewStatus")
        self._status.setProperty("state", "LOADING")
        self._status.setWordWrap(True)
        self._status.hide()
        layout.addWidget(self._status)

        self._alerts_bar = _AlertsBar(self)
        layout.addWidget(self._alerts_bar)

        self._grid = DashboardGrid(self)
        self._kpi_bar = KPIBar(cards=[])
        self._grid.add_kpi_bar(self._kpi_bar)

        # CRM-43 (§81): KPIs secundarios bajo los seis principales.
        self._secondary_bar = KPIBar(cards=[])
        self._grid.add_kpi_bar(self._secondary_bar)
        self._pipeline_card = ChartCard(self)
        self._pipeline_chart = HtmlChartView(self._pipeline_card)
        self._pipeline_card.add(self._pipeline_chart)
        self._grid.add_full_width(self._pipeline_card)
        # CRM-43 (§82): el resto de las gráficas, de dos en dos.
        self._charts: dict[str, HtmlChartView] = {}
        for left, right in (("leads_by_source", "outcomes"), ("by_owner", "cases_by_type"),
                            ("sla", "segments")):
            cards = []
            for key in (left, right):
                card = ChartCard(self)
                chart = HtmlChartView(card)
                card.add(chart)
                self._charts[key] = chart
                cards.append((card, 1))
            self._grid.add_row(*cards)

        self._activity_table = StandardTable(
            [ColumnSpec("Actividad"), ColumnSpec("Tipo"), ColumnSpec("Vence", "date")], self)
        self._grid.add_full_width(self._activity_table)
        self._grid.add_stretch()
        layout.addWidget(self._grid, stretch=1)

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()

    def reload(self) -> None:
        self._status.setText("Cargando indicadores…")
        self._status.setProperty("state", "LOADING")
        self._status.show()
        try:
            view = self._presenter.dashboard()
            self._kpi_bar.set_cards(self._build_kpis(view))
            self._alerts_bar.set_alerts(self._build_alerts(view))
            self._pipeline_chart.set_chart(self._build_pipeline_chart(view))
            self._load_insights()
            self._activity_table.load_rows(self._build_activity_rows(view))
            self._loaded = True
            self._status.hide()
        except Exception as exc:  # a page must always show *something*
            self._status.setProperty("state", "ERROR")
            self._status.setText(f"No fue posible cargar el resumen: {exc}")

    @staticmethod
    def _build_kpis(view) -> list[KPIDTO]:
        return [
            KPIDTO(key="leads_new", title="Leads nuevos", value=str(view.leads_new_count),
                  variant="primary"),
            KPIDTO(key="leads_pending", title="Leads por atender",
                  value=str(view.leads_pending_count), variant="primary"),
            KPIDTO(key="opps_open", title="Oportunidades abiertas",
                  value=str(view.opportunities_open_count), variant="primary"),
            KPIDTO(key="pipeline_weighted", title="Pipeline ponderado",
                  value=f"${view.weighted_pipeline:,.2f}", variant="success"),
            KPIDTO(key="activities_overdue", title="Actividades vencidas",
                  value=str(view.overdue_activities_count),
                  variant="danger" if view.overdue_activities_count else "success"),
            KPIDTO(key="cases_out_of_sla", title="Casos fuera de SLA",
                  value=str(view.cases_out_of_sla_count),
                  variant="danger" if view.cases_out_of_sla_count else "success"),
        ]

    @staticmethod
    def _build_alerts(view) -> list[tuple[str, str, str]]:
        alerts: list[tuple[str, str, str]] = []
        if view.overdue_activities_count:
            alerts.append((
                "danger",
                f"{view.overdue_activities_count} actividad(es)/tarea(s) vencida(s)",
                "activities_overdue"))
        if view.cases_out_of_sla_count:
            alerts.append((
                "danger",
                f"{view.cases_out_of_sla_count} caso(s) fuera de SLA",
                "cases_out_of_sla"))
        return alerts

    @staticmethod
    def _build_pipeline_chart(view) -> ChartDataDTO:
        if not view.pipeline_by_stage:
            return ChartDataDTO.empty(
                "crm_pipeline", ChartType.BAR, "Pipeline por etapa",
                message="Sin oportunidades abiertas")
        return ChartDataDTO(
            chart_id="crm_pipeline", chart_type=ChartType.BAR, title="Pipeline por etapa",
            subtitle=None,
            categories=tuple(slice_.stage_name for slice_ in view.pipeline_by_stage),
            series=(series_from(
                "Monto", [float(slice_.amount) for slice_ in view.pipeline_by_stage]),),
            currency_code="MXN")

    # -- CRM-43: indicadores secundarios y gráficas (§81-82) --------------------
    def _load_insights(self) -> None:
        reader = getattr(self._presenter, "has_reader", None)
        if not (callable(reader) and reader("insights")):
            return
        try:
            insights = self._presenter.read("insights")
        except Exception:  # noqa: BLE001 — sin permisos: se quedan los principales
            return
        self._secondary_bar.set_cards([
            KPIDTO(key="active_customers", title="Clientes activos",
                   value=str(insights.active_customers)),
            KPIDTO(key="conversion", title="Conversión de prospectos",
                   value=f"{insights.lead_conversion_pct}%"),
            KPIDTO(key="won", title="Oportunidades ganadas", value=str(insights.opportunities_won),
                   variant="success"),
            KPIDTO(key="won_value", title="Valor ganado", value=f"${insights.won_value:,.2f}",
                   variant="success"),
            KPIDTO(key="open_cases", title="Casos abiertos", value=str(insights.open_cases)),
            KPIDTO(key="no_follow", title="Clientes sin seguimiento",
                   value=str(insights.customers_without_follow_up),
                   variant="warning" if insights.customers_without_follow_up else "neutral"),
        ])
        from frontend.desktop.modules.customers_crm.labels import label
        user = getattr(self._presenter, "user_name", lambda u: u or "Sin asignar")
        self._chart("leads_by_source", ChartType.DONUT, "Prospectos por fuente",
                    [(label("lead_source", k), v) for k, v in insights.leads_by_source])
        self._chart("outcomes", ChartType.BAR, "Oportunidades por resultado",
                    [(label("opportunity_status", k), v)
                     for k, v in insights.opportunities_by_outcome])
        self._chart("by_owner", ChartType.HORIZONTAL_BAR, "Pipeline por responsable",
                    [(user(k), float(v)) for k, v in insights.pipeline_by_owner], money=True)
        self._chart("cases_by_type", ChartType.BAR, "Casos por tipo",
                    [(label("case_type", k), v) for k, v in insights.cases_by_type])
        self._chart("sla", ChartType.DONUT, "Cumplimiento de SLA",
                    [(label("sla_status", k), v) for k, v in insights.sla_compliance])
        self._chart("segments", ChartType.BAR, "Clientes por segmento",
                    list(insights.customers_by_segment))

    def _chart(self, key: str, chart_type: str, title: str, pairs, *, money: bool = False):
        if not pairs:
            dto = ChartDataDTO.empty(f"crm_{key}", chart_type, title)
        else:
            dto = ChartDataDTO(
                chart_id=f"crm_{key}", chart_type=chart_type, title=title, subtitle=None,
                categories=tuple(str(k) for k, _v in pairs),
                series=(series_from(title, [float(v) for _k, v in pairs]),),
                currency_code="MXN" if money else None)
        self._charts[key].set_chart(dto)

    @staticmethod
    def _build_activity_rows(view) -> list[list[str]]:
        rows = [
            [activity.subject, "Actividad", (activity.scheduled_at or "")[:10]]
            for activity in view.recent_overdue_activities
        ]
        rows += [
            [task.title, "Tarea", (task.due_at or "")[:10]]
            for task in view.recent_overdue_tasks
        ]
        return rows
