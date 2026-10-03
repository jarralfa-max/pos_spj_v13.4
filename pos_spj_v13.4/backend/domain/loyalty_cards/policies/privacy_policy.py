"""LoyaltyCardPrivacyPolicy — qué se imprime de una persona en su tarjeta (§37).

Por omisión NO se imprime: teléfono, correo, domicilio, saldo, puntos, ni
ningún identificador interno. El nombre se imprime según el modo configurado.
La política es pura: recibe el nombre y la configuración y devuelve el texto.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CardNameMode(str, Enum):
    FULL_NAME = "FULL_NAME"
    FIRST_NAME = "FIRST_NAME"
    INITIALS = "INITIALS"
    NOT_PRINTED = "NOT_PRINTED"


@dataclass(frozen=True)
class LoyaltyCardPrivacySettings:
    name_mode: CardNameMode = CardNameMode.FULL_NAME
    print_points_balance: bool = False


class LoyaltyCardPrivacyPolicy:
    @staticmethod
    def printed_name(display_name: str | None, settings: LoyaltyCardPrivacySettings) -> str:
        nombre = " ".join(str(display_name or "").split())
        if not nombre or settings.name_mode is CardNameMode.NOT_PRINTED:
            return ""
        if settings.name_mode is CardNameMode.FIRST_NAME:
            return nombre.split(" ")[0]
        if settings.name_mode is CardNameMode.INITIALS:
            return "".join(f"{parte[0].upper()}." for parte in nombre.split(" ") if parte)
        return nombre

    @staticmethod
    def printed_points(points, settings: LoyaltyCardPrivacySettings) -> str:
        return str(points) if settings.print_points_balance and points is not None else ""


__all__ = ["CardNameMode", "LoyaltyCardPrivacyPolicy", "LoyaltyCardPrivacySettings"]
