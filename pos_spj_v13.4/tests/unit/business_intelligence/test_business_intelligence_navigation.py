from frontend.desktop.modules.business_intelligence.navigation.business_intelligence_sidebar import (
    BUSINESS_INTELLIGENCE_NAV,
    visible_entries,
)


def test_nav_has_unique_page_ids():
    page_ids = [entry.page_id for entry in BUSINESS_INTELLIGENCE_NAV]
    assert len(page_ids) == len(set(page_ids))


def test_executive_dashboard_is_first_entry():
    assert BUSINESS_INTELLIGENCE_NAV[0].page_id == "bi_executive"


def test_visible_entries_filters_by_permission():
    allowed = {BUSINESS_INTELLIGENCE_NAV[0].permission}
    visible = visible_entries(lambda perm: perm in allowed)
    assert len(visible) == 1
    assert visible[0][0].page_id == "bi_executive"


def test_visible_entries_grants_all_when_permission_check_allows_everything():
    visible = visible_entries(lambda perm: True)
    assert len(visible) == len(BUSINESS_INTELLIGENCE_NAV)


def test_visible_entries_denies_all_when_permission_check_denies_everything():
    visible = visible_entries(lambda perm: False)
    assert visible == ()


def test_badge_lookup_returns_none_when_no_badges_provided():
    entries_with_badge_key = [e for e in BUSINESS_INTELLIGENCE_NAV if e.badge_key]
    assert entries_with_badge_key  # sanity: at least one entry declares a badge_key
    visible = visible_entries(lambda perm: True, badges=None)
    for entry, badge in visible:
        if entry.badge_key:
            assert badge is None


def test_badge_lookup_returns_count_when_provided():
    entry_with_badge = next(e for e in BUSINESS_INTELLIGENCE_NAV if e.badge_key)
    visible = visible_entries(lambda perm: True, badges={entry_with_badge.badge_key: 5})
    match = next(b for e, b in visible if e.page_id == entry_with_badge.page_id)
    assert match == 5
