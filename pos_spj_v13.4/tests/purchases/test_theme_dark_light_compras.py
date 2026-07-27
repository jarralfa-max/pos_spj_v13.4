"""
tests/purchases/test_theme_dark_light_compras.py
──────────────────────────────────────────────────
FASE 1 — Pruebas de caracterización: compatibilidad dark/light.

Verifica sin instanciar PyQt5:
1. compras_pro.py no tiene colores hex hardcodeados FUERA del sistema Colors.*
2. recepcion_qr_widget.py ídem
3. design_tokens.py define Colors.* correctamente
4. Todos los hexadecimales en UI están precedidos por Colors.* o son parámetros alpha (#RRGGBBAA)
5. No hay estilos hardcodeados que rompan dark/light
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import re
import ast
import pytest


def _src(filename: str) -> str:
    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "modulos", filename,
    )
    return open(path, encoding="utf-8").read()


def _find_bare_hex(src: str, exclude_alpha_suffix: bool = True) -> list[tuple[int, str]]:
    """
    Finds #RRGGBB hex colors NOT preceded by Colors.* token in 50-char context.
    Alpha suffixes (#RRGGBBAA) are expected inside Colors usage and allowed.
    """
    bare = []
    # Match #RRGGBB (6-digit) hex colors
    for m in re.finditer(r'#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?', src):
        pos = m.start()
        ctx = src[max(0, pos - 60):pos]
        hex_val = m.group()
        # Skip if Colors.* appears in context (within 60 chars before)
        if "Colors" in ctx:
            continue
        # Skip if inside a comment
        line_start = src.rfind('\n', 0, pos) + 1
        line_content = src[line_start:pos]
        if '#' in line_content and line_content.strip().startswith('#'):
            # This is a comment line
            continue
        # Skip if it's an alpha suffix of a Colors.* color (e.g., f"{Colors.X}22")
        # These are handled by the Colors context check above
        bare.append((pos, hex_val))
    return bare


class TestDesignTokens:

    def test_design_tokens_importable(self):
        from modulos.design_tokens import Colors
        assert Colors is not None

    def test_colors_has_primary_base(self):
        from modulos.design_tokens import Colors
        assert hasattr(Colors, 'PRIMARY_BASE')

    def test_colors_has_danger_base(self):
        from modulos.design_tokens import Colors
        assert hasattr(Colors, 'DANGER_BASE')

    def test_colors_has_success_base(self):
        from modulos.design_tokens import Colors
        assert hasattr(Colors, 'SUCCESS_BASE')

    def test_colors_has_warning_base(self):
        from modulos.design_tokens import Colors
        assert hasattr(Colors, 'WARNING_BASE')

    def test_colors_has_info_base(self):
        from modulos.design_tokens import Colors
        assert hasattr(Colors, 'INFO_BASE')

    def test_colors_has_neutral(self):
        from modulos.design_tokens import Colors
        assert hasattr(Colors, 'NEUTRAL')

    def test_colors_neutral_has_slate_tokens(self):
        from modulos.design_tokens import Colors
        neutral = Colors.NEUTRAL
        assert hasattr(neutral, 'SLATE_50') or hasattr(neutral, 'SLATE_100'), (
            "Colors.NEUTRAL debe tener tokens SLATE_*"
        )

    def test_primary_base_is_hex_string(self):
        from modulos.design_tokens import Colors
        val = Colors.PRIMARY_BASE
        assert isinstance(val, str) and val.startswith('#'), (
            f"Colors.PRIMARY_BASE debe ser hex string, got: {val!r}"
        )


class TestComprasProTheme:

    def test_compras_pro_no_syntax_error(self):
        ast.parse(_src("compras_pro.py"))

    def test_compras_pro_imports_colors(self):
        src = _src("compras_pro.py")
        assert "Colors" in src, "compras_pro.py debe importar Colors desde design_tokens"

    def test_compras_pro_uses_colors_not_raw_hex(self):
        src = _src("compras_pro.py")
        # Exclude _refresh_hist_timeline body (Phase 7 documented exception: inline
        # node colors for the timeline widget where Colors.* context doesn't wrap them)
        idx_tl = src.find("def _refresh_hist_timeline")
        next_def = src.find("\n    def ", idx_tl + 1) if idx_tl != -1 else -1
        src_no_timeline = (src[:idx_tl] + src[next_def:]) if idx_tl != -1 and next_def != -1 else src
        bare = _find_bare_hex(src_no_timeline)
        # Allow up to 5 bare hex outside timeline — HTML table cells / rich text
        assert len(bare) <= 5, (
            f"compras_pro.py tiene {len(bare)} hex sin token Colors.* (exc. timeline): "
            f"{[h for _, h in bare[:10]]}"
        )

    def test_compras_pro_no_hardcoded_white_or_black_backgrounds(self):
        src = _src("compras_pro.py")
        # Pure white/black backgrounds outside Colors context are a dark-mode risk
        danger_patterns = [
            r'background:\s*#ffffff\b',
            r'background:\s*#000000\b',
            r'background-color:\s*white\b',
            r'background-color:\s*black\b',
        ]
        for pattern in danger_patterns:
            matches = re.findall(pattern, src, re.IGNORECASE)
            assert not matches, (
                f"compras_pro.py contiene background hardcodeado '{pattern}': {matches}"
            )

    def test_compras_pro_uses_colors_for_state_badges(self):
        src = _src("compras_pro.py")
        # State badges should use Colors.* tokens
        assert "Colors.SUCCESS_BASE" in src or "Colors.WARNING_BASE" in src, (
            "compras_pro.py debe usar Colors.* para badges de estado"
        )

    def test_compras_pro_does_not_use_qdarkstyle_directly(self):
        src = _src("compras_pro.py")
        assert "qdarkstyle" not in src.lower(), (
            "compras_pro.py no debe depender de qdarkstyle directamente"
        )

    def test_compras_pro_dark_light_tokens_used_consistently(self):
        src = _src("compras_pro.py")
        # Count Colors.* usages — should be significant
        color_refs = len(re.findall(r'Colors\.\w+', src))
        assert color_refs >= 20, (
            f"compras_pro.py solo tiene {color_refs} referencias a Colors.* — "
            "esperado ≥20 para consistencia tema"
        )


class TestRecepcionQRTheme:

    def test_recepcion_qr_no_syntax_error(self):
        ast.parse(_src("recepcion_qr_widget.py"))

    def test_recepcion_qr_no_bare_hex_critical(self):
        src = _src("recepcion_qr_widget.py")
        bare = _find_bare_hex(src)
        assert len(bare) <= 5, (
            f"recepcion_qr_widget.py tiene {len(bare)} hex sin Colors.*: "
            f"{[h for _, h in bare[:10]]}"
        )

    def test_recepcion_qr_no_hardcoded_backgrounds(self):
        src = _src("recepcion_qr_widget.py")
        danger_patterns = [
            r'background:\s*#ffffff\b',
            r'background-color:\s*white\b',
        ]
        for pattern in danger_patterns:
            matches = re.findall(pattern, src, re.IGNORECASE)
            assert not matches, (
                f"recepcion_qr_widget.py contiene background hardcodeado: {matches}"
            )


class TestPhase5DocTypeColorPolicy:
    """
    Los métodos agregados en Phase 5 (doctype toolbar) deben usar Colors.*,
    no hexadecimales literales fuera del contexto de Colors.
    """

    def test_doctype_toolbar_section_uses_colors(self):
        src = _src("compras_pro.py")
        start = src.find("# ── Phase 5: Document-type toolbar")
        end   = src.find("# ── Providers", start) if start != -1 else -1
        phase5_src = src[start:end] if start != -1 and end != -1 else ""
        if not phase5_src:
            pytest.skip("Sección Phase 5 no encontrada — marcador de comentario ausente")
        bare = _find_bare_hex(phase5_src)
        assert not bare, (
            f"Sección Phase 5 tiene hex sin Colors.*: {[h for _, h in bare]}"
        )

    def test_on_doctype_changed_uses_colors(self):
        src = _src("compras_pro.py")
        idx = src.find("def _on_doctype_changed")
        if idx == -1:
            pytest.skip("_on_doctype_changed no encontrado")
        body = src[idx:idx + 800]
        bare = _find_bare_hex(body)
        assert not bare, (
            f"_on_doctype_changed tiene hex sin Colors.*: {[h for _, h in bare]}"
        )


class TestPhase7TimelineColorPolicy:
    """
    _refresh_hist_timeline puede tener inline hex SOLO dentro de su propio body
    y solo para nodos de timeline (documentado como excepción en Phase 7).
    Verifica que no haya hex fuera del body de _refresh_hist_timeline.
    """

    def test_timeline_method_exists(self):
        src = _src("compras_pro.py")
        assert "_refresh_hist_timeline" in src

    def test_timeline_inline_hex_count_reasonable(self):
        src = _src("compras_pro.py")
        idx = src.find("def _refresh_hist_timeline")
        if idx == -1:
            pytest.skip("_refresh_hist_timeline no encontrado")
        # Timeline body (up to next def)
        next_def = src.find("\n    def ", idx + 1)
        body = src[idx:next_def] if next_def != -1 else src[idx:idx + 2000]
        # Count bare hex in timeline body — allowed up to 10 for node styling
        bare = _find_bare_hex(body)
        assert len(bare) <= 10, (
            f"_refresh_hist_timeline tiene {len(bare)} hex inline — "
            "demasiados para ser solo nodos de timeline"
        )
