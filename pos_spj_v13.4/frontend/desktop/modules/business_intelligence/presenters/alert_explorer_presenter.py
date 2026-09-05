"""AlertExplorerPresenter (§14/§46-50, BI-28) — feeds the "Alertas" page:
runs 2 canonical `AnalyticalAlertRule`s (BI-20) against the REAL KPI values
`BiDashboardService.build_dashboard()` already computes (the "merma"/
"margen" KPIs) — the exact same checks `BiDashboardService._alerts()`
already makes ad hoc in plain Python, now expressed through the canonical
`AnalyticalAlertEngine` (BI-20) instead, with real fingerprint-based dedup/
cooldown and the full 6-state lifecycle (§50) the ad-hoc `Alert` dataclass
never had.

Only WASTE_SPIKE/MARGIN_DROP are wired — the other 14 canonical AlertTypes
(§47) need metric sources this page doesn't have wired yet (forecast
deviation, purchase/production risk, branch underperformance, etc.);
building them without a real metric behind them would be a fabricated
placeholder — documented in `docs/refactor/BI-28_alerts_ui.md`, not
silently skipped.

Rules run fresh on every `evaluate_all()` call (scope = ALL_BRANCHES)
rather than reading persisted alerts — there is still no persistence for
`AnalyticalAlert` anywhere in the repo (same documented gap as
`BusinessRecommendation`, BI-22/27); lifecycle transitions apply to the
in-memory alert only.

Reuses the existing `threshold_merma_pct`/`threshold_margen_bajo_pct`
settings (§3/§64 — one canonical threshold, not a second one invented for
this page) already used by `BiDashboardService._alerts()`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from backend.application.analytical_alerting.services.alert_engine import AnalyticalAlertEngine
from backend.application.analytics.dto.bi_dashboard_dto import DashboardFilters
from backend.application.analytics.queries.bi_dashboard_query_service import (
    BiDashboardQueryService,
)
from backend.application.analytics.services.bi_dashboard_service import BiDashboardService
from backend.application.analytics.services.bi_settings_service import BiSettingsService
from backend.domain.analytical_alerting.enums import AlertSeverity, AlertType, Comparison
from backend.domain.analytical_alerting.exceptions import InvalidAlertTransitionError
from backend.domain.analytical_alerting.services import alert_lifecycle
from backend.domain.analytical_alerting.value_objects.alert_rule import AnalyticalAlertRule
from backend.shared.ids import new_uuid
from frontend.desktop.components.kpi_card import KPIDTO

#: Fixed cooldown convention (24h) — same "fixed convention over guesswork"
#: spirit as the pricing-decision elasticity thresholds (BI-16); no
#: per-rule cooldown setting exists yet to source this from.
_COOLDOWN_MINUTES = 1440
_ALL_BRANCHES = "ALL_BRANCHES"

_SEVERITY_VARIANT = {
    "CRITICAL": "danger", "HIGH": "danger", "MEDIUM": "warning",
    "LOW": "info", "INFO": "neutral",
}


class AlertTransitionError(Exception):
    """Raised when the requested lifecycle action isn't valid from the
    alert's current status, the action name is unknown, or it requires an
    authenticated actor that isn't available."""


def map_alert_kpis(alert) -> list[KPIDTO]:
    return [
        KPIDTO(key="type", title="Tipo", value=alert.alert_type.value, variant="primary"),
        KPIDTO(key="severity", title="Severidad", value=alert.severity.value,
               variant=_SEVERITY_VARIANT.get(alert.severity.value, "neutral")),
        KPIDTO(key="status", title="Estado", value=alert.status.value,
               variant="success" if alert.status.value == "RESOLVED" else "neutral"),
    ]


class AlertExplorerPresenter:
    def __init__(self, connection, *, settings: BiSettingsService | None = None,
                 actor_user_id: str | None = None) -> None:
        self._settings = settings or BiSettingsService()
        query_service = BiDashboardQueryService(connection)
        self._dashboard = BiDashboardService(query_service, settings=self._settings)
        self._engine = AnalyticalAlertEngine()
        self._actor_user_id = actor_user_id

    def _rules(self) -> dict[str, AnalyticalAlertRule]:
        return {
            "merma": AnalyticalAlertRule(
                id=new_uuid(), alert_type=AlertType.WASTE_SPIKE, metric_key="merma",
                comparison=Comparison.GREATER_THAN,
                threshold=Decimal(str(self._settings.get("threshold_merma_pct"))),
                severity=AlertSeverity.HIGH, cooldown_minutes=_COOLDOWN_MINUTES,
            ),
            "margen": AnalyticalAlertRule(
                id=new_uuid(), alert_type=AlertType.MARGIN_DROP, metric_key="margen",
                comparison=Comparison.LESS_THAN,
                threshold=Decimal(str(self._settings.get("threshold_margen_bajo_pct"))),
                severity=AlertSeverity.MEDIUM, cooldown_minutes=_COOLDOWN_MINUTES,
            ),
        }

    def evaluate_all(self) -> list:
        payload = self._dashboard.build_dashboard(DashboardFilters())
        metrics = {k["key"]: k["value"] for k in payload.kpis}
        now = datetime.now(timezone.utc)
        alerts = []
        for rule in self._rules().values():
            metric_value = metrics.get(rule.metric_key)
            if metric_value is None:
                continue
            alert = self._engine.evaluate(
                rule=rule, metric_value=Decimal(str(metric_value)),
                branch_id=_ALL_BRANCHES, target_id=rule.metric_key,
                evidence={"metric_key": rule.metric_key, "metric_value": str(metric_value),
                          "threshold": str(rule.threshold)},
                title=f"{rule.alert_type.value} — {rule.metric_key}",
                message=f"{rule.metric_key}={metric_value} cruza el umbral {rule.threshold}",
                now=now,
            )
            if alert is not None:
                alerts.append(alert)
        return alerts

    def apply_transition(self, alert, action: str, *, reason: str = ""):
        try:
            if action == "acknowledge":
                self._ensure_actor()
                return alert_lifecycle.acknowledge(alert, self._actor_user_id,
                                                    datetime.now(timezone.utc))
            if action == "start_progress":
                return alert_lifecycle.start_progress(alert)
            if action == "resolve":
                self._ensure_actor()
                return alert_lifecycle.resolve(alert, self._actor_user_id,
                                                datetime.now(timezone.utc), reason)
            if action == "dismiss":
                self._ensure_actor()
                return alert_lifecycle.dismiss(alert, self._actor_user_id,
                                                datetime.now(timezone.utc), reason)
            raise AlertTransitionError(f"Acción desconocida: {action}")
        except InvalidAlertTransitionError as exc:
            raise AlertTransitionError(str(exc)) from exc
        except ValueError as exc:  # e.g. resolve/dismiss without a reason
            raise AlertTransitionError(str(exc)) from exc

    def _ensure_actor(self) -> None:
        if not self._actor_user_id:
            raise AlertTransitionError("Se requiere un usuario autenticado para esta acción.")
