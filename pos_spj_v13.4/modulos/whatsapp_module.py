# modulos/whatsapp_module.py — SPJ POS v13.2
"""
Módulo WhatsApp UI — conectado a core/services/whatsapp_service.py,
services/bot_pedidos.py y la tabla whatsapp_numeros.
Soporta Rasa, cotizaciones, número por sucursal.
"""
from __future__ import annotations
from core.services.auto_audit import audit_write
from modulos.spj_styles import spj_btn, apply_btn_styles, apply_object_names
import logging
from modulos.spj_phone_widget import PhoneWidget
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QGroupBox, QFormLayout, QLineEdit, QCheckBox, QComboBox,
    QTabWidget, QTextEdit, QMessageBox, QSpinBox,
)
from PyQt5.QtCore import Qt, QTimer

logger = logging.getLogger("spj.modulo.whatsapp")


class ModuloWhatsApp(QWidget):

    def __init__(self, container, parent=None):
        super().__init__(parent)
        self.container   = container
        self.db          = container.db
        self.sucursal_id = 1
        self.usuario     = ""
        self._ensure_table()
        self._build_ui()
        self._cargar_config()
        self._cargar_historial()
        self._timer = QTimer(self)
        self._timer.setInterval(30_000)
        self._timer.timeout.connect(self._cargar_historial)
        self._timer.start()

    def set_usuario_actual(self, usuario: str, rol: str = "") -> None:
        self.usuario = usuario

    def set_sucursal(self, sucursal_id: int, nombre: str = "") -> None:
        self.sucursal_id = sucursal_id
        self._cargar_config()
        self._cargar_historial()

    def _ensure_table(self):
        """Crea whatsapp_numeros si no existe."""
        try:
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS whatsapp_numeros (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    sucursal_id  INTEGER,
                    canal        TEXT DEFAULT 'todos',
                    proveedor    TEXT DEFAULT 'meta',
                    numero_negocio TEXT,
                    meta_token   TEXT,
                    meta_phone_id TEXT,
                    twilio_sid   TEXT,
                    twilio_token TEXT,
                    verify_token TEXT DEFAULT 'spj_verify',
                    rasa_url     TEXT DEFAULT 'http://localhost:5005',
                    rasa_activo  INTEGER DEFAULT 0,
                    activo       INTEGER DEFAULT 1,
                    nombre_sucursal TEXT,
                    UNIQUE(sucursal_id, canal)
                )""")
            try: self.db.commit()
            except Exception: pass
        except Exception: pass

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)

        hdr = QHBoxLayout()
        titulo = QLabel("💬 Módulo WhatsApp")
        titulo.setStyleSheet("font-size:18px;font-weight:bold;")
        hdr.addWidget(titulo)
        self.lbl_status = QLabel("●")
        self.lbl_status.setStyleSheet("color:#aaa;font-size:18px;")
        hdr.addWidget(self.lbl_status); hdr.addStretch()
        btn_test = QPushButton("🔌 Probar conexión")
        btn_test.setObjectName("primaryBtn")
        btn_test.clicked.connect(self._test_conexion)
        hdr.addWidget(btn_test)
        lay.addLayout(hdr)

        tabs = QTabWidget()
        lay.addWidget(tabs)

        # ── Tab 1: Números por sucursal ──────────────────────────────────
        tab_numeros = QWidget(); tabs.addTab(tab_numeros, "📱 Números / Sucursales")
        ln = QVBoxLayout(tab_numeros)

        info = QLabel(
            "Configura un número de WhatsApp por sucursal. "
            "Si solo tienes uno global, déjalo en 'Sin sucursal asignada'."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#555;font-size:11px;background:#fffbea;padding:6px;border-radius:5px;")
        ln.addWidget(info)

        # Tabla de números registrados
        self.tbl_numeros = QTableWidget()
        self.tbl_numeros.setColumnCount(6)
        self.tbl_numeros.setHorizontalHeaderLabels([
            "ID", "Sucursal", "Canal", "Número", "Proveedor", "Activo"
        ])
        hh = self.tbl_numeros.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.tbl_numeros.setColumnHidden(0, True)
        self.tbl_numeros.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_numeros.setSelectionBehavior(QAbstractItemView.SelectRows)
        ln.addWidget(self.tbl_numeros)

        btn_row = QHBoxLayout()
        btn_add_n   = QPushButton("➕ Agregar número"); btn_add_n.setObjectName("successBtn"); btn_add_n.setStyleSheet("background:#27ae60;color:white;padding:5px 12px;")
        btn_edit_n  = QPushButton("✏️ Editar"); btn_edit_n.setObjectName("warningBtn"); btn_edit_n.setStyleSheet("background:#f39c12;color:white;padding:5px 12px;")
        btn_del_n   = QPushButton("🗑️ Eliminar"); btn_del_n.setObjectName("dangerBtn"); btn_del_n.setStyleSheet("background:#e74c3c;color:white;padding:5px 12px;")
        btn_row.addWidget(btn_add_n); btn_row.addWidget(btn_edit_n); btn_row.addWidget(btn_del_n); btn_row.addStretch()
        ln.addLayout(btn_row)
        btn_add_n.clicked.connect(self._dialogo_numero)
        btn_edit_n.clicked.connect(lambda: self._dialogo_numero(editar=True))
        btn_del_n.clicked.connect(self._eliminar_numero)
        self._cargar_tabla_numeros()

        # ── Tab 2: Bot / Rasa ────────────────────────────────────────────
        tab_bot = QWidget(); tabs.addTab(tab_bot, "🤖 Bot / Rasa")
        lb = QVBoxLayout(tab_bot)

        grp_bot = QGroupBox("Configuración del Bot")
        fb = QFormLayout(grp_bot)
        self.txt_nombre_bot = QLineEdit(); self.txt_nombre_bot.setPlaceholderText("Asistente SPJ")
        self.chk_bot_activo = QCheckBox("Bot activo (responde automáticamente)")
        self.chk_rasa_activo = QCheckBox("Usar Rasa para intención avanzada")
        self.txt_rasa_url = QLineEdit(); self.txt_rasa_url.setPlaceholderText("http://localhost:5005")
        self.spin_timeout = QSpinBox(); self.spin_timeout.setRange(1,120); self.spin_timeout.setValue(30); self.spin_timeout.setSuffix(" min")
        self.cmb_idioma = QComboBox(); self.cmb_idioma.addItems(["Español","English","Español + English"])
        fb.addRow("Nombre del bot:", self.txt_nombre_bot)
        fb.addRow("", self.chk_bot_activo)
        fb.addRow("", self.chk_rasa_activo)
        fb.addRow("URL de Rasa:", self.txt_rasa_url)
        fb.addRow("Timeout sesión:", self.spin_timeout)
        fb.addRow("Idioma:", self.cmb_idioma)
        lb.addWidget(grp_bot)

        grp_msgs = QGroupBox("Mensajes automáticos")
        fm = QFormLayout(grp_msgs)
        self.txt_msg_bienvenida = QTextEdit(); self.txt_msg_bienvenida.setMaximumHeight(60)
        self.txt_msg_bienvenida.setPlaceholderText("Hola {{nombre}}, bienvenido a nuestro servicio.")
        self.chk_cotizaciones = QCheckBox("Habilitar flujo de cotizaciones (el cliente pide precio sin comprar)")
        self.chk_clientes_rrhh = QCheckBox("Enviar notificaciones RRHH (nómina, vacaciones, turnos) por este número")
        fm.addRow("Bienvenida:", self.txt_msg_bienvenida)
        fm.addRow("", self.chk_cotizaciones)
        fm.addRow("", self.chk_clientes_rrhh)
        lb.addWidget(grp_msgs)

        btn_save_bot = QPushButton("💾 Guardar configuración del bot")
        btn_save_bot.setObjectName("successBtn")
        btn_save_bot.setStyleSheet("background:#27ae60;color:white;font-weight:bold;padding:7px 16px;")
        btn_save_bot.clicked.connect(self._guardar_config_bot)
        lb.addWidget(btn_save_bot); lb.addStretch()

        # ── Tab 3: Historial ─────────────────────────────────────────────
        tab_hist = QWidget(); tabs.addTab(tab_hist, "📋 Historial")
        lh = QVBoxLayout(tab_hist)
        ctrl = QHBoxLayout()
        self.txt_buscar_wa = QLineEdit(); self.txt_buscar_wa.setPlaceholderText("Buscar por número o texto…")
        btn_buscar = QPushButton("🔍"); btn_buscar.setObjectName("primaryBtn"); btn_buscar.clicked.connect(self._cargar_historial)
        btn_refresh = QPushButton("🔄"); btn_refresh.setObjectName("warningBtn"); btn_refresh.clicked.connect(self._cargar_historial)
        ctrl.addWidget(self.txt_buscar_wa, 1); ctrl.addWidget(btn_buscar); ctrl.addWidget(btn_refresh)
        lh.addLayout(ctrl)
        self.tbl_hist = QTableWidget()
        self.tbl_hist.setColumnCount(5)
        self.tbl_hist.setHorizontalHeaderLabels(["Fecha","Número","Dirección","Mensaje","Estado"])
        hh2 = self.tbl_hist.horizontalHeader()
        hh2.setSectionResizeMode(3, QHeaderView.Stretch)
        for i in (0,1,2,4): hh2.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.tbl_hist.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_hist.setAlternatingRowColors(True)
        self.tbl_hist.verticalHeader().setVisible(False)
        lh.addWidget(self.tbl_hist)

        # ── Tab 4: Métricas ──────────────────────────────────────────────
        tab_metrics = QWidget(); tabs.addTab(tab_metrics, "📊 Métricas")
        lmt = QVBoxLayout(tab_metrics)
        self.lbl_metrics = QLabel("Cargando métricas…")
        self.lbl_metrics.setAlignment(Qt.AlignTop)
        self.lbl_metrics.setStyleSheet("font-size:13px;line-height:1.6;")
        self.lbl_metrics.setWordWrap(True)
        lmt.addWidget(self.lbl_metrics)
        btn_refresh_m = QPushButton("🔄 Actualizar métricas")
        btn_refresh_m.setObjectName("warningBtn")
        btn_refresh_m.clicked.connect(self._cargar_metricas)
        lmt.addWidget(btn_refresh_m)
        lmt.addStretch()
        self._cargar_metricas()
        apply_object_names(self)

    # ── Números por sucursal ──────────────────────────────────────────────

    def _cargar_tabla_numeros(self):
        try:
            rows = self.db.execute(
                "SELECT id, COALESCE(nombre_sucursal,'Global'), canal, "
                "COALESCE(numero_negocio,''), proveedor, activo "
                "FROM whatsapp_numeros ORDER BY sucursal_id NULLS FIRST"
            ).fetchall()
        except Exception: rows = []
        self.tbl_numeros.setRowCount(0)
        for i, r in enumerate(rows):
            self.tbl_numeros.insertRow(i)
            for j, v in enumerate(r):
                it = QTableWidgetItem(str(v) if v is not None else "")
                if j == 5:  # activo
                    it = QTableWidgetItem("✅" if v else "❌")
                self.tbl_numeros.setItem(i, j, it)

    def _dialogo_numero(self, editar=False):
        from PyQt5.QtWidgets import (QDialog, QFormLayout, QDialogButtonBox,
                                      QVBoxLayout, QComboBox)
        row_id = None
        if editar:
            row = self.tbl_numeros.currentRow()
            if row < 0:
                QMessageBox.warning(self,"Aviso","Selecciona un número primero."); return
            row_id_item = self.tbl_numeros.item(row, 0)
            if row_id_item: row_id = int(row_id_item.text())

        dlg = QDialog(self); dlg.setWindowTitle("Configurar número WhatsApp"); dlg.setMinimumWidth(480)
        lay = QVBoxLayout(dlg); form = QFormLayout()

        cmb_suc = QComboBox()
        cmb_suc.addItem("Global (todas las sucursales)", None)
        try:
            sucks = self.db.execute("SELECT id, nombre FROM sucursales WHERE activa=1 ORDER BY nombre").fetchall()
            for s in sucks: cmb_suc.addItem(s[1] if hasattr(s,'keys') else s[1], s[0] if hasattr(s,'keys') else s[0])
        except Exception: pass

        cmb_canal = QComboBox()
        cmb_canal.addItems(["todos","clientes","rrhh","alertas"])
        cmb_prov = QComboBox()
        cmb_prov.addItems(["meta","twilio","wppconnect","baileys"])

        txt_numero    = PhoneWidget(default_country="+52")
        txt_phone_id  = QLineEdit(); txt_phone_id.setPlaceholderText("Meta Phone Number ID")
        txt_token     = QLineEdit(); txt_token.setPlaceholderText("Meta Access Token o Twilio Auth Token"); txt_token.setEchoMode(QLineEdit.Password)
        txt_sid       = QLineEdit(); txt_sid.setPlaceholderText("Twilio Account SID")
        txt_rasa      = QLineEdit(); txt_rasa.setPlaceholderText("http://localhost:5005")
        chk_rasa      = QCheckBox("Habilitar Rasa para esta sucursal")
        chk_activo    = QCheckBox("Activo"); chk_activo.setChecked(True)

        form.addRow("Sucursal:", cmb_suc)
        form.addRow("Canal:", cmb_canal)
        form.addRow("Proveedor:", cmb_prov)
        form.addRow("Número origen:", txt_numero)
        form.addRow("Phone ID (Meta):", txt_phone_id)
        form.addRow("Token/Secret:", txt_token)
        form.addRow("Account SID (Twilio):", txt_sid)
        form.addRow("URL Rasa:", txt_rasa)
        form.addRow("", chk_rasa)
        form.addRow("", chk_activo)
        lay.addLayout(form)

        if row_id:
            try:
                ex = self.db.execute(
                    "SELECT sucursal_id, canal, proveedor, numero_negocio, "
                    "meta_phone_id, meta_token, twilio_sid, rasa_url, rasa_activo, activo "
                    "FROM whatsapp_numeros WHERE id=?", (row_id,)
                ).fetchone()
                if ex:
                    # Pre-fill
                    for i in range(cmb_suc.count()):
                        if cmb_suc.itemData(i) == ex[0]:
                            cmb_suc.setCurrentIndex(i); break
                    idx_c = cmb_canal.findText(ex[1] or "todos")
                    if idx_c >= 0: cmb_canal.setCurrentIndex(idx_c)
                    idx_p = cmb_prov.findText(ex[2] or "meta")
                    if idx_p >= 0: cmb_prov.setCurrentIndex(idx_p)
                    txt_numero.set_phone(ex[3] or "")
                    txt_phone_id.setText(ex[4] or "")
                    txt_token.setText(ex[5] or "")
                    txt_sid.setText(ex[6] or "")
                    txt_rasa.setText(ex[7] or "http://localhost:5005")
                    chk_rasa.setChecked(bool(ex[8]))
                    chk_activo.setChecked(bool(ex[9]))
            except Exception: pass

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Save).setText("Aceptar")
        btns.button(QDialogButtonBox.Save).setObjectName("successBtn")
        btns.button(QDialogButtonBox.Cancel).setText("Cancelar")
        btns.button(QDialogButtonBox.Cancel).setObjectName("secondaryBtn")
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec_() != dlg.Accepted: return

        suc_id      = cmb_suc.currentData()
        suc_nombre  = cmb_suc.currentText() if suc_id else None
        canal       = cmb_canal.currentText()
        proveedor   = cmb_prov.currentText()
        numero      = txt_numero.get_e164().strip()
        phone_id    = txt_phone_id.text().strip()
        token       = txt_token.text().strip()
        sid         = txt_sid.text().strip()
        rasa_url    = txt_rasa.text().strip() or "http://localhost:5005"
        rasa_act    = 1 if chk_rasa.isChecked() else 0
        activo      = 1 if chk_activo.isChecked() else 0

        try:
            if row_id:
                self.db.execute("""
                    UPDATE whatsapp_numeros SET sucursal_id=?, canal=?, proveedor=?,
                    numero_negocio=?, meta_phone_id=?, meta_token=?, twilio_sid=?,
                    rasa_url=?, rasa_activo=?, activo=?, nombre_sucursal=?
                    WHERE id=?""",
                    (suc_id, canal, proveedor, numero, phone_id, token, sid,
                     rasa_url, rasa_act, activo, suc_nombre, row_id))
            else:
                self.db.execute("""
                    INSERT INTO whatsapp_numeros
                    (sucursal_id, canal, proveedor, numero_negocio, meta_phone_id,
                     meta_token, twilio_sid, rasa_url, rasa_activo, activo, nombre_sucursal)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (suc_id, canal, proveedor, numero, phone_id, token, sid,
                     rasa_url, rasa_act, activo, suc_nombre))
            try: self.db.commit()
            except Exception: pass
            self._cargar_tabla_numeros()
            QMessageBox.information(self,"✅","Número guardado correctamente.")
        except Exception as e:
            QMessageBox.critical(self,"Error",str(e))

    def _eliminar_numero(self):
        row = self.tbl_numeros.currentRow()
        if row < 0: return
        row_id_item = self.tbl_numeros.item(row, 0)
        if not row_id_item: return
        rid = int(row_id_item.text())
        if QMessageBox.question(self,"Confirmar","¿Eliminar este número?",
           QMessageBox.Yes|QMessageBox.No) != QMessageBox.Yes: return
        self.db.execute("DELETE FROM whatsapp_numeros WHERE id=?", (rid,))
        try: self.db.commit()
        except Exception: pass
        self._cargar_tabla_numeros()

    # ── Config bot ────────────────────────────────────────────────────────

    def _clave(self, k): return f"wa_{k}"

    def _get_cfg(self, k, default=""):
        try:
            r = self.db.execute(
                "SELECT valor FROM configuraciones WHERE clave=?", (self._clave(k),)
            ).fetchone()
            return r[0] if r else default
        except Exception: return default

    def _set_cfg(self, k, v):
        self.db.execute(
            "INSERT INTO configuraciones(clave,valor) VALUES(?,?) "
            "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
            (self._clave(k), v))

    def _cargar_config(self):
        try:
            self.txt_nombre_bot.setText(self._get_cfg("bot_nombre","Asistente SPJ"))
            self.chk_bot_activo.setChecked(self._get_cfg("bot_activo","0") == "1")
            self.chk_rasa_activo.setChecked(self._get_cfg("rasa_activo","0") == "1")
            self.txt_rasa_url.setText(self._get_cfg("rasa_url","http://localhost:5005"))
            self.spin_timeout.setValue(int(self._get_cfg("timeout","30")))
            self.txt_msg_bienvenida.setPlainText(
                self._get_cfg("msg_bienvenida","Hola, bienvenido a nuestro servicio."))
            self.chk_cotizaciones.setChecked(self._get_cfg("cotizaciones","1") == "1")
            self.chk_clientes_rrhh.setChecked(self._get_cfg("rrhh_notif","1") == "1")
        except Exception as e:
            logger.debug("cargar_config WA: %s", e)

    def _guardar_config_bot(self):
        try:
            self._set_cfg("bot_nombre",   self.txt_nombre_bot.text().strip())
            self._set_cfg("bot_activo",   "1" if self.chk_bot_activo.isChecked() else "0")
            self._set_cfg("rasa_activo",  "1" if self.chk_rasa_activo.isChecked() else "0")
            self._set_cfg("rasa_url",     self.txt_rasa_url.text().strip())
            self._set_cfg("timeout",      str(self.spin_timeout.value()))
            self._set_cfg("msg_bienvenida", self.txt_msg_bienvenida.toPlainText().strip())
            self._set_cfg("cotizaciones", "1" if self.chk_cotizaciones.isChecked() else "0")
            self._set_cfg("rrhh_notif",   "1" if self.chk_clientes_rrhh.isChecked() else "0")
            # Also update rasa_url in legacy key
            self.db.execute(
                "INSERT INTO configuraciones(clave,valor) VALUES('rasa_url',?) "
                "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor",
                (self.txt_rasa_url.text().strip(),))
            try: self.db.commit()
            except Exception: pass
            # Update whatsapp_service at runtime if available
            wa = getattr(self.container, 'whatsapp_service', None)
            if wa and hasattr(wa, '_rasa_url'):
                wa._rasa_url = self.txt_rasa_url.text().strip()
            QMessageBox.information(self,"✅ Guardado","Configuración del bot guardada.")
        except Exception as e:
            QMessageBox.critical(self,"Error",str(e))

    # ── Historial ─────────────────────────────────────────────────────────

    def _cargar_historial(self):
        buscar = self.txt_buscar_wa.text().strip() if hasattr(self,"txt_buscar_wa") else ""
        rows = []
        # Try wa_message_queue first (core WhatsApp service)
        for table_query in [
            """SELECT fecha_creacion, to_number,
                      CASE WHEN status='sent' THEN '⬆️ Salida' ELSE '⏳ Cola' END,
                      COALESCE(message,''), COALESCE(status,'pendiente')
               FROM wa_message_queue ORDER BY fecha_creacion DESC LIMIT 200""",
            """SELECT fecha, numero_whatsapp,
                      CASE WHEN direction='in' THEN '⬇️ Entrada' ELSE '⬆️ Salida' END,
                      COALESCE(mensaje,texto,''), COALESCE(estado,'enviado')
               FROM bot_mensajes_log ORDER BY fecha DESC LIMIT 200""",
            """SELECT fecha, COALESCE(numero_whatsapp,telefono_cliente,'?'),
                      '⬇️ Entrada', COALESCE(mensaje,''), 'recibido'
               FROM pedidos_whatsapp ORDER BY fecha DESC LIMIT 100""",
        ]:
            try:
                q = table_query
                if buscar:
                    # add WHERE clause before ORDER BY
                    q = q.replace("ORDER BY", f"WHERE (to_number LIKE '%{buscar}%' OR message LIKE '%{buscar}%' OR numero_whatsapp LIKE '%{buscar}%' OR mensaje LIKE '%{buscar}%') ORDER BY", 1)
                rows = self.db.execute(q).fetchall()
                if rows: break
            except Exception: continue

        self.tbl_hist.setRowCount(0)
        for i, r in enumerate(rows):
            self.tbl_hist.insertRow(i)
            for j, v in enumerate(r):
                self.tbl_hist.setItem(i, j, QTableWidgetItem(str(v) if v else ""))

    # ── Métricas ──────────────────────────────────────────────────────────

    def _cargar_metricas(self):
        try:
            tot, hoy, pend, total_v = 0, 0, 0, 0.0
            for q in [
                ("SELECT COUNT(*) FROM pedidos_whatsapp", "total"),
                ("SELECT COUNT(*) FROM pedidos_whatsapp WHERE DATE(fecha)=DATE('now')", "hoy"),
                ("SELECT COUNT(*) FROM pedidos_whatsapp WHERE estado='pendiente'", "pend"),
                ("SELECT COALESCE(SUM(total),0) FROM pedidos_whatsapp WHERE estado NOT IN ('cancelado','rechazado')", "val"),
            ]:
                try:
                    v = self.db.execute(q[0]).fetchone()[0]
                    if q[1] == "total": tot = v
                    elif q[1] == "hoy": hoy = v
                    elif q[1] == "pend": pend = v
                    else: total_v = float(v)
                except Exception: pass

            # Check if Rasa is configured
            rasa_url = self._get_cfg("rasa_url","")
            rasa_status = "🔵 Configurado" if rasa_url and rasa_url != "http://localhost:5005" else "⚫ No configurado"

            # Check bot_sessions count
            sesiones = 0
            try: sesiones = self.db.execute("SELECT COUNT(*) FROM bot_sessions").fetchone()[0]
            except Exception: pass

            text = (
                f"<b>Pedidos WhatsApp hoy:</b> {hoy}<br>"
                f"<b>Total histórico:</b> {tot}<br>"
                f"<b>Pendientes:</b> {pend}<br>"
                f"<b>Valor total generado:</b> ${total_v:,.2f}<br>"
                f"<b>Sesiones de bot activas:</b> {sesiones}<br><br>"
                f"<b>Bot:</b> {'🟢 Activo' if self._get_cfg('bot_activo','0')=='1' else '🔴 Inactivo'}<br>"
                f"<b>Rasa:</b> {rasa_status}<br>"
                f"<b>Cotizaciones:</b> {'✅' if self._get_cfg('cotizaciones','1')=='1' else '❌'}"
            )
            self.lbl_metrics.setText(text)
        except Exception as e:
            self.lbl_metrics.setText(f"Error cargando métricas: {e}")

    # ── Test ──────────────────────────────────────────────────────────────

    def _test_conexion(self):
        try:
            from core.services.whatsapp_service import WhatsAppService
            wa = getattr(self.container, 'whatsapp_service', None)
            if not wa:
                wa = WhatsAppService(self.container.db)
            ok = wa.test_connection() if hasattr(wa,'test_connection') else False
            if ok:
                self.lbl_status.setStyleSheet("color:#27ae60;font-size:18px;")
                QMessageBox.information(self,"✅ Conexión OK","WhatsApp conectado correctamente.")
            else:
                raise Exception("test_connection retornó False")
        except Exception as e:
            self.lbl_status.setStyleSheet("color:#e74c3c;font-size:18px;")
            QMessageBox.warning(self,"⚠️ Sin conexión",
                f"No se pudo verificar la conexión:\n{e}\n\n"
                "Verifica las credenciales en la pestaña Números / Sucursales.")


    # ── Webhook ───────────────────────────────────────────────────────────

    def _actualizar_webhook_status(self):
        wa = getattr(self.container, 'whatsapp_webhook', None)
        if wa and hasattr(wa, '_running') and wa._running:
            self.lbl_webhook_status.setText("🟢 Webhook activo — escuchando mensajes entrantes")
            self.lbl_webhook_status.setStyleSheet("color:#27ae60;font-size:14px;padding:8px;")
        else:
            self.lbl_webhook_status.setText("🔴 Webhook detenido — los mensajes entrantes no se procesarán")
            self.lbl_webhook_status.setStyleSheet("color:#e74c3c;font-size:14px;padding:8px;")

    def _iniciar_webhook(self):
        try:
            puerto = int(self.txt_webhook_puerto.text() or "8767")
            verify = self.txt_verify_token.text().strip() or "spj_verify"
            wa_hook = getattr(self.container, 'whatsapp_webhook', None)
            if wa_hook:
                wa_hook._port = puerto
                wa_hook.start()
                # Save verify token
                self.db.execute(
                    "INSERT INTO configuraciones(clave,valor) VALUES('wa_verify_token',?) "
                    "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor", (verify,))
                try: self.db.commit()
                except Exception: pass
                self._actualizar_webhook_status()
                QMessageBox.information(self, "✅", f"Webhook iniciado en puerto {puerto}")
            else:
                QMessageBox.warning(self, "Aviso", "WhatsAppWebhookServer no está disponible en el contenedor.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _detener_webhook(self):
        try:
            wa_hook = getattr(self.container, 'whatsapp_webhook', None)
            if wa_hook and hasattr(wa_hook, 'stop'):
                wa_hook.stop()
                self._actualizar_webhook_status()
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def _test_webhook_meta(self):
        """Verifica que Meta pueda alcanzar el webhook haciendo una llamada de prueba."""
        try:
            import urllib.request
            puerto = self.txt_webhook_puerto.text() or "8767"
            url = f"http://127.0.0.1:{puerto}/webhook?hub.mode=subscribe&hub.verify_token=spj_verify&hub.challenge=test123"
            resp = urllib.request.urlopen(url, timeout=3)
            body = resp.read().decode()
            if "test123" in body:
                QMessageBox.information(self, "✅ OK", f"Webhook responde correctamente.\nRespuesta: {body}")
            else:
                QMessageBox.warning(self, "⚠️", f"Respuesta inesperada: {body}")
        except Exception as e:
            QMessageBox.warning(self, "❌ Sin respuesta",
                f"No se pudo conectar al webhook:\n{e}\n\n"
                "Asegúrate de haberlo iniciado primero.")

    def closeEvent(self, event):
        try: self._timer.stop()
        except Exception: pass
        super().closeEvent(event)
