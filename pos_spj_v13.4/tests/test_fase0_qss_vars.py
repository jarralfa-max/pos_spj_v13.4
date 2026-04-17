# tests/test_fase0_qss_vars.py
# Fase 0 — Bug 3: QSS no debe contener CSS var() que Qt no soporta
# Qt no soporta CSS custom properties (var(--xxx)). Deben usarse valores literales.
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


def _get_temas():
    """Importa el diccionario TEMAS de config.py."""
    import config
    return config.TEMAS


def test_oscuro_sin_css_variables():
    """El tema Oscuro no debe contener var(--) en el QSS."""
    temas = _get_temas()
    qss = temas.get("Oscuro", "")
    assert qss, "El tema Oscuro debe estar definido en TEMAS"
    ocurrencias = [line.strip() for line in qss.splitlines() if "var(--" in line]
    assert not ocurrencias, (
        f"El tema Oscuro contiene CSS var() no soportadas por Qt:\n"
        + "\n".join(f"  {o}" for o in ocurrencias)
    )


def test_claro_sin_css_variables():
    """El tema Claro no debe contener var(--) en el QSS."""
    temas = _get_temas()
    qss = temas.get("Claro", "")
    assert qss, "El tema Claro debe estar definido en TEMAS"
    ocurrencias = [line.strip() for line in qss.splitlines() if "var(--" in line]
    assert not ocurrencias, (
        f"El tema Claro contiene CSS var() no soportadas por Qt:\n"
        + "\n".join(f"  {o}" for o in ocurrencias)
    )


def test_oscuro_login_dialog_colores_literales():
    """El tema Oscuro debe tener colores literales para QDialog#loginDialog."""
    temas = _get_temas()
    qss = temas.get("Oscuro", "")
    # El background del loginDialog debe ser un color literal (#hex)
    assert "QDialog#loginDialog" in qss, "QDialog#loginDialog debe existir en tema Oscuro"
    assert "#1E293B" in qss, (
        "El fondo del loginDialog debe ser #1E293B (card-bg del tema oscuro)"
    )


def test_oscuro_input_field_colores_literales():
    """El tema Oscuro debe tener colores literales para QLineEdit#inputField."""
    temas = _get_temas()
    qss = temas.get("Oscuro", "")
    assert "QLineEdit#inputField" in qss, "QLineEdit#inputField debe existir en tema Oscuro"
    # Verificar que el borde usa color literal
    assert "#334155" in qss, (
        "El borde del inputField debe ser #334155 (border del tema oscuro)"
    )


def test_ambos_temas_definidos():
    """Ambos temas (Oscuro y Claro) deben estar presentes en TEMAS."""
    temas = _get_temas()
    assert "Oscuro" in temas, "Tema Oscuro debe estar en TEMAS"
    assert "Claro" in temas, "Tema Claro debe estar en TEMAS"
    assert len(temas["Oscuro"]) > 100, "Tema Oscuro debe tener QSS completo (>100 chars)"
    assert len(temas["Claro"]) > 100, "Tema Claro debe tener QSS completo (>100 chars)"
