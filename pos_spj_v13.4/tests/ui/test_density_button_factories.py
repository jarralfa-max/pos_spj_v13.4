"""Factory buttons must respect the profile even before its first live change."""
import pytest
from PyQt5 import sip
from PyQt5.QtCore import QSettings

from frontend.desktop.components import buttons
from frontend.desktop.themes.theme_manager import ThemeManager
from frontend.desktop.themes.tokens import density_metrics


@pytest.mark.parametrize("density", ["compact", "comfortable", "touch"])
@pytest.mark.parametrize("factory", [buttons.create_primary_button, buttons.create_secondary_button,
                                    buttons.create_success_button, buttons.create_warning_button,
                                    buttons.create_danger_button, buttons.create_outline_button,
                                    buttons.create_ghost_button])
def test_factory_uses_current_profile_immediately(qt_font_resources, ui_tmp_path, monkeypatch, density, factory):
    manager = ThemeManager(QSettings(str(ui_tmp_path / "factory.ini"), QSettings.IniFormat))
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    manager.apply(qt_font_resources, "light", density=density)
    button = factory(text="Consultar")
    try:
        assert button.minimumHeight() == density_metrics(density).button_height
        assert button.text() == "Consultar" and button.isEnabled()
    finally:
        sip.delete(button)
