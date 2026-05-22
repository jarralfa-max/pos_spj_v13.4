# modulos/whatsapp/panels/_panel_styles.py
"""Shared styling utilities for WhatsApp panels."""
from modulos.design_tokens import Colors, Spacing, Typography, Borders


def group_box_style() -> str:
    """Common QGroupBox stylesheet for all WhatsApp panels — theme-safe."""
    return (
        f"QGroupBox {{"
        f"  border: 1px solid {Colors.NEUTRAL.SLATE_200};"
        f"  border-radius: {Borders.RADIUS_XL}px;"
        f"  margin-top: {Spacing.SM}px;"
        f"  padding-top: {Spacing.SM}px;"
        f"  background: transparent;"
        f"}}"
        f"QGroupBox::title {{"
        f"  subcontrol-origin: margin;"
        f"  subcontrol-position: top left;"
        f"  padding: 0 {Spacing.SM}px;"
        f"  color: {Colors.NEUTRAL.SLATE_600};"
        f"  font-size: {Typography.SIZE_MD};"
        f"  font-weight: {Typography.WEIGHT_SEMIBOLD};"
        f"}}"
    )
