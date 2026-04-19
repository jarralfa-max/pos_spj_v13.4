# modulos/modulo_growth_engine.py — SPJ POS v13.2
"""
UI del Growth Engine: configurar metas comunitarias, misiones,
moneda expirable, y ver métricas de pasivo financiero.
"""
from __future__ import annotations
from modulos.spj_styles import spj_btn, apply_btn_styles, apply_object_names
import logging
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QDialog, QFormLayout, QDialogButtonBox, QLineEdit, QSpinBox,
    QDoubleSpinBox, QComboBox, QCheckBox, QTabWidget, QMessageBox,
    QDateEdit, QGroupBox, QTextEdit,
)
from PyQt5.QtCore import Qt, QDate

logger = logging.getLogger("spj.modulo.growth")


class ModuloGrowthEngine(QWidget):

    def __init__(self, container, parent=None):
        super().__init__(parent)
        self.container   = container
        self.db          = container.db
        self.sucursal_id = 1
        self._engine     = None
        self._build_ui()
        self._cargar_todo()

    def _engine_para(self, sucursal_id=None):
        from modulos.growth_engine import GrowthEngine
        wa = getattr(self.container, 'whatsapp_service', None)
        return GrowthEngine(self.db, sucursal_id or self.sucursal_id, wa)

    def set_usuario_actual(self, u: str, r: str = "") -> None: pass
    def set_sucursal(self, sid: int, nombre: str = "") -> None:
        self.sucursal_id = sid; self._cargar_todo()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        hdr = QHBoxLayout()
        t = QLabel("🚀 Growth Engine — Programa de Fidelidad")
        t.setStyleSheet("font-size:18px;font-weight:bold;")
        hdr.addWidget(t); hdr.addStretch()
        lay.addLayout(hdr)

        tabs = QTabWidget(); lay.addWidget(tabs)

        tabs.addTab(self._build_tab_metas(),    "🎯 Metas Comunitarias")
        tabs.addTab(self._build_tab_misiones(), "🏃 Misiones / Rachas")
        tabs.addTab(self._build_tab_config(),   "⚙️ Configuración")
        tabs.addTab(self._build_tab_finanzas(), "💰 Pasivo Financiero")
        tabs.addTab(self._build_tab_clientes(), "👥 Consulta Cliente")
        apply_object_names(self)

    # ── Tab 1: Metas comunitarias ─────────────────────────────────────────

    def _build_tab_metas(self):
        w = QWidget(); lay = QVBoxLayout(w)
        info = QLabel(
            "Las metas comunitarias se financian solas: el premio solo se libera "
            "cuando las ventas ya superaron el umbral de rentabilidad."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#555;background:#fffbea;padding:6px;border-radius:5px;font-size:11px;")
        lay.addWidget(info)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("➕ Nueva meta"); btn_add.setObjectName("successBtn")
        btn_del = QPushButton("🗑️ Eliminar"); btn_del.setObjectName("dangerBtn")
        btn_row.addWidget(btn_add); btn_row.addWidget(btn_del); btn_row.addStretch()
        lay.addLayout(btn_row)

        self.tbl_metas = QTableWidget(); self.tbl_metas.setColumnCount(7)
        self.tbl_metas.setHorizontalHeaderLabels(
            ["ID", "Nombre", "Umbral $", "Progreso $", "%", "Premio", "Estado"])
        hh = self.tbl_metas.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(5, QHeaderView.Stretch)
        self.tbl_metas.setColumnHidden(0, True)
        self.tbl_metas.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_metas.setSelectionBehavior(QAbstractItemView.SelectRows)
        lay.addWidget(self.tbl_metas)

        btn_add.clicked.connect(self._nueva_meta)
        btn_del.clicked.connect(self._eliminar_meta)
        return w

    def _cargar_metas(self):
        eng = self._engine_para()
        metas = eng.get_metas_activas()
        self.tbl_metas.setRowCount(0)
        for i, m in enumerate(metas):
            self.tbl_metas.insertRow(i)
            pct = int(min(100, (m['progreso']/m['umbral']*100))) if m['umbral'] > 0 else 0
            estado = "✅ Completada" if m['completada'] else f"🔄 {pct}%"
            vals = [str(m['id']), m['nombre'],
                    f"${m['umbral']:,.0f}", f"${m['progreso']:,.0f}",
                    f"{pct}%", m['premio'] or "", estado]
            for j, v in enumerate(vals):
                it = QTableWidgetItem(v)
                if j == 6 and m['completada']:
                    it.setForeground(Qt.darkGreen)
                self.tbl_metas.setItem(i, j, it)

    def _nueva_meta(self):
        dlg = QDialog(self); dlg.setWindowTitle("Nueva Meta Comunitaria"); dlg.setMinimumWidth(400)
        lay = QVBoxLayout(dlg); form = QFormLayout()
        txt_nombre = QLineEdit(); txt_nombre.setPlaceholderText("Ej: Vender 1000 piezas en julio")
        spin_umbral = QDoubleSpinBox(); spin_umbral.setRange(1,9999999); spin_umbral.setPrefix("$"); spin_umbral.setDecimals(2)
        txt_premio = QLineEdit(); txt_premio.setPlaceholderText("Ej: 2x1 el sábado siguiente")
        spin_costo = QDoubleSpinBox(); spin_costo.setRange(0,99999); spin_costo.setPrefix("$"); spin_costo.setDecimals(2)
        date_fin = QDateEdit(QDate.currentDate().addMonths(1)); date_fin.setCalendarPopup(True)
        txt_desc = QTextEdit(); txt_desc.setMaximumHeight(60)
        form.addRow("Nombre *:",       txt_nombre)
        form.addRow("Umbral de ventas:", spin_umbral)
        form.addRow("Premio:",          txt_premio)
        form.addRow("Costo del premio:", spin_costo)
        form.addRow("Fecha límite:",    date_fin)
        form.addRow("Descripción:",     txt_desc)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Save).setText("Aceptar")
        btns.button(QDialogButtonBox.Save).setObjectName("successBtn")
        btns.button(QDialogButtonBox.Cancel).setText("Cancelar")
        btns.button(QDialogButtonBox.Cancel).setObjectName("secondaryBtn")
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec_() != QDialog.Accepted: return
        nombre = txt_nombre.text().strip()
        if not nombre: return
        try:
            eng = self._engine_para()
            eng.crear_meta(
                nombre=nombre, umbral=spin_umbral.value(),
                premio=txt_premio.text().strip(),
                costo_premio=spin_costo.value(),
                descripcion=txt_desc.toPlainText().strip(),
                fecha_fin=date_fin.date().toString("yyyy-MM-dd"),
            )
            self._cargar_metas()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _eliminar_meta(self):
        row = self.tbl_metas.currentRow()
        if row < 0: return
        mid = int(self.tbl_metas.item(row,0).text())
        if QMessageBox.question(self,"Confirmar","¿Desactivar esta meta?",
           QMessageBox.Yes|QMessageBox.No) != QMessageBox.Yes: return
        self.db.execute("UPDATE growth_metas SET activa=0 WHERE id=?", (mid,))
        try: self.db.commit()
        except Exception: pass
        self._cargar_metas()

    # ── Tab 2: Misiones ───────────────────────────────────────────────────

    def _build_tab_misiones(self):
        w = QWidget(); lay = QVBoxLayout(w)
        info = QLabel(
            "Las misiones incentivan recurrencia con TTL: si el cliente no completa "
            "las N compras en la ventana de días, el progreso se reinicia."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#555;background:#fffbea;padding:6px;border-radius:5px;font-size:11px;")
        lay.addWidget(info)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("➕ Nueva misión"); btn_add.setObjectName("successBtn")
        btn_del = QPushButton("🗑️ Desactivar"); btn_del.setObjectName("dangerBtn")
        btn_row.addWidget(btn_add); btn_row.addWidget(btn_del); btn_row.addStretch()
        lay.addLayout(btn_row)

        self.tbl_misiones = QTableWidget(); self.tbl_misiones.setColumnCount(5)
        self.tbl_misiones.setHorizontalHeaderLabels(
            ["ID","Nombre","Condición","Ventana","Premio ⭐"])
        hh = self.tbl_misiones.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        self.tbl_misiones.setColumnHidden(0, True)
        self.tbl_misiones.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_misiones.setSelectionBehavior(QAbstractItemView.SelectRows)
        lay.addWidget(self.tbl_misiones)

        btn_add.clicked.connect(self._nueva_mision)
        btn_del.clicked.connect(self._desactivar_mision)
        return w

    def _cargar_misiones(self):
        eng = self._engine_para()
        misiones = eng.get_misiones_activas()
        self.tbl_misiones.setRowCount(0)
        for i, m in enumerate(misiones):
            self.tbl_misiones.insertRow(i)
            cond = f"{m['condicion_n']} compras ({m['condicion_tipo']})"
            vals = [str(m['id']), m['nombre'], cond,
                    f"{m['ventana_dias']} días", str(m['premio_estrellas'])]
            for j, v in enumerate(vals):
                self.tbl_misiones.setItem(i, j, QTableWidgetItem(v))

    def _nueva_mision(self):
        dlg = QDialog(self); dlg.setWindowTitle("Nueva Misión"); dlg.setMinimumWidth(380)
        lay = QVBoxLayout(dlg); form = QFormLayout()
        txt_nombre = QLineEdit(); txt_nombre.setPlaceholderText("Ej: Compra 3 veces antes de mediodía")
        cmb_tipo = QComboBox()
        cmb_tipo.addItems(["compras_consecutivas","compras_en_ventana","monto_acumulado"])
        spin_n = QSpinBox(); spin_n.setRange(1,50); spin_n.setValue(3)
        spin_dias = QSpinBox(); spin_dias.setRange(1,90); spin_dias.setValue(7); spin_dias.setSuffix(" días")
        spin_premio = QSpinBox(); spin_premio.setRange(1,10000); spin_premio.setValue(100); spin_premio.setSuffix(" ⭐")
        form.addRow("Nombre *:", txt_nombre)
        form.addRow("Tipo:", cmb_tipo)
        form.addRow("N compras:", spin_n)
        form.addRow("Ventana:", spin_dias)
        form.addRow("Premio:", spin_premio)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Save).setText("Aceptar")
        btns.button(QDialogButtonBox.Save).setObjectName("successBtn")
        btns.button(QDialogButtonBox.Cancel).setText("Cancelar")
        btns.button(QDialogButtonBox.Cancel).setObjectName("secondaryBtn")
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec_() != QDialog.Accepted: return
        nombre = txt_nombre.text().strip()
        if not nombre: return
        try:
            eng = self._engine_para()
            eng.crear_mision(
                nombre=nombre, condicion_tipo=cmb_tipo.currentText(),
                condicion_n=spin_n.value(), ventana_dias=spin_dias.value(),
                premio_estrellas=spin_premio.value())
            self._cargar_misiones()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _desactivar_mision(self):
        row = self.tbl_misiones.currentRow()
        if row < 0: return
        mid = int(self.tbl_misiones.item(row,0).text())
        self.db.execute("UPDATE growth_misiones SET activa=0 WHERE id=?", (mid,))
        try: self.db.commit()
        except Exception: pass
        self._cargar_misiones()

    # ── Tab 3: Configuración ─────────────────────────────────────────────

    def _build_tab_config(self):
        w = QWidget(); lay = QVBoxLayout(w)

        grp1 = QGroupBox("Estrellas — reglas de acumulación")
        fc = QFormLayout(grp1)
        self.spin_expiry = QSpinBox(); self.spin_expiry.setRange(30,365); self.spin_expiry.setValue(90); self.spin_expiry.setSuffix(" días")
        self.spin_otp_umbral = QSpinBox(); self.spin_otp_umbral.setRange(1,9999); self.spin_otp_umbral.setValue(200); self.spin_otp_umbral.setSuffix(" ⭐")
        self.spin_costo_estrella = QDoubleSpinBox(); self.spin_costo_estrella.setRange(0.01,100); self.spin_costo_estrella.setValue(0.80); self.spin_costo_estrella.setPrefix("$"); self.spin_costo_estrella.setDecimals(2)
        self.spin_cap = QSpinBox(); self.spin_cap.setRange(1,100); self.spin_cap.setValue(50); self.spin_cap.setSuffix("% del subtotal")
        fc.addRow("Expiración por inactividad:", self.spin_expiry)
        fc.addRow("OTP a partir de:", self.spin_otp_umbral)
        fc.addRow("Costo real por estrella:", self.spin_costo_estrella)
        fc.addRow("Cap de redención:", self.spin_cap)
        lay.addWidget(grp1)

        grp2 = QGroupBox("Velocity limits (antifraude)")
        fv = QFormLayout(grp2)
        self.spin_vel_max = QSpinBox(); self.spin_vel_max.setRange(1,20); self.spin_vel_max.setValue(2)
        self.spin_vel_horas = QSpinBox(); self.spin_vel_horas.setRange(1,24); self.spin_vel_horas.setValue(4); self.spin_vel_horas.setSuffix(" horas")
        fv.addRow("Máx compras acumulables:", self.spin_vel_max)
        fv.addRow("Ventana de tiempo:", self.spin_vel_horas)
        lay.addWidget(grp2)

        btn_save = QPushButton("💾 Guardar configuración")
        btn_save.setObjectName("successBtn")
        btn_save.clicked.connect(self._guardar_config)
        lay.addWidget(btn_save); lay.addStretch()
        self._cargar_config()
        return w

    def _cargar_config(self):
        def g(k, d):
            try:
                r = self.db.execute("SELECT valor FROM configuraciones WHERE clave=?", (k,)).fetchone()
                return r[0] if r else d
            except Exception: return d
        self.spin_expiry.setValue(int(g("growth_expiry_dias","90")))
        self.spin_otp_umbral.setValue(int(g("growth_otp_umbral","200")))
        self.spin_costo_estrella.setValue(float(g("growth_costo_estrella","0.80")))
        self.spin_cap.setValue(int(float(g("growth_cap_pct","0.50"))*100))

    def _guardar_config(self):
        cfg = {
            "growth_expiry_dias":    str(self.spin_expiry.value()),
            "growth_otp_umbral":     str(self.spin_otp_umbral.value()),
            "growth_costo_estrella": str(self.spin_costo_estrella.value()),
            "growth_cap_pct":        str(self.spin_cap.value()/100),
        }
        try:
            for k, v in cfg.items():
                self.db.execute(
                    "INSERT INTO configuraciones(clave,valor) VALUES(?,?) "
                    "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor", (k,v))
            try: self.db.commit()
            except Exception: pass
            QMessageBox.information(self,"✅","Configuración guardada.")
        except Exception as e:
            QMessageBox.critical(self,"Error",str(e))

    # ── Tab 4: Pasivo financiero ─────────────────────────────────────────

    def _build_tab_finanzas(self):
        w = QWidget(); lay = QVBoxLayout(w)
        info = QLabel(
            "El pasivo real del programa se calcula con la fórmula actuarial:\n"
            "L = Σ(Estrellas_vigentes × Costo_real × Tasa_de_redención_histórica)"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#555;background:#f0f4ff;padding:7px 16px;border-radius:5px;font-size:11px;")
        lay.addWidget(info)

        self.lbl_pasivo = QLabel("Presiona 'Calcular' para ver el pasivo actual")
        self.lbl_pasivo.setStyleSheet("font-size:14px;padding:12px;")
        self.lbl_pasivo.setWordWrap(True)
        lay.addWidget(self.lbl_pasivo)

        btn_row = QHBoxLayout()
        btn_calc = QPushButton("🔢 Calcular pasivo actual"); btn_calc.setObjectName("primaryBtn")
        btn_calc.clicked.connect(self._calcular_pasivo)
        btn_exp = QPushButton("🌙 Ejecutar expiración nocturna ahora"); btn_exp.setObjectName("warningBtn")
        btn_exp.clicked.connect(self._ejecutar_expiracion)
        btn_row.addWidget(btn_calc); btn_row.addWidget(btn_exp); btn_row.addStretch()
        lay.addLayout(btn_row); lay.addStretch()
        return w

    def _calcular_pasivo(self):
        eng = self._engine_para()
        r = eng.pasivo_financiero()
        if "error" in r:
            self.lbl_pasivo.setText(f"Error: {r['error']}")
            return
        self.lbl_pasivo.setText(
            f"<b>Estrellas vigentes:</b> {r['saldo_total_estrellas']:,}<br>"
            f"<b>Tasa de redención histórica:</b> {r['tasa_redencion_historica']*100:.1f}%<br>"
            f"<b>Costo real por estrella:</b> ${r['costo_real_por_estrella']:.2f}<br><br>"
            f"<b style='font-size:18px;color:#e74c3c;'>Pasivo estimado: "
            f"${r['pasivo_estimado_mxn']:,.2f} MXN</b>"
        )

    def _ejecutar_expiracion(self):
        eng = self._engine_para()
        n = eng.ejecutar_expiracion_nocturna()
        QMessageBox.information(self,"Expiración",
            f"{n} clientes afectados. Sus estrellas inactivas fueron expiradas.")

    # ── Tab 5: Consulta cliente ──────────────────────────────────────────

    def _build_tab_clientes(self):
        w = QWidget(); lay = QVBoxLayout(w)
        ctrl = QHBoxLayout()
        self.txt_buscar_cli = QLineEdit(); self.txt_buscar_cli.setPlaceholderText("ID de cliente o nombre")
        btn_buscar = QPushButton("🔍 Consultar"); btn_buscar.setObjectName("primaryBtn"); btn_buscar.clicked.connect(self._consultar_cliente)
        ctrl.addWidget(self.txt_buscar_cli,1); ctrl.addWidget(btn_buscar)
        lay.addLayout(ctrl)

        self.lbl_cli_info = QLabel("")
        self.lbl_cli_info.setStyleSheet("font-size:13px;padding:8px;")
        self.lbl_cli_info.setWordWrap(True)
        lay.addWidget(self.lbl_cli_info)

        self.tbl_cli_misiones = QTableWidget(); self.tbl_cli_misiones.setColumnCount(4)
        self.tbl_cli_misiones.setHorizontalHeaderLabels(["Misión","Progreso","Total","Estado"])
        self.tbl_cli_misiones.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tbl_cli_misiones.setEditTriggers(QAbstractItemView.NoEditTriggers)
        lay.addWidget(QLabel("Misiones activas:"))
        lay.addWidget(self.tbl_cli_misiones)
        lay.addStretch()
        return w

    def _consultar_cliente(self):
        buscar = self.txt_buscar_cli.text().strip()
        if not buscar: return
        try:
            # Try as ID first, then name
            try:
                row = self.db.execute(
                    "SELECT id, nombre, COALESCE(apellido,'') as apellido FROM clientes WHERE id=?",
                    (int(buscar),)).fetchone()
            except Exception:
                row = self.db.execute(
                    "SELECT id, nombre, COALESCE(apellido,'') FROM clientes "
                    "WHERE nombre LIKE ? LIMIT 1", (f"%{buscar}%",)).fetchone()
            if not row:
                self.lbl_cli_info.setText(f"❌ Cliente '{buscar}' no encontrado"); return
            cid, nombre, apellido = row[0], row[1], row[2]
            eng = self._engine_para()
            saldo = eng.saldo_cliente(cid)
            misiones = eng.progreso_misiones_cliente(cid)

            self.lbl_cli_info.setText(
                f"<b>{nombre} {apellido}</b> (ID: {cid})<br>"
                f"⭐ <b>Saldo: {saldo:,} estrellas</b>"
            )
            self.tbl_cli_misiones.setRowCount(0)
            for i, m in enumerate(misiones):
                self.tbl_cli_misiones.insertRow(i)
                est = "✅" if m['completada'] else "🔄"
                self.tbl_cli_misiones.setItem(i,0,QTableWidgetItem(m['nombre']))
                self.tbl_cli_misiones.setItem(i,1,QTableWidgetItem(str(m['progreso'])))
                self.tbl_cli_misiones.setItem(i,2,QTableWidgetItem(str(m['condicion_n'])))
                self.tbl_cli_misiones.setItem(i,3,QTableWidgetItem(est))
        except Exception as e:
            self.lbl_cli_info.setText(f"Error: {e}")

    # ── Carga general ─────────────────────────────────────────────────────

    def _cargar_todo(self):
        self._cargar_metas()
        self._cargar_misiones()
