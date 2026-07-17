"""SPJ global theme layer — the ONLY place allowed to hold explicit colors.

Public surface:
    BrandColors      — official JUANIS identity palette (DS-1).
    SemanticColors   — meaning-based tokens for light/dark themes (DS-1).
    ChartPalette     — accessible categorical/sequential chart colors (DS-1).
    tokens           — spacing, sizing, radii, metrics (DS-2).
    build_qss        — QSS generator driven by objectName/property (DS-2).
    ThemeManager     — single authority that applies a theme (DS-2).

Modules must import colors/tokens from here — never redefine them locally.
"""
