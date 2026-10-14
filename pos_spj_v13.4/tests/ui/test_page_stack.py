"""Cached page geometry must never create overflow on an unrelated page."""

import pytest
from PyQt5 import sip
from PyQt5.QtWidgets import QLabel, QLineEdit, QVBoxLayout, QWidget

from frontend.desktop.components.page_viewport import PageViewport
from frontend.desktop.components.pages import WizardPage
from frontend.desktop.modules.pricing.navigation import PRICING_NAV
from frontend.desktop.modules.pricing.pricing_workspace import PricingWorkspace


def settle(app):
    for _ in range(6):
        app.processEvents()


def bars(viewport):
    return (viewport.horizontalScrollBar().maximum(),
            viewport.verticalScrollBar().maximum())


def test_pricing_cached_large_page_does_not_enlarge_returned_small_page(qt_font_resources):
    app = qt_font_resources
    route_ids = [entry.page_id for entry in PRICING_NAV]
    built = []

    def build(route_id, _presenter):
        built.append(route_id)
        page = QLineEdit()
        if route_id == route_ids[1]:
            page.setMinimumSize(1800, 1200)
        return page

    workspace = PricingWorkspace(None, has_permission=lambda _: True, page_builder=build)
    try:
        workspace.resize(1000, 600)
        workspace.show()
        settle(app)
        first = workspace._stack.currentWidget()
        first.setText("Captura pendiente")
        assert bars(workspace.viewport) == (0, 0)
        workspace.select_page(route_ids[1])
        settle(app)
        assert all(value > 0 for value in bars(workspace.viewport))
        workspace.select_page(route_ids[0])
        settle(app)
        assert workspace._stack.currentWidget() is first
        assert first.text() == "Captura pendiente"
        assert built == route_ids[:2]
        assert bars(workspace.viewport) == (0, 0)
    finally:
        workspace.close()
        sip.delete(workspace)


@pytest.fixture
def stack_viewport(qt_font_resources):
    from frontend.desktop.components.page_stack import PageStack

    viewport = PageViewport()
    stack = PageStack()
    viewport.set_page(stack)
    viewport.resize(640, 480)
    yield qt_font_resources, viewport, stack
    viewport.close()
    sip.delete(viewport)


def test_active_page_minimum_and_cached_page_identity_survive_switches(stack_viewport):
    app, viewport, stack = stack_viewport
    small, large = QWidget(), QWidget()
    small.setMinimumSize(100, 90)
    large.setMinimumSize(1600, 1200)
    stack.addWidget(small)
    stack.addWidget(large)
    viewport.show()
    settle(app)
    assert bars(viewport) == (0, 0)
    stack.setCurrentWidget(large)
    settle(app)
    assert all(value > 0 for value in bars(viewport))
    stack.setCurrentWidget(small)
    settle(app)
    assert bars(viewport) == (0, 0)
    assert stack.count() == 2
    assert stack.widget(1) is large
    assert (large.minimumWidth(), large.minimumHeight()) == (1600, 1200)
    assert (small.minimumWidth(), small.minimumHeight()) == (100, 90)


def test_hidden_dynamic_content_does_not_expand_current_page(stack_viewport):
    app, viewport, stack = stack_viewport
    small, form = QWidget(), QWidget()
    layout = QVBoxLayout(form)
    stack.addWidget(small)
    stack.addWidget(form)
    viewport.show()
    settle(app)
    fields = []
    for index in range(35):
        field = QLineEdit(str(index))
        layout.addWidget(field)
        fields.append(field)
    settle(app)
    assert bars(viewport) == (0, 0)
    stack.setCurrentWidget(form)
    settle(app)
    assert viewport.verticalScrollBar().maximum() > 0
    for field in fields:
        layout.removeWidget(field)
        sip.delete(field)
    settle(app)
    assert bars(viewport) == (0, 0)


def test_removed_large_page_releases_overflow_without_destroying_other_page(stack_viewport):
    app, viewport, stack = stack_viewport
    large, small = QWidget(), QLineEdit("Conservado")
    large.setMinimumSize(1600, 1200)
    stack.addWidget(large)
    stack.addWidget(small)
    viewport.show()
    settle(app)
    assert all(value > 0 for value in bars(viewport))
    stack.removeWidget(large)
    settle(app)
    assert stack.currentWidget() is small
    assert small.text() == "Conservado"
    assert bars(viewport) == (0, 0)
    sip.delete(large)


def test_wrapped_active_content_keeps_every_line_reachable(stack_viewport):
    app, viewport, stack = stack_viewport
    page = QWidget()
    layout = QVBoxLayout(page)
    label = QLabel("Texto largo que debe quedar visible al reducir el ancho. " * 40)
    label.setWordWrap(True)
    layout.addWidget(label)
    stack.addWidget(page)
    viewport.resize(360, 240)
    viewport.show()
    settle(app)
    assert viewport.horizontalScrollBar().maximum() == 0
    assert viewport.verticalScrollBar().maximum() > 0
    assert label.height() >= label.heightForWidth(label.width())


def test_wizard_only_current_step_contributes_overflow(qt_font_resources):
    app = qt_font_resources
    wizard = WizardPage(title="Captura por pasos")
    small, large = QLineEdit("Dato pendiente"), QWidget()
    large.setMinimumSize(1600, 1200)
    wizard.add_step(small)
    wizard.add_step(large)
    try:
        wizard.resize(640, 480)
        wizard.show()
        settle(app)
        assert bars(wizard.viewport) == (0, 0)
        wizard.next_button.click()
        settle(app)
        assert all(value > 0 for value in bars(wizard.viewport))
        wizard.previous_button.click()
        settle(app)
        assert wizard.steps.currentWidget() is small
        assert small.text() == "Dato pendiente"
        assert bars(wizard.viewport) == (0, 0)
    finally:
        wizard.close()
        sip.delete(wizard)
