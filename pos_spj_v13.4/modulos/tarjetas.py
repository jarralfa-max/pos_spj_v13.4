# modulos/tarjetas.py — SPJ POS v13.2
"""
ModuloTarjetas — gestión de tarjetas de fidelidad físicas.
Muestra el módulo completo LoyaltyCardDesigner que incluye:
  🎨 Diseñador con vista previa CR80 en tiempo real
  ⚙️  Config QR (ID + web + WhatsApp + redes sociales)
  🖨️  Generar Lote PDF (8 tarjetas/página para imprenta)
  📋 Emitidas — asignación a clientes
  📦 Historial Lotes
"""
from __future__ import annotations
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from modulos.spj_styles import spj_btn

class ModuloTarjetas(QWidget):
    """Wrapper que carga el diseñador completo de tarjetas."""

    def __init__(self, container, parent=None):
        super().__init__(parent)
        self.container   = container
        self.sucursal_id = 1
        self.usuario     = ""
        self._inner      = None
        self._build()

    def set_usuario_actual(self, u: str, r: str = "") -> None:
        self.usuario = u
        if self._inner and hasattr(self._inner, 'set_usuario_actual'):
            self._inner.set_usuario_actual(u, r)

    def set_sucursal(self, sid: int, nombre: str = "") -> None:
        self.sucursal_id = sid
        if self._inner and hasattr(self._inner, 'set_sucursal'):
            self._inner.set_sucursal(sid, nombre)

    def _build(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        try:
            from modulos.loyalty_card_designer import ModuloLoyaltyCardDesigner
            self._inner = ModuloLoyaltyCardDesigner(
                container=self.container,
                conexion=self.container.db,
                parent=self
            )
            lay.addWidget(self._inner)
            self._normalizar_botones_tarjetas()
        except Exception as e:
            lbl = QLabel(f"Error cargando diseñador de tarjetas:\n{e}")
            lbl.setStyleSheet("color:#e74c3c; font-size:13px; padding:20px;")
            lay.addWidget(lbl)

    def _normalizar_botones_tarjetas(self) -> None:
        """
        Asegura que botones sin texto tengan nombre/tooltip accesible.
        Evita controles anónimos en el módulo de tarjetas.
        """
        if not self._inner:
            return
        for btn in self._inner.findChildren(QPushButton):
            txt = (btn.text() or "").strip()
            tip = (btn.toolTip() or "").strip()
            if not txt:
                if not tip:
                    tip = "Acción de tarjeta"
                    btn.setToolTip(tip)
                btn.setAccessibleName(tip)
