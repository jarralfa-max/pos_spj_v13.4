"""§7/§26 — Procesamiento no escribe tablas de Inventario. Reserva, descuenta,
recibe y liga lotes por los CASOS DE USO de Inventario (sus adaptadores), nunca
con SQL propio sobre `inventory_*`, `storage_locations` o `stock_*`."""
import re

from tests.architecture._meat_processing_code import code_strings, production_files, rel

ESCRIBE = re.compile(
    r"\b(INSERT\s+(OR\s+\w+\s+)?INTO|UPDATE|DELETE\s+FROM|REPLACE\s+INTO)\s+"
    r"(inventory_\w+|storage_locations|stock_\w+|warehouses)\b", re.I)


def test_processing_never_writes_inventory_tables():
    fugas = [(rel(p), linea, s[:80]) for p in production_files()
             for linea, s in code_strings(p) if ESCRIBE.search(s)]
    assert fugas == []
