
# modulos/configuracion.py
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
import sqlite3
from .base import ModuloBase
import os
import json

# Design System Imports
from modulos.design_tokens import Colors, Spacing, Typography, Shadows
from modulos.ui_components import (
    create_primary_button, create_secondary_button, create_success_button, 
    create_danger_button, create_input_field, create_card,
    create_heading, create_subheading, apply_tooltip
)

try:
    import bcrypt
except ImportError:
    bcrypt = None  # optional dependency
# ── Prefer security.auth for hashing (enterprise) ─────────────────────────────
try:
    from security.auth import hash_password as _hash_password, MIN_PASSWORD_LEN
    _USE_AUTH_MODULE = True
except ImportError:
    _USE_AUTH_MODULE = False

class ModuloConfiguracion(ModuloBase):
    def __init__(self, conexion, parent=None):
        # Accept AppContainer or direct db connection
        if hasattr(conexion, 'db'):
            self.container = conexion
            super().__init__(conexion.db, parent)
        else:
            self.container = None
            super().__init__(conexion, parent)
        self.verificar_tablas_configuraciones()
        self.init_ui()

    def set_usuario_actual(self, usuario: str, rol: str = "cajero") -> None:
        """Recibe el usuario activo al cambiar de sesión."""
        self.usuario_actual = usuario
        self.rol_actual = rol

    def set_sucursal(self, sucursal_id: int, sucursal_nombre: str):
        """Recibe la sucursal activa desde MainWindow."""
        self.sucursal_id     = sucursal_id
        self.sucursal_nombre = sucursal_nombre


    def _on_nav_changed(self, row: int) -> None:
        """Sync stack with nav selection."""
        try:
            self._page_stack.setCurrentIndex(row)
        except Exception:
            pass

    def verificar_tablas_configuraciones(self):
        """Verifica y crea las tablas necesarias para el módulo de configuración"""
        try:
            cursor = self.conexion.cursor()
            
            # Crear tabla de configuración de fidelidad si no existe
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS config_programa_fidelidad (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre_programa TEXT,
                    puntos_por_peso DECIMAL(10,2) DEFAULT 1.0,
                    niveles TEXT,
                    requisitos TEXT,
                    descuentos TEXT,
                    activo INTEGER DEFAULT 1,
                    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Insertar configuración por defecto si no existe
            cursor.execute('''
                INSERT OR IGNORE INTO config_programa_fidelidad 
                (id, nombre_programa, puntos_por_peso) 
                VALUES (1, 'Programa de Puntos', 1.0)
            ''')
            
            # Asegurar que existan las configuracioneses básicas
            configuracioneses_base = [
                ('impuesto_por_defecto', '16.0', 'Impuesto por defecto en porcentaje'),
                ('requerir_admin', 'False', 'Requerir administrador para acciones críticas'),
                ('tema', 'Claro', 'Tema de la aplicación')
            ]
            
            for clave, valor, descripcion in configuracioneses_base:
                cursor.execute('''
                    INSERT OR IGNORE INTO configuraciones (clave, valor, descripcion)
                    VALUES (?, ?, ?)
                ''', (clave, valor, descripcion))
            
            self.conexion.commit()
            print("✅ Tablas de configuración verificadas y creadas")
            
        except sqlite3.Error as e:
            print(f"❌ Error al verificar tablas de configuración: {e}")

    def init_ui(self):
        """Inicializa la interfaz de usuario"""
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)

        # Encabezado
        header_layout = QHBoxLayout()
        title = QLabel("Configuración del Sistema")
        title.setObjectName("tituloPrincipal")
        title.setAlignment(Qt.AlignCenter)
        font = title.font()
        font.setPointSize(16)
        font.setBold(True)
        title.setFont(font)
        header_layout.addWidget(title)
        layout.addLayout(header_layout)

        # Línea separadora
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)

        # ── Navegación vertical (submenú lateral) ────────────────────────
        from PyQt5.QtWidgets import QListWidget, QSplitter, QStackedWidget, QListWidgetItem
        from PyQt5.QtCore import QSize

        content_splitter = QSplitter(Qt.Horizontal)

        # Sidebar de categorías (SIEMPRE OSCURO - estilo del sistema)
        self._nav_list = QListWidget()
        self._nav_list.setFixedWidth(200)
        self._nav_list.setObjectName("sidebarNav")  # Usar clase CSS en lugar de inline
        self._nav_list.currentRowChanged.connect(self._on_nav_changed)

        # Stack de páginas
        self.tabs_config = QStackedWidget()  # backward compat alias
        self._page_stack = self.tabs_config

        content_splitter.addWidget(self._nav_list)
        content_splitter.addWidget(self._page_stack)
        content_splitter.setStretchFactor(1, 1)
        layout.addWidget(content_splitter)

        # Helper to add a page
        def _add_page(label: str, widget: QWidget):
            item = QListWidgetItem(label)
            self._nav_list.addItem(item)
            self._page_stack.addWidget(widget)

        # ── Pages (replaces addTab) ──────────────────────────────────────────
        # Shim: tabs_config.addTab(widget, label) → _add_page(label, widget)
        class _TabShim:
            def __init__(self_s, stack, nav):
                self_s._stack = stack
                self_s._nav = nav
            def addTab(self_s, widget, label):
                _add_page(label, widget)
            def setCurrentIndex(self_s, idx):
                self_s._stack.setCurrentIndex(idx)
                self_s._nav.setCurrentRow(idx)
        self.tabs_config = _TabShim(self._page_stack, self._nav_list)
        
        # Crear pestañas que SÍ se necesitan aquí
        self.tab_general = self.crear_tab_general()

        self.tab_comisiones = QWidget()
        self.tab_happy_hour = QWidget()

        self.tab_empresa   = QWidget()
        self.tab_email      = QWidget()
        self.tab_mercadopago = QWidget()
        self.tab_usuarios_roles = QWidget()
        self.tab_cierre_mensual = QWidget()

        # v13.30: Solo tabs de configuración del SISTEMA.
        # Hardware, Ticket Designer, WhatsApp, Fidelización, Apariencia
        # tienen su propio módulo en el menú lateral.
        self.tabs_config.addTab(self.tab_empresa,          "🏢 Empresa / Fiscal")
        self.tabs_config.addTab(self.tab_general,          "⚙️ General")
        self.tabs_config.addTab(self.tab_usuarios_roles,   "👤 Usuarios y Roles")
        self.tabs_config.addTab(self.tab_email,            "📧 Email / SMTP")
        self.tabs_config.addTab(self.tab_mercadopago,      "💳 Mercado Pago")
        self.tabs_config.addTab(self.tab_comisiones,       "💰 Comisiones")
        self.tabs_config.addTab(self.tab_happy_hour,       "⏰ Happy Hour")
        self.tabs_config.addTab(self.tab_cierre_mensual,   "📅 Cierre Mensual")
        self._setup_tab_cierre_mensual()

        self.setLayout(layout)

        # Cargar datos iniciales
        self.cargar_configuraciones_general()
        self._setup_tab_comisiones()
        self._setup_tab_happy_hour()
        self.cargar_sucursales()
        self._setup_tab_empresa()
        self._setup_tab_email()
        self._setup_tab_mercadopago()
        self._setup_tab_usuarios_roles()
        try:
            self._cargar_usuarios_v13()
        except Exception:
            pass

    def crear_tab_general(self):
        """Crea la pestaña de configuración general"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(15)

        # Grupo de Apariencia — v13.30: solo toggle dark mode
        grupo_apariencia = QGroupBox("Apariencia")
        grupo_apariencia.setObjectName("configGroup")  # Clase CSS para GroupBox
        layout_apariencia = QFormLayout()
        
        self.chk_dark_mode = QCheckBox("🌙 Modo Oscuro")
        self.chk_dark_mode.setToolTip("Activa el tema oscuro para toda la interfaz")
        self.chk_dark_mode.setObjectName("checkboxStandard")  # Clase CSS
        self.chk_dark_mode.stateChanged.connect(self._toggle_dark_mode)
        layout_apariencia.addRow("", self.chk_dark_mode)
        grupo_apariencia.setLayout(layout_apariencia)

        # Grupo de Impuestos
        grupo_impuestos = QGroupBox("Configuración Fiscal")
        grupo_impuestos.setObjectName("configGroup")  # Clase CSS para GroupBox
        layout_impuestos = QFormLayout()
        
        self.spin_impuesto = QDoubleSpinBox()
        self.spin_impuesto.setRange(0.0, 100.0)
        self.spin_impuesto.setSuffix(" %")
        self.spin_impuesto.setDecimals(2)
        self.spin_impuesto.setObjectName("inputField")  # Clase CSS para inputs
        self.spin_impuesto.setToolTip("Impuesto por defecto aplicado a las ventas")
        
        btn_guardar_impuesto = create_primary_button(self, "Guardar Impuesto", "Guardar configuración de impuesto")
        btn_guardar_impuesto.setIcon(self.obtener_icono("save.png"))
        
        layout_impuestos.addRow("IVA por defecto:", self.spin_impuesto)
        layout_impuestos.addRow("", btn_guardar_impuesto)
        grupo_impuestos.setLayout(layout_impuestos)

        # Grupo de Seguridad
        grupo_seguridad = QGroupBox("Seguridad")
        grupo_seguridad.setObjectName("configGroup")  # Clase CSS para GroupBox
        layout_seguridad = QVBoxLayout()
        
        self.chk_requerir_admin = QCheckBox("Requerir autorización de administrador para acciones críticas")
        self.chk_requerir_admin.setToolTip("Activar para requerir permisos de administrador en operaciones sensibles")
        self.chk_requerir_admin.setObjectName("checkboxStandard")  # Clase CSS
        
        btn_guardar_seguridad = create_primary_button(self, "Guardar Configuración de Seguridad", "Guardar configuración de seguridad")
        btn_guardar_seguridad.setIcon(self.obtener_icono("security.png"))
        
        layout_seguridad.addWidget(self.chk_requerir_admin)
        layout_seguridad.addWidget(btn_guardar_seguridad, 0, Qt.AlignLeft)
        grupo_seguridad.setLayout(layout_seguridad)

        # Agregar grupos al layout principal
        layout.addWidget(grupo_apariencia)
        layout.addWidget(grupo_impuestos)
        layout.addWidget(grupo_seguridad)
        layout.addStretch()

        return tab

    def crear_tab_usuarios(self):
        """Crea la pestaña de gestión de usuarios"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        # Barra de herramientas
        toolbar = QHBoxLayout()
        
        self.btn_nuevo_usuario = QPushButton("Nuevo Usuario")
        self.btn_nuevo_usuario.setIcon(self.obtener_icono("add.png"))
        self.btn_nuevo_usuario.setToolTip("Crear un nuevo usuario")
        
        self.btn_editar_usuario = QPushButton("Editar Usuario")
        self.btn_editar_usuario.setIcon(self.obtener_icono("edit.png"))
        self.btn_editar_usuario.setToolTip("Editar usuario seleccionado")
        self.btn_editar_usuario.setEnabled(False)
        
        self.btn_eliminar_usuario = QPushButton("Eliminar Usuario")
        self.btn_eliminar_usuario.setIcon(self.obtener_icono("delete.png"))
        self.btn_eliminar_usuario.setToolTip("Eliminar usuario seleccionado")
        self.btn_eliminar_usuario.setEnabled(False)
        
        self.btn_actualizar = QPushButton("Actualizar")
        self.btn_actualizar.setIcon(self.obtener_icono("refresh.png"))
        self.btn_actualizar.setToolTip("Actualizar lista de usuarios")
        
        toolbar.addWidget(self.btn_nuevo_usuario)
        toolbar.addWidget(self.btn_editar_usuario)
        toolbar.addWidget(self.btn_eliminar_usuario)
        toolbar.addStretch()
        toolbar.addWidget(self.btn_actualizar)
        layout.addLayout(toolbar)

        # Tabla de usuarios
        self.tabla_usuarios = QTableWidget()
        self.tabla_usuarios.setColumnCount(7)
        self.tabla_usuarios.setHorizontalHeaderLabels([
            "ID", "Usuario", "Nombre", "Rol", "Fecha Creación", "Estado"
        ])
        
        # Configurar tabla
        self.tabla_usuarios.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla_usuarios.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla_usuarios.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabla_usuarios.setAlternatingRowColors(True)
        header = self.tabla_usuarios.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        
        layout.addWidget(self.tabla_usuarios)

        # Conexiones
        self.btn_nuevo_usuario.clicked.connect(self.nuevo_usuario)
        self.btn_editar_usuario.clicked.connect(self.editar_usuario)
        self.btn_eliminar_usuario.clicked.connect(self.eliminar_usuario)
        self.btn_actualizar.clicked.connect(self.cargar_usuarios)
        self.tabla_usuarios.itemSelectionChanged.connect(self.actualizar_botones_usuarios)

        return tab

    def crear_tab_fidelizacion(self):
        """Crea la pestaña de configuración de fidelización"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(15)

        # Información del programa actual
        grupo_info = QGroupBox("Información del Programa Actual")
        grupo_info.setObjectName("configGroup")  # Clase CSS para GroupBox
        layout_info = QVBoxLayout()
        
        self.lbl_info_programa = QLabel()
        self.lbl_info_programa.setWordWrap(True)
        self.lbl_info_programa.setObjectName("infoCard")  # Clase CSS para cards informativas
        layout_info.addWidget(self.lbl_info_programa)
        grupo_info.setLayout(layout_info)

        # Configuración del programa
        grupo_config = QGroupBox("Configuración del Programa de Fidelidad")
        grupo_config.setObjectName("configGroup")  # Clase CSS para GroupBox
        layout_config = QFormLayout()
        layout_config.setLabelAlignment(Qt.AlignRight)
        
        self.edit_nombre_programa = create_input_field(self, "Ej: Programa de Puntos MiTienda", "Nombre del programa de fidelidad")
        
        self.spin_puntos_por_peso = QDoubleSpinBox()
        self.spin_puntos_por_peso.setRange(0.01, 100.0)
        self.spin_puntos_por_peso.setValue(1.0)
        self.spin_puntos_por_peso.setSuffix(" puntos por $")
        self.spin_puntos_por_peso.setObjectName("inputField")  # Clase CSS
        self.spin_puntos_por_peso.setToolTip("Puntos ganados por cada peso gastado")
        
        self.edit_niveles = create_input_field(self, "Ej: Bronce,Plata,Oro,Diamante", "Niveles del programa separados por comas")
        
        self.edit_requisitos = create_input_field(self, "Ej: 0,1000,5000,10000", "Puntos requeridos para cada nivel")
        
        self.edit_descuentos = create_input_field(self, "Ej: 5,10,15,20", "Descuentos porcentuales por nivel")
        self.edit_descuentos.setPlaceholderText("Ej: 0,5,10,15")
        self.edit_descuentos.setToolTip("Porcentaje de descuento para cada nivel")
        
        btn_guardar_fidelidad = QPushButton("💾 Guardar Configuración de Fidelidad")
        btn_guardar_fidelidad.setIcon(self.obtener_icono("save.png"))
        btn_guardar_fidelidad.clicked.connect(self.guardar_configuraciones_fidelidad)
        
        layout_config.addRow("Nombre del Programa:", self.edit_nombre_programa)
        layout_config.addRow("Puntos por $ gastado:", self.spin_puntos_por_peso)
        layout_config.addRow("Niveles:", self.edit_niveles)
        layout_config.addRow("Requisitos (puntos):", self.edit_requisitos)
        layout_config.addRow("Descuentos (%):", self.edit_descuentos)
        layout_config.addRow("", btn_guardar_fidelidad)
        grupo_config.setLayout(layout_config)

        # Agregar grupos al layout
        layout.addWidget(grupo_info)
        layout.addWidget(grupo_config)
        layout.addStretch()

        return tab
    
    def _actualizar_suma_pesos(self):
        suma = (self.spin_peso_frecuencia.value() + self.spin_peso_volumen.value() +
                self.spin_peso_margen.value() + self.spin_peso_comunidad.value())
        color = "red" if suma != 100 else "green"
        self.lbl_suma_pesos.setText(
            f"<span style='color:{color}'>Suma: {suma}% "
            f"{'✓' if suma == 100 else '⚠ Debe ser 100%'}</span>"
        )

    
    # ── v9: Tab Diseño Tickets ───────────────────────────────────────────────

    def crear_tab_ticket_designer(self):
        """
        Diseñador visual de tickets y etiquetas.
        Muestra lista de elementos con drag-drop de posición.
        Vista previa simulada.
        """
        from PyQt5.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
            QPushButton, QListWidget, QTextEdit, QLabel,
            QComboBox, QGroupBox
        )
        from PyQt5.QtCore import Qt
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)

        # Tipo de diseño
        top = QHBoxLayout()
        top.addWidget(QLabel("Tipo:"))
        self.combo_design_tipo = QComboBox()
        self.combo_design_tipo.addItems(["ticket", "etiqueta"])
        self.combo_design_tipo.currentTextChanged.connect(self._cargar_diseno_ticket)
        top.addWidget(self.combo_design_tipo)
        top.addStretch()
        btn_guardar_d = QPushButton("💾 Guardar Diseño")
        btn_guardar_d.clicked.connect(self._guardar_diseno_ticket)
        top.addWidget(btn_guardar_d)
        layout.addLayout(top)

        splitter = QSplitter(Qt.Horizontal)

        # Panel izquierdo: elementos disponibles + lista actual
        panel_izq = QWidget()
        lay_izq = QVBoxLayout(panel_izq)

        grp_elem = QGroupBox("Elementos disponibles")
        lay_elem = QVBoxLayout(grp_elem)
        self.lista_elementos_disponibles = QListWidget()
        elementos = [
            "header_empresa", "header_sucursal", "fecha", "folio", "cajero",
            "tabla_items", "totales", "forma_pago", "puntos_cliente",
            "separador", "codigo_qr", "codigo_barras", "logo",
            "texto_personalizado", "footer",
        ]
        self.lista_elementos_disponibles.addItems(elementos)
        lay_elem.addWidget(self.lista_elementos_disponibles)
        btn_agregar_e = QPushButton("➕ Agregar al diseño")
        btn_agregar_e.clicked.connect(self._agregar_elemento_diseno)
        lay_elem.addWidget(btn_agregar_e)
        lay_izq.addWidget(grp_elem)

        grp_actual = QGroupBox("Elementos en diseño (orden = posición)")
        lay_act = QVBoxLayout(grp_actual)
        self.lista_diseno_actual = QListWidget()
        self.lista_diseno_actual.setDragDropMode(QListWidget.InternalMove)
        lay_act.addWidget(self.lista_diseno_actual)
        btn_quitar_e = QPushButton("✖ Quitar seleccionado")
        btn_quitar_e.clicked.connect(self._quitar_elemento_diseno)
        lay_act.addWidget(btn_quitar_e)
        lay_izq.addWidget(grp_actual)

        splitter.addWidget(panel_izq)

        # Panel derecho: vista previa JSON
        panel_der = QWidget()
        lay_der = QVBoxLayout(panel_der)
        lay_der.addWidget(QLabel("Vista previa (JSON elementos):"))
        self.txt_preview_diseno = QTextEdit()
        self.txt_preview_diseno.setReadOnly(True)
        self.txt_preview_diseno.setMaximumHeight(300)
        lay_der.addWidget(self.txt_preview_diseno)

        lay_der.addWidget(QLabel("Variables disponibles:"))
        variables_info = QTextEdit()
        variables_info.setReadOnly(True)
        variables_info.setMaximumHeight(150)
        variables_info.setPlainText(
            "empresa = Nombre del negocio\n"
            "sucursal = Nombre sucursal\n"
            "fecha = Fecha/hora de venta\n"
            "folio = Número de folio\n"
            "cajero = Usuario cajero\n"
            "cliente = Nombre del cliente\n"
            "footer = Mensaje pie de ticket\n"
        )
        lay_der.addWidget(variables_info)
        splitter.addWidget(panel_der)

        layout.addWidget(splitter)

        # Cargar diseño actual
        self._cargar_diseno_ticket()
        return tab

    def _cargar_diseno_ticket(self):
        """Carga elementos del diseño activo para el tipo seleccionado."""
        try:
            import json
            tipo = self.combo_design_tipo.currentText() if hasattr(self, 'combo_design_tipo') else "ticket"
            row = self.conexion.execute(
                "SELECT elementos FROM ticket_design_config WHERE tipo=? AND activo=1 LIMIT 1",
                (tipo,)
            ).fetchone()
            if row:
                elementos = json.loads(row[0])
                self.lista_diseno_actual.clear()
                for elem in elementos:
                    label = elem.get("id", elem.get("tipo", "elemento"))
                    self.lista_diseno_actual.addItem(label)
                self.txt_preview_diseno.setPlainText(
                    json.dumps(elementos, indent=2, ensure_ascii=False)
                )
        except Exception:
            pass
        
    def _guardar_diseno_ticket(self):
        try:
            import json
        # [spj-dedup removed local QMessageBox import]
            tipo = self.combo_design_tipo.currentText()
            elementos = []
            for i in range(self.lista_diseno_actual.count()):
                eid = self.lista_diseno_actual.item(i).text()
                elementos.append({"id": eid, "tipo": eid, "y_pos": i})
            elementos_json = json.dumps(elementos, ensure_ascii=False)
            self.conexion.execute(
                """
                UPDATE ticket_design_config
                SET elementos=?, activo=1
                WHERE tipo=? AND nombre='Default'
                """,
                (elementos_json, tipo)
            )
            if self.conexion.execute(
                "SELECT changes()"
            ).fetchone()[0] == 0:
                self.conexion.execute(
                    "INSERT OR REPLACE INTO ticket_design_config (tipo, nombre, elementos, activo) "
                    "VALUES (?,?,?,1)",
                    (tipo, "Default", elementos_json)
                )
            self.conexion.commit()
            QMessageBox.information(self, "Diseño", f"Diseño de {tipo} guardado.")
        except Exception as exc:
        # [spj-dedup removed local QMessageBox import]
            QMessageBox.critical(self, "Error", str(exc))
            
    def _agregar_elemento_diseno(self):
        item = self.lista_elementos_disponibles.currentItem()
        if item:
            self.lista_diseno_actual.addItem(item.text())
            self._actualizar_preview_diseno()

    def _quitar_elemento_diseno(self):
        fila = self.lista_diseno_actual.currentRow()
        if fila >= 0:
            self.lista_diseno_actual.takeItem(fila)
            self._actualizar_preview_diseno()

    def _actualizar_preview_diseno(self):
        import json
        elementos = []
        for i in range(self.lista_diseno_actual.count()):
            eid = self.lista_diseno_actual.item(i).text()
            elementos.append({"id": eid, "tipo": eid, "y_pos": i})
        self.txt_preview_diseno.setPlainText(
            json.dumps(elementos, indent=2, ensure_ascii=False)
        )
        
    # ── v9: Tab Hardware POS ─────────────────────────────────────────────────

    def crear_tab_hardware(self):
        """
        Configuración de hardware:
        - Impresora térmica (tipo, puerto, ancho)
        - Cajón (método, señal)
        - Scanner (debounce, longitud mínima)
        - Báscula (puerto serial, baud)
        """
        from PyQt5.QtWidgets import (
            QWidget, QVBoxLayout, QFormLayout, QGroupBox,
            QComboBox, QLineEdit, QSpinBox, QCheckBox, QHBoxLayout, QPushButton
        )
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(14)
        layout.setContentsMargins(14, 14, 14, 14)

        # Impresora
        grp_imp = QGroupBox("🖨️ Impresora Térmica")
        form_imp = QFormLayout(grp_imp)
        self.chk_imp_habilitada = QCheckBox("Habilitada")
        self.combo_imp_tipo = QComboBox()
        self.combo_imp_tipo.addItems(["escpos_usb", "escpos_serial", "win32print", "simulado"])
        self.txt_imp_puerto = QLineEdit()
        self.txt_imp_puerto.setPlaceholderText("USB / COM3")
        self.spin_imp_ancho = QSpinBox()
        self.spin_imp_ancho.setRange(48, 120)
        self.spin_imp_ancho.setValue(80)
        self.spin_imp_ancho.setSuffix(" mm")
        form_imp.addRow("Estado:", self.chk_imp_habilitada)
        form_imp.addRow("Tipo:", self.combo_imp_tipo)
        form_imp.addRow("Puerto:", self.txt_imp_puerto)
        form_imp.addRow("Ancho papel:", self.spin_imp_ancho)
        layout.addWidget(grp_imp)

        # Cajón
        grp_caj = QGroupBox("🗃️ Cajón de Dinero")
        form_caj = QFormLayout(grp_caj)
        self.chk_caj_habilitado = QCheckBox("Habilitado")
        self.combo_caj_metodo = QComboBox()
        self.combo_caj_metodo.addItems(["escpos", "serial", "parallel"])
        self.combo_caj_pin = QComboBox()
        self.combo_caj_pin.addItems(["kick1", "kick2"])
        form_caj.addRow("Estado:", self.chk_caj_habilitado)
        form_caj.addRow("Método:", self.combo_caj_metodo)
        form_caj.addRow("Pin de activación:", self.combo_caj_pin)
        layout.addWidget(grp_caj)

        # Scanner
        grp_scan = QGroupBox("🔍 Lector de Código de Barras")
        form_scan = QFormLayout(grp_scan)
        self.chk_scan_habilitado = QCheckBox("Habilitado")
        self.spin_scan_debounce = QSpinBox()
        self.spin_scan_debounce.setRange(20, 500)
        self.spin_scan_debounce.setValue(80)
        self.spin_scan_debounce.setSuffix(" ms")
        self.spin_scan_minlen = QSpinBox()
        self.spin_scan_minlen.setRange(1, 20)
        self.spin_scan_minlen.setValue(3)
        form_scan.addRow("Estado:", self.chk_scan_habilitado)
        form_scan.addRow("Debounce:", self.spin_scan_debounce)
        form_scan.addRow("Longitud mínima:", self.spin_scan_minlen)
        layout.addWidget(grp_scan)

        # Báscula
        grp_bas = QGroupBox("⚖️ Báscula Serial")
        form_bas = QFormLayout(grp_bas)
        self.chk_bas_habilitada = QCheckBox("Habilitada")
        self.txt_bas_puerto = QLineEdit()
        self.txt_bas_puerto.setPlaceholderText("COM3")
        self.spin_bas_baud = QSpinBox()
        self.spin_bas_baud.setRange(1200, 115200)
        self.spin_bas_baud.setValue(9600)
        form_bas.addRow("Estado:", self.chk_bas_habilitada)
        form_bas.addRow("Puerto:", self.txt_bas_puerto)
        form_bas.addRow("Baud rate:", self.spin_bas_baud)
        layout.addWidget(grp_bas)

        # Impresora de etiquetas (Zebra/TSC)
        grp_etiq = QGroupBox("🏷️ Impresora de Etiquetas (ZPL/TSPL)")
        form_etiq = QFormLayout(grp_etiq)
        self.chk_etiq_habilitada = QCheckBox("Habilitada")
        self.combo_etiq_protocolo = QComboBox()
        self.combo_etiq_protocolo.addItems(["ZPL (Zebra)", "TSPL (TSC)", "Auto-detectar"])
        self.txt_etiq_ip = QLineEdit(); self.txt_etiq_ip.setPlaceholderText("192.168.1.100")
        self.spin_etiq_puerto = QSpinBox()
        self.spin_etiq_puerto.setRange(1, 65535); self.spin_etiq_puerto.setValue(9100)
        self.txt_etiq_serial = QLineEdit(); self.txt_etiq_serial.setPlaceholderText("COM4 (si es USB/Serial)")
        self.spin_etiq_ancho = QSpinBox()
        self.spin_etiq_ancho.setRange(25, 150); self.spin_etiq_ancho.setValue(80)
        self.spin_etiq_ancho.setSuffix(" mm")
        form_etiq.addRow("Estado:", self.chk_etiq_habilitada)
        form_etiq.addRow("Protocolo:", self.combo_etiq_protocolo)
        form_etiq.addRow("IP:", self.txt_etiq_ip)
        form_etiq.addRow("Puerto TCP:", self.spin_etiq_puerto)
        form_etiq.addRow("Puerto serial:", self.txt_etiq_serial)
        form_etiq.addRow("Ancho etiqueta:", self.spin_etiq_ancho)
        layout.addWidget(grp_etiq)

        # Monitor cliente / pantalla secundaria
        grp_mon = QGroupBox("🖥️ Monitor Cliente (Pantalla Secundaria)")
        form_mon = QFormLayout(grp_mon)
        self.chk_monitor_cliente = QCheckBox("Habilitar pantalla secundaria para cliente")
        self.spin_monitor_pantalla = QSpinBox()
        self.spin_monitor_pantalla.setRange(1, 4); self.spin_monitor_pantalla.setValue(2)
        self.spin_monitor_pantalla.setPrefix("Pantalla #")
        self.combo_monitor_resolucion = QComboBox()
        self.combo_monitor_resolucion.addItems([
            "1920×1080 (Full HD)", "1280×720 (HD)", "1024×768", "800×600"])
        self.chk_monitor_autostart = QCheckBox(
            "Abrir automáticamente al iniciar el sistema")
        form_mon.addRow("Estado:", self.chk_monitor_cliente)
        form_mon.addRow("Pantalla:", self.spin_monitor_pantalla)
        form_mon.addRow("Resolución:", self.combo_monitor_resolucion)
        form_mon.addRow("", self.chk_monitor_autostart)
        layout.addWidget(grp_mon)

        # Botón guardar
        btn_hw = QPushButton("💾 Guardar Configuración Hardware")
        btn_hw.clicked.connect(self._guardar_hardware_config)
        layout.addWidget(btn_hw)
        layout.addStretch()
        return tab

    def _cargar_hardware_config(self):
        """Carga valores desde hardware_config en la UI."""
        try:
            import json
            rows = self.conexion.execute(
                "SELECT tipo, habilitado, configuraciones FROM hardware_config"
            ).fetchall()
            for tipo, hab, cfg_json in rows:
                cfg = json.loads(cfg_json) if cfg_json else {}
                if tipo == "impresora":
                    self.chk_imp_habilitada.setChecked(bool(hab))
                    idx = self.combo_imp_tipo.findText(cfg.get("tipo", "escpos_usb"))
                    if idx >= 0: self.combo_imp_tipo.setCurrentIndex(idx)
                    self.txt_imp_puerto.setText(cfg.get("puerto", "USB"))
                    self.spin_imp_ancho.setValue(int(cfg.get("ancho_mm", 80)))
                elif tipo == "cajon":
                    self.chk_caj_habilitado.setChecked(bool(hab))
                    idx = self.combo_caj_metodo.findText(cfg.get("metodo", "escpos"))
                    if idx >= 0: self.combo_caj_metodo.setCurrentIndex(idx)
                    idx_p = self.combo_caj_pin.findText(cfg.get("pin", "kick1"))
                    if idx_p >= 0: self.combo_caj_pin.setCurrentIndex(idx_p)
                elif tipo == "scanner":
                    self.chk_scan_habilitado.setChecked(bool(hab))
                    self.spin_scan_debounce.setValue(int(cfg.get("debounce_ms", 80)))
                    self.spin_scan_minlen.setValue(int(cfg.get("min_len", 3)))
                elif tipo == "bascula":
                    self.chk_bas_habilitada.setChecked(bool(hab))
                    self.txt_bas_puerto.setText(cfg.get("puerto", "COM3"))
                    self.spin_bas_baud.setValue(int(cfg.get("baud", 9600)))
        except Exception:
            pass  # tabla no migrada aún
        
    def _guardar_hardware_config(self):
        """Guarda configuración de hardware en hardware_config."""
        try:
            import json
        # [spj-dedup removed local QMessageBox import]
            config_map = {
                "impresora": (
                    1 if self.chk_imp_habilitada.isChecked() else 0,
                    json.dumps({
                        "tipo":     self.combo_imp_tipo.currentText(),
                        "puerto":   self.txt_imp_puerto.text().strip() or "USB",
                        "ancho_mm": self.spin_imp_ancho.value(),
                    })
                ),
                "cajon": (
                    1 if self.chk_caj_habilitado.isChecked() else 0,
                    json.dumps({
                        "metodo": self.combo_caj_metodo.currentText(),
                        "pin":    self.combo_caj_pin.currentText(),
                    })
                ),
                "scanner": (
                    1 if self.chk_scan_habilitado.isChecked() else 0,
                    json.dumps({
                        "debounce_ms": self.spin_scan_debounce.value(),
                        "min_len":     self.spin_scan_minlen.value(),
                    })
                ),
                "bascula": (
                    1 if self.chk_bas_habilitada.isChecked() else 0,
                    json.dumps({
                        "puerto": self.txt_bas_puerto.text().strip() or "COM3",
                        "baud":   self.spin_bas_baud.value(),
                    })
                ),
            }
            for tipo, (hab, cfg) in config_map.items():
                self.conexion.execute(
                    """
                    UPDATE hardware_config
                    SET habilitado=?, configuraciones=?, actualizado_en=datetime('now')
                    WHERE tipo=?
                    """,
                    (hab, cfg, tipo)
                )
            self.conexion.commit()
            QMessageBox.information(self, "Hardware",
                "Configuración de hardware guardada correctamente.")
        except Exception as exc:
        # [spj-dedup removed local QMessageBox import]
            QMessageBox.critical(self, "Error", str(exc))

    
    def crear_tab_loyalty_weights(self):
        """
        Configuración de pesos de scoring multivariable:
        frecuencia, volumen, margen, comunidad.
        Umbrales de nivel: Plata, Oro, Platino.
        """
        from PyQt5.QtWidgets import (
            QWidget, QVBoxLayout, QFormLayout, QGroupBox,
            QSpinBox, QDoubleSpinBox, QPushButton, QLabel
        )
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(12)
        layout.setContentsMargins(14, 14, 14, 14)

        # Pesos dimensiones
        grp_pesos = QGroupBox("Pesos de Scoring (deben sumar 100)")
        form_p = QFormLayout(grp_pesos)

        self.spin_peso_frecuencia = QSpinBox()
        self.spin_peso_frecuencia.setRange(0, 100)
        self.spin_peso_frecuencia.setSuffix(" %")
        self.spin_peso_frecuencia.setValue(30)

        self.spin_peso_volumen = QSpinBox()
        self.spin_peso_volumen.setRange(0, 100)
        self.spin_peso_volumen.setSuffix(" %")
        self.spin_peso_volumen.setValue(30)

        self.spin_peso_margen = QSpinBox()
        self.spin_peso_margen.setRange(0, 100)
        self.spin_peso_margen.setSuffix(" %")
        self.spin_peso_margen.setValue(30)

        self.spin_peso_comunidad = QSpinBox()
        self.spin_peso_comunidad.setRange(0, 100)
        self.spin_peso_comunidad.setSuffix(" %")
        self.spin_peso_comunidad.setValue(10)

        form_p.addRow("Frecuencia de visitas:", self.spin_peso_frecuencia)
        form_p.addRow("Volumen de compra:", self.spin_peso_volumen)
        form_p.addRow("Margen generado:", self.spin_peso_margen)
        form_p.addRow("Comunidad/Referidos:", self.spin_peso_comunidad)

        self.lbl_suma_pesos = QLabel("Suma: 100%")
        form_p.addRow("", self.lbl_suma_pesos)
        for sp in (self.spin_peso_frecuencia, self.spin_peso_volumen,
                   self.spin_peso_margen, self.spin_peso_comunidad):
            sp.valueChanged.connect(self._actualizar_suma_pesos)
        layout.addWidget(grp_pesos)

        # Umbrales de nivel
        grp_umbrales = QGroupBox("Umbrales de Nivel")
        form_u = QFormLayout(grp_umbrales)
        self.spin_umbral_plata   = QDoubleSpinBox()
        self.spin_umbral_oro     = QDoubleSpinBox()
        self.spin_umbral_platino = QDoubleSpinBox()
        for sp in (self.spin_umbral_plata, self.spin_umbral_oro, self.spin_umbral_platino):
            sp.setRange(0, 100)
            sp.setDecimals(1)
        self.spin_umbral_plata.setValue(40)
        self.spin_umbral_oro.setValue(65)
        self.spin_umbral_platino.setValue(85)
        form_u.addRow("Plata (score ≥):", self.spin_umbral_plata)
        form_u.addRow("Oro (score ≥):", self.spin_umbral_oro)
        form_u.addRow("Platino (score ≥):", self.spin_umbral_platino)
        layout.addWidget(grp_umbrales)

        # Parámetros adicionales
        grp_extra = QGroupBox("Parámetros Adicionales")
        form_e = QFormLayout(grp_extra)
        self.spin_periodo_dias = QSpinBox()
        self.spin_periodo_dias.setRange(7, 365)
        self.spin_periodo_dias.setValue(90)
        self.spin_periodo_dias.setSuffix(" días")
        self.spin_puntos_por_peso = QDoubleSpinBox()
        self.spin_puntos_por_peso.setRange(0.01, 100)
        self.spin_puntos_por_peso.setValue(1.0)
        self.spin_puntos_por_peso.setDecimals(2)
        self.spin_bonus_referido = QSpinBox()
        self.spin_bonus_referido.setRange(0, 5000)
        self.spin_bonus_referido.setValue(50)
        form_e.addRow("Período análisis:", self.spin_periodo_dias)
        form_e.addRow("Puntos por $1 gastado:", self.spin_puntos_por_peso)
        form_e.addRow("Bono por referido:", self.spin_bonus_referido)
        layout.addWidget(grp_extra)

        btn_guardar_lw = QPushButton("💾 Guardar Configuración Fidelidad")
        btn_guardar_lw.clicked.connect(self._guardar_loyalty_weights)
        layout.addWidget(btn_guardar_lw)
        layout.addStretch()
        return tab
    
    def _cargar_loyalty_weights(self):
        """Carga valores de loyalty_config en los spinboxes."""
        try:
            rows = self.conexion.execute(
                "SELECT clave, valor FROM loyalty_config"
            ).fetchall()
            cfg = {r[0]: r[1] for r in rows}
            self.spin_peso_frecuencia.setValue(int(cfg.get("peso_frecuencia", 30)))
            self.spin_peso_volumen.setValue(int(cfg.get("peso_volumen", 30)))
            self.spin_peso_margen.setValue(int(cfg.get("peso_margen", 30)))
            self.spin_peso_comunidad.setValue(int(cfg.get("peso_comunidad", 10)))
            self.spin_umbral_plata.setValue(float(cfg.get("umbral_plata", 40)))
            self.spin_umbral_oro.setValue(float(cfg.get("umbral_oro", 65)))
            self.spin_umbral_platino.setValue(float(cfg.get("umbral_platino", 85)))
            self.spin_periodo_dias.setValue(int(cfg.get("periodo_dias", 90)))
            self.spin_puntos_por_peso.setValue(float(cfg.get("puntos_por_peso", 1.0)))
            self.spin_bonus_referido.setValue(int(cfg.get("bonus_referido", 50)))
            self._actualizar_suma_pesos()
        except Exception:
            pass

    def _guardar_loyalty_weights(self):
        """Persiste pesos y umbrales en loyalty_config."""
        try:
        # [spj-dedup removed local QMessageBox import]
            suma = (self.spin_peso_frecuencia.value() + self.spin_peso_volumen.value() +
                    self.spin_peso_margen.value() + self.spin_peso_comunidad.value())
            if suma != 100:
                QMessageBox.warning(self, "Pesos inválidos",
                    f"Los pesos deben sumar 100%. Suma actual: {suma}%")
                return
            updates = [
                ("peso_frecuencia",  str(self.spin_peso_frecuencia.value())),
                ("peso_volumen",     str(self.spin_peso_volumen.value())),
                ("peso_margen",      str(self.spin_peso_margen.value())),
                ("peso_comunidad",   str(self.spin_peso_comunidad.value())),
                ("umbral_plata",     str(self.spin_umbral_plata.value())),
                ("umbral_oro",       str(self.spin_umbral_oro.value())),
                ("umbral_platino",   str(self.spin_umbral_platino.value())),
                ("periodo_dias",     str(self.spin_periodo_dias.value())),
                ("puntos_por_peso",  str(self.spin_puntos_por_peso.value())),
                ("bonus_referido",   str(self.spin_bonus_referido.value())),
            ]
            for clave, valor in updates:
                self.conexion.execute(
                    "INSERT OR REPLACE INTO loyalty_config (clave, valor) VALUES (?,?)",
                    (clave, valor)
                )
            self.conexion.commit()
            QMessageBox.information(self, "Fidelidad",
                "Configuración de fidelidad guardada correctamente.")
        except Exception as exc:
        # [spj-dedup removed local QMessageBox import]
            QMessageBox.critical(self, "Error", str(exc))

    # === MÉTODOS DE CONFIGURACIÓN GENERAL ===
    def _setup_tab_cierre_mensual(self) -> None:
        """UI para ejecutar el cierre contable mensual y bloquear períodos."""
        from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QGroupBox,
                                      QLabel, QPushButton, QTableWidget,
                                      QTableWidgetItem, QHeaderView,
                                      QAbstractItemView, QDateEdit)
        from PyQt5.QtCore import QDate, Qt

        lay = QVBoxLayout(self.tab_cierre_mensual)
        lay.setContentsMargins(12, 12, 12, 12)

        info = QLabel(
            "El cierre mensual consolida las ventas, compras y mermas del período "
            "y bloquea esos registros para que no puedan modificarse retroactivamente.")
        info.setWordWrap(True)
        info.setObjectName("infoBox")
        lay.addWidget(info)

        # ── Ejecutar cierre ───────────────────────────────────────────────────
        grp_exec = QGroupBox("Ejecutar Cierre del Mes")
        grp_exec.setObjectName("styledGroup")
        exec_lay = QHBoxLayout(grp_exec)

        lbl_periodo = QLabel("Mes a cerrar:")
        self._dte_cierre = QDateEdit()
        self._dte_cierre.setDate(QDate.currentDate().addMonths(-1))
        self._dte_cierre.setDisplayFormat("yyyy-MM")
        self._dte_cierre.setCalendarPopup(True)
        self._dte_cierre.setObjectName("inputField")

        btn_cerrar = QPushButton("🔒 Ejecutar Cierre Mensual")
        btn_cerrar = create_danger_button(self, btn_cerrar.text(), "Ejecutar cierre mensual de forma irreversible")
        btn_cerrar.clicked.connect(self._ejecutar_cierre_mensual)

        self._lbl_cierre_status = QLabel("")
        exec_lay.addWidget(lbl_periodo)
        exec_lay.addWidget(self._dte_cierre)
        exec_lay.addWidget(btn_cerrar)
        exec_lay.addWidget(self._lbl_cierre_status)
        exec_lay.addStretch()
        lay.addWidget(grp_exec)

        # ── Historial de cierres ──────────────────────────────────────────────
        grp_hist = QGroupBox("Historial de Cierres")
        grp_hist.setObjectName("styledGroup")
        hist_lay = QVBoxLayout(grp_hist)

        self._tbl_cierres = QTableWidget()
        self._tbl_cierres.setColumnCount(6)
        self._tbl_cierres.setHorizontalHeaderLabels(
            ["Período","Cerrado por","Fecha cierre","Ventas","Compras","Merma"])
        hh = self._tbl_cierres.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        for c in (2,3,4,5): hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self._tbl_cierres.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_cierres.setAlternatingRowColors(True)
        self._tbl_cierres.verticalHeader().setVisible(False)
        hist_lay.addWidget(self._tbl_cierres)
        lay.addWidget(grp_hist)

        self._cargar_historial_cierres()

    def _ejecutar_cierre_mensual(self) -> None:
        """Calcula y guarda el cierre del período seleccionado."""
        from PyQt5.QtWidgets import QMessageBox
        periodo = self._dte_cierre.date().toString("yyyy-MM")
        usuario = getattr(self, 'usuario_actual', 'Sistema')

        # Check if already closed
        try:
            existing = self.conexion.execute(
                "SELECT id FROM cierre_mensual WHERE periodo=?", (periodo,)
            ).fetchone()
            if existing:
                QMessageBox.warning(self, "Ya cerrado",
                    f"El período {periodo} ya fue cerrado anteriormente.")
                return
        except Exception:
            pass

        # Confirm
        resp = QMessageBox.question(
            self, "Confirmar Cierre",
            f"Ejecutar el cierre contable de {periodo}\n\n"
            "Esto consolidara ventas, compras y mermas del mes.\n"
            "Los registros quedaran bloqueados.",
            QMessageBox.Yes | QMessageBox.No)
        if resp != QMessageBox.Yes:
            return

        try:
            # Calculate totals for the period
            inicio = f"{periodo}-01"
            if periodo[5:] == "12":
                fin = f"{int(periodo[:4])+1}-01-01"
            else:
                fin = f"{periodo[:4]}-{int(periodo[5:])+1:02d}-01"

            r_ventas = self.conexion.execute(
                "SELECT COALESCE(SUM(total),0) FROM ventas "
                "WHERE fecha>=? AND fecha<? AND estado='completada'",
                (inicio, fin)).fetchone()
            total_ventas = float(r_ventas[0] if r_ventas else 0)

            r_compras = self.conexion.execute(
                "SELECT COALESCE(SUM(total),0) FROM compras WHERE fecha>=? AND fecha<?",
                (inicio, fin)).fetchone()
            total_compras = float(r_compras[0] if r_compras else 0)

            # mermas doesn't have valor_perdida; approximate with products.precio_compra
            r_merma = self.conexion.execute("""
                SELECT COALESCE(SUM(m.cantidad * COALESCE(p.precio_compra, 0)), 0)
                FROM mermas m
                LEFT JOIN productos p ON p.id = m.producto_id
                WHERE m.created_at >= ? AND m.created_at < ?
            """, (inicio, fin)).fetchone()
            total_merma = float(r_merma[0] if r_merma else 0)

            # Save cierre
            self.conexion.execute("""
                INSERT INTO cierre_mensual
                    (periodo, cerrado_por, total_ventas, total_compras,
                     total_merma, sucursal_id)
                VALUES (?,?,?,?,?,?)
            """, (periodo, usuario, total_ventas, total_compras,
                  total_merma,
                  getattr(self, 'sucursal_id', 1)))
            try: self.conexion.commit()
            except Exception: pass

            self._lbl_cierre_status.setText(
                f"✅ {periodo} cerrado — Ventas ${total_ventas:,.2f}")
            self._lbl_cierre_status.setObjectName("textSuccess")
            self._cargar_historial_cierres()
            from PyQt5.QtWidgets import QMessageBox as _QMB
            _QMB.information(self, "Cierre ejecutado",
                f"Periodo {periodo} cerrado. "
                f"Ventas: ${total_ventas:,.2f} | "
                f"Compras: ${total_compras:,.2f} | "
                f"Merma: ${total_merma:,.2f}")
        except Exception as e:
            from PyQt5.QtWidgets import QMessageBox as _QMB
            _QMB.critical(self, "Error", str(e))
            self._lbl_cierre_status.setText(f"❌ {e}")
            self._lbl_cierre_status.setObjectName("textDanger")

    def _cargar_historial_cierres(self) -> None:
        """Loads the cierre_mensual history table."""
        if not hasattr(self, '_tbl_cierres'): return
        self._tbl_cierres.setRowCount(0)
        try:
            rows = self.conexion.execute("""
                SELECT periodo, cerrado_por, fecha_cierre,
                       total_ventas, total_compras, total_merma
                FROM cierre_mensual
                ORDER BY periodo DESC LIMIT 24
            """).fetchall()
        except Exception:
            return
        for ri, r in enumerate(rows):
            self._tbl_cierres.insertRow(ri)
            vals = [
                str(r[0] or ""), str(r[1] or ""),
                str(r[2] or "")[:16],
                f"${float(r[3] or 0):,.2f}",
                f"${float(r[4] or 0):,.2f}",
                f"${float(r[5] or 0):,.2f}",
            ]
            from PyQt5.QtWidgets import QTableWidgetItem
            from PyQt5.QtCore import Qt
            for ci, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self._tbl_cierres.setItem(ri, ci, it)

    def cargar_configuraciones_general(self):
        """Carga la configuración general desde la base de datos"""
        try:
            cursor = self.conexion.cursor()
            
            # v13.30: Cargar estado dark mode
            cursor.execute("SELECT valor FROM configuraciones WHERE clave = 'tema'")
            resultado = cursor.fetchone()
            is_dark = False
            if resultado and resultado[0]:
                is_dark = 'dark' in str(resultado[0]).lower()
            if hasattr(self, 'chk_dark_mode'):
                self.chk_dark_mode.blockSignals(True)
                self.chk_dark_mode.setChecked(is_dark)
                self.chk_dark_mode.blockSignals(False)
            
            # Cargar impuesto
            cursor.execute("SELECT valor FROM configuraciones WHERE clave = 'impuesto_por_defecto'")
            resultado = cursor.fetchone()
            if resultado:
                self.spin_impuesto.setValue(float(resultado[0]))
            else:
                self.spin_impuesto.setValue(16.0)
            
            # Cargar seguridad
            cursor.execute("SELECT valor FROM configuraciones WHERE clave = 'requerir_admin'")
            resultado = cursor.fetchone()
            if resultado:
                self.chk_requerir_admin.setChecked(resultado[0].lower() == 'true')
                
        except sqlite3.Error as e:
            self.mostrar_mensaje("Error", f"Error al cargar configuración general: {str(e)}", QMessageBox.Critical)

    def _toggle_dark_mode(self, state):
        """v13.30: Toggle dark/light mode — solo cambia colores, no tamaños."""
        tema = "Dark" if state else "Light"
        try:
            self.conexion.execute(
                "INSERT OR REPLACE INTO configuraciones (clave, valor, descripcion) VALUES (?, ?, ?)",
                ('tema', tema, 'Tema de la aplicación'))
            try: self.conexion.commit()
            except Exception: pass
            # Aplicar en tiempo real
            if hasattr(self.main_window, 'aplicar_tema'):
                self.main_window.aplicar_tema(tema)
            elif hasattr(self, 'container') and hasattr(self.container, 'db'):
                from modulos.spj_styles import apply_global_theme
                apply_global_theme(self.container.db)
        except Exception as e:
            self.mostrar_mensaje("Error", f"Error al cambiar tema: {e}", QMessageBox.Critical)

    def aplicar_tema(self):
        """Compat — redirige al toggle."""
        if hasattr(self, 'chk_dark_mode'):
            self._toggle_dark_mode(self.chk_dark_mode.isChecked())

    def guardar_impuesto(self):
        """Guarda la configuración de impuesto"""
        impuesto = self.spin_impuesto.value()
        try:
            cursor = self.conexion.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO configuraciones (clave, valor, descripcion) VALUES (?, ?, ?)",
                ('impuesto_por_defecto', str(impuesto), 'Impuesto por defecto en porcentaje')
            )
            self.conexion.commit()
            self.mostrar_mensaje("Éxito", f"Impuesto por defecto guardado: {impuesto}%")
        except sqlite3.Error as e:
            self.mostrar_mensaje("Error", f"Error al guardar impuesto: {str(e)}", QMessageBox.Critical)

    def guardar_seguridad(self):
        """Guarda la configuración de seguridad"""
        requerir_admin = "True" if self.chk_requerir_admin.isChecked() else "False"
        try:
            cursor = self.conexion.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO configuraciones (clave, valor, descripcion) VALUES (?, ?, ?)",
                ('requerir_admin', requerir_admin, 'Requerir administrador para acciones críticas')
            )
            self.conexion.commit()
            estado = "activada" if self.chk_requerir_admin.isChecked() else "desactivada"
            self.mostrar_mensaje("Éxito", f"Configuración de seguridad {estado} correctamente.")
        except sqlite3.Error as e:
            self.mostrar_mensaje("Error", f"Error al guardar configuración de seguridad: {str(e)}", QMessageBox.Critical)

    # === MÉTODOS DE GESTIÓN DE USUARIOS ===
    def cargar_usuarios(self):
        """Carga la lista de usuarios en la tabla (legacy — redirige a v13 si aplica)."""
        # v13.30: tabla_usuarios ya no se crea (reemplazada por _tbl_usr_v13)
        if not hasattr(self, 'tabla_usuarios'):
            try:
                self._cargar_usuarios_v13()
            except Exception:
                pass
            return
        try:
            cursor = self.conexion.cursor()
            cursor.execute("""
                SELECT id, usuario, nombre, rol, COALESCE(fecha_creacion, fecha_alta, '') as fecha_creacion, COALESCE(activo,1) as activo
                FROM usuarios
                ORDER BY usuario
            """)
            usuarios = cursor.fetchall()

            self.tabla_usuarios.setRowCount(len(usuarios))
            for fila, usuario in enumerate(usuarios):
                for columna, valor in enumerate(usuario):
                    item = QTableWidgetItem(str(valor) if valor is not None else "")
                    
                    # Marcar estado activo/inactivo
                    if columna == 5:  # Columna de estado
                        item.setText("Activo" if valor == 1 else "Inactivo")
                        item.setForeground(QColor("green") if valor == 1 else QColor("red"))
                    
                    self.tabla_usuarios.setItem(fila, columna, item)

            # Ajustar columnas
            self.tabla_usuarios.resizeColumnsToContents()
            
        except sqlite3.Error as e:
            self.mostrar_mensaje("Error", f"Error al cargar usuarios: {str(e)}", QMessageBox.Critical)

    def nuevo_usuario(self):
        """Abre diálogo para crear nuevo usuario"""
        dialogo = DialogoUsuario(self.conexion, self)
        if dialogo.exec_() == QDialog.Accepted:
            self.cargar_usuarios()
            self.registrar_actualizacion("usuario_creado", {"accion": "nuevo_usuario"})

    def editar_usuario(self):
        """Abre diálogo para editar usuario seleccionado"""
        fila = self.tabla_usuarios.currentRow()
        if fila < 0:
            self.mostrar_mensaje("Advertencia", "Seleccione un usuario para editar.")
            return

        try:
            id_usuario = int(self.tabla_usuarios.item(fila, 0).text())
            cursor = self.conexion.cursor()
            cursor.execute("SELECT * FROM usuarios WHERE id = ?", (id_usuario,))
            usuario_data = cursor.fetchone()
            
            if usuario_data:
                columnas = [desc[0] for desc in cursor.description]
                usuario_dict = dict(zip(columnas, usuario_data))
                
                dialogo = DialogoUsuario(self.conexion, self, usuario_dict)
                if dialogo.exec_() == QDialog.Accepted:
                    self.cargar_usuarios()
                    self.registrar_actualizacion("usuario_editado", {"usuario_id": id_usuario})
                    
        except Exception as e:
            self.mostrar_mensaje("Error", f"Error al editar usuario: {str(e)}", QMessageBox.Critical)

    def eliminar_usuario(self):
        """Elimina el usuario seleccionado"""
        fila = self.tabla_usuarios.currentRow()
        if fila < 0:
            self.mostrar_mensaje("Advertencia", "Seleccione un usuario para eliminar.")
            return

        try:
            id_usuario = int(self.tabla_usuarios.item(fila, 0).text())
            nombre_usuario = self.tabla_usuarios.item(fila, 1).text()
            
            # Prevenir eliminación del admin
            if nombre_usuario.lower() == 'admin':
                self.mostrar_mensaje("Error", "No se puede eliminar el usuario administrador principal.")
                return
            
            respuesta = QMessageBox.question(
                self,
                "Confirmar Eliminación",
                f"¿Está seguro que desea eliminar al usuario '{nombre_usuario}'?\n\nEsta acción no se puede deshacer.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if respuesta == QMessageBox.Yes:
                cursor = self.conexion.cursor()
                # SOFT-DELETE: desactivar en lugar de borrar (preserva historial de ventas)
                cursor.execute(
                    "UPDATE usuarios SET activo=0, usuario=usuario||'_baja_'||strftime('%Y%m%d','now') "
                    "WHERE id=?", (id_usuario,))
                self.conexion.commit()
                self.mostrar_mensaje("Éxito",
                    f"Usuario '{nombre_usuario}' desactivado.\n"
                    "Sus registros de auditoría se conservan.")
                self.cargar_usuarios()
                self.registrar_actualizacion("usuario_desactivado",
                    {"usuario_id": id_usuario, "nombre": nombre_usuario})
                
        except Exception as e:
            self.mostrar_mensaje("Error", f"Error al eliminar usuario: {str(e)}", QMessageBox.Critical)

    def actualizar_botones_usuarios(self):
        """Actualiza el estado de los botones según la selección"""
        seleccionado = self.tabla_usuarios.currentRow() >= 0
        self.btn_editar_usuario.setEnabled(seleccionado)
        self.btn_eliminar_usuario.setEnabled(seleccionado)

    # === MÉTODOS DE FIDELIZACIÓN ===
    def cargar_configuraciones_fidelidad(self):
        """Carga la configuración del programa de fidelidad"""
        try:
            cursor = self.conexion.cursor()
            cursor.execute("SELECT * FROM config_programa_fidelidad WHERE id = 1")
            config = cursor.fetchone()
            
            if config:
                nombre = config[1] or "Sin nombre"
                puntos = config[2] or 0
                
                texto_info = f"""
                <b>Programa:</b> {nombre}<br>
                <b>Puntos por $ gastado:</b> {puntos}<br>
                <b>Estado:</b> <span style='color: green'>Activo</span>
                """
                
                if config[3]:  # Niveles
                    niveles = config[3].split(',')
                    texto_info += f"<br><b>Niveles:</b> {', '.join(niveles)}"
                
                self.lbl_info_programa.setText(texto_info)
                self.edit_nombre_programa.setText(nombre)
                self.spin_puntos_por_peso.setValue(float(puntos))
                self.edit_niveles.setText(config[3] or "")
                self.edit_requisitos.setText(config[4] or "")
                self.edit_descuentos.setText(config[5] or "")
            else:
                self.lbl_info_programa.setText("<b>Programa no configurado</b><br>Configure los parámetros del programa de fidelidad.")
                
        except sqlite3.Error as e:
            self.mostrar_mensaje("Error", f"Error al cargar configuración de fidelidad: {str(e)}", QMessageBox.Critical)

    def guardar_configuraciones_fidelidad(self):
        """Guarda la configuración del programa de fidelidad"""
        try:
            nombre_programa = self.edit_nombre_programa.text().strip()
            if not nombre_programa:
                self.mostrar_mensaje("Advertencia", "El nombre del programa es obligatorio.")
                return

            cursor = self.conexion.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO config_programa_fidelidad 
                (id, nombre_programa, puntos_por_peso, niveles, requisitos, descuentos, activo)
                VALUES (1, ?, ?, ?, ?, ?, 1)
            """, (
                nombre_programa,
                self.spin_puntos_por_peso.value(),
                self.edit_niveles.text().strip() or None,
                self.edit_requisitos.text().strip() or None,
                self.edit_descuentos.text().strip() or None
            ))
            
            self.conexion.commit()
            self.mostrar_mensaje("Éxito", "Configuración de fidelidad guardada correctamente.")
            self.cargar_configuraciones_fidelidad()
            self.registrar_actualizacion("config_fidelidad_actualizada", {"programa": nombre_programa})
            
        except sqlite3.Error as e:
            self.mostrar_mensaje("Error", f"Error al guardar configuración de fidelidad: {str(e)}", QMessageBox.Critical)

    def actualizar_datos(self):
        """Actualiza todos los datos del módulo"""
        self.cargar_configuraciones_general()
        self.cargar_usuarios()
        self.cargar_configuraciones_fidelidad()
        self.cargar_sucursales()

    # =========================================================================
    # PESTAÑA DE SUCURSALES
    # =========================================================================
    def crear_tab_sucursales(self):
        """Crea la pestaña de gestión de sucursales."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        # Toolbar
        toolbar = QHBoxLayout()
        btn_nueva = QPushButton("➕ Nueva Sucursal")
        btn_editar = QPushButton("✏️ Editar")
        btn_eliminar = QPushButton("🗑️ Eliminar")
        self.btn_editar_suc   = btn_editar
        self.btn_eliminar_suc = btn_eliminar
        btn_editar.setEnabled(False)
        btn_eliminar.setEnabled(False)

        btn_nueva.clicked.connect(self.nueva_sucursal)
        btn_editar.clicked.connect(self.editar_sucursal)
        btn_eliminar.clicked.connect(self.eliminar_sucursal)

        toolbar.addWidget(btn_nueva)
        toolbar.addWidget(btn_editar)
        toolbar.addWidget(btn_eliminar)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # Tabla
        self.tabla_sucursales = QTableWidget()
        self.tabla_sucursales.setColumnCount(5)
        self.tabla_sucursales.setHorizontalHeaderLabels(
            ["ID", "Nombre", "Dirección", "Teléfono", "Estado"]
        )
        self.tabla_sucursales.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla_sucursales.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla_sucursales.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabla_sucursales.setAlternatingRowColors(True)
        hdr = self.tabla_sucursales.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.tabla_sucursales.itemSelectionChanged.connect(self._actualizar_botones_suc)
        layout.addWidget(self.tabla_sucursales)

        # Info
        info = QLabel("💡 Los cajeros solo verán sus ventas. El administrador puede ver todas las sucursales en Reportes.")
        info.setWordWrap(True)
        info.setObjectName("caption")
        layout.addWidget(info)

        return tab

    def cargar_sucursales(self):
        """Carga la tabla de sucursales."""
        if not hasattr(self, "tabla_sucursales"):
            return
        try:
            rows = self.conexion.execute(
                "SELECT id, nombre, direccion, telefono, activa FROM sucursales ORDER BY id"
            ).fetchall()
            self.tabla_sucursales.setRowCount(len(rows))
            for i, (sid, nombre, direccion, telefono, activa) in enumerate(rows):
                self.tabla_sucursales.setItem(i, 0, QTableWidgetItem(str(sid)))
                self.tabla_sucursales.setItem(i, 1, QTableWidgetItem(nombre or ""))
                self.tabla_sucursales.setItem(i, 2, QTableWidgetItem(direccion or ""))
                self.tabla_sucursales.setItem(i, 3, QTableWidgetItem(telefono or ""))
                estado_item = QTableWidgetItem("✅ Activa" if activa else "❌ Inactiva")
                estado_item.setForeground(QColor("#27ae60") if activa else QColor("#c0392b"))
                self.tabla_sucursales.setItem(i, 4, estado_item)
        except Exception as e:
            print(f"Error cargando sucursales: {e}")

    def _actualizar_botones_suc(self):
        seleccionado = self.tabla_sucursales.currentRow() >= 0
        self.btn_editar_suc.setEnabled(seleccionado)
        self.btn_eliminar_suc.setEnabled(seleccionado)

    def nueva_sucursal(self):
        dlg = DialogoSucursalEdit(self.conexion, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self.cargar_sucursales()
            QMessageBox.information(self, "Éxito", "Sucursal creada correctamente.")

    def editar_sucursal(self):
        fila = self.tabla_sucursales.currentRow()
        if fila < 0:
            return
        sid = int(self.tabla_sucursales.item(fila, 0).text())
        row = self.conexion.execute(
            "SELECT id, nombre, direccion, telefono, activa FROM sucursales WHERE id=?", (sid,)
        ).fetchone()
        if not row:
            return
        data = dict(zip(["id", "nombre", "direccion", "telefono", "activa"], row))
        dlg = DialogoSucursalEdit(self.conexion, sucursal_data=data, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self.cargar_sucursales()
            QMessageBox.information(self, "Éxito", "Sucursal actualizada.")

    def eliminar_sucursal(self):
        fila = self.tabla_sucursales.currentRow()
        if fila < 0:
            return
        sid  = int(self.tabla_sucursales.item(fila, 0).text())
        nombre = self.tabla_sucursales.item(fila, 1).text()
        if sid == 1:
            QMessageBox.warning(self, "No permitido", "No se puede eliminar la sucursal Principal.")
            return
        resp = QMessageBox.question(
            self, "Confirmar",
            f"¿Eliminar la sucursal «{nombre}»?\n\nLas ventas y usuarios asociados quedarán sin sucursal.",
            QMessageBox.Yes | QMessageBox.No
        )
        if resp == QMessageBox.Yes:
            try:
                # SOFT-DELETE: desactivar sucursal (no borrar — las ventas quedarían huérfanas)
                self.conexion.execute(
                    "UPDATE sucursales SET activa=0 WHERE id=?", (sid,))
                self.conexion.commit()
                QMessageBox.information(self, "Desactivada",
                    f"Sucursal «{nombre}» desactivada.\n"
                    "Sus ventas e inventario se conservan. Puede reactivarla editándola.")
                self.cargar_sucursales()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def _setup_tab_whatsapp(self) -> None:
        """
        Tab de configuración WhatsApp multi-canal.
        Gestiona: número principal, número RRHH (opcional), número por sucursal (futuro).
        """
        from PyQt5.QtWidgets import (
            QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
            QLabel, QLineEdit, QComboBox, QPushButton,
            QTableWidget, QTableWidgetItem, QHeaderView,
            QAbstractItemView, QMessageBox, QCheckBox
        )
        lay = QVBoxLayout(self.tab_whatsapp)
        lay.setContentsMargins(12, 10, 12, 10); lay.setSpacing(10)

        info = QLabel(
            "Configura los números de WhatsApp del negocio. "
            "Puedes tener un número para clientes y otro para RRHH. "
            "Agrega uno por sucursal cuando lo necesites."
        )
        info.setWordWrap(True)
        info.setObjectName("caption")
        lay.addWidget(info)

        # ── Tabla de números configurados ─────────────────────────────────────
        self._tbl_wa = QTableWidget()
        self._tbl_wa.setColumnCount(6)
        self._tbl_wa.setHorizontalHeaderLabels([
            "Nombre", "Canal", "Sucursal", "Proveedor", "Número", "Estado"
        ])
        self._tbl_wa.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_wa.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl_wa.verticalHeader().setVisible(False)
        self._tbl_wa.setAlternatingRowColors(True)
        hdr = self._tbl_wa.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1,2,3,4,5): hdr.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        lay.addWidget(self._tbl_wa)

        # ── Formulario agregar/editar ──────────────────────────────────────────
        form_grp = QGroupBox("Agregar / Editar número")
        form_grp.setObjectName("styledGroup")
        form = QFormLayout(form_grp)

        self._wa_txt_nombre = QLineEdit(); self._wa_txt_nombre.setPlaceholderText("Ej: Principal, RRHH")
        self._wa_txt_nombre.setObjectName("inputField")
        self._wa_cmb_canal  = QComboBox()
        self._wa_cmb_canal.addItems(["todos", "clientes", "rrhh", "alertas"])
        self._wa_cmb_canal.setObjectName("inputField")
        self._wa_cmb_prov   = QComboBox()
        self._wa_cmb_prov.addItems(["meta", "twilio", "mock"])
        self._wa_cmb_prov.setObjectName("inputField")
        self._wa_txt_numero = QLineEdit(); self._wa_txt_numero.setPlaceholderText("+521234567890")
        self._wa_txt_numero.setObjectName("inputField")
        self._wa_txt_meta_token = QLineEdit(); self._wa_txt_meta_token.setPlaceholderText("Meta Cloud API token")
        self._wa_txt_meta_token.setEchoMode(QLineEdit.Password)
        self._wa_txt_meta_token.setObjectName("inputField")
        self._wa_txt_phone_id   = QLineEdit(); self._wa_txt_phone_id.setPlaceholderText("Meta Phone ID")
        self._wa_txt_phone_id.setObjectName("inputField")
        self._wa_txt_twilio_sid = QLineEdit(); self._wa_txt_twilio_sid.setPlaceholderText("Twilio Account SID")
        self._wa_txt_twilio_sid.setObjectName("inputField")
        self._wa_txt_twilio_tok = QLineEdit(); self._wa_txt_twilio_tok.setPlaceholderText("Twilio Auth Token")
        self._wa_txt_twilio_tok.setEchoMode(QLineEdit.Password)
        self._wa_txt_twilio_tok.setObjectName("inputField")
        self._wa_chk_activo = QCheckBox("Activo"); self._wa_chk_activo.setChecked(True)

        form.addRow("Nombre*:",        self._wa_txt_nombre)
        form.addRow("Canal*:",         self._wa_cmb_canal)
        form.addRow("Proveedor*:",     self._wa_cmb_prov)
        form.addRow("Número negocio:", self._wa_txt_numero)
        form.addRow("Meta Token:",     self._wa_txt_meta_token)
        form.addRow("Meta Phone ID:",  self._wa_txt_phone_id)
        form.addRow("Twilio SID:",     self._wa_txt_twilio_sid)
        form.addRow("Twilio Token:",   self._wa_txt_twilio_tok)
        form.addRow("",                self._wa_chk_activo)

        btns = QHBoxLayout()
        btn_guardar_wa = QPushButton("💾 Guardar")
        btn_guardar_wa = create_success_button(self, btn_guardar_wa.text(), "Guardar configuración de WhatsApp")
        btn_guardar_wa.clicked.connect(self._guardar_numero_wa)
        btn_del_wa = QPushButton("🗑 Desactivar")
        btn_del_wa = create_secondary_button(self, btn_del_wa.text(), "Desactivar número seleccionado")
        btn_del_wa.clicked.connect(self._desactivar_numero_wa)
        btn_test_wa = QPushButton("🧪 Probar envío")
        btn_test_wa = create_primary_button(self, btn_test_wa.text(), "Enviar mensaje de prueba")
        btn_test_wa.clicked.connect(self._probar_wa)
        btns.addStretch(); btns.addWidget(btn_test_wa)
        btns.addWidget(btn_del_wa); btns.addWidget(btn_guardar_wa)
        form.addRow("", btns)
        lay.addWidget(form_grp)

        self._cargar_tabla_wa()

    def _cargar_tabla_wa(self) -> None:
        from PyQt5.QtWidgets import QTableWidgetItem
        from PyQt5.QtCore import Qt
        try:
            rows = self.conexion.execute(
                "SELECT id, nombre, canal, sucursal_id, proveedor, numero_negocio, activo "
                "FROM whatsapp_numeros ORDER BY id"
            ).fetchall()
            self._tbl_wa.setRowCount(len(rows))
            for ri, r in enumerate(rows):
                suc = str(r[3]) if r[3] else "Global"
                vals = [str(r[1]), str(r[2]), suc, str(r[4]),
                        str(r[5] or "—"), "✅ Activo" if r[6] else "❌ Inactivo"]
                for ci, v in enumerate(vals):
                    it = QTableWidgetItem(v); it.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)
                    if ci == 0: it.setData(Qt.UserRole, r[0])
                    self._tbl_wa.setItem(ri, ci, it)
        except Exception as e:
            pass  # Tabla no existe aún — se crea con migración 042

    def _guardar_numero_wa(self) -> None:
        # [spj-dedup removed local QMessageBox import]
        nombre  = self._wa_txt_nombre.text().strip()
        canal   = self._wa_cmb_canal.currentText()
        prov    = self._wa_cmb_prov.currentText()
        numero  = self._wa_txt_numero.text().strip()
        meta_t  = self._wa_txt_meta_token.text().strip()
        meta_p  = self._wa_txt_phone_id.text().strip()
        twi_s   = self._wa_txt_twilio_sid.text().strip()
        twi_t   = self._wa_txt_twilio_tok.text().strip()
        activo  = int(self._wa_chk_activo.isChecked())
        if not nombre:
            QMessageBox.warning(self, "Aviso", "El nombre es obligatorio."); return
        try:
            self.conexion.execute("""
                INSERT INTO whatsapp_numeros
                    (nombre, canal, proveedor, numero_negocio,
                     meta_token, meta_phone_id, twilio_sid, twilio_token, activo)
                VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT DO NOTHING
            """, (nombre, canal, prov, numero or None,
                  meta_t or None, meta_p or None,
                  twi_s or None, twi_t or None, activo))
            self.conexion.commit()
            self._cargar_tabla_wa()
            QMessageBox.information(self, "Guardado", f"Número «{nombre}» guardado.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _desactivar_numero_wa(self) -> None:
        from PyQt5.QtCore import Qt
        # [spj-dedup removed local QMessageBox import]
        row = self._tbl_wa.currentRow()
        if row < 0: return
        nid = self._tbl_wa.item(row, 0).data(Qt.UserRole) if self._tbl_wa.item(row,0) else None
        if not nid: return
        try:
            self.conexion.execute("UPDATE whatsapp_numeros SET activo=0 WHERE id=?", (nid,))
            self.conexion.commit(); self._cargar_tabla_wa()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _probar_wa(self) -> None:
        # [spj-dedup removed local QMessageBox import]
        numero, ok = QInputDialog.getText(
            self, "Probar WhatsApp", "Número destino (+521234567890):")
        if not ok or not numero.strip(): return
        try:
            from core.services.whatsapp_service import WhatsAppService
            svc = WhatsAppService(conn=self.conexion)
            svc.send_message(phone_number=numero.strip(),
                            message="✅ Prueba de conexión SPJ POS. Si recibes este mensaje, WhatsApp está configurado correctamente.")
            QMessageBox.information(self, "Enviado", "Mensaje de prueba encolado. Revisa el teléfono en unos segundos.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


    def _setup_tab_comisiones(self) -> None:
        """Tab configuración de comisiones por vendedor."""
        from PyQt5.QtWidgets import (
            QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
            QLabel, QDoubleSpinBox, QPushButton, QCheckBox,
            QTableWidget, QTableWidgetItem, QHeaderView,
            QAbstractItemView, QMessageBox, QComboBox
        )
        from PyQt5.QtCore import Qt
        lay = QVBoxLayout(self.tab_comisiones)
        lay.setContentsMargins(12, 10, 12, 10); lay.setSpacing(10)

        info = QLabel(
            "Configura el porcentaje de comisión por venta para cada cajero/vendedor. "
            "El widget de comisión se muestra automáticamente en el POS cuando está activo."
        )
        info.setWordWrap(True)
        info.setObjectName("caption")
        lay.addWidget(info)

        # Tabla de comisiones
        self._tbl_com = QTableWidget()
        self._tbl_com.setColumnCount(4)
        self._tbl_com.setHorizontalHeaderLabels(
            ["Usuario", "% Comisión", "Activo", "Acciones"])
        self._tbl_com.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_com.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl_com.verticalHeader().setVisible(False)
        self._tbl_com.setAlternatingRowColors(True)
        hh = self._tbl_com.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1,2,3): hh.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        lay.addWidget(self._tbl_com)

        # Formulario agregar
        grp = QGroupBox("Agregar / Editar comisión")
        form = QFormLayout(grp)
        self._com_cmb_usuario = QComboBox()
        self._cargar_usuarios_combo()
        self._com_spin_pct = QDoubleSpinBox()
        self._com_spin_pct.setRange(0, 50); self._com_spin_pct.setValue(0.5)
        self._com_spin_pct.setSuffix("%"); self._com_spin_pct.setDecimals(2)
        self._com_chk_activo = QCheckBox("Activo"); self._com_chk_activo.setChecked(True)
        form.addRow("Usuario:", self._com_cmb_usuario)
        form.addRow("% Comisión:", self._com_spin_pct)
        form.addRow("", self._com_chk_activo)
        btn_row = QHBoxLayout()
        btn_save = QPushButton("💾 Guardar")
        btn_save.setObjectName("successBtn")
        apply_tooltip(btn_save, "Guardar configuración de comisión")
        btn_save.clicked.connect(self._guardar_comision)
        btn_row.addStretch(); btn_row.addWidget(btn_save)
        form.addRow("", btn_row)
        lay.addWidget(grp)
        self._cargar_tabla_comisiones()

    def _cargar_usuarios_combo(self):
        try:
            rows = self.conexion.execute(
                "SELECT username FROM usuarios WHERE activo=1 ORDER BY username"
            ).fetchall()
            self._com_cmb_usuario.clear()
            for r in rows:
                self._com_cmb_usuario.addItem(r[0])
        except Exception:
            pass

    def _cargar_tabla_comisiones(self):
        from PyQt5.QtWidgets import QPushButton, QTableWidgetItem
        from PyQt5.QtCore import Qt
        try:
            cs = getattr(self.container, 'comisiones_service', None)
            rows = cs.get_todos() if cs else []
        except Exception:
            rows = []
        self._tbl_com.setRowCount(len(rows))
        for ri, r in enumerate(rows):
            vals = [r['usuario'], f"{float(r['pct_comision']):.2f}%",
                    "✅ Sí" if r['activo'] else "❌ No"]
            for ci, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                if ci == 0: it.setData(Qt.UserRole, r['usuario'])
                self._tbl_com.setItem(ri, ci, it)
            btn_tog = QPushButton("Desactivar" if r['activo'] else "Activar")
            btn_tog.clicked.connect(
                lambda _, u=r['usuario'], a=r['activo']:
                    self._toggle_comision(u, not a))
            self._tbl_com.setCellWidget(ri, 3, btn_tog)

    def _guardar_comision(self):
        # [spj-dedup removed local QMessageBox import]
        usuario = self._com_cmb_usuario.currentText()
        pct     = self._com_spin_pct.value()
        activo  = self._com_chk_activo.isChecked()
        if not usuario:
            QMessageBox.warning(self, "Aviso", "Selecciona un usuario."); return
        try:
            cs = getattr(self.container, 'comisiones_service', None)
            if cs:
                cs.set_config(usuario, pct, activo)
                self._cargar_tabla_comisiones()
                QMessageBox.information(self, "✅ Guardado",
                    f"Comisión de {pct:.2f}% configurada para {usuario}.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _toggle_comision(self, usuario: str, activo: bool):
        try:
            cs = getattr(self.container, 'comisiones_service', None)
            if cs:
                cs.toggle_activo(usuario, activo)
                self._cargar_tabla_comisiones()
        except Exception as e:
        # [spj-dedup removed local QMessageBox import]
            QMessageBox.critical(self, "Error", str(e))


    def _setup_tab_happy_hour(self) -> None:
        """Tab configuración de Happy Hour y difusión WhatsApp."""
        from PyQt5.QtWidgets import (
            QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
            QLabel, QLineEdit, QDoubleSpinBox, QPushButton,
            QTableWidget, QTableWidgetItem, QHeaderView,
            QAbstractItemView, QMessageBox, QComboBox,
            QTextEdit, QCheckBox
        )
        from PyQt5.QtCore import Qt
        lay = QVBoxLayout(self.tab_happy_hour)
        lay.setContentsMargins(12, 10, 12, 10); lay.setSpacing(10)

        info = QLabel(
            "Define descuentos por horario (Happy Hour). "
            "Activa 'Enviar WhatsApp' para notificar a todos los clientes "
            "con teléfono registrado cuando inicie la promoción."
        )
        info.setWordWrap(True)
        info.setObjectName("caption")
        lay.addWidget(info)

        # Tabla de reglas
        self._tbl_hh = QTableWidget()
        self._tbl_hh.setColumnCount(7)
        self._tbl_hh.setHorizontalHeaderLabels(
            ["Nombre", "Hora ini", "Hora fin", "Días", "Descuento", "Activo", "Acciones"])
        self._tbl_hh.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_hh.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl_hh.verticalHeader().setVisible(False)
        self._tbl_hh.setAlternatingRowColors(True)
        hh = self._tbl_hh.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        lay.addWidget(self._tbl_hh)

        # Formulario
        grp = QGroupBox("Nueva regla Happy Hour")
        form = QFormLayout(grp)
        self._hh_txt_nombre   = QLineEdit(); self._hh_txt_nombre.setPlaceholderText("Ej: Tarde feliz pollería")
        self._hh_txt_ini      = QLineEdit("14:00"); self._hh_txt_ini.setPlaceholderText("HH:MM")
        self._hh_txt_fin      = QLineEdit("16:00"); self._hh_txt_fin.setPlaceholderText("HH:MM")
        self._hh_txt_dias     = QLineEdit("0,1,2,3,4"); self._hh_txt_dias.setPlaceholderText("0=lun…6=dom, CSV")
        self._hh_cmb_tipo     = QComboBox()
        self._hh_cmb_tipo.addItems(["porcentaje", "monto_fijo"])
        self._hh_spin_valor   = QDoubleSpinBox()
        self._hh_spin_valor.setRange(1, 100); self._hh_spin_valor.setValue(15); self._hh_spin_valor.setDecimals(1)
        self._hh_cmb_aplica   = QComboBox()
        self._hh_cmb_aplica.addItems(["todos", "categoria", "producto_id"])
        self._hh_txt_aplica_val = QLineEdit(); self._hh_txt_aplica_val.setPlaceholderText("nombre de categoría o ID de producto")
        self._hh_txt_msg_wa   = QTextEdit()
        self._hh_txt_msg_wa.setMaximumHeight(70)
        self._hh_txt_msg_wa.setPlaceholderText(
            "Hola {nombre}! 🎉 Tenemos {promo}: {valor} off "
            "de {hora_ini} a {hora_fin}. ¡Ven y aprovecha!")
        self._hh_chk_enviar_wa = QCheckBox("Enviar WhatsApp a clientes al activarse")

        form.addRow("Nombre*:", self._hh_txt_nombre)
        form.addRow("Hora inicio:", self._hh_txt_ini)
        form.addRow("Hora fin:", self._hh_txt_fin)
        form.addRow("Días (CSV):", self._hh_txt_dias)
        form.addRow("Tipo descuento:", self._hh_cmb_tipo)
        form.addRow("Valor:", self._hh_spin_valor)
        form.addRow("Aplica a:", self._hh_cmb_aplica)
        form.addRow("Valor aplica:", self._hh_txt_aplica_val)
        form.addRow("Mensaje WA:", self._hh_txt_msg_wa)
        form.addRow("", self._hh_chk_enviar_wa)

        btn_row = QHBoxLayout()
        btn_save = QPushButton("💾 Guardar regla")
        btn_save.setObjectName("warningBtn")
        apply_tooltip(btn_save, "Guardar regla de Happy Hour")
        btn_save.clicked.connect(self._guardar_happy_hour)
        btn_enviar = QPushButton("📣 Enviar promo ahora")
        btn_enviar.setToolTip("Envía el mensaje de la regla seleccionada a todos los clientes con teléfono")
        btn_enviar.clicked.connect(self._enviar_promo_ahora)
        btn_row.addStretch(); btn_row.addWidget(btn_enviar); btn_row.addWidget(btn_save)
        form.addRow("", btn_row)
        lay.addWidget(grp)
        self._cargar_tabla_hh()

    def _cargar_tabla_hh(self):
        from PyQt5.QtWidgets import QPushButton, QTableWidgetItem
        from PyQt5.QtCore import Qt
        try:
            hs = getattr(self.container, 'happy_hour_service', None)
            rows = hs.get_reglas() if hs else []
        except Exception:
            rows = []
        self._tbl_hh.setRowCount(len(rows))
        for ri, r in enumerate(rows):
            desc = f"{float(r.get('valor',0)):.0f}{'%' if r.get('tipo_descuento')=='porcentaje' else ' MXN'}"
            vals = [r.get('nombre',''), r.get('hora_inicio',''),
                    r.get('hora_fin',''), r.get('dias_semana',''),
                    desc, "✅" if r.get('activo') else "❌"]
            for ci, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                if ci == 0: it.setData(Qt.UserRole, r.get('id'))
                self._tbl_hh.setItem(ri, ci, it)
            btn_tog = QPushButton("Desactivar" if r.get('activo') else "Activar")
            btn_tog.clicked.connect(
                lambda _, rid=r.get('id'), a=r.get('activo'):
                    self._toggle_hh(rid, not a))
            self._tbl_hh.setCellWidget(ri, 6, btn_tog)

    def _guardar_happy_hour(self):
        # [spj-dedup removed local QMessageBox import]
        nombre = self._hh_txt_nombre.text().strip()
        if not nombre:
            QMessageBox.warning(self, "Aviso", "El nombre es obligatorio."); return
        try:
            hs = getattr(self.container, 'happy_hour_service', None)
            if not hs:
                QMessageBox.warning(self, "Aviso", "HappyHourService no disponible."); return
            msg_wa = self._hh_txt_msg_wa.toPlainText().strip() or None
            rid = hs.crear_regla(
                nombre      = nombre,
                hora_inicio = self._hh_txt_ini.text().strip(),
                hora_fin    = self._hh_txt_fin.text().strip(),
                dias        = self._hh_txt_dias.text().strip() or "0,1,2,3,4,5,6",
                tipo        = self._hh_cmb_tipo.currentText(),
                valor       = self._hh_spin_valor.value(),
                aplica_a    = self._hh_cmb_aplica.currentText(),
                aplica_valor= self._hh_txt_aplica_val.text().strip() or None,
                mensaje_wa  = msg_wa,
            )
            self._cargar_tabla_hh()
            # Enviar WhatsApp si el checkbox está activo
            if self._hh_chk_enviar_wa.isChecked() and msg_wa:
                enviados = hs.enviar_promo_whatsapp(rid, limite=200)
                QMessageBox.information(self, "✅ Guardado",
                    f"Regla «{nombre}» creada.\n"
                    f"Mensaje enviado a {enviados} clientes por WhatsApp.")
            else:
                QMessageBox.information(self, "✅ Guardado",
                    f"Regla «{nombre}» creada exitosamente.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _toggle_hh(self, regla_id: int, activo: bool):
        try:
            hs = getattr(self.container, 'happy_hour_service', None)
            if hs: hs.toggle_regla(regla_id, activo)
            self._cargar_tabla_hh()
        except Exception as e:
        # [spj-dedup removed local QMessageBox import]
            QMessageBox.critical(self, "Error", str(e))

    def _enviar_promo_ahora(self):
        # [spj-dedup removed local QMessageBox import]
        row = self._tbl_hh.currentRow()
        if row < 0:
            QMessageBox.information(self, "Aviso", "Selecciona una regla primero."); return
        it = self._tbl_hh.item(row, 0)
        if not it: return
        from PyQt5.QtCore import Qt
        rid = it.data(Qt.UserRole)
        if not rid: return
        try:
            hs = getattr(self.container, 'happy_hour_service', None)
            if not hs:
                QMessageBox.warning(self, "Aviso", "HappyHourService no disponible."); return
            enviados = hs.enviar_promo_whatsapp(int(rid), limite=500)
            QMessageBox.information(self, "📣 Enviado",
                f"{enviados} mensajes WhatsApp encolados.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    # ══════════════════════════════════════════════════════════════════════
    # TAB: 🏢 Empresa / Fiscal
    # ══════════════════════════════════════════════════════════════════════
    def _setup_tab_empresa(self) -> None:
        from PyQt5.QtWidgets import (
            QVBoxLayout, QFormLayout, QGroupBox, QLabel,
            QLineEdit, QPushButton, QHBoxLayout, QFileDialog, QMessageBox,
            QComboBox
        )
        from PyQt5.QtCore import Qt
        lay = QVBoxLayout(self.tab_empresa)
        lay.setContentsMargins(12,10,12,10); lay.setSpacing(10)

        grp1 = QGroupBox("Datos del negocio")
        f1   = QFormLayout(grp1)
        self.emp_nombre   = QLineEdit(); self.emp_nombre.setPlaceholderText("Nombre del negocio")
        self.emp_eslogan  = QLineEdit(); self.emp_eslogan.setPlaceholderText("Eslogan o tagline")
        from modulos.spj_phone_widget import PhoneWidget as _PW_emp
        self.emp_telefono = _PW_emp(default_country="+52")
        self.emp_email    = QLineEdit()
        self.emp_web      = QLineEdit()
        self.emp_direccion= QLineEdit()
        f1.addRow("Nombre:*",   self.emp_nombre)
        f1.addRow("Eslogan:",   self.emp_eslogan)
        f1.addRow("Teléfono:",  self.emp_telefono)
        f1.addRow("Email:",     self.emp_email)
        f1.addRow("Web:",       self.emp_web)
        f1.addRow("Dirección:", self.emp_direccion)
        lay.addWidget(grp1)

        grp2 = QGroupBox("Datos fiscales")
        f2   = QFormLayout(grp2)
        self.emp_rfc      = QLineEdit(); self.emp_rfc.setPlaceholderText("RFC del negocio")
        self.emp_regimen  = QLineEdit(); self.emp_regimen.setPlaceholderText("Ej: 601 - General de Ley")
        self.emp_tasa_iva = QLineEdit(); self.emp_tasa_iva.setPlaceholderText("0 para carnes, 16 para otros")
        f2.addRow("RFC:",          self.emp_rfc)
        f2.addRow("Régimen fiscal:", self.emp_regimen)
        f2.addRow("Tasa IVA (%):", self.emp_tasa_iva)
        lay.addWidget(grp2)

        grp3 = QGroupBox("Logo")
        f3   = QFormLayout(grp3)
        self.emp_logo_path = QLineEdit(); self.emp_logo_path.setReadOnly(True)
        self.emp_logo_path.setPlaceholderText("(sin logo cargado)")
        btn_logo = QPushButton("📁 Seleccionar logo...")
        btn_logo.clicked.connect(self._seleccionar_logo)
        logo_row = QHBoxLayout()
        logo_row.addWidget(self.emp_logo_path, 1); logo_row.addWidget(btn_logo)
        f3.addRow("Archivo:", logo_row)
        lay.addWidget(grp3)

        # v13.30: Sucursal de esta instalación
        grp4 = QGroupBox("📍 Sucursal de esta terminal")
        f4   = QFormLayout(grp4)
        self.cmb_sucursal_inst = QComboBox()
        self.cmb_sucursal_inst.setToolTip(
            "Define a qué sucursal pertenece esta computadora.\n"
            "Todos los usuarios que inicien sesión aquí operarán en esta sucursal.")
        f4.addRow("Sucursal:", self.cmb_sucursal_inst)
        lbl_info_suc = QLabel(
            "⚠️ Esta configuración determina la sucursal para TODA esta terminal.\n"
            "Inventario, ventas y caja se filtrarán por esta sucursal.")
        lbl_info_suc.setWordWrap(True)
        lbl_info_suc.setObjectName("textWarning")
        f4.addRow("", lbl_info_suc)
        lay.addWidget(grp4)

        btn_save = QPushButton("💾 Guardar datos de empresa")
        btn_save.setObjectName("successBtn")
        apply_tooltip(btn_save, "Guardar configuración de empresa")
        btn_save.clicked.connect(self._guardar_empresa)
        lay.addWidget(btn_save, 0, Qt.AlignRight)
        lay.addStretch()
        self._cargar_empresa()

    def _cargar_empresa(self):
        claves = {
            'nombre_empresa': self.emp_nombre,
            'eslogan_empresa': self.emp_eslogan,
            'email_empresa': self.emp_email,
            'web_empresa': self.emp_web,
            'direccion': self.emp_direccion,
            'rfc': self.emp_rfc,
            'regimen_fiscal': self.emp_regimen,
            'logo_path': self.emp_logo_path,
        }
        for clave, widget in claves.items():
            try:
                row = self.conexion.execute(
                    "SELECT valor FROM configuraciones WHERE clave=?", (clave,)
                ).fetchone()
                if row and row[0]:
                    widget.setText(str(row[0]))
            except Exception:
                pass
        # v13.30: PhoneWidget usa set_phone() en lugar de setText()
        try:
            row = self.conexion.execute(
                "SELECT valor FROM configuraciones WHERE clave='telefono_empresa'"
            ).fetchone()
            if row and row[0]:
                self.emp_telefono.set_phone(str(row[0]))
        except Exception:
            pass
        try:
            row = self.conexion.execute(
                "SELECT valor FROM configuraciones WHERE clave='tasa_iva'"
            ).fetchone()
            self.emp_tasa_iva.setText(str(float(row[0])*100 if row else "0"))
        except Exception:
            pass
        # v13.30: Cargar sucursales en combo
        try:
            self.cmb_sucursal_inst.clear()
            sucs = self.conexion.execute(
                "SELECT id, nombre FROM sucursales WHERE activa=1 ORDER BY nombre"
            ).fetchall()
            if not sucs:
                self.cmb_sucursal_inst.addItem("Principal", 1)
            else:
                for s in sucs:
                    self.cmb_sucursal_inst.addItem(s['nombre'], s['id'])
            # Seleccionar la configurada
            row_suc = self.conexion.execute(
                "SELECT valor FROM configuraciones WHERE clave='sucursal_instalacion_id'"
            ).fetchone()
            suc_id = int(row_suc[0]) if row_suc and row_suc[0] else 1
            for i in range(self.cmb_sucursal_inst.count()):
                if self.cmb_sucursal_inst.itemData(i) == suc_id:
                    self.cmb_sucursal_inst.setCurrentIndex(i)
                    break
        except Exception:
            pass

    def _guardar_empresa(self):
        # v13.30: Verificar permiso
        try:
            from core.permissions import verificar_permiso
            _ctr = self.container if hasattr(self, 'container') else None
            if _ctr and not verificar_permiso(_ctr, "config.editar", self):
                return
        except Exception: pass
        # [spj-dedup removed local QMessageBox import]
        nombre = self.emp_nombre.text().strip()
        if not nombre:
            QMessageBox.warning(self, "Aviso", "El nombre del negocio es obligatorio."); return
        datos = {
            'nombre_empresa':   nombre,
            'eslogan_empresa':  self.emp_eslogan.text().strip(),
            'telefono_empresa': self.emp_telefono.get_e164().strip(),
            'email_empresa':    self.emp_email.text().strip(),
            'web_empresa':      self.emp_web.text().strip(),
            'direccion':        self.emp_direccion.text().strip(),
            'rfc':              self.emp_rfc.text().strip().upper(),
            'regimen_fiscal':   self.emp_regimen.text().strip(),
            'logo_path':        self.emp_logo_path.text().strip(),
        }
        try:
            tasa_pct = float(self.emp_tasa_iva.text().replace(',','.') or '0')
            datos['tasa_iva'] = str(tasa_pct / 100)
        except Exception:
            datos['tasa_iva'] = '0'
        try:
            for clave, valor in datos.items():
                self.conexion.execute(
                    "INSERT OR REPLACE INTO configuraciones(clave,valor) VALUES(?,?)",
                    (clave, valor))
            # v13.30: Guardar sucursal de la instalación
            if hasattr(self, 'cmb_sucursal_inst'):
                suc_id = self.cmb_sucursal_inst.currentData()
                if suc_id:
                    self.conexion.execute(
                        "INSERT OR REPLACE INTO configuraciones(clave,valor) VALUES(?,?)",
                        ('sucursal_instalacion_id', str(suc_id)))
            self.conexion.commit()
            QMessageBox.information(self, "✅ Guardado",
                "Datos de empresa guardados.\n"
                "La sucursal de esta terminal se aplicará en el próximo inicio de sesión.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _seleccionar_logo(self):
        from PyQt5.QtWidgets import QFileDialog
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar logo", "", "Imágenes (*.png *.jpg *.jpeg *.svg)")
        if ruta:
            self.emp_logo_path.setText(ruta)

    # ══════════════════════════════════════════════════════════════════════
    # TAB: 🎨 Apariencia — ThemeService completo
    # ══════════════════════════════════════════════════════════════════════
    def _setup_tab_apariencia(self) -> None:
        from PyQt5.QtWidgets import (
            QVBoxLayout, QFormLayout, QGroupBox, QComboBox,
            QPushButton, QLabel, QSpinBox, QHBoxLayout
        )
        from PyQt5.QtCore import Qt
        lay = QVBoxLayout(self.tab_apariencia)
        lay.setContentsMargins(12,10,12,10); lay.setSpacing(12)

        grp = QGroupBox("Apariencia de la interfaz")
        form = QFormLayout(grp)

        self.ap_combo_tema = QComboBox()
        self.ap_combo_tema.addItems(["Claro", "Oscuro"])
        self.ap_combo_tema.setToolTip("Tema de colores del sistema\nClaro: fondo blanco, texto oscuro\nOscuro: fondo oscuro, texto claro")

        self.ap_combo_densidad = QComboBox()
        self.ap_combo_densidad.addItems(["Compact", "Normal", "Comfortable"])
        self.ap_combo_densidad.setToolTip("Espaciado y altura de elementos\nCompact: más datos en pantalla\nComfortable: más fácil de usar en táctil")

        self.ap_spin_fuente = QSpinBox()
        self.ap_spin_fuente.setRange(9, 16); self.ap_spin_fuente.setValue(12)
        self.ap_spin_fuente.setSuffix(" pt")

        self.ap_spin_iconos = QSpinBox()
        self.ap_spin_iconos.setRange(16, 48); self.ap_spin_iconos.setValue(24)
        self.ap_spin_iconos.setSuffix(" px")

        form.addRow("Tema de colores:", self.ap_combo_tema)
        form.addRow("Densidad (espaciado):", self.ap_combo_densidad)
        form.addRow("Tamaño de fuente:", self.ap_spin_fuente)
        form.addRow("Tamaño de iconos:", self.ap_spin_iconos)
        lay.addWidget(grp)

        info = QLabel("Los cambios se aplican en tiempo real sin necesidad de reiniciar.")
        info.setObjectName("textSuccess")
        lay.addWidget(info)

        btn_row = QHBoxLayout()
        btn_preview = QPushButton("👁 Vista previa")
        btn_preview.clicked.connect(self._previsualizar_tema)
        btn_apply = QPushButton("✅ Aplicar ahora")
        btn_apply.setObjectName("primaryBtn")
        apply_tooltip(btn_apply, "Aplicar configuración de apariencia")
        btn_apply.clicked.connect(self._aplicar_apariencia)
        btn_row.addWidget(btn_preview); btn_row.addStretch(); btn_row.addWidget(btn_apply)
        lay.addLayout(btn_row)
        lay.addStretch()
        self._cargar_apariencia()

    def _cargar_apariencia(self):
        try:
            # Cargar tema desde BD (clave='tema') para sincronización global
            from core.db.connection import get_connection
            conn = get_connection()
            row = conn.execute(
                "SELECT valor FROM configuraciones WHERE clave='tema'"
            ).fetchone()
            tema_guardado = row[0] if row else 'Oscuro'
            
            # Normalizar a nombres válidos: Light/Dark → Claro/Oscuro
            tema_normalizado = 'Oscuro' if 'dark' in tema_guardado.lower() or tema_guardado == 'Oscuro' else 'Claro'
            
            densidad = 'Normal'
            fuente = 12
            iconos = 24
            
            # Intentar cargar prefs adicionales de ThemeService si existe
            ts = getattr(self.container, 'theme_service', None) if hasattr(self, 'container') else None
            if ts:
                prefs = ts.get_user_preferences()
                densidad = prefs.get('density', 'Normal')
                fuente = int(prefs.get('font_size', 12))
                iconos = int(prefs.get('icon_size', 24))
            
            # Solo mostrar opciones Claro/Oscuro en el combo
            idx = self.ap_combo_tema.findText(tema_normalizado)
            if idx >= 0: 
                self.ap_combo_tema.setCurrentIndex(idx)
            else:
                # Si el tema guardado no existe, usar Oscuro por defecto
                self.ap_combo_tema.setCurrentIndex(0)
                
            idx2 = self.ap_combo_densidad.findText(densidad)
            if idx2 >= 0: self.ap_combo_densidad.setCurrentIndex(idx2)
            self.ap_spin_fuente.setValue(fuente)
            self.ap_spin_iconos.setValue(iconos)
        except Exception as e:
            logging.getLogger("spj.config").debug("Error cargando apariencia: %s", e)
            pass

    def _previsualizar_tema(self):
        self._aplicar_apariencia(save=False)

    def _aplicar_apariencia(self, save=True):
        from PyQt5.QtWidgets import QApplication, QMessageBox
        # Solo permitir temas Claro u Oscuro
        tema_raw = self.ap_combo_tema.currentText()
        tema = 'Oscuro' if 'dark' in tema_raw.lower() or tema_raw == 'Oscuro' else 'Claro'
        
        densidad = self.ap_combo_densidad.currentText()
        fuente   = str(self.ap_spin_fuente.value())
        iconos   = str(self.ap_spin_iconos.value())
        
        try:
            # 1. Guardar en BD (clave='tema') para persistencia global
            from core.db.connection import get_connection
            conn = get_connection()
            conn.execute(
                "INSERT OR REPLACE INTO configuraciones (clave, valor) VALUES ('tema', ?)",
                (tema,)
            )
            conn.commit()
            
            # 2. Aplicar tema usando theme_engine (fuente única de verdad: config.TEMAS)
            from ui.themes.theme_engine import apply_theme
            app = QApplication.instance()
            apply_theme(app, tema)
            
            # 3. Guardar prefs adicionales en ThemeService si existe
            ts = getattr(self.container, 'theme_service', None) if hasattr(self, 'container') else None
            if ts and save:
                ts.save_preferences(tema, densidad, fuente, iconos)
            
            if save:
                QMessageBox.information(self, "✅ Aplicado",
                    f"Tema '{tema}' aplicado correctamente.\nLos cambios son inmediatos.")
        except Exception as e:
            logging.getLogger("spj.config").error("Error aplicando tema: %s", e)
            QMessageBox.warning(self, "Error", f"No se pudo aplicar el tema:\n{e}")

    # ══════════════════════════════════════════════════════════════════════
    # TAB: 📧 Email / SMTP
    # ══════════════════════════════════════════════════════════════════════
    def _setup_tab_email(self) -> None:
        from PyQt5.QtWidgets import (
            QVBoxLayout, QFormLayout, QGroupBox, QLabel,
            QLineEdit, QPushButton, QHBoxLayout, QSpinBox,
            QCheckBox, QMessageBox
        )
        from PyQt5.QtCore import Qt
        lay = QVBoxLayout(self.tab_email)
        lay.setContentsMargins(12,10,12,10); lay.setSpacing(10)

        grp = QGroupBox("Configuración SMTP para reportes por email")
        form = QFormLayout(grp)
        self.smtp_host    = QLineEdit(); self.smtp_host.setPlaceholderText("smtp.gmail.com")
        self.smtp_port    = QSpinBox(); self.smtp_port.setRange(1,65535); self.smtp_port.setValue(587)
        self.smtp_user    = QLineEdit(); self.smtp_user.setPlaceholderText("usuario@gmail.com")
        self.smtp_pass    = QLineEdit(); self.smtp_pass.setEchoMode(QLineEdit.Password)
        self.smtp_pass.setPlaceholderText("Contraseña o App Password")
        self.smtp_tls     = QCheckBox("Usar TLS (recomendado)"); self.smtp_tls.setChecked(True)
        self.smtp_gerente = QLineEdit(); self.smtp_gerente.setPlaceholderText("gerente@empresa.com")
        form.addRow("Host SMTP:",         self.smtp_host)
        form.addRow("Puerto:",            self.smtp_port)
        form.addRow("Usuario:",           self.smtp_user)
        form.addRow("Contraseña:",        self.smtp_pass)
        form.addRow("",                   self.smtp_tls)
        form.addRow("Email del gerente:", self.smtp_gerente)
        lay.addWidget(grp)

        btn_row = QHBoxLayout()
        btn_test = QPushButton("📧 Enviar correo de prueba")
        btn_test.clicked.connect(self._test_smtp)
        btn_save = QPushButton("💾 Guardar")
        btn_save.setObjectName("successBtn")
        apply_tooltip(btn_save, "Guardar configuración SMTP")
        btn_save.clicked.connect(self._guardar_smtp)
        btn_row.addWidget(btn_test); btn_row.addStretch(); btn_row.addWidget(btn_save)
        lay.addLayout(btn_row)
        lay.addStretch()
        self._cargar_smtp()

    def _cargar_smtp(self):
        campos = {
            'smtp_host': (self.smtp_host, 'setText'),
            'smtp_port': (self.smtp_port, 'setValue'),
            'smtp_user': (self.smtp_user, 'setText'),
            'smtp_password': (self.smtp_pass, 'setText'),
            'email_gerente': (self.smtp_gerente, 'setText'),
        }
        for clave, (widget, method) in campos.items():
            try:
                row = self.conexion.execute(
                    "SELECT valor FROM configuraciones WHERE clave=?", (clave,)
                ).fetchone()
                if row and row[0]:
                    if method == 'setValue':
                        getattr(widget, method)(int(row[0]))
                    else:
                        getattr(widget, method)(str(row[0]))
            except Exception:
                pass

    def _guardar_smtp(self):
        # [spj-dedup removed local QMessageBox import]
        datos = {
            'smtp_host':     self.smtp_host.text().strip(),
            'smtp_port':     str(self.smtp_port.value()),
            'smtp_user':     self.smtp_user.text().strip(),
            'smtp_password': self.smtp_pass.text(),
            'smtp_tls':      '1' if self.smtp_tls.isChecked() else '0',
            'email_gerente': self.smtp_gerente.text().strip(),
        }
        try:
            for k, v in datos.items():
                self.conexion.execute(
                    "INSERT OR REPLACE INTO configuraciones(clave,valor) VALUES(?,?)", (k,v))
            self.conexion.commit()
            QMessageBox.information(self, "✅", "Configuración SMTP guardada.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _test_smtp(self):
        # [spj-dedup removed local QMessageBox import]
        host  = self.smtp_host.text().strip()
        port  = self.smtp_port.value()
        user  = self.smtp_user.text().strip()
        pwd   = self.smtp_pass.text()
        dest  = self.smtp_gerente.text().strip() or user
        if not host or not user:
            QMessageBox.warning(self, "Aviso", "Completa host y usuario primero."); return
        try:
            import smtplib, ssl
            from email.mime.text import MIMEText
            msg = MIMEText("Correo de prueba desde SPJ POS v13. Todo funciona correctamente.")
            msg['Subject'] = "SPJ POS — Prueba de correo"
            msg['From']    = user
            msg['To']      = dest
            ctx = ssl.create_default_context()
            with smtplib.SMTP(host, port, timeout=10) as s:
                s.ehlo()
                if self.smtp_tls.isChecked():
                    s.starttls(context=ctx)
                s.login(user, pwd)
                s.sendmail(user, [dest], msg.as_string())
            QMessageBox.information(self, "✅ Enviado",
                f"Correo de prueba enviado a {dest}.")
        except Exception as e:
            QMessageBox.critical(self, "Error SMTP", str(e))

    # ══════════════════════════════════════════════════════════════════════
    # TAB: 💳 Mercado Pago
    # ══════════════════════════════════════════════════════════════════════
    def _setup_tab_mercadopago(self) -> None:
        from PyQt5.QtWidgets import (
            QVBoxLayout, QFormLayout, QGroupBox, QLabel,
            QLineEdit, QPushButton, QHBoxLayout, QMessageBox
        )
        from PyQt5.QtCore import Qt
        lay = QVBoxLayout(self.tab_mercadopago)
        lay.setContentsMargins(12,10,12,10); lay.setSpacing(10)

        info = QLabel(
            "Configura tus credenciales de Mercado Pago para recibir pagos con link.\n"
            "Obtén el Access Token en: https://www.mercadopago.com.mx/developers/panel"
        )
        info.setWordWrap(True)
        info.setObjectName("caption")
        lay.addWidget(info)

        grp = QGroupBox("Credenciales API")
        form = QFormLayout(grp)
        self.mp_token       = QLineEdit(); self.mp_token.setEchoMode(QLineEdit.Password)
        self.mp_token.setPlaceholderText("APP_USR-xxxx...")
        btn_show = QPushButton("👁")
        btn_show.setFixedWidth(32)
        btn_show.setCheckable(True)
        btn_show.toggled.connect(
            lambda on: self.mp_token.setEchoMode(
                QLineEdit.Normal if on else QLineEdit.Password))
        token_row = QHBoxLayout()
        token_row.addWidget(self.mp_token,1); token_row.addWidget(btn_show)
        self.mp_webhook_url = QLineEdit(); self.mp_webhook_url.setPlaceholderText("https://tudominio.com/mp/webhook")
        self.mp_return_url  = QLineEdit(); self.mp_return_url.setPlaceholderText("https://tudominio.com/mp/gracias")
        self.mp_sandbox     = QLineEdit(); self.mp_sandbox.setPlaceholderText("Vacío = producción; TEST = sandbox")
        form.addRow("Access Token:", token_row)
        form.addRow("URL Webhook:", self.mp_webhook_url)
        form.addRow("URL Retorno:", self.mp_return_url)
        form.addRow("Modo:", self.mp_sandbox)
        lay.addWidget(grp)

        btn_row = QHBoxLayout()
        btn_verify = QPushButton("🔍 Verificar token")
        btn_verify.clicked.connect(self._verificar_mp_token)
        btn_save = QPushButton("💾 Guardar")
        btn_save.setObjectName("accentBtn")
        apply_tooltip(btn_save, "Guardar credenciales de Mercado Pago")
        btn_save.clicked.connect(self._guardar_mp)
        btn_row.addWidget(btn_verify); btn_row.addStretch(); btn_row.addWidget(btn_save)
        lay.addLayout(btn_row)

        self.mp_status_lbl = QLabel("")
        self.mp_status_lbl.setObjectName("caption")
        lay.addWidget(self.mp_status_lbl)
        lay.addStretch()
        self._cargar_mp()

    def _cargar_mp(self):
        claves = {
            'mp_access_token': self.mp_token,
            'mp_webhook_url':  self.mp_webhook_url,
            'mp_return_url':   self.mp_return_url,
        }
        for clave, widget in claves.items():
            try:
                row = self.conexion.execute(
                    "SELECT valor FROM configuraciones WHERE clave=?", (clave,)
                ).fetchone()
                if row and row[0]: widget.setText(str(row[0]))
            except Exception: pass

    def _guardar_mp(self):
        # [spj-dedup removed local QMessageBox import]
        datos = {
            'mp_access_token': self.mp_token.text().strip(),
            'mp_webhook_url':  self.mp_webhook_url.text().strip(),
            'mp_return_url':   self.mp_return_url.text().strip(),
        }
        if not datos['mp_access_token']:
            QMessageBox.warning(self, "Aviso", "El Access Token es obligatorio."); return
        try:
            for k, v in datos.items():
                self.conexion.execute(
                    "INSERT OR REPLACE INTO configuraciones(clave,valor) VALUES(?,?)", (k,v))
            self.conexion.commit()
            QMessageBox.information(self, "✅", "Credenciales de Mercado Pago guardadas.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _verificar_mp_token(self):
        token = self.mp_token.text().strip()
        if not token:
            self.mp_status_lbl.setText("❌ Ingresa el Access Token primero.")
            self.mp_status_lbl.setObjectName("textDanger")
            return
        self.mp_status_lbl.setText("⏳ Verificando...")
        try:
            import urllib.request, json
            req = urllib.request.Request(
                "https://api.mercadopago.com/v1/payment_methods",
                headers={"Authorization": f"Bearer {token}"}
            )
            resp = urllib.request.urlopen(req, timeout=8)
            data = json.loads(resp.read())
            if isinstance(data, list) and len(data) > 0:
                self.mp_status_lbl.setText(f"✅ Token válido — {len(data)} métodos de pago disponibles.")
                self.mp_status_lbl.setObjectName("textSuccess")
            else:
                self.mp_status_lbl.setText("⚠️ Respuesta inesperada del servidor.")
                self.mp_status_lbl.setObjectName("textWarning")
        except Exception as e:
            self.mp_status_lbl.setText(f"❌ Error: {str(e)[:80]}")
            self.mp_status_lbl.setObjectName("textDanger")

    # ══════════════════════════════════════════════════════════════════════
    # TAB: 👤 Usuarios y Roles — versión embebida en config
    # ══════════════════════════════════════════════════════════════════════
    def _setup_tab_usuarios_roles(self) -> None:
        from PyQt5.QtWidgets import (
            QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
            QTableWidget, QTableWidgetItem, QHeaderView,
            QAbstractItemView, QTabWidget, QWidget
        )
        from PyQt5.QtCore import Qt
        lay = QVBoxLayout(self.tab_usuarios_roles)
        lay.setContentsMargins(0,0,0,0)

        sub_tabs = QTabWidget()
        lay.addWidget(sub_tabs)

        # ── Sub-tab: Sucursales ──────────────────────────────────────────
        tab_suc = QWidget(); suc_lay = QVBoxLayout(tab_suc)
        suc_hdr = QHBoxLayout()
        suc_hdr.addWidget(QLabel("Sucursales del sistema con horarios de atención"))
        suc_hdr.addStretch()
        btn_new_suc = QPushButton("➕ Nueva sucursal")
        btn_new_suc.setObjectName("successBtn")
        apply_tooltip(btn_new_suc, "Crear nueva sucursal")
        btn_new_suc.clicked.connect(self._nueva_sucursal_v13)
        suc_hdr.addWidget(btn_new_suc)
        suc_lay.addLayout(suc_hdr)

        self._tbl_suc_v13 = QTableWidget()
        self._tbl_suc_v13.setColumnCount(6)
        self._tbl_suc_v13.setHorizontalHeaderLabels(
            ["Nombre","Dirección","Horario","Días","Estado","Acciones"])
        hh = self._tbl_suc_v13.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        for i in (0,2,3,4): hh.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self._tbl_suc_v13.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_suc_v13.verticalHeader().setVisible(False)
        self._tbl_suc_v13.setAlternatingRowColors(True)
        suc_lay.addWidget(self._tbl_suc_v13)
        sub_tabs.addTab(tab_suc, "🏪 Sucursales")

        # ── Sub-tab: Usuarios ────────────────────────────────────────────
        tab_usr = QWidget(); usr_lay = QVBoxLayout(tab_usr)
        usr_hdr = QHBoxLayout()
        usr_hdr.addWidget(QLabel("Usuarios del sistema vinculados a empleados RRHH"))
        usr_hdr.addStretch()
        btn_new_usr = QPushButton("➕ Nuevo usuario")
        btn_new_usr.setObjectName("primaryBtn")
        apply_tooltip(btn_new_usr, "Crear nuevo usuario")
        btn_new_usr.clicked.connect(self._nuevo_usuario_v13)
        usr_hdr.addWidget(btn_new_usr)
        usr_lay.addLayout(usr_hdr)

        self._tbl_usr_v13 = QTableWidget()
        self._tbl_usr_v13.setColumnCount(6)
        self._tbl_usr_v13.setHorizontalHeaderLabels(
            ["Usuario","Nombre","Rol","Sucursal","Estado","Acciones"])
        hh2 = self._tbl_usr_v13.horizontalHeader()
        hh2.setSectionResizeMode(1, QHeaderView.Stretch)
        for i in (0,2,3,4): hh2.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self._tbl_usr_v13.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_usr_v13.verticalHeader().setVisible(False)
        self._tbl_usr_v13.setAlternatingRowColors(True)
        usr_lay.addWidget(self._tbl_usr_v13)
        sub_tabs.addTab(tab_usr, "👤 Usuarios")

        # ── Sub-tab: Roles ───────────────────────────────────────────────
        tab_roles = QWidget(); roles_lay = QVBoxLayout(tab_roles)
        roles_lay.addWidget(QLabel("Roles con sus permisos por módulo. Los roles del sistema no se pueden eliminar."))
        self._tbl_roles_v13 = QTableWidget()
        self._tbl_roles_v13.setColumnCount(4)
        self._tbl_roles_v13.setHorizontalHeaderLabels(
            ["Nombre","Descripción","# Usuarios","Acciones"])
        hh3 = self._tbl_roles_v13.horizontalHeader()
        hh3.setSectionResizeMode(1, QHeaderView.Stretch)
        self._tbl_roles_v13.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_roles_v13.verticalHeader().setVisible(False)
        self._tbl_roles_v13.setAlternatingRowColors(True)
        roles_lay.addWidget(self._tbl_roles_v13)
        sub_tabs.addTab(tab_roles, "🔑 Roles")

        # ── Sub-tab: Auditoría ───────────────────────────────────────────
        tab_audit = QWidget(); audit_lay = QVBoxLayout(tab_audit)
        audit_lay.addWidget(QLabel("Últimas 200 acciones registradas en el sistema"))
        self._tbl_audit_v13 = QTableWidget()
        self._tbl_audit_v13.setColumnCount(5)
        self._tbl_audit_v13.setHorizontalHeaderLabels(
            ["Fecha","Usuario","Módulo","Acción","Detalle"])
        hh4 = self._tbl_audit_v13.horizontalHeader()
        hh4.setSectionResizeMode(4, QHeaderView.Stretch)
        self._tbl_audit_v13.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_audit_v13.verticalHeader().setVisible(False)
        self._tbl_audit_v13.setAlternatingRowColors(True)
        audit_lay.addWidget(self._tbl_audit_v13)
        sub_tabs.addTab(tab_audit, "📋 Auditoría")

        sub_tabs.currentChanged.connect(self._on_usuarios_roles_tab_change)
        self._cargar_sucursales_v13()

    def _on_usuarios_roles_tab_change(self, idx):
        if idx == 0: self._cargar_sucursales_v13()
        elif idx == 1: self._cargar_usuarios_v13()
        elif idx == 2: self._cargar_roles_v13()
        elif idx == 3: self._cargar_auditoria_v13()

    def _cargar_sucursales_v13(self):
        from PyQt5.QtWidgets import QPushButton, QWidget, QHBoxLayout, QTableWidgetItem
        from PyQt5.QtCore import Qt
        try:
            rows = self.conexion.execute("""
                SELECT id,nombre,COALESCE(direccion,''),
                       COALESCE(hora_apertura,'08:00'),COALESCE(hora_cierre,'21:00'),
                       COALESCE(dias_operacion,'1,2,3,4,5,6'),activa
                FROM sucursales ORDER BY nombre
            """).fetchall()
        except Exception: rows = []
        self._tbl_suc_v13.setRowCount(len(rows))
        for ri, r in enumerate(rows):
            dias_n = str(r[5]).count(',') + 1 if r[5] else 6
            vals = [r[1], r[2], f"{r[3]}–{r[4]}", f"{dias_n} días/sem",
                    "✅ Activa" if r[6] else "❌ Inactiva"]
            for ci, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)
                if ci == 0: it.setData(Qt.UserRole, r[0])
                self._tbl_suc_v13.setItem(ri, ci, it)
            suc_id = r[0]; suc_nombre = r[1]
            btn_w = QWidget(); bl = QHBoxLayout(btn_w); bl.setContentsMargins(2,2,2,2)
            btn_ed = QPushButton("✏️"); btn_ed.setFixedSize(26,24)
            btn_ed.clicked.connect(lambda _, sid=suc_id: self._editar_sucursal_v13(sid))
            bl.addWidget(btn_ed)
            self._tbl_suc_v13.setCellWidget(ri, 5, btn_w)

    def _nueva_sucursal_v13(self):
        self._editar_sucursal_v13(None)

    def _editar_sucursal_v13(self, sucursal_id):
        from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout,
                                      QLineEdit, QCheckBox, QVBoxLayout, QMessageBox,
                                      QGroupBox, QHBoxLayout, QTextEdit)
        from modulos.spj_phone_widget import PhoneWidget as _PW_suc
        dlg = QDialog(self); dlg.setWindowTitle("Sucursal"); dlg.setMinimumWidth(460)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        txt_nombre  = QLineEdit()
        txt_dir     = QLineEdit()
        txt_tel     = _PW_suc(default_country="+52")
        txt_abre    = QLineEdit("08:00"); txt_abre.setPlaceholderText("HH:MM")
        txt_cierra  = QLineEdit("21:00"); txt_cierra.setPlaceholderText("HH:MM")
        dias_chks   = {}
        dias_nombres = ["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"]
        dias_w = QWidget(); dias_lay = QHBoxLayout(dias_w); dias_lay.setContentsMargins(0,0,0,0)
        for i, dn in enumerate(dias_nombres, 1):
            chk = QCheckBox(dn); chk.setChecked(i <= 6)
            dias_chks[i] = chk; dias_lay.addWidget(chk)
        chk_acepta = QCheckBox("Aceptar pedidos fuera de horario (se programan)")
        txt_msg    = QTextEdit()
        txt_msg.setMaximumHeight(60)
        txt_msg.setPlaceholderText("Mensaje al cliente fuera de horario")
        txt_msg.setPlainText("Estamos cerrados. Tu pedido quedará programado para cuando abramos.")
        form.addRow("Nombre*:", txt_nombre)
        form.addRow("Dirección:", txt_dir)
        form.addRow("Teléfono:", txt_tel)
        form.addRow("Abre:", txt_abre); form.addRow("Cierra:", txt_cierra)
        form.addRow("Días:", dias_w)
        form.addRow("", chk_acepta)
        form.addRow("Msg. cierre:", txt_msg)
        lay.addLayout(form)

        if sucursal_id:
            try:
                row = self.conexion.execute(
                    "SELECT nombre,direccion,telefono,hora_apertura,hora_cierre,"
                    "dias_operacion,acepta_pedidos_fuera_horario,mensaje_fuera_horario "
                    "FROM sucursales WHERE id=?", (sucursal_id,)
                ).fetchone()
                if row:
                    txt_nombre.setText(row[0] or ""); txt_dir.setText(row[1] or "")
                    txt_tel.set_phone(row[2] or ""); txt_abre.setText(row[3] or "08:00")
                    txt_cierra.setText(row[4] or "21:00")
                    dias_sel = (row[5] or "1,2,3,4,5,6").split(",")
                    for n, chk in dias_chks.items():
                        chk.setChecked(str(n) in dias_sel)
                    chk_acepta.setChecked(bool(row[6]))
                    if row[7]: txt_msg.setPlainText(row[7])
            except Exception: pass

        btns = QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        if dlg.exec_() != QDialog.Accepted: return
        nombre = txt_nombre.text().strip()
        if not nombre:
            QMessageBox.warning(self, "Aviso", "El nombre es obligatorio."); return
        dias = ",".join(str(n) for n, chk in dias_chks.items() if chk.isChecked())
        try:
            if sucursal_id:
                self.conexion.execute("""
                    UPDATE sucursales SET nombre=?,direccion=?,telefono=?,
                    hora_apertura=?,hora_cierre=?,dias_operacion=?,
                    acepta_pedidos_fuera_horario=?,mensaje_fuera_horario=?
                    WHERE id=?
                """, (nombre, txt_dir.text().strip(), txt_tel.get_e164().strip(),
                      txt_abre.text().strip(), txt_cierra.text().strip(), dias,
                      int(chk_acepta.isChecked()), txt_msg.toPlainText().strip(),
                      sucursal_id))
            else:
                self.conexion.execute("""
                    INSERT INTO sucursales
                        (nombre,direccion,telefono,hora_apertura,hora_cierre,
                         dias_operacion,acepta_pedidos_fuera_horario,mensaje_fuera_horario,activa)
                    VALUES(?,?,?,?,?,?,?,?,1)
                """, (nombre, txt_dir.text().strip(), txt_tel.get_e164().strip(),
                      txt_abre.text().strip(), txt_cierra.text().strip(), dias,
                      int(chk_acepta.isChecked()), txt_msg.toPlainText().strip()))
            self.conexion.commit()
            self._cargar_sucursales_v13()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _cargar_usuarios_v13(self):
        from PyQt5.QtWidgets import QPushButton, QWidget, QHBoxLayout, QTableWidgetItem
        from PyQt5.QtCore import Qt
        try:
            rows = self.conexion.execute("""
                SELECT u.id,u.usuario,u.nombre,
                       COALESCE(r.nombre,'cajero') as rol,
                       COALESCE(s.nombre,'Principal') as sucursal,
                       u.activo
                FROM usuarios u
                LEFT JOIN roles r ON r.nombre=u.rol
                LEFT JOIN sucursales s ON s.id=u.sucursal_id
                ORDER BY u.nombre LIMIT 200
            """).fetchall()
        except Exception:
            rows = []
        self._tbl_usr_v13.setRowCount(len(rows))
        for ri, r in enumerate(rows):
            vals = [r[1], r[2] or "", r[3], r[4],
                    "✅ Activo" if r[5] else "❌ Inactivo"]
            for ci, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                it.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)
                if ci == 0: it.setData(Qt.UserRole, r[0])
                self._tbl_usr_v13.setItem(ri, ci, it)
            uid = r[0]
            btn_w = QWidget(); bl = QHBoxLayout(btn_w); bl.setContentsMargins(2,2,2,2)
            btn_ed = QPushButton("✏️"); btn_ed.setFixedSize(26,24)
            btn_ed.clicked.connect(lambda _, uid=uid: self._editar_usuario_v13(uid))
            btn_tog = QPushButton("✅" if r[5] else "❌"); btn_tog.setFixedSize(26,24)
            btn_tog.clicked.connect(
                lambda _, uid=uid, a=r[5]: self._toggle_usuario(uid, not a))
            bl.addWidget(btn_ed); bl.addWidget(btn_tog)
            self._tbl_usr_v13.setCellWidget(ri, 5, btn_w)

    def _nuevo_usuario_v13(self):
        # v13.30: Verificar permiso
        try:
            from core.permissions import verificar_permiso
            _ctr = self.container if hasattr(self, 'container') else None
            if _ctr and not verificar_permiso(_ctr, "usuarios.gestionar", self):
                return
        except Exception: pass
        self._editar_usuario_v13(None)

    def _editar_usuario_v13(self, usuario_id):
        from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout,
                                      QLineEdit, QComboBox, QVBoxLayout,
                                      QMessageBox, QCheckBox, QLabel)
        dlg = QDialog(self); dlg.setWindowTitle("Usuario"); dlg.setMinimumWidth(440)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        txt_usuario  = QLineEdit()
        txt_nombre   = QLineEdit()
        txt_email    = QLineEdit()
        txt_pass     = QLineEdit(); txt_pass.setEchoMode(QLineEdit.Password)
        txt_pass.setPlaceholderText("(dejar vacío para no cambiar)" if usuario_id else "Contraseña")
        cmb_rol      = QComboBox()
        cmb_sucursal = QComboBox()
        chk_activo   = QCheckBox("Activo"); chk_activo.setChecked(True)
        cmb_empleado = QComboBox(); cmb_empleado.addItem("(ninguno)", None)
        lbl_emp_hint = QLabel("Vincula este usuario a un empleado de RRHH")
        lbl_emp_hint.setObjectName("caption")

        # Fill roles and sucursales
        try:
            for rn in self.conexion.execute("SELECT nombre FROM roles ORDER BY id").fetchall():
                cmb_rol.addItem(rn[0])
        except Exception:
            for rn in ["admin","gerente","cajero","almacen","repartidor","solo_lectura"]:
                cmb_rol.addItem(rn)
        try:
            for sn in self.conexion.execute("SELECT id,nombre FROM sucursales WHERE activa=1").fetchall():
                cmb_sucursal.addItem(sn[1], sn[0])
        except Exception:
            cmb_sucursal.addItem("Principal", 1)
        try:
            for em in self.conexion.execute(
                "SELECT id, nombre||' '||COALESCE(apellidos,'') FROM personal WHERE activo=1 ORDER BY nombre"
            ).fetchall():
                cmb_empleado.addItem(em[1].strip(), em[0])
        except Exception: pass

        form.addRow("Usuario*:", txt_usuario)
        form.addRow("Nombre:", txt_nombre)
        form.addRow("Email:", txt_email)
        form.addRow("Contraseña:", txt_pass)
        form.addRow("Rol:", cmb_rol)
        form.addRow("Sucursal:", cmb_sucursal)
        form.addRow("Empleado RRHH:", cmb_empleado)
        form.addRow("", lbl_emp_hint)
        form.addRow("", chk_activo)
        lay.addLayout(form)

        if usuario_id:
            try:
                row = self.conexion.execute(
                    "SELECT usuario,nombre,email,rol,sucursal_id,activo,empleado_id "
                    "FROM usuarios WHERE id=?", (usuario_id,)
                ).fetchone()
                if row:
                    txt_usuario.setText(row[0] or ""); txt_nombre.setText(row[1] or "")
                    txt_email.setText(row[2] or "")
                    idx = cmb_rol.findText(row[3] or "cajero")
                    if idx >= 0: cmb_rol.setCurrentIndex(idx)
                    for i in range(cmb_sucursal.count()):
                        if cmb_sucursal.itemData(i) == row[4]:
                            cmb_sucursal.setCurrentIndex(i); break
                    chk_activo.setChecked(bool(row[5]))
                    if row[6]:
                        for i in range(cmb_empleado.count()):
                            if cmb_empleado.itemData(i) == row[6]:
                                cmb_empleado.setCurrentIndex(i); break
            except Exception: pass

        btns = QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        if dlg.exec_() != QDialog.Accepted: return
        uname = txt_usuario.text().strip()
        if not uname:
            QMessageBox.warning(self, "Aviso", "El nombre de usuario es obligatorio."); return
        try:
            import bcrypt as _bcrypt
        except ImportError:
            _bcrypt = None
        try:
            pwd_raw = txt_pass.text()
            suc_id  = cmb_sucursal.currentData() or 1
            emp_id  = cmb_empleado.currentData()
            activo  = int(chk_activo.isChecked())
            if usuario_id:
                if pwd_raw:
                    if _bcrypt:
                        pwd_hash = _bcrypt.hashpw(pwd_raw.encode(), _bcrypt.gensalt()).decode()
                    else:
                        pwd_hash = pwd_raw
                    self.conexion.execute(
                        "UPDATE usuarios SET usuario=?,nombre=?,email=?,rol=?,"
                        "sucursal_id=?,activo=?,empleado_id=?,password_hash=? WHERE id=?",
                        (uname, txt_nombre.text().strip(), txt_email.text().strip(),
                         cmb_rol.currentText(), suc_id, activo, emp_id, pwd_hash, usuario_id))
                else:
                    self.conexion.execute(
                        "UPDATE usuarios SET usuario=?,nombre=?,email=?,rol=?,"
                        "sucursal_id=?,activo=?,empleado_id=? WHERE id=?",
                        (uname, txt_nombre.text().strip(), txt_email.text().strip(),
                         cmb_rol.currentText(), suc_id, activo, emp_id, usuario_id))
            else:
                if not pwd_raw:
                    QMessageBox.warning(self, "Aviso", "La contraseña es obligatoria."); return
                if _bcrypt:
                    pwd_hash = _bcrypt.hashpw(pwd_raw.encode(), _bcrypt.gensalt()).decode()
                else:
                    pwd_hash = pwd_raw
                self.conexion.execute(
                    "INSERT INTO usuarios(usuario,nombre,email,password_hash,rol,"
                    "sucursal_id,activo,empleado_id) VALUES(?,?,?,?,?,?,?,?)",
                    (uname, txt_nombre.text().strip(), txt_email.text().strip(),
                     pwd_hash, cmb_rol.currentText(), suc_id, activo, emp_id))
                # Si tiene empleado vinculado, actualizar personal.usuario_id
                if emp_id:
                    new_uid = self.conexion.execute("SELECT last_insert_rowid()").fetchone()[0]
                    self.conexion.execute(
                        "UPDATE personal SET usuario_id=? WHERE id=?", (new_uid, emp_id))
            self.conexion.commit()
            self._cargar_usuarios_v13()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _toggle_usuario(self, uid, activo):
        try:
            self.conexion.execute(
                "UPDATE usuarios SET activo=? WHERE id=?", (int(activo), uid))
            self.conexion.commit()
            self._cargar_usuarios_v13()
        except Exception as e:
        # [spj-dedup removed local QMessageBox import]
            QMessageBox.critical(self, "Error", str(e))

    def _cargar_roles_v13(self):
        from PyQt5.QtWidgets import QPushButton, QWidget, QHBoxLayout, QTableWidgetItem
        from PyQt5.QtCore import Qt
        try:
            rows = self.conexion.execute("""
                SELECT r.id, r.nombre, r.descripcion,
                       COUNT(u.id) as num_usuarios
                FROM roles r
                LEFT JOIN usuarios u ON u.rol=r.nombre AND u.activo=1
                GROUP BY r.id ORDER BY r.id
            """).fetchall()
        except Exception: rows = []
        self._tbl_roles_v13.setRowCount(len(rows))
        for ri, r in enumerate(rows):
            vals = [r[1], r[2] or "", str(r[3])]
            for ci, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)
                self._tbl_roles_v13.setItem(ri, ci, it)
            btn_w = QWidget(); bl = QHBoxLayout(btn_w); bl.setContentsMargins(2,2,2,2)
            btn_perm = QPushButton("🔑 Permisos")
            btn_perm.setObjectName("secondaryBtn")
            apply_tooltip(btn_perm, f"Editar permisos del rol {r[1]}")
            btn_perm.clicked.connect(
                lambda _, rid=r[0], rnom=r[1]: self._editar_permisos_rol(rid, rnom))
            bl.addWidget(btn_perm)
            self._tbl_roles_v13.setCellWidget(ri, 3, btn_w)

    def _editar_permisos_rol(self, rol_id, rol_nombre):
        from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QTableWidget,
                                      QTableWidgetItem, QHeaderView, QCheckBox,
                                      QDialogButtonBox, QMessageBox, QScrollArea)
        from PyQt5.QtCore import Qt
        dlg = QDialog(self); dlg.setWindowTitle(f"Permisos — {rol_nombre}")
        dlg.setMinimumSize(600, 500)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(f"Configura permisos para el rol: <b>{rol_nombre}</b>"))

        MODULOS = ["POS","INVENTARIO","PRODUCTOS","CLIENTES","COMPRAS","CAJA",
                   "REPORTES_BI","TESORERIA","RRHH","CONFIGURACION","USUARIOS",
                   "DELIVERY","COTIZACIONES","MERMA","PROVEEDORES","PRODUCCION"]
        ACCIONES = ["ver","crear","editar","eliminar","exportar"]

        # Load existing permisos
        existing = {}
        try:
            rows = self.conexion.execute(
                "SELECT modulo, accion, permitido FROM rol_permisos WHERE rol_id=?",
                (rol_id,)
            ).fetchall()
            for r in rows:
                existing[(r[0],r[1])] = bool(r[2])
        except Exception: pass

        tbl = QTableWidget(len(MODULOS), len(ACCIONES)+1)
        tbl.setHorizontalHeaderLabels(["Módulo"] + ACCIONES)
        tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        chks = {}
        for ri, mod in enumerate(MODULOS):
            tbl.setItem(ri, 0, QTableWidgetItem(mod))
            for ci, acc in enumerate(ACCIONES, 1):
                chk = QCheckBox()
                chk.setChecked(existing.get((mod, acc), False))
                chks[(mod, acc)] = chk
                tbl.setCellWidget(ri, ci, chk)

        scroll = QScrollArea(); scroll.setWidget(tbl); scroll.setWidgetResizable(True)
        lay.addWidget(scroll)

        btns = QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        if dlg.exec_() != QDialog.Accepted: return
        try:
            self.conexion.execute("DELETE FROM rol_permisos WHERE rol_id=?", (rol_id,))
            for (mod, acc), chk in chks.items():
                self.conexion.execute(
                    "INSERT INTO rol_permisos(rol_id,modulo,accion,permitido) VALUES(?,?,?,?)",
                    (rol_id, mod, acc, int(chk.isChecked())))
            self.conexion.commit()
            QMessageBox.information(dlg, "✅", f"Permisos de '{rol_nombre}' guardados.")
        except Exception as e:
            QMessageBox.critical(dlg, "Error", str(e))

    def _cargar_auditoria_v13(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        from PyQt5.QtCore import Qt
        try:
            rows = self.conexion.execute("""
                SELECT fecha, usuario, modulo, accion, COALESCE(detalles,'')
                FROM audit_logs ORDER BY fecha DESC LIMIT 200
            """).fetchall()
        except Exception: rows = []
        self._tbl_audit_v13.setRowCount(len(rows))
        for ri, r in enumerate(rows):
            for ci, v in enumerate(r):
                it = QTableWidgetItem(str(v)[:60])
                it.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)
                self._tbl_audit_v13.setItem(ri, ci, it)


    def closeEvent(self, event):
        """Maneja el cierre del módulo"""
        self.registrar_actualizacion("modulo_cerrado", {"modulo": "configuraciones"})
        super().closeEvent(event)


class DialogoUsuario(QDialog):
    def __init__(self, conexion, parent=None, usuario_data=None):
        super().__init__(parent)
        # Accept AppContainer or direct db connection
        if hasattr(conexion, 'db'):
            self.container = conexion
            self.conexion  = conexion.db
        else:
            self.container = None
            self.conexion  = conexion
        self.usuario_data = usuario_data
        self.es_edicion = usuario_data is not None
        
        self.setWindowTitle("Editar Usuario" if self.es_edicion else "Nuevo Usuario")
        self.setFixedSize(500, 500)
        self.setModal(True)
        
        self.init_ui()
        if self.es_edicion:
                self.setWindowTitle("Editar Usuario")
                self.cargar_datos()
        else:
            self.setWindowTitle("Crear Nuevo Usuario")

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Título
        titulo = QLabel("Editar Usuario" if self.es_edicion else "Crear Nuevo Usuario")
        titulo.setAlignment(Qt.AlignCenter)
        font = titulo.font()
        font.setPointSize(14)
        font.setBold(True)
        titulo.setFont(font)
        layout.addWidget(titulo)

        # Formulario
        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignRight)
        form_layout.setVerticalSpacing(10)
        
        self.edit_usuario = QLineEdit()
        self.edit_usuario.setPlaceholderText("Nombre de usuario único")
        
        self.edit_nombre = QLineEdit()
        self.edit_nombre.setPlaceholderText("Nombre completo del usuario")
        
        self.edit_contrasena = QLineEdit()
        self.edit_contrasena.setEchoMode(QLineEdit.Password)
        self.edit_contrasena.setPlaceholderText("Mínimo 6 caracteres" if not self.es_edicion else "Dejar en blanco para no cambiar")
        
        self.edit_confirmar = QLineEdit()
        self.edit_confirmar.setEchoMode(QLineEdit.Password)
        self.edit_confirmar.setPlaceholderText("Confirmar contraseña")
        
        self.combo_rol = QComboBox()
        self.combo_rol.addItems(["admin", "cajero", "vendedor", "inventario"])

        # Sucursal asignada
        self.combo_sucursal_usuario = QComboBox()
        self._cargar_sucursales_combo()

        # Módulos permitidos
        grupo_modulos = QGroupBox("Módulos Permitidos")
        layout_modulos = QGridLayout()
        self.modulos_checkboxes = {}
        
        modulos = [
            ("ventas", "Ventas"),
            ("clientes", "Clientes"), 
            ("productos", "Productos"),
            ("inventario", "Inventario"),
            ("compras", "Compras"),
            ("gastos", "Gastos"),
            ("reportes", "Reportes"),
            ("configuraciones", "Configuración")
        ]
        
        for i, (clave, nombre) in enumerate(modulos):
            chk = QCheckBox(nombre)
            self.modulos_checkboxes[clave] = chk
            layout_modulos.addWidget(chk, i // 2, i % 2)
        
        grupo_modulos.setLayout(layout_modulos)

        form_layout.addRow("Usuario*:", self.edit_usuario)
        form_layout.addRow("Nombre completo:", self.edit_nombre)
        form_layout.addRow("Contraseña*:", self.edit_contrasena)
        form_layout.addRow("Confirmar*:", self.edit_confirmar)
        form_layout.addRow("Rol*:", self.combo_rol)
        form_layout.addRow("Sucursal:", self.combo_sucursal_usuario)
        form_layout.addRow("Permisos:", grupo_modulos)
        
        layout.addLayout(form_layout)

        # Botones
        btn_layout = QHBoxLayout()
        self.btn_guardar = QPushButton("💾 Guardar")
        self.btn_guardar.setDefault(True)
        self.btn_cancelar = QPushButton("❌ Cancelar")
        
        btn_layout.addWidget(self.btn_guardar)
        btn_layout.addWidget(self.btn_cancelar)
        layout.addLayout(btn_layout)

        # Conexiones
        self.btn_guardar.clicked.connect(self.guardar_usuario)
        self.btn_cancelar.clicked.connect(self.reject)

    def _cargar_sucursales_combo(self):
        """Carga las sucursales en el combo del formulario de usuario."""
        self.combo_sucursal_usuario.clear()
        try:
            sucursales = self.conexion.execute(
                "SELECT id, nombre FROM sucursales WHERE activa=1 ORDER BY id"
            ).fetchall()
            for sid, nombre in sucursales:
                self.combo_sucursal_usuario.addItem(f"🏪 {nombre}", sid)
        except Exception:
            self.combo_sucursal_usuario.addItem("🏪 Principal", 1)

    def cargar_datos_usuario(self):
        """Carga los datos del usuario en el formulario"""
        if not self.usuario_data:
            return
            
        self.edit_usuario.setText(self.usuario_data.get('usuario', ''))
        self.edit_nombre.setText(self.usuario_data.get('nombre', ''))
        self.combo_rol.setCurrentText(self.usuario_data.get('rol', 'vendedor'))

        # Cargar sucursal
        suc_id = self.usuario_data.get('sucursal_id', 1) or 1
        for i in range(self.combo_sucursal_usuario.count()):
            if self.combo_sucursal_usuario.itemData(i) == suc_id:
                self.combo_sucursal_usuario.setCurrentIndex(i)
                break
        
        # Cargar módulos permitidos
        modulos_permitidos = self.usuario_data.get('modulos_permitidos', '')
        if modulos_permitidos:
            for modulo in modulos_permitidos.split(','):
                modulo = modulo.strip()
                if modulo in self.modulos_checkboxes:
                    self.modulos_checkboxes[modulo].setChecked(True)

    def validar_formulario(self):
        """Valida los datos del formulario"""
        usuario = self.edit_usuario.text().strip()
        contrasena = self.edit_contrasena.text()
        confirmar = self.edit_confirmar.text()
        
        if not usuario:
            QMessageBox.warning(self, "Error", "El nombre de usuario es obligatorio.")
            return False
            
        if not self.es_edicion and not contrasena:
            QMessageBox.warning(self, "Error", "La contraseña es obligatoria para nuevos usuarios.")
            return False
            
        if contrasena and len(contrasena) < 6:
            QMessageBox.warning(self, "Error", "La contraseña debe tener al menos 6 caracteres.")
            return False
            
        if contrasena and contrasena != confirmar:
            QMessageBox.warning(self, "Error", "Las contraseñas no coinciden.")
            return False
            
        return True

    def guardar_usuario(self):
            usuario = self.txt_usuario.text().strip()
            nombre = self.txt_nombre.text().strip()
            contrasena = self.txt_contrasena.text() # NO strip() por si el espacio es intencional, pero se hashea
            rol = self.combo_rol.currentText()
            modulos = [self.lst_modulos.item(i).text() for i in range(self.lst_modulos.count()) if self.lst_modulos.item(i).checkState() == Qt.Checked]
            modulos_str = json.dumps(modulos)
            
            if not usuario or not nombre or not rol:
                QMessageBox.warning(self, "Advertencia", "Todos los campos obligatorios deben ser llenados.")
                return

            if not self.es_edicion and not contrasena:
                QMessageBox.warning(self, "Advertencia", "Se debe ingresar una contraseña para el nuevo usuario.")
                return

            try:
                cursor = self.conexion.cursor()
                
                # --- Lógica de Hashing de Contraseña ---
                hashed_password = None
                if contrasena:
                    # Aplicar bcrypt para generar un hash seguro de la contraseña
                    if _USE_AUTH_MODULE:
                        try:
                            hashed_password = _hash_password(contrasena)
                        except Exception:
                            hashed_password = __import__('hashlib').sha256(contrasena.encode()).hexdigest() if not bcrypt else bcrypt.hashpw(contrasena.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                    else:
                        hashed_password = __import__('hashlib').sha256(contrasena.encode()).hexdigest() if not bcrypt else bcrypt.hashpw(contrasena.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                
                if self.es_edicion:
                    id_usuario = self.usuario_data['id']
                    
                    # Prepara la lista de campos a actualizar
                    sucursal_id_val = self.combo_sucursal_usuario.currentData() or 1
                    update_fields = ['usuario', 'nombre', 'rol', 'modulos_permitidos', 'sucursal_id']
                    update_values = [usuario, nombre, rol, modulos_str, sucursal_id_val]


                    # Si se proporcionó una nueva contraseña, añádela a la actualización
                    if hashed_password:
                        update_fields.append('contrasena')
                        update_values.append(hashed_password)
                    
                    # Construye la consulta de actualización de forma dinámica
                    sets = ', '.join([f"{f} = ?" for f in update_fields])
                    update_values.append(id_usuario)

                    # Whitelist campos para prevenir SQL injection
                    _campos_ok = {'nombre','usuario','password_hash','rol','sucursal_id',
                                   'activo','email','foto_path','empleado_id'}
                    sets_safe = ', '.join(
                        p for p in sets.split(',')
                        if p.strip().split('=')[0].strip() in _campos_ok
                    )
                    cursor.execute("UPDATE usuarios SET " + sets_safe + " WHERE id=?", update_values)
                    
                else:
                    # Nuevo usuario - verificar que no exista
                    cursor.execute("SELECT id FROM usuarios WHERE usuario = ?", (usuario,))
                    if cursor.fetchone():
                        QMessageBox.warning(self, "Error", "Ya existe un usuario con ese nombre.")
                        return
                    
                    # USAR EL HASH EN LA INSERCIÓN
                    sucursal_id_val = self.combo_sucursal_usuario.currentData() or 1
                    cursor.execute("""
                        INSERT INTO usuarios (usuario, nombre, contrasena, rol, modulos_permitidos, sucursal_id, fecha_creacion, activo)
                        VALUES (?, ?, ?, ?, ?, ?, datetime('now'), 1)
                    """, (usuario, nombre, hashed_password, rol, modulos_str, sucursal_id_val))
                
                self.conexion.commit()
                QMessageBox.information(self, "Éxito", 
                                      "Usuario guardado correctamente." if self.es_edicion 
                                      else "Usuario creado correctamente.")
                self.accept()
                
            except sqlite3.Error as e:
                self.conexion.rollback()
                QMessageBox.critical(self, "Error", f"Error en base de datos: {str(e)}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error inesperado: {str(e)}")

# =============================================================================
# DIÁLOGO PARA CREAR / EDITAR SUCURSAL
# =============================================================================
class DialogoSucursalEdit(QDialog):
    """Formulario para crear o editar una sucursal."""

    def __init__(self, conexion, sucursal_data=None, parent=None):
        super().__init__(parent)
        self.conexion       = conexion
        self.sucursal_data  = sucursal_data
        self.es_edicion     = sucursal_data is not None
        self.setWindowTitle("Editar Sucursal" if self.es_edicion else "Nueva Sucursal")
        self.setModal(True)
        self.setFixedSize(440, 300)
        self._init_ui()
        if self.es_edicion:
            self._cargar_datos()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        form = QFormLayout()
        form.setVerticalSpacing(10)

        self.txt_nombre    = QLineEdit()
        self.txt_nombre.setPlaceholderText("Ej: Sucursal Norte")
        self.txt_direccion = QLineEdit()
        self.txt_direccion.setPlaceholderText("Calle, colonia, ciudad")
        self.txt_telefono  = QLineEdit()
        self.txt_telefono.setPlaceholderText("10 dígitos")
        self.chk_activa    = QCheckBox("Sucursal activa")
        self.chk_activa.setChecked(True)

        form.addRow("Nombre*:",    self.txt_nombre)
        form.addRow("Dirección:", self.txt_direccion)
        form.addRow("Teléfono:",  self.txt_telefono)
        form.addRow("",            self.chk_activa)
        layout.addLayout(form)
        layout.addStretch()

        btns = QHBoxLayout()
        btn_guardar  = QPushButton("💾 Guardar")
        btn_cancelar = QPushButton("❌ Cancelar")
        btn_guardar.setMinimumHeight(34)
        btn_cancelar.setMinimumHeight(34)
        btn_guardar.clicked.connect(self._guardar)
        btn_cancelar.clicked.connect(self.reject)
        btns.addWidget(btn_guardar)
        btns.addWidget(btn_cancelar)
        layout.addLayout(btns)

    def _cargar_datos(self):
        self.txt_nombre.setText(self.sucursal_data.get("nombre", ""))
        self.txt_direccion.setText(self.sucursal_data.get("direccion", "") or "")
        self.txt_telefono.setText(self.sucursal_data.get("telefono", "") or "")
        self.chk_activa.setChecked(bool(self.sucursal_data.get("activa", 1)))

    def _guardar(self):
        nombre = self.txt_nombre.text().strip()
        if not nombre:
            QMessageBox.warning(self, "Error", "El nombre de la sucursal es obligatorio.")
            return
        direccion = self.txt_direccion.text().strip() or None
        telefono  = self.txt_telefono.text().strip() or None
        activa    = 1 if self.chk_activa.isChecked() else 0
        try:
            if self.es_edicion:
                self.conexion.execute(
                    "UPDATE sucursales SET nombre=?, direccion=?, telefono=?, activa=? WHERE id=?",
                    (nombre, direccion, telefono, activa, self.sucursal_data["id"])
                )
            else:
                self.conexion.execute(
                    "INSERT INTO sucursales (nombre, direccion, telefono, activa) VALUES (?,?,?,?)",
                    (nombre, direccion, telefono, activa)
                )
            self.conexion.commit()
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


    
