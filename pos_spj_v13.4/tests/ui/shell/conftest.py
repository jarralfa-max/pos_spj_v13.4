import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PyQt5")

from PyQt5.QtWidgets import QApplication  # noqa: E402

from backend.bootstrap.application_context import ApplicationContext, FeatureContext  # noqa: E402
from frontend.desktop.shell.routing.route_definition import RouteDefinition  # noqa: E402
from frontend.desktop.shell.routing.route_registry import RouteRegistry  # noqa: E402
from frontend.desktop.shell.routing.view_factory_registry import ViewFactoryRegistry  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def app():
    application = QApplication.instance() or QApplication([])
    yield application


def make_context(**overrides) -> ApplicationContext:
    fields = dict(
        installation_id="install-1", company_id="company-1", branch_id="branch-1",
        branch_name="Sucursal Centro", workstation_id="ws-1", workstation_type="pos",
        user_id="user-1", user_name="Jose Alfaro", roles=("admin",),
        permissions=frozenset({"*"}), feature_context=FeatureContext(),
        session_id="session-1",
    )
    fields.update(overrides)
    return ApplicationContext(**fields)


@pytest.fixture
def context() -> ApplicationContext:
    return make_context()
