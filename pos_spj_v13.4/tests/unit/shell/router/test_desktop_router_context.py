from frontend.desktop.shell.router.desktop_router import DesktopRouter
from tests.unit.shell.router.conftest import make_context


def test_current_context_reflects_constructor_argument(routes, view_factories, context):
    router = DesktopRouter(route_registry=routes, view_factory_registry=view_factories, initial_context=context)
    assert router.current_context is context


def test_update_context_replaces_current_context(routes, view_factories, context):
    router = DesktopRouter(route_registry=routes, view_factory_registry=view_factories, initial_context=context)
    new_context = make_context(user_id="user-2")
    router.update_context(new_context)
    assert router.current_context is new_context


def test_navigate_after_update_context_uses_the_new_context_for_authorization(routes, view_factories, context):
    router = DesktopRouter(
        route_registry=routes, view_factory_registry=view_factories,
        initial_context=make_context(permissions=frozenset()),
    )
    router.update_context(make_context(permissions=frozenset({"SALES.VER"})))
    result = router.navigate("sales.pos")
    assert result.route.route_id == "sales.pos"


def test_current_route_still_allowed_true_when_nothing_navigated(routes, view_factories, context):
    router = DesktopRouter(route_registry=routes, view_factory_registry=view_factories, initial_context=context)
    assert router.current_route_still_allowed() is True


def test_current_route_still_allowed_true_after_valid_navigation(routes, view_factories, context):
    router = DesktopRouter(route_registry=routes, view_factory_registry=view_factories, initial_context=context)
    router.navigate("sales.pos")
    assert router.current_route_still_allowed() is True


def test_current_route_still_allowed_false_after_permission_revoked(routes, view_factories, context):
    router = DesktopRouter(route_registry=routes, view_factory_registry=view_factories, initial_context=context)
    router.navigate("sales.pos")
    router.update_context(make_context(permissions=frozenset()))
    assert router.current_route_still_allowed() is False


def test_current_route_still_allowed_false_after_feature_flag_disabled(routes, view_factories):
    from backend.bootstrap.application_context import FeatureContext

    router = DesktopRouter(
        route_registry=routes, view_factory_registry=view_factories,
        initial_context=make_context(feature_context=FeatureContext(enabled_features=frozenset({"whatsapp_module"}))),
    )
    router.navigate("whatsapp.status")
    router.update_context(make_context(feature_context=FeatureContext()))
    assert router.current_route_still_allowed() is False
