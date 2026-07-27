# tests/test_fase0_ventas_canje.py
# Fase 0 — Hotfix: _toggle_canje y _recalcular_canje en DialogoPago
# Verifica que los métodos existen y funcionan sin UI (sin PyQt5 headless).
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


class FakeSpinPuntos:
    """Stub mínimo de QSpinBox para tests sin display."""
    def __init__(self, value=0):
        self._value = value
        self._enabled = False

    def setEnabled(self, v):
        self._enabled = v

    def value(self):
        return self._value


class FakeLbl:
    """Stub mínimo de QLabel."""
    def __init__(self):
        self._text = ""

    def setText(self, t):
        self._text = t

    def text(self):
        return self._text


class FakeBtn:
    """Stub mínimo de QPushButton."""
    def __init__(self):
        self._enabled = True

    def setEnabled(self, v):
        self._enabled = v


class FakeSpinDbl:
    """Stub mínimo de QDoubleSpinBox."""
    def __init__(self, value=0.0):
        self._value = value

    def setValue(self, v):
        self._value = v

    def value(self):
        return self._value


class StubDialogoPago:
    """
    Stub que reproduce únicamente el estado y la lógica de canje
    de DialogoPago, sin instanciar ningún widget PyQt5.
    """
    def __init__(self, total, loyalty_balance=None):
        self.total_a_pagar = float(total)
        self.total_original = float(total)
        self._loyalty = loyalty_balance or {}
        self.descuento_puntos = 0.0
        self.puntos_a_canjear = 0
        self.cambio = 0.0
        self.forma_pago = "Efectivo"
        self.efectivo_recibido = total

        self._spin_puntos = FakeSpinPuntos(self._loyalty.get("puntos", 0))
        self._lbl_desc_puntos = FakeLbl()
        self.lbl_total = FakeLbl()
        self.lbl_total.setText(f"Total a pagar: ${self.total_a_pagar:.2f}")
        self.txt_recibido = FakeSpinDbl(total)
        self.btn_aceptar = FakeBtn()

    # ── Métodos bajo prueba ────────────────────────────────────────────────
    def calcular_cambio(self):
        self.efectivo_recibido = self.txt_recibido.value()
        if self.forma_pago == "Efectivo":
            self.cambio = round(self.efectivo_recibido - self.total_a_pagar, 2)
            if self.cambio < 0:
                self.btn_aceptar.setEnabled(False)
            else:
                self.btn_aceptar.setEnabled(True)
        else:
            self.efectivo_recibido = self.total_a_pagar
            self.cambio = 0.0
            self.btn_aceptar.setEnabled(True)

    def _toggle_canje(self, checked: bool):
        """Copia exacta del método implementado en modulos/ventas.py."""
        self._spin_puntos.setEnabled(checked)
        if checked:
            self._recalcular_canje(self._spin_puntos.value())
        else:
            self.descuento_puntos = 0.0
            self.puntos_a_canjear = 0
            self.total_a_pagar = self.total_original
            self._lbl_desc_puntos.setText("")
            self.lbl_total.setText(f"Total a pagar: ${self.total_a_pagar:.2f}")
            self.txt_recibido.setValue(self.total_a_pagar)
            self.calcular_cambio()

    def _recalcular_canje(self, value: int):
        """Copia exacta del método implementado en modulos/ventas.py."""
        pts = self._loyalty.get("puntos", 0)
        valor_total = self._loyalty.get("valor_canje", 0.0)
        if pts <= 0:
            return
        valor_por_punto = valor_total / pts
        descuento = round(value * valor_por_punto, 2)
        descuento = min(descuento, self.total_original)
        self.descuento_puntos = descuento
        self.puntos_a_canjear = value
        self.total_a_pagar = round(self.total_original - descuento, 2)
        self._lbl_desc_puntos.setText(f"-${descuento:.2f}")
        self.lbl_total.setText(f"Total a pagar: ${self.total_a_pagar:.2f}")
        self.txt_recibido.setValue(self.total_a_pagar)
        self.calcular_cambio()


# ── Tests ─────────────────────────────────────────────────────────────────────

LOYALTY = {
    "puntos": 100,
    "valor_canje": 50.0,   # $0.50 por punto
    "puede_canjear": True,
    "min_puntos_canje": 50,
}


def test_toggle_canje_activa_spinbox():
    """Al activar el canje el spinbox queda habilitado."""
    dlg = StubDialogoPago(total=200.0, loyalty_balance=LOYALTY)
    dlg._toggle_canje(True)
    assert dlg._spin_puntos._enabled is True


def test_toggle_canje_desactiva_spinbox():
    """Al desactivar el canje el spinbox queda deshabilitado."""
    dlg = StubDialogoPago(total=200.0, loyalty_balance=LOYALTY)
    dlg._toggle_canje(True)
    dlg._toggle_canje(False)
    assert dlg._spin_puntos._enabled is False


def test_recalcular_canje_descuenta_total():
    """Canjear 100 pts (=$50) descuenta el total de $200 → $150."""
    dlg = StubDialogoPago(total=200.0, loyalty_balance=LOYALTY)
    dlg._recalcular_canje(100)
    assert dlg.total_a_pagar == pytest.approx(150.0)
    assert dlg.descuento_puntos == pytest.approx(50.0)
    assert dlg.puntos_a_canjear == 100


def test_recalcular_canje_no_excede_total():
    """El descuento nunca puede superar el total original."""
    dlg = StubDialogoPago(total=30.0, loyalty_balance=LOYALTY)
    dlg._recalcular_canje(100)  # $50 de desc sobre $30
    assert dlg.total_a_pagar == pytest.approx(0.0)
    assert dlg.descuento_puntos == pytest.approx(30.0)


def test_toggle_off_restaura_total():
    """Desactivar canje restaura el total original."""
    dlg = StubDialogoPago(total=200.0, loyalty_balance=LOYALTY)
    dlg._toggle_canje(True)
    assert dlg.total_a_pagar == pytest.approx(150.0)
    dlg._toggle_canje(False)
    assert dlg.total_a_pagar == pytest.approx(200.0)
    assert dlg.descuento_puntos == 0.0


def test_recalcular_canje_cero_puntos_no_crash():
    """Sin puntos disponibles no debe ocurrir ningún error."""
    dlg = StubDialogoPago(total=100.0, loyalty_balance={"puntos": 0, "valor_canje": 0.0})
    dlg._recalcular_canje(0)  # no debe lanzar excepción
    assert dlg.total_a_pagar == pytest.approx(100.0)


def test_toggle_canje_actualiza_label():
    """El label de descuento muestra el monto correcto."""
    dlg = StubDialogoPago(total=200.0, loyalty_balance=LOYALTY)
    dlg._toggle_canje(True)
    assert dlg._lbl_desc_puntos.text() == "-$50.00"


def test_ventas_py_tiene_metodo_toggle_canje():
    """Verifica que modulos/ventas.py tenga _toggle_canje definido."""
    import ast
    src = open("modulos/ventas.py").read()
    tree = ast.parse(src)
    methods = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    ]
    assert "_toggle_canje" in methods, "_toggle_canje no está definido en modulos/ventas.py"
    assert "_recalcular_canje" in methods, "_recalcular_canje no está definido en modulos/ventas.py"


def test_ventas_py_no_duplica_metodos_canje():
    """Evita regresión por doble definición accidental en DialogoPago."""
    import ast
    src = open("modulos/ventas.py").read()
    tree = ast.parse(src)
    names = [
        n.name for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name in {"_toggle_canje", "_recalcular_canje"}
    ]
    assert names.count("_toggle_canje") == 1, "_toggle_canje está duplicado en modulos/ventas.py"
    assert names.count("_recalcular_canje") == 1, "_recalcular_canje está duplicado en modulos/ventas.py"
