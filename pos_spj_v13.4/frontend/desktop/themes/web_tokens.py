"""JUANIS tokens exported for the web apps and printed documents (SDLC-UI-005).

One visual system: the PWAs (``frontend/web/*``) and the BI PDF take their
colors from ``semantic_colors.py`` — the same source as the desktop QSS. The
PWAs embed a generated ``:root`` block; regenerate it after a token change with

    python -m frontend.desktop.themes.web_tokens --write

Printed output and the PWAs use the light theme (paper / outdoor screens).
"""

from __future__ import annotations

from pathlib import Path
import sys

from frontend.desktop.themes.color_utils import hex_to_rgb
from frontend.desktop.themes.semantic_colors import Light

#: CSS custom property → light semantic token.
_CSS_TOKENS = (
    ("--primary", "PRIMARY_DEFAULT"),
    ("--primary-strong", "PRIMARY_PRESSED"),
    ("--primary-subtle", "PRIMARY_SUBTLE"),
    ("--accent", "ACCENT_DEFAULT"),
    ("--focus", "FOCUS_RING"),
    ("--text", "TEXT_PRIMARY"),
    ("--text-secondary", "TEXT_SECONDARY"),
    ("--text-muted", "TEXT_MUTED"),
    ("--text-inverse", "TEXT_INVERSE"),
    ("--border", "BORDER_DEFAULT"),
    ("--input-border", "INPUT_BORDER"),
    ("--surface", "SURFACE"),
    ("--canvas", "BACKGROUND"),
    ("--success", "SUCCESS_DEFAULT"),
    ("--success-subtle", "SUCCESS_SUBTLE"),
    ("--warning", "WARNING_DEFAULT"),
    ("--warning-subtle", "WARNING_SUBTLE"),
    ("--danger", "DANGER_DEFAULT"),
    ("--danger-subtle", "DANGER_SUBTLE"),
    ("--media", "TOOLTIP_BACKGROUND"),       # camera letterbox / overlay shade
)

_BLOCK_START = "/* JUANIS tokens: generado por frontend/desktop/themes/web_tokens.py; no editar a mano */"
_BLOCK_END = "/* fin de tokens JUANIS */"
WEB_APPS = ("delivery", "logistics")


def _rgba(color: str, alpha: float) -> str:
    r, g, b = hex_to_rgb(color)
    return f"rgba({r},{g},{b},{alpha})"


def css_tokens() -> tuple[tuple[str, str], ...]:
    colors = tuple((name, getattr(Light, attr)) for name, attr in _CSS_TOKENS)
    derived = (
        ("--shadow", f"0 8px 24px {_rgba(Light.PRIMARY_DEFAULT, 0.09)}"),
        ("--focus-glow", _rgba(Light.FOCUS_RING, 0.35)),
    )
    return colors + derived


def token_values() -> frozenset[str]:
    """Every hex the web apps may contain (manifest/meta/SVG need literals)."""
    return frozenset(getattr(Light, attr) for _, attr in _CSS_TOKENS)


def css_token_block() -> str:
    body = ";".join(f"{name}:{value}" for name, value in css_tokens())
    return f"{_BLOCK_START}\n:root{{{body}}}\n{_BLOCK_END}"


def document_palette() -> dict[str, str]:
    """Colors for printed reports (BI PDF), from the same light tokens."""
    return {
        "header_background": Light.PRIMARY_DEFAULT,
        "header_text": Light.TEXT_INVERSE,
        "grid": Light.BORDER_DEFAULT,
    }


def write_stylesheets(web_root: Path | None = None) -> list[Path]:
    """Replace (or prepend) the generated block in each PWA stylesheet,
    keeping each file's own line endings."""
    root = web_root or Path(__file__).resolve().parents[2] / "web"
    written = []
    for app in WEB_APPS:
        path = root / app / "styles.css"
        raw = path.read_bytes().decode("utf-8")
        newline = "\r\n" if "\r\n" in raw else "\n"
        css = raw.replace("\r\n", "\n")
        if _BLOCK_START in css and _BLOCK_END in css:
            head, rest = css.split(_BLOCK_START, 1)
            tail = rest.split(_BLOCK_END, 1)[1]
            css = head + css_token_block() + tail
        else:
            css = css_token_block() + "\n" + css
        path.write_bytes(css.replace("\n", newline).encode("utf-8"))
        written.append(path)
    return written


if __name__ == "__main__":  # pragma: no cover - developer tool
    if "--write" in sys.argv:
        for written_path in write_stylesheets():
            print(written_path)
    else:
        print(css_token_block())
