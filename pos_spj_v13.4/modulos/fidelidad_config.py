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
    QComboBox, QInputDialog, QDoubleSpinBox, QCheckBox, QTextEdit, QFileDialog,
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QColor
import logging
import csv
from modulos.design_tokens import Colors, Spacing, Typography, Borders
from modulos.ui_components import (
    create_heading, create_primary_button, create_success_button,
    create_danger_button, create_secondary_button, apply_tooltip,
    PageHeader, Toast, create_kpi_bar, create_kpi_card, EmptyStateWidget,
)

logger = logging.getLogger("spj.fidelidad_unified")


class ModuloFidelidadConfig(QWidget):
    """Módulo unificado de fidelización — reemplaza Growth Engine + Tarjetas duplicados."""

    def __init__(self, container, parent=None):
        super().__init__(parent)
        self.container   = container
        self.sucursal_id = getattr(container, 'sucursal_id', '') or ''
        self.usuario     = ""
        self._ge_widget  = None  # Growth Engine widget (lazy)
        self._last_raffle_winner_by_id = {}
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
        self.kpi_bar = create_kpi_bar(self, [])
        lay.addWidget(self.kpi_bar)

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
        self.tab_raffles = QWidget()

        self.tabs.addTab(self.tab_growth,    "🎯 Metas y Misiones")
        self.tabs.addTab(self.tab_referidos, "🤝 Referidos")
        self.tabs.addTab(self.tab_cumples,   "🎂 Cumpleaños")
        self.tabs.addTab(self.tab_riesgo,    "⚠️ Retención")
        self.tabs.addTab(self.tab_raffles,   "🎟️ Rifas y Sorteos")

        lay.addWidget(self.tabs)
        self._refresh_dashboard_kpis()

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
        elif idx == 4 and 4 not in self._tabs_loaded:
            self._build_tab_raffles()
            self._tabs_loaded.add(4)

    def _refresh_dashboard_kpis(self):
        try:
            k = self.container.loyalty_service.get_dashboard_kpis()
        except Exception:
            k = {}
        items = [
            {"title": "Clientes con puntos", "value": k.get("clientes_con_puntos", 0), "icon": "👥", "tone": "primary"},
            {"title": "Puntos activos", "value": k.get("puntos_activos", 0), "icon": "⭐", "tone": "info"},
            {"title": "Pasivo operativo", "value": f"${float(k.get('pasivo_operativo', 0.0)):,.2f}", "icon": "💰", "tone": "warning"},
            {"title": "Emitidos mes", "value": k.get("puntos_emitidos_mes", 0), "icon": "📈", "tone": "success"},
            {"title": "Canjeados mes", "value": k.get("puntos_canjeados_mes", 0), "icon": "🎁", "tone": "accent"},
            {"title": "Cumples próximos", "value": k.get("cumples_7_dias", 0), "icon": "🎂", "tone": "primary"},
            {"title": "Clientes en riesgo", "value": k.get("clientes_en_riesgo", 0), "icon": "⚠️", "tone": "danger"},
        ]
        old = self.kpi_bar
        self.kpi_bar = create_kpi_bar(self, items)
        self.layout().replaceWidget(old, self.kpi_bar)
        old.deleteLater()

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
                        font = it.font()
                        font.setBold(True)
                        it.setFont(font)
                    self.tbl_riesgo.setItem(i, j, it)

            self.lbl_riesgo_resumen.setText(
                f"⚠️ {len(rows)} clientes con {dias}+ días sin comprar")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def _build_tab_raffles(self):
        lay = QVBoxLayout(self.tab_raffles)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(Spacing.SM)
        lay.setAlignment(Qt.AlignTop)
        title = QLabel("🎟️ Gestión de Rifas y Sorteos")
        title.setObjectName("subheading")
        lay.addWidget(title)
        self.raffle_kpi_bar = create_kpi_bar(self.tab_raffles, [])
        self.raffle_kpi_bar.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.raffle_kpi_bar, 0)
        btn_row = QHBoxLayout()
        self.btn_nueva_rifa = create_primary_button(self, "➕ Nueva rifa")
        self.btn_nueva_rifa.clicked.connect(self._on_nueva_rifa)
        self.btn_reservar = create_secondary_button(self, "💰 Reservar presupuesto")
        self.btn_activar = create_secondary_button(self, "✅ Activar")
        self.btn_cerrar = create_secondary_button(self, "🔒 Cerrar")
        self.btn_ganador = create_secondary_button(self, "🏆 Seleccionar ganador")
        self.btn_entregar = create_secondary_button(self, "📦 Marcar premio entregado")
        self.btn_ver_boletos = create_secondary_button(self, "🎫 Ver boletos")
        self.btn_ver_boletos.clicked.connect(self._on_ver_boletos)
        btn_row.addWidget(self.btn_nueva_rifa)
        btn_row.addWidget(self.btn_reservar)
        btn_row.addWidget(self.btn_activar)
        btn_row.addWidget(self.btn_cerrar)
        btn_row.addWidget(self.btn_ganador)
        btn_row.addWidget(self.btn_entregar)
        btn_row.addWidget(self.btn_ver_boletos)
        self.btn_reservar.clicked.connect(self._on_reservar_presupuesto)
        self.btn_activar.clicked.connect(self._on_activar_rifa)
        self.btn_cerrar.clicked.connect(self._on_cerrar_rifa)
        self.btn_ganador.clicked.connect(self._on_seleccionar_ganador)
        self.btn_entregar.clicked.connect(self._on_entregar_premio)
        btn_row.addStretch()
        lay.addLayout(btn_row)
        self.tbl_raffles = QTableWidget()
        self.tbl_raffles.setColumnCount(9)
        self.tbl_raffles.setHorizontalHeaderLabels(["ID", "Nombre", "Premio", "Estado", "Finanzas", "Inicio", "Fin", "Boletos", "Presupuesto"])
        self.tbl_raffles.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_raffles.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_raffles.setAlternatingRowColors(True)
        self.tbl_raffles.itemSelectionChanged.connect(self._update_raffle_actions_state)
        hh = self.tbl_raffles.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        lay.addWidget(self.tbl_raffles)
        self.empty_raffles = EmptyStateWidget(
            "Sin rifas activas",
            "Crea tu primera rifa para campañas especiales y fidelización estacional.",
            "🎟️",
            self.tab_raffles,
        )
        lay.addWidget(self.empty_raffles)
        self._cargar_raffles()
        self._update_raffle_actions_state()



    def _selected_raffle_row(self):
        row = self.tbl_raffles.currentRow()
        if row < 0:
            return None
        vals = []
        for c in range(self.tbl_raffles.columnCount()):
            it = self.tbl_raffles.item(row, c)
            vals.append((it.text() if it else "").strip())
        return {
            "id": vals[0], "nombre": vals[1], "premio": vals[2], "estado": vals[3].lower(),
            "financial_status": vals[4].lower(), "inicio": vals[5], "fin": vals[6],
            "boletos": vals[7], "presupuesto": vals[8],
        }

    def _update_raffle_actions_state(self):
        row = self._selected_raffle_row()
        has = row is not None
        self.btn_reservar.setEnabled(has)
        self.btn_activar.setEnabled(False)
        self.btn_cerrar.setEnabled(False)
        self.btn_ganador.setEnabled(False)
        self.btn_entregar.setEnabled(False)
        if not has:
            return
        estado = row["estado"]
        fin = row["financial_status"]
        self.btn_activar.setEnabled(fin == "reservada" and estado in ("borrador", "inactiva"))
        self.btn_cerrar.setEnabled(estado == "activa")
        self.btn_ganador.setEnabled(estado == "cerrada")
        self.btn_entregar.setEnabled(estado == "cerrada")

    def _cargar_raffles(self):
        resumen = {}
        try:
            resumen = self.container.loyalty_service.get_raffle_summary()
        except Exception as e:
            logger.debug("_cargar_raffles resumen: %s", e)
        kpis = [
            {"title": "Rifas activas", "value": int(resumen.get("rifas_activas", 0) or 0), "icon": "🎟️", "tone": "info"},
            {"title": "Boletos emitidos", "value": int(resumen.get("boletos_emitidos", 0) or 0), "icon": "🎫", "tone": "primary"},
            {"title": "Boletos cancelados", "value": int(resumen.get("boletos_cancelados", 0) or 0), "icon": "🛑", "tone": "warning"},
            {"title": "Premios pendientes", "value": int(resumen.get("premios_pendientes", 0) or 0), "icon": "🏆", "tone": "accent"},
            {"title": "Pasivo promocional", "value": f"${float(resumen.get('pasivo_promocional', 0) or 0):,.2f}", "icon": "💰", "tone": "danger"},
            {"title": "Presupuesto usado", "value": f"${float(resumen.get('presupuesto_usado', 0) or 0):,.2f}", "icon": "📉", "tone": "info"},
            {"title": "ROI estimado", "value": f"{float(resumen.get('roi_estimado', 0) or 0):.2f}%", "icon": "📈", "tone": "success"},
        ]
        old = self.raffle_kpi_bar
        self.raffle_kpi_bar = create_kpi_bar(self.tab_raffles, kpis)
        self.tab_raffles.layout().replaceWidget(old, self.raffle_kpi_bar)
        self.raffle_kpi_bar.setContentsMargins(0, 0, 0, 0)
        old.deleteLater()

        rows = self.container.loyalty_service.list_raffles(limit=50)
        self.tbl_raffles.setRowCount(len(rows))
        for i, r in enumerate(rows):
            for j, v in enumerate(r):
                val = v
                if j == 8:
                    try:
                        val = f"${float(v):,.2f}"
                    except Exception:
                        pass
                self.tbl_raffles.setItem(i, j, QTableWidgetItem(str(val or "")))
        has_data = len(rows) > 0
        self.tbl_raffles.setVisible(has_data)
        self.empty_raffles.setVisible(not has_data)
        self._update_raffle_actions_state()

    def _require_selected_raffle(self):
        row = self._selected_raffle_row()
        if not row:
            Toast.warning(self, "Rifas", "Selecciona una rifa.")
            return None
        return row

    def _on_nueva_rifa(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Nueva rifa / sorteo")
        dlg.resize(860, 640)
        root = QVBoxLayout(dlg)
        tabs = QTabWidget(dlg)
        root.addWidget(tabs)

        # 1) Datos generales
        t1 = QWidget(); f1 = QFormLayout(t1)
        txt_nombre = QLineEdit(); txt_descripcion = QTextEdit()
        dt_inicio = QDateEdit(); dt_inicio.setCalendarPopup(True); dt_inicio.setDate(QDate.currentDate())
        dt_fin = QDateEdit(); dt_fin.setCalendarPopup(True); dt_fin.setDate(QDate.currentDate().addDays(30))
        cmb_sucursal = QSpinBox(); cmb_sucursal.setRange(1, 99999); cmb_sucursal.setValue(str(self.sucursal_id) if str(self.sucursal_id or "").isdigit() else 0)
        f1.addRow("Nombre:", txt_nombre); f1.addRow("Descripción:", txt_descripcion)
        f1.addRow("Fecha inicio:", dt_inicio); f1.addRow("Fecha fin:", dt_fin); f1.addRow("Sucursal:", cmb_sucursal)
        tabs.addTab(t1, "Datos generales")

        # 2) Premios
        t2 = QWidget(); l2 = QVBoxLayout(t2)
        tbl_prizes = QTableWidget(0, 3); tbl_prizes.setHorizontalHeaderLabels(["Nombre", "Cantidad", "Costo estimado"])
        p_nombre = QLineEdit(); p_cantidad = QSpinBox(); p_cantidad.setRange(1, 9999)
        p_costo = QDoubleSpinBox(); p_costo.setRange(0, 99999999); p_costo.setDecimals(2)
        btn_add = QPushButton("Agregar premio")
        def _add_prize():
            if not p_nombre.text().strip(): return
            r = tbl_prizes.rowCount(); tbl_prizes.insertRow(r)
            tbl_prizes.setItem(r, 0, QTableWidgetItem(p_nombre.text().strip()))
            tbl_prizes.setItem(r, 1, QTableWidgetItem(str(p_cantidad.value())))
            tbl_prizes.setItem(r, 2, QTableWidgetItem(str(p_costo.value())))
            p_nombre.clear(); p_cantidad.setValue(1); p_costo.setValue(0)
        btn_add.clicked.connect(_add_prize)
        f2 = QFormLayout(); f2.addRow("Nombre premio:", p_nombre); f2.addRow("Cantidad:", p_cantidad); f2.addRow("Costo estimado:", p_costo); f2.addRow("", btn_add)
        l2.addLayout(f2); l2.addWidget(tbl_prizes); tabs.addTab(t2, "Premios")

        # 3) Presupuesto
        t3 = QWidget(); f3 = QFormLayout(t3)
        presupuesto = QDoubleSpinBox(); presupuesto.setRange(0, 99999999); presupuesto.setDecimals(2)
        ventas_obj = QDoubleSpinBox(); ventas_obj.setRange(0, 99999999); ventas_obj.setDecimals(2)
        roi_obj = QDoubleSpinBox(); roi_obj.setRange(0, 9999); roi_obj.setDecimals(2)
        f3.addRow("Presupuesto máximo:", presupuesto); f3.addRow("Ventas objetivo:", ventas_obj); f3.addRow("ROI objetivo:", roi_obj)
        tabs.addTab(t3, "Presupuesto")

        # 4) Reglas
        t4 = QWidget(); f4 = QFormLayout(t4)
        req_reg = QCheckBox("Requiere cliente registrado")
        min_sale = QDoubleSpinBox(); min_sale.setRange(0, 99999999); min_sale.setDecimals(2)
        strategy = QComboBox(); strategy.addItems(["per_amount", "per_sale", "fixed"])
        amount_per_ticket = QDoubleSpinBox(); amount_per_ticket.setRange(0, 99999999); amount_per_ticket.setDecimals(2)
        tickets_per_sale = QSpinBox(); tickets_per_sale.setRange(0, 99999)
        max_per_sale = QSpinBox(); max_per_sale.setRange(0, 99999)
        max_per_customer = QSpinBox(); max_per_customer.setRange(0, 99999)
        allowed_pm = QLineEdit(); allowed_pm.setPlaceholderText("efectivo,tarjeta,transferencia")
        f4.addRow("", req_reg); f4.addRow("Mínimo compra:", min_sale); f4.addRow("Estrategia:", strategy)
        f4.addRow("Monto por boleto:", amount_per_ticket); f4.addRow("Boletos por venta:", tickets_per_sale)
        f4.addRow("Máximo por venta:", max_per_sale); f4.addRow("Máximo por cliente:", max_per_customer)
        f4.addRow("Formas pago permitidas:", allowed_pm)
        tabs.addTab(t4, "Reglas")

        # 5) Revisión
        t5 = QWidget(); l5 = QVBoxLayout(t5); lbl_review = QLabel("Revisión pendiente...")
        l5.addWidget(lbl_review); tabs.addTab(t5, "Revisión")
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        root.addWidget(btns)
        btns.rejected.connect(dlg.reject)
        def _refresh_review():
            total_prizes = 0.0
            for i in range(tbl_prizes.rowCount()):
                q = float(tbl_prizes.item(i, 1).text() or 0); c = float(tbl_prizes.item(i, 2).text() or 0)
                total_prizes += (q * c)
            ready = bool(txt_nombre.text().strip()) and dt_inicio.date() <= dt_fin.date() and tbl_prizes.rowCount() > 0 and presupuesto.value() > 0
            lbl_review.setText(f"Costo premios: ${total_prizes:,.2f}\nPresupuesto: ${presupuesto.value():,.2f}\nEstado: {'Listo' if ready else 'No listo'}")
        tabs.currentChanged.connect(lambda *_: _refresh_review()); _refresh_review()
        btns.accepted.connect(dlg.accept)
        if dlg.exec_() != QDialog.Accepted:
            return
        try:
            prizes = []
            for i in range(tbl_prizes.rowCount()):
                prizes.append({
                    "nombre": (tbl_prizes.item(i, 0).text() if tbl_prizes.item(i, 0) else "").strip(),
                    "cantidad": int(float(tbl_prizes.item(i, 1).text() if tbl_prizes.item(i, 1) else 0)),
                    "costo_estimado": float(tbl_prizes.item(i, 2).text() if tbl_prizes.item(i, 2) else 0),
                    "orden": i + 1,
                })
            self.container.loyalty_service.create_raffle_with_rules(
                {
                    "nombre": txt_nombre.text().strip(),
                    "descripcion": txt_descripcion.toPlainText().strip(),
                    "premio": (prizes[0]["nombre"] if prizes else ""),
                    "premio_costo_estimado": sum(float(p["costo_estimado"]) * int(p["cantidad"]) for p in prizes),
                    "presupuesto_maximo": presupuesto.value(),
                    "ventas_objetivo": ventas_obj.value(),
                    "roi_objetivo": roi_obj.value(),
                    "monto_por_boleto": amount_per_ticket.value(),
                    "fecha_inicio": f"{dt_inicio.date().toString('yyyy-MM-dd')} 00:00:00",
                    "fecha_fin": f"{dt_fin.date().toString('yyyy-MM-dd')} 23:59:59",
                    "sucursal_id": cmb_sucursal.value(),
                },
                {
                    "requires_registered_customer": 1 if req_reg.isChecked() else 0,
                    "min_sale_amount": min_sale.value(),
                    "ticket_strategy": strategy.currentText(),
                    "amount_per_ticket": amount_per_ticket.value(),
                    "tickets_per_sale": tickets_per_sale.value(),
                    "max_tickets_per_sale": max_per_sale.value(),
                    "max_tickets_per_customer": max_per_customer.value(),
                    "allowed_payment_methods": allowed_pm.text().strip(),
                },
                prizes,
                {"branches": [cmb_sucursal.value()]},
            )
            Toast.success(self, "Rifas", "Rifa creada.")
            self._cargar_raffles()
        except Exception as e:
            Toast.error(self, "Rifas", str(e))

    def _on_reservar_presupuesto(self):
        row = self._require_selected_raffle()
        if not row: return
        monto, ok = QInputDialog.getDouble(self, "Reservar presupuesto", "Monto:", 0.0, 0.0, 99999999.0, 2)
        if not ok or monto <= 0: return
        try:
            self.container.loyalty_service.reserve_raffle_budget(int(row["id"]), float(monto), self.usuario or "sistema", f"ui:reserve:{row['id']}")
            Toast.success(self, "Rifas", "Presupuesto reservado.")
            self._cargar_raffles()
        except Exception as e:
            Toast.error(self, "Rifas", str(e))

    def _on_activar_rifa(self):
        row = self._require_selected_raffle();
        if not row: return
        try:
            self.container.loyalty_service.activate_raffle(int(row["id"]), self.usuario or "sistema")
            Toast.success(self, "Rifas", "Rifa activada.")
            self._cargar_raffles()
        except Exception as e:
            Toast.error(self, "Rifas", str(e))

    def _on_cerrar_rifa(self):
        row = self._require_selected_raffle();
        if not row: return
        try:
            self.container.loyalty_service.close_raffle(int(row["id"]), self.usuario or "sistema")
            Toast.success(self, "Rifas", "Rifa cerrada.")
            self._cargar_raffles()
        except Exception as e:
            Toast.error(self, "Rifas", str(e))

    def _on_seleccionar_ganador(self):
        row = self._require_selected_raffle();
        if not row: return
        try:
            winner = self.container.loyalty_service.select_winner(int(row["id"]), self.usuario or "sistema")
            winner_id = int(winner.get("id") or 0) if isinstance(winner, dict) else 0
            if winner_id > 0:
                self._last_raffle_winner_by_id[int(row["id"])] = winner_id
            Toast.success(self, "Rifas", "Ganador seleccionado.")
            self._cargar_raffles()
        except Exception as e:
            Toast.error(self, "Rifas", str(e))

    def _on_entregar_premio(self):
        row = self._require_selected_raffle()
        if not row:
            return
        raffle_id = str(row["id"])
        suggested = str(self._last_raffle_winner_by_id.get(raffle_id, "") or "")
        winner_id, ok = QInputDialog.getText(self, "Entregar premio", "ID del ganador:", text=suggested)
        winner_id = str(winner_id or "").strip()
        if not ok or not winner_id: return
        costo, ok2 = QInputDialog.getDouble(self, "Entregar premio", "Costo real:", 0.0, 0.0, 99999999.0, 2)
        if not ok2: return
        try:
            self.container.loyalty_service.mark_prize_delivered(winner_id, self.usuario or "sistema", float(costo), f"ui:winner:{winner_id}")
            Toast.success(self, "Rifas", "Premio entregado.")
            self._cargar_raffles()
        except Exception as e:
            Toast.error(self, "Rifas", str(e))

    def _on_ver_boletos(self):
        row = self._require_selected_raffle()
        if not row: return
        try:
            tickets = self.container.loyalty_service.list_raffle_tickets(int(row["id"]), limit=200)
            dlg = QDialog(self); dlg.setWindowTitle("Boletos de rifa"); dlg.resize(1080, 620)
            lay = QVBoxLayout(dlg)
            top = QHBoxLayout()
            txt_search = QLineEdit(); txt_search.setPlaceholderText("Buscar por boleto, cliente, venta, folio, estado...")
            btn_copy = QPushButton("Copiar")
            btn_export = QPushButton("Exportar CSV")
            top.addWidget(txt_search); top.addWidget(btn_copy); top.addWidget(btn_export)
            lay.addLayout(top)

            tbl = QTableWidget(0, 7); tbl.setHorizontalHeaderLabels(["Boleto", "Cliente", "Venta", "Folio", "Estado", "Fecha", "ID"])
            tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
            tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            all_rows = []
            for t in tickets:
                all_rows.append([
                    str(t.get("numero_boleto","")),
                    str(t.get("cliente_id","")),
                    str(t.get("venta_id","")),
                    str(t.get("folio_venta","")),
                    str(t.get("estado","")),
                    str(t.get("created_at","")),
                    str(t.get("id","")),
                ])

            def _render(filtered_rows):
                tbl.setRowCount(0)
                for row_vals in filtered_rows:
                    r = tbl.rowCount(); tbl.insertRow(r)
                    for c, v in enumerate(row_vals):
                        tbl.setItem(r, c, QTableWidgetItem(v))

            def _apply_filter():
                q = txt_search.text().strip().lower()
                if not q:
                    _render(all_rows); return
                _render([r for r in all_rows if q in " ".join(r).lower()])

            def _copy_selected():
                rows = sorted({idx.row() for idx in tbl.selectedIndexes()})
                if not rows:
                    rows = list(range(tbl.rowCount()))
                lines = []
                for r in rows:
                    lines.append(" | ".join(tbl.item(r, c).text() if tbl.item(r, c) else "" for c in range(tbl.columnCount())))
                self.clipboard().setText("\n".join(lines))
                Toast.success(self, "Boletos", "Filas copiadas al portapapeles.")

            def _export_csv():
                path, _ = QFileDialog.getSaveFileName(dlg, "Exportar boletos", "boletos_rifa.csv", "CSV (*.csv)")
                if not path:
                    return
                with open(path, "w", newline="", encoding="utf-8") as fh:
                    wr = csv.writer(fh)
                    wr.writerow(["numero_boleto", "cliente_id", "venta_id", "folio_venta", "estado", "created_at", "id"])
                    for r in range(tbl.rowCount()):
                        wr.writerow([tbl.item(r, c).text() if tbl.item(r, c) else "" for c in range(tbl.columnCount())])
                Toast.success(self, "Boletos", "CSV exportado correctamente.")

            txt_search.textChanged.connect(lambda *_: _apply_filter())
            btn_copy.clicked.connect(_copy_selected)
            btn_export.clicked.connect(_export_csv)
            _render(all_rows)
            lay.addWidget(tbl); dlg.exec_()
        except Exception as e:
            Toast.error(self, "Boletos", str(e))
