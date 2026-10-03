"""LOY-29 — privacidad de lo impreso (§37), reverso y dúplex (§33-34, §40).

* El nombre se imprime según el modo; los puntos NO se imprimen por omisión.
* El esquema admite reverso (`back_elements`) validado con la misma lista
  blanca, y rechaza cualquier clave de primer nivel desconocida.
* El renderizador produce anverso Y reverso por pliego.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from backend.domain.loyalty_cards.design_schema import validate_design_schema
from backend.domain.loyalty_cards.exceptions import InvalidCardDesignSchemaError
from backend.domain.loyalty_cards.policies.privacy_policy import (
    CardNameMode,
    LoyaltyCardPrivacyPolicy,
    LoyaltyCardPrivacySettings,
)

_QR = {"type": "QR", "data_source": "CARD_TOKEN", "x_mm": "60", "y_mm": "25",
       "width_mm": "20", "height_mm": "20"}
_BARRAS = {"type": "BARCODE", "format": "CODE128", "data_source": "CARD_NUMBER",
           "x_mm": "5", "y_mm": "40", "width_mm": "45", "height_mm": "7"}


def _pages(pdf: bytes) -> int:
    return pdf.count(b"/Type /Page") - pdf.count(b"/Type /Pages")


class TestPrivacy:
    @pytest.mark.parametrize("modo,esperado", [
        (CardNameMode.FULL_NAME, "Ana María Torres"), (CardNameMode.FIRST_NAME, "Ana"),
        (CardNameMode.INITIALS, "A.M.T."), (CardNameMode.NOT_PRINTED, "")])
    def test_name_modes(self, modo, esperado):
        assert LoyaltyCardPrivacyPolicy.printed_name(
            "Ana  María Torres", LoyaltyCardPrivacySettings(name_mode=modo)) == esperado

    def test_points_are_not_printed_by_default(self):
        assert LoyaltyCardPrivacyPolicy.printed_points(500, LoyaltyCardPrivacySettings()) == ""
        assert LoyaltyCardPrivacyPolicy.printed_points(
            500, LoyaltyCardPrivacySettings(print_points_balance=True)) == "500"


class TestBackSide:
    def _schema(self, **extra) -> str:
        return json.dumps({"canvas": {"width_mm": "85.6", "height_mm": "53.98"},
                           "elements": [_QR], **extra})

    def test_back_side_is_validated_with_the_same_whitelist(self):
        assert validate_design_schema(self._schema(back_elements=[_BARRAS]))["back_elements"]
        with pytest.raises(InvalidCardDesignSchemaError):
            validate_design_schema(self._schema(back_elements=[{"type": "SCRIPT"}]))

    def test_unknown_top_level_keys_are_rejected(self):
        with pytest.raises(InvalidCardDesignSchemaError):
            validate_design_schema(self._schema(on_load="alert(1)"))

    @pytest.mark.parametrize("con_reverso,paginas", [(False, 1), (True, 2)])
    def test_renderer_prints_front_and_back_per_sheet(self, con_reverso, paginas):
        pytest.importorskip("reportlab")
        pytest.importorskip("qrcode")
        pytest.importorskip("barcode")
        from backend.infrastructure.loyalty_cards.print_renderer import PrintUnit, render_batch_pdf

        extra = {"back_elements": [_BARRAS]} if con_reverso else {}
        unidades = [PrintUnit(card_id=f"c{i}", sheet_number=1, position_in_sheet=i,
                              placeholder_values={"card_token": "SPJ-CARD:abc",
                                                  "card_number": f"LC-{i:08d}"})
                    for i in (1, 2)]
        pdf = render_batch_pdf(
            sheet_width_mm=Decimal("304.8"), sheet_height_mm=Decimal("457.2"),
            margin_left_mm=Decimal("5"), margin_top_mm=Decimal("5"), columns=3, rows=7,
            card_width_mm=Decimal("85.6"), card_height_mm=Decimal("53.98"),
            bleed_mm=Decimal("3"), gutter_horizontal_mm=Decimal("0"),
            gutter_vertical_mm=Decimal("0"), design_schema=json.loads(self._schema(**extra)),
            print_units=unidades)
        assert _pages(pdf) == paginas
