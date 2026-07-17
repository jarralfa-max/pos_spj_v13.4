"""Color math for the theme layer (WCAG contrast, tint/shade, alpha flatten).

Theme-layer file: explicit numeric color operations are allowed here (and only
here + the palette/token files). Pure functions, no Qt, no I/O.
"""

from __future__ import annotations

RGB = tuple[int, int, int]


def hex_to_rgb(value: str) -> RGB:
    v = value.lstrip("#")
    if len(v) == 3:
        v = "".join(ch * 2 for ch in v)
    if len(v) != 6:
        raise ValueError(f"Invalid hex color: {value!r}")
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def rgb_to_hex(rgb: RGB) -> str:
    r, g, b = (max(0, min(255, int(round(c)))) for c in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


def mix(color_a: str, color_b: str, weight_b: float) -> str:
    """Linear blend; ``weight_b`` in [0,1] is the share of ``color_b``."""
    w = max(0.0, min(1.0, weight_b))
    ra, ga, ba = hex_to_rgb(color_a)
    rb, gb, bb = hex_to_rgb(color_b)
    return rgb_to_hex((
        ra + (rb - ra) * w,
        ga + (gb - ga) * w,
        ba + (bb - ba) * w,
    ))


def lighten(color: str, amount: float) -> str:
    """Move ``amount`` of the way toward white."""
    return mix(color, "#FFFFFF", amount)


def darken(color: str, amount: float) -> str:
    """Move ``amount`` of the way toward black."""
    return mix(color, "#000000", amount)


def flatten_over(foreground: str, alpha: float, background: str) -> str:
    """Composite a translucent ``foreground`` (alpha in [0,1]) over ``background``."""
    return mix(background, foreground, alpha)


def _linearize(channel: int) -> float:
    c = channel / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(color: str) -> float:
    """WCAG relative luminance in [0,1]."""
    r, g, b = hex_to_rgb(color)
    return 0.2126 * _linearize(r) + 0.7152 * _linearize(g) + 0.0722 * _linearize(b)


def contrast_ratio(color_a: str, color_b: str) -> float:
    """WCAG contrast ratio (1..21), order-independent."""
    la, lb = relative_luminance(color_a), relative_luminance(color_b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


# WCAG 2.1 thresholds
AA_NORMAL_TEXT = 4.5
AA_LARGE_TEXT = 3.0
AA_UI_COMPONENT = 3.0


def meets_aa(foreground: str, background: str, *, large: bool = False) -> bool:
    threshold = AA_LARGE_TEXT if large else AA_NORMAL_TEXT
    return contrast_ratio(foreground, background) >= threshold
