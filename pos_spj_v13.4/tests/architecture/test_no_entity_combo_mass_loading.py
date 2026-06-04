from .allowlists import ENTITY_COMBO_MASS_LOADING_ALLOWLIST
from .architecture_guardrails import QCOMBOBOX_RE, UI_ROOTS, assert_no_new_violations, collect_regex_violations, has_entity_term


def test_no_qcombobox_mass_loading_for_entities() -> None:
    violations = collect_regex_violations(
        pattern=QCOMBOBOX_RE,
        roots=UI_ROOTS,
        line_filter=lambda _path, _number, line: has_entity_term(line),
    )
    assert_no_new_violations("QComboBox mass entity loading", violations, ENTITY_COMBO_MASS_LOADING_ALLOWLIST)
