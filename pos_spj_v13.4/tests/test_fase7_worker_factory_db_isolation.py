from pathlib import Path

import pytest

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


def test_worker_factory_disabled_or_removed():
    f = SaleCheckoutWorkerFactory(_Container(object()))
    with pytest.raises(RuntimeError, match="deshabilitado"):
        f.build(_uc(object()), [], {}, 1, "u")


def test_modulo_ventas_does_not_use_worker_factory_for_sale_transaction():
    repo_root = Path(__file__).resolve().parents[1]
    src = (repo_root / "modulos" / "ventas.py").read_text(encoding="utf-8")
    assert "self._sale_checkout_worker_factory.build(" not in src
    assert "SaleCheckoutWorkerFactory" not in src
    assert "result = _uc.ejecutar(_items_uc, _dp, self.sucursal_id, usuario)" in src


def test_sale_does_not_use_shallow_cloned_worker():
    repo_root = Path(__file__).resolve().parents[1]
    factory_src = (repo_root / "presentation" / "sales" / "workers" / "sale_checkout_worker_factory.py").read_text(encoding="utf-8")
    assert "copy.copy" not in factory_src
    assert "_clone_uc" not in factory_src
    assert "deshabilitado" in factory_src


def test_sale_checkout_factory_disabled_or_removed():
    with pytest.raises(RuntimeError, match="deshabilitado"):
        SaleCheckoutWorkerFactory(_Container(object())).build(_uc(object()), [], {}, 1, "u")


def test_sale_transaction_uses_single_db_connection():
    repo_root = Path(__file__).resolve().parents[1]
    src = (repo_root / "modulos" / "ventas.py").read_text(encoding="utf-8")
    fn = src.split("def finalizar_venta", 1)[1].split("def _on_checkout_success", 1)[0]
    assert "moveToThread" not in fn
    assert "QThread" not in fn
    assert "result = _uc.ejecutar(_items_uc, _dp, self.sucursal_id, usuario)" in fn


def test_printing_still_async_after_sale():
    repo_root = Path(__file__).resolve().parents[1]
    src = (repo_root / "modulos" / "ventas.py").read_text(encoding="utf-8")
    pdf_fn = src.split("def _guardar_ticket_pdf_async", 1)[1].split("def generar_html_ticket", 1)[0]
    assert "TicketOutputWorker" in pdf_fn
    assert "moveToThread" in pdf_fn
