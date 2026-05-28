import sqlite3
from pathlib import Path

from core.use_cases.venta import ProcesarVentaUC
from presentation.sales.workers.sale_checkout_worker_factory import SaleCheckoutWorkerFactory


class _Svc:
    def __init__(self, db):
        self.db = db


def _uc(db):
    return ProcesarVentaUC(_Svc(db), _Svc(db), _Svc(db), _Svc(db), None)


class _Container:
    def __init__(self, db):
        self.db = db


def test_worker_factory_creates_dedicated_db_connection(tmp_path):
    dbp = tmp_path / "t.db"
    db = sqlite3.connect(str(dbp), check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE IF NOT EXISTS x(id INTEGER)")
    c = _Container(db)
    f = SaleCheckoutWorkerFactory(c)
    w = f.build(_uc(db), [], {}, 1, "u")
    ucw = w._uc_venta
    assert getattr(ucw, "_sales").db is not db


def test_modulo_ventas_uses_worker_factory():
    src = Path("pos_spj_v13.4/modulos/ventas.py").read_text(encoding="utf-8")
    assert "SaleCheckoutWorkerFactory" in src
    assert "self._sale_checkout_worker_factory.build(" in src
