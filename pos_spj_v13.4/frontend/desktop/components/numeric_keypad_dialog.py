"""Diálogo estándar de captura numérica con teclado tipo calculadora.

Cumple SPJ_REFACTOR_SKILL.md:
- Regla 22: el campo numérico inicia en cero/vacío (sin default arbitrario).
- Regla 23: no usa defaults arbitrarios (1, 7, 10, 30, 50, 100…).
- UI en español; componente reutilizable (FASE 3).

Reemplaza el uso crudo de QInputDialog.getDouble para capturar valores numéricos
(cantidades, pesos, montos, porcentajes). Acepta entrada por teclado físico
(báscula/USB) y por el teclado en pantalla (touch/mouse), útil en el contexto POS.
El teclado en pantalla es desplegable (toggle) y con botones grandes (táctil).

Uso (drop-in, misma forma que QInputDialog.getDouble):

    from frontend.desktop.components.numeric_keypad_dialog import NumericKeypadDialog
    monto, ok = NumericKeypadDialog.get_value(
        self, "Cobro global CxC", "Monto total:", decimals=2, unidad="$")
    if ok and monto > 0:
        ...

`permitir_cero=True` habilita confirmar 0 (p.ej. fondo de caja inicial en 0).
"""
from __future__ import annotations

from PyQt5.QtCore import Qt, QLocale
from PyQt5.QtGui import QDoubleValidator
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QWidget, QSizePolicy,
)


class NumericKeypadDialog(QDialog):
    """Popup de captura numérica con teclado tipo calculadora (grande, desplegable)."""

    def __init__(
        self,
        parent=None,
        *,
        titulo: str = "Valor",
        mensaje: str = "Ingrese el valor:",
        decimals: int = 3,
        minimo: float = 0.0,
        maximo: float = 999999999.0,
        unidad: str = "",
        inicial: float = 0.0,
        permitir_cero: bool = False,
    ) -> None:
        super().__init__(parent)
        self._decimals = max(0, int(decimals))
        self._minimo = float(minimo)
        self._maximo = float(maximo)
        self._permitir_cero = bool(permitir_cero)
        self.setWindowTitle(titulo)
        self.setModal(True)
        self.setObjectName("numericKeypadDialog")
        self.setMinimumWidth(340)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        lbl = QLabel(mensaje)
        lbl.setWordWrap(True)
        lbl.setObjectName("numericKeypadPrompt")
        lay.addWidget(lbl)

        # ── Display (inicia vacío = cero absoluto, Regla 22) ────────────────────
        disp_row = QHBoxLayout()
        disp_row.setSpacing(6)
        self.display = QLineEdit()
        self.display.setObjectName("numericKeypadDisplay")
        self.display.setAlignment(Qt.AlignRight)
        self.display.setPlaceholderText("0")
        self.display.setClearButtonEnabled(False)
        # Validador: acepta sólo números en [minimo, maximo] con los decimales dados.
        # Locale "C" para forzar el punto decimal (independiente del sistema).
        validator = QDoubleValidator(self._minimo, self._maximo, self._decimals, self)
        validator.setNotation(QDoubleValidator.StandardNotation)
        validator.setLocale(QLocale.c())
        self.display.setValidator(validator)
        self.display.setLocale(QLocale.c())
        f = self.display.font()
        f.setPointSize(max(14, f.pointSize() + 6))
        f.setBold(True)
        self.display.setFont(f)
        self.display.setMinimumHeight(44)
        disp_row.addWidget(self.display, 1)
        if unidad:
            u = QLabel(unidad)
            u.setObjectName("numericKeypadUnit")
            disp_row.addWidget(u)
        lay.addLayout(disp_row)

        # Sólo pre-carga un valor inicial cuando se edita un valor existente
        # (> 0). Nunca inyecta un default arbitrario en una captura nueva.
        if inicial and inicial > 0:
            self.display.setText(self._format(inicial))
            self.display.selectAll()

        # ── Toggle: mostrar/ocultar el teclado (desplegable) ────────────────────
        self._btn_toggle = QPushButton("⌨  Ocultar teclado")
        self._btn_toggle.setObjectName("secondaryBtn")
        self._btn_toggle.setCheckable(True)
        self._btn_toggle.setChecked(True)
        self._btn_toggle.setFocusPolicy(Qt.NoFocus)
        self._btn_toggle.setMinimumHeight(36)
        self._btn_toggle.toggled.connect(self._toggle_teclado)
        lay.addWidget(self._btn_toggle)

        # ── Panel del teclado numérico (calculadora, botones grandes touch) ─────
        self._keypad_panel = QWidget()
        self._keypad_panel.setObjectName("numericKeypadPanel")
        panel_lay = QVBoxLayout(self._keypad_panel)
        panel_lay.setContentsMargins(0, 0, 0, 0)
        panel_lay.setSpacing(8)
        grid = QGridLayout()
        grid.setSpacing(8)
        botones = [
            ("7", 0, 0), ("8", 0, 1), ("9", 0, 2),
            ("4", 1, 0), ("5", 1, 1), ("6", 1, 2),
            ("1", 2, 0), ("2", 2, 1), ("3", 2, 2),
            ("0", 3, 0), (".", 3, 1), ("⌫", 3, 2),
        ]
        for texto, r, c in botones:
            b = QPushButton(texto)
            b.setObjectName("numericKeypadBtn")
            b.setFocusPolicy(Qt.NoFocus)
            b.setMinimumSize(76, 76)   # objetivo táctil grande
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            bf = b.font(); bf.setPointSize(26); bf.setBold(True); b.setFont(bf)
            if texto == "⌫":
                b.clicked.connect(self._retroceso)
            elif texto == ".":
                b.clicked.connect(self._punto_decimal)
            else:
                b.clicked.connect(lambda _=False, d=texto: self._agregar_digito(d))
            grid.addWidget(b, r, c)
        panel_lay.addLayout(grid)

        # Botón limpiar (C) a todo lo ancho
        btn_clear = QPushButton("C  (Limpiar)")
        btn_clear.setObjectName("secondaryBtn")
        btn_clear.setFocusPolicy(Qt.NoFocus)
        btn_clear.setMinimumHeight(48)
        cf = btn_clear.font(); cf.setPointSize(15); cf.setBold(True); btn_clear.setFont(cf)
        btn_clear.clicked.connect(self._limpiar)
        panel_lay.addWidget(btn_clear)
        lay.addWidget(self._keypad_panel)

        # ── Aceptar / Cancelar ──────────────────────────────────────────────────
        acc = QHBoxLayout()
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.setObjectName("secondaryBtn")
        self.btn_cancel.setMinimumHeight(40)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok = QPushButton("Aceptar")
        self.btn_ok.setObjectName("primaryBtn")
        self.btn_ok.setMinimumHeight(40)
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self._aceptar)
        acc.addWidget(self.btn_cancel, 1)
        acc.addWidget(self.btn_ok, 1)
        lay.addLayout(acc)

        self.display.textChanged.connect(self._sync_ok_enabled)
        self._sync_ok_enabled()
        self.display.setFocus()

    # ── Formato / valor ─────────────────────────────────────────────────────────
    def _format(self, v: float) -> str:
        s = f"{float(v):.{self._decimals}f}" if self._decimals else str(int(round(v)))
        # Recorta ceros y punto sobrantes (12.500 -> 12.5, 12.000 -> 12)
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return s

    def valor(self) -> float:
        txt = self.display.text().strip()
        if not txt or txt == ".":
            return 0.0
        try:
            return float(txt)
        except ValueError:
            return 0.0

    def _valido(self) -> bool:
        v = self.valor()
        if not (self._minimo <= v <= self._maximo):
            return False
        return self._permitir_cero or v > 0

    # ── Entrada por teclado en pantalla ─────────────────────────────────────────
    def _agregar_digito(self, d: str) -> None:
        actual = self.display.text()
        # Si hay una selección (p.ej. valor inicial pre-cargado), la reemplaza.
        if self.display.hasSelectedText():
            actual = ""
        # Respeta el límite de decimales.
        if "." in actual and self._decimals >= 0:
            entero, _, frac = actual.partition(".")
            if len(frac) >= self._decimals:
                return
        nuevo = actual + d
        # El QDoubleValidator trata los valores > máximo como "Intermedio", no como
        # inválidos, así que se rechaza el exceso de máximo explícitamente.
        try:
            if float(nuevo) > self._maximo:
                return
        except ValueError:
            pass
        # Deja que el validador rechace lo que no cumpla rango/decimales.
        if self.display.validator().validate(nuevo, len(nuevo))[0] != 0:  # not Invalid
            self.display.setText(nuevo)

    def _punto_decimal(self) -> None:
        if self._decimals <= 0:
            return
        actual = self.display.text()
        if self.display.hasSelectedText():
            actual = ""
        if "." in actual:
            return
        if not actual:
            actual = "0"
        self.display.setText(actual + ".")

    def _retroceso(self) -> None:
        if self.display.hasSelectedText():
            self.display.clear()
            return
        self.display.setText(self.display.text()[:-1])

    def _limpiar(self) -> None:
        self.display.clear()

    def _toggle_teclado(self, visible: bool) -> None:
        """Muestra/oculta el teclado en pantalla (desplegable). Útil cuando se
        captura con teclado físico o báscula y no se necesita el teclado táctil."""
        self._keypad_panel.setVisible(visible)
        self._btn_toggle.setText("⌨  Ocultar teclado" if visible else "⌨  Mostrar teclado")
        # Reajusta el diálogo al colapsar/expandir el panel.
        self.adjustSize()

    def _sync_ok_enabled(self) -> None:
        self.btn_ok.setEnabled(self._valido())

    def _aceptar(self) -> None:
        if self._valido():
            self.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self.btn_ok.isEnabled():
                self._aceptar()
            return
        super().keyPressEvent(event)

    # ── API estilo QInputDialog.getDouble ───────────────────────────────────────
    @classmethod
    def get_value(
        cls,
        parent=None,
        titulo: str = "Valor",
        mensaje: str = "Ingrese el valor:",
        *,
        decimals: int = 3,
        minimo: float = 0.0,
        maximo: float = 999999999.0,
        unidad: str = "",
        inicial: float = 0.0,
        permitir_cero: bool = False,
    ) -> tuple[float, bool]:
        """Devuelve (valor, ok). Compatible en forma con QInputDialog.getDouble."""
        dlg = cls(
            parent, titulo=titulo, mensaje=mensaje, decimals=decimals,
            minimo=minimo, maximo=maximo, unidad=unidad, inicial=inicial,
            permitir_cero=permitir_cero,
        )
        ok = dlg.exec_() == QDialog.Accepted
        return (dlg.valor() if ok else 0.0, ok)
