# LOSS-20 — BI and analytics

- Branch-scoped QueryService with timezone-aware periods and granular permissions.
- Exact Decimal KPIs: case count, gross value, recovery, net loss, recovery rate, investigations and overdue actions.
- Canonical `ChartDataDTO` outputs for status distribution, Pareto and daily trend; charts degrade to accessible tables.
- Pareto exposes individual and cumulative percentages.
- Stable UTF-8 CSV export is generated in application code from repository rows.
- Desktop Overview and Analysis routes use the same presenter and read model; no SQL is present in PyQt.
