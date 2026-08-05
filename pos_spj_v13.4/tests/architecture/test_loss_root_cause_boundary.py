from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def test_loss16_ui_uses_presenter_and_search_selectors_without_sql():
    page=(ROOT/"frontend/desktop/modules/losses/pages/root_cause_page.py").read_text(encoding="utf-8")
    presenter=(ROOT/"frontend/desktop/modules/losses/presenters/root_cause_presenter.py").read_text(encoding="utf-8")
    assert page.count("SearchSelector(") >= 3
    assert "SELECT " not in page and ".execute(" not in page
    assert "RecordRootCauseAnalysisCommand" in presenter

def test_loss16_has_catalog_methods_contributors_and_canonical_event():
    migration=(ROOT/"migrations/standalone/174_losses_bounded_context_schema.py").read_text(encoding="utf-8")
    domain=(ROOT/"backend/domain/losses/root_cause.py").read_text(encoding="utf-8")
    events=(ROOT/"backend/domain/losses/events.py").read_text(encoding="utf-8")
    assert "loss_root_cause_catalog" in migration
    assert "loss_root_cause_analyses" in migration
    assert "role IN ('PRIMARY','CONTRIBUTING')" in migration
    for method in ("FIVE_WHYS","FISHBONE","PARETO","FAULT_TREE","DIRECT_OBSERVATION"):
        assert method in domain
    assert "LOSS_ROOT_CAUSE_RECORDED" in events
