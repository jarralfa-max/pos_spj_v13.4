"""Ayudante de pruebas para el corte SUP-6 de proveedores.

Muchas pruebas de Compras y Logística siembran la tabla heredada `proveedores`
porque era de donde leía Compras. Desde el corte, Compras lee el maestro
canónico `supplier_master`.

Estas pruebas NO se reescriben para sembrar el maestro a mano: siguen sembrando
lo heredado y luego **pasan por la migración 263**, que es exactamente lo que le
ocurrirá a una instalación real. Así cada una de ellas prueba, además de lo suyo,
que el corte no rompe lo que ya funcionaba — que es la pregunta que de verdad
importa en una migración de datos.

Sembrar el maestro directamente habría sido más corto y habría dejado la
migración sin probar en ninguno de estos escenarios.
"""

from __future__ import annotations

import importlib

from backend.infrastructure.db.schema.supplier_schema import create_supplier_schema

_263 = importlib.import_module("migrations.standalone.263_suppliers_legacy_into_master")


def apply_supplier_cutover(connection) -> None:
    """Crea el esquema canónico y copia lo heredado. Idempotente.

    Puede llamarse varias veces sobre la misma conexión: las pruebas que
    insertan proveedores después del fixture vuelven a llamarla, y la 263 se
    salta los que ya están en el maestro.
    """
    create_supplier_schema(connection)
    _263.run(connection)
