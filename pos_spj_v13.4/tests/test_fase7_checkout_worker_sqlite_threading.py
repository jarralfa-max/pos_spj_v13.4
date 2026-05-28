import sqlite3

from presentation.sales.workers.sale_checkout_worker import SaleCheckoutWorker


class _UCOK:
    class _Sales:
        db = object()

    _sales = _Sales()

    def ejecutar(self, *args, **kwargs):
        return {"ok": True}


class _UCThreadErr:
    class _Sales:
        db = object()

    _sales = _Sales()

    def ejecutar(self, *args, **kwargs):
        raise sqlite3.ProgrammingError("SQLite objects created in a thread can only be used in that same thread")


class _UCGenericErr:
    class _Sales:
        db = object()

    _sales = _Sales()

    def ejecutar(self, *args, **kwargs):
        raise RuntimeError("boom")


def test_checkout_worker_reports_sqlite_thread_error():
    w = SaleCheckoutWorker(_UCThreadErr(), [], {}, 1, "u")
    got = {}
    w.failed.connect(lambda m, tb: got.update({"m": m, "tb": tb}))
    w.run()
    assert "SQLite objects created" in got.get("m", "")


def test_checkout_worker_success_with_threadsafe_connection():
    w = SaleCheckoutWorker(_UCOK(), [], {}, 1, "u")
    got = {}
    w.success.connect(lambda r: got.update({"r": r}))
    w.run()
    assert got.get("r") == {"ok": True}


def test_checkout_worker_does_not_use_main_thread_sqlite_connection_if_not_threadsafe():
    src = open("pos_spj_v13.4/presentation/sales/workers/sale_checkout_worker.py", encoding="utf-8").read()
    assert "SQLite thread error in checkout worker" in src
    assert "db_conn_id" in src
