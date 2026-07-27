# tests/test_fase1_design_tokens.py
# Fase 1 — apply_object_names(): design tokens objectName en QPushButtons
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

# Guard: PyQt5 puede no estar disponible en CI sin display
try:
    from PyQt5.QtWidgets import QApplication, QWidget, QPushButton
    _app = QApplication.instance() or QApplication(sys.argv)
    _HAS_QT = True
except Exception:
    _HAS_QT = False

pytestmark = pytest.mark.skipif(not _HAS_QT, reason="PyQt5 no disponible")


def _make_widget(*labels):
    """Crea un QWidget con botones de los textos dados."""
    w = QWidget()
    for label in labels:
        btn = QPushButton(label, w)
        btn.setObjectName("")  # sin objectName asignado
    return w


# ══════════════════════════════════════════════════════════════════════════════
# apply_object_names — asignación de objectName
# ══════════════════════════════════════════════════════════════════════════════

def test_apply_object_names_cobrar_es_primary():
    """Botón 'Cobrar' → objectName 'primaryBtn'."""
    from modulos.spj_styles import apply_object_names
    w = _make_widget("Cobrar")
    apply_object_names(w)
    btn = w.findChildren(QPushButton)[0]
    assert btn.objectName() == "primaryBtn"


def test_apply_object_names_guardar_es_success():
    """Botón 'Guardar' → objectName 'successBtn'."""
    from modulos.spj_styles import apply_object_names
    w = _make_widget("Guardar")
    apply_object_names(w)
    btn = w.findChildren(QPushButton)[0]
    assert btn.objectName() == "successBtn"


def test_apply_object_names_eliminar_es_danger():
    """Botón 'Eliminar' → objectName 'dangerBtn'."""
    from modulos.spj_styles import apply_object_names
    w = _make_widget("Eliminar")
    apply_object_names(w)
    btn = w.findChildren(QPushButton)[0]
    assert btn.objectName() == "dangerBtn"


def test_apply_object_names_editar_es_warning():
    """Botón 'Editar' → objectName 'warningBtn'."""
    from modulos.spj_styles import apply_object_names
    w = _make_widget("Editar")
    apply_object_names(w)
    btn = w.findChildren(QPushButton)[0]
    assert btn.objectName() == "warningBtn"


def test_apply_object_names_cerrar_es_secondary():
    """Botón 'Cerrar' → objectName 'secondaryBtn'."""
    from modulos.spj_styles import apply_object_names
    w = _make_widget("Cerrar")
    apply_object_names(w)
    btn = w.findChildren(QPushButton)[0]
    assert btn.objectName() == "secondaryBtn"


def test_apply_object_names_sin_keyword_fallback():
    """Botón sin keyword reconocida → fallback 'secondaryBtn'."""
    from modulos.spj_styles import apply_object_names
    w = _make_widget("XYZ_desconocido_123")
    apply_object_names(w)
    btn = w.findChildren(QPushButton)[0]
    assert btn.objectName() == "secondaryBtn"


def test_apply_object_names_es_idempotente():
    """Segunda llamada a apply_object_names() no cambia objectName ya asignado."""
    from modulos.spj_styles import apply_object_names
    w = _make_widget("Guardar")
    apply_object_names(w)
    btn = w.findChildren(QPushButton)[0]
    first_name = btn.objectName()
    apply_object_names(w)  # Segunda llamada
    assert btn.objectName() == first_name


def test_apply_object_names_no_sobrescribe_spj_existente():
    """Botón que ya tiene objectName SPJ ('primaryBtn') no debe cambiarse."""
    from modulos.spj_styles import apply_object_names
    w = QWidget()
    btn = QPushButton("Eliminar", w)
    btn.setObjectName("primaryBtn")  # Asignado previamente
    apply_object_names(w)
    # Debe conservar 'primaryBtn', no cambiarlo a 'dangerBtn'
    assert btn.objectName() == "primaryBtn"


def test_apply_object_names_multiples_botones():
    """Múltiples botones reciben objectName correcto cada uno."""
    from modulos.spj_styles import apply_object_names
    w = _make_widget("Guardar", "Eliminar", "Cerrar")
    apply_object_names(w)
    btns = {b.text(): b.objectName() for b in w.findChildren(QPushButton)}
    assert btns["Guardar"] == "successBtn"
    assert btns["Eliminar"] == "dangerBtn"
    assert btns["Cerrar"] == "secondaryBtn"
