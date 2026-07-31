"""P0-03 guardrail — la unidad base es un UUID de catálogo, no texto libre.

- El formulario de producto usa un selector de catálogo con búsqueda
  (`SearchableComboBox`, §7.1/§20) para la unidad base y NO un `QLineEdit` de
  texto ni una lista `QComboBox` larga sin búsqueda.
- El caso de uso de alta/edición del maestro valida que `base_unit_id` exista en el
  catálogo (`unit_exists`) antes de persistir.
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_FORM = _ROOT / "frontend/desktop/modules/products/dialogs/product_form_dialog.py"
_USE_CASES = _ROOT / "backend/application/products/use_cases/product_master_use_cases.py"


def test_form_unit_is_a_catalog_selector():
    src = _FORM.read_text(encoding="utf-8")
    # §7.1/§20: catálogo con búsqueda + placeholder, no texto libre ni lista larga.
    assert "self.base_unit = SearchableComboBox(" in src
    # el valor guardado es el UUID del catálogo (via helper placeholder-safe)
    assert "_combo_value(self.base_unit)" in src
    # no debe leerse la unidad como texto libre
    assert "self.base_unit.text()" not in src


def test_use_case_validates_unit_exists():
    src = _USE_CASES.read_text(encoding="utf-8")
    assert "unit_exists(command.base_unit_id)" in src
