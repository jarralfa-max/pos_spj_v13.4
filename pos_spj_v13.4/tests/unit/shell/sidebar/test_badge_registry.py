from frontend.desktop.shell.sidebar.badge_registry import BadgeRegistry


def test_unregistered_key_resolves_to_none():
    registry = BadgeRegistry()
    assert registry.count_for("sales.pending") is None


def test_empty_key_resolves_to_none():
    registry = BadgeRegistry()
    assert registry.count_for("") is None


def test_registered_source_is_invoked():
    registry = BadgeRegistry()
    registry.register("sales.pending", lambda: 7)
    assert registry.count_for("sales.pending") == 7


def test_is_registered_reflects_state():
    registry = BadgeRegistry()
    assert registry.is_registered("sales.pending") is False
    registry.register("sales.pending", lambda: 1)
    assert registry.is_registered("sales.pending") is True


def test_re_registering_a_key_replaces_the_source():
    registry = BadgeRegistry()
    registry.register("sales.pending", lambda: 1)
    registry.register("sales.pending", lambda: 99)
    assert registry.count_for("sales.pending") == 99


def test_source_is_invoked_fresh_on_every_call():
    counter = {"n": 0}

    def source():
        counter["n"] += 1
        return counter["n"]

    registry = BadgeRegistry()
    registry.register("k", source)
    assert registry.count_for("k") == 1
    assert registry.count_for("k") == 2
