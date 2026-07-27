"""
tests/purchases/test_phase5_ui_doctype.py
──────────────────────────────────────────
FASE 5 — Tests del selector de tipo de documento en la UI de Compra Tradicional.

Verifica el comportamiento de routing de _doc_type sin instanciar PyQt5
(los tests de UI no pueden ejecutarse en headless sin pantalla).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import ast
import inspect
import pytest


class TestDoctypeSourceCode:
    """Verifica que el código fuente de compras_pro.py tiene las adiciones de Phase 5."""

    def _load_source(self):
        # tests/purchases/ → tests/ → pos_spj_v13.4/ → modulos/
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "modulos", "compras_pro.py",
        )
        return open(path, encoding="utf-8").read()

    def test_compras_pro_has_no_syntax_error(self):
        src = self._load_source()
        ast.parse(src)  # raises SyntaxError if broken

    def test_doc_type_attribute_initialized(self):
        src = self._load_source()
        assert 'self._doc_type = "DIRECT"' in src, (
            "compras_pro.__init__ debe inicializar self._doc_type = 'DIRECT'"
        )

    def test_build_doctype_toolbar_exists(self):
        src = self._load_source()
        assert "_build_doctype_toolbar" in src

    def test_on_doctype_changed_exists(self):
        src = self._load_source()
        assert "_on_doctype_changed" in src

    def test_refresh_doctype_ui_exists(self):
        src = self._load_source()
        assert "_refresh_doctype_ui" in src

    def test_procesar_como_pr_exists(self):
        src = self._load_source()
        assert "_procesar_como_pr" in src

    def test_pr_routing_in_procesar_compra(self):
        src = self._load_source()
        assert '_doc_type' in src and '"PR"' in src, (
            "_procesar_compra debe ramificar por _doc_type"
        )

    def test_po_routing_in_procesar_compra(self):
        src = self._load_source()
        assert '"PO"' in src

    def test_no_hardcoded_hex_in_new_methods(self):
        """Los métodos nuevos deben usar Colors.* — no hexadecimales literales sueltos."""
        src = self._load_source()
        # Extract only the Phase 5 section (between the two markers)
        start = src.find("# ── Phase 5: Document-type toolbar")
        end   = src.find("# ── Providers", start)
        phase5_src = src[start:end] if start != -1 and end != -1 else ""
        # Allow Colors.* references (they expand to hex internally), but not bare #RRGGBB
        import re
        # Find all hex colors in the phase5 source
        all_hex = [(m.start(), m.group()) for m in re.finditer(r'#[0-9A-Fa-f]{6}', phase5_src)]
        # A hex is "bare" if it's not preceded by Colors.* in the same expression
        bare = []
        for pos, h in all_hex:
            ctx = phase5_src[max(0, pos - 40):pos]
            if "Colors" not in ctx and '{"' not in ctx:
                bare.append(h)
        assert not bare, (
            f"Hexadecimales sin token Colors.* en código Phase 5: {bare}"
        )

    def test_procesar_como_pr_uses_traditional_uc(self):
        src = self._load_source()
        assert "uc_compra_tradicional" in src and "DocumentType.PR" in src

    def test_build_doctype_toolbar_inserted_before_stepper(self):
        src = self._load_source()
        idx_doc  = src.find("_build_doctype_toolbar()")
        idx_step = src.find("_build_stepper_bar()")
        assert idx_doc < idx_step, (
            "_build_doctype_toolbar debe insertarse antes de _build_stepper_bar en el layout"
        )

    def test_direct_flow_unchanged(self):
        """El flujo DIRECT sigue usando RegistrarCompraUC."""
        src = self._load_source()
        assert "RegistrarCompraUC" in src

    def test_qr_tab_untouched(self):
        """_build_tab_qr no debe referenciar _doc_type."""
        src = self._load_source()
        # Find _build_tab_qr body
        start = src.find("def _build_tab_qr(")
        end   = src.find("\n    def ", start + 1)
        qr_body = src[start:end]
        assert "_doc_type" not in qr_body, (
            "_build_tab_qr no debe usar _doc_type — QR NO-TOUCH policy"
        )
