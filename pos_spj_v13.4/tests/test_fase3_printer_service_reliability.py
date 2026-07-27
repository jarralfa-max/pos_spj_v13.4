import threading
import time

from core.services.printer_service import (
    PrintJob,
    PrintJobType,
    PrintJobStatus,
    PrintQueue,
    PrintTransport,
    PrinterService,
    TransportType,
)


def test_print_worker_false_transport_marks_failed(monkeypatch):
    q = PrintQueue()
    monkeypatch.setattr(PrintTransport, "send", staticmethod(lambda *a, **k: False))
    q._running = True
    called = []
    job = PrintJob(job_type=PrintJobType.TICKET, data=b"x", transport=TransportType.NETWORK, destination="127.0.0.1:9100", retries=1, on_error=lambda e: called.append(str(e)))
    q.submit(job)
    t = threading.Thread(target=q._worker, daemon=True)
    t.start()
    time.sleep(0.2)
    q._running = False
    t.join(timeout=1)
    assert job.status == PrintJobStatus.FAILED
    assert "Transport returned False" in (job.error_msg or "")
    assert called


def test_print_ticket_invalid_config_not_queued(monkeypatch):
    s = PrinterService(db_conn=None)
    s._ticket_cfg = {"tipo": "network", "ubicacion": ""}
    count = []
    monkeypatch.setattr(s.queue, "submit", lambda job: count.append(job))
    assert s.print_ticket({"folio": "F1"}) == ""
    assert count == []
    s.close()


def test_has_ticket_printer_uses_validation(monkeypatch):
    s = PrinterService(db_conn=None)
    monkeypatch.setattr(s, "validate_ticket_printer_config", lambda: type("VR", (), {"ok": False})())
    assert s.has_ticket_printer() is False
    s.close()


def test_serial_unavailable_validation_fails(monkeypatch):
    s = PrinterService(db_conn=None)
    s._ticket_cfg = {"tipo": "serial", "ubicacion": "COM9"}
    monkeypatch.setattr(PrintTransport, "is_available", staticmethod(lambda *a, **k: False))
    vr = s.validate_ticket_printer_config()
    assert vr.ok is False
    assert any("no disponible" in e.lower() for e in vr.errors)
    s.close()


def test_win32_unavailable_validation_fails(monkeypatch):
    s = PrinterService(db_conn=None)
    s._ticket_cfg = {"tipo": "usb_win32", "ubicacion": "POS-PRINTER"}
    monkeypatch.setattr(PrintTransport, "is_available", staticmethod(lambda *a, **k: False))
    vr = s.validate_ticket_printer_config()
    assert vr.ok is False
    s.close()


def test_network_unavailable_validation_fails(monkeypatch):
    s = PrinterService(db_conn=None)
    s._ticket_cfg = {"tipo": "network", "ubicacion": "127.0.0.1:9100"}
    monkeypatch.setattr(PrintTransport, "is_available", staticmethod(lambda *a, **k: False))
    vr = s.validate_ticket_printer_config()
    assert vr.ok is False
    s.close()


def test_on_error_called_when_print_config_invalid():
    s = PrinterService(db_conn=None)
    s._ticket_cfg = {"tipo": "network", "ubicacion": ""}
    called = []
    s.print_ticket({"folio": "F2"}, on_error=lambda e: called.append(str(e)))
    assert called
    s.close()
