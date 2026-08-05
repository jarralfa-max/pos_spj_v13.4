"""LOSS-20 scoped read model for KPIs, charts, Pareto, trends and export."""
import csv,io
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from backend.application.dto.charts.chart_data import ChartDataDTO,ChartSeriesDTO,ChartType,FreshnessState
from backend.application.losses.execution_context import LossExecutionContext
from backend.application.losses.permissions import LossPermissions
from backend.domain.losses.analytics import LossKpis,ParetoPoint,build_kpis,build_pareto
from backend.domain.losses.exceptions import LossInvariantError
@dataclass(frozen=True,slots=True)
class LossAnalyticsQuery:
    context:LossExecutionContext;branch_id:str;start_at:datetime;end_at:datetime
@dataclass(frozen=True,slots=True)
class LossAnalyticsDashboard:
    kpis:LossKpis;pareto:tuple[ParetoPoint,...];trend:tuple[tuple[str,Decimal],...];charts:tuple[ChartDataDTO,...]
class LossAnalyticsQueryService:
    def __init__(self,repository,authorization):self._repository=repository;self._authorization=authorization
    def dashboard(self,query):
        self._validate(query,LossPermissions.ANALYTICS_VIEW);params=self._params(query);kpis=build_kpis(self._repository.summary(**params));statuses=self._repository.status_distribution(**params);pareto=build_pareto(self._repository.pareto(**params));trend=tuple((str(day),Decimal(str(value))) for day,value in self._repository.trend(**params));return LossAnalyticsDashboard(kpis,pareto,trend,self._charts(statuses,pareto,trend))
    def export_csv(self,query):
        self._validate(query,LossPermissions.EXPORT);buffer=io.StringIO(newline="");fields=("case_id","occurred_on","classification","status","gross_value","recovered_value","net_loss_value","currency_code");writer=csv.writer(buffer,lineterminator="\n");writer.writerow(fields);writer.writerows(self._repository.export_rows(**self._params(query)));return buffer.getvalue()
    def _validate(self,query,permission):
        self._authorization.require(query.context.actor_user_id,permission);query.context.enforce_branch(query.branch_id)
        if query.start_at.tzinfo is None or query.end_at.tzinfo is None:raise LossInvariantError("El rango analítico debe incluir zona horaria")
        if query.start_at>=query.end_at:raise LossInvariantError("El rango analítico es inválido")
    @staticmethod
    def _params(query):return {"branch_id":query.branch_id,"start_at":query.start_at.isoformat(),"end_at":query.end_at.isoformat()}
    @staticmethod
    def _charts(statuses,pareto,trend):
        now=datetime.now().astimezone();status_chart=ChartDataDTO("loss_status",ChartType.BAR,"Expedientes por estado",None,tuple(str(r[0]) for r in statuses),(ChartSeriesDTO("Expedientes",tuple(float(r[1]) for r in statuses)),),unit="expedientes",generated_at=now,freshness_state=FreshnessState.LIVE)
        pareto_chart=ChartDataDTO("loss_pareto",ChartType.COMBO,"Pareto de pérdida neta",None,tuple(p.label for p in pareto),(ChartSeriesDTO("Pérdida neta",tuple(float(p.net_loss_value) for p in pareto),series_type="bar"),ChartSeriesDTO("Acumulado %",tuple(float(p.cumulative_percent) for p in pareto),series_type="line")),generated_at=now,freshness_state=FreshnessState.LIVE)
        trend_chart=ChartDataDTO("loss_trend",ChartType.LINE,"Tendencia de pérdida neta",None,tuple(d for d,_ in trend),(ChartSeriesDTO("Pérdida neta",tuple(float(v) for _,v in trend)),),generated_at=now,freshness_state=FreshnessState.LIVE)
        return (status_chart,pareto_chart,trend_chart)
