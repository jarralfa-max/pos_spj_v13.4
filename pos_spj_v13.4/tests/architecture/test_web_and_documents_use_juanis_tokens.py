"""SDLC-UI-005 — un solo sistema visual: las PWA y el PDF de BI usan JUANIS.

Decisión del responsable (2026-11-02): las PWA de delivery y logística llevan
identidad JUANIS. Sus colores salen de la misma fuente que el QSS
(``semantic_colors.py``) a través de ``web_tokens.py``; ningún hex vive fuera de
esa fuente en ``frontend/web``.
"""

from __future__ import annotations

from pathlib import Path
import re

import pytest

from frontend.desktop.themes import web_tokens

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "frontend" / "web"
APPS = ("delivery", "logistics")
#: CSS/HTML/SVG/JSON color literals: #rgb or #rrggbb in a value position.
_HEX = re.compile(r"(?<![\w&])#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})\b")
_TEXT_SUFFIXES = {".css", ".html", ".js", ".webmanifest", ".svg", ".json"}


def _normalize(value: str) -> str:
    value = value.lstrip("#").upper()
    return "#" + ("".join(ch * 2 for ch in value) if len(value) == 3 else value)


def _web_files():
    for path in sorted(WEB.rglob("*")):
        if path.is_file() and path.suffix in _TEXT_SUFFIXES and "vendor" not in path.parts:
            yield path


@pytest.mark.parametrize("app", APPS)
def test_stylesheet_embeds_the_generated_token_block(app):
    css = (WEB / app / "styles.css").read_text(encoding="utf-8")
    assert web_tokens.css_token_block() in css, (
        f"{app}/styles.css no trae el bloque generado; corre "
        "`python -m frontend.desktop.themes.web_tokens --write`")


@pytest.mark.parametrize("app", APPS)
def test_stylesheet_has_no_hex_outside_the_generated_block(app):
    css = (WEB / app / "styles.css").read_text(encoding="utf-8")
    rest = css.replace(web_tokens.css_token_block(), "")
    assert _HEX.findall(rest) == []


def test_no_web_hex_outside_the_juanis_source():
    allowed = {_normalize(v) for v in web_tokens.token_values()}
    strays = []
    for path in _web_files():
        for match in _HEX.findall(path.read_text(encoding="utf-8")):
            if _normalize(match) not in allowed:
                strays.append(f"{path.relative_to(ROOT).as_posix()}: #{match}")
    assert not strays, "hex fuera de la fuente JUANIS:\n" + "\n".join(strays)


def test_tokens_come_from_semantic_colors():
    from frontend.desktop.themes.semantic_colors import Light
    tokens = dict(web_tokens.css_tokens())
    assert tokens["--primary"] == Light.PRIMARY_DEFAULT
    assert tokens["--danger"] == Light.DANGER_DEFAULT
    assert tokens["--surface"] == Light.SURFACE


def test_bi_pdf_uses_injected_juanis_document_colors(tmp_path, monkeypatch):
    pytest.importorskip("reportlab")
    import reportlab.platypus as platypus
    from backend.application.analytics.services.bi_export_service import BiExportService

    captured = []
    real = platypus.TableStyle

    def spy(commands, *args, **kwargs):
        captured.extend(commands)
        return real(commands, *args, **kwargs)

    monkeypatch.setattr(platypus, "TableStyle", spy)
    palette = web_tokens.document_palette()
    payload = {"kpis": [], "alerts": [], "insights": []}
    BiExportService(document_colors=palette).export_summary(
        payload, {"usuario": "u"}, str(tmp_path / "r.pdf"), fmt="pdf")
    by_name = {c[0]: c for c in captured}
    assert by_name["BACKGROUND"][3].hexval().upper() == "0X" + palette["header_background"][1:].upper()
    assert by_name["GRID"][4].hexval().upper() == "0X" + palette["grid"][1:].upper()


def test_bi_export_service_has_no_hand_written_hex():
    source = (ROOT / "backend/application/analytics/services/bi_export_service.py").read_text(encoding="utf-8")
    assert _HEX.findall(source) == []


def test_reports_presenter_injects_the_juanis_document_palette():
    source = (ROOT / "frontend/desktop/modules/business_intelligence/presenters/reports_presenter.py").read_text(encoding="utf-8")
    assert "BiExportService(document_colors=document_palette())" in source
