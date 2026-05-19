# modulos/caja.py
from modulos.design_tokens import Colors, Spacing, Typography, Borders, Shadows
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
    QComboBox, QMessageBox, QFormLayout, QDoubleSpinBox,
    QTableWidget, QTableWidgetItem, QDialog, QHeaderView,
    QAbstractItemView, QFrame, QGridLayout, QTabWidget,
    QInputDialog, QStackedWidget, QSizePolicy, QScrollArea,
)
from PyQt5.QtCore import Qt
from datetime import datetime

# Icon font-size used inside circular badges — no token at this size
_ICON_FONT_SIZE = "18px"
# Large numeric display (KPI totals, arqueo total)
_KPI_FONT_LARGE = "20px"


# ── KPI card — mirrors _InvKPICard from inventario_local.py ──────────────────

class _CajaKPICard(QFrame):
    """Operational KPI card for caja — theme-aware via objectName kpiCard."""

    def __init__(self, titulo: str, valor: str = "—",
                 icono: str = "💵", variant: str = "primary",
                 parent=None):
        super().__init__(parent)
        _accent = {
            "primary": Colors.PRIMARY.BASE,
            "success": Colors.SUCCESS.BASE,
            "danger":  Colors.DANGER.BASE,
            "warning": Colors.WARNING.BASE,
            "info":    Colors.INFO.BASE,
        }.get(variant, Colors.PRIMARY.BASE)

        self.setObjectName("kpiCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(96)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        bar = QFrame(self)
        bar.setFixedHeight(3)
        bar.setStyleSheet(
            f"background: {_accent}; border: none;"
            f" border-top-left-radius: 12px; border-top-right-radius: 12px;"
        )
        outer.addWidget(bar)

        body = QHBoxLayout()
        body.setContentsMargins(16, 12, 16, 12)
        body.setSpacing(10)
        outer.addLayout(body)

        col = QVBoxLayout()
        col.setSpacing(2)

        lbl_t = QLabel(titulo.upper())
        lbl_t.setStyleSheet(
            f"color: {Colors.NEUTRAL.SLATE_500}; font-size: {Typography.SIZE_XS};"
            f" font-weight: {Typography.WEIGHT_SEMIBOLD}; letter-spacing: 0.08em;"
            f" background: transparent; border: none;"
        )
        col.addWidget(lbl_t)

        self.lbl_valor = QLabel(valor)
        self.lbl_valor.setObjectName("kpiValue")
        self.lbl_valor.setStyleSheet(
            f"font-size: 22px; font-weight: {Typography.WEIGHT_BOLD};"
            f" letter-spacing: -0.02em; background: transparent; border: none;"
        )
        col.addWidget(self.lbl_valor)
        body.addLayout(col, 1)

        lbl_icon = QLabel(icono)
        lbl_icon.setFixedSize(36, 36)
        lbl_icon.setAlignment(Qt.AlignCenter)
        lbl_icon.setStyleSheet(
            f"font-size: {_ICON_FONT_SIZE}; background: {_accent}1A;"
            f" border-radius: 18px; border: none;"
        )
        body.addWidget(lbl_icon, 0, alignment=Qt.AlignTop)

    def set_valor(self, v: str):
        self.lbl_valor.setText(v)


# ── Dialog: registrar ingreso / retiro ────────────────────────────────────────

class DialogoMovimientoCaja(QDialog):
    """Dialog for manual cash in/out movements."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Registrar Movimiento de Efectivo")
        self.setMinimumWidth(400)
        self.setModal(True)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(Spacing.MD)
        root.setContentsMargins(Spacing.XL, Spacing.XL, Spacing.XL, Spacing.XL)

        hdr = QLabel("MOVIMIENTO DE EFECTIVO")
        hdr.setAlignment(Qt.AlignCenter)
        hdr.setStyleSheet(
            f"font-size: {Typography.SIZE_XL}; font-weight: {Typography.WEIGHT_BOLD};"
            f" color: {Colors.NEUTRAL.SLATE_700}; background: transparent; border: none;"
            f" padding-bottom: {Spacing.SM}px;"
        )
        root.addWidget(hdr)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"background: {Colors.NEUTRAL.SLATE_200}; border: none;")
        sep.setFixedHeight(1)
        root.addWidget(sep)

        form = QFormLayout()
        form.setSpacing(Spacing.MD)
        form.setLabelAlignment(Qt.AlignRight)

        self.cmb_tipo = QComboBox()
        self.cmb_tipo.addItems(["RETIRO (Salida de dinero)", "INGRESO (Entrada extra)"])
        self.cmb_tipo.setObjectName("inputField")
        form.addRow("Tipo:", self.cmb_tipo)

        self.spin_monto = QDoubleSpinBox()
        self.spin_monto.setRange(0.1, 999_999.0)
        self.spin_monto.setPrefix("$ ")
        self.spin_monto.setDecimals(2)
        self.spin_monto.setObjectName("inputField")
        form.addRow("Monto:", self.spin_monto)

        self.txt_concepto = QLineEdit()
        self.txt_concepto.setPlaceholderText("Ej. Pago a proveedor, Cambio extra...")
        self.txt_concepto.setObjectName("inputField")
        form.addRow("Concepto:", self.txt_concepto)

        root.addLayout(form)
        root.addSpacing(Spacing.SM)

        btns = QHBoxLayout()
        btn_cancel = create_secondary_button(self, "Cancelar", "Cancelar sin guardar")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = create_success_button(self, "✔ Guardar Movimiento", "Registrar movimiento")
        btn_ok.clicked.connect(self._validar_y_aceptar)
        btns.addWidget(btn_cancel)
        btns.addStretch()
        btns.addWidget(btn_ok)
        root.addLayout(btns)

    def _validar_y_aceptar(self):
        if not self.txt_concepto.text().strip():
            QMessageBox.warning(self, "Aviso", "Debe ingresar un concepto.")
            self.txt_concepto.setFocus()
            return
        self.accept()

    def get_values(self):
        tipo = "RETIRO" if "RETIRO" in self.cmb_tipo.currentText() else "INGRESO"
        return tipo, self.spin_monto.value(), self.txt_concepto.text().strip()


# ── Corte Z wizard ────────────────────────────────────────────────────────────

class DialogoCorteZCiego(QDialog):
    """
    Corte Z blind-count wizard.

    Cashier counts physical cash before the system reveals expected amounts,
    preventing fraud by adjusting counts to match system figures.

    Step 1 — Denomination count (cashier counts bills/coins)
    Step 2 — Confirm total counted
    Step 3 — System reveals difference
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
        self.setMinimumWidth(600)
        self.setMinimumHeight(580)
        self.setModal(True)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.XL, Spacing.LG, Spacing.XL, Spacing.LG)
        root.setSpacing(Spacing.MD)

        # ── Header ──
        hdr_frame = QFrame()
        hdr_frame.setStyleSheet(
            f"background: {Colors.WARNING.BG_SOFT};"
            f" border-radius: {Borders.RADIUS_XL}px;"
            f" border: 1px solid {Colors.WARNING.BORDER};"
        )
        hdr_lay = QVBoxLayout(hdr_frame)
        hdr_lay.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        hdr_lay.setSpacing(Spacing.XS)

        ttl = QLabel("🔒  CORTE Z — CONTEO FÍSICO")
        ttl.setAlignment(Qt.AlignCenter)
        ttl.setStyleSheet(
            f"font-size: {Typography.SIZE_XXL}; font-weight: {Typography.WEIGHT_BOLD};"
            f" color: {Colors.WARNING.ACTIVE}; background: transparent; border: none;"
        )
        hdr_lay.addWidget(ttl)

        aviso = QLabel(
            "Cuenta el efectivo del cajón ANTES de ver los resultados del sistema. "
            "No consultes el módulo de ventas. "
            "La diferencia se revelará solo después de confirmar tu conteo."
        )
        aviso.setWordWrap(True)
        aviso.setAlignment(Qt.AlignCenter)
        aviso.setStyleSheet(
            f"font-size: {Typography.SIZE_SM}; color: {Colors.WARNING.ACTIVE};"
            f" background: transparent; border: none;"
        )
        hdr_lay.addWidget(aviso)
        root.addWidget(hdr_frame)

        # ── Step indicator ──
        self._step_frame = self._build_step_indicator()
        root.addWidget(self._step_frame)

        # ── Pages ──
        self._stack = QStackedWidget()
        root.addWidget(self._stack, 1)
        self._stack.addWidget(self._page_arqueo())
        self._stack.addWidget(self._page_confirmar())
        self._stack.addWidget(self._page_resultado())

        # ── Navigation ──
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"background: {Colors.NEUTRAL.SLATE_200}; border: none;")
        sep.setFixedHeight(1)
        root.addWidget(sep)

        self._nav = QHBoxLayout()
        self._btn_cancel = create_secondary_button(self, "Cancelar", "Cancelar el corte")
        self._btn_cancel.clicked.connect(self.reject)

        self._btn_back = create_secondary_button(self, "◀ Anterior", "Volver al paso anterior")
        self._btn_back.setEnabled(False)
        self._btn_back.clicked.connect(self._prev_page)

        self._btn_next = create_primary_button(self, "Siguiente ▶", "Continuar al siguiente paso")
        self._btn_next.clicked.connect(self._next_page)

        self._nav.addWidget(self._btn_cancel)
        self._nav.addStretch()
        self._nav.addWidget(self._btn_back)
        self._nav.addWidget(self._btn_next)
        root.addLayout(self._nav)

    def _build_step_indicator(self) -> QFrame:
        f = QFrame()
        f.setStyleSheet("background: transparent; border: none;")
        lay = QHBoxLayout(f)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(Spacing.XS)
        lay.addStretch()

        self._step_labels = []
        steps = ["1. Contar efectivo", "2. Confirmar total", "3. Resultado"]
        for i, text in enumerate(steps):
            lbl = QLabel(text)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(self._step_style(i == 0))
            lbl.setContentsMargins(Spacing.MD, Spacing.XS, Spacing.MD, Spacing.XS)
            self._step_labels.append(lbl)
            lay.addWidget(lbl)

            if i < len(steps) - 1:
                arr = QLabel("›")
                arr.setStyleSheet(
                    f"color: {Colors.NEUTRAL.SLATE_400}; font-size: 16px;"
                    f" background: transparent; border: none;"
                )
                lay.addWidget(arr)

        lay.addStretch()
        return f

    def _step_style(self, active: bool) -> str:
        if active:
            return (
                f"background: {Colors.PRIMARY.BASE}; color: {Colors.NEUTRAL.WHITE};"
                f" font-size: {Typography.SIZE_SM}; font-weight: {Typography.WEIGHT_SEMIBOLD};"
                f" border-radius: {Borders.RADIUS_MD}px; border: none;"
            )
        return (
            f"background: {Colors.NEUTRAL.SLATE_100}; color: {Colors.NEUTRAL.SLATE_500};"
            f" font-size: {Typography.SIZE_SM}; font-weight: {Typography.WEIGHT_NORMAL};"
            f" border-radius: {Borders.RADIUS_MD}px; border: none;"
        )

    def _update_steps(self, active_idx: int):
        for i, lbl in enumerate(self._step_labels):
            lbl.setStyleSheet(self._step_style(i == active_idx))

    # ── Page 1: Denomination count ────────────────────────────────────────────

    def _page_arqueo(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(Spacing.MD)

        sub = QLabel("Cuenta los billetes y monedas del cajón")
        sub.setObjectName("subheading")
        lay.addWidget(sub)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        grid_frame = QFrame()
        grid_frame.setObjectName("kpiCard")
        grid = QGridLayout(grid_frame)
        grid.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        grid.setHorizontalSpacing(Spacing.LG)
        grid.setVerticalSpacing(Spacing.MD)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(4, 1)

        self._den_spins  = {}
        self._den_labels = {}
        for i, (label, valor) in enumerate(self.DENOMINACIONES):
            row_idx = i // 2
            col     = (i % 2) * 4

            lbl_den = QLabel(f"<b>{label}</b>")
            lbl_den.setMinimumWidth(56)
            lbl_den.setStyleSheet("background: transparent; border: none;")
            grid.addWidget(lbl_den, row_idx, col)

            spin = QDoubleSpinBox()
            spin.setRange(0, 9999)
            spin.setDecimals(0)
            spin.setSuffix(" pzas")
            spin.setMinimumWidth(100)
            spin.setObjectName("inputField")
            spin.valueChanged.connect(self._recalcular_arqueo)
            self._den_spins[valor] = spin
            grid.addWidget(spin, row_idx, col + 1)

            lbl_sub = QLabel("$0.00")
            lbl_sub.setMinimumWidth(76)
            lbl_sub.setStyleSheet(
                f"color: {Colors.NEUTRAL.SLATE_500}; font-size: {Typography.SIZE_SM};"
                f" background: transparent; border: none;"
            )
            self._den_labels[valor] = lbl_sub
            grid.addWidget(lbl_sub, row_idx, col + 2)

            if i % 2 == 0 and i < len(self.DENOMINACIONES) - 1:
                sep = QFrame()
                sep.setFrameShape(QFrame.VLine)
                sep.setStyleSheet(
                    f"background: {Colors.NEUTRAL.SLATE_200}; border: none;"
                )
                grid.addWidget(sep, row_idx, 3, 1, 1)

            grid.setRowMinimumHeight(row_idx, 32)

        scroll.setWidget(grid_frame)
        lay.addWidget(scroll, 1)

        total_frame = QFrame()
        total_frame.setStyleSheet(
            f"background: {Colors.SUCCESS.BG_SOFT}; border-radius: {Borders.RADIUS_LG}px;"
            f" border: 1px solid {Colors.SUCCESS.BORDER};"
        )
        total_lay = QHBoxLayout(total_frame)
        total_lay.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        total_lbl = QLabel("Total contado:")
        total_lbl.setStyleSheet(
            f"color: {Colors.SUCCESS.ACTIVE}; font-weight: {Typography.WEIGHT_SEMIBOLD};"
            f" background: transparent; border: none;"
        )
        self.lbl_total_arq = QLabel("$0.00")
        self.lbl_total_arq.setStyleSheet(
            f"color: {Colors.SUCCESS.ACTIVE}; font-size: {_KPI_FONT_LARGE};"
            f" font-weight: {Typography.WEIGHT_BOLD}; background: transparent; border: none;"
        )
        total_lay.addWidget(total_lbl)
        total_lay.addStretch()
        total_lay.addWidget(self.lbl_total_arq)
        lay.addWidget(total_frame)
        return w

    def _recalcular_arqueo(self):
        total = 0.0
        for valor, spin in self._den_spins.items():
            sub = float(valor) * spin.value()
            total += sub
            self._den_labels[valor].setText(f"${sub:,.2f}")
        self.total_contado = total
        self.lbl_total_arq.setText(f"${total:,.2f}")

    # ── Page 2: Confirmation ──────────────────────────────────────────────────

    def _page_confirmar(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(Spacing.MD)

        sub = QLabel("Confirma el total que contaste")
        sub.setObjectName("subheading")
        lay.addWidget(sub)

        info_frame = QFrame()
        info_frame.setStyleSheet(
            f"background: {Colors.INFO.BG_SOFT}; border-radius: {Borders.RADIUS_LG}px;"
            f" border: 1px solid {Colors.INFO.BORDER};"
        )
        info_lay = QVBoxLayout(info_frame)
        info_lay.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        info_txt = QLabel(
            "El total del arqueo se muestra abajo. "
            "Si es correcto, haz clic en CONFIRMAR CORTE. "
            "El sistema calculará la diferencia en ese momento."
        )
        info_txt.setWordWrap(True)
        info_txt.setStyleSheet(
            f"color: {Colors.INFO.ACTIVE}; font-size: {Typography.SIZE_SM};"
            f" background: transparent; border: none;"
        )
        info_lay.addWidget(info_txt)
        lay.addWidget(info_frame)

        form_frame = QFrame()
        form_frame.setObjectName("kpiCard")
        form = QFormLayout(form_frame)
        form.setSpacing(Spacing.MD)
        form.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        form.setLabelAlignment(Qt.AlignRight)

        self.spin_total_fisico = QDoubleSpinBox()
        self.spin_total_fisico.setRange(0, 9_999_999)
        self.spin_total_fisico.setDecimals(2)
        self.spin_total_fisico.setPrefix("$ ")
        self.spin_total_fisico.setObjectName("inputField")
        form.addRow("Efectivo contado:", self.spin_total_fisico)

        self.txt_observaciones = QLineEdit()
        self.txt_observaciones.setPlaceholderText(
            "Observaciones opcionales (ej. faltante detectado antes del corte)"
        )
        self.txt_observaciones.setObjectName("inputField")
        form.addRow("Observaciones:", self.txt_observaciones)

        lay.addWidget(form_frame)
        lay.addStretch()
        return w

    # ── Page 3: Result ────────────────────────────────────────────────────────

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
            self._update_steps(1)
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
            self._update_steps(0)
            self._btn_back.setEnabled(False)
            self._btn_next.setText("Siguiente ▶")
            self._btn_next.setToolTip("Continuar al siguiente paso")

    def _ejecutar_corte(self):
        efectivo = self.spin_total_fisico.value()
        obs      = self.txt_observaciones.text().strip()

        try:
            svc = getattr(self.container, 'caja_service', None)
            if svc is None:
                svc = self.container.finance_service
                resultado = svc.generar_corte_z(
                    self.turno_id, self.sucursal_id, self.cajero, efectivo
                )
            else:
                resultado = svc.generar_corte_z(
                    self.turno_id, self.sucursal_id, self.cajero, efectivo, obs
                )
            self.resultado = resultado

            dif      = resultado.get("diferencia", 0)
            esperado = resultado.get("efectivo_esperado", resultado.get("esperado", 0))

            if abs(dif) < 0.01:
                dif_txt   = "✅  CAJA CUADRADA"
                dif_color = Colors.SUCCESS.BASE
            elif dif < 0:
                dif_txt   = f"⚠️  FALTANTE  ${abs(dif):,.2f}"
                dif_color = Colors.DANGER.HOVER
            else:
                dif_txt   = f"ℹ️  SOBRANTE  ${dif:,.2f}"
                dif_color = Colors.WARNING.BASE

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
                f"<table width='100%' cellspacing='6' style='font-size:{Typography.SIZE_LG};text-align:left;'>"
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
                f"<td align='right'><b style='color:{dif_color};'>${dif:+,.2f}</b></td></tr>"
                f"</table>"
            )
            if obs:
                html += (
                    f"<p style='color:{Colors.NEUTRAL.SLATE_500};"
                    f"font-size:{Typography.SIZE_SM};'>Obs: {obs}</p>"
                )

            self.lbl_resultado.setText(html)
            self._stack.setCurrentIndex(2)
            self._update_steps(2)
            self._btn_back.setEnabled(False)

            idx = self._nav.indexOf(self._btn_next)
            if idx != -1:
                self._nav.removeWidget(self._btn_next)
                self._btn_next.deleteLater()

            self._btn_next = create_primary_button(
                self, "🖨️ Cerrar e Imprimir", "Cerrar el corte e imprimir comprobante"
            )
            self._btn_next.clicked.connect(self.accept)
            self._nav.insertWidget(idx, self._btn_next)
            self._btn_cancel.setEnabled(False)

        except Exception as e:
            import logging
            logging.getLogger(__name__).error("_ejecutar_corte: %s", e)
            QMessageBox.critical(self, "Error al ejecutar corte", str(e))

    def get_resultado(self):
        return self.resultado


# ── Main module ───────────────────────────────────────────────────────────────

class ModuloCaja(QWidget, RefreshMixin):
    """Módulo Visual Enterprise para el control de la Caja Registradora."""

    def __init__(self, container, parent=None):
        super().__init__(parent)
        try:
            self._init_refresh(container, ["VENTA_COMPLETADA"])
        except Exception:
            pass
        self.container      = container
        self.sucursal_id    = 1
        self.usuario_actual = ""
        self.rol_actual     = "cajero"
        self.turno_actual   = None

        self.init_ui()

        from PyQt5.QtWidgets import QShortcut
        from PyQt5.QtGui import QKeySequence
        try:
            QShortcut(QKeySequence("F1"),  self).activated.connect(self.abrir_caja)
            QShortcut(QKeySequence("F2"),  self).activated.connect(self._abrir_dialogo_movimiento)
            QShortcut(QKeySequence("F3"),  self).activated.connect(self.cerrar_caja)
            QShortcut(QKeySequence("F10"), self).activated.connect(self.cerrar_caja)
        except Exception:
            pass

    # ── Service helper ────────────────────────────────────────────────────────

    @property
    def _caja_svc(self):
        return getattr(self.container, 'caja_service', None)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_sucursal(self, sucursal_id: int, nombre_sucursal: str):
        self.sucursal_id = sucursal_id
        self.verificar_estado_caja()

    def set_usuario_actual(self, usuario: str, rol: str):
        self.usuario_actual = usuario
        self.rol_actual     = rol or "cajero"
        self.verificar_estado_caja()

    # ── UI construction ───────────────────────────────────────────────────────

    def init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.XL, Spacing.LG, Spacing.XL, Spacing.LG)
        root.setSpacing(Spacing.LG)

        root.addWidget(self._build_header())
        root.addWidget(self._build_kpi_bar())
        root.addWidget(self._build_turno_card())
        root.addWidget(self._build_quick_actions())
        root.addWidget(self._build_tabs(), 1)

    def _build_header(self) -> QWidget:
        try:
            return PageHeader(
                title="Gestión de Caja Registradora",
                subtitle="Control de turnos, movimientos y cortes Z",
                parent=self,
            )
        except Exception:
            lbl = QLabel("💵  Gestión de Caja Registradora")
            lbl.setObjectName("heading")
            return lbl

    def _build_kpi_bar(self) -> QWidget:
        container = QWidget(self)
        lyt = QHBoxLayout(container)
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.setSpacing(Spacing.LG)

        self._kpi_fondo   = _CajaKPICard("Fondo inicial",   "—", "💰", "primary")
        self._kpi_ventas  = _CajaKPICard("Ventas turno",    "—", "📈", "success")
        self._kpi_movs    = _CajaKPICard("Movimientos",     "—", "⚖️",  "warning")
        self._kpi_cortes  = _CajaKPICard("Cortes hoy",      "—", "🔒", "info")

        for card in (self._kpi_fondo, self._kpi_ventas,
                     self._kpi_movs, self._kpi_cortes):
            lyt.addWidget(card)

        return container

    def _build_turno_card(self) -> QFrame:
        card = QFrame(self)
        card.setObjectName("kpiCard")
        lay = QHBoxLayout(card)
        lay.setContentsMargins(Spacing.XL, Spacing.LG, Spacing.XL, Spacing.LG)
        lay.setSpacing(Spacing.LG)

        self._lbl_turno_icono = QLabel("⏸")
        self._lbl_turno_icono.setFixedSize(48, 48)
        self._lbl_turno_icono.setAlignment(Qt.AlignCenter)
        self._lbl_turno_icono.setStyleSheet(
            f"font-size: 22px; background: {Colors.NEUTRAL.SLATE_100};"
            f" border-radius: 24px; border: none;"
        )
        lay.addWidget(self._lbl_turno_icono)

        info = QVBoxLayout()
        info.setSpacing(2)
        self._lbl_turno_titulo = QLabel("ESTADO DEL TURNO")
        self._lbl_turno_titulo.setStyleSheet(
            f"color: {Colors.NEUTRAL.SLATE_500}; font-size: {Typography.SIZE_XS};"
            f" font-weight: {Typography.WEIGHT_SEMIBOLD}; letter-spacing: 0.08em;"
            f" background: transparent; border: none;"
        )
        self._lbl_turno_status = QLabel("Buscando estado del turno...")
        self._lbl_turno_status.setStyleSheet(
            f"font-size: {Typography.SIZE_XL}; font-weight: {Typography.WEIGHT_BOLD};"
            f" background: transparent; border: none;"
        )
        info.addWidget(self._lbl_turno_titulo)
        info.addWidget(self._lbl_turno_status)
        lay.addLayout(info, 1)

        self._btn_accion_turno = create_primary_button(
            self, "Acción de Turno", "Abrir o cerrar turno de caja"
        )
        self._btn_accion_turno.setMinimumWidth(180)
        self._btn_accion_turno.clicked.connect(self.gestionar_turno)
        lay.addWidget(self._btn_accion_turno)

        self._turno_card = card
        return card

    def _build_quick_actions(self) -> QFrame:
        bar = QFrame(self)
        bar.setObjectName("kpiCard")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(Spacing.XL, Spacing.MD, Spacing.XL, Spacing.MD)
        lay.setSpacing(Spacing.MD)

        lbl = QLabel("Acciones rápidas:")
        lbl.setStyleSheet(
            f"color: {Colors.NEUTRAL.SLATE_500}; font-size: {Typography.SIZE_SM};"
            f" font-weight: {Typography.WEIGHT_SEMIBOLD}; background: transparent; border: none;"
        )
        lay.addWidget(lbl)
        lay.addSpacing(Spacing.SM)

        self._btn_mov = create_success_button(
            self, "💸 Ingreso / Retiro  [F2]",
            "Registrar movimiento de efectivo (ingreso o retiro)"
        )
        self._btn_mov.clicked.connect(self._abrir_dialogo_movimiento)
        self._btn_mov.setEnabled(False)
        lay.addWidget(self._btn_mov)

        self._btn_refresh_kpi = create_secondary_button(
            self, "↻ Actualizar KPIs", "Recargar indicadores del turno"
        )
        self._btn_refresh_kpi.clicked.connect(self._refresh_kpi_bar)
        lay.addWidget(self._btn_refresh_kpi)

        lay.addStretch()

        self._btn_corte_z = create_danger_button(
            self, "🔒 Corte Z  [F10]", "Cerrar turno y generar corte Z"
        )
        self._btn_corte_z.clicked.connect(self.cerrar_caja)
        self._btn_corte_z.setEnabled(False)
        lay.addWidget(self._btn_corte_z)

        return bar

    def _build_tabs(self) -> QTabWidget:
        self._tabs_caja = QTabWidget(self)
        self._tabs_caja.currentChanged.connect(self._on_tab_change)

        # Tab 0: Resumen
        self._tab_resumen = QWidget()
        self._tabs_caja.addTab(self._tab_resumen, "📊 Resumen")

        # Tab 1: Movimientos
        self._tab_movs = QWidget()
        self._tabs_caja.addTab(self._tab_movs, "📋 Movimientos")

        # Tab 2: Arqueo
        self._tab_arqueo = QWidget()
        self._tabs_caja.addTab(self._tab_arqueo, "🔢 Arqueo")

        # Tab 3: Historial
        self._tab_hist = QWidget()
        self._tabs_caja.addTab(self._tab_hist, "📜 Historial")

        self._build_tab_resumen()
        self._build_tab_movimientos()
        self._build_tab_arqueo()
        self._build_tab_historial()

        return self._tabs_caja

    # ── Tab: Resumen ──────────────────────────────────────────────────────────

    def _build_tab_resumen(self) -> None:
        lay = QVBoxLayout(self._tab_resumen)
        lay.setContentsMargins(Spacing.XL, Spacing.XL, Spacing.XL, Spacing.XL)
        lay.setSpacing(Spacing.LG)

        hdr = QLabel("Resumen del Turno Activo")
        hdr.setObjectName("subheading")
        lay.addWidget(hdr)

        # Two-column card layout: left column + right column
        cols_layout = QHBoxLayout()
        cols_layout.setSpacing(Spacing.LG)

        left_frame  = QFrame(); left_frame.setObjectName("kpiCard")
        right_frame = QFrame(); right_frame.setObjectName("kpiCard")
        for f in (left_frame, right_frame):
            f.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            f.setMinimumWidth(260)
        left_form  = QFormLayout(left_frame)
        right_form = QFormLayout(right_frame)
        for frm in (left_form, right_form):
            frm.setContentsMargins(Spacing.XL, Spacing.XL, Spacing.XL, Spacing.XL)
            frm.setSpacing(Spacing.LG)
            frm.setLabelAlignment(Qt.AlignRight)
            frm.setHorizontalSpacing(Spacing.XL)

        def _make_row(label_txt: str, attr: str, form: "QFormLayout"):
            lbl_key = QLabel(label_txt)
            lbl_key.setStyleSheet(
                f"color: {Colors.NEUTRAL.SLATE_500}; font-size: {Typography.SIZE_SM};"
                f" background: transparent; border: none;"
            )
            lbl_val = QLabel("—")
            lbl_val.setMinimumHeight(30)
            lbl_val.setStyleSheet(
                f"font-size: {Typography.SIZE_XXL}; font-weight: {Typography.WEIGHT_SEMIBOLD};"
                f" background: transparent; border: none;"
            )
            form.addRow(lbl_key, lbl_val)
            setattr(self, attr, lbl_val)

        _make_row("Cajero:",          "_res_cajero",    left_form)
        _make_row("Turno abierto:",   "_res_apertura",  left_form)
        _make_row("Fondo inicial:",   "_res_fondo",     left_form)
        _make_row("Ingresos extra:",  "_res_ingresos",  left_form)

        _make_row("Ventas totales:",      "_res_ventas",    right_form)
        _make_row("Retiros:",             "_res_retiros",   right_form)
        _make_row("Efectivo esperado:",   "_res_esperado",  right_form)

        cols_layout.addWidget(left_frame, 1)
        cols_layout.addWidget(right_frame, 1)
        lay.addLayout(cols_layout)

        btn_refresh = create_secondary_button(
            self, "↻ Actualizar resumen", "Recargar resumen del turno"
        )
        btn_refresh.clicked.connect(self._cargar_resumen_turno)
        lay.addWidget(btn_refresh, 0, Qt.AlignLeft)
        lay.addStretch()

    def _cargar_resumen_turno(self) -> None:
        svc = self._caja_svc
        if not svc or not self.usuario_actual:
            return
        try:
            turno = svc.get_estado_turno(self.sucursal_id, self.usuario_actual)
            if not turno:
                for attr in ("_res_cajero", "_res_apertura", "_res_fondo",
                             "_res_ventas", "_res_ingresos", "_res_retiros", "_res_esperado"):
                    getattr(self, attr, QLabel()).setText("—")
                return

            kpis = svc.get_caja_kpis(self.sucursal_id, self.usuario_actual)

            self._res_cajero.setText(self.usuario_actual)
            self._res_apertura.setText(str(turno.get('hora_apertura', turno.get('fecha_apertura', '—')))[:16])
            self._res_fondo.setText(f"${float(turno.get('fondo_inicial', 0)):,.2f}")
            self._res_ventas.setText(f"${float(kpis.get('total_ventas_turno', 0)):,.2f}")
            self._res_ingresos.setText(f"${float(kpis.get('total_ingresos', 0)):,.2f}")
            self._res_retiros.setText(f"${float(kpis.get('total_retiros', 0)):,.2f}")
            esperado = (
                float(turno.get('fondo_inicial', 0))
                + float(kpis.get('total_ventas_turno', 0))
                + float(kpis.get('total_ingresos', 0))
                - float(kpis.get('total_retiros', 0))
            )
            self._res_esperado.setText(f"${esperado:,.2f}")
        except Exception:
            pass

    # ── Tab: Movimientos ──────────────────────────────────────────────────────

    def _build_tab_movimientos(self) -> None:
        lay = QVBoxLayout(self._tab_movs)
        lay.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        lay.setSpacing(Spacing.MD)

        hdr = QHBoxLayout()
        lbl = QLabel("Movimientos de efectivo del turno activo")
        lbl.setObjectName("subheading")
        hdr.addWidget(lbl)
        hdr.addStretch()
        btn_ref = create_secondary_button(self, "↻", "Recargar movimientos")
        btn_ref.setFixedWidth(34)
        btn_ref.clicked.connect(self._cargar_movimientos_turno)
        hdr.addWidget(btn_ref)
        lay.addLayout(hdr)

        self._tbl_movs = create_table_with_columns(
            self,
            columns=["Hora", "Tipo", "Concepto", "Monto", "Usuario", "ID Turno"],
            show_grid=False,
            alternating_colors=True,
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
            rows_raw = svc.get_movimientos_turno(self.turno_actual, self.rol_actual) if svc else []
        except Exception:
            rows_raw = []

        ingresos = retiros = ventas = 0.0
        from PyQt5.QtGui import QColor

        for ri, r in enumerate(rows_raw):
            self._tbl_movs.insertRow(ri)
            fecha_str = str(r.get('fecha', r[0] if isinstance(r, (list, tuple)) else '') or "")[:16]
            tipo      = str(r.get('tipo',  r[1] if isinstance(r, (list, tuple)) else '') or "")
            concepto  = str(r.get('concepto', r[2] if isinstance(r, (list, tuple)) else '') or "")
            monto     = float(r.get('monto', r[3] if isinstance(r, (list, tuple)) else 0) or 0)
            usuario   = str(r.get('usuario', r[4] if isinstance(r, (list, tuple)) else 'Sistema') or "Sistema")
            turno_id  = str(r.get('turno_id', r[5] if isinstance(r, (list, tuple)) else '') or "")

            es_gerente = getattr(self, 'rol_actual', 'cajero').lower() in ('admin', 'administrador', 'gerente')
            monto_display = f"${monto:,.2f}" if es_gerente else "***"

            vals = [fecha_str, tipo, concepto, monto_display, usuario, turno_id]
            for ci, val in enumerate(vals):
                it = QTableWidgetItem(val)
                it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                if tipo == "VENTA":
                    it.setForeground(QColor(Colors.SUCCESS.BASE))
                elif tipo in ("RETIRO", "GASTO"):
                    it.setForeground(QColor(Colors.DANGER.BASE))
                self._tbl_movs.setItem(ri, ci, it)

            if tipo == "VENTA":
                ventas   += monto
            elif tipo == "INGRESO":
                ingresos += monto
            elif tipo in ("RETIRO", "GASTO"):
                retiros  += monto

        fondo = 0.0
        try:
            if svc:
                turno = svc.get_estado_turno(self.sucursal_id, self.usuario_actual)
                if turno:
                    fondo = float(turno.get('fondo_inicial', 0) or 0)
        except Exception:
            pass

        neto       = fondo + ventas + ingresos - retiros
        es_gerente = getattr(self, 'rol_actual', 'cajero').lower() in ('admin', 'administrador', 'gerente')

        if es_gerente:
            self.lbl_mov_ingresos.setText(f"Ingresos: ${ingresos:,.2f}")
            self.lbl_mov_retiros.setText(f"Retiros: ${retiros:,.2f}")
            self.lbl_mov_ventas.setText(f"Ventas: ${ventas:,.2f}")
            self.lbl_mov_neto.setText(f"Neto en caja: ${neto:,.2f}")
        else:
            n_ing = sum(1 for r in rows_raw if str(r.get('tipo','') if isinstance(r,dict) else r[1]) == 'INGRESO')
            n_ret = sum(1 for r in rows_raw if str(r.get('tipo','') if isinstance(r,dict) else r[1]) in ('RETIRO','GASTO'))
            n_ven = sum(1 for r in rows_raw if str(r.get('tipo','') if isinstance(r,dict) else r[1]) == 'VENTA')
            self.lbl_mov_ingresos.setText(f"Entradas: {n_ing} mov.")
            self.lbl_mov_retiros.setText(f"Retiros: {n_ret} mov.")
            self.lbl_mov_ventas.setText(f"Ventas: {n_ven} registradas")
            self.lbl_mov_neto.setText("Corte al cerrar turno")
            self.lbl_mov_neto.setObjectName("badge-neutral")

    # ── Tab: Arqueo ───────────────────────────────────────────────────────────

    def _build_tab_arqueo(self) -> None:
        lay = QVBoxLayout(self._tab_arqueo)
        lay.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        lay.setSpacing(Spacing.LG)

        info = create_label(
            self,
            "Cuenta los billetes y monedas del cajón para verificar el cierre.",
            "caption",
        )
        lay.addWidget(info)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        grid_frame = QFrame()
        grid_frame.setObjectName("kpiCard")
        grid = QGridLayout(grid_frame)
        grid.setContentsMargins(Spacing.XL, Spacing.XL, Spacing.XL, Spacing.XL)
        grid.setHorizontalSpacing(Spacing.XL)
        grid.setVerticalSpacing(Spacing.LG)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(4, 1)

        DENOMINACIONES = [
            ("$1,000", 1000), ("$500", 500), ("$200", 200), ("$100", 100),
            ("$50", 50), ("$20", 20), ("$10", 10), ("$5", 5),
            ("$2", 2), ("$1", 1), ("$0.50", 0.5),
        ]
        self._arqueo_spins      = {}
        self._arqueo_sub_labels = {}

        for i, (label, valor) in enumerate(DENOMINACIONES):
            col     = (i % 2) * 4   # cols 0-2 left block, cols 4-6 right block
            row_idx = i // 2

            lbl_den = QLabel(label)
            lbl_den.setObjectName("subheading")
            lbl_den.setMinimumWidth(60)
            grid.addWidget(lbl_den, row_idx, col)

            spin = QDoubleSpinBox()
            spin.setRange(0, 9999)
            spin.setDecimals(0)
            spin.setSuffix(" pzas")
            spin.setMinimumWidth(110)
            spin.setObjectName("inputField")
            spin.valueChanged.connect(self._calcular_arqueo)
            self._arqueo_spins[valor] = spin
            grid.addWidget(spin, row_idx, col + 1)

            lbl_sub = QLabel("$0.00")
            lbl_sub.setObjectName(f"lbl_arq_{valor}")
            lbl_sub.setMinimumWidth(80)
            lbl_sub.setStyleSheet(
                f"color: {Colors.NEUTRAL.SLATE_500}; font-size: {Typography.SIZE_SM};"
                f" background: transparent; border: none;"
            )
            self._arqueo_sub_labels[valor] = lbl_sub
            grid.addWidget(lbl_sub, row_idx, col + 2)

            # vertical separator between left and right blocks
            if i % 2 == 0 and i < len(DENOMINACIONES) - 1:
                sep = QFrame()
                sep.setFrameShape(QFrame.VLine)
                sep.setStyleSheet(
                    f"background: {Colors.NEUTRAL.SLATE_200}; border: none;"
                )
                grid.addWidget(sep, row_idx, 3, 1, 1)

            grid.setRowMinimumHeight(row_idx, 34)

        scroll.setWidget(grid_frame)
        lay.addWidget(scroll)

        total_row = QHBoxLayout()
        total_row.addStretch()
        self.lbl_diferencia_arqueo = QLabel("")
        self.lbl_diferencia_arqueo.setObjectName("badge-neutral")
        self.lbl_total_arqueo = QLabel("Total contado: $0.00")
        self.lbl_total_arqueo.setObjectName("subheading")
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
                total   += subtotal
                lbl = self._arqueo_sub_labels.get(valor)
                if lbl:
                    lbl.setText(f"${subtotal:,.2f}")
            self.lbl_total_arqueo.setText(f"Total contado: ${total:,.2f}")

            if self.turno_actual:
                try:
                    svc = self._caja_svc
                    if svc:
                        arqueo = svc.calcular_arqueo(self.turno_actual, total)
                        if 'error' not in arqueo:
                            sistema = arqueo.get('esperado', 0)
                            diff    = total - sistema
                            color   = Colors.SUCCESS.BASE if abs(diff) < 0.01 else Colors.DANGER.HOVER
                            self.lbl_diferencia_arqueo.setText(
                                f"Sistema (esperado): ${sistema:,.2f} | Diferencia: "
                                f"<span style='color:{color}'>${diff:+.2f}</span>"
                            )
                except Exception:
                    pass
        except Exception:
            pass

    def _limpiar_arqueo(self) -> None:
        for spin in self._arqueo_spins.values():
            spin.setValue(0)

    # ── Tab: Historial ────────────────────────────────────────────────────────

    def _build_tab_historial(self) -> None:
        lay = QVBoxLayout(self._tab_hist)
        lay.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        lay.setSpacing(Spacing.MD)

        lay.addWidget(create_subheading(self, "Historial de cortes Z y X de esta sucursal"))

        self._tbl_hist = QTableWidget()
        self._tbl_hist.setColumnCount(6)
        self._tbl_hist.setHorizontalHeaderLabels(
            ["Tipo", "Fecha", "Cajero", "Ventas", "Efectivo", "Acciones"]
        )
        hh = self._tbl_hist.horizontalHeader()
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        self._tbl_hist.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_hist.verticalHeader().setVisible(False)
        self._tbl_hist.setAlternatingRowColors(True)
        lay.addWidget(self._tbl_hist)

    def _cargar_historial_cortes(self) -> None:
        svc = self._caja_svc
        try:
            rows = svc.get_historial_cortes(self.sucursal_id, limit=100) if svc else []
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

            btn_w   = QWidget()
            btn_lay = QHBoxLayout(btn_w)
            btn_lay.setContentsMargins(2, 2, 2, 2)
            btn_r = create_secondary_button(self, "🖨️ Reimprimir", "Reimprimir comprobante de corte")
            btn_r.clicked.connect(lambda _, cid=cierre_id: self._reimprimir_corte(cid))
            btn_lay.addWidget(btn_r)
            self._tbl_hist.setCellWidget(ri, 5, btn_w)

    # ── Tab change handler ────────────────────────────────────────────────────

    def _on_tab_change(self, idx: int) -> None:
        if idx == 0:
            self._cargar_resumen_turno()
        elif idx == 1:
            self._cargar_movimientos_turno()
        elif idx == 2:
            self._init_arqueo()
        elif idx == 3:
            self._cargar_historial_cortes()

    # ── Auto-refresh ──────────────────────────────────────────────────────────

    def _on_refresh(self, event_type: str, data: dict) -> None:
        try:
            self.verificar_estado_caja()   # also calls _refresh_kpi_bar
            if self.turno_actual:
                self._cargar_movimientos_turno()
                self._refresh_kpi_bar()
        except Exception:
            pass

    # ── KPI bar refresh ───────────────────────────────────────────────────────

    def _refresh_kpi_bar(self) -> None:
        import logging
        _log = logging.getLogger(__name__)
        try:
            svc = self._caja_svc
            if not svc or not self.usuario_actual:
                return
            kpi = svc.get_caja_kpis(self.sucursal_id, self.usuario_actual)
            self._kpi_fondo.set_valor(f"${float(kpi.get('fondo_inicial', 0)):,.0f}")
            self._kpi_ventas.set_valor(f"${float(kpi.get('total_ventas_turno', 0)):,.0f}")
            self._kpi_movs.set_valor(str(kpi.get('num_movimientos_hoy', 0)))
            self._kpi_cortes.set_valor(str(kpi.get('num_cortes_hoy', 0)))
        except Exception as e:
            _log.warning("_refresh_kpi_bar: %s", e)

    # ── Turno state ───────────────────────────────────────────────────────────

    def verificar_estado_caja(self):
        if not self.usuario_actual:
            return
        try:
            svc   = self._caja_svc
            turno = svc.get_estado_turno(self.sucursal_id, self.usuario_actual) if svc else None

            if turno:
                self.turno_actual = turno['id']

                self._lbl_turno_icono.setText("✅")
                self._lbl_turno_icono.setStyleSheet(
                    f"font-size: 22px; background: {Colors.SUCCESS.BG_SOFT};"
                    f" border-radius: 24px; border: none;"
                )
                self._lbl_turno_status.setText(
                    f"TURNO ABIERTO  —  Fondo: ${turno['fondo_inicial']:.2f}"
                )
                self._lbl_turno_status.setStyleSheet(
                    f"font-size: {Typography.SIZE_XL}; font-weight: {Typography.WEIGHT_BOLD};"
                    f" color: {Colors.SUCCESS.BASE}; background: transparent; border: none;"
                )

                self._btn_accion_turno.setText("🔓 TURNO ABIERTO")
                self._btn_accion_turno.setEnabled(False)

                self._btn_mov.setEnabled(True)
                self._btn_corte_z.setEnabled(True)

            else:
                self.turno_actual = None

                self._lbl_turno_icono.setText("❌")
                self._lbl_turno_icono.setStyleSheet(
                    f"font-size: 22px; background: {Colors.DANGER.BG_SOFT};"
                    f" border-radius: 24px; border: none;"
                )
                self._lbl_turno_status.setText("CAJA CERRADA — Sin turno activo")
                self._lbl_turno_status.setStyleSheet(
                    f"font-size: {Typography.SIZE_XL}; font-weight: {Typography.WEIGHT_BOLD};"
                    f" color: {Colors.DANGER.BASE}; background: transparent; border: none;"
                )

                self._btn_accion_turno.setText("🔓 ABRIR TURNO DE CAJA  [F1]")
                self._btn_accion_turno.setEnabled(True)

                self._btn_mov.setEnabled(False)
                self._btn_corte_z.setEnabled(False)

            self._refresh_kpi_bar()

        except Exception as e:
            self._lbl_turno_status.setText("Error leyendo estado de caja.")
            import logging
            logging.getLogger(__name__).error("verificar_estado_caja: %s", e)

    def gestionar_turno(self):
        if self.turno_actual is None:
            self.abrir_caja()

    # ── Actions ───────────────────────────────────────────────────────────────

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
            value=0.0, min=0.0, max=99_999.0, decimals=2,
        )
        if not ok:
            return

        try:
            svc = self._caja_svc
            if svc:
                svc.abrir_turno(self.sucursal_id, self.usuario_actual, fondo)

            Toast.success(self, "Turno abierto", f"Fondo inicial: ${fondo:.2f}")

            if hasattr(self.container, 'hardware_service'):
                self.container.hardware_service.open_cash_drawer()

            self.verificar_estado_caja()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _abrir_dialogo_movimiento(self):
        try:
            from core.permissions import verificar_permiso
            if not verificar_permiso(self.container, "caja.movimientos", self):
                return
        except Exception:
            pass

        if not self.turno_actual:
            QMessageBox.information(self, "Sin turno", "No hay turno activo. Abre la caja primero.")
            return

        dlg = DialogoMovimientoCaja(parent=self)
        if dlg.exec_() != QDialog.Accepted:
            return

        tipo, monto, concepto = dlg.get_values()
        self.registrar_movimiento(tipo, monto, concepto)

    def registrar_movimiento(self, tipo: str = None, monto: float = None, concepto: str = None):
        """Register a manual cash movement. When called without args, opens the dialog."""
        if tipo is None:
            self._abrir_dialogo_movimiento()
            return

        if not self.turno_actual:
            return

        try:
            svc = self._caja_svc
            if svc:
                svc.registrar_movimiento_manual(
                    self.turno_actual, self.sucursal_id,
                    self.usuario_actual, tipo, monto, concepto,
                )

            Toast.success(self, "Movimiento registrado", f"{tipo} registrado correctamente.")
            try:
                self._cargar_movimientos_turno()
            except Exception:
                pass

            if hasattr(self.container, 'hardware_service'):
                self.container.hardware_service.open_cash_drawer()

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def cerrar_caja(self):
        """Corte Z blind-count flow."""
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

    # ── Printing helpers ──────────────────────────────────────────────────────

    def _fallback_imprimir(self, resultado: dict):
        try:
            from PyQt5.QtWidgets import QDialog as _D, QVBoxLayout as _V, QTextBrowser as _TB
            from PyQt5.QtPrintSupport import QPrinter, QPrintDialog
            from PyQt5.QtGui import QTextDocument
            dados = {
                'fecha':         datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'cajero':        self.usuario_actual,
                'ventas_totales': float(resultado.get('total_ventas', resultado.get('ventas_totales', 0))),
                'retiros':       float(resultado.get('retiros', 0)),
                'esperado':      float(resultado.get('efectivo_esperado', resultado.get('esperado', 0))),
                'contado':       float(resultado.get('efectivo_contado', resultado.get('contado', 0))),
                'diferencia':    float(resultado.get('diferencia', 0)),
                'fondo_inicial': float(resultado.get('fondo_inicial', 0)),
            }
            cierre_id = resultado.get('cierre_id', resultado.get('turno_id', 0))
            html = self._generar_html_corte_simple(dados, cierre_id)
            dlg = _D(self)
            dlg.setWindowTitle("Ticket Corte Z")
            dlg.setMinimumSize(420, 400)
            lay = _V(dlg)
            browser = _TB()
            browser.setHtml(html)
            lay.addWidget(browser)
            btn_row = QHBoxLayout()
            btn_p   = create_primary_button(dlg, "🖨️ Imprimir", "Imprimir")
            btn_c   = create_secondary_button(dlg, "Cerrar", "Cerrar")

            def _print():
                p  = QPrinter(QPrinter.HighResolution)
                pd = QPrintDialog(p, dlg)
                if pd.exec_() == QPrintDialog.Accepted:
                    doc = QTextDocument()
                    doc.setHtml(html)
                    doc.print_(p)

            btn_p.clicked.connect(_print)
            btn_c.clicked.connect(dlg.accept)
            btn_row.addWidget(btn_p)
            btn_row.addStretch()
            btn_row.addWidget(btn_c)
            lay.addLayout(btn_row)
            dlg.exec_()
        except Exception:
            pass

    def _generar_html_corte_simple(self, datos: dict, cierre_id: int) -> str:
        dif = float(datos.get('diferencia', 0))
        if dif < -0.01:
            dif_txt = f"<span style='color:{Colors.DANGER.BASE};'>FALTANTE: ${abs(dif):.2f}</span>"
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

    def _reimprimir_corte(self, cierre_id: int) -> None:
        svc = self._caja_svc
        try:
            d = svc.get_cierre_por_id(cierre_id) if svc else None
            if not d:
                QMessageBox.warning(self, "No encontrado", "No se encontró el corte.")
                return

            datos_r = {
                'fecha':         str(d.get('fecha_cierre', d.get('fecha', ''))),
                'cajero':        d.get('usuario', '?'),
                'ventas_totales': float(d.get('total_ventas', d.get('ventas_totales', 0)) or 0),
                'retiros':       float(d.get('retiros', d.get('total_retiros', 0)) or 0),
                'esperado':      float(d.get('efectivo_esperado', d.get('esperado', 0)) or 0),
                'contado':       float(d.get('efectivo_contado', d.get('contado', d.get('total_efectivo', 0))) or 0),
                'diferencia':    float(d.get('diferencia', 0) or 0),
                'fondo_inicial': float(d.get('fondo_inicial', 0) or 0),
            }

            ticket_svc = getattr(self.container, 'caja_ticket_service', None)
            html = (
                ticket_svc.generar_html_corte(datos_r, cierre_id)
                if ticket_svc
                else self._generar_html_corte_simple(datos_r, cierre_id)
            )
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
