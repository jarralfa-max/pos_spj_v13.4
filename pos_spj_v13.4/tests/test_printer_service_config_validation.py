from core.services.printer_service import PrinterService


def _svc(cfg):
    s = PrinterService(db_conn=None)
    s._ticket_cfg = cfg
    return s


def test_config_valida_tcp():
    s = _svc({"transport": "tcp", "ubicacion": "127.0.0.1:9100", "encoding": "cp850"})
    r = s.validate_ticket_printer_config()
    assert r.ok is True


def test_config_valida_serial():
    s = _svc({"transport": "serial", "ubicacion": "COM4", "baud_rate": "9600"})
    r = s.validate_ticket_printer_config()
    assert r.ok is True


def test_config_valida_usb_win32():
    s = _svc({"transport": "usb_win32", "ubicacion": "EPSON TM-T20"})
    r = s.validate_ticket_printer_config()
    assert r.ok is True


def test_config_sin_ubicacion_falla():
    s = _svc({"transport": "tcp", "ubicacion": ""})
    r = s.validate_ticket_printer_config()
    assert r.ok is False


def test_system_no_valido_para_termica():
    s = _svc({"transport": "system", "ubicacion": "Default"})
    r = s.validate_ticket_printer_config()
    assert r.ok is False
    assert any("SYSTEM" in e for e in r.errors)


def test_print_test_ticket_genera_job(monkeypatch):
    s = _svc({"transport": "tcp", "ubicacion": "127.0.0.1:9100", "encoding": "cp850"})
    monkeypatch.setattr(s, "print_ticket", lambda payload: "job-test" if payload.get("ticket_type") == "test_ticket" else "")
    job = s.print_test_ticket()
    assert job == "job-test"
