"""LOSS-20 desktop presentation adapter."""
from datetime import datetime,timedelta,timezone
from frontend.desktop.components.kpi_card import KPIDTO
from backend.application.losses.analytics import LossAnalyticsQuery
class LossAnalyticsPresenter:
    def __init__(self,service,context_provider):self._service=service;self._context_provider=context_provider
    def _query(self):
        context=self._context_provider();end=datetime.now(timezone.utc);return LossAnalyticsQuery(context,context.active_branch_id,end-timedelta(days=30),end)
    def dashboard(self):return self._service.dashboard(self._query())
    def kpi_cards(self,dashboard):
        k=dashboard.kpis;return (KPIDTO("cases","Expedientes",str(k.case_count)),KPIDTO("gross","Valor bruto",f"${k.gross_value:,.2f}"),KPIDTO("recovery","Recuperación",f"${k.recovered_value:,.2f}"),KPIDTO("net","Pérdida neta",f"${k.net_loss_value:,.2f}",variant="danger"),KPIDTO("rate","Recuperación",f"{k.recovery_rate:.2f}%"),KPIDTO("actions","Acciones vencidas",str(k.overdue_actions),variant="warning"))
    def export_csv(self):return self._service.export_csv(self._query())
