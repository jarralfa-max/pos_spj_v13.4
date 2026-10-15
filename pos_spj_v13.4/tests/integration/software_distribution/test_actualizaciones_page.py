"""«Acerca de y actualizaciones» builds on real use cases and hides what the
user may not do. No window is shown."""
from __future__ import annotations

import pytest

pytest.importorskip("PyQt5")

from backend.application.configuracion.permissions import ConfiguracionPermissions as P  # noqa: E402
from frontend.desktop.modules.configuracion.navigation.configuracion_sidebar import (  # noqa: E402
    CONFIGURACION_NAV,
)
from frontend.desktop.modules.configuracion.pages import PAGE_CLASSES  # noqa: E402
from frontend.desktop.modules.configuracion.software_updates_presenter import (  # noqa: E402
    SoftwareUpdatesPresenter,
)

from .test_update_use_cases import ALL, env  # noqa: E402,F401  (fixture reuse)


@pytest.fixture(scope="module")
def qapp():
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


class _ModulePresenter:
    def __init__(self, software_updates) -> None:
        self.software_updates = software_updates


def _page(env, granted, handoffs):
    presenter = SoftwareUpdatesPresenter(
        env["deps"](granted=granted), copy_file=lambda a, b: None,
        request_handoff=lambda request: handoffs.append(request) or True)
    page = PAGE_CLASSES["config_actualizaciones"](_ModulePresenter(presenter))
    page.ensure_loaded()
    return page, presenter


def test_page_is_registered_with_its_view_permission():
    entry = next(e for e in CONFIGURACION_NAV if e.page_id == "config_actualizaciones")
    assert entry.permission == P.ACTUALIZACIONES_VIEW


def test_viewer_sees_status_but_no_actions(qapp, env):
    page, _ = _page(env, {P.ACTUALIZACIONES_VIEW}, [])
    assert page._facts["version"].text() == "13.4.0"
    assert page.download_button.isHidden() and page.install_button.isHidden()
    assert page.offline_button.isHidden()
    assert not page.save_channel_button.isEnabled()
    assert not page.warnings_card.isHidden()  # no signing key in this build


def test_administrator_downloads_and_hands_over_to_the_updater(qapp, env):
    env["publish"]()
    handoffs = []
    page, presenter = _page(env, ALL, handoffs)
    ok, _ = presenter.check()
    assert ok
    page.reload()
    assert page.download_button.isEnabled() and not page.install_button.isEnabled()
    prepared, message = presenter.prepare_download()
    assert prepared is not None, message
    prepared.run()  # the worker thread's part, run inline here
    ok, _ = presenter.finish_download(prepared, None)
    assert ok
    page.reload()
    assert page.install_button.isEnabled()
    ok, message = presenter.install_now()
    assert ok, message
    assert handoffs and handoffs[0].job.to_version == "13.5.0"


def test_failed_handoff_cancels_the_staged_job(qapp, env):
    env["publish"]()
    presenter = SoftwareUpdatesPresenter(env["deps"](), copy_file=lambda a, b: None,
                                         request_handoff=lambda request: False)
    presenter.check()
    prepared, _ = presenter.prepare_download()
    prepared.run()
    presenter.finish_download(prepared, None)
    ok, message = presenter.install_now()
    assert not ok and "no se cambió nada" in message
    assert env["deps"]().job_store.load() is None
