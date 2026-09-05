"""ReportsPresenter (§14/§30, BI-30) — feeds the "Reportes" page: exports
the executive dashboard summary via the REAL, pre-existing
`BiExportService` — the exact same service + payload shape
`modulos/reportes_bi_v2.py`'s own "Reportes" tab already calls
(`bi_dashboard_service.build_dashboard(filters).to_dict()` ->
`export_summary(payload, meta, filepath, fmt)`), just wired through the new
module's own Design System instead of the legacy one.

"Biblioteca de reportes" (§30) is, for now, a catalog of exactly ONE real
report definition — "Resumen ejecutivo" — since that is the only payload
shape `BiExportService.export_summary()` actually knows how to render. More
report definitions are future work once other exportable payloads exist,
not fabricated here.

"Reportes programados" (§30) is deliberately NOT built — no job-scheduling
infrastructure (a cron-like abstraction, a persisted schedule, a recurring-
run history) exists anywhere in this repository for BI or otherwise.
Building one from scratch to support a single report type would be exactly
the "infrastructure without a real consumer" this transformation has
avoided in every prior phase — documented in
`docs/refactor/BI-30_reports.md`, not silently skipped.
"""

from __future__ import annotations

from datetime import datetime

from backend.application.analytics.dto.bi_dashboard_dto import DashboardFilters
from backend.application.analytics.queries.bi_dashboard_query_service import (
    BiDashboardQueryService,
)
from backend.application.analytics.services.bi_dashboard_service import BiDashboardService
from backend.application.analytics.services.bi_export_service import BiExportService

#: The only report `BiExportService` can actually render today (§30 — one
#: real catalog entry, not several fabricated ones).
REPORT_CATALOG: tuple[dict, ...] = (
    {"key": "executive_summary", "title": "Resumen ejecutivo",
     "description": "KPIs, gráficas y predicciones del dashboard ejecutivo."},
)

_FORMAT_EXTENSIONS = {"xlsx", "pdf", "csv"}


class ReportUnavailableError(Exception):
    """Raised when a report cannot be generated (unknown report key/format,
    or the export itself failed) — the page shows this message, never a
    stack trace."""


class ReportsPresenter:
    def __init__(self, connection, *, actor_user_id: str | None = None) -> None:
        query_service = BiDashboardQueryService(connection)
        self._dashboard = BiDashboardService(query_service)
        self._export = BiExportService()
        self._actor_user_id = actor_user_id

    def list_reports(self) -> tuple[dict, ...]:
        return REPORT_CATALOG

    def default_filename(self, report_key: str, fmt: str) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        return f"{report_key}_{ts}.{fmt}"

    def generate(self, *, report_key: str, fmt: str, filepath: str,
                 branch_label: str = "Todas") -> str:
        if report_key != "executive_summary":
            raise ReportUnavailableError(f"Reporte desconocido: {report_key}")
        if fmt not in _FORMAT_EXTENSIONS:
            raise ReportUnavailableError(f"Formato desconocido: {fmt}")
        try:
            filters = DashboardFilters().resolved()
            payload = self._dashboard.build_dashboard(filters).to_dict()
            meta = {
                "usuario": self._actor_user_id or "—",
                "rango": f"{filters.date_from} a {filters.date_to}",
                "sucursal": branch_label,
                "generado": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            return self._export.export_summary(payload, meta, filepath, fmt=fmt)
        except ReportUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 - surface, never crash the page
            raise ReportUnavailableError(str(exc)) from exc
