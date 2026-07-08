# modulos/rrhh_turnos.py — SPJ POS v13.2
"""
Roles de Turnos: programa turnos, rota automáticamente, 
y notifica vía WhatsApp el día de descanso una semana y un día antes.
"""
from __future__ import annotations
from core.services.auto_audit import audit_write
from modulos.spj_styles import spj_btn, apply_btn_styles, apply_object_names
import logging
from datetime import date, timedelta, datetime
from modulos.spj_phone_widget import PhoneWidget
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QDialog, QFormLayout, QComboBox, QDialogButtonBox, QMessageBox,
    QDateEdit, QSpinBox, QCheckBox, QGroupBox, QTextEdit, QLineEdit,
    QTabWidget,
)
from PyQt5.QtCore import Qt, QDate

logger = logging.getLogger("spj.rrhh.turnos")


class ModuloRRHHTurnos(QWidget):

    def __init__(self, container, parent=None):
        super().__init__(parent)
        self.container   = container
        self.db          = container.db
        self.sucursal_id = getattr(container, "sucursal_id", "") or ""
        self.usuario     = ""
        self._ensure_tables()
        self._build_ui()
        self._cargar()

    def set_usuario_actual(self, u: str, r: str = "") -> None: self.usuario = u
    def set_sucursal(self, sid: int, nombre: str = "") -> None:
        self.sucursal_id = sid; self._cargar()

    def _ensure_tables(self):
        # Plan B born-clean: schema canónico en migrations/ (DDL y commit removidos).
        pass

    def _build_ui(self):
        lay = QVBoxLayout(self)
        hdr = QHBoxLayout()
        lbl = QLabel("🗓️ Roles y Turnos de Trabajo")
        lbl.setStyleSheet("font-size:17px;font-weight:bold;")
        hdr.addWidget(lbl); hdr.addStretch()
        btn_notif = QPushButton("📲 Enviar notificaciones pendientes")
        btn_notif.setStyleSheet("background:#8e44ad;color:white;padding:5px 12px;")
        btn_notif.clicked.connect(self._enviar_notificaciones_pendientes)
        hdr.addWidget(btn_notif)
        lay.addLayout(hdr)

        tabs = QTabWidget()
        lay.addWidget(tabs)

        # ── Tab 1: Roles de turno ─────────────────────────────────────────
        tab_roles = QWidget(); tabs.addTab(tab_roles, "🎯 Roles de Turno")
        lr = QVBoxLayout(tab_roles)
        btn_row = QHBoxLayout()
        btn_add_r = QPushButton("➕ Nuevo rol"); btn_add_r.setStyleSheet("background:#27ae60;color:white;padding:5px 12px;")
        btn_edit_r = QPushButton("✏️ Editar"); btn_edit_r.setStyleSheet("background:#f39c12;color:white;padding:5px 12px;")
        btn_del_r  = QPushButton("🗑️ Eliminar"); btn_del_r.setStyleSheet("background:#e74c3c;color:white;padding:5px 12px;")
        btn_row.addWidget(btn_add_r); btn_row.addWidget(btn_edit_r); btn_row.addWidget(btn_del_r); btn_row.addStretch()
        lr.addLayout(btn_row)
        self.tbl_roles = QTableWidget(); self.tbl_roles.setColumnCount(4)
        self.tbl_roles.setHorizontalHeaderLabels(["ID","Nombre","Horario","Descripción"])
        self.tbl_roles.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tbl_roles.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.tbl_roles.setColumnHidden(0, True)
        self.tbl_roles.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_roles.setSelectionBehavior(QAbstractItemView.SelectRows)
        lr.addWidget(self.tbl_roles)
        btn_add_r.clicked.connect(self._nuevo_rol)
        btn_edit_r.clicked.connect(lambda: self._editar_rol())
        btn_del_r.clicked.connect(self._eliminar_rol)

        # ── Tab 2: Asignaciones ───────────────────────────────────────────
        tab_asig = QWidget(); tabs.addTab(tab_asig, "👤 Asignaciones")
        la = QVBoxLayout(tab_asig)
        btn_row2 = QHBoxLayout()
        btn_add_a  = QPushButton("➕ Asignar turno"); btn_add_a.setStyleSheet("background:#27ae60;color:white;padding:5px 12px;")
        btn_edit_a = QPushButton("✏️ Editar"); btn_edit_a.setStyleSheet("background:#f39c12;color:white;padding:5px 12px;")
        btn_del_a  = QPushButton("🗑️ Quitar"); btn_del_a.setStyleSheet("background:#e74c3c;color:white;padding:5px 12px;")
        btn_row2.addWidget(btn_add_a); btn_row2.addWidget(btn_edit_a); btn_row2.addWidget(btn_del_a); btn_row2.addStretch()
        la.addLayout(btn_row2)
        self.tbl_asig = QTableWidget(); self.tbl_asig.setColumnCount(6)
        self.tbl_asig.setHorizontalHeaderLabels(["ID","Empleado","Turno","Día Descanso","Desde","Hasta"])
        self.tbl_asig.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tbl_asig.setColumnHidden(0, True)
        self.tbl_asig.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_asig.setSelectionBehavior(QAbstractItemView.SelectRows)
        la.addWidget(self.tbl_asig)
        btn_add_a.clicked.connect(self._asignar_turno)
        btn_edit_a.clicked.connect(lambda: self._editar_asignacion())
        btn_del_a.clicked.connect(self._quitar_asignacion)

        # ── Tab 3: Config notificaciones ──────────────────────────────────
        tab_notif = QWidget(); tabs.addTab(tab_notif, "📲 Notificaciones")
        ln = QVBoxLayout(tab_notif)
        grp = QGroupBox("Configuración de notificaciones de descanso")
        fn  = QFormLayout(grp)
        info = QLabel(
            "El sistema revisará diariamente los días de descanso próximos\n"
            "y enviará un mensaje WhatsApp al empleado.\n"
            "• Notificación 1 semana antes\n"
            "• Notificación 1 día antes"
        )
        info.setStyleSheet("color:#555;font-size:11px;")
        fn.addRow(info)
        self.chk_notif_activas = QCheckBox("Habilitar notificaciones automáticas")
        self.txt_msg_semana = QTextEdit()
        self.txt_msg_semana.setMaximumHeight(70)
        self.txt_msg_semana.setPlaceholderText("Mensaje 1 semana antes. Usa {{nombre}} y {{dia_descanso}}")
        self.txt_msg_dia = QTextEdit()
        self.txt_msg_dia.setMaximumHeight(70)
        self.txt_msg_dia.setPlaceholderText("Mensaje 1 día antes. Usa {{nombre}} y {{dia_descanso}}")
        fn.addRow("", self.chk_notif_activas)
        fn.addRow("Mensaje semana antes:", self.txt_msg_semana)
        fn.addRow("Mensaje día antes:",    self.txt_msg_dia)
        ln.addWidget(grp)
        btn_save_n = QPushButton("💾 Guardar configuración de notificaciones")
        btn_save_n.setStyleSheet("background:#27ae60;color:white;font-weight:bold;padding:7px 16px;")
        btn_save_n.clicked.connect(self._guardar_config_notif)
        ln.addWidget(btn_save_n); ln.addStretch()
        self._cargar_config_notif()
        apply_object_names(self)

    # ── Cargar ────────────────────────────────────────────────────────────────

    def _cargar(self):
        self._cargar_roles(); self._cargar_asignaciones()

    def _cargar_roles(self):
        try:
            from core.services.rrhh_turnos_service import RRHHTurnosService
            rows = RRHHTurnosService(self.db).listar_roles_activos()
        except Exception: rows = []
        self.tbl_roles.setRowCount(0)
        for i, r in enumerate(rows):
            self.tbl_roles.insertRow(i)
            for j, v in enumerate(r):
                self.tbl_roles.setItem(i, j, QTableWidgetItem(str(v) if v else ""))

    def _cargar_asignaciones(self):
        try:
            from core.services.rrhh_turnos_service import RRHHTurnosService
            rows = RRHHTurnosService(self.db).listar_asignaciones()
        except Exception: rows = []
        self.tbl_asig.setRowCount(0)
        for i, r in enumerate(rows):
            self.tbl_asig.insertRow(i)
            for j, v in enumerate(r):
                self.tbl_asig.setItem(i, j, QTableWidgetItem(str(v) if v else ""))

    # ── Roles CRUD ────────────────────────────────────────────────────────────

    def _nuevo_rol(self): self._dialogo_rol()
    def _editar_rol(self):
        row = self.tbl_roles.currentRow()
        if row < 0: return
        rid = self.tbl_roles.item(row,0).text()
        self._dialogo_rol(rid)

    def _dialogo_rol(self, rol_id=None):
        dlg = QDialog(self); dlg.setWindowTitle("Rol de Turno"); dlg.setMinimumWidth(360)
        lay = QVBoxLayout(dlg); form = QFormLayout()
        txt_nombre = QLineEdit(); txt_hi = QLineEdit("08:00"); txt_hf = QLineEdit("16:00")
        txt_desc   = QLineEdit()
        from core.services.rrhh_turnos_service import RRHHTurnosService
        _svc = RRHHTurnosService(self.db)
        if rol_id:
            row = _svc.obtener_rol(rol_id)
            if row: txt_nombre.setText(row[0]); txt_hi.setText(row[1] or ""); txt_hf.setText(row[2] or ""); txt_desc.setText(row[3] or "")
        form.addRow("Nombre *:",      txt_nombre)
        form.addRow("Hora inicio:",   txt_hi)
        form.addRow("Hora fin:",      txt_hf)
        form.addRow("Descripción:",   txt_desc)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec_() != QDialog.Accepted: return
        nombre = txt_nombre.text().strip()
        if not nombre: return
        try:
            if rol_id:
                _svc.actualizar_rol(rol_id, nombre, txt_hi.text(), txt_hf.text(), txt_desc.text())
            else:
                _svc.crear_rol(nombre, txt_hi.text(), txt_hf.text(), txt_desc.text())
            self._cargar_roles()
        except Exception as e:
            QMessageBox.critical(self,"Error",str(e))

    def _eliminar_rol(self):
        row = self.tbl_roles.currentRow()
        if row < 0: return
        rid = self.tbl_roles.item(row,0).text()
        if QMessageBox.question(self,"Confirmar","¿Eliminar este rol de turno?",
           QMessageBox.Yes|QMessageBox.No) != QMessageBox.Yes: return
        from core.services.rrhh_turnos_service import RRHHTurnosService
        RRHHTurnosService(self.db).desactivar_rol(rid)
        self._cargar_roles()

    # ── Asignaciones ──────────────────────────────────────────────────────────

    def _asignar_turno(self): self._dialogo_asignacion()
    def _editar_asignacion(self):
        row = self.tbl_asig.currentRow()
        if row < 0: return
        aid = self.tbl_asig.item(row,0).text()
        self._dialogo_asignacion(aid)

    def _dialogo_asignacion(self, asig_id=None):
        dlg = QDialog(self); dlg.setWindowTitle("Asignación de Turno"); dlg.setMinimumWidth(400)
        lay = QVBoxLayout(dlg); form = QFormLayout()
        cmb_emp  = QComboBox(); cmb_rol = QComboBox()
        cmb_desc = QComboBox()
        cmb_desc.addItems(["Domingo","Lunes","Martes","Miércoles","Jueves","Viernes","Sábado"])
        date_ini = QDateEdit(QDate.currentDate()); date_ini.setCalendarPopup(True)
        date_fin = QDateEdit(QDate.currentDate().addMonths(3)); date_fin.setCalendarPopup(True)
        spin_rot = QSpinBox(); spin_rot.setRange(1,30); spin_rot.setValue(7); spin_rot.setSuffix(" días")
        chk_sem  = QCheckBox("Notificar 1 semana antes"); chk_sem.setChecked(True)
        chk_dia  = QCheckBox("Notificar 1 día antes"); chk_dia.setChecked(True)
        from core.services.rrhh_turnos_service import RRHHTurnosService
        _svc = RRHHTurnosService(self.db)
        try:
            emps = _svc.listar_empleados_lookup()
            for r in emps: cmb_emp.addItem(r[1].strip(), r[0])
            roles = _svc.listar_roles_lookup()
            for r in roles: cmb_rol.addItem(r[1], r[0])
        except Exception: pass
        form.addRow("Empleado:",    cmb_emp); form.addRow("Turno:",       cmb_rol)
        form.addRow("Día descanso:", cmb_desc)
        form.addRow("Desde:",       date_ini); form.addRow("Hasta:",      date_fin)
        form.addRow("Rotar cada:",  spin_rot)
        form.addRow("",             chk_sem); form.addRow("", chk_dia)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec_() != QDialog.Accepted: return
        try:
            datos = (cmb_emp.currentData(), cmb_rol.currentData(),
                     date_ini.date().toString("yyyy-MM-dd"),
                     date_fin.date().toString("yyyy-MM-dd"),
                     cmb_desc.currentText(), spin_rot.value(),
                     1 if chk_sem.isChecked() else 0,
                     1 if chk_dia.isChecked() else 0)
            if asig_id:
                _svc.actualizar_asignacion(asig_id, *datos)
            else:
                _svc.crear_asignacion(*datos)
            self._cargar_asignaciones()
        except Exception as e:
            QMessageBox.critical(self,"Error",str(e))

    def _quitar_asignacion(self):
        row = self.tbl_asig.currentRow()
        if row < 0: return
        aid = self.tbl_asig.item(row,0).text()
        if QMessageBox.question(self,"Confirmar","¿Quitar esta asignación de turno?",
           QMessageBox.Yes|QMessageBox.No) != QMessageBox.Yes: return
        from core.services.rrhh_turnos_service import RRHHTurnosService
        RRHHTurnosService(self.db).desactivar_asignacion(aid)
        self._cargar_asignaciones()

    # ── Notificaciones ────────────────────────────────────────────────────────

    def _cargar_config_notif(self):
        try:
            from core.services.rrhh_turnos_service import RRHHTurnosService
            _svc = RRHHTurnosService(self.db)
            activas = _svc.obtener_config("turnos_notif_activas")
            self.chk_notif_activas.setChecked(bool(activas and activas[0]=="1"))
            msg_s = _svc.obtener_config("turnos_msg_semana")
            msg_d = _svc.obtener_config("turnos_msg_dia")
            if msg_s: self.txt_msg_semana.setPlainText(msg_s[0])
            else:     self.txt_msg_semana.setPlainText("Hola {{nombre}}, recuerda que tu día de descanso esta semana es el {{dia_descanso}}. 🌟")
            if msg_d: self.txt_msg_dia.setPlainText(msg_d[0])
            else:     self.txt_msg_dia.setPlainText("Hola {{nombre}}, mañana es tu día de descanso ({{dia_descanso}}). ¡Descansa bien! 😊")
        except Exception: pass

    def _guardar_config_notif(self):
        try:
            from core.services.rrhh_turnos_service import RRHHTurnosService
            _svc = RRHHTurnosService(self.db)
            for clave, valor in [
                ("turnos_notif_activas", "1" if self.chk_notif_activas.isChecked() else "0"),
                ("turnos_msg_semana", self.txt_msg_semana.toPlainText().strip()),
                ("turnos_msg_dia",    self.txt_msg_dia.toPlainText().strip()),
            ]:
                _svc.guardar_config(clave, valor)
            QMessageBox.information(self,"✅ Guardado","Configuración guardada.")
        except Exception as e:
            QMessageBox.critical(self,"Error",str(e))

    def _enviar_notificaciones_pendientes(self):
        """Revisa asignaciones y envía WA si toca notificar."""
        hoy = date.today()
        enviados = 0
        from core.services.rrhh_turnos_service import RRHHTurnosService
        _svc = RRHHTurnosService(self.db)
        try:
            rows = _svc.listar_asignaciones_para_notificar(str(hoy))
        except Exception as e:
            QMessageBox.warning(self,"Error",str(e)); return

        dias_map = {"Domingo":6,"Lunes":0,"Martes":1,"Miércoles":2,
                    "Jueves":3,"Viernes":4,"Sábado":5}
        msg_sem = self.txt_msg_semana.toPlainText()
        msg_dia = self.txt_msg_dia.toPlainText()

        for r in rows:
            asig_id, nombre, telefono, dia_desc, notif_sem, notif_dia = r
            if not telefono: continue
            dias_desc_num = dias_map.get(dia_desc, 6)
            # Find next descanso from today
            days_ahead = (dias_desc_num - hoy.weekday()) % 7
            if days_ahead == 0: days_ahead = 7
            prox_descanso = hoy + timedelta(days=days_ahead)
            diff = (prox_descanso - hoy).days
            msg = None
            tipo = None
            if notif_sem and diff == 7:
                msg  = msg_sem.replace("{{nombre}}", nombre).replace("{{dia_descanso}}", dia_desc)
                tipo = "semana"
            elif notif_dia and diff == 1:
                msg  = msg_dia.replace("{{nombre}}", nombre).replace("{{dia_descanso}}", dia_desc)
                tipo = "dia"
            if msg:
                try:
                    wa = getattr(self.container, "whatsapp_service", None)
                    if wa:
                        wa.send_message(telefono, msg)
                    _svc.registrar_notificacion(asig_id, tipo, msg)
                    enviados += 1
                except Exception as e:
                    logger.warning("Notif WA turno: %s", e)
        QMessageBox.information(self,"📲 Notificaciones",
            f"Se enviaron {enviados} notificaciones." if enviados
            else "No hay notificaciones pendientes para hoy.")
