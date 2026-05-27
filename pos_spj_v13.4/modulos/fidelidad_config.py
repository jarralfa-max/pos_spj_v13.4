# modulos/fidelidad_config.py — SPJ POS v13.30
"""
Módulo UNIFICADO de Fidelización de Clientes.

Consolida en un solo módulo:
  - Growth Engine (metas, misiones, config, finanzas, clientes)
  - Diseñador de Tarjetas (diseño, QR, lotes PDF, emitidas)
  - Referidos (programa de referidos entre clientes)
  - Cumpleaños (notificaciones automáticas con cupón)
  - Clientes en Riesgo (detección de abandono y win-back)

Antes eran 4 entradas de menú duplicadas; ahora es 1.
"""
from __future__ import annotations
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget,
    QPushButton, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QLineEdit, QFormLayout,
    QGroupBox, QSpinBox, QDialog, QDialogButtonBox, QDateEdit,
    QComboBox,
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QColor, QFont
import logging
from modulos.design_tokens import Colors, Spacing, Typography, Borders
from modulos.ui_components import (
    create_heading, create_primary_button, create_success_button,
    create_danger_button, create_secondary_button, apply_tooltip,
    PageHeader, Toast,
)

logger = logging.getLogger("spj.fidelidad_unified")


class ModuloFidelidadConfig(QWidget):
    """Módulo unificado de fidelización — reemplaza Growth Engine + Tarjetas duplicados."""

    def __init__(self, container, parent=None):
        super().__init__(parent)
        self.container   = container
        self.sucursal_id = getattr(container, 'sucursal_id', 1)
        self.usuario     = ""
        self._ge_widget  = None  # Growth Engine widget (lazy)
        self._build_ui()

    def set_usuario_actual(self, u: str, r: str = "") -> None:
        self.usuario = u
        if self._ge_widget and hasattr(self._ge_widget, 'set_usuario_actual'):
            self._ge_widget.set_usuario_actual(u, r)

    def set_sucursal(self, sid: int, nombre: str = "") -> None:
        self.sucursal_id = sid
        if self._ge_widget:
            self._ge_widget.sucursal_id = sid

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        # Header
        hdr = QHBoxLayout()
        titulo = QLabel("⭐ Centro de Fidelización")
        titulo.setObjectName("heading")
        hdr.addWidget(titulo)
        hdr.addStretch()
        lay.addLayout(hdr)

        # Tabs principales
        self.tabs = QTabWidget()
        self.tabs.setObjectName("tabWidget")
        self.tabs.currentChanged.connect(self._on_tab_change)

        # v13.30 FIX: _tabs_loaded MUST exist before addTab triggers currentChanged
        self._tabs_loaded = set()

        # Tab placeholders (lazy load)
        self.tab_growth = QWidget()
        self.tab_referidos = QWidget()
        self.tab_cumples = QWidget()
        self.tab_riesgo = QWidget()

        self.tabs.addTab(self.tab_growth,    "🎯 Metas y Misiones")
        self.tabs.addTab(self.tab_referidos, "🤝 Referidos")
        self.tabs.addTab(self.tab_cumples,   "🎂 Cumpleaños")
        self.tabs.addTab(self.tab_riesgo,    "⚠️ Retención")

        lay.addWidget(self.tabs)

    def _on_tab_change(self, idx):
        if idx == 0 and 0 not in self._tabs_loaded:
            self._load_growth_engine()
            self._tabs_loaded.add(0)
        elif idx == 1 and 1 not in self._tabs_loaded:
            self._build_tab_referidos()
            self._tabs_loaded.add(1)
        elif idx == 2 and 2 not in self._tabs_loaded:
            self._build_tab_cumples()
            self._tabs_loaded.add(2)
        elif idx == 3 and 3 not in self._tabs_loaded:
            self._build_tab_riesgo()
            self._tabs_loaded.add(3)

    # ── Lazy loaders ──────────────────────────────────────────────────────────

    def _load_growth_engine(self):
        lay = QVBoxLayout(self.tab_growth)
        lay.setContentsMargins(0, 0, 0, 0)
        try:
            from modulos.modulo_growth_engine import ModuloGrowthEngine
            self._ge_widget = ModuloGrowthEngine(container=self.container, parent=self.tab_growth)
            lay.addWidget(self._ge_widget)
        except Exception as e:
            lay.addWidget(QLabel(f"Error cargando Growth Engine:\n{e}"))

    # ── Tab: Programa de Referidos ────────────────────────────────────────────

    def _build_tab_referidos(self):
        lay = QVBoxLayout(self.tab_referidos)
        lay.setSpacing(10)

        lay.addWidget(QLabel(
            "🤝 Programa de Referidos\n"
            "Cuando un cliente refiere a otro y el referido hace su primera compra,\n"
            "ambos ganan estrellas de bonificación."))

        grp = QGroupBox("Configuración del programa")
        form = QFormLayout(grp)
        self.spin_ref_referidor = QSpinBox()
        self.spin_ref_referidor.setRange(0, 1000); self.spin_ref_referidor.setValue(50)
        self.spin_ref_referidor.setSuffix(" estrellas")
        form.addRow("Bono para quien refiere:", self.spin_ref_referidor)
        self.spin_ref_referido = QSpinBox()
        self.spin_ref_referido.setRange(0, 1000); self.spin_ref_referido.setValue(25)
        self.spin_ref_referido.setSuffix(" estrellas")
        form.addRow("Bono para el referido:", self.spin_ref_referido)
        self.spin_ref_max = QSpinBox()
        self.spin_ref_max.setRange(1, 100); self.spin_ref_max.setValue(10)
        self.spin_ref_max.setSuffix(" referidos/mes")
        form.addRow("Máximo por mes:", self.spin_ref_max)
        lay.addWidget(grp)

        btn_save = create_success_button(self, "💾 Guardar configuración", "Guardar configuración del programa de referidos")
        btn_save.clicked.connect(self._guardar_config_referidos)
        lay.addWidget(btn_save)

        # Tabla de referidos recientes
        lay.addWidget(QLabel("Últimos referidos registrados:"))
        self.tbl_referidos = QTableWidget()
        self.tbl_referidos.setColumnCount(5)
        self.tbl_referidos.setHorizontalHeaderLabels(
            ["Fecha", "Referidor", "Referido", "Bono", "Estado"])
        self.tbl_referidos.setEditTriggers(QAbstractItemView.NoEditTriggers)
        hh = self.tbl_referidos.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        lay.addWidget(self.tbl_referidos)
        self._cargar_config_referidos()
        self._cargar_referidos()

    def _guardar_config_referidos(self):
        try:
            self.container.loyalty_service.save_referral_config(
                self.spin_ref_referidor.value(),
                self.spin_ref_referido.value(),
                self.spin_ref_max.value(),
            )
            Toast.success(self, "Configuración guardada", "Programa de referidos actualizado.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _cargar_config_referidos(self):
        try:
            cfg = self.container.loyalty_service.get_referral_config()
            self.spin_ref_referidor.setValue(int(cfg.get('ref_bono_referidor', 50)))
            self.spin_ref_referido.setValue(int(cfg.get('ref_bono_referido', 25)))
            self.spin_ref_max.setValue(int(cfg.get('ref_max_mensual', 10)))
        except Exception:
            pass

    def _cargar_referidos(self):
        try:
            rows = self.container.loyalty_service.list_referrals(limit=50)
            self.tbl_referidos.setRowCount(len(rows))
            for i, r in enumerate(rows):
                for j, v in enumerate(r):
                    self.tbl_referidos.setItem(i, j, QTableWidgetItem(str(v or "")))
        except Exception as e:
            logger.debug("_cargar_referidos: %s", e)

    # ── Tab: Cumpleaños ───────────────────────────────────────────────────────

    def _build_tab_cumples(self):
        lay = QVBoxLayout(self.tab_cumples)
        lay.setSpacing(10)

        lay.addWidget(QLabel(
            "🎂 Notificaciones de Cumpleaños\n"
            "Envía automáticamente un cupón de descuento vía WhatsApp\n"
            "a los clientes que cumplen años esta semana."))

        grp = QGroupBox("Configuración")
        form = QFormLayout(grp)
        self.spin_cumple_bono = QSpinBox()
        self.spin_cumple_bono.setRange(0, 500); self.spin_cumple_bono.setValue(100)
        self.spin_cumple_bono.setSuffix(" estrellas")
        form.addRow("Bono de cumpleaños:", self.spin_cumple_bono)
        self.txt_cumple_msg = QLineEdit("🎂 ¡Feliz cumpleaños {nombre}! Te regalamos {puntos} estrellas.")
        form.addRow("Mensaje WA:", self.txt_cumple_msg)
        lay.addWidget(grp)

        btn_save = create_success_button(self, "💾 Guardar", "Guardar configuración de cumpleaños")
        btn_save.clicked.connect(self._guardar_config_cumples)
        lay.addWidget(btn_save)

        # Próximos cumpleaños
        lay.addWidget(QLabel("Cumpleaños próximos 7 días:"))
        self.tbl_cumples = QTableWidget()
        self.tbl_cumples.setColumnCount(4)
        self.tbl_cumples.setHorizontalHeaderLabels(["Cliente", "Fecha Nac.", "Teléfono", "Nivel"])
        self.tbl_cumples.setEditTriggers(QAbstractItemView.NoEditTriggers)
        hh = self.tbl_cumples.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        lay.addWidget(self.tbl_cumples)

        btn_enviar = create_primary_button(self, "📱 Enviar felicitaciones ahora", "Enviar mensajes de cumpleaños vía WhatsApp")
        btn_enviar.clicked.connect(self._enviar_cumples)
        lay.addWidget(btn_enviar)

        self._cargar_config_cumples()
        self._cargar_cumples()

    def _guardar_config_cumples(self):
        try:
            self.container.loyalty_service.save_birthday_config(
                bono_estrellas=self.spin_cumple_bono.value(),
                mensaje_wa=self.txt_cumple_msg.text(),
            )
            Toast.success(self, "Configuración guardada", "Programa de cumpleaños actualizado.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _cargar_config_cumples(self):
        try:
            cfg = self.container.loyalty_service.get_birthday_config()
            try: self.spin_cumple_bono.setValue(int(cfg.get('cumple_bono_estrellas', '100')) )
            except: pass
            self.txt_cumple_msg.setText(cfg.get('cumple_mensaje_wa',
                '🎂 ¡Feliz cumpleaños {nombre}! Te regalamos {puntos} estrellas.'))
        except Exception:
            pass

    def _cargar_cumples(self):
        try:
            rows = self.container.loyalty_service.list_upcoming_birthdays(7)
            self.tbl_cumples.setRowCount(len(rows))
            for i, r in enumerate(rows):
                for j, v in enumerate(r):
                    self.tbl_cumples.setItem(i, j, QTableWidgetItem(str(v or "")))
        except Exception as e:
            logger.debug("_cargar_cumples: %s", e)

    def _enviar_cumples(self):
        Toast.info(
            self, "📱 Enviar felicitaciones",
            "Requiere módulo WhatsApp configurado.",
        )

    # ── Tab: Retención / Clientes en Riesgo ───────────────────────────────────

    def _build_tab_riesgo(self):
        lay = QVBoxLayout(self.tab_riesgo)
        lay.setSpacing(10)

        lay.addWidget(QLabel(
            "⚠️ Detección de Clientes en Riesgo de Abandono\n"
            "Identifica clientes que no han comprado recientemente para campañas de win-back."))

        grp = QGroupBox("Parámetros")
        form = QFormLayout(grp)
        self.spin_dias_inactivo = QSpinBox()
        self.spin_dias_inactivo.setRange(7, 365); self.spin_dias_inactivo.setValue(30)
        self.spin_dias_inactivo.setSuffix(" días sin comprar")
        form.addRow("Umbral de riesgo:", self.spin_dias_inactivo)
        lay.addWidget(grp)

        btn_analizar = create_danger_button(self, "🔍 Analizar clientes en riesgo", "Identificar clientes que no han comprado recientemente")
        btn_analizar.clicked.connect(self._analizar_riesgo)
        lay.addWidget(btn_analizar)

        self.tbl_riesgo = QTableWidget()
        self.tbl_riesgo.setColumnCount(5)
        self.tbl_riesgo.setHorizontalHeaderLabels(
            ["Cliente", "Última Compra", "Días Inactivo", "Total Histórico", "Teléfono"])
        self.tbl_riesgo.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_riesgo.setAlternatingRowColors(True)
        hh = self.tbl_riesgo.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        lay.addWidget(self.tbl_riesgo)

        self.lbl_riesgo_resumen = QLabel("")
        self.lbl_riesgo_resumen.setObjectName("textDanger")
        lay.addWidget(self.lbl_riesgo_resumen)

    def _analizar_riesgo(self):
        dias = self.spin_dias_inactivo.value()
        try:
            rows = self.container.loyalty_service.list_at_risk_customers(days_without_sale=dias, limit=200)

            self.tbl_riesgo.setRowCount(len(rows))
            for i, r in enumerate(rows):
                for j, v in enumerate(r):
                    val = v
                    if j == 3 and v is not None:
                        val = f"${float(v):.2f}"
                    elif j == 2 and v is not None:
                        val = str(int(v))
                    it = QTableWidgetItem(str(val or "Nunca"))
                    if j == 2 and v is not None and int(v) > 60:
                        it.setForeground(QColor(Colors.DANGER_HOVER))
                        it.setFont(QFont("Arial", -1, QFont.Bold))
                    self.tbl_riesgo.setItem(i, j, it)

            self.lbl_riesgo_resumen.setText(
                f"⚠️ {len(rows)} clientes con {dias}+ días sin comprar")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))
