import pytest

from frontend.desktop.components.icons import Icons
from frontend.desktop.shell.sidebar.navigation_item_definition import NavigationItemDefinition


def _item(**overrides) -> NavigationItemDefinition:
    kwargs = dict(
        item_id="nav.sales.pos", module_id="sales", route_id="sales.pos",
        label="Punto de Venta", icon=Icons.SALES,
    )
    kwargs.update(overrides)
    return NavigationItemDefinition(**kwargs)


def test_minimal_item_has_sane_defaults():
    item = _item()
    assert item.order == 0
    assert item.group == ""
    assert item.required_permission == ""
    assert item.feature_flag == ""
    assert item.badge_key == ""


def test_item_is_frozen():
    item = _item()
    with pytest.raises(AttributeError):
        item.label = "other"


@pytest.mark.parametrize("field", ["item_id", "module_id", "route_id", "label", "icon"])
def test_rejects_empty_required_fields(field):
    with pytest.raises(ValueError):
        _item(**{field: ""})
