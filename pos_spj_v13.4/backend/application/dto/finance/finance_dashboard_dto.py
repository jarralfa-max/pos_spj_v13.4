"""DTOs del tablero financiero (§29). Los valores llegan calculados por el
QueryService; la pantalla sólo los muestra."""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.application.dto.charts.chart_data import ChartDataDTO


@dataclass(frozen=True)
class FinanceKpiDTO:
    key: str
    label: str
    value: str            # importe decimal en texto o conteo
    variant: str = "primary"   # primary | success | warning | danger
    is_money: bool = True
    hint: str = ""


@dataclass(frozen=True)
class FinanceAlertDTO:
    key: str
    label: str
    count: int
    severity: str          # info | warning | danger
    route: str             # sección del módulo que la atiende


@dataclass(frozen=True)
class FinanceDashboardDTO:
    period_from: str
    period_to: str
    currency_code: str
    kpis: tuple[FinanceKpiDTO, ...]
    alerts: tuple[FinanceAlertDTO, ...]
    charts: tuple[ChartDataDTO, ...] = field(default_factory=tuple)
