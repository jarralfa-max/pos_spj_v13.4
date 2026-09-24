from frontend.desktop.shell.application_shell.status_bar import StatusBar


def test_default_connectivity_text_is_online():
    bar = StatusBar()
    assert bar.connectivity_text == "En línea"


def test_offline_status_shows_sin_conexion():
    bar = StatusBar()
    bar.set_offline_status("OFFLINE")
    assert bar.connectivity_text == "Sin conexión"


def test_online_but_degraded_route_shows_conexion_limitada():
    bar = StatusBar()
    bar.set_offline_status("ONLINE", degraded=True)
    assert bar.connectivity_text == "Conexión limitada"


def test_degraded_flag_takes_priority_over_offline_status():
    bar = StatusBar()
    bar.set_offline_status("OFFLINE", degraded=True)
    assert bar.connectivity_text == "Conexión limitada"


def test_online_not_degraded_shows_en_linea():
    bar = StatusBar()
    bar.set_offline_status("OFFLINE")
    bar.set_offline_status("ONLINE", degraded=False)
    assert bar.connectivity_text == "En línea"


def test_set_workstation_shows_branch_and_workstation_id():
    bar = StatusBar()
    bar.set_workstation("ws-7", "Sucursal Norte")
    assert "Sucursal Norte" in bar.workstation_text
    assert "ws-7" in bar.workstation_text


def test_startup_message_does_not_overlap_connectivity(qt_font_resources):
    from PyQt5 import sip
    from frontend.desktop.components.standard_window import StandardWindow
    window = StandardWindow()
    bar = StatusBar(window)
    window.setStatusBar(bar)
    bar.set_workstation("ws-7", "Sucursal Norte")
    bar.showMessage("Lista para operar")
    try:
        window.show()
        qt_font_resources.processEvents()
        assert not bar._connectivity_badge.isVisible()
        assert bar._workstation_label.isVisible()
        assert bar.currentMessage() == "Lista para operar"
        bar.clearMessage()
        qt_font_resources.processEvents()
        assert bar._connectivity_badge.isVisible()
        assert bar.connectivity_text == "En línea"
    finally:
        sip.delete(window)
