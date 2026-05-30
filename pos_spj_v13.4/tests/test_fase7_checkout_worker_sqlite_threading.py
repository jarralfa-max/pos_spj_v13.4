from pathlib import Path

import pytest

from presentation.sales.workers.sale_checkout_worker import SaleCheckoutWorker


class _UCOK:
    def ejecutar(self, *args, **kwargs):
        return {"ok": True}


def test_checkout_worker_blocked_before_any_sqlite_thread_use():
    with pytest.raises(RuntimeError, match="deshabilitado"):
        SaleCheckoutWorker(_UCOK(), [], {}, 1, "u")


def test_checkout_worker_source_has_no_sqlite_thread_execution_path():
    repo_root = Path(__file__).resolve().parents[1]
    src = (repo_root / "presentation" / "sales" / "workers" / "sale_checkout_worker.py").read_text(encoding="utf-8")
    assert "SQLite thread error in checkout worker" not in src
    assert "self._uc_venta.ejecutar" not in src
    assert "raise RuntimeError(_DISABLED_MESSAGE)" in src
