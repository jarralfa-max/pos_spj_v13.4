import pytest

from frontend.desktop.shell.background.background_service_descriptor import BackgroundServiceDescriptor


def test_minimal_descriptor_has_sane_defaults():
    descriptor = BackgroundServiceDescriptor(service_id="sync", display_name="Sync Engine")
    assert descriptor.module_id == ""


def test_descriptor_is_frozen():
    descriptor = BackgroundServiceDescriptor(service_id="sync", display_name="Sync Engine")
    with pytest.raises(AttributeError):
        descriptor.display_name = "other"


@pytest.mark.parametrize("field", ["service_id", "display_name"])
def test_rejects_empty_required_fields(field):
    kwargs = dict(service_id="sync", display_name="Sync Engine")
    kwargs[field] = ""
    with pytest.raises(ValueError):
        BackgroundServiceDescriptor(**kwargs)
