"""LOY-19 — safe design import (master prompt §41-42)."""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO

import pytest

from backend.domain.loyalty_cards.exceptions import InvalidCardDesignSchemaError
from backend.infrastructure.loyalty_cards.design_import import import_canvas_dimensions


def _png_bytes(width: int, height: int) -> bytes:
    from PIL import Image
    buf = BytesIO()
    Image.new("RGB", (width, height), color="white").save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_bytes(width: int, height: int) -> bytes:
    from PIL import Image
    buf = BytesIO()
    Image.new("RGB", (width, height), color="white").save(buf, format="JPEG")
    return buf.getvalue()


def _svg_bytes(width: str, height: str, extra: str = "") -> bytes:
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">{extra}</svg>'
    return svg.encode("utf-8")


class TestRasterImport:
    def test_png_dimensions_at_300dpi(self):
        # 1011x638 px @ 300dpi ~= 85.6mm x 54mm (standard card size)
        result = import_canvas_dimensions(_png_bytes(1011, 638), "PNG", dpi=300)
        assert Decimal(result["width_mm"]) == pytest.approx(Decimal("85.63"), abs=Decimal("0.1"))

    def test_jpeg_accepted(self):
        result = import_canvas_dimensions(_jpeg_bytes(600, 400), "JPEG", dpi=300)
        assert Decimal(result["width_mm"]) > 0
        assert Decimal(result["height_mm"]) > 0

    def test_jpg_alias_accepted(self):
        result = import_canvas_dimensions(_jpeg_bytes(600, 400), "jpg", dpi=300)
        assert Decimal(result["width_mm"]) > 0

    def test_corrupted_image_rejected(self):
        with pytest.raises(InvalidCardDesignSchemaError):
            import_canvas_dimensions(b"not a real image", "PNG", dpi=300)

    def test_declared_format_mismatch_rejected(self):
        # A real JPEG declared as PNG must be rejected, not silently accepted.
        with pytest.raises(InvalidCardDesignSchemaError):
            import_canvas_dimensions(_jpeg_bytes(100, 100), "PNG", dpi=300)

    def test_empty_bytes_rejected(self):
        with pytest.raises(InvalidCardDesignSchemaError):
            import_canvas_dimensions(b"", "PNG", dpi=300)

    def test_oversized_file_rejected(self):
        with pytest.raises(InvalidCardDesignSchemaError):
            import_canvas_dimensions(b"x" * (11 * 1024 * 1024), "PNG", dpi=300)

    def test_non_positive_dpi_rejected(self):
        with pytest.raises(InvalidCardDesignSchemaError):
            import_canvas_dimensions(_png_bytes(100, 100), "PNG", dpi=0)


class TestSvgImport:
    def test_valid_svg_dimensions(self):
        result = import_canvas_dimensions(_svg_bytes("85.6", "54"), "SVG")
        assert result["width_mm"] == "85.6"
        assert result["height_mm"] == "54"

    def test_svg_without_viewbox_rejected(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>'
        with pytest.raises(InvalidCardDesignSchemaError):
            import_canvas_dimensions(svg, "SVG")

    def test_svg_with_script_tag_rejected(self):
        malicious = _svg_bytes("10", "10", extra="<script>alert(1)</script>")
        with pytest.raises(InvalidCardDesignSchemaError):
            import_canvas_dimensions(malicious, "SVG")

    def test_svg_with_event_handler_attribute_rejected(self):
        malicious = _svg_bytes("10", "10", extra='<rect onload="evil()" width="1" height="1"/>')
        with pytest.raises(InvalidCardDesignSchemaError):
            import_canvas_dimensions(malicious, "SVG")

    def test_svg_with_foreign_object_rejected(self):
        malicious = _svg_bytes("10", "10", extra="<foreignObject><body>x</body></foreignObject>")
        with pytest.raises(InvalidCardDesignSchemaError):
            import_canvas_dimensions(malicious, "SVG")

    def test_svg_with_remote_href_rejected(self):
        malicious = _svg_bytes(
            "10", "10", extra='<image href="http://evil.example.com/x.png"/>')
        with pytest.raises(InvalidCardDesignSchemaError):
            import_canvas_dimensions(malicious, "SVG")

    def test_svg_with_xxe_rejected(self):
        xxe = (b'<?xml version="1.0"?>'
               b'<!DOCTYPE svg [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
               b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">&xxe;</svg>')
        with pytest.raises(InvalidCardDesignSchemaError):
            import_canvas_dimensions(xxe, "SVG")

    def test_malformed_xml_rejected(self):
        with pytest.raises(InvalidCardDesignSchemaError):
            import_canvas_dimensions(b"<svg><unclosed>", "SVG")

    def test_non_svg_root_rejected(self):
        with pytest.raises(InvalidCardDesignSchemaError):
            import_canvas_dimensions(b'<html><body>hi</body></html>', "SVG")


class TestUnsupportedFormats:
    def test_pdf_explicitly_not_implemented(self):
        with pytest.raises(InvalidCardDesignSchemaError):
            import_canvas_dimensions(b"%PDF-1.4", "PDF")

    def test_unknown_format_rejected(self):
        with pytest.raises(InvalidCardDesignSchemaError):
            import_canvas_dimensions(b"data", "TIFF")
