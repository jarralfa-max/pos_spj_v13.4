import sqlite3

from core.tickets.branding_service import BrandingService


def _db_with_config(pairs):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE configuraciones (clave TEXT PRIMARY KEY, valor TEXT)")
    for k, v in pairs.items():
        conn.execute("INSERT INTO configuraciones(clave, valor) VALUES (?,?)", (k, v))
    conn.commit()
    return conn


def test_uses_global_logo_when_present():
    db = _db_with_config({"brand_logo_b64": "GLOBAL", "ticket_logo_b64": "LEGACY"})
    svc = BrandingService(db_conn=db)
    p = svc.get_ticket_branding()
    assert p.logo_b64 == "GLOBAL"


def test_fallback_to_legacy_logo_if_global_missing():
    db = _db_with_config({"ticket_logo_b64": "LEGACY"})
    svc = BrandingService(db_conn=db)
    p = svc.get_ticket_branding()
    assert p.logo_b64 == "LEGACY"


def test_brand_name_from_global_config_with_legacy_fallback():
    db = _db_with_config({"brand_name": "Mi Marca", "nombre_empresa": "Legacy SA"})
    svc = BrandingService(db_conn=db)
    p = svc.get_ticket_branding()
    assert p.brand_name == "Mi Marca"


def test_ticket_visual_preferences_can_remain_separate():
    db = _db_with_config({
        "ticket_logo_width": "180",
        "ticket_logo_pos": "Centrado",
        "ticket_show_logo": "1",
        "nombre_empresa": "Legacy SA",
    })
    svc = BrandingService(db_conn=db)
    p = svc.get_ticket_branding()
    assert p.brand_name == "Legacy SA"
    row_w = db.execute("SELECT valor FROM configuraciones WHERE clave='ticket_logo_width'").fetchone()
    row_p = db.execute("SELECT valor FROM configuraciones WHERE clave='ticket_logo_pos'").fetchone()
    assert row_w[0] == "180"
    assert row_p[0] == "Centrado"
