"""CRM-1 (§79, "Consumir exclusivamente frontend/desktop/design_system/...")

The CRM UI must not fall back to the legacy widget vocabulary
(``modulos.ui_components``, ``modulos.design_tokens``) or raw PyQt widgets
that the canonical design system replaces (``QTableWidget``, styled
``QGroupBox``, ``QFrame``-as-card, ``QTabWidget`` for primary navigation,
``QDoubleSpinBox`` for money). Mirrors
``test_transfers_ui_uses_design_system.py`` and
``test_losses_sidebar_navigation.py`` for their own modules.
"""

from __future__ import annotations

from .customers_crm_guardrails import CRM_UI_ROOT, crm_source_text, relative

_FORBIDDEN_LEGACY_IMPORTS = ("modulos.ui_components", "modulos.design_tokens", "modulos.spj_styles")
_FORBIDDEN_RAW_WIDGETS = ("QTableWidget", "QGroupBox", "QDoubleSpinBox", "QTabWidget")


def test_customers_crm_ui_does_not_use_legacy_component_libraries():
    source = crm_source_text((CRM_UI_ROOT,))
    offenders = [tok for tok in _FORBIDDEN_LEGACY_IMPORTS if tok in source]
    assert not offenders, (
        f"{relative(CRM_UI_ROOT)} imports legacy component modules — use "
        f"frontend/desktop/components/ instead: {offenders}"
    )


def test_customers_crm_ui_does_not_use_raw_pyqt_widgets_with_canonical_equivalents():
    source = crm_source_text((CRM_UI_ROOT,))
    offenders = [tok for tok in _FORBIDDEN_RAW_WIDGETS if tok in source]
    assert not offenders, (
        f"{relative(CRM_UI_ROOT)} instantiates raw PyQt widgets that have a "
        f"canonical replacement (StandardTable V2 / StandardCard / MoneyInput / "
        f"ModuleSidebar+PageState): {offenders}"
    )
