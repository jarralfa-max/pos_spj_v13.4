from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SALES_UI = ROOT / "modulos/ventas.py"


def test_sales_manual_quantity_dialogs_default_to_zero() -> None:
    content = SALES_UI.read_text(encoding="utf-8")
    # Sin defaults arbitrarios distintos de cero (Regla 22/23).
    assert "value=0.500" not in content
    assert "value=0.100" not in content
    assert "value=1.0" not in content
    # Las capturas de cantidad/peso migraron al componente estándar de teclado
    # numérico, que inicia en 0/vacío por diseño (más fuerte que value=0.0) y
    # cumple SPJ_REFACTOR_SKILL FASE 3. Ya no debe quedar QInputDialog.getDouble.
    assert "QInputDialog.getDouble" not in content, (
        "ventas.py no debe usar QInputDialog.getDouble; usa QuantityInputDialog/"
        "NumericKeypadDialog (teclado numérico estándar)."
    )
    assert (
        "QuantityInputDialog.get_quantity" in content
        or "NumericKeypadDialog.get_value" in content
    ), "ventas.py debe capturar cantidades con el teclado numérico estándar."
