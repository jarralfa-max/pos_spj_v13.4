import sys
from pathlib import Path
import sqlite3
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pos_spj_v13.4"))

from erp.bridge import ERPBridge


def _db_path(tmp_path):
    dbp = tmp_path / "erp.db"
    conn = sqlite3.connect(dbp)
    conn.execute("CREATE TABLE clientes (id INTEGER PRIMARY KEY, nombre TEXT)")
    conn.execute("INSERT INTO clientes(id,nombre) VALUES (1,'Ana')")
    conn.commit()
    conn.close()
    return str(dbp)


def test_notify_pos_new_order_routes_scheduled_vs_immediate(tmp_path):
    bridge = ERPBridge(_db_path(tmp_path))

    calls = {"scheduled": 0, "immediate": 0}

    class DummyNotifier:
        def __init__(self, _db):
            pass

        def notify_scheduled_whatsapp_order(self, **kwargs):
            calls["scheduled"] += 1

        def notify_new_whatsapp_order(self, **kwargs):
            calls["immediate"] += 1

    with patch("erp.pos_notifier.POSNotifier", DummyNotifier):
        bridge._notify_pos_new_order(
            venta_id=1, folio="WA-1", total=100,
            cliente_id=1, sucursal_id=1, tipo_entrega="domicilio",
            direccion="Calle", items=[], fecha_entrega="2026-06-01 10:00:00"
        )
        bridge._notify_pos_new_order(
            venta_id=2, folio="WA-2", total=120,
            cliente_id=1, sucursal_id=1, tipo_entrega="domicilio",
            direccion="Calle", items=[], fecha_entrega=""
        )

    assert calls["scheduled"] == 1
    assert calls["immediate"] == 1


def test_notify_pos_new_order_also_calls_desktop_notification_service(tmp_path):
    bridge = ERPBridge(_db_path(tmp_path))

    calls = {"new": 0, "scheduled": 0}

    class DummyNotifier:
        def __init__(self, _db):
            pass

        def notify_scheduled_whatsapp_order(self, **kwargs):
            pass

        def notify_new_whatsapp_order(self, **kwargs):
            pass

    class DummyDesktopSvc:
        def __init__(self, _db):
            pass

        def notify_new_order(self, **kwargs):
            calls["new"] += 1
            return True

        def notify_scheduled_order(self, **kwargs):
            calls["scheduled"] += 1
            return True

    with patch("erp.pos_notifier.POSNotifier", DummyNotifier), \
         patch("core.services.desktop_notification_service.DesktopNotificationService", DummyDesktopSvc):
        bridge._notify_pos_new_order(
            venta_id=10, folio="WA-10", total=100,
            cliente_id=1, sucursal_id=1, tipo_entrega="domicilio",
            direccion="Calle", items=[], fecha_entrega=""
        )
        bridge._notify_pos_new_order(
            venta_id=11, folio="WA-11", total=120,
            cliente_id=1, sucursal_id=1, tipo_entrega="domicilio",
            direccion="Calle", items=[], fecha_entrega="2026-06-01 10:00:00"
        )

    assert calls["new"] == 1
    assert calls["scheduled"] == 1
