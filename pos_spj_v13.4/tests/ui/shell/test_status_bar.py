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
