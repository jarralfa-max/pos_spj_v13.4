import pytest

from frontend.desktop.shell.router.errors import NoNavigationHistoryError
from frontend.desktop.shell.router.navigation_history import NavigationHistory


def test_starts_empty():
    history = NavigationHistory()
    assert history.current() is None
    assert history.can_go_back() is False
    assert history.can_go_forward() is False


def test_push_sets_current():
    history = NavigationHistory()
    history.push("sales.pos")
    assert history.current() == "sales.pos"


def test_push_twice_enables_back():
    history = NavigationHistory()
    history.push("sales.pos")
    history.push("inventory.overview")
    assert history.current() == "inventory.overview"
    assert history.can_go_back() is True
    assert history.peek_back() == "sales.pos"


def test_push_same_route_id_does_not_duplicate_back_entry():
    history = NavigationHistory()
    history.push("sales.pos")
    history.push("sales.pos")
    assert history.can_go_back() is False


def test_commit_back_moves_pointer_and_enables_forward():
    history = NavigationHistory()
    history.push("sales.pos")
    history.push("inventory.overview")
    route_id = history.commit_back()
    assert route_id == "sales.pos"
    assert history.current() == "sales.pos"
    assert history.can_go_forward() is True
    assert history.peek_forward() == "inventory.overview"


def test_commit_forward_moves_pointer_back_to_original():
    history = NavigationHistory()
    history.push("sales.pos")
    history.push("inventory.overview")
    history.commit_back()
    route_id = history.commit_forward()
    assert route_id == "inventory.overview"
    assert history.current() == "inventory.overview"
    assert history.can_go_forward() is False


def test_peek_back_without_history_raises():
    with pytest.raises(NoNavigationHistoryError):
        NavigationHistory().peek_back()


def test_peek_forward_without_history_raises():
    with pytest.raises(NoNavigationHistoryError):
        NavigationHistory().peek_forward()


def test_new_push_after_back_clears_forward_stack():
    history = NavigationHistory()
    history.push("sales.pos")
    history.push("inventory.overview")
    history.commit_back()
    history.push("whatsapp.status")
    assert history.can_go_forward() is False


def test_peek_does_not_mutate_state():
    history = NavigationHistory()
    history.push("sales.pos")
    history.push("inventory.overview")
    history.peek_back()
    history.peek_back()
    assert history.current() == "inventory.overview"
    assert history.peek_back() == "sales.pos"


def test_clear_resets_everything():
    history = NavigationHistory()
    history.push("sales.pos")
    history.push("inventory.overview")
    history.clear()
    assert history.current() is None
    assert history.can_go_back() is False
    assert history.can_go_forward() is False
