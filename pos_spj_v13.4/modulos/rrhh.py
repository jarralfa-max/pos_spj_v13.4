
# modulos/rrhh.py
import logging
from core.events.event_bus import get_bus
from modulos.spj_phone_widget import PhoneWidget
from modulos.spj_styles import spj_btn, apply_btn_styles
from modulos.design_tokens import Colors, Spacing, Typography, Borders
from modulos.ui_components import create_primary_button, create_success_button, create_danger_button, create_input, create_heading, create_subheading, apply_tooltip
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QIcon
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class DialogoEmpleado(QDialog):
    """Formulario para Crear y Editar Personal"""
    def __init__(self, db_conn, empleado_id=None, parent=None):
        super().__init__(parent)
        self.db = db_conn
        self.empleado_id = empleado_id
        
        self.setWindowTitle("Nuevo Empleado" if not empleado_id else "Editar Empleado")
        self.setMinimumWidth(400)
        self.setModal(True)
        self.init_ui()
        
        if self.empleado_id:
            self.cargar_datos()

    def init_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        self.txt_nombre = QLineEdit()
        self.txt_apellidos = QLineEdit()
        self.txt_telefono = PhoneWidget(); self.txt_telefono.setPlaceholderText("+52 ej: +5215512345678"); self.txt_telefono.setToolTip("Formato WhatsApp: +codigopais+numero")
        
        self.cmb_puesto = QComboBox()
        self.cmb_puesto.addItems(["Cajero", "Almacenista", "Carnicero", "Repartidor", "Gerente"])
        self.cmb_puesto.setEditable(True) # Permite escribir nuevos puestos
        
        self.txt_salario = QDoubleSpinBox()
        self.txt_salario.setRange(0.0, 999999.0)
        self.txt_salario.setPrefix("$ ")
        self.txt_salario.setToolTip("Salario base por periodo (Ej. Quincena o Semana)")
        
        self.dt_ingreso = QDateEdit()
        self.dt_ingreso.setCalendarPopup(True)
        self.dt_ingreso.setDate(datetime.now().date())
        
        form.addRow("Nombre(s)*:", self.txt_nombre)
        form.addRow("Apellidos:", self.txt_apellidos)
        form.addRow("Teléfono (WhatsApp):", self.txt_telefono)
        form.addRow("Puesto:", self.cmb_puesto)
        form.addRow("Salario Base:", self.txt_salario)
        form.addRow("Fecha de Ingreso:", self.dt_ingreso)
        
        layout.addLayout(form)
        
        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.guardar)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _on_refresh(self, event_type: str, data: dict) -> None:
        """Auto-refresh al recibir eventos del EventBus."""
        try: self.cargar_datos()
        except Exception: pass

    def cargar_datos(self):
        try:
            cursor = self.db.cursor()
            emp = cursor.execute("SELECT * FROM personal WHERE id = ?", (self.empleado_id,)).fetchone()
            if emp:
                self.txt_nombre.setText(emp['nombre'])
                self.txt_apellidos.setText(emp['apellidos'] or '')
                self.txt_telefono.set_phone(emp['telefono'] or '')
                self.cmb_puesto.setCurrentText(emp['puesto'] or 'Cajero')
                self.txt_salario.setValue(emp['salario'] or 0.0)
                
                if emp['fecha_ingreso']:
                    # Convertir texto a QDate
                    from PyQt5.QtCore import QDate
                    try:
                        partes = emp['fecha_ingreso'].split('-')
                        if len(partes) == 3:
                            self.dt_ingreso.setDate(QDate(int(partes[0]), int(partes[1]), int(partes[2])))
                    except: pass
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudo cargar: {e}")

    def guardar(self):
        nombre = self.txt_nombre.text().strip()
        if not nombre:
            QMessageBox.warning(self, "Validación", "El nombre es obligatorio.")
            return
            
        try:
            cursor = self.db.cursor()
            datos = (
                nombre, self.txt_apellidos.text().strip(), self.cmb_puesto.currentText(),
                self.txt_salario.value(), self.dt_ingreso.date().toString("yyyy-MM-dd"),
                self.txt_telefono.get_e164().strip()
            )
            
            if self.empleado_id:
                cursor.execute("""
                    UPDATE personal SET 
                        nombre=?, apellidos=?, puesto=?, salario=?, fecha_ingreso=?, telefono=?
                    WHERE id=?
                """, (*datos, self.empleado_id))
            else:
                cursor.execute("""
                    INSERT INTO personal (nombre, apellidos, puesto, salario, fecha_ingreso, telefono, activo)
                    VALUES (?, ?, ?, ?, ?, ?, 1)
                """, datos)
                
            self.db.commit()
            self.accept()
        except Exception as e:
            self.db.rollback()
            QMessageBox.critical(self, "Error", f"Fallo al guardar: {e}")

class ModuloRRHH(QWidget):
    """
    Módulo de Recursos Humanos y Nóminas (Ultra-Protegido).
    """
    def __init__(self, container, parent=None):
        super().__init__(parent)
        try:
            from modulos.spj_refresh_mixin import RefreshMixin
            if isinstance(self, RefreshMixin):
                self._init_refresh(container, ["EMPLEADO_ACTUALIZADO"])
        except Exception: pass
        self.container = container
        self.sucursal_id = 1
        self.usuario_actual = ""
        
        self.init_ui()

    def set_sucursal(self, sucursal_id: int, nombre_sucursal: str):
        self.sucursal_id = sucursal_id

    def set_usuario_actual(self, usuario: str, rol: str):
        self.usuario_actual = usuario
        # Auto-desbloquear si el rol es 'admin' o 'gerente_rh'
        if rol in ['admin', 'gerente_rh']:
            self.desbloquear_modulo()

    def init_ui(self):
        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(0, 0, 0, 0)
        
        # 🛡️ PANTALLAS: Bloqueo y Dashboard
        self.stack = QStackedWidget()
        
        self.pantalla_bloqueo = self._crear_pantalla_bloqueo()
        self.pantalla_dashboard = self._crear_dashboard_rrhh()
        
        self.stack.addWidget(self.pantalla_bloqueo)    # Index 0
        self.stack.addWidget(self.pantalla_dashboard)  # Index 1
        
        layout_principal.addWidget(self.stack)

    # =========================================================
    # PANTALLA DE BLOQUEO DE SEGURIDAD
    # =========================================================
    def _crear_pantalla_bloqueo(self):
        panel = QWidget()
        panel.setObjectName("card")  # Usar clase CSS para fondo y bordes
        
        layout = QVBoxLayout(panel)
        
        lbl_icono = QLabel("🔒")
        lbl_icono.setAlignment(Qt.AlignCenter)
        lbl_icono.setStyleSheet(f"font-size: {Typography.SIZE_72};")
        
        lbl_titulo = create_heading(self, "Área Restringida: Recursos Humanos y Nómina")
        lbl_titulo.setAlignment(Qt.AlignCenter)
        
        self.txt_password = QLineEdit()
        self.txt_password.setEchoMode(QLineEdit.Password)
        self.txt_password.setPlaceholderText("Ingrese NIP o Contraseña Maestra...")
        self.txt_password.setObjectName("inputField")  # Usar clase CSS estándar
        self.txt_password.setStyleSheet(f"padding: {Spacing.LG}; font-size: {Typography.SIZE_LG};")  # Solo tamaño específico
        self.txt_password.setFixedWidth(300)
        self.txt_password.returnPressed.connect(self.intentar_desbloqueo)
        apply_tooltip(self.txt_password, "Ingrese su contraseña para acceder al módulo de RRHH")
        
        btn_desbloquear = create_success_button(self, "Desbloquear Módulo", "Acceder al módulo restringido de RRHH")
        btn_desbloquear.setFixedWidth(300)
        btn_desbloquear.setStyleSheet(f"padding: {Spacing.LG}; font-size: {Typography.SIZE_LG}; font-weight: bold;")  # Solo tamaño específico
        
        layout.addStretch()
        layout.addWidget(lbl_icono)
        layout.addWidget(lbl_titulo)
        layout.addWidget(self.txt_password, alignment=Qt.AlignCenter)
        layout.addWidget(btn_desbloquear, alignment=Qt.AlignCenter)
        layout.addStretch()
        
        return panel

    def intentar_desbloqueo(self):
        pwd = self.txt_password.text()
        # Aquí puedes validarlo contra una clave maestra del ConfigService o el AuthService
        clave_maestra = self.container.config_service.get('pin_rrhh', '1234')
        
        if pwd == clave_maestra:
            self.desbloquear_modulo()
        else:
            QMessageBox.critical(self, "Acceso Denegado", "Contraseña incorrecta.")
            self.txt_password.clear()
            
            # Auditoría: Alguien intentó ver las nóminas
            if hasattr(self.container, 'audit_service'):
                self.container.audit_service.log_change(
                    usuario=self.usuario_actual, accion="INTENTO_ACCESO_FALLIDO", 
                    modulo="RRHH", entidad="seguridad"
                )

    def desbloquear_modulo(self):
        self.stack.setCurrentIndex(1) # Mostrar el Dashboard real
        self.cargar_lista_empleados()

    # =========================================================
    # DASHBOARD REAL DE RRHH
    # =========================================================

    def _crear_dashboard_rrhh(self):
        from PyQt5.QtWidgets import QTabWidget
        dashboard = QWidget()
        lay = QVBoxLayout(dashboard)
        lay.setContentsMargins(0,0,0,0)

        self.tabs_rrhh = QTabWidget()

        # Tabs principales
        self.tab_empleados  = QWidget()
        self.tab_asistencias = QWidget()
        self.tab_nomina     = QWidget()
        self.tab_vacaciones = QWidget()
        self.tab_evaluaciones = QWidget()

        self.tabs_rrhh.addTab(self.tab_empleados,    "👔 Empleados")
        self.tabs_rrhh.addTab(self.tab_asistencias,  "📅 Asistencias")
        self.tabs_rrhh.addTab(self.tab_nomina,        "💰 Nómina")
        self.tabs_rrhh.addTab(self.tab_vacaciones,   "🏖️ Vacaciones")
        self.tabs_rrhh.addTab(self.tab_evaluaciones, "⭐ Evaluaciones")

        self.tab_puestos = QWidget()
        self.tabs_rrhh.addTab(self.tab_puestos, "🪑 Puestos")

        self.tab_roles_turno = QWidget()
        self.tabs_rrhh.addTab(self.tab_roles_turno, "🗓️ Turnos de Trabajo")

        # ── Tab Reglas Laborales (HRRuleEngine) ──────────────────────────
        self.tab_reglas = QWidget()
        self.tabs_rrhh.addTab(self.tab_reglas, "⚖️ Reglas Laborales")

        self.tabs_rrhh.currentChanged.connect(self._on_rrhh_tab_change)
        lay.addWidget(self.tabs_rrhh)

        self.setup_tab_empleados()
        self.setup_tab_asistencias()
        self.setup_tab_nomina()
        self.setup_tab_vacaciones()
        self.setup_tab_evaluaciones()
        self.setup_tab_puestos()
        self._setup_tab_turnos_completo()
        self.setup_tab_reglas_laborales()
        return dashboard

    def setup_tab_roles_turno(self):
        """Tab para gestionar roles de turno del personal."""
        from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel,
            QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
            QDialog, QFormLayout, QLineEdit, QTimeEdit, QColorDialog,
            QDialogButtonBox, QMessageBox)
        from PyQt5.QtCore import QTime

        lay = QVBoxLayout(self.tab_roles_turno)

        info = QLabel("Define los roles de turno: Mañana, Tarde, Noche, etc. "
                      "Cada rol tiene horario y color para el calendario.")
        info.setWordWrap(True)
        info.setObjectName("caption")  # Usar clase CSS para texto secundario
        info.setStyleSheet(f"background: {Colors.INFO_BG}; padding: {Spacing.SM}; border-radius: {Borders.RADIUS_SM}; font-size: {Typography.SIZE_XS};")
        lay.addWidget(info)

        btn_row = QHBoxLayout()
        btn_add = create_success_button(self, "➕ Nuevo rol de turno", "Agregar un nuevo rol de turno")
        btn_del = create_danger_button(self, "🗑️ Eliminar", "Eliminar rol de turno seleccionado")
        btn_row.addWidget(btn_add); btn_row.addWidget(btn_del); btn_row.addStretch()
        lay.addLayout(btn_row)

        self._tbl_roles_turno = QTableWidget()
        self._tbl_roles_turno.setColumnCount(5)
        self._tbl_roles_turno.setHorizontalHeaderLabels(
            ["ID","Nombre","Hora inicio","Hora fin","Color"])
        hh = self._tbl_roles_turno.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        self._tbl_roles_turno.setColumnHidden(0, True)
        self._tbl_roles_turno.setSelectionBehavior(QTableWidget.SelectRows)
        lay.addWidget(self._tbl_roles_turno)

        btn_add.clicked.connect(self._nuevo_rol_turno)
        btn_del.clicked.connect(self._eliminar_rol_turno)
        self._cargar_roles_turno()

    def _cargar_roles_turno(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        try:
            conn = self.container.db if hasattr(self,'container') else self.conexion
            rows = conn.execute(
                "SELECT id, nombre, hora_inicio, hora_fin, COALESCE(color,'#3498db') "
                "FROM turno_roles ORDER BY nombre"
            ).fetchall()
        except Exception:
            rows = []
        self._tbl_roles_turno.setRowCount(0)
        for i, r in enumerate(rows):
            self._tbl_roles_turno.insertRow(i)
            for j, v in enumerate(r):
                self._tbl_roles_turno.setItem(i, j, QTableWidgetItem(str(v) if v else ""))

    def _nuevo_rol_turno(self):
        from PyQt5.QtWidgets import (QDialog, QFormLayout, QDialogButtonBox,
            QVBoxLayout, QLineEdit, QTimeEdit, QColorDialog, QPushButton,
            QHBoxLayout, QMessageBox)
        from PyQt5.QtCore import QTime

        dlg = QDialog(self); dlg.setWindowTitle("Nuevo Rol de Turno")
        dlg.setMinimumWidth(360)
        lay = QVBoxLayout(dlg); form = QFormLayout()
        txt_nombre = create_input(self, "Ej: Turno Mañana", "Nombre del rol de turno")
        te_inicio  = QTimeEdit(QTime(8,0)); te_inicio.setDisplayFormat("HH:mm"); te_inicio.setObjectName("inputField")
        te_fin     = QTimeEdit(QTime(16,0)); te_fin.setDisplayFormat("HH:mm"); te_fin.setObjectName("inputField")
        self._rol_color = Colors.PRIMARY_BASE
        btn_color = QPushButton("🎨 Color"); 
        btn_color.setObjectName("secondaryBtn")
        btn_color.setStyleSheet(f"background:{self._rol_color};color:white;")
        apply_tooltip(btn_color, "Seleccionar color para identificar el turno en el calendario")
        def pick_color():
            from PyQt5.QtWidgets import QColorDialog
            c = QColorDialog.getColor()
            if c.isValid():
                self._rol_color = c.name()
                btn_color.setStyleSheet(f"background:{self._rol_color};color:white;")
        btn_color.clicked.connect(pick_color)
        form.addRow("Nombre *:", txt_nombre)
        form.addRow("Hora inicio:", te_inicio)
        form.addRow("Hora fin:", te_fin)
        form.addRow("Color:", btn_color)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec_() != QDialog.Accepted: return
        nombre = txt_nombre.text().strip()
        if not nombre: return
        try:
            conn = self.container.db if hasattr(self,'container') else self.conexion
            conn.execute(
                "INSERT INTO turno_roles(nombre,hora_inicio,hora_fin,color) VALUES(?,?,?,?)",
                (nombre, te_inicio.time().toString("HH:mm"),
                 te_fin.time().toString("HH:mm"), self._rol_color))
            try: conn.commit()
            except Exception: pass
            self._cargar_roles_turno()
        except Exception as e:
            QMessageBox.critical(self,"Error",str(e))

    def _eliminar_rol_turno(self):
        # [spj-dedup removed local QMessageBox import]
        row = self._tbl_roles_turno.currentRow()
        if row < 0: return
        rid = int(self._tbl_roles_turno.item(row,0).text())
        if QMessageBox.question(self,"Confirmar","¿Eliminar este rol?",
           QMessageBox.Yes|QMessageBox.No) != QMessageBox.Yes: return
        conn = self.container.db if hasattr(self,'container') else self.conexion
        conn.execute("DELETE FROM turno_roles WHERE id=?", (rid,))
        try: conn.commit()
        except Exception: pass
        self._cargar_roles_turno()

    # ── v13.30: Integración completa del módulo de Turnos ─────────────────────
    def _setup_tab_turnos_completo(self):
        """Embebe el ModuloRRHHTurnos completo dentro de la tab de turnos."""
        from PyQt5.QtWidgets import QVBoxLayout, QLabel
        lay = QVBoxLayout(self.tab_roles_turno)
        lay.setContentsMargins(0, 0, 0, 0)
        try:
            from modulos.rrhh_turnos import ModuloRRHHTurnos
            self._turnos_widget = ModuloRRHHTurnos(
                container=self.container, parent=self.tab_roles_turno)
            lay.addWidget(self._turnos_widget)
        except Exception as e:
            lbl = QLabel(f"Error cargando módulo de turnos:\n{e}")
            lbl.setObjectName("dangerText")  # Usar clase CSS para texto de error
            lbl.setStyleSheet(f"font-size: {Typography.SIZE_SM}; padding: {Spacing.LG};")
            lay.addWidget(lbl)

    def _on_rrhh_tab_change(self, idx):
        if idx == 0: self.cargar_tabla_empleados()
        elif idx == 1: self._cargar_asistencias()
        elif idx == 2: self.cargar_lista_empleados()
        elif idx == 6:  # Tab Turnos
            if hasattr(self, '_turnos_widget'):
                try: self._turnos_widget._cargar()
                except Exception: pass

    # =========================================================
    # PESTAÑA 1: DIRECTORIO DE PERSONAL (CRUD)
    # =========================================================
    def setup_tab_empleados(self):
        layout = QVBoxLayout(self.tab_empleados)
        
        # Barra de herramientas
        toolbar = QHBoxLayout()
        btn_nuevo = create_success_button(self, "➕ Contratar / Nuevo Empleado", "Registrar nuevo empleado en el sistema")
        btn_nuevo.clicked.connect(self.abrir_nuevo_empleado)
        
        btn_refrescar = QPushButton("🔄 Refrescar")
        btn_refrescar.setObjectName("secondaryBtn")
        btn_refrescar.clicked.connect(self.cargar_tabla_empleados)
        
        toolbar.addWidget(btn_nuevo)
        toolbar.addWidget(btn_refrescar)
        toolbar.addStretch()
        layout.addLayout(toolbar)
        
        # Tabla de Empleados
        self.tabla_emp = QTableWidget()
        self.tabla_emp.setColumnCount(7)
        self.tabla_emp.setHorizontalHeaderLabels(["ID", "Nombre Completo", "Puesto", "Teléfono", "Salario Base", "Acciones", ""])
        self.tabla_emp.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tabla_emp.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla_emp.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.tabla_emp)
        
        self.cargar_tabla_empleados()

    def cargar_tabla_empleados(self):
        self.tabla_emp.setRowCount(0)
        try:
            cursor = self.container.db.cursor()
            # Solo mostramos a los empleados activos
            rows = cursor.execute("SELECT * FROM personal WHERE activo = 1 ORDER BY nombre LIMIT 500").fetchall()
            
            for row_idx, emp in enumerate(rows):
                self.tabla_emp.insertRow(row_idx)
                
                nombre_completo = f"{emp['nombre']} {emp['apellidos'] or ''}".strip()
                
                self.tabla_emp.setItem(row_idx, 0, QTableWidgetItem(str(emp['id'])))
                self.tabla_emp.setItem(row_idx, 1, QTableWidgetItem(nombre_completo))
                self.tabla_emp.setItem(row_idx, 2, QTableWidgetItem(emp['puesto'] or ''))
                self.tabla_emp.setItem(row_idx, 3, QTableWidgetItem(emp['telefono'] or ''))
                self.tabla_emp.setItem(row_idx, 4, QTableWidgetItem(f"${emp['salario']:,.2f}"))
                
                # Botón Editar
                btn_editar = QPushButton("✏️ Editar")
                btn_editar.setObjectName("warningBtn")  # Naranja para edición
                btn_editar.clicked.connect(lambda _, eid=emp['id']: self.abrir_editar_empleado(eid))
                apply_tooltip(btn_editar, f"Editar datos de {nombre_completo}")
                self.tabla_emp.setCellWidget(row_idx, 5, btn_editar)
                
                # Botón Eliminar (Dar de Baja)
                btn_baja = create_danger_button(self, "❌ Dar de Baja", f"Dar de baja a {nombre_completo}")
                btn_baja.clicked.connect(lambda _, eid=emp['id'], nom=nombre_completo: self.dar_baja_empleado(eid, nom))
                self.tabla_emp.setCellWidget(row_idx, 6, btn_baja)
                
        except Exception as e:
            logger.error(f"Error cargando personal: {e}")

    def abrir_nuevo_empleado(self):
        dlg = DialogoEmpleado(self.container.db, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self.cargar_tabla_empleados()
            self.cargar_lista_empleados() # Refresca el combo de la pestaña de nómina

    def abrir_editar_empleado(self, empleado_id):
        dlg = DialogoEmpleado(self.container.db, empleado_id=empleado_id, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self.cargar_tabla_empleados()
            self.cargar_lista_empleados()

    def dar_baja_empleado(self, empleado_id, nombre):
        """SOFT DELETE: No lo borramos, solo lo marcamos como inactivo."""
        resp = QMessageBox.question(
            self, "Confirmar Baja", 
            f"¿Está seguro de dar de baja a '{nombre}'?\n\n"
            f"El empleado ya no aparecerá en los cálculos de nómina, pero su historial de pagos se conservará.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if resp == QMessageBox.Yes:
            try:
                cursor = self.container.db.cursor()
                cursor.execute("UPDATE personal SET activo = 0 WHERE id = ?", (empleado_id,))
                self.container.db.commit()
                
                # Auditoría Enterprise
                if hasattr(self.container, 'audit_service'):
                    self.container.audit_service.log_change(
                        usuario=self.usuario_actual, accion="BAJA_EMPLEADO", 
                        modulo="RRHH", entidad="personal", entidad_id=str(empleado_id)
                    )
                
                QMessageBox.information(self, "Baja Exitosa", "El empleado ha sido dado de baja.")
                self.cargar_tabla_empleados()
                self.cargar_lista_empleados() # Actualiza el combobox de la pestaña de nómina
                
            except Exception as e:
                self.container.db.rollback()
                QMessageBox.critical(self, "Error", f"No se pudo procesar la baja: {e}")

    def setup_tab_nomina(self):
        layout = QVBoxLayout(self.tab_nomina)
        
        # Filtros de Nómina
        filtros = QHBoxLayout()
        self.cmb_empleado = QComboBox()
        self.cmb_empleado.setObjectName("inputField")
        
        btn_calcular = create_success_button(self, "🧮 Calcular Nómina del Periodo", "Calcular la nómina completa del periodo seleccionado")
        btn_calcular.clicked.connect(self.ejecutar_calculo_nomina)
        
        filtros.addWidget(QLabel("Seleccionar Empleado:"))
        filtros.addWidget(self.cmb_empleado, 1)
        filtros.addWidget(btn_calcular)
        layout.addLayout(filtros)
        
        # Panel de Resultados (Recibo Visual)
        self.panel_recibo = QGroupBox("Resumen de Nómina")
        self.panel_recibo.setObjectName("styledGroup")
        recibo_layout = QFormLayout(self.panel_recibo)
        
        self.lbl_nom_empleado = QLabel("-")
        self.lbl_dias = QLabel("0")
        self.lbl_horas = QLabel("0.0")
        self.lbl_total_pago = QLabel("$0.00")
        self.lbl_total_pago.setObjectName("textSuccess")
        self.lbl_total_pago.setStyleSheet(f"font-size: {Typography.SIZE_24}; font-weight: bold;")
        
        recibo_layout.addRow("Nombre Completo:", self.lbl_nom_empleado)
        recibo_layout.addRow("Días Asistidos:", self.lbl_dias)
        recibo_layout.addRow("Total Horas Trabajadas:", self.lbl_horas)
        recibo_layout.addRow("Neto a Pagar:", self.lbl_total_pago)
        layout.addWidget(self.panel_recibo)
        
        # Botones de Acción Final
        acciones = QHBoxLayout()
        self.cmb_metodo_pago = QComboBox()
        self.cmb_metodo_pago.setObjectName("inputField")
        self.cmb_metodo_pago.addItems(["Transferencia", "Efectivo (De Caja)"])
        
        self.btn_pagar = create_success_button(self, "💸 APROBAR PAGO Y ENVIAR WHATSAPP", "Aprobar el pago y enviar comprobante por WhatsApp")
        self.btn_pagar.clicked.connect(self.aprobar_y_pagar)
        self.btn_pagar.setEnabled(False)
        self.btn_pagar.setStyleSheet(f"padding: {Spacing.LG}; font-weight: bold;")
        
        acciones.addWidget(QLabel("Método de Pago:"))
        acciones.addWidget(self.cmb_metodo_pago)
        acciones.addStretch()
        acciones.addWidget(self.btn_pagar)
        layout.addLayout(acciones)
        layout.addStretch()

        self.nomina_actual = None # Guarda los datos calculados en memoria

    def cargar_lista_empleados(self):
        self.cmb_empleado.clear()
        try:
            cursor = self.container.db.cursor()
            rows = cursor.execute("SELECT id, nombre, COALESCE(apellidos,'') as apellidos FROM personal WHERE activo = 1").fetchall()
            for row in rows:
                self.cmb_empleado.addItem(f"{row['nombre']} {row['apellidos']}", row['id'])
        except Exception: pass

    def ejecutar_calculo_nomina(self):
        empleado_id = self.cmb_empleado.currentData()
        if not empleado_id: return
        
        # Calcular periodo (Ejemplo: Últimos 7 días)
        fin = datetime.now()
        inicio = fin - timedelta(days=7)
        
        try:
            # 🚀 LLAMADA ENTERPRISE: El servicio calcula las horas y el dinero
            if hasattr(self.container, 'rrhh_service'):
                datos = self.container.rrhh_service.calcular_nomina(
                    empleado_id, inicio.strftime("%Y-%m-%d"), fin.strftime("%Y-%m-%d")
                )
                
                # Actualizar el recibo visual
                self.lbl_nom_empleado.setText(datos['nombre_completo'])
                self.lbl_dias.setText(str(datos['dias_asistidos']))
                self.lbl_horas.setText(f"{datos['total_horas']:.2f}")
                self.lbl_total_pago.setText(f"${datos['neto_a_pagar']:,.2f}")
                
                self.nomina_actual = datos
                self.btn_pagar.setEnabled(True)
            else:
                QMessageBox.warning(self, "Aviso", "RRHHService no está conectado.")
        except Exception as e:
            QMessageBox.critical(self, "Error de Cálculo", str(e))

    def aprobar_y_pagar(self):
        if not self.nomina_actual: return
        
        metodo = self.cmb_metodo_pago.currentText()
        msg = (f"¿Aprobar el pago de ${self.nomina_actual['neto_a_pagar']:,.2f} a {self.nomina_actual['nombre_completo']}?\n\n"
               f"Esto restará el dinero contablemente de los OPEX y enviará el recibo por WhatsApp.")
               
        if QMessageBox.question(self, "Confirmar Pago", msg) == QMessageBox.Yes:
            try:
                # 🚀 LLAMADA ENTERPRISE: Registra el OPEX, genera PDF y envía WhatsApp
                mensaje_exito = self.container.rrhh_service.procesar_pago_nomina(
                    datos_nomina=self.nomina_actual,
                    metodo_pago=metodo,
                    sucursal_id=self.sucursal_id,
                    admin_user=self.usuario_actual
                )
                
                QMessageBox.information(self, "Nómina Procesada", mensaje_exito)
                
                # Resetear interfaz
                self.nomina_actual = None
                self.lbl_nom_empleado.setText("-")
                self.lbl_total_pago.setText("$0.00")
                self.btn_pagar.setEnabled(False)
                
            except Exception as e:
                QMessageBox.critical(self, "Error Crítico", str(e))
    # ══════════════════════════════════════════════════════════════
    # TAB: 📅 ASISTENCIAS
    # ══════════════════════════════════════════════════════════════
    def setup_tab_asistencias(self):
        from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QFormLayout,
            QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
            QAbstractItemView, QComboBox, QDateEdit, QMessageBox)
        from PyQt5.QtCore import Qt, QDate

        lay = QVBoxLayout(self.tab_asistencias)

        # Controles
        ctrl = QHBoxLayout()
        self.cmb_asist_empleado = QComboBox(); self.cmb_asist_empleado.setMinimumWidth(200)
        self.cmb_asist_empleado.setObjectName("inputField")
        
        self.date_asist_desde   = QDateEdit(QDate.currentDate().addDays(-30))
        self.date_asist_desde.setCalendarPopup(True)
        self.date_asist_desde.setObjectName("inputField")
        
        self.date_asist_hasta   = QDateEdit(QDate.currentDate())
        self.date_asist_hasta.setCalendarPopup(True)
        self.date_asist_hasta.setObjectName("inputField")
        
        btn_buscar = create_primary_button(self, "🔍 Buscar", "Buscar asistencias en el rango de fechas")
        btn_buscar.clicked.connect(self._cargar_asistencias)
        
        btn_registro = create_success_button(self, "✅ Registrar entrada/salida", "Registrar asistencia del empleado seleccionado")
        btn_registro.clicked.connect(self._registrar_asistencia)
        
        ctrl.addWidget(QLabel("Empleado:")); ctrl.addWidget(self.cmb_asist_empleado)
        ctrl.addWidget(QLabel("Desde:")); ctrl.addWidget(self.date_asist_desde)
        ctrl.addWidget(QLabel("Hasta:")); ctrl.addWidget(self.date_asist_hasta)
        ctrl.addWidget(btn_buscar); ctrl.addStretch(); ctrl.addWidget(btn_registro)
        lay.addLayout(ctrl)

        self.tbl_asist = QTableWidget(); self.tbl_asist.setColumnCount(6)
        self.tbl_asist.setHorizontalHeaderLabels(
            ["Empleado","Fecha","Entrada","Salida","Horas","Estado"])
        hh = self.tbl_asist.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1,2,3,4,5): hh.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.tbl_asist.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_asist.verticalHeader().setVisible(False)
        self.tbl_asist.setAlternatingRowColors(True)
        self.tbl_asist.setObjectName("tableView")
        lay.addWidget(self.tbl_asist)

        # Summary
        self.lbl_asist_resumen = QLabel("")
        self.lbl_asist_resumen.setObjectName("caption")
        self.lbl_asist_resumen.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: {Typography.SIZE_XS}; padding: {Spacing.XS};")
        lay.addWidget(self.lbl_asist_resumen)
        self._cargar_combo_asistencias()

    def _cargar_combo_asistencias(self):
        try:
            rows = self.container.db.execute(
                "SELECT id, nombre||' '||COALESCE(apellidos,'') FROM personal "
                "WHERE activo=1 ORDER BY nombre"
            ).fetchall()
            self.cmb_asist_empleado.clear()
            self.cmb_asist_empleado.addItem("Todos", None)
            for r in rows:
                self.cmb_asist_empleado.addItem(r[1].strip(), r[0])
        except Exception:
            pass

    def _cargar_asistencias(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        from PyQt5.QtCore import Qt
        emp_id = self.cmb_asist_empleado.currentData()
        desde  = self.date_asist_desde.date().toString("yyyy-MM-dd")
        hasta  = self.date_asist_hasta.date().toString("yyyy-MM-dd")
        try:
            query = """
                SELECT p.nombre||' '||COALESCE(p.apellidos,''),
                       a.fecha, a.hora_entrada, a.hora_salida,
                       ROUND(COALESCE(a.horas_trabajadas,0),2), a.estado
                FROM asistencias a
                JOIN personal p ON p.id=a.personal_id
                WHERE a.fecha BETWEEN ? AND ?
            """
            params = [desde, hasta]
            if emp_id:
                query += " AND a.personal_id=?"; params.append(emp_id)
            query += " ORDER BY a.fecha DESC, p.nombre LIMIT 300"
            rows = self.container.db.execute(query, params).fetchall()
        except Exception: rows = []

        self.tbl_asist.setRowCount(len(rows))
        total_horas = 0
        for ri, r in enumerate(rows):
            for ci, v in enumerate(r):
                it = QTableWidgetItem(str(v) if v is not None else "—")
                it.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)
                self.tbl_asist.setItem(ri, ci, it)
            try: total_horas += float(r[4] or 0)
            except Exception: pass

        self.lbl_asist_resumen.setText(
            f"{len(rows)} registros | Total horas: {total_horas:.1f}h")

    def _registrar_asistencia(self):
        """Registra entrada o salida segun el estado actual del empleado."""
        from PyQt5.QtWidgets import (QDialog, QFormLayout, QComboBox,
            QDialogButtonBox, QVBoxLayout, QMessageBox, QLabel)
        from PyQt5.QtCore import QDate, QTime
        from datetime import datetime, date as _date

        # Choose employee
        dlg = QDialog(self); dlg.setWindowTitle("Registro Asistencia"); dlg.setMinimumWidth(340)
        lay = QVBoxLayout(dlg); form = QFormLayout()
        cmb_emp = QComboBox()
        cmb_emp.setObjectName("inputField")
        try:
            rows = self.container.db.execute(
                "SELECT id, nombre||' '||COALESCE(apellidos,'') FROM personal WHERE activo=1 ORDER BY nombre"
            ).fetchall()
            for r in rows: cmb_emp.addItem(r[1].strip(), r[0])
        except Exception: pass
        form.addRow("Empleado:", cmb_emp)
        lbl_status = QLabel(""); form.addRow("Estado:", lbl_status)
        lbl_status.setObjectName("caption")
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setObjectName("primaryBtn")
        btns.button(QDialogButtonBox.Cancel).setObjectName("secondaryBtn")
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        def _update_status():
            emp_id = cmb_emp.currentData()
            if not emp_id: return
            hoy = str(_date.today())
            row = self.container.db.execute(
                "SELECT hora_entrada, hora_salida FROM asistencias WHERE personal_id=? AND fecha=?",
                (emp_id, hoy)
            ).fetchone()
            if not row:
                lbl_status.setText("Sin registro hoy — se registrará ENTRADA")
                lbl_status.setStyleSheet(f"color: {Colors.SUCCESS_BASE}; font-weight: bold;")
            elif row[0] and not row[1]:
                lbl_status.setText(f"Entrada: {row[0]} — se registrará SALIDA")
                lbl_status.setStyleSheet(f"color: {Colors.WARNING_BASE}; font-weight: bold;")
            else:
                lbl_status.setText(f"Jornada completa: {row[0]}-{row[1]}")
                lbl_status.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
        cmb_emp.currentIndexChanged.connect(_update_status)
        _update_status()

        if dlg.exec_() != QDialog.Accepted: return
        emp_id = cmb_emp.currentData()
        if not emp_id: return
        hoy  = str(_date.today())
        hora = datetime.now().strftime("%H:%M")

        try:
            row = self.container.db.execute(
                "SELECT id, hora_entrada, hora_salida FROM asistencias WHERE personal_id=? AND fecha=?",
                (emp_id, hoy)
            ).fetchone()
            if not row:
                # New check-in
                self.container.db.execute(
                    "INSERT INTO asistencias(personal_id,fecha,hora_entrada,estado) VALUES(?,?,?,'PRESENTE')",
                    (emp_id, hoy, hora))
                msg = f"✅ Entrada registrada: {hora}"
            elif row[1] and not row[2]:
                # Check-out
                t1 = datetime.strptime(row[1], "%H:%M")
                t2 = datetime.strptime(hora, "%H:%M")
                horas = max(0, (t2-t1).seconds/3600)
                self.container.db.execute(
                    "UPDATE asistencias SET hora_salida=?, horas_trabajadas=? WHERE id=?",
                    (hora, round(horas,2), row[0]))
                msg = f"✅ Salida registrada: {hora} ({horas:.1f}h)"
            else:
                QMessageBox.information(self,"Info","Jornada ya completa para hoy."); return
            try: self.container.db.commit()
            except Exception: pass
            try: get_bus().publish("EMPLEADO_ACTUALIZADO", {"event_type": "EMPLEADO_ACTUALIZADO"})
            except Exception: pass
            except Exception: pass
            QMessageBox.information(self,"Asistencia", msg)
            self._cargar_asistencias()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
        return
    def _registrar_asistencia_ORIG(self):
        from PyQt5.QtWidgets import (QDialog, QFormLayout, QComboBox, QDialogButtonBox,
                                      QVBoxLayout, QDateEdit, QTimeEdit, QComboBox,
                                      QMessageBox)
        from PyQt5.QtCore import QDate, QTime, Qt
        from datetime import datetime

        dlg = QDialog(self); dlg.setWindowTitle("Registrar Asistencia"); dlg.setMinimumWidth(360)
        lay = QVBoxLayout(dlg); form = QFormLayout()
        cmb_emp    = QComboBox()
        date_edit  = QDateEdit(QDate.currentDate()); date_edit.setCalendarPopup(True)
        time_ent   = QTimeEdit(QTime.currentTime())
        time_sal   = QTimeEdit(); time_sal.setTime(QTime(0,0))
        cmb_estado = QComboBox(); cmb_estado.addItems(["PRESENTE","TARDANZA","FALTA","PERMISO"])

        try:
            rows = self.container.db.execute(
                "SELECT id, nombre||' '||COALESCE(apellidos,'') FROM personal "
                "WHERE activo=1 ORDER BY nombre"
            ).fetchall()
            for r in rows: cmb_emp.addItem(r[1].strip(), r[0])
        except Exception: pass

        form.addRow("Empleado:", cmb_emp)
        form.addRow("Fecha:", date_edit)
        form.addRow("Hora entrada:", time_ent)
        form.addRow("Hora salida:", time_sal)
        form.addRow("Estado:", cmb_estado)
        lay.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec_() != QDialog.Accepted: return

        emp_id = cmb_emp.currentData()
        if not emp_id: return
        fecha   = date_edit.date().toString("yyyy-MM-dd")
        h_ent   = time_ent.time().toString("HH:mm")
        h_sal   = time_sal.time().toString("HH:mm") if time_sal.time() != QTime(0,0) else None
        horas   = None
        if h_sal:
            try:
                t1 = datetime.strptime(h_ent, "%H:%M")
                t2 = datetime.strptime(h_sal, "%H:%M")
                horas = max(0, (t2-t1).seconds/3600)
            except Exception: pass
        estado = cmb_estado.currentText()
        try:
            self.container.db.execute(
                "INSERT OR REPLACE INTO asistencias"
                "(personal_id,fecha,hora_entrada,hora_salida,horas_trabajadas,estado) "
                "VALUES(?,?,?,?,?,?)",
                (emp_id, fecha, h_ent, h_sal, horas, estado))
            try: self.container.db.commit()
            except Exception: pass
            self._cargar_asistencias()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ══════════════════════════════════════════════════════════════
    # TAB: 🏖️ VACACIONES
    # ══════════════════════════════════════════════════════════════
    def setup_tab_vacaciones(self):
        from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
            QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView)
        from PyQt5.QtCore import Qt
        lay = QVBoxLayout(self.tab_vacaciones)
        hdr = QHBoxLayout()
        hdr.addWidget(create_heading(self, "Registro de vacaciones y permisos"))
        hdr.addStretch()
        btn_nuevo = create_primary_button(self, "➕ Registrar vacaciones", "Agregar nuevo registro de vacaciones o permiso")
        btn_nuevo.clicked.connect(self._registrar_vacaciones)
        hdr.addWidget(btn_nuevo)
        lay.addLayout(hdr)

        self.tbl_vac = QTableWidget(); self.tbl_vac.setColumnCount(7)
        self.tbl_vac.setHorizontalHeaderLabels(
            ["ID","Empleado","Tipo","Desde","Hasta","Días","Estado"])
        hh = self.tbl_vac.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        self.tbl_vac.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_vac.verticalHeader().setVisible(False)
        self.tbl_vac.setAlternatingRowColors(True)
        self.tbl_vac.setObjectName("tableView")
        lay.addWidget(self.tbl_vac)
        self._cargar_vacaciones()

        # Approval buttons
        from PyQt5.QtWidgets import QHBoxLayout
        btn_ap_lay = QHBoxLayout()
        btn_aprobar  = create_success_button(self, "✅ Aprobar", "Aprobar solicitud de vacaciones seleccionada")
        btn_rechazar = create_danger_button(self, "❌ Rechazar", "Rechazar solicitud de vacaciones seleccionada")
        btn_aprobar.clicked.connect(lambda: self._cambiar_estado_vac("aprobado"))
        btn_rechazar.clicked.connect(lambda: self._cambiar_estado_vac("rechazado"))
        btn_ap_lay.addWidget(btn_aprobar); btn_ap_lay.addWidget(btn_rechazar); btn_ap_lay.addStretch()
        lay.addLayout(btn_ap_lay)

    def setup_tab_puestos(self):
        from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QTableWidget,
            QTableWidgetItem, QPushButton, QHeaderView, QAbstractItemView,
            QDialog, QFormLayout, QLineEdit, QTextEdit, QDialogButtonBox, QLabel)
        from PyQt5.QtCore import Qt
        lay = QVBoxLayout(self.tab_puestos)

        hdr = QHBoxLayout()
        hdr.addWidget(create_heading(self, "Catálogo de puestos de trabajo"))
        hdr.addStretch()
        btn_nuevo  = create_success_button(self, "➕ Nuevo puesto", "Crear nuevo puesto de trabajo")
        btn_editar = create_warning_button(self, "✏️ Editar", "Editar puesto seleccionado")
        btn_borrar = create_danger_button(self, "🗑️ Eliminar", "Eliminar puesto seleccionado")
        hdr.addWidget(btn_nuevo); hdr.addWidget(btn_editar); hdr.addWidget(btn_borrar)
        lay.addLayout(hdr)

        self.tbl_puestos = QTableWidget(); self.tbl_puestos.setColumnCount(3)
        self.tbl_puestos.setHorizontalHeaderLabels(["ID","Puesto","Descripción"])
        self.tbl_puestos.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tbl_puestos.setColumnHidden(0, True)
        self.tbl_puestos.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_puestos.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl_puestos.setObjectName("tableView")
        lay.addWidget(self.tbl_puestos)

        def _cargar():
            try:
                self.container.db.execute(
                    "CREATE TABLE IF NOT EXISTS puestos("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                    "nombre TEXT NOT NULL UNIQUE,"
                    "descripcion TEXT,"
                    "activo INTEGER DEFAULT 1)"
                )
                rows = self.container.db.execute(
                    "SELECT id,nombre,COALESCE(descripcion,'') FROM puestos WHERE activo=1 ORDER BY nombre"
                ).fetchall()
            except Exception: rows = []
            self.tbl_puestos.setRowCount(0)
            for i, r in enumerate(rows):
                self.tbl_puestos.insertRow(i)
                for j, v in enumerate(r):
                    self.tbl_puestos.setItem(i, j, QTableWidgetItem(str(v) if v else ""))

        def _dialogo(puesto_id=None):
            d = QDialog(self); d.setWindowTitle("Puesto"); d.setMinimumWidth(360)
            lay2 = QVBoxLayout(d); form = QFormLayout()
            txt_nombre = QLineEdit(); txt_desc = QTextEdit(); txt_desc.setMaximumHeight(80)
            if puesto_id:
                row = self.container.db.execute(
                    "SELECT nombre,descripcion FROM puestos WHERE id=?", (puesto_id,)
                ).fetchone()
                if row: txt_nombre.setText(row[0] or ""); txt_desc.setPlainText(row[1] or "")
            form.addRow("Nombre *:", txt_nombre); form.addRow("Descripción:", txt_desc)
            lay2.addLayout(form)
            btns = QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
            btns.accepted.connect(d.accept); btns.rejected.connect(d.reject)
            lay2.addWidget(btns)
            if d.exec_() != QDialog.Accepted: return
            nombre = txt_nombre.text().strip()
            if not nombre: return
            desc = txt_desc.toPlainText().strip()
            try:
                if puesto_id:
                    self.container.db.execute(
                        "UPDATE puestos SET nombre=?,descripcion=? WHERE id=?",
                        (nombre, desc, puesto_id))
                else:
                    self.container.db.execute(
                        "INSERT INTO puestos(nombre,descripcion) VALUES(?,?)", (nombre, desc))
                try: self.container.db.commit()
                except Exception: pass
                _cargar()
            except Exception as e:
        # [spj-dedup removed local QMessageBox import]
                QMessageBox.critical(self,"Error",str(e))

        def _borrar():
        # [spj-dedup removed local QMessageBox import]
            row = self.tbl_puestos.currentRow()
            if row < 0: return
            pid  = int(self.tbl_puestos.item(row,0).text())
            if QMessageBox.question(self,"Confirmar","¿Eliminar puesto?",
               QMessageBox.Yes|QMessageBox.No) != QMessageBox.Yes: return
            self.container.db.execute("UPDATE puestos SET activo=0 WHERE id=?", (pid,))
            try: self.container.db.commit()
            except Exception: pass
            _cargar()

        btn_nuevo.clicked.connect(lambda: _dialogo())
        btn_editar.clicked.connect(lambda: _dialogo(
            int(self.tbl_puestos.item(self.tbl_puestos.currentRow(),0).text())
            if self.tbl_puestos.currentRow() >= 0 else None))
        btn_borrar.clicked.connect(_borrar)
        _cargar()

    def _cambiar_estado_vac(self, nuevo_estado: str) -> None:
        # [spj-dedup removed local QMessageBox import]
        row = self.tbl_vac.currentRow()
        if row < 0:
            QMessageBox.warning(self,"Aviso","Selecciona un registro de vacaciones."); return
        vac_id_item = self.tbl_vac.item(row, 0)
        if not vac_id_item: return
        vac_id = int(vac_id_item.text())
        try:
            self.container.db.execute(
                "UPDATE vacaciones_personal SET estado=? WHERE id=?", (nuevo_estado, vac_id))
            try: self.container.db.commit()
            except Exception: pass
            self._cargar_vacaciones()
        except Exception as e:
            QMessageBox.critical(self,"Error", str(e))

    def _cargar_vacaciones(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        from PyQt5.QtCore import Qt
        try:
            # Ensure table exists
            self.container.db.execute("""
                CREATE TABLE IF NOT EXISTS vacaciones_personal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    personal_id INTEGER NOT NULL,
                    tipo TEXT DEFAULT 'vacaciones',
                    fecha_inicio DATE NOT NULL,
                    fecha_fin DATE NOT NULL,
                    dias INTEGER DEFAULT 1,
                    estado TEXT DEFAULT 'aprobado',
                    notas TEXT,
                    fecha_registro DATETIME DEFAULT (datetime('now'))
                )
            """)
            rows = self.container.db.execute("""
                SELECT v.id, p.nombre||' '||COALESCE(p.apellidos,''),
                       v.tipo, v.fecha_inicio, v.fecha_fin, v.dias, v.estado
                FROM vacaciones_personal v
                JOIN personal p ON p.id=v.personal_id
                ORDER BY v.fecha_inicio DESC LIMIT 200
            """).fetchall()
        except Exception: rows = []
        self.tbl_vac.setRowCount(len(rows))
        for ri, r in enumerate(rows):
            for ci, v in enumerate(r):
                it = QTableWidgetItem(str(v) if v else "")
                it.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)
                self.tbl_vac.setItem(ri, ci, it)

    def _registrar_vacaciones(self):
        from PyQt5.QtWidgets import (QDialog, QFormLayout, QComboBox, QDialogButtonBox,
                                      QVBoxLayout, QDateEdit, QSpinBox, QMessageBox)
        from PyQt5.QtCore import QDate
        dlg = QDialog(self); dlg.setWindowTitle("Vacaciones/Permiso"); dlg.setMinimumWidth(360)
        lay = QVBoxLayout(dlg); form = QFormLayout()
        cmb_emp  = QComboBox(); cmb_tipo = QComboBox()
        cmb_tipo.addItems(["vacaciones","permiso","incapacidad","día personal"])
        date_ini = QDateEdit(QDate.currentDate()); date_ini.setCalendarPopup(True)
        date_fin = QDateEdit(QDate.currentDate().addDays(5)); date_fin.setCalendarPopup(True)
        cmb_est  = QComboBox(); cmb_est.addItems(["aprobado","pendiente","rechazado"])
        try:
            rows = self.container.db.execute(
                "SELECT id, nombre||' '||COALESCE(apellidos,'') FROM personal "
                "WHERE activo=1 ORDER BY nombre"
            ).fetchall()
            for r in rows: cmb_emp.addItem(r[1].strip(), r[0])
        except Exception: pass
        form.addRow("Empleado:", cmb_emp); form.addRow("Tipo:", cmb_tipo)
        form.addRow("Desde:", date_ini); form.addRow("Hasta:", date_fin)
        form.addRow("Estado:", cmb_est)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec_() != QDialog.Accepted: return
        emp_id = cmb_emp.currentData()
        if not emp_id: return
        d_ini = date_ini.date().toPyDate()
        d_fin = date_fin.date().toPyDate()
        dias  = max(1, (d_fin - d_ini).days + 1)
        try:
            self.container.db.execute(
                "INSERT INTO vacaciones_personal"
                "(personal_id,tipo,fecha_inicio,fecha_fin,dias,estado) VALUES(?,?,?,?,?,?)",
                (emp_id, cmb_tipo.currentText(), str(d_ini), str(d_fin), dias, cmb_est.currentText()))
            try: self.container.db.commit()
            except Exception: pass
            self._cargar_vacaciones()
        except Exception as e:
        # [spj-dedup removed local QMessageBox import]
            QMessageBox.critical(self, "Error", str(e))

    # ══════════════════════════════════════════════════════════════
    # TAB: ⭐ EVALUACIONES
    # ══════════════════════════════════════════════════════════════
    def setup_tab_evaluaciones(self):
        from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
            QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView)
        from PyQt5.QtCore import Qt
        lay = QVBoxLayout(self.tab_evaluaciones)
        hdr = QHBoxLayout()
        hdr.addWidget(create_heading(self, "Evaluaciones de desempeño del personal"))
        hdr.addStretch()
        btn_nuevo = create_accent_button(self, "➕ Nueva evaluación", "Crear nueva evaluación de desempeño")
        btn_nuevo.clicked.connect(self._nueva_evaluacion)
        hdr.addWidget(btn_nuevo)
        lay.addLayout(hdr)

        self.tbl_eval_rrhh = QTableWidget(); self.tbl_eval_rrhh.setColumnCount(5)
        self.tbl_eval_rrhh.setHorizontalHeaderLabels(
            ["Empleado","Período","Calificación","Evaluador","Fecha"])
        hh = self.tbl_eval_rrhh.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        self.tbl_eval_rrhh.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl_eval_rrhh.verticalHeader().setVisible(False)
        self.tbl_eval_rrhh.setAlternatingRowColors(True)
        self.tbl_eval_rrhh.setObjectName("tableView")
        lay.addWidget(self.tbl_eval_rrhh)
        self._cargar_evaluaciones_rrhh()

    def _cargar_evaluaciones_rrhh(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        from PyQt5.QtCore import Qt
        try:
            rows = self.container.db.execute("""
                SELECT p.nombre||' '||COALESCE(p.apellidos,''),
                       e.periodo, e.calificacion, e.evaluador, e.fecha
                FROM evaluaciones_personal e
                JOIN personal p ON p.id=e.personal_id
                ORDER BY e.fecha DESC LIMIT 200
            """).fetchall()
        except Exception: rows = []
        self.tbl_eval_rrhh.setRowCount(len(rows))
        for ri, r in enumerate(rows):
            for ci, v in enumerate(r):
                it = QTableWidgetItem(str(v) if v else "")
                it.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)
                self.tbl_eval_rrhh.setItem(ri, ci, it)

    def _nueva_evaluacion(self):
        from PyQt5.QtWidgets import (QDialog, QFormLayout, QComboBox, QDialogButtonBox,
                                      QVBoxLayout, QSpinBox, QLineEdit, QMessageBox)
        dlg = QDialog(self); dlg.setWindowTitle("Nueva Evaluación"); dlg.setMinimumWidth(360)
        lay = QVBoxLayout(dlg); form = QFormLayout()
        cmb_emp  = QComboBox()
        txt_per  = QLineEdit(); txt_per.setPlaceholderText("Ej: 2025-Q1")
        spin_cal = QSpinBox(); spin_cal.setRange(1,10); spin_cal.setValue(8)
        txt_eva  = QLineEdit(); txt_eva.setText(self.usuario_actual or "")
        try:
            rows = self.container.db.execute(
                "SELECT id, nombre||' '||COALESCE(apellidos,'') FROM personal "
                "WHERE activo=1 ORDER BY nombre"
            ).fetchall()
            for r in rows: cmb_emp.addItem(r[1].strip(), r[0])
        except Exception: pass
        form.addRow("Empleado:", cmb_emp); form.addRow("Período:", txt_per)
        form.addRow("Calificación (1-10):", spin_cal); form.addRow("Evaluador:", txt_eva)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec_() != QDialog.Accepted: return
        emp_id = cmb_emp.currentData()
        if not emp_id: return
        try:
            self.container.db.execute(
                "INSERT INTO evaluaciones_personal(personal_id,periodo,calificacion,evaluador,fecha) "
                "VALUES(?,?,?,?,date('now'))",
                (emp_id, txt_per.text().strip(), spin_cal.value(), txt_eva.text().strip()))
            try: self.container.db.commit()
            except Exception: pass
            self._cargar_evaluaciones_rrhh()
        except Exception as e:
        # [spj-dedup removed local QMessageBox import]
            QMessageBox.critical(self, "Error", str(e))

    # ══════════════════════════════════════════════════════════════
    # RECIBO DE NÓMINA PDF
    # ══════════════════════════════════════════════════════════════
    def generar_recibo_nomina_pdf(self, pago_id: int = None, empleado_id: int = None):
        """Genera un recibo de nómina en PDF para el empleado."""
        # [spj-dedup removed local QMessageBox import]
        try:
            # Obtener datos del pago o el último pago del empleado
            if pago_id:
                row = self.container.db.execute(
                    "SELECT np.*, p.nombre, p.apellidos, p.puesto, p.rfc "
                    "FROM nomina_pagos np JOIN personal p ON p.id=np.empleado_id "
                    "WHERE np.id=?", (pago_id,)
                ).fetchone()
            elif empleado_id:
                row = self.container.db.execute(
                    "SELECT np.*, p.nombre, p.apellidos, p.puesto, p.rfc "
                    "FROM nomina_pagos np JOIN personal p ON p.id=np.empleado_id "
                    "WHERE np.empleado_id=? ORDER BY np.fecha DESC LIMIT 1",
                    (empleado_id,)
                ).fetchone()
            else:
                QMessageBox.warning(self, "Aviso", "Especifica un pago o empleado."); return

            if not row:
                QMessageBox.warning(self, "Sin datos", "No se encontró el pago."); return

            data = dict(row)
            ruta, _ = QFileDialog.getSaveFileName(
                self, "Guardar recibo", f"recibo_{data.get('nombre','')}.pdf", "PDF (*.pdf)")
            if not ruta: return

            # Generate PDF with reportlab
            from reportlab.pdfgen import canvas as rl_canvas
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.units import mm

            W, H = A4
            c = rl_canvas.Canvas(ruta, pagesize=A4)

            # Header
            neg_row = self.container.db.execute(
                "SELECT valor FROM configuraciones WHERE clave='nombre_empresa'"
            ).fetchone()
            neg = neg_row[0] if neg_row else "SPJ"

            c.setFont("Helvetica-Bold", 18)
            c.drawCentredString(W/2, H - 30*mm, neg)
            c.setFont("Helvetica", 11)
            c.drawCentredString(W/2, H - 38*mm, "RECIBO DE NÓMINA")
            c.line(15*mm, H - 42*mm, W - 15*mm, H - 42*mm)

            # Employee info
            c.setFont("Helvetica-Bold", 10); y = H - 55*mm
            c.drawString(20*mm, y, f"Empleado: {data.get('nombre','')} {data.get('apellidos','')}")
            c.setFont("Helvetica", 10); y -= 8*mm
            c.drawString(20*mm, y, f"Puesto: {data.get('puesto','')}")
            if data.get('rfc'): y -= 8*mm; c.drawString(20*mm, y, f"RFC: {data.get('rfc','')}")
            y -= 8*mm
            c.drawString(20*mm, y, f"Período: {data.get('periodo_inicio','')} — {data.get('periodo_fin','')}")

            # Amounts table
            y -= 15*mm
            c.setFont("Helvetica-Bold", 10)
            c.drawString(20*mm, y, "PERCEPCIONES"); c.drawString(120*mm, y, "DEDUCCIONES")
            y -= 5*mm
            c.line(15*mm, y, W - 15*mm, y); y -= 8*mm
            c.setFont("Helvetica", 10)
            salario = float(data.get('salario_base', 0))
            bonos   = float(data.get('bonos', 0))
            deduc   = float(data.get('deducciones', 0))
            total   = float(data.get('total', 0))
            c.drawString(20*mm, y, f"Salario base: ${salario:,.2f}")
            if bonos > 0: y -= 7*mm; c.drawString(20*mm, y, f"Bonos: ${bonos:,.2f}")
            c.drawString(120*mm, y + 7*mm, f"IMSS/ISR: ${deduc:,.2f}")
            y -= 12*mm
            c.line(15*mm, y, W - 15*mm, y); y -= 8*mm
            c.setFont("Helvetica-Bold", 12)
            c.drawString(20*mm, y, f"TOTAL NETO A PAGAR: ${total:,.2f}")
            y -= 15*mm

            # Method and date
            c.setFont("Helvetica", 10)
            c.drawString(20*mm, y, f"Método de pago: {data.get('metodo_pago','efectivo').upper()}")
            y -= 8*mm
            c.drawString(20*mm, y, f"Fecha de pago: {str(data.get('fecha',''))[:10]}")

            # Signature lines
            y -= 30*mm
            c.line(20*mm, y, 90*mm, y); c.line(110*mm, y, W-20*mm, y)
            y -= 5*mm
            c.setFont("Helvetica", 9)
            c.drawCentredString(55*mm, y, "Firma del empleado")
            c.drawCentredString(155*mm, y, "Firma del empleador")

            c.save()
            QMessageBox.information(self, "✅ PDF generado",
                f"Recibo guardado en:\n{ruta}")
        except Exception as e:
        # [spj-dedup removed local QMessageBox import]
            QMessageBox.critical(self, "Error", str(e))

    # =========================================================
    # TAB: REGLAS LABORALES (HRRuleEngine)
    # =========================================================

    def setup_tab_reglas_laborales(self):
        """
        UI para configurar y auditar las reglas laborales del HRRuleEngine.
        Muestra: días consecutivos, descansos, cobertura mínima, horas extra.
        """
        from PyQt5.QtWidgets import (
            QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
            QSpinBox, QLabel, QPushButton, QTextEdit, QScrollArea,
            QWidget, QFrame, QSizePolicy
        )
        from PyQt5.QtCore import Qt

        lay = QVBoxLayout(self.tab_reglas)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        # ── Encabezado ────────────────────────────────────────────────────────
        lbl_titulo = create_subheading(self, "⚖️ Reglas Laborales — NOM-035 / LFT México")
        lay.addWidget(lbl_titulo)

        lbl_desc = QLabel(
            "Configura los parámetros de jornada y ejecuta auditorías "
            "automáticas para detectar violaciones laborales en tiempo real."
        )
        lbl_desc.setWordWrap(True)
        lbl_desc.setObjectName("caption")
        lay.addWidget(lbl_desc)

        # ── Parámetros configurables ──────────────────────────────────────────
        grp_params = QGroupBox("Parámetros de jornada (Art. LFT)")
        grp_params.setObjectName("styledGroup")
        form = QFormLayout(grp_params)
        form.setLabelAlignment(Qt.AlignRight)
        form.setSpacing(8)

        self._spin_max_dias = QSpinBox()
        self._spin_max_dias.setRange(1, 7)
        self._spin_max_dias.setValue(6)
        self._spin_max_dias.setSuffix(" días")
        self._spin_max_dias.setToolTip("Art. 69 LFT: máximo días consecutivos sin descanso")
        form.addRow("Máx. días consecutivos:", self._spin_max_dias)

        self._spin_horas_sem = QSpinBox()
        self._spin_horas_sem.setRange(1, 72)
        self._spin_horas_sem.setValue(48)
        self._spin_horas_sem.setSuffix(" hrs/semana")
        self._spin_horas_sem.setToolTip("Art. 61 LFT: jornada semanal máxima diurna")
        form.addRow("Límite semanal de horas:", self._spin_horas_sem)

        self._spin_cobertura = QSpinBox()
        self._spin_cobertura.setRange(1, 20)
        self._spin_cobertura.setValue(1)
        self._spin_cobertura.setSuffix(" empleado(s)")
        self._spin_cobertura.setToolTip("Empleados mínimos activos por turno/sucursal")
        form.addRow("Cobertura mínima por turno:", self._spin_cobertura)

        self._spin_periodo_pago = QSpinBox()
        self._spin_periodo_pago.setRange(1, 30)
        self._spin_periodo_pago.setValue(7)
        self._spin_periodo_pago.setSuffix(" días")
        self._spin_periodo_pago.setToolTip("Frecuencia de pago: 7=semanal, 14=quincenal, 30=mensual")
        form.addRow("Periodo de nómina:", self._spin_periodo_pago)

        lay.addWidget(grp_params)

        # ── Botones de acción ─────────────────────────────────────────────────
        row_btns = QHBoxLayout()

        btn_guardar = create_success_button(self, "💾 Guardar parámetros", "Guardar configuración de reglas laborales")
        btn_guardar.clicked.connect(self._guardar_reglas_laborales)

        btn_auditar = create_primary_button(self, "🔍 Ejecutar auditoría ahora", "Ejecutar auditoría de cumplimiento laboral")
        btn_auditar.clicked.connect(self._ejecutar_auditoria_hr)

        btn_nomina = create_accent_button(self, "💰 Verificar nóminas vencidas", "Revisar nóminas pendientes de pago")
        btn_nomina.clicked.connect(self._verificar_nomina_hr)

        row_btns.addWidget(btn_guardar)
        row_btns.addWidget(btn_auditar)
        row_btns.addWidget(btn_nomina)
        row_btns.addStretch()
        lay.addLayout(row_btns)

        # ── Panel de resultados ───────────────────────────────────────────────
        grp_resultado = QGroupBox("Resultado de auditoría")
        grp_resultado.setObjectName("styledGroup")
        lay_res = QVBoxLayout(grp_resultado)

        self._txt_resultado_hr = QTextEdit()
        self._txt_resultado_hr.setReadOnly(True)
        self._txt_resultado_hr.setMinimumHeight(200)
        self._txt_resultado_hr.setObjectName("inputField")
        self._txt_resultado_hr.setPlaceholderText(
            "Presiona 'Ejecutar auditoría' para ver violaciones laborales, "
            "descansos sugeridos y estado de cobertura..."
        )
        lay_res.addWidget(self._txt_resultado_hr)
        lay.addWidget(grp_resultado)

        # Cargar parámetros guardados al abrir
        self._cargar_reglas_laborales()

    def _cargar_reglas_laborales(self):
        """Carga parámetros desde la BD (tabla configuraciones)."""
        try:
            db = self.container.db
            def _cfg(k, d):
                r = db.execute(
                    "SELECT valor FROM configuraciones WHERE clave=?", (k,)
                ).fetchone()
                return r[0] if r else d
            self._spin_max_dias.setValue(int(_cfg("hr_max_dias_consecutivos", 6)))
            self._spin_horas_sem.setValue(int(_cfg("hr_max_horas_semana", 48)))
            self._spin_cobertura.setValue(int(_cfg("hr_cobertura_minima", 1)))
            self._spin_periodo_pago.setValue(int(_cfg("hr_periodo_pago_dias", 7)))
        except Exception:
            pass

    def _guardar_reglas_laborales(self):
        """Persiste los parámetros en la tabla configuraciones."""
        try:
            db = self.container.db
            params = {
                "hr_max_dias_consecutivos": self._spin_max_dias.value(),
                "hr_max_horas_semana":      self._spin_horas_sem.value(),
                "hr_cobertura_minima":      self._spin_cobertura.value(),
                "hr_periodo_pago_dias":     self._spin_periodo_pago.value(),
            }
            for clave, valor in params.items():
                db.execute(
                    "INSERT OR REPLACE INTO configuraciones "
                    "(clave, valor, descripcion) VALUES (?,?,?)",
                    (clave, str(valor), "Regla laboral LFT")
                )
            try:
                db.commit()
            except Exception:
                pass
            QMessageBox.information(
                self, "✅ Guardado",
                "Parámetros de reglas laborales actualizados correctamente."
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo guardar: {e}")

    def _ejecutar_auditoria_hr(self):
        """Llama a HRRuleEngine.auditar_sucursal() y muestra el resultado."""
        try:
            engine = getattr(self.container, "hr_rule_engine", None)
            if engine is None:
                from core.services.hr_rule_engine import HRRuleEngine
                engine = HRRuleEngine(
                    self.container.db,
                    getattr(self.container, "module_config", None)
                )
            resultado = engine.auditar_sucursal(self.sucursal_id)
            self._mostrar_resultado_auditoria(resultado)
        except Exception as e:
            self._txt_resultado_hr.setPlainText(f"❌ Error al auditar: {e}")

    def _verificar_nomina_hr(self):
        """Verifica nóminas vencidas o próximas a vencer."""
        try:
            engine = getattr(self.container, "hr_rule_engine", None)
            if engine is None:
                from core.services.hr_rule_engine import HRRuleEngine
                engine = HRRuleEngine(
                    self.container.db,
                    getattr(self.container, "module_config", None)
                )
            alertas = engine.auditar_nomina_pendiente()
            if not alertas:
                self._txt_resultado_hr.setPlainText(
                    "✅ Nóminas al día — ningún empleado con pago vencido."
                )
                return
            lineas = ["⚠️ NÓMINAS PENDIENTES / VENCIDAS\n" + "─" * 50]
            for a in alertas:
                lineas.append(
                    f"• {a.get('nombre','?')} — "
                    f"Último pago: {a.get('ultimo_pago','N/A')} "
                    f"({a.get('dias_vencido', '?')} días)"
                )
            self._txt_resultado_hr.setPlainText("\n".join(lineas))
        except Exception as e:
            self._txt_resultado_hr.setPlainText(f"❌ Error al verificar nómina: {e}")

    def _mostrar_resultado_auditoria(self, resultado: dict):
        """Formatea y muestra el resultado de auditoría en el QTextEdit."""
        lineas = []
        lineas.append("═" * 55)
        lineas.append(f"  AUDITORÍA LABORAL — Sucursal {resultado.get('sucursal_id', '?')}")
        lineas.append(f"  Fecha: {resultado.get('fecha', 'N/A')}")
        lineas.append("═" * 55)
        lineas.append(
            f"  Empleados total : {resultado.get('empleados_total', 0)}"
        )
        lineas.append(
            f"  Activos hoy     : {resultado.get('activos_hoy', 0)}"
        )
        cob = resultado.get("cobertura_ok", True)
        lineas.append(
            f"  Cobertura mín.  : {'✅ OK' if cob else '❌ INSUFICIENTE'}"
        )
        lineas.append("")

        overwork = resultado.get("overwork", [])
        if overwork:
            lineas.append(f"⚠️  SOBRETIEMPO DETECTADO ({len(overwork)} empleado(s)):")
            for ov in overwork:
                lineas.append(
                    f"   • {ov.get('nombre','?')} — "
                    f"{ov.get('dias_consecutivos', 0)} días consecutivos "
                    f"(máx. permitido: 6)"
                )
        else:
            lineas.append("✅ Ningún empleado excede días consecutivos.")

        lineas.append("")
        descansos = resultado.get("descansos_sugeridos", [])
        if descansos:
            lineas.append(f"🗓️  DESCANSOS SUGERIDOS ({len(descansos)}):")
            for d in descansos:
                lineas.append(
                    f"   • {d.get('nombre','?')} — "
                    f"descanso sugerido: {d.get('fecha_descanso', 'N/A')}"
                )
        else:
            lineas.append("✅ No se requieren descansos adicionales.")

        lineas.append("")
        lineas.append("─" * 55)
        lineas.append("Auditoría completada. Revisa el log del sistema para más detalles.")
        self._txt_resultado_hr.setPlainText("\n".join(lineas))
