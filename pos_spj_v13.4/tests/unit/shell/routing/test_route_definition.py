import pytest

from frontend.desktop.shell.modules.startup_mode import StartupMode
from frontend.desktop.shell.routing.cache_policy import CachePolicy
from frontend.desktop.shell.routing.offline_policy import OfflinePolicy
from frontend.desktop.shell.routing.route_definition import RouteDefinition


def _route(**overrides) -> RouteDefinition:
    kwargs = dict(
        route_id="sales.pos", module_id="sales", title="Punto de Venta",
        view_factory_id="sales.pos_view",
    )
    kwargs.update(overrides)
    return RouteDefinition(**kwargs)


def test_minimal_route_has_sane_defaults():
    route = _route()
    assert route.startup_mode is StartupMode.LAZY
    assert route.cache_policy is CachePolicy.RECREATE_ON_NAVIGATION
    assert route.offline_policy is OfflinePolicy.REQUIRES_ONLINE
    assert route.breadcrumb == ()
    assert route.required_permission == ""
    assert route.feature_flag == ""


def test_full_route_matches_master_plan_example_shape():
    route = _route(
        breadcrumb=("Ventas", "Punto de Venta"),
        required_permission="POS.ver",
        feature_flag="new_pos_ui",
        startup_mode=StartupMode.EAGER,
        cache_policy=CachePolicy.KEEP_ALIVE,
        offline_policy=OfflinePolicy.AVAILABLE_OFFLINE,
    )
    assert route.route_id == "sales.pos"
    assert route.breadcrumb == ("Ventas", "Punto de Venta")
    assert route.cache_policy is CachePolicy.KEEP_ALIVE


@pytest.mark.parametrize("field", ["route_id", "module_id", "title", "view_factory_id"])
def test_rejects_empty_required_fields(field):
    with pytest.raises(ValueError):
        _route(**{field: ""})


def test_route_is_frozen():
    route = _route()
    with pytest.raises(AttributeError):
        route.title = "other"
