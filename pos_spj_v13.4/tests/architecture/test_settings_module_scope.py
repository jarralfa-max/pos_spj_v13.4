from pathlib import Path

CONFIGURATION_MODULE = Path("pos_spj_v13.4/modulos/configuracion.py")

EXPECTED_TAB_LABELS = [
    "🏢 Empresa / Fiscal",
    "👤 Usuarios y Roles",
    "📧 Email / SMTP",
    "💳 Mercado Pago",
    "⏰ Happy Hour",
    "📅 Cierre Mensual",
]

REMOVED_GENERAL_TOKENS = [
    "tab_general",
    "crear_tab_general",
    "cargar_configuraciones_general",
    "guardar_impuesto",
    "guardar_seguridad",
    "spin_impuesto",
    "chk_requerir_admin",
    "⚙️ General",
]


def test_settings_module_scope_has_exact_canonical_tabs() -> None:
    content = CONFIGURATION_MODULE.read_text(encoding="utf-8")

    removed = [token for token in REMOVED_GENERAL_TOKENS if token in content]
    missing = [label for label in EXPECTED_TAB_LABELS if label not in content]

    assert "def _setup_tab_happy_hour" in content
    assert not removed, "General tab remnants: " + ", ".join(removed)
    assert not missing, "Missing canonical tabs: " + ", ".join(missing)
