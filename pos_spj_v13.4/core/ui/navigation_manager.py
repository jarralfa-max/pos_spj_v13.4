
# core/ui/navigation_manager.py
from __future__ import annotations
import logging
from typing import Dict, Optional, Callable
from PyQt5.QtWidgets import QStackedWidget, QPushButton, QWidget
from PyQt5.QtCore import QObject, pyqtSignal

logger = logging.getLogger("spj.ui.nav")

class NavigationManager(QObject):
    modulo_cambiado = pyqtSignal(str)

    def __init__(self, stacked_widget, botones, parent=None):
        super().__init__(parent)
        self.stacked  = stacked_widget
        self.botones  = botones
        self._current = None
        self._guards  = []

    def add_guard(self, fn):
        self._guards.append(fn)

    def registrar_modulo(self, nombre, widget):
        self.stacked.addWidget(widget)
        widget.hide()
        widget._nav_key = nombre

    def ir_a(self, nombre):
        for g in self._guards:
            try:
                if not g(nombre): return False
            except Exception: pass
        for i in range(self.stacked.count()):
            w = self.stacked.widget(i)
            if getattr(w, "_nav_key", None) == nombre:
                self._activar(nombre, i, w)
                return True
        logger.warning("Modulo no encontrado: %s", nombre)
        return False

    def _activar(self, nombre, index, widget):
        self._reset_botones()
        if nombre in self.botones:
            b = self.botones[nombre]
            b.setProperty("class","botonModuloActivo")
            b.style().unpolish(b); b.style().polish(b)
        self.stacked.setCurrentIndex(index)
        widget.show()
        for fn in ("on_activate","actualizar_datos","refresh"):
            if hasattr(widget, fn):
                try: getattr(widget, fn)()
                except Exception: pass
                break
        self._current = nombre
        self.modulo_cambiado.emit(nombre)

    def _reset_botones(self):
        for b in self.botones.values():
            b.setProperty("class","botonModulo")
            b.style().unpolish(b); b.style().polish(b)

    def ir_inicio(self):
        self.stacked.setCurrentIndex(0)
        self._reset_botones()
        self._current = None

    def set_enabled(self, enabled):
        for b in self.botones.values():
            b.setEnabled(enabled)

    @property
    def modulo_actual(self): return self._current
