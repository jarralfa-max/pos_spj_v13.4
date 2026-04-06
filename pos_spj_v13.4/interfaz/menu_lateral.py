
# interfaz/menu_lateral.py
from PyQt5.QtWidgets import (QFrame, QVBoxLayout, QPushButton, QLabel, 
                             QSpacerItem, QSizePolicy, QScrollArea, QWidget)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QPixmap

class MenuLateral(QFrame):
    # Señal maestra que avisa a la ventana principal a qué módulo queremos ir
    opcion_seleccionada = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MenuLateral")
        self.setFixedWidth(240) # Lo hicimos un poco más ancho para que quepan los nombres largos
        
        # Estilos base del panel lateral
        self.setStyleSheet("""
            QFrame#MenuLateral {
                background-color: #1E272E;
                color: white;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QWidget#ContenedorBotones {
                background-color: transparent;
            }
            QLabel.SeccionHeader {
                color: #808E9B;
                font-size: 11px;
                font-weight: bold;
                text-transform: uppercase;
                padding-left: 15px;
                margin-top: 15px;
                margin-bottom: 5px;
            }
            QPushButton {
                background-color: transparent;
                color: #D2DAE2;
                text-align: left;
                padding: 10px 15px;
                font-size: 13px;
                border: none;
                border-radius: 4px;
                margin: 0px 5px;
            }
            QPushButton:hover {
                background-color: #34495E;
                color: white;
            }
            QPushButton:pressed {
                background-color: #0FB9B1;
                color: white;
            }
        """)
        self._permisos = set()
        self._rol = ""
        self._configurar_ui()

    def _configurar_ui(self):
        # Layout principal del Frame
        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(0, 0, 0, 0)
        layout_principal.setSpacing(0)

        # ==========================================
        # 1. ZONA DEL LOGO Y NOMBRE DE LA EMPRESA
        # ==========================================
        zona_logo = QFrame()
        zona_logo.setStyleSheet("background-color: #1E272E;")
        layout_logo = QVBoxLayout(zona_logo)
        layout_logo.setContentsMargins(10, 20, 10, 20)
        layout_logo.setAlignment(Qt.AlignCenter)

        self.lbl_logo = QLabel()
        self.lbl_logo.setAlignment(Qt.AlignCenter)
        # Intenta cargar el logo
        pixmap = QPixmap("assets/logo.png")
        if not pixmap.isNull():
            self.lbl_logo.setPixmap(pixmap.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.lbl_logo.setText("🏢\nSPJ POS")
            self.lbl_logo.setStyleSheet("font-size: 24px; font-weight: bold; color: white;")
            
        layout_logo.addWidget(self.lbl_logo)
        
        lbl_version = QLabel("Enterprise Edition v13.4")
        lbl_version.setAlignment(Qt.AlignCenter)
        lbl_version.setStyleSheet("color: #0FB9B1; font-size: 10px; font-weight: bold;")
        layout_logo.addWidget(lbl_version)
        
        layout_principal.addWidget(zona_logo)

        # ==========================================
        # 2. ZONA DESLIZABLE (SCROLL) PARA LOS MÓDULOS
        # ==========================================
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        contenedor_botones = QWidget()
        contenedor_botones.setObjectName("ContenedorBotones")
        layout_botones = QVBoxLayout(contenedor_botones)
        layout_botones.setContentsMargins(0, 0, 0, 0)
        layout_botones.setSpacing(2)

        # --- SECCIÓN: OPERACIONES CORE ---
        layout_botones.addWidget(self._crear_header("Operaciones"))
        layout_botones.addWidget(self._crear_boton("📊 Dashboard", "DASHBOARD"))
        layout_botones.addWidget(self._crear_boton("🛒 Punto de Venta", "POS"))
        layout_botones.addWidget(self._crear_boton("💰 Caja / Cortes Z", "CAJA"))
        layout_botones.addWidget(self._crear_boton("📦 Inventario", "INVENTARIO"))
        layout_botones.addWidget(self._crear_boton("🔄 Transferencias", "TRANSFERENCIAS"))
        layout_botones.addWidget(self._crear_boton("🏷️ Productos", "PRODUCTOS"))
        layout_botones.addWidget(self._crear_boton("👥 Clientes", "CLIENTES"))
        layout_botones.addWidget(self._crear_boton("🗑️ Merma", "MERMA"))

        # --- SECCIÓN: COMERCIAL ---
        layout_botones.addWidget(self._crear_header("Comercial"))
        layout_botones.addWidget(self._crear_boton("🛵 Delivery", "DELIVERY"))
        layout_botones.addWidget(self._crear_boton("🛒 Compras", "COMPRAS"))
        layout_botones.addWidget(self._crear_boton("📋 Cotizaciones", "COTIZACIONES"))
        layout_botones.addWidget(self._crear_boton("🏭 Proveedores", "PROVEEDORES"))

        # --- SECCIÓN: PRODUCCIÓN ---
        layout_botones.addWidget(self._crear_header("Producción"))
        layout_botones.addWidget(self._crear_boton("🔪 Procesamiento Cárnico", "PRODUCCION"))
        layout_botones.addWidget(self._crear_boton("🏷️ Etiquetas", "ETIQUETAS"))
        layout_botones.addWidget(self._crear_boton("📖 Recetas Industriales", "RECETAS"))
        layout_botones.addWidget(self._crear_boton("📈 Planeación de Compras", "PLANEACION_COMPRAS"))

        # --- SECCIÓN: ADMINISTRACIÓN ---
        layout_botones.addWidget(self._crear_header("Administración"))
        layout_botones.addWidget(self._crear_boton("🏦 Tesorería", "TESORERIA"))
        layout_botones.addWidget(self._crear_boton("📊 Finanzas", "FINANZAS"))
        layout_botones.addWidget(self._crear_boton("🏗️ Activos", "ACTIVOS"))
        layout_botones.addWidget(self._crear_boton("👔 Recursos Humanos", "RRHH"))
        layout_botones.addWidget(self._crear_boton("⭐ Fidelización", "GROWTH_ENGINE"))
        layout_botones.addWidget(self._crear_boton("💳 Tarjetas Fidelidad", "TARJETAS_FIDELIDAD"))
        layout_botones.addWidget(self._crear_boton("📈 Inteligencia (BI)", "INTELIGENCIA_BI"))
        layout_botones.addWidget(self._crear_boton("📱 Pedidos WhatsApp", "WHATSAPP"))

        # --- SECCIÓN: CONFIGURACIÓN ---
        layout_botones.addWidget(self._crear_header("Sistema"))
        layout_botones.addWidget(self._crear_boton("🎨 Diseñador Tickets", "DISEÑADOR_TICKETS"))
        layout_botones.addWidget(self._crear_boton("🖨️ Hardware", "CONFIG_HARDWARE"))
        layout_botones.addWidget(self._crear_boton("🛡️ Configuración", "CONFIG_SEGURIDAD"))

        # Espaciador para empujar los botones hacia arriba dentro del scroll
        spacer = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        layout_botones.addItem(spacer)

        # Asignar el contenedor al scroll
        scroll.setWidget(contenedor_botones)
        layout_principal.addWidget(scroll)

        # ==========================================
        # 3. ZONA INFERIOR (CERRAR SESIÓN)
        # ==========================================
        zona_inferior = QFrame()
        zona_inferior.setStyleSheet("background-color: #1E272E;")
        layout_inferior = QVBoxLayout(zona_inferior)
        layout_inferior.setContentsMargins(5, 10, 5, 10)
        
        btn_logout = self._crear_boton("🚪 Cerrar Sesión", "LOGOUT")
        btn_logout.setStyleSheet(
            "color: #FF4757; font-weight: bold; background-color: transparent;"
            "text-align: left; padding: 10px 15px; border: none; border-radius: 4px;"
            "margin: 0px 5px;")
        layout_inferior.addWidget(btn_logout)
        
        layout_principal.addWidget(zona_inferior)

    def _crear_header(self, texto):
        """Crea un título pequeño para agrupar las secciones."""
        lbl = QLabel(texto)
        lbl.setProperty("class", "SeccionHeader")
        return lbl

    def set_permisos(self, permisos: set, rol: str = "") -> None:
        """
        Filtra los botones del menú según los permisos del usuario activo.
        Llámalo desde main_window después de login exitoso.
        """
        self._permisos = permisos
        self._rol = rol.lower()

        # Módulos restringidos por rol
        SOLO_ADMIN_GERENTE = {
            "TESORERIA", "RRHH", "ACTIVOS", "CONFIG_SEGURIDAD",
            "CONFIG_MODULOS", "CONFIG_HARDWARE",
        }
        SOLO_ADMIN = {"CONFIG_SEGURIDAD", "CONFIG_MODULOS"}
        GERENTE_O_SUPERIOR = {"INTELIGENCIA_BI", "PREDICCIONES"}

        from PyQt5.QtWidgets import QPushButton as _QPB
        for btn in self.findChildren(_QPB):
            codigo = btn.property("modulo_codigo")
            if not codigo or codigo == "LOGOUT":
                continue
            visible = True
            if codigo in SOLO_ADMIN and self._rol not in ("admin", "administrador"):
                visible = False
            elif codigo in SOLO_ADMIN_GERENTE and self._rol not in ("admin", "administrador", "gerente"):
                visible = False
            elif codigo in GERENTE_O_SUPERIOR and self._rol not in ("admin", "administrador", "gerente"):
                visible = False
            btn.setVisible(visible)

    def set_module_config(self, module_config) -> None:
        """
        Muestra u oculta botones según feature flags del ModuleConfig (FASES 1-13).
        Se llama desde main_window después del login exitoso.

        Módulos avanzados que se ocultan si su toggle está desactivado:
          franchise_mode_enabled  → (solo info — no hay módulo UI independiente)
          forecasting_enabled     → PLANEACION_COMPRAS
          whatsapp_integration_enabled → WHATSAPP
          rrhh_enabled            → RRHH
          treasury_central_enabled → TESORERIA
        """
        # Mapeo: código de botón → clave de toggle en module_config
        TOGGLE_MAP = {
            "PLANEACION_COMPRAS": "forecasting_enabled",
            "WHATSAPP":           "whatsapp_integration_enabled",
            "RRHH":               "rrhh_enabled",
            "TESORERIA":          "treasury_central_enabled",
            "INTELIGENCIA_BI":    "finance_enabled",
        }

        from PyQt5.QtWidgets import QPushButton as _QPB
        for btn in self.findChildren(_QPB):
            codigo = btn.property("modulo_codigo")
            if not codigo or codigo == "LOGOUT":
                continue
            toggle_key = TOGGLE_MAP.get(codigo)
            if toggle_key is not None:
                enabled = module_config.is_enabled(toggle_key)
                if not enabled:
                    btn.setVisible(False)

    def actualizar_logo(self, logo_path: str = "", nombre: str = "SPJ POS") -> None:
        """Actualiza el logo y nombre del negocio en el sidebar."""
        if logo_path:
            try:
                from PyQt5.QtGui import QPixmap
                from PyQt5.QtCore import Qt
                import os
                if os.path.exists(logo_path):
                    pix = QPixmap(logo_path)
                    if not pix.isNull():
                        self.lbl_logo.setPixmap(
                            pix.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                        self.lbl_logo.setStyleSheet("")
                        return
            except Exception:
                pass
        # Fallback: text
        self.lbl_logo.setText(f"🏢\n{nombre[:12]}")
        self.lbl_logo.setStyleSheet("font-size:20px;font-weight:bold;color:white;")

    def _crear_boton(self, texto, codigo_modulo):
        """Fabrica el botón, lo etiqueta con su código y conecta la señal."""
        btn = QPushButton(texto)
        btn.setProperty("modulo_codigo", codigo_modulo)
        btn.clicked.connect(lambda _, m=codigo_modulo: self.opcion_seleccionada.emit(m))
        return btn