"""SDLC-ORD-003 — el pipeline autoritativo de pedidos es `customer_orders`.

Decisión registrada en `docs/sdlc/items/SDLC-ORD-003/decision.md`. Mientras se
hace el corte, ningún código nuevo del ERP puede leer ni escribir la tabla
legacy `delivery_orders` ni el estado `pendiente_wa`. Esta lista sólo encoge:
quien retire un lector, lo quita de aquí.
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

_SQL_LEGACY = re.compile(r"(FROM|INTO|UPDATE|JOIN)\s+delivery_orders\b|['\"]pendiente_wa['\"]",
                         re.IGNORECASE)

#: Lectores y escritores legacy medidos el 2026-11-06. Sólo puede encoger.
PERMITIDOS = frozenset({
    "backend/application/customers/queries/customer_delivery_summary_query.py",
    "backend/application/queries/driver_settlement_query_service.py",
    "backend/application/use_cases/settle_delivery_driver_use_case.py",
})


def _usuarios_legacy() -> set[str]:
    encontrados = set()
    for base in ("backend", "frontend"):
        for archivo in (RAIZ / base).rglob("*.py"):
            texto = archivo.read_text(encoding="utf-8", errors="ignore")
            if _SQL_LEGACY.search(texto):
                encontrados.add(archivo.relative_to(RAIZ).as_posix())
    return encontrados


def test_ningun_lector_nuevo_del_pipeline_legacy():
    nuevos = _usuarios_legacy() - PERMITIDOS
    assert not nuevos, (
        f"{sorted(nuevos)} usa delivery_orders/pendiente_wa: los pedidos viven en "
        "customer_orders (SDLC-ORD-003)")


def test_la_lista_solo_encoge():
    sobrantes = PERMITIDOS - _usuarios_legacy()
    assert not sobrantes, f"{sorted(sobrantes)} ya no usa lo legacy: quítalo de PERMITIDOS"
