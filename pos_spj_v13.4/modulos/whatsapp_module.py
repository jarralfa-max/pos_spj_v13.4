# modulos/whatsapp_module.py — SPJ POS v13.4
"""
Módulo WhatsApp — UI pura (PyQt5).
Toda lógica de negocio y acceso a datos delegada a WhatsAppAdminService.
"""
from __future__ import annotations
import logging
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QGroupBox, QFormLayout, QLineEdit, QCheckBox, QComboBox,
    QTabWidget, QTextEdit, QMessageBox, QSpinBox, QDialog,
    QDialogButtonBox,
)
from PyQt5.QtCore import Qt, QTimer

from modulos.spj_styles import spj_btn, apply_spj_buttons, apply_object_names
from modulos.design_tokens import Colors
from modulos.spj_phone_widget import PhoneWidget
from core.services.whatsapp_admin_service import WhatsAppAdminService

logger = logging.getLogger("spj.modulo.whatsapp")


class ModuloWhatsApp(QWidget):

    def __init__(self, container, parent=None):
        super().__init__(parent)
        self.container   = container
        self.sucursal_id = 1
        self.usuario     = ""
        self._svc = WhatsAppAdminService(container.db)
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

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)

        hdr = QHBoxLayout()
        titulo = QLabel("💬 Módulo WhatsApp")
        titulo.setStyleSheet(
            f"font-size:18px;font-weight:bold;color:{Colors.NEUTRAL.SLATE_800};")
        hdr.addWidget(titulo)
        self.lbl_status = QLabel("●")
        self.lbl_status.setStyleSheet(
            f"color:{Colors.NEUTRAL.SLATE_400};font-size:18px;")
        hdr.addWidget(self.lbl_status)
        hdr.addStretch()
        btn_test = QPushButton("🔌 Probar conexión")
        spj_btn(btn_test, "primary")
        btn_test.clicked.connect(self._test_conexion)
        hdr.addWidget(btn_test)
        lay.addLayout(hdr)

        tabs = QTabWidget()
        lay.addWidget(tabs)

        tabs.addTab(self._build_tab_numeros(), "📱 Números / Sucursales")
        tabs.addTab(self._build_tab_bot(), "🤖 Bot / Rasa")
        tabs.addTab(self._build_tab_webhook(), "🔗 Webhook")
        tabs.addTab(self._build_tab_historial(), "📋 Historial")
        tabs.addTab(self._build_tab_metricas(), "📊 Métricas")
        apply_object_names(self)
        apply_spj_buttons(self)

    # ── Tab: Números ──────────────────────────────────────────────────────────

    def _build_tab_numeros(self) -> QWidget:
        w = QWidget()
        ln = QVBoxLayout(w)
        info = QLabel(
            "Configura un número de WhatsApp por sucursal. "
            "Si solo tienes uno global, déjalo en 'Sin sucursal asignada'."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            f"color:{Colors.NEUTRAL.SLATE_600};font-size:11px;"
            "background:#fffbea;padding:6px;border-radius:5px;")
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
        btn_add_n  = QPushButton("➕ Agregar número")
        btn_edit_n = QPushButton("✏️ Editar")
        btn_del_n  = QPushButton("🗑️ Eliminar")
        spj_btn(btn_add_n, "success")
        spj_btn(btn_edit_n, "warning")
        spj_btn(btn_del_n, "danger")
        btn_row.addWidget(btn_add_n)
        btn_row.addWidget(btn_edit_n)
        btn_row.addWidget(btn_del_n)
        btn_row.addStretch()
        ln.addLayout(btn_row)
        btn_add_n.clicked.connect(self._dialogo_numero)
        btn_edit_n.clicked.connect(lambda: self._dialogo_numero(editar=True))
        btn_del_n.clicked.connect(self._eliminar_numero)
        self._cargar_tabla_numeros()
        return w

    # ── Tab: Bot ──────────────────────────────────────────────────────────────

    def _build_tab_bot(self) -> QWidget:
        w = QWidget()
        lb = QVBoxLayout(w)

        grp_bot = QGroupBox("Configuración del Bot")
        fb = QFormLayout(grp_bot)
        self.txt_nombre_bot  = QLineEdit()
        self.txt_nombre_bot.setPlaceholderText("Asistente SPJ")
        self.chk_bot_activo  = QCheckBox("Bot activo (responde automáticamente)")
        self.chk_rasa_activo = QCheckBox("Usar Rasa para intención avanzada")
        self.txt_rasa_url    = QLineEdit()
        self.txt_rasa_url.setPlaceholderText("http://localhost:5005")
        self.spin_timeout    = QSpinBox()
        self.spin_timeout.setRange(1, 120)
        self.spin_timeout.setValue(30)
        self.spin_timeout.setSuffix(" min")
        self.cmb_idioma = QComboBox()
        self.cmb_idioma.addItems(["Español", "English", "Español + English"])
        fb.addRow("Nombre del bot:", self.txt_nombre_bot)
        fb.addRow("", self.chk_bot_activo)
        fb.addRow("", self.chk_rasa_activo)
        fb.addRow("URL de Rasa:", self.txt_rasa_url)
        fb.addRow("Timeout sesión:", self.spin_timeout)
        fb.addRow("Idioma:", self.cmb_idioma)
        lb.addWidget(grp_bot)

        grp_msgs = QGroupBox("Mensajes automáticos")
        fm = QFormLayout(grp_msgs)
        self.txt_msg_bienvenida = QTextEdit()
        self.txt_msg_bienvenida.setMaximumHeight(60)
        self.txt_msg_bienvenida.setPlaceholderText(
            "Hola {{nombre}}, bienvenido a nuestro servicio.")
        self.chk_cotizaciones  = QCheckBox("Habilitar flujo de cotizaciones")
        self.chk_clientes_rrhh = QCheckBox(
            "Enviar notificaciones RRHH por este número")
        fm.addRow("Bienvenida:", self.txt_msg_bienvenida)
        fm.addRow("", self.chk_cotizaciones)
        fm.addRow("", self.chk_clientes_rrhh)
        lb.addWidget(grp_msgs)

        btn_save_bot = QPushButton("💾 Guardar configuración del bot")
        spj_btn(btn_save_bot, "success")
        btn_save_bot.clicked.connect(self._guardar_config_bot)
        lb.addWidget(btn_save_bot)
        lb.addStretch()
        return w

    # ── Tab: Webhook ──────────────────────────────────────────────────────────

    def _build_tab_webhook(self) -> QWidget:
        w = QWidget()
        lw = QVBoxLayout(w)

        grp_wh = QGroupBox("Webhook local (opcional — para desarrollo)")
        fw = QFormLayout(grp_wh)
        self.txt_webhook_puerto = QLineEdit()
        self.txt_webhook_puerto.setPlaceholderText("8767")
        self.txt_verify_token   = QLineEdit()
        self.txt_verify_token.setPlaceholderText("spj_verify")
        fw.addRow("Puerto webhook:", self.txt_webhook_puerto)
        fw.addRow("Verify token:", self.txt_verify_token)
        lw.addWidget(grp_wh)

        self.lbl_webhook_status = QLabel("⚫ Estado del webhook local desconocido")
        self.lbl_webhook_status.setStyleSheet(
            f"color:{Colors.NEUTRAL.SLATE_500};font-size:13px;padding:6px;")
        lw.addWidget(self.lbl_webhook_status)

        btn_row = QHBoxLayout()
        btn_start  = QPushButton("▶️ Iniciar webhook")
        btn_stop   = QPushButton("⏹️ Detener webhook")
        btn_test_m = QPushButton("🔌 Test Meta")
        spj_btn(btn_start, "success")
        spj_btn(btn_stop, "danger")
        spj_btn(btn_test_m, "info")
        btn_row.addWidget(btn_start)
        btn_row.addWidget(btn_stop)
        btn_row.addWidget(btn_test_m)
        btn_row.addStretch()
        lw.addLayout(btn_row)
        btn_start.clicked.connect(self._iniciar_webhook)
        btn_stop.clicked.connect(self._detener_webhook)
        btn_test_m.clicked.connect(self._test_webhook_meta)

        note = QLabel(
            "ℹ️ <b>Producción:</b> El webhook de Meta apunta al microservicio "
            "(puerto 8000). Este webhook local es solo para desarrollo/testing.")
        note.setWordWrap(True)
        note.setStyleSheet(
            f"color:{Colors.INFO_BASE};font-size:11px;padding:6px;")
        lw.addWidget(note)
        lw.addStretch()
        self._actualizar_webhook_status()
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
        spj_btn(btn_buscar, "primary")
        spj_btn(btn_refresh, "secondary")
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
        hh2 = self.tbl_hist.horizontalHeader()
        hh2.setSectionResizeMode(3, QHeaderView.Stretch)
        for i in (0, 1, 2, 4):
            hh2.setSectionResizeMode(i, QHeaderView.ResizeToContents)
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
        btn_refresh_m = QPushButton("🔄 Actualizar métricas")
        spj_btn(btn_refresh_m, "secondary")
        btn_refresh_m.clicked.connect(self._cargar_metricas)
        lmt.addWidget(btn_refresh_m)
        lmt.addStretch()
        self._cargar_metricas()
        return w

    # ── Números: carga / diálogo / eliminar ───────────────────────────────────

    def _cargar_tabla_numeros(self):
        rows = self._svc.get_numeros()
        self.tbl_numeros.setRowCount(0)
        for i, r in enumerate(rows):
            self.tbl_numeros.insertRow(i)
            for j, v in enumerate(r):
                it = QTableWidgetItem("✅" if v else "❌") if j == 5 \
                    else QTableWidgetItem(str(v) if v is not None else "")
                self.tbl_numeros.setItem(i, j, it)

    def _dialogo_numero(self, editar=False):
        row_id = None
        if editar:
            row = self.tbl_numeros.currentRow()
            if row < 0:
                QMessageBox.warning(self, "Aviso", "Selecciona un número primero.")
                return
            item = self.tbl_numeros.item(row, 0)
            if item:
                row_id = int(item.text())

        dlg = QDialog(self)
        dlg.setWindowTitle("Configurar número WhatsApp")
        dlg.setMinimumWidth(480)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()

        cmb_suc = QComboBox()
        cmb_suc.addItem("Global (todas las sucursales)", None)
        for suc in self._svc.get_sucursales_activas():
            cmb_suc.addItem(suc[1], suc[0])

        cmb_canal = QComboBox()
        cmb_canal.addItems(["todos", "clientes", "rrhh", "alertas"])
        cmb_prov  = QComboBox()
        cmb_prov.addItems(["meta", "twilio", "wppconnect", "baileys"])

        txt_numero   = PhoneWidget(default_country="+52")
        txt_phone_id = QLineEdit()
        txt_phone_id.setPlaceholderText("Meta Phone Number ID")
        txt_token    = QLineEdit()
        txt_token.setPlaceholderText("Meta Access Token o Twilio Auth Token")
        txt_token.setEchoMode(QLineEdit.Password)
        txt_sid    = QLineEdit()
        txt_sid.setPlaceholderText("Twilio Account SID")
        txt_rasa   = QLineEdit()
        txt_rasa.setPlaceholderText("http://localhost:5005")
        chk_rasa   = QCheckBox("Habilitar Rasa para esta sucursal")
        chk_activo = QCheckBox("Activo")
        chk_activo.setChecked(True)

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
            ex = self._svc.get_numero_by_id(row_id)
            if ex:
                for i in range(cmb_suc.count()):
                    if cmb_suc.itemData(i) == ex[0]:
                        cmb_suc.setCurrentIndex(i)
                        break
                idx = cmb_canal.findText(ex[1] or "todos")
                if idx >= 0:
                    cmb_canal.setCurrentIndex(idx)
                idx = cmb_prov.findText(ex[2] or "meta")
                if idx >= 0:
                    cmb_prov.setCurrentIndex(idx)
                txt_numero.set_phone(ex[3] or "")
                txt_phone_id.setText(ex[4] or "")
                # Show masked placeholder — do not pre-fill actual token
                txt_token.setPlaceholderText(
                    "(token guardado — introduce nuevo para cambiar)")
                txt_sid.setText(ex[6] or "")
                txt_rasa.setText(ex[7] or "http://localhost:5005")
                chk_rasa.setChecked(bool(ex[8]))
                chk_activo.setChecked(bool(ex[9]))

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec_() != dlg.Accepted:
            return

        suc_id     = cmb_suc.currentData()
        suc_nombre = cmb_suc.currentText() if suc_id else None
        token_val  = txt_token.text().strip()

        # If editing and token is empty, keep the existing token (don't overwrite)
        if row_id and not token_val:
            ex = self._svc.get_numero_by_id(row_id)
            token_val = ex[5] if ex else ""

        try:
            self._svc.save_numero(
                numero_id=row_id,
                suc_id=suc_id,
                canal=cmb_canal.currentText(),
                proveedor=cmb_prov.currentText(),
                numero=txt_numero.get_e164().strip(),
                phone_id=txt_phone_id.text().strip(),
                token=token_val,
                sid=txt_sid.text().strip(),
                rasa_url=txt_rasa.text().strip() or "http://localhost:5005",
                rasa_act=1 if chk_rasa.isChecked() else 0,
                activo=1 if chk_activo.isChecked() else 0,
                suc_nombre=suc_nombre,
            )
            self._cargar_tabla_numeros()
            QMessageBox.information(self, "✅", "Número guardado correctamente.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _eliminar_numero(self):
        row = self.tbl_numeros.currentRow()
        if row < 0:
            return
        item = self.tbl_numeros.item(row, 0)
        if not item:
            return
        rid = int(item.text())
        if QMessageBox.question(self, "Confirmar", "¿Eliminar este número?",
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        self._svc.delete_numero(rid)
        self._cargar_tabla_numeros()

    # ── Config bot ────────────────────────────────────────────────────────────

    def _cargar_config(self):
        try:
            cfg = self._svc.get_bot_config()
            self.txt_nombre_bot.setText(cfg["bot_nombre"])
            self.chk_bot_activo.setChecked(cfg["bot_activo"])
            self.chk_rasa_activo.setChecked(cfg["rasa_activo"])
            self.txt_rasa_url.setText(cfg["rasa_url"])
            self.spin_timeout.setValue(cfg["timeout"])
            self.txt_msg_bienvenida.setPlainText(cfg["msg_bienvenida"])
            self.chk_cotizaciones.setChecked(cfg["cotizaciones"])
            self.chk_clientes_rrhh.setChecked(cfg["rrhh_notif"])
            # Also load webhook config
            self.txt_verify_token.setText(
                self._svc.get_config_value("verify_token", "spj_verify"))
        except Exception as e:
            logger.debug("cargar_config WA: %s", e)

    def _guardar_config_bot(self):
        try:
            self._svc.save_bot_config({
                "bot_nombre":     self.txt_nombre_bot.text().strip(),
                "bot_activo":     self.chk_bot_activo.isChecked(),
                "rasa_activo":    self.chk_rasa_activo.isChecked(),
                "rasa_url":       self.txt_rasa_url.text().strip(),
                "timeout":        self.spin_timeout.value(),
                "msg_bienvenida": self.txt_msg_bienvenida.toPlainText().strip(),
                "cotizaciones":   self.chk_cotizaciones.isChecked(),
                "rrhh_notif":     self.chk_clientes_rrhh.isChecked(),
            })
            wa = getattr(self.container, "whatsapp_service", None)
            if wa and hasattr(wa, "_rasa_url"):
                wa._rasa_url = self.txt_rasa_url.text().strip()
            QMessageBox.information(self, "✅ Guardado", "Configuración del bot guardada.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ── Historial ─────────────────────────────────────────────────────────────

    def _cargar_historial(self):
        buscar = (self.txt_buscar_wa.text().strip()
                  if hasattr(self, "txt_buscar_wa") else "")
        rows = self._svc.get_history(buscar)
        self.tbl_hist.setRowCount(0)
        for i, r in enumerate(rows):
            self.tbl_hist.insertRow(i)
            for j, v in enumerate(r):
                self.tbl_hist.setItem(i, j, QTableWidgetItem(str(v) if v else ""))

    # ── Métricas ──────────────────────────────────────────────────────────────

    def _cargar_metricas(self):
        try:
            m = self._svc.get_metrics()
            cfg = self._svc.get_bot_config()
            rasa_url = cfg["rasa_url"]
            rasa_status = ("🔵 Configurado"
                           if rasa_url and rasa_url != "http://localhost:5005"
                           else "⚫ No configurado")
            text = (
                f"<b>Pedidos WhatsApp hoy:</b> {m['hoy']}<br>"
                f"<b>Total histórico:</b> {m['total']}<br>"
                f"<b>Pendientes:</b> {m['pendientes']}<br>"
                f"<b>Valor total generado:</b> ${m['valor_total']:,.2f}<br>"
                f"<b>Sesiones de bot activas:</b> {m['sesiones']}<br><br>"
                f"<b>Bot:</b> {'🟢 Activo' if cfg['bot_activo'] else '🔴 Inactivo'}<br>"
                f"<b>Rasa:</b> {rasa_status}<br>"
                f"<b>Cotizaciones:</b> {'✅' if cfg['cotizaciones'] else '❌'}"
            )
            self.lbl_metrics.setText(text)
        except Exception as e:
            self.lbl_metrics.setText(f"Error cargando métricas: {e}")

    # ── Test de conexión ──────────────────────────────────────────────────────

    def _test_conexion(self):
        wa = getattr(self.container, "whatsapp_service", None)
        ok = self._svc.test_connection(wa)
        if ok:
            self.lbl_status.setStyleSheet(
                f"color:{Colors.SUCCESS_BASE};font-size:18px;")
            QMessageBox.information(self, "✅ Conexión OK",
                                    "WhatsApp conectado correctamente.")
        else:
            self.lbl_status.setStyleSheet(
                f"color:{Colors.DANGER_BASE};font-size:18px;")
            QMessageBox.warning(self, "⚠️ Sin conexión",
                "No se pudo verificar la conexión.\n\n"
                "Verifica las credenciales en la pestaña Números / Sucursales.")

    # ── Webhook ───────────────────────────────────────────────────────────────

    def _actualizar_webhook_status(self):
        wa = getattr(self.container, "whatsapp_webhook", None)
        running = wa and hasattr(wa, "_running") and wa._running
        if running:
            self.lbl_webhook_status.setText(
                "🟢 Webhook activo — escuchando mensajes entrantes")
            self.lbl_webhook_status.setStyleSheet(
                f"color:{Colors.SUCCESS_BASE};font-size:13px;padding:6px;")
        else:
            self.lbl_webhook_status.setText("🔴 Webhook local detenido")
            self.lbl_webhook_status.setStyleSheet(
                f"color:{Colors.DANGER_BASE};font-size:13px;padding:6px;")

    def _iniciar_webhook(self):
        try:
            puerto = int(self.txt_webhook_puerto.text() or "8767")
            verify = self.txt_verify_token.text().strip() or "spj_verify"
            wa_hook = getattr(self.container, "whatsapp_webhook", None)
            if wa_hook:
                wa_hook._port = puerto
                wa_hook.start()
                self._svc._cfg_repo.set_config_raw("wa_verify_token", verify)
                self._svc._cfg_repo.commit()
                self._actualizar_webhook_status()
                QMessageBox.information(self, "✅",
                                        f"Webhook iniciado en puerto {puerto}")
            else:
                QMessageBox.warning(self, "Aviso",
                    "WhatsAppWebhookServer no está disponible en el contenedor.\n"
                    "Para producción usa el microservicio en puerto 8000.")
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
        """Verifica que el webhook local responda al desafío de Meta."""
        try:
            import urllib.request
            puerto = self.txt_webhook_puerto.text().strip() or "8767"
            verify = self.txt_verify_token.text().strip() or "spj_verify"
            url = (
                f"http://127.0.0.1:{puerto}/webhook"
                f"?hub.mode=subscribe&hub.verify_token={verify}"
                f"&hub.challenge=test123"
            )
            resp = urllib.request.urlopen(url, timeout=3)
            body = resp.read().decode()
            if "test123" in body:
                QMessageBox.information(self, "✅ OK",
                    f"Webhook responde correctamente.\nRespuesta: {body}")
            else:
                QMessageBox.warning(self, "⚠️",
                                    f"Respuesta inesperada: {body}")
        except Exception as e:
            QMessageBox.warning(self, "❌ Sin respuesta",
                f"No se pudo conectar al webhook local:\n{e}\n\n"
                "Asegúrate de haberlo iniciado primero.")

    def closeEvent(self, event):
        try:
            self._timer.stop()
        except Exception:
            pass
        super().closeEvent(event)
