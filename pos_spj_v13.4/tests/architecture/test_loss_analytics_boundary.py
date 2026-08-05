from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def test_loss20_ui_uses_query_service_and_canonical_charts_without_sql():
    page=(ROOT/"frontend/desktop/modules/losses/pages/analytics_page.py").read_text(encoding="utf-8");service=(ROOT/"backend/application/losses/analytics.py").read_text(encoding="utf-8")
    assert "HtmlChartView" in page and "KPIBar" in page and "SELECT " not in page and ".execute(" not in page
    assert "ChartDataDTO" in service and "build_pareto" in service
def test_loss20_repository_is_read_only_and_export_is_application_owned():
    repository=(ROOT/"backend/infrastructure/persistence/loss_analytics_repository.py").read_text(encoding="utf-8");service=(ROOT/"backend/application/losses/analytics.py").read_text(encoding="utf-8")
    for mutation in ("INSERT ","UPDATE ","DELETE ","CREATE TABLE"):assert mutation not in repository
    assert "csv.writer" in service and "LossPermissions.EXPORT" in service
