import re

from .allowlists import ENTITY_COMBO_MASS_LOADING_ALLOWLIST
from .architecture_guardrails import QCOMBOBOX_RE, UI_ROOTS, assert_no_new_violations, collect_regex_violations, has_entity_term

#: `has_entity_term` busca la palabra como subcadena, asi que `product_type` o
#: `recipe_type` cuentan como "producto"/"receta". Pero un selector de TIPO no
#: es un catalogo de entidades: se llena desde un enum fijo de tres o cuatro
#: valores, no desde la base. Esta regla existe contra cargar miles de
#: entidades en un desplegable, y los catalogos de verdad de esas mismas
#: pantallas (unidades, categorias, marcas) ya usan `SearchableComboBox`.
#:
#: El codigo lo dice explicitamente donde saltaba:
#:     # El tipo es un enum fijo -> QComboBox es aceptable (no es un catalogo grande).
_TYPE_SELECTOR_RE = re.compile(r"\w+_(?:type|tipo|kind|clase)")


def test_no_qcombobox_mass_loading_for_entities() -> None:
    violations = collect_regex_violations(
        pattern=QCOMBOBOX_RE,
        roots=UI_ROOTS,
        line_filter=lambda _path, _number, line: (
            has_entity_term(line) and not _TYPE_SELECTOR_RE.search(line)),
    )
    assert_no_new_violations("QComboBox mass entity loading", violations, ENTITY_COMBO_MASS_LOADING_ALLOWLIST)
