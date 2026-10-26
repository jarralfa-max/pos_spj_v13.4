"""Product dialogs preserve capture and service calls inside the canonical shell."""
from importlib import import_module
import os
from pathlib import Path
from unittest.mock import Mock

import pytest
from PyQt5 import sip
from PyQt5.QtCore import QEvent, QPoint, QRect, QSettings, Qt
from PyQt5.QtTest import QSignalSpy, QTest
from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QMessageBox

from frontend.desktop.components.dialogs import StandardDialog
from frontend.desktop.themes.theme_manager import ThemeManager
from frontend.desktop.themes.tokens import density_metrics


PRODUCT_ID = "019f327a-1694-7000-8000-000000000001"
UNIT_ID = "019f327a-1694-7000-8000-000000000002"
ATTRIBUTE_ID = "019f327a-1694-7000-8000-000000000003"
OPTION_ID = "019f327a-1694-7000-8000-000000000004"
NAMED_PRODUCT = {"product_id": PRODUCT_ID, "product_name": "Producto de prueba"}
CASES = [
    ("attribute_form_dialog", "AttributeFormDialog", {}),
    ("attribute_form_dialog", "_OptionEditor", {"attribute_id": ATTRIBUTE_ID}),
    ("attribute_form_dialog", "AttributeOptionsDialog", {
        "attribute": {"id": ATTRIBUTE_ID, "name": "Color", "data_type": "LIST"}}),
    ("brand_form_dialog", "BrandFormDialog", {}),
    ("bundle_form_dialog", "BundleFormDialog", {"product_id": PRODUCT_ID}),
    ("bundle_form_dialog", "_ComponentEditor", {}),
    ("bundles_dialog", "BundlesDialog", NAMED_PRODUCT),
    ("category_form_dialog", "CategoryFormDialog", {}),
    ("category_form_dialog", "MoveCategoryDialog", {
        "category_id": ATTRIBUTE_ID, "category_name": "Categoría"}),
    ("cutting_dialog", "CuttingSchemesDialog", NAMED_PRODUCT),
    ("cutting_form_dialog", "CuttingSchemeFormDialog", {"input_product_id": PRODUCT_ID}),
    ("cutting_form_dialog", "_OutputEditor", {}),
    ("product_form_dialog", "ProductFormDialog", {}),
    ("purchase_units_dialog", "PurchaseUnitsDialog", NAMED_PRODUCT),
    ("recipe_form_dialog", "RecipeFormDialog", {"product_id": PRODUCT_ID}),
    ("recipe_form_dialog", "_ComponentEditor", {}),
    ("recipe_form_dialog", "_OutputEditor", {}),
    ("recipes_dialog", "RecipesDialog", NAMED_PRODUCT),
    ("variant_generator_dialog", "VariantGeneratorDialog", NAMED_PRODUCT),
    ("yield_form_dialog", "YieldProfileFormDialog", {"input_product_id": PRODUCT_ID}),
    ("yield_form_dialog", "_OutputEditor", {}),
    ("yields_dialog", "YieldProfilesDialog", NAMED_PRODUCT),
]
CASE_IDS = [f"{module}.{name}" for module, name, _ in CASES]


@pytest.fixture
def presenter():
    result = Mock()
    for name in (
        "list_categories", "list_brands", "list_species", "list_attribute_options",
        "list_bundles", "list_bundle_versions", "list_cutting_schemes",
        "list_cutting_versions", "list_recipes", "list_recipe_versions",
        "list_yield_profiles", "list_yield_versions", "list_variants",
        "variant_axes_catalog", "search_products_for_assignment", "purchase_unit_choices",
    ):
        getattr(result, name).return_value = []
    result.list_units.return_value = [{"id": UNIT_ID, "code": "KG", "name": "Kilogramo"}]
    result.preview_code.return_value = "PR-000001"
    result.settings.defaults.return_value = {}
    result.purchase_unit_profile.return_value = None
    result.product_search_reason.return_value = ""
    for name in ("can_override_code", "can_manage_images"):
        setattr(result, name, False)
    return result


@pytest.fixture
def dialogs(qt_font_resources, monkeypatch, ui_tmp_path):
    app = qt_font_resources
    manager = ThemeManager(settings=QSettings(str(ui_tmp_path / "appearance.ini"), QSettings.IniFormat))
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    manager.apply(app, "light", density="comfortable")
    opened = []

    def build(case, presenter):
        module, name, kwargs = case
        cls = getattr(import_module(f"frontend.desktop.modules.products.dialogs.{module}"), name)
        dialog = cls(**kwargs) if (module, name) == ("bundle_form_dialog", "_ComponentEditor") else cls(presenter, **kwargs)
        opened.append(dialog)
        return dialog

    yield build
    for dialog in opened:
        if not sip.isdeleted(dialog):
            dialog.close()
            sip.delete(dialog)
    app.sendPostedEvents(None, QEvent.DeferredDelete)
    app.processEvents()


def _settle(app):
    for _ in range(4):
        app.processEvents()


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_every_product_dialog_has_scroll_body_and_fixed_footer(dialogs, presenter, case, qt_font_resources, monkeypatch):
    dialog = dialogs(case, presenter)
    assert isinstance(dialog, StandardDialog)
    monkeypatch.setattr(dialog, "available_geometry", lambda: QRect(0, 0, 640, 480))
    dialog.show()
    _settle(qt_font_resources)
    footer = dialog.findChild(QDialogButtonBox)
    assert footer is not None and footer.isVisible()
    assert dialog._frame.indexOf(footer) > dialog._frame.indexOf(dialog.viewport)
    assert not dialog.viewport.isAncestorOf(footer)
    assert dialog._heading.text() == dialog.windowTitle()
    assert dialog.available_geometry().contains(dialog.frameGeometry())
    assert all(button.minimumHeight() >= density_metrics().button_height for button in footer.buttons())


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_escape_rejects_each_product_dialog_without_writes(dialogs, presenter, case, qt_font_resources):
    dialog = dialogs(case, presenter)
    accepted, rejected = QSignalSpy(dialog.accepted), QSignalSpy(dialog.rejected)
    presenter.reset_mock()
    dialog.show()
    _settle(qt_font_resources)
    QTest.keyClick(dialog, Qt.Key_Escape)
    _settle(qt_font_resources)
    assert not dialog.isVisible()
    assert dialog.result() == QDialog.Rejected
    assert len(accepted) == 0 and len(rejected) == 1
    assert presenter.mock_calls == []


@pytest.mark.parametrize("kind", ["brand", "category", "attribute", "option"])
@pytest.mark.parametrize("activation", ["click", "enter"])
def test_catalog_validation_and_saved_payload_are_preserved(dialogs, presenter, qt_font_resources, kind, activation):
    case = {"brand": CASES[3], "category": CASES[7], "attribute": CASES[0], "option": CASES[1]}[kind]
    dialog = dialogs(case, presenter)
    method = {"brand": "save_brand", "category": "save_category", "attribute": "save_attribute", "option": "save_attribute_option"}[kind]
    save = getattr(presenter, method)
    save.return_value = (True, "Guardado", PRODUCT_ID)
    accepted = QSignalSpy(dialog.accepted)
    dialog.show()
    _settle(qt_font_resources)
    button = dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Save)

    def activate():
        if activation == "click":
            QTest.mouseClick(button, Qt.LeftButton)
        else:
            dialog.code.setFocus()
            QTest.keyClick(dialog.code, Qt.Key_Return)
        _settle(qt_font_resources)

    activate()
    assert dialog.isVisible() and len(accepted) == 0
    save.assert_not_called()
    dialog.code.setText(" prueba ")
    (dialog.label if kind == "option" else dialog.name).setText(" Nombre de prueba ")
    activate()
    assert dialog.result() == QDialog.Accepted and len(accepted) == 1
    expected = {
        "brand": dict(brand_id=None, code="PRUEBA", name="Nombre de prueba", description=None),
        "category": dict(category_id=None, code="PRUEBA", name="Nombre de prueba", parent_id=None, sort_order=0),
        "attribute": dict(attribute_id=None, code="PRUEBA", name="Nombre de prueba", data_type="LIST"),
        "option": dict(option_id=None, attribute_id=ATTRIBUTE_ID, code="PRUEBA", label="Nombre de prueba", sort_order=0, active=True),
    }[kind]
    save.assert_called_once_with(**expected)


def test_product_save_failure_keeps_capture_and_success_accepts_once(dialogs, presenter, qt_font_resources, monkeypatch):
    dialog = dialogs(CASES[12], presenter)
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: warnings.append(_args))
    dialog.show()
    _settle(qt_font_resources)
    accepted = QSignalSpy(dialog.accepted)
    button = dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.Save)
    QTest.mouseClick(button, Qt.LeftButton)
    presenter.save_product.assert_not_called()
    assert dialog.isVisible() and not accepted
    dialog.name.setText("Producto capturado")
    dialog.product_type.setCurrentIndex(dialog.product_type.findData("FINISHED_GOOD"))
    dialog.base_unit.set_current_id(UNIT_ID)
    expected = dialog._fields()
    presenter.save_product.return_value = (False, "Error de prueba", None)
    QTest.mouseClick(button, Qt.LeftButton)
    assert dialog.isVisible() and len(accepted) == 0
    assert dialog._fields() == expected and len(warnings) == 1
    presenter.save_product.assert_called_once_with(product_id=None, fields=expected)
    presenter.save_product.return_value = (True, "Guardado", PRODUCT_ID)
    QTest.mouseClick(button, Qt.LeftButton)
    assert dialog.result() == QDialog.Accepted and len(accepted) == 1
    assert presenter.save_product.call_count == 2


def test_variant_generate_retains_nonclosing_behavior(dialogs, presenter, qt_font_resources):
    presenter.variant_axes_catalog.return_value = [{
        "id": ATTRIBUTE_ID, "name": "Color", "code": "COLOR",
        "options": [{"id": OPTION_ID, "label": "Rojo", "code": "ROJO"}],
    }]
    presenter.generate_variants.return_value = (True, "Variantes generadas")
    dialog = dialogs(CASES[18], presenter)
    dialog.show()
    _settle(qt_font_resources)
    accepted = QSignalSpy(dialog.accepted)
    QTest.mouseClick(dialog._btn_generate, Qt.LeftButton)
    presenter.generate_variants.assert_not_called()
    dialog.tree.topLevelItem(0).child(0).setCheckState(0, Qt.Checked)
    QTest.mouseClick(dialog._btn_generate, Qt.LeftButton)
    presenter.generate_variants.assert_called_once_with(parent_product_id=PRODUCT_ID, axes={ATTRIBUTE_ID: [OPTION_ID]})
    assert dialog.isVisible() and len(accepted) == 0
    assert dialog._status.text() == "Variantes generadas"


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("density", ["compact", "comfortable", "touch"])
def test_product_long_form_scroll_keeps_footer_and_capture(dialogs, presenter, qt_font_resources, monkeypatch, theme, density):
    manager = ThemeManager.instance()
    manager.apply(qt_font_resources, theme, density=density)
    dialog = dialogs(CASES[12], presenter)
    assert isinstance(dialog, StandardDialog)
    monkeypatch.setattr(dialog, "available_geometry", lambda: QRect(0, 0, 640, 480))
    dialog.name.setText("Captura conservada")
    expected = dialog._fields()
    dialog.show()
    _settle(qt_font_resources)
    footer = dialog.findChild(QDialogButtonBox)
    original = footer.mapTo(dialog, QPoint())
    dialog.tabs.setCurrentIndex(1)  # Operación: las capacidades ahora están en su propia pestaña.
    _settle(qt_font_resources)
    scroll = dialog.viewport.verticalScrollBar()
    assert scroll.maximum() > 0
    scroll.setValue(scroll.maximum())
    _settle(qt_font_resources)
    assert footer.mapTo(dialog, QPoint()) == original
    last_field = dialog._flag_boxes["internal_only"]
    assert dialog.viewport.viewport().rect().contains(last_field.mapTo(dialog.viewport.viewport(), last_field.rect().bottomRight()))
    manager.set_density("touch" if density != "touch" else "compact")
    _settle(qt_font_resources)
    assert dialog._fields() == expected and footer.isVisible()
    assert dialog.available_geometry().contains(dialog.frameGeometry())
    artifact_dir = os.environ.get("SPJ_SHELL_DIALOG_ARTIFACTS")
    if artifact_dir:
        target = Path(artifact_dir)
        target.mkdir(parents=True, exist_ok=True)
        manager.set_density(density)
        _settle(qt_font_resources)
        scroll.setValue(scroll.maximum())
        assert dialog.grab().save(str(target / f"products-{theme}-{density}-640x480.png"))
