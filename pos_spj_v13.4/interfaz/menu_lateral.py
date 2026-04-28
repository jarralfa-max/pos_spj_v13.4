
# interfaz/menu_lateral.py
from PyQt5.QtWidgets import (QFrame, QVBoxLayout, QPushButton, QLabel,
                             QSpacerItem, QSizePolicy, QScrollArea, QWidget,
                             QShortcut)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QPixmap, QKeySequence
import unicodedata

from modulos.ui_components import create_input_field
from modulos.design_tokens import Colors, Borders, Typography

# Inventario explícito de módulos v13.4 (referencia para wiring UI)
MODULOS = [
    "ventas",
    "compras_pro",
    "inventario",
    "productos",
    "clientes",
    # "proveedores",  # ELIMINADO: Ahora integrado en FINANZAS_UNIFICADAS
    "caja",
    "finanzas_unificadas",  # UNIFICADO: Incluye Tesorería, Finanzas y Proveedores
    "contabilidad",
    "rrhh",
    "activos",
    "merma",
    "produccion",
    "transferencias",
    "delivery",
    "whatsapp",
    "tarjetas",
    "fidelidad",
    "etiquetas",
    "ticket_designer",
    "hardware",
    "configuracion",
    "modulos_config",
    "inteligencia_bi",  # UNIFICADO: Incluye BI, BI Pro y Decisiones
]

# Módulos que SIEMPRE deben ser visibles sin importar los toggles de ModuleConfig
# (Fase 0 whitelist — Plan Maestro SPJ v13.4)
WHITELIST_SIEMPRE_VISIBLE = {
    "FINANZAS_UNIFICADAS",  # UNIFICADO: Reemplaza TESORERIA + FINANZAS + PROVEEDORES
    "ACTIVOS",
    "PLANEACION_COMPRAS",
    "WHATSAPP",
    "INTELIGENCIA_BI",  # UNIFICADO: Reemplaza DECISIONES + BI_PRO + INTELIGENCIA_BI
    "CONFIG_SEGURIDAD",
}

def _build_sidebar_qss() -> str:
    """
    Genera el QSS del sidebar desde design_tokens.Colors.SIDEBAR.

    Invariante de producto (Plan Maestro SPJ v13.4): el sidebar es
    SIEMPRE oscuro independientemente del tema activo de la aplicación.
    El QSS resultante contiene literalmente:

        QFrame#MenuLateral {
            background-color: #020617;   ← Colors.SIDEBAR.BG
            color:            #E2E8F0;   ← Colors.SIDEBAR.TEXT
            border-right:     1px solid #1E293B;  ← Colors.SIDEBAR.BORDER
        }

    El sidebar NO se parametriza por tema (claro/oscuro) — siempre es
    oscuro. Pero los hex codes se centralizan aquí: cualquier ajuste
    futuro en design_tokens.py propaga automáticamente al sidebar.
    """
    s = Colors.SIDEBAR
    n = Colors.NEUTRAL
    return f"""
        QFrame#MenuLateral {{
            background-color: {s.BG};
            color: {s.TEXT};
            border-right: 1px solid {s.BORDER};
        }}
        QFrame#MenuLateral QScrollArea {{
            border: none;
            background-color: transparent;
        }}
        QFrame#MenuLateral QWidget#ContenedorBotones {{
            background-color: transparent;
        }}
        QFrame#MenuLateral QLabel[class="SeccionHeader"] {{
            color: {n.SLATE_500};
            font-size: {Typography.SIZE_SM};
            font-weight: {Typography.WEIGHT_BOLD};
            text-transform: uppercase;
            padding-left: 15px;
            margin-top: 20px;
            margin-bottom: 8px;
            letter-spacing: 0.5px;
        }}
        QFrame#MenuLateral QPushButton {{
            background-color: transparent;
            color: {s.ICON};
            text-align: left;
            padding: 12px 16px;
            font-size: {Typography.SIZE_LG};
            font-weight: {Typography.WEIGHT_MEDIUM};
            border: none;
            border-radius: {Borders.RADIUS_LG}px;
            margin: 2px 8px;
        }}
        QFrame#MenuLateral QLineEdit#SidebarSearch {{
            background-color: {n.SLATE_900};
            color: {s.TEXT};
            border: 1px solid {n.SLATE_700};
            border-radius: {Borders.RADIUS_LG}px;
            padding: 8px 10px;
            selection-background-color: {Colors.PRIMARY.BASE};
        }}
        QFrame#MenuLateral QPushButton:hover {{
            background-color: {s.HOVER};
            color: {s.TEXT};
        }}
        QFrame#MenuLateral QPushButton:pressed {{
            background-color: {s.ACTIVE};
            color: {n.WHITE};
        }}
        QFrame#MenuLateral QPushButton:checked {{
            background-color: {s.ACTIVE};
            color: {n.WHITE};
            font-weight: {Typography.WEIGHT_SEMIBOLD};
            border: none;
        }}
        QFrame#MenuLateral QPushButton:focus {{
            outline: none;
            border: none;
        }}
        QFrame#MenuLateral QScrollBar:vertical {{
            background-color: {s.BG};
            width: 6px;
            margin: 0;
            border: none;
        }}
        QFrame#MenuLateral QScrollBar::handle:vertical {{
            background-color: {n.SLATE_700};
            border-radius: 3px;
            min-height: 20px;
        }}
        QFrame#MenuLateral QScrollBar::handle:vertical:hover {{
            background-color: {n.SLATE_600};
        }}
        QFrame#MenuLateral QScrollBar::add-line:vertical,
        QFrame#MenuLateral QScrollBar::sub-line:vertical {{
            height: 0;
            background: none;
        }}
    """


_SIDEBAR_DARK_QSS = _build_sidebar_qss()

class MenuLateral(QFrame):
    # Señal maestra que avisa a la ventana principal a qué módulo queremos ir
    opcion_seleccionada = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MenuLateral")
        self.setFixedWidth(240) # Lo hicimos un poco más ancho para que quepan los nombres largos
        self.enforce_dark_mode()
        self._permisos = set()
        self._rol = ""
        self._menu_buttons = []
        self._configurar_ui()

    def enforce_dark_mode(self) -> None:
        """Sidebar SIEMPRE oscuro — re-aplica después de cualquier cambio de tema global."""
        self.setStyleSheet(_SIDEBAR_DARK_QSS)
        # Forzar color en cada SeccionHeader individualmente para que gane
        # sobre el QSS de la app (widget-level > app-level en Qt, pero reforzamos)
        from PyQt5.QtWidgets import QLabel as _QLabel
        for child in self.findChildren(_QLabel):
            if child.property("class") == "SeccionHeader":
                child.setStyleSheet(
                    f"color: {Colors.NEUTRAL.SLATE_500};"
                    f" font-size: {Typography.SIZE_SM};"
                    f" font-weight: {Typography.WEIGHT_BOLD};"
                    f" padding-left: 15px; margin-top: 20px; margin-bottom: 8px;"
                    f" background: transparent;"
                )

    def _configurar_ui(self):
        # Layout principal del Frame
        layout_principal = QVBoxLayout(self)
        layout_principal.setContentsMargins(0, 0, 0, 0)
        layout_principal.setSpacing(0)

        # ==========================================
        # 1. ZONA DEL LOGO Y NOMBRE DE LA EMPRESA
        # ==========================================
        zona_logo = QFrame()
        zona_logo.setStyleSheet(
            f"background-color: {Colors.SIDEBAR.BG};"
            f" border-bottom: 1px solid {Colors.SIDEBAR.BORDER};"
        )
        layout_logo = QVBoxLayout(zona_logo)
        layout_logo.setContentsMargins(10, 24, 10, 24)
        layout_logo.setAlignment(Qt.AlignCenter)

        self.lbl_logo = QLabel()
        self.lbl_logo.setAlignment(Qt.AlignCenter)
        # Intenta cargar el logo
        pixmap = QPixmap("assets/logo.png")
        if not pixmap.isNull():
            self.lbl_logo.setPixmap(pixmap.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.lbl_logo.setText("🏢\nSPJ POS")
            self.lbl_logo.setStyleSheet(
                f"font-size: 28px;"
                f" font-weight: {Typography.WEIGHT_BOLD};"
                f" color: {Colors.NEUTRAL.WHITE};"
            )

        layout_logo.addWidget(self.lbl_logo)

        lbl_version = QLabel("Enterprise Edition v13.4")
        lbl_version.setAlignment(Qt.AlignCenter)
        lbl_version.setStyleSheet(
            f"color: {Colors.PRIMARY.BASE};"
            f" font-size: {Typography.SIZE_SM};"
            f" font-weight: {Typography.WEIGHT_SEMIBOLD};"
            f" letter-spacing: 0.5px;"
        )
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

        # Filtro rápido para navegar todos los módulos del menú lateral.
        self.txt_buscar_modulo = create_input_field(
            self,
            placeholder="🔎 Buscar módulo... (Ctrl+K)",
            fixed_width=206,
        )
        self.txt_buscar_modulo.setObjectName("SidebarSearch")
        self.txt_buscar_modulo.textChanged.connect(self._filtrar_modulos_menu)
        # Atajo Ctrl+K para enfocar la búsqueda — patrón estándar SaaS
        # (Notion, Linear, Stripe). El parent es self (sidebar), pero el
        # contexto Qt.ApplicationShortcut hace que funcione desde cualquier
        # widget de la app.
        self._search_shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        self._search_shortcut.setContext(Qt.ApplicationShortcut)
        self._search_shortcut.activated.connect(self._enfocar_buscador)
        row_busqueda = QVBoxLayout()
        row_busqueda.setContentsMargins(12, 10, 12, 8)
        row_busqueda.addWidget(self.txt_buscar_modulo)
        layout_botones.addLayout(row_busqueda)

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
        # ELIMINADO: Botón "Proveedores" — ahora integrado en FINANZAS_UNIFICADAS

        # --- SECCIÓN: PRODUCCIÓN ---
        layout_botones.addWidget(self._crear_header("Producción"))
        layout_botones.addWidget(self._crear_boton("🔪 Procesamiento Cárnico", "PRODUCCION"))
        layout_botones.addWidget(self._crear_boton("🏷️ Etiquetas", "ETIQUETAS"))
        layout_botones.addWidget(self._crear_boton("📈 Planeación de Compras", "PLANEACION_COMPRAS"))

        # --- SECCIÓN: ADMINISTRACIÓN ---
        layout_botones.addWidget(self._crear_header("Administración"))
        # FINANZAS UNIFICADAS: Incluye Tesorería, Contabilidad y Gestión de Proveedores
        # Todos consumen core/services/finance/* (single source of truth)
        layout_botones.addWidget(self._crear_boton("💰 Finanzas", "FINANZAS_UNIFICADAS"))
        layout_botones.addWidget(self._crear_boton("🏗️ Activos", "ACTIVOS"))
        layout_botones.addWidget(self._crear_boton("👔 Recursos Humanos", "RRHH"))
        layout_botones.addWidget(self._crear_boton("⭐ Fidelización", "GROWTH_ENGINE"))
        layout_botones.addWidget(self._crear_boton("💳 Tarjetas Fidelidad", "TARJETAS_FIDELIDAD"))
        # INTELIGENCIA DE NEGOCIOS UNIFICADA: Incluye BI, BI Pro, Decisiones y Planeación
        # Todos consumen core/services/analytics/analytics_engine.py
        layout_botones.addWidget(self._crear_boton("📈 Inteligencia de Negocios", "INTELIGENCIA_BI"))
        layout_botones.addWidget(self._crear_boton("📱 Pedidos WhatsApp", "WHATSAPP"))

        # --- SECCIÓN: SISTEMA ---
        layout_botones.addWidget(self._crear_header("Sistema"))
        layout_botones.addWidget(self._crear_boton("🎨 Diseñador Tickets", "DISEÑADOR_TICKETS"))
        layout_botones.addWidget(self._crear_boton("🖨️ Hardware", "CONFIG_HARDWARE"))
        layout_botones.addWidget(self._crear_boton("🔌 Configuración Módulos", "CONFIG_MODULOS"))
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
        zona_inferior.setStyleSheet(
            f"background-color: {Colors.SIDEBAR.BG};"
            f" border-top: 1px solid {Colors.SIDEBAR.BORDER};"
        )
        layout_inferior = QVBoxLayout(zona_inferior)
        layout_inferior.setContentsMargins(8, 12, 8, 12)
        
        btn_logout = self._crear_boton("🚪 Cerrar Sesión", "LOGOUT")
        # El hover se maneja por el estilo global del sidebar
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
            "FINANZAS_UNIFICADAS", "RRHH", "ACTIVOS", "CONFIG_SEGURIDAD",
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
          finance_enabled         → FINANZAS_UNIFICADAS (reemplaza treasury_central_enabled)
        """
        # Mapeo: código de botón → clave de toggle en module_config
        TOGGLE_MAP = {
            "PLANEACION_COMPRAS": "forecasting_enabled",
            "WHATSAPP":           "whatsapp_integration_enabled",
            "RRHH":               "rrhh_enabled",
            "FINANZAS_UNIFICADAS": "finance_enabled",
            "INTELIGENCIA_BI":    "analytics_enabled",
        }

        from PyQt5.QtWidgets import QPushButton as _QPB
        for btn in self.findChildren(_QPB):
            codigo = btn.property("modulo_codigo")
            if not codigo or codigo == "LOGOUT":
                continue
            # Módulos en whitelist SIEMPRE visibles (Fase 0 — Plan Maestro)
            if codigo in WHITELIST_SIEMPRE_VISIBLE:
                btn.setVisible(True)
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
        self.lbl_logo.setStyleSheet(
            f"font-size: 20px;"
            f" font-weight: {Typography.WEIGHT_BOLD};"
            f" color: {Colors.NEUTRAL.WHITE};"
        )

    def _crear_boton(self, texto, codigo_modulo):
        """Fabrica el botón, lo etiqueta con su código y conecta la señal.

        El botón es checkable para que el sidebar pueda marcar visualmente
        cuál módulo está activo. set_modulo_activo() administra el grupo
        exclusivo (solo uno checked a la vez). LOGOUT no se marca.
        """
        btn = QPushButton(texto)
        btn.setProperty("modulo_codigo", codigo_modulo)
        btn.setProperty("menu_label", texto)
        btn.setObjectName("SidebarModuleButton")
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn.setMinimumHeight(40)
        btn.setCursor(Qt.PointingHandCursor)
        if codigo_modulo != "LOGOUT":
            btn.setCheckable(True)
        btn.clicked.connect(lambda _, m=codigo_modulo: self._on_clic_boton(m))
        self._menu_buttons.append(btn)
        return btn

    def _on_clic_boton(self, codigo_modulo: str) -> None:
        """Marca el botón activo y emite la señal para la ventana principal."""
        if codigo_modulo != "LOGOUT":
            self.set_modulo_activo(codigo_modulo)
        self.opcion_seleccionada.emit(codigo_modulo)

    def set_modulo_activo(self, codigo_modulo: str) -> None:
        """
        Marca visualmente cuál módulo está activo en el sidebar.

        Es seguro llamar desde main_window cuando el usuario navega
        programáticamente (ej. atajos de teclado, click en KPICard del
        dashboard) — el botón correspondiente queda checked y los demás
        unchecked, simulando un grupo exclusivo.
        """
        for btn in self._menu_buttons:
            if not btn.isCheckable():
                continue
            btn.setChecked(btn.property("modulo_codigo") == codigo_modulo)

    def _enfocar_buscador(self) -> None:
        """Selecciona y enfoca el campo de búsqueda (handler de Ctrl+K)."""
        self.txt_buscar_modulo.setFocus()
        self.txt_buscar_modulo.selectAll()

    def _filtrar_modulos_menu(self, text: str) -> None:
        """Filtra botones de módulos por texto para menús con muchos accesos."""
        needle = self._normalizar(text)
        for btn in self._menu_buttons:
            label = self._normalizar(str(btn.property("menu_label") or ""))
            codigo = self._normalizar(str(btn.property("modulo_codigo") or ""))
            visible = (not needle) or (needle in label) or (needle in codigo)
            btn.setVisible(visible)

    @staticmethod
    def _normalizar(texto: str) -> str:
        if not texto:
            return ""
        raw = unicodedata.normalize("NFKD", texto)
        return "".join(c for c in raw if not unicodedata.combining(c)).strip().lower()
