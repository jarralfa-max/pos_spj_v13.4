# modulos/caja.py
from modulos.design_tokens import Colors, Spacing, Typography, Shadows
from modulos.ui_components import (
    create_primary_button, create_secondary_button, create_danger_button,
    create_success_button, create_card, create_input_field,
    create_heading, create_subheading, apply_tooltip, create_caption,
    create_table_with_columns, create_table_button, create_label, confirm_action,
    PageHeader, Toast,
)
from modulos.spj_refresh_mixin import RefreshMixin
from core.events.event_bus import VENTA_COMPLETADA
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QMessageBox, QFormLayout, QDoubleSpinBox, QGroupBox,
    QTableWidget, QTableWidgetItem, QDialog, QHeaderView,
    QAbstractItemView, QFrame, QGridLayout, QTabWidget,
    QInputDialog, QStackedWidget,
)
from PyQt5.QtCore import Qt
from datetime import datetime


class DialogoCorteZCiego(QDialog):
    """
    Diálogo de Corte Z a Ciegas.

    El cajero NO puede ver el total de ventas del sistema antes de
    ingresar su conteo físico. Esto previene ajuste del conteo al
    número esperado (fraude o descuido).

    Flujo:
      Paso 1 — Instrucción + Arqueo de denominaciones (cajero cuenta billetes)
      Paso 2 — Confirmación del total contado
      Paso 3 — El sistema revela la diferencia
    """

    DENOMINACIONES = [
        ("$1,000", 1000.0), ("$500", 500.0), ("$200", 200.0), ("$100", 100.0),
        ("$50",    50.0),   ("$20",  20.0),  ("$10",  10.0),  ("$5",    5.0),
        ("$2",      2.0),   ("$1",    1.0),  ("$0.50", 0.5),
    ]

    def __init__(self, turno_id, cajero, container, sucursal_id=1, parent=None):
        super().__init__(parent)
        self.turno_id    = turno_id
        self.cajero      = cajero
        self.container   = container
        self.sucursal_id = sucursal_id
        self.total_contado = 0.0
        self.resultado     = None

        self.setWindowTitle("🔒 Corte Z — Conteo a Ciegas")
        self.setMinimumWidth(520)
        self.setModal(True)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)

        hdr = QLabel("CORTE Z — CONTEO FÍSICO DE EFECTIVO")
        hdr.setAlignment(Qt.AlignCenter)
        hdr.setObjectName("dialogHeader")
        root.addWidget(hdr)

        aviso = QLabel(
            "IMPORTANTE: Cuenta el efectivo fisico del cajon ANTES de ver "
            "los resultados del sistema. No consultes el modulo de ventas. "
            "El sistema te mostrara la diferencia solo despues de confirmar tu conteo.")
        aviso.setWordWrap(True)
        aviso.setObjectName("warningBox")
        root.addWidget(aviso)

        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)

        self._stack.addWidget(self._page_arqueo())
        self._stack.addWidget(self._page_confirmar())
        self._stack.addWidget(self._page_resultado())

        # Navigation buttons — stored as self._nav to be accessible from _ejecutar_corte
        self._nav = QHBoxLayout()

        self._btn_cancel = create_secondary_button(self, "Cancelar", "Cancelar el corte de caja")
        self._btn_cancel.clicked.connect(self.reject)

        self._btn_back = create_secondary_button(self, "◀ Anterior", "Volver al paso anterior")
        self._btn_back.setEnabled(False)
        self._btn_back.clicked.connect(self._prev_page)

        self._btn_next = create_primary_button(self, "Siguiente ▶", "Continuar al siguiente paso del corte")
        self._btn_next.clicked.connect(self._next_page)

        self._nav.addWidget(self._btn_cancel)
        self._nav.addStretch()
        self._nav.addWidget(self._btn_back)
        self._nav.addWidget(self._btn_next)
        root.addLayout(self._nav)

    # ── Page 1: Arqueo ────────────────────────────────────────────────────────
    def _page_arqueo(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        lbl = QLabel("Paso 1 de 2 — Cuenta los billetes y monedas del cajón")
        lbl.setObjectName("subheading")
        lay.addWidget(lbl)

        grp = QGroupBox("Denominaciones")
        grp.setObjectName("styledGroup")
        grid = QGridLayout(grp)
        grid.setSpacing(6)

        self._den_spins = {}
        self._den_labels = {}
        for i, (label, valor) in enumerate(self.DENOMINACIONES):
            row_idx = i // 2
            col     = (i % 2) * 4
            grid.addWidget(QLabel(f"<b>{label}</b>"), row_idx, col)
            spin = QDoubleSpinBox()
            spin.setRange(0, 9999); spin.setDecimals(0)
            spin.setSuffix(" pzas"); spin.setFixedWidth(100)
            spin.valueChanged.connect(self._recalcular_arqueo)
            self._den_spins[valor] = spin
            grid.addWidget(spin, row_idx, col + 1)
            lbl_sub = QLabel("$0.00")
            lbl_sub.setFixedWidth(80)
            lbl_sub.setObjectName("textSecondary")
            self._den_labels[valor] = lbl_sub
            grid.addWidget(lbl_sub, row_idx, col + 2)

        lay.addWidget(grp)

        self.lbl_total_arq = QLabel("Total contado: $0.00")
        self.lbl_total_arq.setAlignment(Qt.AlignRight)
        self.lbl_total_arq.setObjectName("successBox")
        lay.addWidget(self.lbl_total_arq)
        return w

    def _recalcular_arqueo(self):
        total = 0.0
        for valor, spin in self._den_spins.items():
            sub = float(valor) * spin.value()
            total += sub
            self._den_labels[valor].setText(f"${sub:,.2f}")
        self.total_contado = total
        self.lbl_total_arq.setText(f"Total contado: ${total:,.2f}")

    # ── Page 2: Confirmation ──────────────────────────────────────────────────
    def _page_confirmar(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        lbl = QLabel("Paso 2 de 2 — Confirma el total que contaste")
        lbl.setObjectName("subheading")
        lay.addWidget(lbl)

        aviso = QLabel(
            "El total del arqueo se muestra abajo. Si es correcto, haz clic en CONFIRMAR CORTE. El sistema calculara la diferencia en ese momento.")
        aviso.setWordWrap(True)
        aviso.setObjectName("textSecondary")
        lay.addWidget(aviso)

        grp = QGroupBox("Total físico contado")
        grp.setObjectName("styledGroup")
        form = QFormLayout(grp)

        self.spin_total_fisico = QDoubleSpinBox()
        self.spin_total_fisico.setRange(0, 9999999)
        self.spin_total_fisico.setDecimals(2)
        self.spin_total_fisico.setPrefix("$ ")
        self.spin_total_fisico.setObjectName("input")
        form.addRow("Efectivo contado:", self.spin_total_fisico)

        self.txt_observaciones = QLineEdit()
        self.txt_observaciones.setPlaceholderText(
            "Observaciones opcionales (ej. faltante detectado antes del corte)")
        self.txt_observaciones.setObjectName("input")
        form.addRow("Observaciones:", self.txt_observaciones)
        lay.addWidget(grp)
        lay.addStretch()
        return w

    # ── Page 3: Result (revealed AFTER confirmation) ──────────────────────────
    def _page_resultado(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.lbl_resultado = QLabel("Procesando...")
        self.lbl_resultado.setWordWrap(True)
        self.lbl_resultado.setAlignment(Qt.AlignCenter)
        self.lbl_resultado.setObjectName("resultadoCard")
        lay.addWidget(self.lbl_resultado, 1)
        return w

    # ── Navigation ────────────────────────────────────────────────────────────
    def _next_page(self):
        cur = self._stack.currentIndex()

        if cur == 0:
            self.spin_total_fisico.setValue(self.total_contado)
            self._stack.setCurrentIndex(1)
            self._btn_back.setEnabled(True)
            self._btn_next.setText("✅ CONFIRMAR CORTE")
            self._btn_next.setToolTip("Confirmar el corte de caja y revelar resultados")

        elif cur == 1:
            if not confirm_action(
                self,
                "Confirmar Corte Z",
                "¿Confirmas el total físico capturado para ejecutar el corte?",
                confirm_text="Sí, ejecutar",
                cancel_text="Revisar",
            ):
                return
            self._ejecutar_corte()

    def _prev_page(self):
        cur = self._stack.currentIndex()
        if cur == 1:
            self._stack.setCurrentIndex(0)
            self._btn_back.setEnabled(False)
            self._btn_next.setText("Siguiente ▶")
            self._btn_next.setToolTip("Continuar al siguiente paso")

    def _ejecutar_corte(self):
        """Llama al servicio canónico, luego revela el resultado."""
        efectivo = self.spin_total_fisico.value()
        obs = self.txt_observaciones.text().strip()

        try:
            # Usar CajaApplicationService (fuente única de verdad)
            svc = getattr(self.container, 'caja_service', None)
            if svc is None:
                # Fallback para compatibilidad: usar finance_service
                svc = self.container.finance_service
                resultado = svc.generar_corte_z(
                    self.turno_id, self.sucursal_id, self.cajero, efectivo
                )
            else:
                resultado = svc.generar_corte_z(
                    self.turno_id, self.sucursal_id, self.cajero, efectivo, obs
                )
            self.resultado = resultado

            dif = resultado.get("diferencia", 0)
            esperado = resultado.get("efectivo_esperado", resultado.get("esperado", 0))

            if abs(dif) < 0.01:
                dif_txt   = "✅  CAJA CUADRADA"
                dif_color = Colors.SUCCESS_BASE
            elif dif < 0:
                dif_txt   = f"⚠️  FALTANTE  ${abs(dif):,.2f}"
                dif_color = Colors.DANGER_HOVER
            else:
                dif_txt   = f"ℹ️  SOBRANTE  ${dif:,.2f}"
                dif_color = Colors.WARNING_BASE

            breakdown_rows = ""
            ventas_por_pago = resultado.get("ventas_por_pago", {})
            if ventas_por_pago:
                breakdown_rows = "<tr><td colspan='2'><b>Desglose por forma de pago:</b></td></tr>"
                for fp, data in ventas_por_pago.items():
                    breakdown_rows += (
                        f"<tr><td style='padding-left:12px'>{fp} "
                        f"({data.get('count',0)} vtas):</td>"
                        f"<td align='right'>${data.get('total',0):,.2f}</td></tr>"
                    )

            html = (
                f"<h3 style='color:{dif_color};'>{dif_txt}</h3>"
                f"<table width='100%' cellspacing='6' "
                f"style='font-size:13px;text-align:left;'>"
                f"<tr><td>Ventas del turno:</td>"
                f"<td align='right'><b>${resultado.get('total_ventas', resultado.get('ventas_totales',0)):,.2f}</b></td></tr>"
                f"{breakdown_rows}"
                f"<tr><td>Retiros / gastos:</td>"
                f"<td align='right'>${resultado.get('retiros',0):,.2f}</td></tr>"
                f"<tr><td>Efectivo esperado:</td>"
                f"<td align='right'><b>${esperado:,.2f}</b></td></tr>"
                f"<tr><td>Efectivo contado:</td>"
                f"<td align='right'>${efectivo:,.2f}</td></tr>"
                f"<tr><td colspan='2'><hr></td></tr>"
                f"<tr><td><b>Diferencia:</b></td>"
                f"<td align='right'><b style='color:{dif_color};'>"
                f"${dif:+,.2f}</b></td></tr>"
                f"</table>"
            )
            if obs:
                html += f"<p style='color:#555;font-size:11px;'>Obs: {obs}</p>"

            self.lbl_resultado.setText(html)
            self._stack.setCurrentIndex(2)
            self._btn_back.setEnabled(False)

            # Reemplazar botón Siguiente por Cerrar e Imprimir usando self._nav
            idx = self._nav.indexOf(self._btn_next)
            if idx != -1:
                self._nav.removeWidget(self._btn_next)
                self._btn_next.deleteLater()

            self._btn_next = create_primary_button(self, "🖨️ Cerrar e Imprimir", "Cerrar el corte e imprimir comprobante")
            self._btn_next.clicked.connect(self.accept)
            self._nav.insertWidget(idx, self._btn_next)
            self._btn_cancel.setEnabled(False)

        except Exception as e:
            import logging
            logging.getLogger(__name__).error("_ejecutar_corte: %s", e)
            QMessageBox.critical(self, "Error al ejecutar corte", str(e))

    def get_resultado(self):
        return self.resultado


class ModuloCaja(QWidget, RefreshMixin):
    """
    Módulo Visual Enterprise para el control de la Caja Registradora.
    """
    def __init__(self, container, parent=None):
        super().__init__(parent)
        try: self._init_refresh(container, ["VENTA_COMPLETADA"])
        except Exception: pass
        self.container = container
        self.sucursal_id = 1
        self.usuario_actual = ""
        self.rol_actual = "cajero"
        self.turno_actual = None
        self.layout_estado = None

        self.init_ui()

        from PyQt5.QtWidgets import QShortcut
        from PyQt5.QtGui import QKeySequence
        try:
            QShortcut(QKeySequence("F1"), self).activated.connect(self.abrir_caja)
            QShortcut(QKeySequence("F2"), self).activated.connect(self.registrar_movimiento)
            QShortcut(QKeySequence("F3"), self).activated.connect(
                lambda: self.cerrar_caja() if hasattr(self, 'cerrar_caja') else None)
            QShortcut(QKeySequence("F10"), self).activated.connect(self.cerrar_caja)
        except Exception:
            pass

    # ── Helpers de servicio ───────────────────────────────────────────────────

    @property
    def _caja_svc(self):
        """Retorna CajaApplicationService si disponible, o None."""
        return getattr(self.container, 'caja_service', None)

    def set_sucursal(self, sucursal_id: int, nombre_sucursal: str):
        self.sucursal_id = sucursal_id
        self.verificar_estado_caja()

    def _crear_caja_kpi_bar(self) -> QFrame:
        """Barra de KPIs: fondo, ventas del turno, movimientos, cortes del día."""
        bar = QFrame()
        bar.setObjectName("cajaKpiBar")
        bar.setFixedHeight(64)
        bar.setStyleSheet(
            f"QFrame#cajaKpiBar {{ background:{Colors.SURFACE_DARK if hasattr(Colors,'SURFACE_DARK') else '#1E293B'};"
            f" border-radius:8px; border:1px solid #334155; margin-bottom:4px; }}"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 8, 20, 8)
        lay.setSpacing(0)

        kpis = [
            ("Fondo inicial",  "—", Colors.PRIMARY_BASE),
            ("Ventas turno",   "—", Colors.SUCCESS_BASE),
            ("Movimientos",    "—", Colors.WARNING_BASE),
            ("Cortes hoy",     "—", Colors.INFO_BASE),
        ]

        # Obtener datos desde caja_service (sin SQL directo)
        try:
            svc = self._caja_svc
            if svc and self.usuario_actual:
                kpi_data = svc.get_caja_kpis(self.sucursal_id, self.usuario_actual)
                fondo = kpi_data.get("fondo_inicial", 0)
                ventas = kpi_data.get("total_ventas_turno", 0)
                movs = kpi_data.get("num_movimientos_hoy", 0)
                cortes = kpi_data.get("num_cortes_hoy", 0)
                kpis[0] = ("Fondo inicial", f"${fondo:,.0f}", Colors.PRIMARY_BASE)
                kpis[1] = ("Ventas turno",  f"${ventas:,.0f}", Colors.SUCCESS_BASE)
                kpis[2] = ("Movimientos", str(movs), Colors.WARNING_BASE)
                kpis[3] = ("Cortes hoy", str(cortes), Colors.INFO_BASE)
        except Exception:
            pass

        self._caja_kpi_labels = {}
        for i, (lbl, val, col) in enumerate(kpis):
            if i > 0:
                s = QFrame()
                s.setFrameShape(QFrame.VLine)
                s.setFixedWidth(1)
                s.setStyleSheet("background:#334155; border:none;")
                lay.addWidget(s)
                lay.addSpacing(20)
            c = QVBoxLayout()
            c.setSpacing(1)
            v = QLabel(val)
            v.setStyleSheet(f"color:{col};font-size:18px;font-weight:700;background:transparent;")
            l = QLabel(lbl.upper())
            l.setStyleSheet("color:#64748B;font-size:9px;font-weight:700;letter-spacing:0.5px;background:transparent;")
            c.addWidget(v)
            c.addWidget(l)
            lay.addLayout(c)
            self._caja_kpi_labels[lbl] = v
            if i < 3:
                lay.addSpacing(20)
        lay.addStretch()
        return bar

    def set_usuario_actual(self, usuario: str, rol: str):
        self.usuario_actual = usuario
        self.rol_actual = rol or "cajero"
        self.verificar_estado_caja()

    def init_ui(self):
        layout_principal = QVBoxLayout(self)

        self.lbl_titulo = QLabel("💵 Gestión de Caja Registradora")
        self.lbl_titulo.setObjectName("heading")
        layout_principal.addWidget(self.lbl_titulo)

        self._caja_kpi_bar_widget = self._crear_caja_kpi_bar()
        layout_principal.addWidget(self._caja_kpi_bar_widget)

        self.panel_estado = QGroupBox("Estado Actual")
        self.panel_estado.setObjectName("styledGroup")
        self.layout_estado = QVBoxLayout(self.panel_estado)

        self.lbl_status = QLabel("Buscando estado del turno...")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setObjectName("statusLabel")
        self.layout_estado.addWidget(self.lbl_status)

        self.btn_accion_turno = create_primary_button(self, "Acción de Turno", "Abrir o cerrar turno de caja según estado")
        self.btn_accion_turno.clicked.connect(self.gestionar_turno)
        self.layout_estado.addWidget(self.btn_accion_turno)

        layout_principal.addWidget(self.panel_estado)

        self.panel_movimientos = QGroupBox("💸 Registrar Movimiento de Efectivo")
        self.panel_movimientos.setObjectName("styledGroup")
        layout_mov = QFormLayout(self.panel_movimientos)

        self.cmb_tipo_movimiento = QComboBox()
        self.cmb_tipo_movimiento.addItems(["RETIRO (Salida de dinero)", "INGRESO (Entrada extra)"])
        self.cmb_tipo_movimiento.setObjectName("inputField")

        self.txt_monto_mov = QDoubleSpinBox()
        self.txt_monto_mov.setRange(0.1, 999999.0)
        self.txt_monto_mov.setPrefix("$ ")
        self.txt_monto_mov.setObjectName("inputField")

        self.txt_concepto = QLineEdit()
        self.txt_concepto.setPlaceholderText("Ej. Pago a proveedor de refrescos, Cambio extra...")
        self.txt_concepto.setObjectName("inputField")

        self.btn_guardar_mov = create_success_button(self, "Guardar Movimiento", "Registrar movimiento de efectivo en el turno")
        self.btn_guardar_mov.clicked.connect(self.registrar_movimiento)

        layout_mov.addRow("Tipo:", self.cmb_tipo_movimiento)
        layout_mov.addRow("Monto:", self.txt_monto_mov)
        layout_mov.addRow("Concepto:", self.txt_concepto)
        layout_mov.addRow("", self.btn_guardar_mov)

        layout_principal.addWidget(self.panel_movimientos)

        self._tabs_caja = QTabWidget()
        layout_principal.addWidget(self._tabs_caja, 1)

        self._tab_movs = QWidget()
        self._tabs_caja.addTab(self._tab_movs, "📋 Movimientos del Turno")
        self._build_tab_movimientos()

        self._tab_hist = QWidget()
        self._tabs_caja.addTab(self._tab_hist, "📜 Historial de Cortes")

        self._tab_arqueo = QWidget()
        self._tabs_caja.addTab(self._tab_arqueo, "🔢 Arqueo")

        self._tabs_caja.currentChanged.connect(self._on_tab_change)

        self._build_tab_historial()
        self._build_tab_arqueo()

    def _on_refresh(self, event_type: str, data: dict) -> None:
        """Auto-refresh caja state and movimientos on VENTA_COMPLETADA."""
        try:
            self.verificar_estado_caja()
            if self.turno_actual:
                self._cargar_movimientos_turno()
        except Exception:
            pass

    def verificar_estado_caja(self):
        """Consulta al servicio de caja si el usuario ya abrió su caja hoy."""
        if not self.usuario_actual:
            return

        try:
            svc = self._caja_svc
            if svc:
                turno = svc.get_estado_turno(self.sucursal_id, self.usuario_actual)
            else:
                turno = self.container.finance_service.get_estado_turno(self.sucursal_id, self.usuario_actual)

            if turno:
                self.turno_actual = turno['id']
                self.lbl_status.setText(f"✅ TURNO ABIERTO\nFondo Inicial: ${turno['fondo_inicial']:.2f}")
                self.lbl_status.setProperty("class", "status-success")
                self.lbl_status.style().unpolish(self.lbl_status)
                self.lbl_status.style().polish(self.lbl_status)

                idx = self.layout_estado.indexOf(self.btn_accion_turno)
                if idx != -1:
                    self.layout_estado.removeWidget(self.btn_accion_turno)
                    self.btn_accion_turno.deleteLater()

                self.btn_accion_turno = create_danger_button(self, "🔒 CERRAR CAJA (CORTE Z)", "Cerrar turno y realizar corte Z")
                self.btn_accion_turno.clicked.connect(self.gestionar_turno)
                self.layout_estado.insertWidget(idx, self.btn_accion_turno)
                self.panel_movimientos.setEnabled(True)
            else:
                self.turno_actual = None
                self.lbl_status.setText("❌ CAJA CERRADA")
                self.lbl_status.setProperty("class", "status-neutral")
                self.lbl_status.style().unpolish(self.lbl_status)
                self.lbl_status.style().polish(self.lbl_status)

                idx = self.layout_estado.indexOf(self.btn_accion_turno)
                if idx != -1:
                    self.layout_estado.removeWidget(self.btn_accion_turno)
                    self.btn_accion_turno.deleteLater()

                self.btn_accion_turno = create_primary_button(self, "🔓 ABRIR TURNO DE CAJA", "Iniciar nuevo turno de caja con fondo inicial")
                self.btn_accion_turno.clicked.connect(self.gestionar_turno)
                self.layout_estado.insertWidget(idx, self.btn_accion_turno)
                self.panel_movimientos.setEnabled(False)

        except Exception as e:
            self.lbl_status.setText("Error leyendo estado de caja.")
            import logging
            logging.getLogger(__name__).error("verificar_estado_caja: %s", e)

    def gestionar_turno(self):
        if self.turno_actual is None:
            self.abrir_caja()
        else:
            self.cerrar_caja()

    def abrir_caja(self):
        try:
            from core.permissions import verificar_permiso
            if not verificar_permiso(self.container, "caja.abrir", self):
                return
        except Exception:
            pass

        fondo, ok = QInputDialog.getDouble(
            self, "Abrir Turno",
            "¿Con cuánto dinero en efectivo inicias el turno en el cajón?",
            value=0.0, min=0.0, max=99999.0, decimals=2
        )

        if ok:
            try:
                svc = self._caja_svc
                if svc:
                    svc.abrir_turno(self.sucursal_id, self.usuario_actual, fondo)
                else:
                    self.container.finance_service.abrir_turno(self.sucursal_id, self.usuario_actual, fondo)

                Toast.success(self, "Turno abierto", f"Fondo inicial: ${fondo:.2f}")

                if hasattr(self.container, 'hardware_service'):
                    self.container.hardware_service.open_cash_drawer()

                self.verificar_estado_caja()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def registrar_movimiento(self):
        try:
            from core.permissions import verificar_permiso
            if not verificar_permiso(self.container, "caja.movimientos", self):
                return
        except Exception:
            pass

        if not self.turno_actual:
            return

        monto = self.txt_monto_mov.value()
        concepto = self.txt_concepto.text().strip()
        tipo = "RETIRO" if "RETIRO" in self.cmb_tipo_movimiento.currentText() else "INGRESO"

        if not concepto:
            QMessageBox.warning(self, "Aviso", "Debe ingresar un concepto para justificar el movimiento.")
            return

        try:
            svc = self._caja_svc
            if svc:
                svc.registrar_movimiento_manual(
                    self.turno_actual, self.sucursal_id, self.usuario_actual, tipo, monto, concepto
                )
            else:
                self.container.finance_service.registrar_movimiento_manual(
                    self.turno_actual, self.sucursal_id, self.usuario_actual, tipo, monto, concepto
                )

            Toast.success(self, "Movimiento registrado", f"{tipo} registrado correctamente.")
            try:
                self._cargar_movimientos_turno()
            except Exception:
                pass

            if hasattr(self.container, 'hardware_service'):
                self.container.hardware_service.open_cash_drawer()

            self.txt_monto_mov.setValue(0.1)
            self.txt_concepto.clear()

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def cerrar_caja(self):
        """
        Flujo de Corte Z a Ciegas:
        El cajero NO ve los totales del sistema antes de contar el efectivo.
        Solo después de ingresar su conteo se revela la diferencia.
        """
        try:
            from core.permissions import verificar_permiso
            if not verificar_permiso(self.container, "caja.cerrar", self):
                return
        except Exception:
            pass

        dlg = DialogoCorteZCiego(
            turno_id    = self.turno_actual,
            cajero      = self.usuario_actual,
            container   = self.container,
            sucursal_id = self.sucursal_id,
            parent      = self,
        )
        if dlg.exec_() != QDialog.Accepted:
            return

        resultado = dlg.get_resultado()
        if not resultado:
            return

        try:
            notif = getattr(self.container, 'notification_service', None)
            if notif:
                notif.notificar_corte_z(
                    folio        = str(resultado.get('cierre_id', '?')),
                    total_ventas = float(resultado.get('total_ventas', resultado.get('ventas_totales', 0))),
                    total_caja   = float(resultado.get('efectivo_contado', resultado.get('contado', 0))),
                    diferencia   = float(resultado.get('diferencia', 0)),
                    cajero       = self.usuario_actual,
                    sucursal_id  = self.sucursal_id,
                )
        except Exception as _e:
            import logging
            logging.getLogger(__name__).debug("notif corte_z: %s", _e)

        # Impresión via CajaTicketService (sin lógica de impresión en UI)
        try:
            ticket_svc = getattr(self.container, 'caja_ticket_service', None)
            if ticket_svc:
                ticket_svc.preview_or_print_corte(resultado, self.usuario_actual, parent=self)
            else:
                self._fallback_imprimir(resultado)
        except Exception as _e:
            import logging
            logging.getLogger(__name__).warning("imprimir corte: %s", _e)

        self.verificar_estado_caja()
        try:
            self._cargar_movimientos_turno()
        except Exception:
            pass

    def _fallback_imprimir(self, resultado: dict):
        """Impresión básica cuando CajaTicketService no está disponible."""
        try:
            from PyQt5.QtWidgets import QDialog as _D, QVBoxLayout as _V, QTextBrowser as _TB
            from PyQt5.QtPrintSupport import QPrinter, QPrintDialog
            from PyQt5.QtGui import QTextDocument
            datos = {
                'fecha': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'cajero': self.usuario_actual,
                'ventas_totales': float(resultado.get('total_ventas', resultado.get('ventas_totales', 0))),
                'retiros': float(resultado.get('retiros', 0)),
                'esperado': float(resultado.get('efectivo_esperado', resultado.get('esperado', 0))),
                'contado': float(resultado.get('efectivo_contado', resultado.get('contado', 0))),
                'diferencia': float(resultado.get('diferencia', 0)),
                'fondo_inicial': float(resultado.get('fondo_inicial', 0)),
            }
            cierre_id = resultado.get('cierre_id', resultado.get('turno_id', 0))
            html = self._generar_html_corte_simple(datos, cierre_id)
            dlg = _D(self)
            dlg.setWindowTitle("Ticket Corte Z")
            dlg.setMinimumSize(420, 400)
            lay = _V(dlg)
            browser = _TB()
            browser.setHtml(html)
            lay.addWidget(browser)
            btn_row = QHBoxLayout()
            btn_p = create_primary_button(dlg, "🖨️ Imprimir", "Imprimir")
            btn_c = create_secondary_button(dlg, "Cerrar", "Cerrar")
            def _print():
                p = QPrinter(QPrinter.HighResolution)
                pd = QPrintDialog(p, dlg)
                if pd.exec_() == QPrintDialog.Accepted:
                    doc = QTextDocument(); doc.setHtml(html); doc.print_(p)
            btn_p.clicked.connect(_print)
            btn_c.clicked.connect(dlg.accept)
            btn_row.addWidget(btn_p); btn_row.addStretch(); btn_row.addWidget(btn_c)
            lay.addLayout(btn_row)
            dlg.exec_()
        except Exception:
            pass

    def _generar_html_corte_simple(self, datos: dict, cierre_id: int) -> str:
        dif = float(datos.get('diferencia', 0))
        if dif < -0.01:
            dif_txt = f"<span style='color:red;'>FALTANTE: ${abs(dif):.2f}</span>"
        elif dif > 0.01:
            dif_txt = f"SOBRANTE: ${dif:.2f}"
        else:
            dif_txt = "Exacto ($0.00)"
        return f"""
        <html><body style="font-family:monospace;text-align:center;width:300px;">
            <h2>CORTE DE CAJA (Z)</h2><p>=============================</p>
            <p><strong>Folio:</strong> {cierre_id}</p>
            <p><strong>Fecha:</strong> {datos.get('fecha','')}</p>
            <p><strong>Cajero:</strong> {datos.get('cajero','')}</p>
            <p>=============================</p>
            <div style="text-align:left;padding-left:20px;">
                <p>Ventas Totales: ${float(datos.get('ventas_totales',0)):.2f}</p>
                <p>Gastos/Retiros: ${float(datos.get('retiros',0)):.2f}</p>
                <p>-------------------------</p>
                <p><strong>EFECTIVO ESPERADO: ${float(datos.get('esperado',0)):.2f}</strong></p>
                <p><strong>EFECTIVO CONTADO:  ${float(datos.get('contado',0)):.2f}</strong></p>
                <p>-------------------------</p>
                <h3>DIFERENCIA: {dif_txt}</h3>
            </div>
            <br><br><p>_________________________</p><p>Firma del Cajero</p>
        </body></html>"""

    # ── Tabs ──────────────────────────────────────────────────────────────────

    def _build_tab_movimientos(self) -> None:
        lay = QVBoxLayout(self._tab_movs)
        lay.setContentsMargins(8, 8, 8, 8)

        hdr = QHBoxLayout()
        lbl = QLabel("Movimientos de efectivo del turno activo")
        lbl.setObjectName("subheading")
        hdr.addWidget(lbl)
        hdr.addStretch()
        btn_ref = create_primary_button(self, "🔄 Actualizar", "Recargar lista de movimientos del turno")
        btn_ref.clicked.connect(self._cargar_movimientos_turno)
        hdr.addWidget(btn_ref)
        lay.addLayout(hdr)

        self._tbl_movs = create_table_with_columns(
            self,
            columns=["Hora", "Tipo", "Concepto", "Monto", "Usuario", "ID Turno"],
            show_grid=False,
            alternating_colors=True
        )
        hh = self._tbl_movs.horizontalHeader()
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        for c in (0, 1, 3, 4, 5):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        lay.addWidget(self._tbl_movs)

        tot_row = QHBoxLayout()
        self.lbl_mov_ingresos = QLabel("Ingresos: $0.00")
        self.lbl_mov_retiros  = QLabel("Retiros: $0.00")
        self.lbl_mov_ventas   = QLabel("Ventas: $0.00")
        self.lbl_mov_neto     = QLabel("Neto en caja: $0.00")
        for lbl in (self.lbl_mov_ingresos, self.lbl_mov_retiros,
                    self.lbl_mov_ventas, self.lbl_mov_neto):
            lbl.setObjectName("badge")
        self.lbl_mov_neto.setObjectName("badge-success")
        tot_row.addWidget(self.lbl_mov_ingresos)
        tot_row.addWidget(self.lbl_mov_retiros)
        tot_row.addWidget(self.lbl_mov_ventas)
        tot_row.addStretch()
        tot_row.addWidget(self.lbl_mov_neto)
        lay.addLayout(tot_row)

    def _cargar_movimientos_turno(self) -> None:
        self._tbl_movs.setRowCount(0)
        if not self.turno_actual:
            return

        svc = self._caja_svc
        try:
            if svc:
                rows_raw = svc.get_movimientos_turno(self.turno_actual, self.rol_actual)
            else:
                rows_raw = self.container.finance_service.get_movimientos_turno(self.turno_actual)
        except Exception:
            rows_raw = []

        ingresos = retiros = ventas = 0.0

        from PyQt5.QtGui import QColor
        for ri, r in enumerate(rows_raw):
            self._tbl_movs.insertRow(ri)
            fecha_str = str(r.get('fecha', r[0] if isinstance(r, (list, tuple)) else '') or "")[:16]
            tipo      = str(r.get('tipo', r[1] if isinstance(r, (list, tuple)) else '') or "")
            concepto  = str(r.get('concepto', r[2] if isinstance(r, (list, tuple)) else '') or "")
            monto     = float(r.get('monto', r[3] if isinstance(r, (list, tuple)) else 0) or 0)
            usuario   = str(r.get('usuario', r[4] if isinstance(r, (list, tuple)) else 'Sistema') or "Sistema")
            turno_id  = str(r.get('turno_id', r[5] if isinstance(r, (list, tuple)) else '') or "")

            rol = getattr(self, 'rol_actual', 'cajero').lower()
            monto_display = (f"${monto:,.2f}"
                             if rol in ('admin', 'administrador', 'gerente')
                             else "***")
            vals = [fecha_str, tipo, concepto, monto_display, usuario, turno_id]
            for ci, val in enumerate(vals):
                it = QTableWidgetItem(val)
                it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                if tipo == "VENTA":
                    it.setForeground(QColor('#27ae60'))
                elif tipo in ("RETIRO", "GASTO"):
                    it.setForeground(QColor('#e74c3c'))
                self._tbl_movs.setItem(ri, ci, it)

            if tipo == "VENTA":      ventas   += monto
            elif tipo == "INGRESO":  ingresos += monto
            elif tipo in ("RETIRO", "GASTO"): retiros += monto

        # Fondo inicial via servicio
        fondo = 0.0
        try:
            if svc:
                turno = svc.get_estado_turno(self.sucursal_id, self.usuario_actual)
                if turno:
                    fondo = float(turno.get('fondo_inicial', 0) or 0)
            else:
                row = self.container.finance_service.get_estado_turno(self.sucursal_id, self.usuario_actual)
                if row:
                    fondo = float(row.get('fondo_inicial', 0) or 0)
        except Exception:
            pass

        neto = fondo + ventas + ingresos - retiros
        rol = getattr(self, 'rol_actual', 'cajero').lower()
        es_gerente = rol in ('admin', 'administrador', 'gerente')

        if es_gerente:
            self.lbl_mov_ingresos.setText(f"Ingresos: ${ingresos:,.2f}")
            self.lbl_mov_retiros.setText(f"Retiros: ${retiros:,.2f}")
            self.lbl_mov_ventas.setText(f"Ventas: ${ventas:,.2f}")
            self.lbl_mov_neto.setText(f"Neto en caja: ${neto:,.2f}")
        else:
            num_ingresos = sum(1 for r in rows_raw if str(r.get('tipo', '') if isinstance(r, dict) else r[1]) == 'INGRESO')
            num_retiros  = sum(1 for r in rows_raw if str(r.get('tipo', '') if isinstance(r, dict) else r[1]) in ('RETIRO','GASTO'))
            num_ventas   = sum(1 for r in rows_raw if str(r.get('tipo', '') if isinstance(r, dict) else r[1]) == 'VENTA')
            self.lbl_mov_ingresos.setText(f"Entradas: {num_ingresos} mov.")
            self.lbl_mov_retiros.setText(f"Retiros: {num_retiros} mov.")
            self.lbl_mov_ventas.setText(f"Ventas: {num_ventas} registradas")
            self.lbl_mov_neto.setText("Corte al cerrar turno")
            self.lbl_mov_neto.setObjectName("badge-neutral")

    def _on_tab_change(self, idx: int) -> None:
        if idx == 0:
            self._cargar_movimientos_turno()
        elif idx == 1:
            self._cargar_historial_cortes()
        elif idx == 2:
            self._init_arqueo()

    def _build_tab_historial(self) -> None:
        lay = QVBoxLayout(self._tab_hist)
        lay.addWidget(create_subheading(self, "Historial de cortes Z y X de esta sucursal"))
        self._tbl_hist = QTableWidget()
        self._tbl_hist.setColumnCount(6)
        self._tbl_hist.setHorizontalHeaderLabels(
            ["Tipo", "Fecha", "Cajero", "Ventas", "Efectivo", "Acciones"])
        hh = self._tbl_hist.horizontalHeader()
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        self._tbl_hist.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_hist.verticalHeader().setVisible(False)
        self._tbl_hist.setAlternatingRowColors(True)
        lay.addWidget(self._tbl_hist)

    def _cargar_historial_cortes(self) -> None:
        from PyQt5.QtWidgets import QWidget as _W, QHBoxLayout as _H
        svc = self._caja_svc
        try:
            if svc:
                rows = svc.get_historial_cortes(self.sucursal_id, limit=100)
            else:
                rows = []
        except Exception:
            rows = []

        self._tbl_hist.setRowCount(len(rows))
        for ri, r in enumerate(rows):
            if isinstance(r, dict):
                vals = [
                    r.get('tipo', 'Z'),
                    str(r.get('fecha_cierre', ''))[:16],
                    r.get('usuario', ''),
                    f"${float(r.get('total_ventas', 0) or 0):,.2f}",
                    f"${float(r.get('total_efectivo', r.get('efectivo_contado', 0)) or 0):,.2f}",
                ]
                cierre_id = r.get('id', 0)
            else:
                vals = [r[0] or "Z", str(r[1] or "")[:16], r[2] or "",
                        f"${float(r[3] or 0):,.2f}", f"${float(r[4] or 0):,.2f}"]
                cierre_id = r[5]

            for ci, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self._tbl_hist.setItem(ri, ci, it)

            btn_w = _W()
            btn_lay = _H(btn_w)
            btn_lay.setContentsMargins(2, 2, 2, 2)
            btn_r = create_secondary_button(self, "🖨️ Reimprimir", "Volver a imprimir comprobante de corte")
            btn_r.clicked.connect(lambda _, cid=cierre_id: self._reimprimir_corte(cid))
            btn_lay.addWidget(btn_r)
            self._tbl_hist.setCellWidget(ri, 5, btn_w)

    def _reimprimir_corte(self, cierre_id: int) -> None:
        svc = self._caja_svc
        try:
            if svc:
                d = svc.get_cierre_por_id(cierre_id)
            else:
                d = None

            if not d:
                QMessageBox.warning(self, "No encontrado", "No se encontró el corte.")
                return

            datos_r = {
                'fecha': str(d.get('fecha_cierre', d.get('fecha', ''))),
                'cajero': d.get('usuario', '?'),
                'ventas_totales': float(d.get('total_ventas', d.get('ventas_totales', 0)) or 0),
                'retiros': float(d.get('retiros', d.get('total_retiros', 0)) or 0),
                'esperado': float(d.get('efectivo_esperado', d.get('esperado', 0)) or 0),
                'contado': float(d.get('efectivo_contado', d.get('contado', d.get('total_efectivo', 0))) or 0),
                'diferencia': float(d.get('diferencia', 0) or 0),
                'fondo_inicial': float(d.get('fondo_inicial', 0) or 0),
            }

            ticket_svc = getattr(self.container, 'caja_ticket_service', None)
            if ticket_svc:
                html = ticket_svc.generar_html_corte(datos_r, cierre_id)
            else:
                html = self._generar_html_corte_simple(datos_r, cierre_id)

            self._imprimir_html(html)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _imprimir_html(self, html: str) -> None:
        from PyQt5.QtPrintSupport import QPrinter, QPrintDialog
        from PyQt5.QtGui import QTextDocument
        printer = QPrinter(QPrinter.HighResolution)
        dlg = QPrintDialog(printer, self)
        if dlg.exec_() != QPrintDialog.Accepted:
            return
        doc = QTextDocument()
        doc.setHtml(html)
        doc.print_(printer)

    def _build_tab_arqueo(self) -> None:
        lay = QVBoxLayout(self._tab_arqueo)

        info = create_label(self, "Cuenta los billetes y monedas del cajón para verificar el cierre.", "caption")
        lay.addWidget(info)

        grp = QGroupBox("Billetes y Monedas")
        grp.setObjectName("styledGroup")
        grid = QGridLayout(grp)
        DENOMINACIONES = [
            ("$1,000", 1000), ("$500", 500), ("$200", 200), ("$100", 100),
            ("$50", 50), ("$20", 20), ("$10", 10), ("$5", 5),
            ("$2", 2), ("$1", 1), ("$0.50", 0.5),
        ]
        self._arqueo_spins = {}
        self._arqueo_sub_labels = {}
        for i, (label, valor) in enumerate(DENOMINACIONES):
            col = (i % 2) * 3
            row_idx = i // 2
            lbl_den = QLabel(label)
            lbl_den.setObjectName("subheading")
            grid.addWidget(lbl_den, row_idx, col)
            spin = QDoubleSpinBox()
            spin.setRange(0, 9999)
            spin.setDecimals(0)
            spin.setSuffix(" pzas")
            spin.setFixedWidth(100)
            spin.setObjectName("inputField")
            spin.valueChanged.connect(self._calcular_arqueo)
            self._arqueo_spins[valor] = spin
            grid.addWidget(spin, row_idx, col + 1)
            # Keep the specific name for lookup; do NOT overwrite with a generic one
            lbl_subtotal = QLabel("$0.00")
            lbl_subtotal.setObjectName(f"lbl_arq_{valor}")
            self._arqueo_sub_labels[valor] = lbl_subtotal  # Direct reference — no findChild needed
            grid.addWidget(lbl_subtotal, row_idx, col + 2)

        lay.addWidget(grp)

        total_row = QHBoxLayout()
        total_row.addStretch()
        self.lbl_total_arqueo = QLabel("Total contado: $0.00")
        self.lbl_total_arqueo.setObjectName("subheading")
        self.lbl_diferencia_arqueo = QLabel("")
        self.lbl_diferencia_arqueo.setObjectName("badge-neutral")
        total_row.addWidget(self.lbl_diferencia_arqueo)
        total_row.addWidget(self.lbl_total_arqueo)
        lay.addLayout(total_row)

        btn_limpiar = create_secondary_button(self, "🔄 Limpiar", "Limpiar conteo de arqueo")
        btn_limpiar.clicked.connect(self._limpiar_arqueo)
        lay.addWidget(btn_limpiar, 0, Qt.AlignLeft)
        lay.addStretch()

    def _init_arqueo(self) -> None:
        self._calcular_arqueo()

    def _calcular_arqueo(self) -> None:
        try:
            total = 0.0
            for valor, spin in self._arqueo_spins.items():
                subtotal = float(valor) * spin.value()
                total += subtotal
                lbl = self._arqueo_sub_labels.get(valor)
                if lbl:
                    lbl.setText(f"${subtotal:,.2f}")
            self.lbl_total_arqueo.setText(f"Total contado: ${total:,.2f}")

            # Compare with system via caja_service (no direct DB access)
            if self.turno_actual:
                try:
                    svc = self._caja_svc
                    if svc:
                        arqueo = svc.calcular_arqueo(self.turno_actual, total)
                        if 'error' not in arqueo:
                            sistema = arqueo.get('esperado', 0)
                            diff = total - sistema
                            color = Colors.SUCCESS_BASE if abs(diff) < 0.01 else Colors.DANGER_HOVER
                            self.lbl_diferencia_arqueo.setText(
                                f"Sistema (esperado): ${sistema:,.2f} | Diferencia: "
                                f"<span style='color:{color}'>${diff:+.2f}</span>")
                except Exception:
                    pass
        except Exception:
            pass

    def _limpiar_arqueo(self) -> None:
        for spin in self._arqueo_spins.values():
            spin.setValue(0)
