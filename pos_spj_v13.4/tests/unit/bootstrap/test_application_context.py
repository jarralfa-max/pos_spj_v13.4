from backend.bootstrap.application_context import (
    DEFAULT_CURRENCY,
    DEFAULT_LOCALE,
    DEFAULT_TIMEZONE,
    ApplicationContext,
    FeatureContext,
    default_workstation_id,
)


def _context(**overrides) -> ApplicationContext:
    fields = dict(
        installation_id="install-1", company_id="company-1", branch_id="branch-1",
        branch_name="Sucursal Centro", workstation_id="ws-1", workstation_type="pos",
        user_id="user-1", user_name="Jose Alfaro", roles=("cajero",),
        permissions=frozenset({"POS.ver"}), feature_context=FeatureContext(),
        session_id="session-1",
    )
    fields.update(overrides)
    return ApplicationContext(**fields)


def test_default_locale_timezone_currency():
    ctx = _context()
    assert ctx.locale == DEFAULT_LOCALE == "es-MX"
    assert ctx.timezone == DEFAULT_TIMEZONE == "America/Mexico_City"
    assert ctx.currency == DEFAULT_CURRENCY == "MXN"


def test_default_workstation_id_is_non_empty_string():
    assert isinstance(default_workstation_id(), str)
    assert default_workstation_id() != ""


def test_is_admin_true_for_admin_role():
    assert _context(roles=("admin",)).is_admin() is True


def test_is_admin_true_for_system_owner_role():
    assert _context(roles=("system_owner",)).is_admin() is True


def test_is_admin_is_case_insensitive():
    assert _context(roles=("ADMIN",)).is_admin() is True


def test_is_admin_false_for_regular_role():
    assert _context(roles=("cajero",)).is_admin() is False


def test_is_admin_true_if_any_role_is_admin():
    assert _context(roles=("cajero", "admin")).is_admin() is True


def test_context_is_frozen():
    ctx = _context()
    try:
        ctx.branch_id = "other"
        assert False, "ApplicationContext should be immutable"
    except AttributeError:
        pass


def test_with_branch_returns_new_instance_and_leaves_original_unchanged():
    ctx = _context()
    new_features = FeatureContext(enabled_features=frozenset({"new_pos_ui"}))
    switched = ctx.with_branch(
        branch_id="branch-2", branch_name="Sucursal Norte",
        permissions=frozenset({"POS.ver", "POS.crear"}), feature_context=new_features,
    )

    assert switched is not ctx
    assert switched.branch_id == "branch-2"
    assert switched.branch_name == "Sucursal Norte"
    assert switched.permissions == frozenset({"POS.ver", "POS.crear"})
    assert switched.feature_context is new_features
    assert ctx.branch_id == "branch-1"  # original untouched


def test_with_branch_preserves_unrelated_fields():
    ctx = _context()
    switched = ctx.with_branch(
        branch_id="branch-2", branch_name="Sucursal Norte",
        permissions=frozenset(), feature_context=FeatureContext(),
    )
    assert switched.user_id == ctx.user_id
    assert switched.session_id == ctx.session_id
    assert switched.installation_id == ctx.installation_id
    assert switched.roles == ctx.roles


# ── FeatureContext ───────────────────────────────────────────────────────────

def test_feature_context_defaults_to_no_features_enabled():
    assert FeatureContext().is_enabled("anything") is False


def test_feature_context_is_enabled_true_for_included_feature():
    fc = FeatureContext(enabled_features=frozenset({"whatsapp"}))
    assert fc.is_enabled("whatsapp") is True
    assert fc.is_enabled("delivery") is False


def test_feature_context_from_flags_dict_only_includes_enabled():
    fc = FeatureContext.from_flags_dict({"whatsapp": True, "delivery": False, "kiosk": True})
    assert fc.enabled_features == frozenset({"whatsapp", "kiosk"})


def test_feature_context_from_flags_dict_handles_none():
    assert FeatureContext.from_flags_dict(None).enabled_features == frozenset()


def test_feature_context_from_flags_dict_handles_empty_dict():
    assert FeatureContext.from_flags_dict({}).enabled_features == frozenset()
