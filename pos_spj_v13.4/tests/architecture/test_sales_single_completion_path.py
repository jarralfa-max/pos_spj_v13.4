"""Guardas de la auditoría de Ventas cebf67a (2026-10-15).

* V07 — una sola ruta para completar una venta: `CheckoutSaleUseCase`. Había
  un `CompleteSaleUseCase` que completaba con sólo el total (sin inventario,
  Caja, folio ni costo); se eliminó y no debe volver.
* V05 — ningún caso de uso de Ventas carga una venta por id sin pasar por el
  alcance de sucursal (`_SalesBaseUseCase._load_sale`).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SALES_APP = ROOT / "backend" / "application" / "sales"


def _sources():
    for path in SALES_APP.rglob("*.py"):
        yield path, path.read_text(encoding="utf-8")


def test_only_the_canonical_checkout_completes_a_sale():
    offenders = []
    for path, text in _sources():
        if re.search(r"^class CompleteSaleUseCase\b", text, re.M):
            offenders.append(f"{path.relative_to(ROOT)} define CompleteSaleUseCase")
        if re.search(r"\bsale\.complete\(\)", text) and path.name != "checkout_use_cases.py":
            offenders.append(f"{path.relative_to(ROOT)} llama sale.complete()")
    assert not offenders, offenders


def test_use_cases_load_sales_only_through_the_branch_scoped_loader():
    allowed = {"_base.py", "receipt_use_cases.py"}   # el cargador y el del ticket (con alcance)
    offenders = [
        str(path.relative_to(ROOT)) for path, text in _sources()
        if path.parent.name == "use_cases" and path.name not in allowed
        and "uow.sales.get(" in text
    ]
    assert not offenders, offenders


def test_the_receipt_loader_checks_the_branch():
    text = (SALES_APP / "use_cases" / "receipt_use_cases.py").read_text(encoding="utf-8")
    assert "require_branch(" in text
