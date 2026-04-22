
# interfaz/main_window.py — SPJ POS v12
# ── Ventana Principal / Orquestador Visual ────────────────────────────────────
# Conecta TODOS los módulos disponibles mediante try/except por seguridad.
# Un módulo con error de sintaxis NO derrumba el sistema completo.
import logging
from PyQt5.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QStackedWidget,
                             QLabel, QDialog, QVBoxLayout, QLineEdit, QPushButton,
                             QMessageBox, QFrame, QMenuBar, QSizePolicy, QComboBox, QFormLayout)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap

logger = logging.getLogger("spj.main_window")

from interfaz.menu_lateral import MenuLateral

# ─────────────────────────────────────────────────────────────────────────────
# IMPORTACIÓN SEGURA DE TODOS LOS MÓDULOS
# Cada módulo en try/except independiente: error en uno NO afecta a los demás.
# ─────────────────────────────────────────────────────────────────────────────

# ── Operaciones ──────────────────────────────────────────────────────────────
try:
    from modulos.ventas import ModuloVentas
except Exception as e:
    ModuloVentas = None
    logger.error("Error cargando ModuloVentas: %s", e)

try:
    from modulos.caja import ModuloCaja
except Exception as e:
    ModuloCaja = None
    logger.error("Error cargando ModuloCaja: %s", e)

try:
    from modulos.inventario_local import ModuloInventarioLocal
except Exception as e:
    ModuloInventarioLocal = None
    logger.error("Error cargando ModuloInventarioLocal: %s", e)

try:
    from modulos.productos import ModuloProductos
except Exception as e:
    ModuloProductos = None
    logger.error("Error cargando ModuloProductos: %s", e)

try:
    from modulos.clientes import ModuloClientes
except Exception as e:
    ModuloClientes = None
    logger.error("Error cargando ModuloClientes: %s", e)

try:
    from modulos.delivery import ModuloDelivery
except Exception as e:
    ModuloDelivery = None
    logger.error("Error cargando ModuloDelivery: %s", e)

try:
    from modulos.compras_pro import ModuloComprasPro
except Exception as e:
    ModuloComprasPro = None
    logger.error("Error cargando ModuloComprasPro: %s", e)

try:
    from modulos.cotizaciones import ModuloCotizaciones
except Exception as e:
    ModuloCotizaciones = None
    logger.error("Error cargando ModuloCotizaciones: %s", e)

try:
    from modulos.merma import ModuloMerma
except Exception as e:
    ModuloMerma = None
    logger.error("Error cargando ModuloMerma: %s", e)

# ELIMINADO: Módulo Proveedores independiente — ahora integrado en FINANZAS_UNIFICADAS
# La gestión de proveedores se accede desde la pestaña "Proveedores" dentro de Finanzas Unificadas
ModuloProveedores = None

try:
    from modulos.etiquetas import ModuloEtiquetas
except Exception as e:
    ModuloEtiquetas = None
    logger.error("Error cargando ModuloEtiquetas: %s", e)

try:
    from modulos.config_modules import ModuloConfigModulos
except Exception as e:
    ModuloConfigModulos = None
    logger.error("Error cargando ModuloConfigModulos: %s", e)

# ── Finanzas & Admin (UNIFICADOS) ───────────────────────────────────────────
# Nota: Tesorería, Finanzas y Proveedores ahora usan servicios unificados
#       en core/services/finance/ pero mantienen UI independiente para UX
try:
    from modulos.finanzas_unificadas import ModuloFinanzasUnificadas as ModuloFinanzas
except Exception as e:
    ModuloFinanzas = None
    logger.error("Error cargando ModuloFinanzas: %s", e)

# ELIMINADO: Módulo Tesorería independiente — ahora integrado en FINANZAS_UNIFICADAS
ModuloTesoreria = None

try:
    from modulos.rrhh import ModuloRRHH
except Exception as e:
    ModuloRRHH = None
    logger.error("Error cargando ModuloRRHH: %s", e)

try:
    from modulos.activos import ModuloActivos
except Exception as e:
    ModuloActivos = None
    logger.error("Error cargando ModuloActivos: %s", e)

# ── Marketing & Fidelidad ─────────────────────────────────────────────────────
try:
    from modulos.tarjetas import ModuloTarjetas
except Exception as e:
    ModuloTarjetas = None
    logger.error("Error cargando ModuloTarjetas: %s", e)

try:
    from modulos.fidelidad_config import ModuloFidelidadConfig
except Exception as e:
    ModuloFidelidadConfig = None
    logger.error("Error cargando ModuloFidelidadConfig: %s", e)

try:
    from modulos.loyalty_card_designer import ModuloLoyaltyCardDesigner
except Exception as e:
    ModuloLoyaltyCardDesigner = None
    logger.error("Error cargando ModuloLoyaltyCardDesigner: %s", e)

try:
    from modulos.reportes_bi_v2 import ModuloReportesBIv2
except Exception as e:
    ModuloReportesBIv2 = None
    logger.error("Error cargando ModuloReportesBIv2: %s", e)

try:
    from modulos.planeacion_compras import ModuloPlaneacionCompras
except Exception as e:
    ModuloPlaneacionCompras = None
    logger.error("Error cargando ModuloPlaneacionCompras: %s", e)

# ── Producción & Recetas ──────────────────────────────────────────────────────
try:
    from modulos.produccion import ModuloProduccion
except Exception as e:
    ModuloProduccion = None
    logger.error("Error cargando ModuloProduccion: %s", e)

# produccion_carnica unificada en ModuloProduccion (tabs Cárnica + Recetas)

try:
    from modulos.whatsapp_module import ModuloWhatsApp
except Exception as e:
    ModuloWhatsApp = None
    logger.error("Error cargando ModuloWhatsApp: %s", e)


# ── Configuración & Herramientas ──────────────────────────────────────────────
try:
    from modulos.configuracion import ModuloConfiguracion
except Exception as e:
    ModuloConfiguracion = None
    logger.error("Error cargando ModuloConfiguracion: %s", e)

try:
    from modulos.config_hardware import ModuloConfigHardware
except Exception as e:
    ModuloConfigHardware = None
    logger.error("Error cargando ModuloConfigHardware: %s", e)

try:
    from modulos.ticket_designer import ModuloTicketDesigner
except Exception as e:
    ModuloTicketDesigner = None
    logger.error("Error cargando ModuloTicketDesigner: %s", e)

try:
    from modulos.transferencias import ModuloTransferencias
except Exception as e:
    ModuloTransferencias = None
    logger.error("Error cargando ModuloTransferencias: %s", e)

# BI/Analytics UNIFICADO: Decisiones, BI Pro e Inteligencia BI usan el mismo motor
# Nota: Todos los módulos de BI ahora consumen core/services/analytics/analytics_engine.py
try:
    from modulos.reportes_bi_v2 import ModuloReportesBIv2 as ModuloDecisiones
except Exception:
    ModuloDecisiones = None

# ModuloReportesBIv2 ya está importado arriba (línea 140-143)
# No se necesita import duplicado


# ─────────────────────────────────────────────────────────────────────────────
# DIÁLOGO DE LOGIN
# ─────────────────────────────────────────────────────────────────────────────
class DialogoLogin(QDialog):
    def __init__(self, auth_service, parent=None):
        super().__init__(parent)
        self.auth_service = auth_service
        self.usuario_autenticado = None
        self._sucursal_instalacion = self._leer_sucursal_instalacion()

        self.setWindowTitle("SPJ POS — Iniciar Sesión")
        self.setFixedSize(340, 450)
        
        # Usar objectName para que el tema global aplique estilos consistentes
        self.setObjectName("loginDialog")
        self._configurar_ui()

    def _leer_sucursal_instalacion(self) -> dict:
        """Lee la sucursal configurada para ESTA instalación."""
        try:
            db = getattr(getattr(self.auth_service, 'repo', None), 'db', None)
            if not db:
                return {'id': 1, 'nombre': 'Principal'}
            # Leer sucursal de la instalación (configurada por admin)
            row = db.execute(
                "SELECT valor FROM configuraciones WHERE clave='sucursal_instalacion_id'"
            ).fetchone()
            suc_id = int(row[0]) if row and row[0] else 1
            # Obtener nombre
            suc_row = db.execute(
                "SELECT nombre FROM sucursales WHERE id=?", (suc_id,)
            ).fetchone()
            nombre = suc_row[0] if suc_row else 'Principal'
            return {'id': suc_id, 'nombre': nombre}
        except Exception:
            return {'id': 1, 'nombre': 'Principal'}

    def _configurar_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(30, 30, 30, 30)

        # Logo empresa - CORREGIDO: Sin cortes, escalado proporcional adecuado y visible completo
        self.lbl_logo = QLabel()
        self.lbl_logo.setAlignment(Qt.AlignCenter)
        self.lbl_logo.setObjectName("loginLogo")
        self.lbl_logo.setFixedHeight(90)
        self.lbl_logo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.lbl_logo.setScaledContents(False)

        try:
            from PyQt5.QtGui import QPixmap as _QP
            import os
            _db = getattr(getattr(self.auth_service, 'repo', None), 'db', None)
            if _db:
                _r = _db.execute("SELECT valor FROM configuraciones WHERE clave='logo_path'").fetchone()
                if _r and _r[0] and os.path.exists(_r[0]):
                    _pix = _QP(_r[0])
                    if not _pix.isNull():
                        _scaled = _pix.scaled(80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        self.lbl_logo.setPixmap(_scaled)
                        self.lbl_logo.setAlignment(Qt.AlignCenter)
                    else:
                        raise Exception()
                else:
                    raise Exception()
            else:
                raise Exception()
        except Exception:
            self.lbl_logo.setText("🏢")
            self.lbl_logo.setStyleSheet("font-size: 40px; background-color: transparent;")
            self.lbl_logo.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.lbl_logo)

        titulo = QLabel("Iniciar Sesión")
        titulo.setObjectName("loginTitle")
        titulo.setAlignment(Qt.AlignCenter)
        layout.addWidget(titulo)

        # Mostrar sucursal de esta instalación (solo info, no editable)
        suc_nombre = self._sucursal_instalacion.get('nombre', 'Principal')
        lbl_suc = QLabel(f"Sucursal: {suc_nombre}")
        lbl_suc.setAlignment(Qt.AlignCenter)
        lbl_suc.setObjectName("loginSucursal")
        lbl_suc.setWordWrap(True)
        layout.addWidget(lbl_suc)

        layout.addSpacing(10)  # Espacio extra antes de inputs

        self.txt_usuario = QLineEdit()
        self.txt_usuario.setPlaceholderText("Usuario o PIN")
        self.txt_usuario.setObjectName("inputField")
        self.txt_usuario.setMinimumHeight(40)
        
        self.txt_password = QLineEdit()
        self.txt_password.setPlaceholderText("Contraseña")
        self.txt_password.setEchoMode(QLineEdit.Password)
        self.txt_password.setObjectName("inputField")
        self.txt_password.setMinimumHeight(40)
        self.txt_password.returnPressed.connect(self.intentar_login)
        
        layout.addWidget(self.txt_usuario)
        layout.addWidget(self.txt_password)

        layout.addStretch()  # Empuja el botón hacia abajo

        self.btn_login = QPushButton("ENTRAR AL SISTEMA")
        self.btn_login.setObjectName("primaryBtn")
        self.btn_login.setCursor(Qt.PointingHandCursor)
        self.btn_login.setMinimumHeight(45)
        self.btn_login.clicked.connect(self.intentar_login)
        layout.addWidget(self.btn_login)

        # Mensaje de error (oculto por defecto)
        self.lbl_error = QLabel("")
        self.lbl_error.setObjectName("errorMsg")
        self.lbl_error.setAlignment(Qt.AlignCenter)
        self.lbl_error.setWordWrap(True)
        layout.addWidget(self.lbl_error)

    def intentar_login(self):
        usuario  = self.txt_usuario.text().strip()
        password = self.txt_password.text()

        if not usuario or not password:
            QMessageBox.warning(self, "Aviso", "Por favor ingresa tu usuario y contraseña.")
            return

        try:
            resultado = self.auth_service.authenticate(usuario, password)
            if not resultado:
                return

            # v13.4: Forzar la sucursal de ESTA instalación (no la del usuario)
            resultado['sucursal_id'] = self._sucursal_instalacion['id']
            resultado['sucursal_nombre'] = self._sucursal_instalacion['nombre']

            self.usuario_autenticado = resultado
            self.accept()

        except PermissionError as e:
            QMessageBox.warning(self, "Acceso Denegado", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al iniciar sesión:\n{str(e)}")


try:
    from modulos.config_interfaz import ModuloConfigUI
except Exception:
    ModuloConfigUI = None

class MainWindow(QMainWindow):
    """Ventana principal del ERP SPJ POS."""

    def __init__(self, container):
        super().__init__()
        self.container       = container
        self.usuario_actual  = None
        self.indices_pantallas = {}

        self.setWindowTitle("ERP SPJ POS v13.4 — Enterprise Edition")
        self.resize(1280, 800)
        self.setMinimumSize(1024, 600)

        self._configurar_menu_superior()
        self._configurar_ui()
        self._configurar_busqueda_global()
        self._cargar_tema_inicial()
        self._cargar_logo_empresa()

    # ── Menú superior ────────────────────────────────────────────────────────
    def _configurar_menu_superior(self):
        mb = self.menuBar()
        mb.setStyleSheet("""
            QMenuBar           { background:#2D3748; color:white; font-size:13px; }
            QMenuBar::item:selected { background:#4A5568; }
            QMenu              { background:#1E1E1E; color:white; border:1px solid #4A5568; }
            QMenu::item:selected { background:#3498DB; }
        """)
        m_archivo = mb.addMenu("📁 Archivo")
        m_archivo.addAction("🚪 Cerrar sesión").triggered.connect(
            lambda: self.manejar_navegacion("LOGOUT"))
        m_archivo.addAction("❌ Salir").triggered.connect(self.close)

        m_iface = mb.addMenu("🎨 Interfaz")
        # v13.4: Solo dark mode toggle — no múltiples temas
        self._action_dark = m_iface.addAction("🌙 Modo Oscuro")
        self._action_dark.setCheckable(True)
        self._action_dark.triggered.connect(
            lambda checked: self._aplicar_tema("Dark" if checked else "Light"))

        m_hw = mb.addMenu("🖨️ Hardware")
        m_hw.addAction("⚙️ Configurar Dispositivos").triggered.connect(
            lambda: self.manejar_navegacion("CONFIG_HARDWARE"))

        # ── Menú Ayuda con Diagnóstico ────────────────────────────────────────
        m_ayuda = mb.addMenu("❓ Ayuda")
        m_ayuda.addAction("🔧 Diagnóstico del Sistema").triggered.connect(
            self._mostrar_diagnostico)
        m_ayuda.addAction("ℹ️ Acerca de SPJ POS").triggered.connect(
            self._mostrar_acerca_de)

        # ── Badge de pedidos WhatsApp ─────────────────────────────────────────
        self._btn_pedidos = mb.addMenu("📦 Pedidos (0)")
        self._btn_pedidos.setObjectName("pedidos_badge")
        self._btn_pedidos.setStyleSheet("QMenu::item { background:#e74c3c; color:white; font-weight:bold; }")
        self._btn_pedidos.aboutToShow.connect(self._abrir_panel_pedidos)

    # ── UI principal ──────────────────────────────────────────────────────────
    def _configurar_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_lay = QVBoxLayout(central)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)

        # Content area (menu + stack)
        content = QWidget()
        lay = QHBoxLayout(content)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.menu = MenuLateral()
        self.menu.opcion_seleccionada.connect(self.manejar_navegacion)
        lay.addWidget(self.menu)

        self.stack = QStackedWidget()
        # v13.4: No hardcoded background — let theme QSS control it
        lay.addWidget(self.stack)
        main_lay.addWidget(content, 1)

        # v13.4: Barra de sesión (📍 Sucursal — 👤 Usuario — Rol)
        self._session_bar = QLabel("  Esperando inicio de sesión...")
        self._session_bar.setFixedHeight(28)
        self._session_bar.setStyleSheet(
            "background:#2C3E50; color:#ecf0f1; font-size:11px; padding:0 12px;")
        main_lay.addWidget(self._session_bar)

        self._construir_todas_las_pantallas()

    # ── Construir pantallas ───────────────────────────────────────────────────
    def _construir_todas_las_pantallas(self):
        self.indices_pantallas["BIENVENIDA"] = self.stack.addWidget(
            self._crear_pantalla_bienvenida())

        # ── Operaciones ──────────────────────────────────────────────────────
        try:
            from ui.dashboard import DashboardWidget
            self._conectar("DASHBOARD", DashboardWidget, "📊 Dashboard")
        except Exception:
            pass

        self._conectar("POS",            ModuloVentas,         "🛒 Punto de Venta")
        self._conectar("CAJA",           ModuloCaja,           "💰 Caja / Cortes Z")
        self._conectar("INVENTARIO",     ModuloInventarioLocal,"📦 Inventario")
        self._conectar("TRANSFERENCIAS", ModuloTransferencias, "🔄 Transferencias")
        self._conectar("PRODUCTOS",      ModuloProductos,      "🏷️ Productos")
        self._conectar("CLIENTES",       ModuloClientes,       "👥 Clientes")
        self._conectar("MERMA",          ModuloMerma,          "🗑️ Merma")

        # ── Comercial ────────────────────────────────────────────────────────
        self._conectar("DELIVERY",       ModuloDelivery,       "🛵 Delivery")
        self._conectar("COMPRAS",        ModuloComprasPro,     "🛒 Compras")
        self._conectar("COTIZACIONES",   ModuloCotizaciones,   "📋 Cotizaciones")
        # ELIMINADO: _conectar("PROVEEDORES", ...) — módulo integrado en FINANZAS_UNIFICADAS

        # ── Producción ───────────────────────────────────────────────────────
        self._conectar("PRODUCCION",       ModuloProduccion,       "🔪 Procesamiento Cárnico")
        self._conectar("ETIQUETAS",        ModuloEtiquetas,        "🏷️ Etiquetas")
        self._conectar("PLANEACION_COMPRAS", ModuloPlaneacionCompras, "📈 Planeación de Compras")

        # ── Administración ───────────────────────────────────────────────────
        # FINANZAS UNIFICADAS: Unifica Tesorería, Finanzas y Proveedores en un solo módulo UI
        # Todos consumen core/services/finance/* (single source of truth)
        self._conectar("FINANZAS_UNIFICADAS", ModuloFinanzas, "💰 Finanzas Unificadas")
        self._conectar("ACTIVOS",             ModuloActivos,        "🏗️ Activos")
        self._conectar("RRHH",                ModuloRRHH,           "👔 Recursos Humanos")
        self._conectar("GROWTH_ENGINE",       ModuloFidelidadConfig,  "⭐ Fidelización")
        self._conectar("TARJETAS_FIDELIDAD",  ModuloTarjetas,         "💳 Tarjetas Fidelidad")
        # INTELIGENCIA DE NEGOCIOS UNIFICADA: Unifica BI, BI Pro, Decisiones y Planeación
        # Todos consumen core/services/analytics/analytics_engine.py
        self._conectar("INTELIGENCIA_BI",     ModuloReportesBIv2,     "📈 Inteligencia de Negocios")
        self._conectar("WHATSAPP",            ModuloWhatsApp,         "📱 Pedidos WhatsApp")

        # ── Sistema ──────────────────────────────────────────────────────────
        self._conectar("DISEÑADOR_TICKETS", ModuloTicketDesigner, "🎨 Diseñador Tickets")
        self._conectar("CONFIG_HARDWARE",   ModuloConfigHardware, "🖨️ Hardware")
        self._conectar("CONFIG_MODULOS",    ModuloConfigModulos,  "🔌 Configuración Módulos")
        self._conectar("CONFIG_SEGURIDAD",  ModuloConfiguracion,  "🛡️ Configuración")

    def _conectar(self, codigo, clase_widget, titulo_fallback):
        """Carga el módulo real; si falla instancia pantalla de aviso.
        v13.4: Aplica auto-estilizado de botones por keyword."""
        if clase_widget is not None:
            try:
                pantalla = clase_widget(self.container)
                # v13.4: Auto-aplicar colores estándar a botones del módulo
                try:
                    from modulos.spj_styles import apply_spj_buttons, apply_spj_tooltips
                    apply_spj_buttons(pantalla)
                    apply_spj_tooltips(pantalla)
                except Exception:
                    pass
                self.indices_pantallas[codigo] = self.stack.addWidget(pantalla)
                return
            except Exception as e:
                desc = f"Error al cargar módulo:\n{e}"
        else:
            desc = "Módulo en integración..."
        self._registrar_placeholder(codigo, titulo_fallback, desc)

    def _registrar_placeholder(self, codigo, titulo, descripcion):
        w = QWidget()
        lay = QVBoxLayout(w); lay.setAlignment(Qt.AlignCenter)
        lbl_t = QLabel(titulo)
        lbl_t.setStyleSheet("font-size:22px; font-weight:bold;")
        lbl_t.setAlignment(Qt.AlignCenter)
        lbl_d = QLabel(descripcion)
        lbl_d.setStyleSheet("font-size:13px; color:#E74C3C;")
        lbl_d.setAlignment(Qt.AlignCenter)
        lay.addWidget(lbl_t); lay.addWidget(lbl_d)
        self.indices_pantallas[codigo] = self.stack.addWidget(w)

    # ── Pantalla de bienvenida ────────────────────────────────────────────────
    def _crear_pantalla_bienvenida(self):
        w = QWidget()
        lay = QVBoxLayout(w); lay.setAlignment(Qt.AlignCenter); lay.setSpacing(20)
        self.lbl_saludo = QLabel("¡Bienvenido al sistema SPJ POS!")
        self.lbl_saludo.setAlignment(Qt.AlignCenter)
        self.lbl_saludo.setStyleSheet("font-size:24px; font-weight:bold;")
        lbl_sub = QLabel("Enterprise Edition · Selecciona un módulo en el menú lateral")
        lbl_sub.setAlignment(Qt.AlignCenter)
        lbl_sub.setStyleSheet("font-size:13px; opacity:0.7;")
        lay.addWidget(self.lbl_saludo); lay.addWidget(lbl_sub)
        return w

    # ── Login ─────────────────────────────────────────────────────────────────
    def mostrar_login(self):
        self.hide()
        dlg = DialogoLogin(self.container.auth_service, self)
        if dlg.exec_() == QDialog.Accepted:
            self.usuario_actual = dlg.usuario_autenticado
            nombre = self.usuario_actual.get("nombre",
                     self.usuario_actual.get("username", "Usuario"))
            self.lbl_saludo.setText(f"¡Hola, {nombre}! Buen trabajo. 💼")
            try: self._cargar_logo_empresa()
            except Exception: pass
            self._propagar_usuario()
            self.stack.setCurrentIndex(self.indices_pantallas["BIENVENIDA"])
            self.show()
        else:
            self.stack.setCurrentIndex(self.indices_pantallas.get('BIENVENIDA', 0))

    def _propagar_usuario(self):
        """Notifica a todos los módulos cargados el usuario y sucursal actual."""
        if not self.usuario_actual:
            return

        # v13.4: Configurar SessionContext centralizado PRIMERO
        try:
            self.container.set_session_user(self.usuario_actual)
        except Exception:
            pass

        usuario     = self.usuario_actual.get("username", "")
        nombre      = self.usuario_actual.get("nombre", usuario)
        rol         = self.usuario_actual.get("rol", "cajero")
        sucursal_id = self.usuario_actual.get("sucursal_id", 1)
        nombre_suc  = self.usuario_actual.get("sucursal_nombre", "Principal")

        # v13.4: Actualizar barra de sesión
        if hasattr(self, '_session_bar'):
            rol_display = rol.capitalize().replace("_", " ")
            self._session_bar.setText(
                f"  📍 {nombre_suc}  —  👤 {nombre} ({rol_display})  —  "
                f"Sucursal ID: {sucursal_id}")
            # Color según rol
            if rol in ('admin', 'superadmin'):
                self._session_bar.setStyleSheet(
                    "background:#1a252f; color:#e74c3c; font-size:11px; "
                    "padding:0 12px; font-weight:bold;")
            elif rol in ('gerente', 'gerente_rh'):
                self._session_bar.setStyleSheet(
                    "background:#1a252f; color:#f39c12; font-size:11px; "
                    "padding:0 12px; font-weight:bold;")
            else:
                self._session_bar.setStyleSheet(
                    "background:#2C3E50; color:#ecf0f1; font-size:11px; padding:0 12px;")

        # Filtrar menú según rol (RBAC)
        try:
            from security.rbac import get_permisos
            uid = self.usuario_actual.get('id', 0)
            permisos = get_permisos(uid, sucursal_id)
            if hasattr(self.menu, 'set_permisos'):
                self.menu.set_permisos(permisos, rol)
            # v13.4: Guardar permisos en SessionContext
            try:
                self.container.session.set_permisos(permisos)
            except Exception:
                pass
        except Exception:
            pass

        # v13.4 FASES 1-13: Aplicar feature flags al menú tras login
        try:
            mc = getattr(self.container, 'module_config', None)
            if mc and hasattr(self.menu, 'set_module_config'):
                self.menu.set_module_config(mc)
        except Exception:
            pass

        for idx in range(self.stack.count()):
            widget = self.stack.widget(idx)
            if hasattr(widget, "set_usuario_actual"):
                try: widget.set_usuario_actual(usuario, rol)
                except Exception: pass
            if hasattr(widget, "set_sucursal"):
                try: widget.set_sucursal(sucursal_id, nombre_suc)
                except Exception: pass

        # Propagar sucursal activa al AppContainer
        try:
            self.container.set_sucursal_activa(sucursal_id, nombre_suc)
        except Exception as _e:
            import logging; logging.getLogger(__name__).debug("set_sucursal_activa: %s", _e)

        # ── Session timeout: cierra sesión por inactividad ────────────────────
        self._arrancar_session_timeout()

        # ── Inbox POS: mostrar mensajes no leídos tras login ──────────────────
        QTimer.singleShot(800, self._mostrar_inbox_login)

    def _arrancar_session_timeout(self) -> None:
        """Activa el monitor de inactividad (se resetea con mouse/teclado)."""
        try:
            from PyQt5.QtWidgets import QApplication
            from core.auth.session_timeout import SessionTimeoutMonitor
            if not hasattr(self, '_session_monitor'):
                self._session_monitor = SessionTimeoutMonitor.from_config(
                    self.container.db, parent=self
                )
                self._session_monitor.sesion_expirada.connect(
                    lambda: self.manejar_navegacion("LOGOUT")
                )
                self._session_monitor.advertencia.connect(self._on_session_warning)
            QApplication.instance().installEventFilter(self._session_monitor)
            self._session_monitor.iniciar()
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug("session_timeout: %s", e)

    def _on_session_warning(self, segundos: int) -> None:
        """Muestra aviso no bloqueante antes de cerrar sesión."""
        # [spj-dedup] from PyQt5.QtWidgets import QMessageBox
        msg = QMessageBox(self)
        msg.setWindowTitle("Sesión por expirar")
        msg.setText(
            f"⏱️ Tu sesión cerrará en {segundos} segundos por inactividad.\n"
            f"Mueve el mouse o presiona una tecla para continuar."
        )
        msg.setStandardButtons(QMessageBox.Ok)
        msg.setWindowModality(Qt.NonModal)
        msg.show()

    def _mostrar_inbox_login(self) -> None:
        """Muestra notificaciones pendientes del inbox POS al iniciar sesión."""
        try:
            if not hasattr(self.container, 'notification_service'):
                return
            usuario_id = self.usuario_actual.get('id') if self.usuario_actual else None
            if not usuario_id:
                return
            # Buscar empleado_id asociado al usuario
            row = self.container.db.execute(
                "SELECT id FROM personal WHERE activo=1 LIMIT 1"
            ).fetchone()
            if not row:
                return
            notifs = self.container.notification_service.get_inbox_empleado(
                row[0], solo_no_leidos=True
            )
            if not notifs:
                return
            from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QScrollArea, QWidget
            dlg = QDialog(self)
            dlg.setWindowTitle(f"📬 Tienes {len(notifs)} notificaciones")
            dlg.setMinimumWidth(420)
            lay = QVBoxLayout(dlg)
            scroll = QScrollArea(); scroll.setWidgetResizable(True)
            container_w = QWidget(); c_lay = QVBoxLayout(container_w)
            for n in notifs[:10]:
                card = QLabel(f"<b>{n['titulo']}</b><br><small>{n['created_at'][:16]}</small>")
                card.setStyleSheet(
                    "border:1px solid #ddd;border-radius:4px;padding:8px;"
                    "background:white;margin:2px;")
                card.setWordWrap(True)
                c_lay.addWidget(card)
            c_lay.addStretch()
            scroll.setWidget(container_w)
            lay.addWidget(scroll)
            btn = QPushButton("✅ Marcar todas como leídas y cerrar")
            btn.setStyleSheet("background:#27ae60;color:white;padding:8px;border-radius:4px;")
            btn.clicked.connect(dlg.accept)
            lay.addWidget(btn)
            dlg.exec_()
            # Marcar leídas
            self.container.notification_service.marcar_inbox_leido(
                empleado_id=row[0]
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug("inbox_login: %s", e)

    # ── Navegación ────────────────────────────────────────────────────────────
    def mostrar_notif_update(self, info: dict) -> None:
        """Muestra notificación de nueva versión disponible."""
        # [spj-dedup] from PyQt5.QtWidgets import QMessageBox
        resp = QMessageBox.information(
            self, "🆕 Nueva versión disponible",
            f"Versión {info['version']} disponible.\n\n{info.get('notas','')}\n\n"
            f"Descarga en: {info.get('url','')}",
            QMessageBox.Ok
        )

    def _iniciar_gestor_notificaciones(self) -> None:
        """Inicia notificaciones: EventBus (event-driven) + GestorNotificaciones (fallback polling)."""
        # v13.1: Subscribe to PEDIDO_NUEVO via EventBus (instant, no polling)
        try:
            from core.events.event_bus import get_bus, PEDIDO_NUEVO
            get_bus().subscribe(
                PEDIDO_NUEVO,
                lambda data: self._on_pedido_nuevo_bus(data),
                label="main_window_badge"
            )
        except Exception as _e:
            import logging; logging.getLogger(__name__).debug("EventBus PEDIDO_NUEVO sub: %s", _e)

        # Fallback: GestorNotificaciones polling (30s — reduced from original)
        try:
            from services.notificaciones import GestorNotificaciones
            self._gestor_notif = GestorNotificaciones(
                self.container.db, intervalo_ms=30000  # 30s fallback
            )
            self._gestor_notif.pedido_nuevo.connect(self._on_pedido_nuevo)
            self._gestor_notif.iniciar()  # QObject/QTimer — usar iniciar(), no start()
        except Exception as _e:
            import logging; logging.getLogger(__name__).debug("GestorNotificaciones: %s", _e)

    def _on_pedido_nuevo_bus(self, data: dict) -> None:
        """Handler EventBus — llamado desde hilo del executor, usa invokeMethod para UI."""
        from PyQt5.QtCore import QMetaObject, Qt
        try:
            QMetaObject.invokeMethod(
                self, "_on_pedido_nuevo",
                Qt.QueuedConnection,
            )
        except Exception:
            pass  # fallback silencioso si la ventana ya cerró
    def _on_pedido_nuevo(self, pedido: dict) -> None:
        """Actualiza el badge y muestra notificación cuando llega pedido WA."""
        try:
            # Contar pedidos sin atender
            n = self.container.db.execute(
                "SELECT COUNT(*) FROM pedidos_whatsapp "
                "WHERE estado IN ('nuevo','confirmado') AND leido=1"
            ).fetchone()[0]
            if n > 0:
                self._btn_pedidos.setTitle(f"📦 Pedidos ({n}) 🔴")
            else:
                self._btn_pedidos.setTitle("📦 Pedidos")
        except Exception:
            pass

    def _on_pago_confirmado(self, pago: dict) -> None:
        """Notifica pago confirmado."""
        try:
            # [spj-dedup] from PyQt5.QtWidgets import QMessageBox
            QMessageBox.information(
                self, "✅ Pago confirmado",
                f"Pago confirmado — Pedido #{pago.get('id','')}\n"
                f"Cliente: {pago.get('cliente_nombre','')}\n"
                f"Total: ${float(pago.get('total',0)):.2f}"
            )
        except Exception:
            pass

    def _abrir_panel_pedidos(self) -> None:
        """Navega al módulo de pedidos WA o muestra panel lateral."""
        self.manejar_navegacion("DELIVERY")

    def _mostrar_diagnostico(self):
        """Muestra el diálogo de diagnóstico del sistema"""
        try:
            from interfaz.diagnostico import mostrar_diagnostico
            mostrar_diagnostico(self)
        except Exception as e:
            logger.error(f"Error al mostrar diagnóstico: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"No se pudo abrir el diagnóstico del sistema:\n{str(e)}"
            )

    def _mostrar_acerca_de(self):
        """Muestra información sobre la aplicación"""
        from datetime import datetime
        mensaje = (
            "<h2>SPJ POS v13.4</h2>"
            "<p><b>Sistema de Punto de Venta Profesional</b></p>"
            "<hr>"
            f"<p><b>Versión:</b> 13.4.0</p>"
            f"<p><b>Fecha de compilación:</b> {datetime.now().strftime('%Y-%m-%d')}</p>"
            "<p><b>Desarrollado con:</b> Python + PyQt5</p>"
            "<hr>"
            "<p>© 2024-2025 SPJ Systems</p>"
        )
        QMessageBox.information(self, "Acerca de SPJ POS", mensaje)

    def manejar_navegacion(self, modulo: str):
        if modulo == "LOGOUT":
            self.usuario_actual = None
            # v13.4: Limpiar SessionContext
            try:
                self.container.clear_session()
            except Exception:
                pass
            # Resetear barra de sesión
            if hasattr(self, '_session_bar'):
                self._session_bar.setText("  Esperando inicio de sesión...")
                self._session_bar.setStyleSheet(
                    "background:#2C3E50; color:#ecf0f1; font-size:11px; padding:0 12px;")
            self.mostrar_login()
        elif modulo in self.indices_pantallas:
            # v13.4: Verificar permisos antes de navegar al módulo
            try:
                from core.permissions import verificar_acceso_modulo
                if not verificar_acceso_modulo(self.container, modulo, self):
                    return  # Permiso denegado — no navega
            except Exception:
                pass  # Si falla el check, permitir (compat)
            self.stack.setCurrentIndex(self.indices_pantallas[modulo])
        else:
            QMessageBox.information(
                self, "Módulo no disponible",
                f"El módulo '{modulo}' aún no está registrado en el sistema.")

    def aplicar_tema(self, nombre_tema: str) -> None:
        """Aplica el tema — API pública para configuracion.py."""
        self._aplicar_tema(nombre_tema)

    def _aplicar_tema(self, nombre_tema: str) -> None:
        """Aplica el tema seleccionado a toda la aplicación."""
        from PyQt5.QtWidgets import QApplication
        try:
            theme_svc = getattr(self.container, 'theme_service', None)
            if not theme_svc:
                from core.services.theme_service import ThemeService
                theme_svc = ThemeService(self.container.db)
            theme_svc.save_preferences(
                theme=nombre_tema, density="Normal",
                font_size="12", icon_size="24",
            )
            qss = theme_svc.generate_qss()
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(0, lambda: QApplication.instance().setStyleSheet(qss))
            # Sidebar siempre oscuro (regla de diseño) — run after stylesheet is applied
            if hasattr(self, "menu") and hasattr(self.menu, "enforce_dark_mode"):
                QTimer.singleShot(10, self.menu.enforce_dark_mode)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("_aplicar_tema: %s", e)

    def closeEvent(self, event):
        """v13.2: Clean up all threads before closing to prevent QThread warnings."""
        # Stop notification timer
        try:
            if hasattr(self, '_gestor_notif') and self._gestor_notif:
                self._gestor_notif.detener()
        except Exception:
            pass
        # Stop VersionChecker QThread
        try:
            if hasattr(self, '_version_checker') and self._version_checker:
                self._version_checker.quit()
                self._version_checker.wait(3000)
        except Exception:
            pass
        super().closeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        # v13.2: start notification manager AFTER event loop is running
        if not getattr(self, '_notif_started', False):
            self._notif_started = True
            try:
                self._iniciar_gestor_notificaciones()
            except Exception as _e:
                import logging
                logging.getLogger(__name__).debug("showEvent notif: %s", _e)
        if not self.usuario_actual:
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(0, self.mostrar_login)
            
    def _configurar_busqueda_global(self):
        """Configura el atajo de teclado para la búsqueda global (Ctrl+F)."""
        from PyQt5.QtWidgets import QShortcut
        from PyQt5.QtGui import QKeySequence
        try:
            sc = QShortcut(QKeySequence("Ctrl+F"), self)
            sc.activated.connect(self._abrir_busqueda_global)
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug("busqueda_global shortcut: %s", e)

    def _abrir_busqueda_global(self):
        """Búsqueda rápida de productos/clientes (Ctrl+F)."""
        from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLineEdit,
            QListWidget, QListWidgetItem, QLabel, QHBoxLayout)
        from PyQt5.QtCore import Qt, QTimer
        try:
            db = self.container.db
        except Exception:
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("🔍 Búsqueda rápida — Ctrl+F")
        dlg.setMinimumWidth(480)
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowStaysOnTopHint)
        lay = QVBoxLayout(dlg)

        txt = QLineEdit(); txt.setPlaceholderText("Buscar producto, cliente o folio de venta…")
        txt.setStyleSheet("font-size:14px;padding:8px;")
        lay.addWidget(txt)

        lst = QListWidget(); lst.setMaximumHeight(280)
        lay.addWidget(lst)

        lbl_hint = QLabel("↑↓ navegar   Enter: ir al módulo   Esc: cerrar")
        lbl_hint.setStyleSheet("color:#999;font-size:11px;")
        lay.addWidget(lbl_hint)

        def buscar(texto):
            lst.clear()
            if len(texto) < 2: return
            try:
                # Productos
                rows = db.execute(
                    "SELECT nombre, precio, existencia FROM productos "
                    "WHERE (nombre LIKE ? OR codigo LIKE ?) AND activo=1 LIMIT 8",
                    (f"%{texto}%", f"%{texto}%")
                ).fetchall()
                for r in rows:
                    it = QListWidgetItem(f"📦 {r[0]}  —  ${float(r[1]):.2f}  |  stock: {float(r[2]):.1f}")
                    it.setData(Qt.UserRole, ("PRODUCTOS", None))
                    lst.addItem(it)
                # Clientes
                rows2 = db.execute(
                    "SELECT nombre, COALESCE(apellido,''), COALESCE(telefono,'') "
                    "FROM clientes WHERE nombre LIKE ? LIMIT 5",
                    (f"%{texto}%",)
                ).fetchall()
                for r in rows2:
                    it = QListWidgetItem(f"👤 {r[0]} {r[1]}  —  {r[2]}")
                    it.setData(Qt.UserRole, ("CLIENTES", None))
                    lst.addItem(it)
                # Ventas por folio
                rows3 = db.execute(
                    "SELECT folio, total, fecha FROM ventas "
                    "WHERE folio LIKE ? ORDER BY fecha DESC LIMIT 4",
                    (f"%{texto}%",)
                ).fetchall()
                for r in rows3:
                    it = QListWidgetItem(f"🧾 Folio {r[0]}  —  ${float(r[1]):.2f}")
                    it.setData(Qt.UserRole, ("POS", None))
                    lst.addItem(it)
            except Exception as e:
                import logging
                logging.getLogger(__name__).debug("busqueda_global: %s", e)

        _timer = QTimer(); _timer.setSingleShot(True)
        _timer.timeout.connect(lambda: buscar(txt.text()))
        txt.textChanged.connect(lambda t: _timer.start(250))

        def on_enter(item=None):
            it = item or lst.currentItem()
            if it:
                modulo, _ = it.data(Qt.UserRole)
                dlg.accept()
                self.manejar_navegacion(modulo)

        lst.itemDoubleClicked.connect(on_enter)
        txt.returnPressed.connect(lambda: on_enter(lst.currentItem() if lst.count() else None))

        dlg.exec_()

    def _cargar_logo_empresa(self) -> None:
        """Carga el logo de la empresa desde BD y lo aplica en sidebar y titlebar."""
        try:
            row = self.container.db.execute(
                "SELECT valor FROM configuraciones WHERE clave='logo_path'"
            ).fetchone()
            logo_path = row[0] if row and row[0] else ""
            nombre_row = self.container.db.execute(
                "SELECT valor FROM configuraciones WHERE clave='nombre_empresa'"
            ).fetchone()
            nombre = nombre_row[0] if nombre_row and nombre_row[0] else "SPJ POS"
            if hasattr(self, 'menu') and hasattr(self.menu, 'actualizar_logo'):
                self.menu.actualizar_logo(logo_path, nombre)
            self.setWindowTitle(f"{nombre} — ERP SPJ POS v13.4")
            if logo_path:
                try:
                    from PyQt5.QtGui import QIcon
                    self.setWindowIcon(QIcon(logo_path))
                except Exception:
                    pass
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug("_cargar_logo_empresa: %s", e)

    def _cargar_tema_inicial(self):
        """v13.4: Carga dark/light mode desde BD y sincroniza toggle."""
        try:
            from modulos.spj_styles import apply_global_theme
            apply_global_theme(self.container.db)
            # Sync menu toggle
            row = self.container.db.execute(
                "SELECT valor FROM configuraciones WHERE clave='tema'"
            ).fetchone()
            is_dark = row and row[0] and 'dark' in str(row[0]).lower()
            if hasattr(self, '_action_dark'):
                self._action_dark.setChecked(is_dark)
            if hasattr(self, "menu") and hasattr(self.menu, "enforce_dark_mode"):
                self.menu.enforce_dark_mode()
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug("_cargar_tema_inicial: %s", e)

try:
    from modulos.rrhh_turnos import ModuloRRHHTurnos
except Exception:
    ModuloRRHHTurnos = None
try:
    from modulos.modulo_growth_engine import ModuloGrowthEngine
except Exception:
    ModuloGrowthEngine = None
 
