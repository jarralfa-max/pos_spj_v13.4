import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SALES_UI = ROOT / "modulos/ventas.py"
FORBIDDEN = {
    "hardware_config": re.compile(r"\bself\.conexion\.execute\([^\n]*\n?\s*['\"]SELECT[^\n]+hardware_config", re.IGNORECASE),
    "customer_insert": re.compile(r"INSERT\s+INTO\s+clientes", re.IGNORECASE),
    "loyalty_card_insert": re.compile(r"INSERT\s+OR\s+IGNORE\s+INTO\s+tarjetas_fidelidad", re.IGNORECASE),
    "ticket_config": re.compile(r"SELECT\s+valor\s+FROM\s+configuraciones", re.IGNORECASE),
}


def test_sales_no_direct_sql_for_catalog_hardware_customer_ticket() -> None:
    content = SALES_UI.read_text(encoding="utf-8")
    violations = [name for name, pattern in FORBIDDEN.items() if pattern.search(content)]
    assert violations == []
