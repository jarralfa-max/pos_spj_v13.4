"""
tests/purchases/test_fase6_doctype_ui.py
─────────────────────────────────────────
FASE 6 — Separar rutas doctypes (DIRECT / PR / PO).

Verifica (vía AST, sin instanciar PyQt5):
1. Doctype toolbar es visible en el centro (no oculto sin condición)
2. Stepper está en el layout del centro y su visibilidad depende del doc type
3. _refresh_doctype_ui() maneja los 3 doc types completos
4. Botón tiene colores diferenciados por doc type
5. Hint text actualiza según doc type
6. _lbl_hint almacenado como atributo de instancia
7. _refresh_doctype_ui() se llama en _build_tab_tradicional()
8. _doctype_buttons resalta el tipo activo
9. _on_doctype_changed() llama _refresh_doctype_ui()

No instancia PyQt5.
"""
from __future__ import annotations

import ast
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _source() -> str:
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return open(os.path.join(base, "modulos", "compras_pro.py"), encoding="utf-8").read()


def _method_src(method_name: str) -> str | None:
    src = _source()
    tree = ast.parse(src)
    lines = src.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "ModuloComprasPro":
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == method_name:
                    return "\n".join(lines[item.lineno - 1:item.end_lineno])
    return None


# ── 1. Doctype toolbar visible in center column ───────────────────────────────

class TestDoctypeToolbarVisible:
    """Doctype toolbar deve estar en el layout del centro (FASE 6 — visible)."""

    def test_toolbar_built_in_center_column(self):
        src = _method_src("_build_center_column")
        assert src is not None
        assert "_hidden_doctype_toolbar = self._build_doctype_toolbar()" in src

    def test_toolbar_added_to_layout(self):
        src = _method_src("_build_center_column")
        assert src is not None
        assert "lay.addWidget(self._hidden_doctype_toolbar)" in src, (
            "FASE 6: doctype toolbar debe añadirse al layout del centro para ser visible."
        )

    def test_toolbar_not_unconditionally_hidden(self):
        """No debe haber .hide() justo después de construir el toolbar."""
        src = _method_src("_build_center_column")
        assert src is not None
        idx = src.find("_hidden_doctype_toolbar = self._build_doctype_toolbar()")
        assert idx != -1
        # Check the 120 chars after the assignment — no .hide() should appear
        block = src[idx:idx + 120]
        assert "_hidden_doctype_toolbar.hide()" not in block, (
            "FASE 6: doctype toolbar no debe ocultarse después de construirse. "
            "La visibilidad la controla _refresh_doctype_ui()."
        )


# ── 2. Stepper in center column layout ───────────────────────────────────────

class TestStepperInCenterColumn:
    """El stepper está en el layout del centro y su visibilidad depende del doc type."""

    def test_stepper_built_in_center_column(self):
        src = _method_src("_build_center_column")
        assert src is not None
        assert "_hidden_stepper = self._build_stepper_bar()" in src

    def test_stepper_added_to_layout(self):
        src = _method_src("_build_center_column")
        assert src is not None
        assert "lay.addWidget(self._hidden_stepper)" in src, (
            "FASE 6: stepper debe añadirse al layout del centro."
        )

    def test_stepper_hidden_initially(self):
        """Stepper empieza oculto (doc type inicial es DIRECT — sin stepper)."""
        src = _method_src("_build_center_column")
        assert src is not None
        idx = src.find("_hidden_stepper = self._build_stepper_bar()")
        assert idx != -1
        block = src[idx:idx + 120]
        assert "_hidden_stepper.hide()" in block, (
            "Stepper debe iniciarse oculto. _refresh_doctype_ui() lo muestra para PR/PO."
        )

    def test_refresh_doctype_ui_controls_stepper_visibility(self):
        src = _method_src("_refresh_doctype_ui")
        assert src is not None
        assert "_hidden_stepper" in src, (
            "_refresh_doctype_ui debe controlar la visibilidad del stepper."
        )
        assert "setVisible" in src or ".show()" in src or ".hide()" in src


# ── 3. _refresh_doctype_ui handles all 3 doc types ───────────────────────────

class TestRefreshDoctypeUICompleteness:
    """_refresh_doctype_ui() tiene configuración para los 3 tipos de documento."""

    def _src(self):
        return _method_src("_refresh_doctype_ui")

    def test_method_exists(self):
        assert self._src() is not None

    def test_direct_config_present(self):
        assert '"DIRECT"' in self._src() or "'DIRECT'" in self._src()

    def test_pr_config_present(self):
        assert '"PR"' in self._src() or "'PR'" in self._src()

    def test_po_config_present(self):
        assert '"PO"' in self._src() or "'PO'" in self._src()

    def test_handles_unknown_doc_type_with_fallback(self):
        """_cfg.get() debe tener fallback al tipo DIRECT."""
        src = self._src()
        assert '_cfg["DIRECT"]' in src or "_cfg['DIRECT']" in src, (
            "_refresh_doctype_ui debe tener fallback a DIRECT para tipos desconocidos."
        )


# ── 4. Button colors per doc type ─────────────────────────────────────────────

class TestButtonColorPerDoctype:
    """El botón de acción tiene color diferenciado por doc type."""

    def _src(self):
        return _method_src("_refresh_doctype_ui")

    def test_success_color_for_direct(self):
        """DIRECT → SUCCESS_BASE (verde)."""
        src = self._src()
        assert "SUCCESS_BASE" in src, (
            "_refresh_doctype_ui debe usar Colors.SUCCESS_BASE para DIRECT."
        )

    def test_primary_color_for_pr(self):
        """PR → PRIMARY_BASE (azul)."""
        src = self._src()
        assert "PRIMARY_BASE" in src, (
            "_refresh_doctype_ui debe usar Colors.PRIMARY_BASE para PR."
        )

    def test_warning_color_for_po(self):
        """PO → WARNING_BASE (ámbar)."""
        src = self._src()
        assert "WARNING_BASE" in src, (
            "_refresh_doctype_ui debe usar Colors.WARNING_BASE para PO."
        )

    def test_btn_autorizar_style_updated(self):
        """_btn_autorizar debe recibir setStyleSheet en _refresh_doctype_ui."""
        src = self._src()
        assert "_btn_autorizar" in src
        assert "setStyleSheet" in src, (
            "_refresh_doctype_ui debe actualizar el estilo de _btn_autorizar."
        )

    def test_btn_autorizar_text_updated_per_doctype(self):
        """El texto del botón cambia: Autorizar / Crear solicitud / Ver instrucciones."""
        src = self._src()
        assert "Autorizar" in src or "Autorizar compra" in src
        assert "Crear solicitud" in src
        assert "instrucciones" in src or "Ver instrucciones" in src


# ── 5. Stepper visibility config per doc type ────────────────────────────────

class TestStepperVisibilityConfig:
    """El config de _refresh_doctype_ui define show_stepper correctamente."""

    def _src(self):
        return _method_src("_refresh_doctype_ui")

    def test_stepper_visible_for_pr(self):
        """PR debe tener show_stepper = True en el config."""
        src = self._src()
        # Config for PR must come before True for show_stepper
        pr_idx = src.find('"PR"')
        if pr_idx == -1:
            pr_idx = src.find("'PR'")
        po_idx = src.find('"PO"')
        if po_idx == -1:
            po_idx = src.find("'PO'")
        # Between PR and PO, there must be a True for show_stepper
        pr_section = src[pr_idx:po_idx] if po_idx > pr_idx else src[pr_idx:pr_idx + 300]
        assert "True" in pr_section, (
            "Config de PR debe incluir show_stepper=True."
        )

    def test_stepper_hidden_for_direct(self):
        """DIRECT debe tener show_stepper = False en el config."""
        src = self._src()
        direct_idx = src.find('"DIRECT"')
        if direct_idx == -1:
            direct_idx = src.find("'DIRECT'")
        pr_idx = src.find('"PR"')
        if pr_idx == -1:
            pr_idx = src.find("'PR'")
        direct_section = src[direct_idx:pr_idx] if pr_idx > direct_idx else src[direct_idx:direct_idx + 300]
        assert "False" in direct_section, (
            "Config de DIRECT debe incluir show_stepper=False."
        )


# ── 6. _lbl_hint stored as instance attr ─────────────────────────────────────

class TestHintLabelAsAttr:
    """_lbl_hint debe guardarse como atributo para que _refresh_doctype_ui lo actualice."""

    def test_lbl_hint_stored_in_build_dynamic_action_button(self):
        src = _method_src("_build_dynamic_action_button")
        assert src is not None
        assert "self._lbl_hint" in src, (
            "_lbl_hint debe guardarse como self._lbl_hint (no variable local) "
            "para que _refresh_doctype_ui() pueda actualizar el texto."
        )

    def test_lbl_hint_added_to_layout(self):
        src = _method_src("_build_dynamic_action_button")
        assert src is not None
        assert "lay.addWidget(self._lbl_hint)" in src

    def test_refresh_doctype_ui_updates_hint(self):
        src = _method_src("_refresh_doctype_ui")
        assert src is not None
        assert "_lbl_hint" in src, (
            "_refresh_doctype_ui debe actualizar el texto de _lbl_hint."
        )
        assert ".setText(" in src


# ── 7. _refresh_doctype_ui called in _build_tab_tradicional ──────────────────

class TestRefreshCalledOnBuild:
    """_refresh_doctype_ui() debe llamarse en _build_tab_tradicional()
    para aplicar el estado inicial después de construir todos los paneles."""

    def test_refresh_doctype_ui_called_in_build_tab_tradicional(self):
        src = _method_src("_build_tab_tradicional")
        assert src is not None
        assert "_refresh_doctype_ui()" in src, (
            "_build_tab_tradicional debe llamar _refresh_doctype_ui() "
            "después de construir todos los paneles (centro + derecha) "
            "para aplicar el estado inicial del tipo de documento."
        )

    def test_refresh_called_after_summary_panel(self):
        """El refresh debe llamarse DESPUÉS de _build_summary_panel() para que
        _btn_autorizar exista cuando se actualiza el estilo."""
        src = _method_src("_build_tab_tradicional")
        assert src is not None
        summary_idx = src.find("_build_summary_panel()")
        refresh_idx = src.find("_refresh_doctype_ui()")
        assert refresh_idx > summary_idx, (
            "_refresh_doctype_ui() debe llamarse DESPUÉS de _build_summary_panel() "
            "para que _btn_autorizar ya exista al actualizar el estilo."
        )


# ── 8. _doctype_buttons highlights active type ───────────────────────────────

class TestDoctypeButtonsHighlight:
    """_doctype_buttons resalta el tipo activo con _apply_doctype_button_styles()."""

    def test_apply_doctype_button_styles_exists(self):
        src = _method_src("_apply_doctype_button_styles")
        assert src is not None

    def test_active_button_has_primary_bg(self):
        """El botón activo usa PRIMARY_BASE como fondo."""
        src = _method_src("_apply_doctype_button_styles")
        assert "PRIMARY_BASE" in src, (
            "_apply_doctype_button_styles debe usar Colors.PRIMARY_BASE para el botón activo."
        )

    def test_idle_button_has_slate_bg(self):
        """Los botones inactivos usan SLATE_100 como fondo."""
        src = _method_src("_apply_doctype_button_styles")
        assert "SLATE_100" in src, (
            "_apply_doctype_button_styles debe usar Colors.NEUTRAL.SLATE_100 para botones inactivos."
        )

    def test_on_doctype_changed_calls_refresh(self):
        """_on_doctype_changed() debe llamar _refresh_doctype_ui()."""
        src = _method_src("_on_doctype_changed")
        assert src is not None
        assert "_refresh_doctype_ui()" in src, (
            "_on_doctype_changed debe llamar _refresh_doctype_ui() al cambiar el tipo."
        )

    def test_on_doctype_changed_updates_doc_type_attr(self):
        src = _method_src("_on_doctype_changed")
        assert src is not None
        assert "self._doc_type" in src

    def test_on_doctype_changed_updates_checked_state(self):
        src = _method_src("_on_doctype_changed")
        assert src is not None
        assert "setChecked" in src


# ── 9. No banned colors in new/modified methods ───────────────────────────────

class TestNoBannedColorsInFase6Methods:
    """Las modificaciones de FASE 6 no introducen colores hardcodeados prohibidos."""

    @pytest.mark.parametrize("method_name", [
        "_refresh_doctype_ui",
        "_build_center_column",
        "_build_dynamic_action_button",
        "_on_doctype_changed",
        "_apply_doctype_button_styles",
        "_build_tab_tradicional",
    ])
    def test_no_background_white(self, method_name: str):
        import re
        src = _method_src(method_name)
        if src is None:
            pytest.skip(f"{method_name} not found")
        offenses = [
            l.strip() for l in src.splitlines()
            if re.search(r'background\s*:\s*white\b', l, re.IGNORECASE)
        ]
        assert not offenses, f"background:white en {method_name}: {offenses}"

    @pytest.mark.parametrize("method_name", [
        "_refresh_doctype_ui",
        "_build_center_column",
        "_build_dynamic_action_button",
        "_on_doctype_changed",
        "_apply_doctype_button_styles",
        "_build_tab_tradicional",
    ])
    def test_no_slate50_as_background(self, method_name: str):
        import re
        src = _method_src(method_name)
        if src is None:
            pytest.skip(f"{method_name} not found")
        offenses = []
        for line in src.splitlines():
            stripped = line.strip()
            if not re.search(r'\bSLATE_50\b', stripped):
                continue
            if "background" not in stripped:
                continue
            if "background:transparent" in stripped or "background: transparent" in stripped:
                continue
            offenses.append(stripped)
        assert not offenses, f"SLATE_50 como background en {method_name}: {offenses}"
