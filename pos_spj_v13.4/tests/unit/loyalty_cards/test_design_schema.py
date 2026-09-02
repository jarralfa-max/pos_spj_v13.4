"""LOY-18 — declarative card design schema validator (master prompt
§34-36: "no código ejecutable en las plantillas")."""

from __future__ import annotations

import json

import pytest

from backend.domain.loyalty_cards.design_schema import validate_design_schema
from backend.domain.loyalty_cards.exceptions import InvalidCardDesignSchemaError


def _schema(**overrides) -> str:
    base = {
        "canvas": {"width_mm": "85.6", "height_mm": "54", "background_color": "#FFFFFF"},
        "elements": [
            {"type": "TEXT", "x_mm": "5", "y_mm": "5", "width_mm": "40", "height_mm": "10",
             "content": "{{customer_name}}"},
        ],
    }
    base.update(overrides)
    return json.dumps(base)


class TestValidSchemas:
    def test_minimal_valid_schema(self):
        schema = validate_design_schema(_schema())
        assert schema["canvas"]["width_mm"] == "85.6"

    def test_empty_elements_list_is_valid(self):
        validate_design_schema(_schema(elements=[]))

    def test_all_element_types(self):
        elements = [
            {"type": "TEXT", "x_mm": "1", "y_mm": "1", "width_mm": "10", "height_mm": "5",
             "content": "{{card_number}}", "align": "CENTER"},
            {"type": "IMAGE", "x_mm": "1", "y_mm": "1", "width_mm": "10", "height_mm": "5",
             "source": "LOGO"},
            {"type": "QR", "x_mm": "1", "y_mm": "1", "width_mm": "10", "height_mm": "10",
             "data_source": "CARD_TOKEN"},
            {"type": "BARCODE", "x_mm": "1", "y_mm": "1", "width_mm": "20", "height_mm": "8",
             "format": "CODE128", "data_source": "CARD_NUMBER"},
            {"type": "SHAPE", "x_mm": "1", "y_mm": "1", "width_mm": "10", "height_mm": "10",
             "shape_type": "RECTANGLE"},
        ]
        validate_design_schema(_schema(elements=elements))


class TestInvalidSchemas:
    def test_empty_string_rejected(self):
        with pytest.raises(InvalidCardDesignSchemaError):
            validate_design_schema("")

    def test_malformed_json_rejected(self):
        with pytest.raises(InvalidCardDesignSchemaError):
            validate_design_schema("{not json")

    def test_missing_canvas_rejected(self):
        with pytest.raises(InvalidCardDesignSchemaError):
            validate_design_schema(json.dumps({"elements": []}))

    def test_missing_elements_rejected(self):
        with pytest.raises(InvalidCardDesignSchemaError):
            validate_design_schema(json.dumps({"canvas": {"width_mm": "1", "height_mm": "1"}}))

    def test_non_positive_canvas_dimension_rejected(self):
        with pytest.raises(InvalidCardDesignSchemaError):
            validate_design_schema(_schema(canvas={"width_mm": "0", "height_mm": "54"}))

    def test_invalid_background_color_rejected(self):
        with pytest.raises(InvalidCardDesignSchemaError):
            validate_design_schema(
                _schema(canvas={"width_mm": "85.6", "height_mm": "54",
                                "background_color": "red"}))

    def test_unknown_element_type_rejected(self):
        with pytest.raises(InvalidCardDesignSchemaError):
            validate_design_schema(_schema(elements=[
                {"type": "SCRIPT", "x_mm": "1", "y_mm": "1", "width_mm": "1", "height_mm": "1"},
            ]))

    def test_html_in_text_content_rejected(self):
        with pytest.raises(InvalidCardDesignSchemaError):
            validate_design_schema(_schema(elements=[
                {"type": "TEXT", "x_mm": "1", "y_mm": "1", "width_mm": "1", "height_mm": "1",
                 "content": "<script>alert(1)</script>"},
            ]))

    def test_unknown_placeholder_rejected(self):
        with pytest.raises(InvalidCardDesignSchemaError):
            validate_design_schema(_schema(elements=[
                {"type": "TEXT", "x_mm": "1", "y_mm": "1", "width_mm": "1", "height_mm": "1",
                 "content": "{{__import__('os')}}"},
            ]))

    def test_negative_element_dimension_rejected(self):
        with pytest.raises(InvalidCardDesignSchemaError):
            validate_design_schema(_schema(elements=[
                {"type": "TEXT", "x_mm": "-1", "y_mm": "1", "width_mm": "1", "height_mm": "1",
                 "content": "hola"},
            ]))

    def test_invalid_qr_data_source_rejected(self):
        with pytest.raises(InvalidCardDesignSchemaError):
            validate_design_schema(_schema(elements=[
                {"type": "QR", "x_mm": "1", "y_mm": "1", "width_mm": "1", "height_mm": "1",
                 "data_source": "CUSTOM_URL"},
            ]))

    def test_invalid_barcode_format_rejected(self):
        with pytest.raises(InvalidCardDesignSchemaError):
            validate_design_schema(_schema(elements=[
                {"type": "BARCODE", "x_mm": "1", "y_mm": "1", "width_mm": "1", "height_mm": "1",
                 "format": "QR_CODE", "data_source": "CARD_NUMBER"},
            ]))

    def test_element_not_an_object_rejected(self):
        with pytest.raises(InvalidCardDesignSchemaError):
            validate_design_schema(_schema(elements=["not-a-dict"]))
