from frontend.desktop.shell.modules.startup_mode import StartupMode


def test_has_the_four_master_plan_modes():
    assert {m.value for m in StartupMode} == {"EAGER", "LAZY", "ON_DEMAND", "BACKGROUND_PRELOAD"}
