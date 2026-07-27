# tests/test_ticket_designer_config_route.py
"""Remediación F — ticket_designer usa ConfigService (no SQL directo).

Caracteriza que la ruta canónica ConfigService.set()→get() persiste y devuelve
los parámetros de ticket (logo, papel, QR) que el widget lee/escribe, tras
extraer el SQL crudo de configuraciones que vivía en la UI.
"""
import sqlite3

import pytest


@pytest.fixture
def cfg():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    from migrations import engine
    engine.up(conn)
    conn.commit()
    from repositories.config_repository import ConfigRepository
    from core.services.config_service import ConfigService
    return ConfigService(ConfigRepository(conn)), conn


def test_set_get_roundtrip_ticket_keys(cfg):
    svc, _conn = cfg
    svc.set("ticket_logo_b64", "data:image/png;base64,AAA")
    svc.set("ticket_paper_width", "80")
    svc.set("ticket_qr_enabled", "1")
    assert svc.get("ticket_logo_b64") == "data:image/png;base64,AAA"
    assert int(svc.get("ticket_paper_width", "0")) == 80
    assert svc.get("ticket_qr_enabled", "0") == "1"


def test_get_default_para_clave_ausente(cfg):
    svc, _conn = cfg
    # clave inexistente devuelve el default provisto (semántica usada por el widget)
    assert (svc.get("ticket_font_family") or "Courier New") == "Courier New"


def test_set_persiste_en_bd_y_sobrevive_refresh(cfg):
    svc, conn = cfg
    svc.set("ticket_font_size", "14")
    # Nuevo ConfigService sobre la misma BD ve el valor (persistió, no sólo caché)
    from repositories.config_repository import ConfigRepository
    from core.services.config_service import ConfigService
    svc2 = ConfigService(ConfigRepository(conn))
    assert svc2.get("ticket_font_size") == "14"
