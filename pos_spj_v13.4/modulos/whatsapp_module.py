# modulos/whatsapp_module.py — SPJ POS v13.4
"""
Módulo WhatsApp UI — solo presentación.
Toda la lógica de datos está en WhatsAppAdminService.
"""
from __future__ import annotations
import logging

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QGroupBox, QFormLayout, QLineEdit, QCheckBox, QComboBox,
    QTabWidget, QTextEdit, QMessageBox, QSpinBox,
    QDialog, QDialogButtonBox,
)
from PyQt5.QtCore import Qt, QTimer

from modulos.spj_styles import spj_btn, apply_spj_buttons, apply_object_names
from modulos.spj_phone_widget import PhoneWidget
from core.services.whatsapp_admin_service import WhatsAppAdminService
from core.services.whatsapp_credential_service import WhatsAppCredentialService

logger = logging.getLogger("spj.modulo.whatsapp")


class ModuloWhatsApp(QWidget):

    def __init__(self, container, parent=None):
        super().__init__(parent)
        self.container   = container
        self.sucursal_id = 1
        self.usuario     = ""
        self._svc  = WhatsAppAdminService(container.db)
        self._cred = WhatsAppCredentialService(container.db)
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

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)

        # Header
        hdr = QHBoxLayout()
        titulo = QLabel("💬 Módulo WhatsApp")
        titulo.setStyleSheet("font-size:18px;font-weight:bold;")
        hdr.addWidget(titulo)
        self.lbl_status = QLabel("●")
        self.lbl_status.setStyleSheet("color:#aaa;font-size:18px;")
        hdr.addWidget(self.lbl_status)
        hdr.addStretch()
        btn_test = QPushButton("🔌 Probar conexión")
        spj_btn(btn_test, "primary")
        btn_test.clicked.connect(self._test_conexion)
        hdr.addWidget(btn_test)
        lay.addLayout(hdr)

        tabs = QTabWidget()
        lay.addWidget(tabs)

        tabs.addTab(self._build_tab_numeros(),  "📱 Números / Sucursales")
        tabs.addTab(self._build_tab_bot(),       "🤖 Bot / Rasa")
        tabs.addTab(self._build_tab_historial(), "📋 Historial")
        tabs.addTab(self._build_tab_metricas(),  "📊 Métricas")
        tabs.addTab(self._build_tab_webhook(),   "🔗 Webhook")

        apply_object_names(self)

    # ── Tab: Números ──────────────────────────────────────────────────────────

    def _build_tab_numeros(self) -> QWidget:
        w = QWidget()
        ln = QVBoxLayout(w)

        info = QLabel(
            "Configura un número de WhatsApp por sucursal. "
            "Si solo tienes uno global, déjalo en 'Sin sucursal asignada'."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#555;font-size:11px;background:#fffbea;"
                           "padding:6px;border-radius:5px;")
        ln.addWidget(info)

        self.tbl_numeros = QTableWidget()
        self.tbl_numeros.setColumnCount(6)
        self.tbl_numeros.setHorizontalHeaderLabels(
            ["ID", "Sucursal", "Canal", "Número", "Proveedor", "Activo"])
        hh = self.tbl_numeros.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.tbl_numeros.setColumnHidden(0, True)
        self.tbl_numeros.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_numeros.setSelectionBehavior(QAbstractItemView.SelectRows)
        ln.addWidget(self.tbl_numeros)

        btn_row = QHBoxLayout()
        btn_add  = QPushButton("➕ Agregar número")
        btn_edit = QPushButton("✏️ Editar")
        btn_del  = QPushButton("🗑️ Eliminar")
        spj_btn(btn_add, "success")
        spj_btn(btn_edit, "warning")
        spj_btn(btn_del, "danger")
        btn_add.clicked.connect(self._dialogo_numero)
        btn_edit.clicked.connect(lambda: self._dialogo_numero(editar=True))
        btn_del.clicked.connect(self._eliminar_numero)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_edit)
        btn_row.addWidget(btn_del)
        btn_row.addStretch()
        ln.addLayout(btn_row)
        self._cargar_tabla_numeros()
        return w

    # ── Tab: Bot ──────────────────────────────────────────────────────────────

    def _build_tab_bot(self) -> QWidget:
        w = QWidget()
        lb = QVBoxLayout(w)

        grp_bot = QGroupBox("Configuración del Bot")
        fb = QFormLayout(grp_bot)
        self.txt_nombre_bot   = QLineEdit(); self.txt_nombre_bot.setPlaceholderText("Asistente SPJ")
        self.chk_bot_activo   = QCheckBox("Bot activo (responde automáticamente)")
        self.chk_rasa_activo  = QCheckBox("Usar Rasa para intención avanzada")
        self.txt_rasa_url     = QLineEdit(); self.txt_rasa_url.setPlaceholderText("http://localhost:5005")
        self.spin_timeout     = QSpinBox(); self.spin_timeout.setRange(1,120); self.spin_timeout.setValue(30); self.spin_timeout.setSuffix(" min")
        self.cmb_idioma       = QComboBox(); self.cmb_idioma.addItems(["Español","English","Español + English"])
        fb.addRow("Nombre del bot:",  self.txt_nombre_bot)
        fb.addRow("",                 self.chk_bot_activo)
        fb.addRow("",                 self.chk_rasa_activo)
        fb.addRow("URL de Rasa:",     self.txt_rasa_url)
        fb.addRow("Timeout sesión:",  self.spin_timeout)
        fb.addRow("Idioma:",          self.cmb_idioma)
        lb.addWidget(grp_bot)

        grp_msgs = QGroupBox("Mensajes automáticos")
        fm = QFormLayout(grp_msgs)
        self.txt_msg_bienvenida = QTextEdit(); self.txt_msg_bienvenida.setMaximumHeight(60)
        self.txt_msg_bienvenida.setPlaceholderText("Hola {{nombre}}, bienvenido a nuestro servicio.")
        self.chk_cotizaciones  = QCheckBox("Habilitar flujo de cotizaciones")
        self.chk_clientes_rrhh = QCheckBox("Enviar notificaciones RRHH por este número")
        fm.addRow("Bienvenida:", self.txt_msg_bienvenida)
        fm.addRow("",            self.chk_cotizaciones)
        fm.addRow("",            self.chk_clientes_rrhh)
        lb.addWidget(grp_msgs)

        btn_save = QPushButton("💾 Guardar configuración del bot")
        spj_btn(btn_save, "success")
        btn_save.clicked.connect(self._guardar_config_bot)
        lb.addWidget(btn_save)
        lb.addStretch()
        return w

    # ── Tab: Historial ────────────────────────────────────────────────────────

    def _build_tab_historial(self) -> QWidget:
        w = QWidget()
        lh = QVBoxLayout(w)
        ctrl = QHBoxLayout()
        self.txt_buscar_wa = QLineEdit()
        self.txt_buscar_wa.setPlaceholderText("Buscar por número o texto…")
        btn_buscar  = QPushButton("🔍")
        btn_refresh = QPushButton("🔄")
        spj_btn(btn_buscar, "primary", "sm")
        spj_btn(btn_refresh, "secondary", "sm")
        btn_buscar.clicked.connect(self._cargar_historial)
        btn_refresh.clicked.connect(self._cargar_historial)
        ctrl.addWidget(self.txt_buscar_wa, 1)
        ctrl.addWidget(btn_buscar)
        ctrl.addWidget(btn_refresh)
        lh.addLayout(ctrl)

        self.tbl_hist = QTableWidget()
        self.tbl_hist.setColumnCount(5)
        self.tbl_hist.setHorizontalHeaderLabels(
            ["Fecha", "Número", "Dirección", "Mensaje", "Estado"])
        hh = self.tbl_hist.horizontalHeader()
        hh.setSectionResizeMode(3, QHeaderView.Stretch)
        for i in (0, 1, 2, 4):
            hh.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.tbl_hist.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_hist.setAlternatingRowColors(True)
        self.tbl_hist.verticalHeader().setVisible(False)
        lh.addWidget(self.tbl_hist)
        return w

    # ── Tab: Métricas ─────────────────────────────────────────────────────────

    def _build_tab_metricas(self) -> QWidget:
        w = QWidget()
        lmt = QVBoxLayout(w)
        self.lbl_metrics = QLabel("Cargando métricas…")
        self.lbl_metrics.setAlignment(Qt.AlignTop)
        self.lbl_metrics.setStyleSheet("font-size:13px;line-height:1.6;")
        self.lbl_metrics.setWordWrap(True)
        lmt.addWidget(self.lbl_metrics)
        btn_refresh = QPushButton("🔄 Actualizar métricas")
        spj_btn(btn_refresh, "secondary")
        btn_refresh.clicked.connect(self._cargar_metricas)
        lmt.addWidget(btn_refresh)
        lmt.addStretch()
        self._cargar_metricas()
        return w

    # ── Tab: Webhook ──────────────────────────────────────────────────────────

    def _build_tab_webhook(self) -> QWidget:
        w = QWidget()
        lw = QVBoxLayout(w)

        grp = QGroupBox("Servidor webhook local (Meta → ERP)")
        fg = QFormLayout(grp)
        self.txt_webhook_puerto = QLineEdit("8767")
        self.txt_verify_token   = QLineEdit()
        self.txt_verify_token.setPlaceholderText("spj_verify")
        fg.addRow("Puerto:", self.txt_webhook_puerto)
        fg.addRow("Verify token:", self.txt_verify_token)
        lw.addWidget(grp)

        self.lbl_webhook_status = QLabel("🔴 Webhook detenido")
        self.lbl_webhook_status.setStyleSheet(
            "color:#e74c3c;font-size:14px;padding:8px;")
        lw.addWidget(self.lbl_webhook_status)

        btn_row = QHBoxLayout()
        btn_start = QPushButton("▶️ Iniciar webhook")
        btn_stop  = QPushButton("⏹️ Detener webhook")
        btn_test  = QPushButton("🧪 Test Meta")
        spj_btn(btn_start, "success")
        spj_btn(btn_stop, "danger")
        spj_btn(btn_test, "secondary")
        btn_start.clicked.connect(self._iniciar_webhook)
        btn_stop.clicked.connect(self._detener_webhook)
        btn_test.clicked.connect(self._test_webhook_meta)
        btn_row.addWidget(btn_start)
        btn_row.addWidget(btn_stop)
        btn_row.addWidget(btn_test)
        btn_row.addStretch()
        lw.addLayout(btn_row)
        lw.addStretch()
        self._actualizar_webhook_status()
        return w

    # ── Datos: Números ────────────────────────────────────────────────────────

    def _cargar_tabla_numeros(self):
        rows = self._svc.list_numeros()
        self.tbl_numeros.setRowCount(0)
        for i, r in enumerate(rows):
            self.tbl_numeros.insertRow(i)
            vals = [r.get("id",""), r.get("nombre_sucursal","Global"),
                    r.get("canal",""), r.get("numero_negocio",""),
                    r.get("proveedor",""), r.get("activo", 0)]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(
                    ("✅" if v else "❌") if j == 5
                    else str(v) if v is not None else "")
                self.tbl_numeros.setItem(i, j, item)

    def _dialogo_numero(self, editar: bool = False):
        row_id = None
        existing = None
        if editar:
            row = self.tbl_numeros.currentRow()
            if row < 0:
                QMessageBox.warning(self, "Aviso", "Selecciona un número primero.")
                return
            item = self.tbl_numeros.item(row, 0)
            if item:
                row_id = int(item.text())
                existing = self._svc.get_numero(row_id)

        dlg = QDialog(self)
        dlg.setWindowTitle("Configurar número WhatsApp")
        dlg.setMinimumWidth(480)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()

        cmb_suc = QComboBox()
        cmb_suc.addItem("Global (todas las sucursales)", None)
        for s in self._svc.list_sucursales():
            cmb_suc.addItem(s["nombre"], s["id"])

        cmb_canal = QComboBox()
        cmb_canal.addItems(["todos", "clientes", "rrhh", "alertas"])
        cmb_prov = QComboBox()
        cmb_prov.addItems(["meta", "twilio", "wppconnect", "baileys"])

        txt_numero   = PhoneWidget(default_country="+52")
        txt_phone_id = QLineEdit(); txt_phone_id.setPlaceholderText("Meta Phone Number ID")
        txt_token    = QLineEdit()
        txt_token.setPlaceholderText("Meta Access Token (se almacena cifrado)")
        txt_token.setEchoMode(QLineEdit.Password)
        txt_sid      = QLineEdit(); txt_sid.setPlaceholderText("Twilio Account SID")
        txt_rasa     = QLineEdit(); txt_rasa.setPlaceholderText("http://localhost:5005")
        chk_rasa     = QCheckBox("Habilitar Rasa para esta sucursal")
        chk_activo   = QCheckBox("Activo"); chk_activo.setChecked(True)

        form.addRow("Sucursal:",           cmb_suc)
        form.addRow("Canal:",              cmb_canal)
        form.addRow("Proveedor:",          cmb_prov)
        form.addRow("Número origen:",      txt_numero)
        form.addRow("Phone ID (Meta):",    txt_phone_id)
        form.addRow("Token/Secret:",       txt_token)
        form.addRow("Account SID (Twilio):", txt_sid)
        form.addRow("URL Rasa:",           txt_rasa)
        form.addRow("",                    chk_rasa)
        form.addRow("",                    chk_activo)
        lay.addLayout(form)

        if existing:
            for i in range(cmb_suc.count()):
                if cmb_suc.itemData(i) == existing.get("sucursal_id"):
                    cmb_suc.setCurrentIndex(i); break
            idx_c = cmb_canal.findText(existing.get("canal") or "todos")
            if idx_c >= 0: cmb_canal.setCurrentIndex(idx_c)
            idx_p = cmb_prov.findText(existing.get("proveedor") or "meta")
            if idx_p >= 0: cmb_prov.setCurrentIndex(idx_p)
            txt_numero.set_phone(existing.get("numero_negocio") or "")
            txt_phone_id.setText(existing.get("meta_phone_id") or "")
            # Token: mostrar enmascarado — no pre-llenar campo de contraseña
            txt_sid.setText(existing.get("twilio_sid") or "")
            txt_rasa.setText(existing.get("rasa_url") or "http://localhost:5005")
            chk_rasa.setChecked(bool(existing.get("rasa_activo")))
            chk_activo.setChecked(bool(existing.get("activo", 1)))

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec_() != QDialog.Accepted:
            return

        suc_id     = cmb_suc.currentData()
        token_raw  = txt_token.text().strip()

        # Al editar: si no se ingresó nuevo token, preservar el existente
        if existing and not token_raw:
            token_raw = existing.get("meta_token") or ""

        ok = self._cred.save_credentials(
            sucursal_id=suc_id,
            canal=cmb_canal.currentText(),
            proveedor=cmb_prov.currentText(),
            numero=txt_numero.get_e164().strip(),
            meta_token=token_raw,
            meta_phone_id=txt_phone_id.text().strip(),
            twilio_sid=txt_sid.text().strip(),
            rasa_url=txt_rasa.text().strip() or "http://localhost:5005",
            rasa_activo=chk_rasa.isChecked(),
            activo=chk_activo.isChecked(),
            nombre_sucursal=cmb_suc.currentText() if suc_id else None,
            row_id=row_id,
        )
        if ok:
            self._cargar_tabla_numeros()
            QMessageBox.information(self, "✅", "Número guardado correctamente.")
        else:
            QMessageBox.critical(self, "Error", "No se pudo guardar el número.")

    def _eliminar_numero(self):
        row = self.tbl_numeros.currentRow()
        if row < 0: return
        item = self.tbl_numeros.item(row, 0)
        if not item: return
        rid = int(item.text())
        if QMessageBox.question(
                self, "Confirmar", "¿Eliminar este número?",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        if self._svc.delete_numero(rid):
            self._cargar_tabla_numeros()

    # ── Datos: Config bot ─────────────────────────────────────────────────────

    def _cargar_config(self):
        try:
            svc = self._svc
            self.txt_nombre_bot.setText(svc.get_config("bot_nombre","Asistente SPJ"))
            self.chk_bot_activo.setChecked(svc.get_config("bot_activo","0") == "1")
            self.chk_rasa_activo.setChecked(svc.get_config("rasa_activo","0") == "1")
            self.txt_rasa_url.setText(svc.get_config("rasa_url","http://localhost:5005"))
            self.spin_timeout.setValue(int(svc.get_config("timeout","30") or "30"))
            self.txt_msg_bienvenida.setPlainText(
                svc.get_config("msg_bienvenida","Hola, bienvenido a nuestro servicio."))
            self.chk_cotizaciones.setChecked(svc.get_config("cotizaciones","1") == "1")
            self.chk_clientes_rrhh.setChecked(svc.get_config("rrhh_notif","1") == "1")
            self.txt_verify_token.setText(svc.get_config("verify_token","spj_verify"))
        except Exception as e:
            logger.debug("_cargar_config WA: %s", e)

    def _guardar_config_bot(self):
        try:
            self._svc.save_bot_config({
                "bot_nombre":     self.txt_nombre_bot.text().strip(),
                "bot_activo":     "1" if self.chk_bot_activo.isChecked() else "0",
                "rasa_activo":    "1" if self.chk_rasa_activo.isChecked() else "0",
                "rasa_url":       self.txt_rasa_url.text().strip(),
                "timeout":        str(self.spin_timeout.value()),
                "msg_bienvenida": self.txt_msg_bienvenida.toPlainText().strip(),
                "cotizaciones":   "1" if self.chk_cotizaciones.isChecked() else "0",
                "rrhh_notif":     "1" if self.chk_clientes_rrhh.isChecked() else "0",
            })
            # Actualizar rasa_url en servicio runtime si disponible
            wa = getattr(self.container, "whatsapp_service", None)
            if wa and hasattr(wa, "_rasa_url"):
                wa._rasa_url = self.txt_rasa_url.text().strip()
            QMessageBox.information(self, "✅ Guardado", "Configuración del bot guardada.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ── Datos: Historial ──────────────────────────────────────────────────────

    def _cargar_historial(self):
        search = self.txt_buscar_wa.text().strip() if hasattr(self, "txt_buscar_wa") else ""
        rows = self._svc.get_history(search=search)
        self.tbl_hist.setRowCount(0)
        for i, r in enumerate(rows):
            self.tbl_hist.insertRow(i)
            for j, key in enumerate(["fecha","numero","direccion","mensaje","estado"]):
                self.tbl_hist.setItem(i, j, QTableWidgetItem(str(r.get(key) or "")))

    # ── Datos: Métricas ───────────────────────────────────────────────────────

    def _cargar_metricas(self):
        try:
            m = self._svc.get_metrics()
            rasa_url = m.get("rasa_url","")
            rasa_status = ("🔵 Configurado"
                           if rasa_url and rasa_url != "http://localhost:5005"
                           else "⚫ No configurado")
            text = (
                f"<b>Pedidos WhatsApp hoy:</b> {m['pedidos_hoy']}<br>"
                f"<b>Total histórico:</b> {m['total_pedidos']}<br>"
                f"<b>Pendientes:</b> {m['pendientes']}<br>"
                f"<b>Valor total generado:</b> ${m['valor_total']:,.2f}<br>"
                f"<b>Sesiones de bot activas:</b> {m['sesiones_activas']}<br><br>"
                f"<b>Bot:</b> {'🟢 Activo' if m['bot_activo'] else '🔴 Inactivo'}<br>"
                f"<b>Rasa:</b> {rasa_status}<br>"
                f"<b>Cotizaciones:</b> {'✅' if m['cotizaciones'] else '❌'}"
            )
            self.lbl_metrics.setText(text)
        except Exception as e:
            self.lbl_metrics.setText(f"Error cargando métricas: {e}")

    # ── Test conexión ─────────────────────────────────────────────────────────

    def _test_conexion(self):
        ok = self._svc.test_connection()
        if ok:
            self.lbl_status.setStyleSheet("color:#27ae60;font-size:18px;")
            QMessageBox.information(self, "✅ Conexión OK",
                                    "WhatsApp conectado correctamente.")
        else:
            self.lbl_status.setStyleSheet("color:#e74c3c;font-size:18px;")
            QMessageBox.warning(self, "⚠️ Sin conexión",
                "No se pudo verificar la conexión.\n\n"
                "Verifica las credenciales en la pestaña Números / Sucursales.")

    # ── Webhook ───────────────────────────────────────────────────────────────

    def _actualizar_webhook_status(self):
        wa = getattr(self.container, "whatsapp_webhook", None)
        running = wa and getattr(wa, "_running", False)
        if running:
            self.lbl_webhook_status.setText("🟢 Webhook activo — escuchando mensajes entrantes")
            self.lbl_webhook_status.setStyleSheet("color:#27ae60;font-size:14px;padding:8px;")
        else:
            self.lbl_webhook_status.setText("🔴 Webhook detenido — mensajes entrantes no se procesarán")
            self.lbl_webhook_status.setStyleSheet("color:#e74c3c;font-size:14px;padding:8px;")

    def _iniciar_webhook(self):
        try:
            puerto = int(self.txt_webhook_puerto.text() or "8767")
            verify = self.txt_verify_token.text().strip() or "spj_verify"
            val = self._cred.validate_webhook_token(verify)
            if not val["valid"]:
                QMessageBox.warning(self, "Token inválido", val["error"]); return
            wa_hook = getattr(self.container, "whatsapp_webhook", None)
            if wa_hook:
                wa_hook._port = puerto
                wa_hook.start()
                self._svc.save_bot_config({"verify_token": verify})
                self._actualizar_webhook_status()
                QMessageBox.information(self, "✅", f"Webhook iniciado en puerto {puerto}")
            else:
                QMessageBox.warning(self, "Aviso",
                    "WhatsAppWebhookServer no está disponible en el contenedor.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _detener_webhook(self):
        try:
            wa_hook = getattr(self.container, "whatsapp_webhook", None)
            if wa_hook and hasattr(wa_hook, "stop"):
                wa_hook.stop()
                self._actualizar_webhook_status()
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))

    def _test_webhook_meta(self):
        try:
            import urllib.request
            puerto = self.txt_webhook_puerto.text() or "8767"
            verify = self.txt_verify_token.text().strip() or "spj_verify"
            url = (f"http://127.0.0.1:{puerto}/webhook"
                   f"?hub.mode=subscribe"
                   f"&hub.verify_token={verify}"
                   f"&hub.challenge=test123")
            resp = urllib.request.urlopen(url, timeout=3)
            body = resp.read().decode()
            if "test123" in body:
                QMessageBox.information(self, "✅ OK",
                    f"Webhook responde correctamente.\nRespuesta: {body}")
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
