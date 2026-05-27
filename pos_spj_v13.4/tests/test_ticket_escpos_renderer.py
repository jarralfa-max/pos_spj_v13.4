from core.ticket_escpos_renderer import TicketESCPOSRenderer, INIT, CUT_PARTIAL


def _sample(show_fomo=True):
    return {
        "empresa": "SPJ POS",
        "direccion": "Calle 1",
        "telefono": "123",
        "folio": "V-1",
        "fecha": "2026-01-01",
        "cajero": "admin",
        "cliente": "Cliente 😀 Largo Nombre Muy Muy Largo",
        "items": [
            {"nombre": "Producto con nombre extremadamente largo para envolver columnas", "cantidad": 1, "precio_unitario": 10, "total": 10}
        ],
        "totales": {"subtotal": 10, "descuento": 0, "total_final": 10},
        "puntos_ganados": 5,
        "puntos_totales": 20,
        "mensaje_psicologico": "Gracias 😀",
        "layout_config": {"paper_width_mm": 58, "show_qr": False, "show_fomo": show_fomo},
    }


def test_bytes_start_init_and_end_cut():
    r = TicketESCPOSRenderer()
    b = r.render(_sample())
    assert b.startswith(INIT)
    assert b.endswith(CUT_PARTIAL)


def test_total_and_points_present_when_enabled():
    r = TicketESCPOSRenderer()
    b = r.render(_sample())
    t = b.decode("cp850", errors="replace")
    assert "TOTAL: $10.00" in t
    assert "Puntos ganados" in t


def test_58_and_80_chars_layout():
    r = TicketESCPOSRenderer()
    p58 = r.render_text_preview(_sample(), None)
    assert max(len(x) for x in p58.splitlines()) <= 32
    s = _sample()
    s["layout_config"] = {"paper_width_mm": 80}
    p80 = r.render_text_preview(s, None)
    assert max(len(x) for x in p80.splitlines()) <= 48


def test_sanitize_emoji_and_cp850_encoding_safe():
    r = TicketESCPOSRenderer(encoding="cp850")
    b = r.render(_sample())
    t = b.decode("cp850", errors="replace")
    assert "😀" not in t


def test_long_names_wrapped_in_preview():
    r = TicketESCPOSRenderer()
    p = r.render_text_preview(_sample())
    assert "extremadamente" in p
