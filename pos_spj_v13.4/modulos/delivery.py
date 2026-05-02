
# modulos/delivery.py — SPJ POS v7  DELIVERY UI COMPLETO
from __future__ import annotations
import logging
from modulos.spj_phone_widget import PhoneWidget
from modulos.spj_styles import spj_btn, apply_btn_styles
from modulos.design_tokens import Colors, Spacing, Typography, Borders
from modulos.ui_components import (
    create_primary_button, create_success_button, create_danger_button,
    create_secondary_button, create_warning_button, create_input, create_combo,
    create_card, apply_tooltip, LoadingIndicator, EmptyStateWidget,
    PageHeader, Toast,
)
from modulos.spj_refresh_mixin import RefreshMixin
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QComboBox, QLineEdit, QGroupBox, QFormLayout,
    QMessageBox, QHeaderView, QSplitter, QTextEdit, QDialog, QDialogButtonBox,
    QSpinBox, QDoubleSpinBox, QFrame, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QColor
from core.db.connection import get_connection
from core.services.delivery_service import DeliveryService
logger = logging.getLogger("spj.delivery")

ESTADOS = ["pendiente","preparacion","en_ruta","entregado","cancelado"]
ESTADO_COLOR = {
    "pendiente": Colors.WARNING_BASE,"preparacion":Colors.PRIMARY_BASE,"en_ruta":Colors.ACCENT_BASE,
    "entregado":Colors.SUCCESS_BASE,"cancelado":Colors.DANGER_BASE
}

class AsignarDriverDialog(QDialog):
    def __init__(self, pedido_id, parent=None):
        super().__init__(parent)
        self.pedido_id = pedido_id
        self.setWindowTitle(f"Asignar Repartidor — Pedido #{pedido_id}")
        self.setMinimumWidth(400)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.combo_driver = QComboBox()
        self._cargar_drivers()
        form.addRow("Repartidor:", self.combo_driver)
        self.spin_tiempo = QSpinBox()
        self.spin_tiempo.setRange(5, 120); self.spin_tiempo.setValue(30)
        self.spin_tiempo.setSuffix(" min")
        form.addRow("Tiempo estimado:", self.spin_tiempo)
        self.txt_notas = QTextEdit(); self.txt_notas.setMaximumHeight(80)
        self.txt_notas.setPlaceholderText("Instrucciones al repartidor...")
        form.addRow("Notas:", self.txt_notas)
        layout.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _cargar_drivers(self):
        try:
            conn = get_connection()
            rows = conn.execute("SELECT id, nombre FROM drivers WHERE activo=1 ORDER BY nombre").fetchall()
            for r in rows:
                self.combo_driver.addItem(r[1], r[0])
            if self.combo_driver.count() == 0:
                self.combo_driver.addItem("Sin repartidores registrados", None)
        except Exception as e:
            self.combo_driver.addItem(f"Error: {e}", None)

    def get_data(self):
        return {
            "driver_id": self.combo_driver.currentData(),
            "tiempo": self.spin_tiempo.value(),
            "notas": self.txt_notas.toPlainText()
        }

class NuevoPedidoDialog(QDialog):
    def __init__(self, delivery_service: DeliveryService, parent=None):
        super().__init__(parent)
        self.delivery_service = delivery_service
        self._selected_coords = None
        self.setWindowTitle("Nuevo Pedido Delivery")
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.txt_cliente = QLineEdit(); self.txt_cliente.setPlaceholderText("Buscar cliente...")
        self.txt_direccion = QLineEdit(); self.txt_direccion.setPlaceholderText("Escribe dirección (mín. 4 caracteres)")
        self.lst_sugerencias = QListWidget()
        self.lst_sugerencias.setMaximumHeight(130)
        self.lst_sugerencias.hide()
        self.txt_notas = QLineEdit(); self.txt_notas.setPlaceholderText("Notas del pedido")
        self.combo_sucursal = QComboBox()
        self.combo_sucursal.addItems(["Sucursal Principal","Sucursal 2","Sucursal 3"])
        form.addRow("Cliente:", self.txt_cliente)
        form.addRow("Dirección:", self.txt_direccion)
        form.addRow("Sugerencias:", self.lst_sugerencias)
        form.addRow("Notas:", self.txt_notas)
        form.addRow("Sucursal:", self.combo_sucursal)
        layout.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        layout.addWidget(btns)
        self.txt_direccion.textChanged.connect(self._buscar_sugerencias)
        self.lst_sugerencias.itemClicked.connect(self._tomar_sugerencia)

    def _buscar_sugerencias(self, text: str):
        self.lst_sugerencias.clear()
        self._selected_coords = None
        if len(text.strip()) < 4:
            self.lst_sugerencias.hide()
            return
        for item in self.delivery_service.autocomplete_address(text):
            w = QListWidgetItem(item.get("label", ""))
            w.setData(Qt.UserRole, item)
            self.lst_sugerencias.addItem(w)
        self.lst_sugerencias.setVisible(self.lst_sugerencias.count() > 0)

    def _tomar_sugerencia(self, item: QListWidgetItem):
        data = item.data(Qt.UserRole) or {}
        self.txt_direccion.setText(data.get("label", ""))
        self._selected_coords = data
        self.lst_sugerencias.hide()

    def get_data(self):
        return {
            "cliente": self.txt_cliente.text().strip(),
            "direccion": self.txt_direccion.text().strip(),
            "coords": self._selected_coords,
            "notas": self.txt_notas.text().strip(),
            "sucursal_id": self.combo_sucursal.currentIndex() + 1
        }

class TarjetaPedido(QFrame):
    accion_requerida = pyqtSignal(int, str)  # pedido_id, accion
    def __init__(self, pedido: dict, parent=None):
        super().__init__(parent)
        self.pedido = pedido
        self.setFrameShape(QFrame.StyledPanel)
        color = ESTADO_COLOR.get(pedido.get("estado","pendiente"), Colors.TEXT_SECONDARY)
        self.setObjectName("cardPedido")
        # Estilo dinámico solo para borde de estado y fondo
        self.setStyleSheet(f"""
            QFrame#cardPedido {{
                border-left: 4px solid {color};
                border-radius: {Borders.RADIUS_MD};
                background: {Colors.CARD_DARK if hasattr(Colors, 'CARD_DARK') else Colors.NEUTRAL_800};
                padding: {Spacing.SM};
                margin: {Spacing.XS};
            }}
        """)
        layout = QHBoxLayout(self)
        info = QVBoxLayout()
        
        titulo = QLabel(f"<b>#{pedido.get('id','')}  {pedido.get('direccion','Sin dirección')[:40]}</b>")
        titulo.setObjectName("subheading")
        
        cliente = QLabel(f"Cliente: {pedido.get('cliente_nombre','N/A')}  |  Tel: {pedido.get('cliente_tel','')}")
        cliente.setObjectName("caption")
        
        driver_txt = f"Repartidor: {pedido.get('driver_nombre','Sin asignar')}"
        driver_lbl = QLabel(driver_txt)
        driver_lbl.setObjectName("textMuted")
        
        estado_lbl = QLabel(pedido.get("estado","").upper())
        estado_lbl.setObjectName("badge")
        estado_lbl.setStyleSheet(f"color: {color}; font-weight: bold;")
        
        info.addWidget(titulo)
        info.addWidget(cliente)
        info.addWidget(driver_lbl)
        info.addWidget(estado_lbl)
        layout.addLayout(info, 1)
        btns = QVBoxLayout()
        estado = pedido.get("estado","pendiente")
        if estado == "pendiente":
            btn = create_primary_button(self, "Asignar", "Asignar repartidor al pedido")
            btn.setFixedWidth(90)
            btn.clicked.connect(lambda _, pid=self.pedido["id"]: self.accion_requerida.emit(pid,"asignar"))
            btns.addWidget(btn)
        if estado == "preparacion":
            btn = create_primary_button(self, "En Ruta", "Marcar pedido como en ruta")
            btn.setFixedWidth(90)
            btn.clicked.connect(lambda _, pid=self.pedido["id"]: self.accion_requerida.emit(pid,"en_ruta"))
            btns.addWidget(btn)
        if estado == "en_ruta":
            btn = create_success_button(self, "Entregado", "Confirmar entrega del pedido")
            btn.setFixedWidth(90)
            btn.clicked.connect(lambda _, pid=self.pedido["id"]: self.accion_requerida.emit(pid,"entregado"))
            btns.addWidget(btn)
        if estado not in ("entregado","cancelado"):
            btn_cancel = create_danger_button(self, "Cancelar", "Cancelar pedido de delivery")
            btn_cancel.setFixedWidth(90)
            btn_cancel.clicked.connect(lambda _, pid=self.pedido["id"]: self.accion_requerida.emit(pid,"cancelado"))
            btns.addWidget(btn_cancel)
        layout.addLayout(btns)

class ModuloDelivery(QWidget, RefreshMixin):
    def __init__(self, conexion_o_container, usuario="admin", parent=None):
        super().__init__(parent)
        # Accept either AppContainer or direct db connection
        if hasattr(conexion_o_container, 'db'):
            self.container = conexion_o_container
            self.conexion  = conexion_o_container.db
        else:
            self.container = None
            self.conexion  = conexion_o_container
        self.usuario = usuario
        self.delivery_service = DeliveryService(self.conexion)
        self._pedidos_cache = []
        self._init_ui()
        self._init_tables()
        # EventBus: recarga reactiva al completar/modificar pedido
        # Timer de 5 min solo como fallback (antes era 30s polling constante)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.cargar_pedidos)
        self.refresh_timer.start(300000)   # 5 min fallback (era 30s)

        try:
            from core.events.event_bus import get_bus
            _bus = get_bus()
            for event in ("PEDIDO_NUEVO", "PEDIDO_ACTUALIZADO",
                          "VENTA_COMPLETADA", "DELIVERY_UPDATE"):
                try:
                    _bus.subscribe(
                        event,
                        lambda _p, _s=self: (
                            _s.cargar_pedidos()
                            if _s.isVisible() else None
                        ),
                        label=f"delivery.refresh.{event}",
                        priority=-1
                    )
                except Exception:
                    pass
        except Exception:
            pass  # EventBus no disponible — fallback al timer

        self.cargar_pedidos()


    # ── Interfaz de sesión — compatible con SessionManager ────────────────
    def set_sesion(self, usuario: str, rol: str) -> None:
        self.usuario = usuario
        if hasattr(self, "_on_sesion_change"):
            try: self._on_sesion_change(usuario, rol)
            except Exception: pass

    def set_usuario_actual(self, usuario: str, rol: str) -> None:
        self.set_sesion(usuario, rol)

    def set_sucursal(self, sucursal_id: int, sucursal_nombre: str = "") -> None:
        if hasattr(self, "sucursal_id"):
            self.sucursal_id = sucursal_id
        if hasattr(self, "sucursal_nombre"):
            self.sucursal_nombre = sucursal_nombre

    def cerrar_sesion(self) -> None:
        self.usuario = ""


    def _init_ui(self):
        layout = QVBoxLayout(self)
        # Header
        header = QHBoxLayout()
        title = QLabel("🚚 Módulo Delivery"); title.setObjectName("heading")
        btn_nuevo = create_success_button(self, "+ Nuevo Pedido", "Crear nuevo pedido de delivery")
        btn_nuevo.clicked.connect(self.nuevo_pedido)
        btn_driver = create_secondary_button(self, "Gestionar Repartidores", "Administrar repartidores disponibles")
        btn_driver.clicked.connect(self.gestionar_drivers)
        # v13.30: Corte de caja por repartidor
        btn_corte = create_warning_button(self, "💰 Corte Repartidor", "Corte de caja: cuánto efectivo debe entregar cada repartidor")
        btn_hist = create_secondary_button(self, "📋 Historial", "Historial de cortes y entregas")
        btn_hist.clicked.connect(self._historial_cortes)

        self.btn_auto_assign = create_primary_button(self, "🤖 Auto-Asignar", "Asigna automáticamente todos los pedidos pendientes al repartidor disponible más cercano")
        self.btn_auto_assign.clicked.connect(self._auto_asignar_todos)
        # Configurable: se deshabilita si feature_flag 'delivery_auto_asign' está off
        try:
            habilitado = self.container.feature_flag_service.is_enabled('delivery_auto_asign', 1) if hasattr(self.container, 'feature_flag_service') else True
            self.btn_auto_assign.setVisible(habilitado)
        except Exception:
            pass
        btn_refresh = create_secondary_button(self, "🔄 Actualizar", "Recargar lista de pedidos")
        btn_refresh.clicked.connect(self.cargar_pedidos)
        header.addWidget(title); header.addStretch()
        header.addWidget(btn_nuevo); header.addWidget(btn_driver)
        header.addWidget(btn_corte); header.addWidget(btn_hist)
        header.addWidget(self.btn_auto_assign); header.addWidget(btn_refresh)
        layout.addLayout(header)
        # Filtro de estado
        filtro_layout = QHBoxLayout()
        filtro_layout.addWidget(QLabel("Filtrar:"))
        self.combo_filtro = create_combo(self, ["Todos","pendiente","preparacion","en_ruta","entregado","cancelado"], "Seleccionar estado para filtrar")
        self.combo_filtro.currentTextChanged.connect(self.cargar_pedidos)
        filtro_layout.addWidget(self.combo_filtro); filtro_layout.addStretch()
        # Stats
        self.lbl_stats = QLabel()
        self.lbl_stats.setObjectName("caption")
        filtro_layout.addWidget(self.lbl_stats)
        layout.addLayout(filtro_layout)
        self._loading = LoadingIndicator("Cargando pedidos delivery…", self)
        self._loading.hide()
        layout.addWidget(self._loading)
        self._empty = EmptyStateWidget(
            "Sin pedidos",
            "No hay pedidos de delivery para el filtro seleccionado.",
            "🛵",
            self,
        )
        self._empty.hide()
        layout.addWidget(self._empty)

        # ── Toggle Lista / Kanban ─────────────────────────────────────────
        self._vista_actual = "lista"
        toggle_bar = QHBoxLayout()
        toggle_bar.setSpacing(0)

        self._btn_vista_lista = QPushButton("≡  Lista")
        self._btn_vista_lista.setFixedHeight(28)
        self._btn_vista_lista.setCheckable(True)
        self._btn_vista_lista.setChecked(True)
        self._btn_vista_lista.setStyleSheet(self._qss_toggle_activo())
        self._btn_vista_lista.clicked.connect(lambda: self._toggle_vista("lista"))

        self._btn_vista_kanban = QPushButton("⊞  Kanban")
        self._btn_vista_kanban.setFixedHeight(28)
        self._btn_vista_kanban.setCheckable(True)
        self._btn_vista_kanban.setChecked(False)
        self._btn_vista_kanban.setStyleSheet(self._qss_toggle_inactivo())
        self._btn_vista_kanban.clicked.connect(lambda: self._toggle_vista("kanban"))

        toggle_bar.addWidget(self._btn_vista_lista)
        toggle_bar.addWidget(self._btn_vista_kanban)
        toggle_bar.addStretch()
        layout.addLayout(toggle_bar)

        # ── Stacked: index 0 = Lista, index 1 = Kanban ────────────────────
        from PyQt5.QtWidgets import QStackedWidget as _SW
        self._stack = _SW()

        # — Lista —
        self._stack.addWidget(self._build_lista_view())

        # — Kanban —
        kanban_widget = QWidget()
        kanban_layout = QVBoxLayout(kanban_widget)
        kanban_layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Horizontal)
        self.columnas = {}
        for estado in ["pendiente","preparacion","en_ruta","entregado"]:
            col_widget = QWidget()
            col_layout = QVBoxLayout(col_widget)
            color = ESTADO_COLOR[estado]
            titulo = QLabel(estado.upper().replace("_"," "))
            titulo.setObjectName("subheading")
            titulo.setStyleSheet(
                f"color: {color}; font-weight: bold; padding: {Spacing.SM};"
                f" border-bottom: 2px solid {color};")
            col_layout.addWidget(titulo)
            scroll_content = QWidget()
            self.columnas[estado] = QVBoxLayout(scroll_content)
            self.columnas[estado].addStretch()
            col_layout.addWidget(scroll_content)
            col_layout.addStretch()
            splitter.addWidget(col_widget)
        kanban_layout.addWidget(splitter)
        self._stack.addWidget(kanban_widget)

        layout.addWidget(self._stack, 1)

        # ── Botón de mapa de repartidores ─────────────────────────────────
        btn_mapa = create_success_button(self, "🗺️ Ver Mapa de Repartidores", "Ver ubicación de repartidores en tiempo real")
        btn_mapa.setObjectName("btnMapa")
        btn_mapa.setStyleSheet(f"margin-top: {Spacing.SM};")
        btn_mapa.clicked.connect(self._abrir_mapa)
        layout.addWidget(btn_mapa)

    def _abrir_mapa(self):
        """Abre el mapa Leaflet de repartidores en una ventana flotante."""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout
        dlg = QDialog(self)
        dlg.setWindowTitle("🗺️ Mapa de Repartidores en Tiempo Real")
        dlg.resize(820, 560)
        lay = QVBoxLayout(dlg)

        try:
            from PyQt5.QtWebEngineWidgets import QWebEngineView
            view = QWebEngineView()
            # Build drivers data + pedidos geolocalizados
            try:
                rows = self.conexion.execute(
                    "SELECT c.nombre, dl.lat, dl.lng, dl.actualizado "
                    "FROM driver_locations dl "
                    "JOIN empleados c ON c.id = dl.chofer_id "
                    "ORDER BY dl.actualizado DESC"
                ).fetchall()
                drivers_js = str([{"name": r[0], "lat": float(r[1] or 20.967),
                                   "lng": float(r[2] or -89.623)} for r in rows])
            except Exception:
                drivers_js = "[]"
            pedidos_js = str([
                {
                    "id": p.get("id"),
                    "cliente": p.get("cliente_nombre", ""),
                    "direccion": p.get("direccion", ""),
                    "estado": p.get("estado", "pendiente"),
                    "lat": float(p.get("lat") or 20.967),
                    "lng": float(p.get("lng") or -89.623),
                }
                for p in (self._pedidos_cache or [])
                if p.get("lat") is not None and p.get("lng") is not None
            ])

            html = f"""<!DOCTYPE html><html><head>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>body{{margin:0}}#map{{height:100vh}}</style>
</head><body><div id="map"></div><script>
var map = L.map('map').setView([20.967, -89.623], 13);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',
    {{attribution:'© OpenStreetMap'}}).addTo(map);
var drivers = {drivers_js};
var pedidos = {pedidos_js};
var icon = L.icon({{iconUrl:'https://cdn-icons-png.flaticon.com/32/3050/3050553.png',iconSize:[32,32]}});
drivers.forEach(function(d){{
    L.marker([d.lat,d.lng],{{icon:icon}}).addTo(map)
     .bindPopup('<b>' + d.name + '</b>').openPopup();
}});
pedidos.forEach(function(p){{
    L.circleMarker([p.lat,p.lng],{{radius:8,color:'#ef4444'}}).addTo(map)
      .bindPopup('Pedido #' + p.id + '<br/>' + p.estado + '<br/>' + p.cliente + '<br/>' + p.direccion);
}});
if(drivers.length===0){{
    L.marker([20.967,-89.623]).addTo(map)
     .bindPopup('Sin repartidores activos').openPopup();
}}
</script></body></html>"""
            view.setHtml(html)
            lay.addWidget(view)
        except ImportError:
            from PyQt5.QtWidgets import QLabel
            lbl = QLabel(
                "⚠️ PyQtWebEngine no instalado.\n\n"
                "Para ver el mapa instala:\n  pip install PyQtWebEngine")
            lbl.setObjectName("caption")
            lay.addWidget(lbl)

        dlg.exec_()

    # ═══════════════════════════════════════════════════════════════════════
    # TOGGLE LISTA / KANBAN
    # ═══════════════════════════════════════════════════════════════════════
    @staticmethod
    def _qss_toggle_activo() -> str:
        return (f"background:{Colors.PRIMARY_BASE}; color:white; border:1px solid {Colors.PRIMARY_BASE};"
                f" border-radius:5px; padding:3px 14px; font-weight:600; font-size:12px;")

    @staticmethod
    def _qss_toggle_inactivo() -> str:
        return (f"background:transparent; color:{Colors.NEUTRAL.SLATE_400};"
                f" border:1px solid {Colors.NEUTRAL.SLATE_700};"
                f" border-radius:5px; padding:3px 14px; font-size:12px;")

    def _toggle_vista(self, vista: str) -> None:
        self._vista_actual = vista
        self._stack.setCurrentIndex(0 if vista == "lista" else 1)
        self._btn_vista_lista.setChecked(vista == "lista")
        self._btn_vista_kanban.setChecked(vista == "kanban")
        self._btn_vista_lista.setStyleSheet(
            self._qss_toggle_activo() if vista == "lista" else self._qss_toggle_inactivo())
        self._btn_vista_kanban.setStyleSheet(
            self._qss_toggle_activo() if vista == "kanban" else self._qss_toggle_inactivo())

    # ═══════════════════════════════════════════════════════════════════════
    # VISTA LISTA + PANEL DETALLE
    # ═══════════════════════════════════════════════════════════════════════
    def _build_lista_view(self) -> QWidget:
        """Construye la vista Lista: panel izquierdo (lista) + panel derecho (detalle)."""
        widget = QWidget()
        splitter = QSplitter(Qt.Horizontal, widget)
        outer = QHBoxLayout(widget)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(splitter)

        # ── Panel izquierdo — lista de pedidos ───────────────────────────
        left = QWidget()
        left.setMinimumWidth(240)
        left.setMaximumWidth(280)
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(0)

        self._lst_pedidos = QListWidget()
        self._lst_pedidos.setObjectName("listaPedidos")
        self._lst_pedidos.setStyleSheet(f"""
            QListWidget {{ border:none; background:{Colors.NEUTRAL.DARK_BG}; }}
            QListWidget::item {{ border-bottom:1px solid {Colors.NEUTRAL.DARK_BORDER};
                                 padding:0; }}
            QListWidget::item:selected {{ background:{Colors.NEUTRAL.DARK_CARD}; }}
            QListWidget::item:hover {{ background:{Colors.NEUTRAL.DARK_CARD}; }}
        """)
        self._lst_pedidos.currentRowChanged.connect(self._on_lista_seleccion)
        left_lay.addWidget(self._lst_pedidos)
        splitter.addWidget(left)

        # ── Panel derecho — detalle ──────────────────────────────────────
        self._detalle_widget = QWidget()
        self._detalle_widget.setStyleSheet(
            f"background:{Colors.NEUTRAL.DARK_BG};")
        detalle_lay = QVBoxLayout(self._detalle_widget)
        detalle_lay.setContentsMargins(16, 12, 16, 12)
        detalle_lay.setSpacing(10)

        # — Cabecera del pedido —
        self._det_header = QLabel("Selecciona un pedido")
        self._det_header.setObjectName("heading")
        self._det_header.setWordWrap(True)
        detalle_lay.addWidget(self._det_header)

        self._det_sub = QLabel("")
        self._det_sub.setObjectName("caption")
        self._det_sub.setWordWrap(True)
        detalle_lay.addWidget(self._det_sub)

        # — Productos —
        grp_items = QGroupBox("Productos del pedido")
        grp_items_lay = QVBoxLayout(grp_items)
        self._det_tabla = QTableWidget(0, 4)
        self._det_tabla.setHorizontalHeaderLabels(["Producto","Cant.","Precio","Total"])
        self._det_tabla.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._det_tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        self._det_tabla.setMaximumHeight(140)
        self._det_tabla.verticalHeader().setVisible(False)
        grp_items_lay.addWidget(self._det_tabla)
        detalle_lay.addWidget(grp_items)

        # — Notas —
        self._det_notas = QLabel("")
        self._det_notas.setObjectName("textMuted")
        self._det_notas.setWordWrap(True)
        detalle_lay.addWidget(self._det_notas)

        # — Total / anticipo —
        self._det_total = QLabel("")
        self._det_total.setObjectName("subheading")
        detalle_lay.addWidget(self._det_total)

        # — Acciones contextuales —
        self._det_acciones_layout = QHBoxLayout()
        self._det_acciones_layout.setSpacing(8)
        detalle_lay.addLayout(self._det_acciones_layout)

        detalle_lay.addStretch()
        splitter.addWidget(self._detalle_widget)
        splitter.setSizes([260, 700])
        return widget

    def _on_lista_seleccion(self, row: int) -> None:
        """Popula el panel de detalle cuando el usuario selecciona una fila."""
        if row < 0 or row >= len(self._pedidos_cache):
            return
        self._seleccionar_pedido(self._pedidos_cache[row])

    def _seleccionar_pedido(self, pedido: dict) -> None:
        """Rellena el panel de detalle con los datos del pedido seleccionado."""
        pid    = pedido.get("id", "")
        estado = pedido.get("estado", "pendiente")
        color  = ESTADO_COLOR.get(estado, Colors.TEXT_SECONDARY)

        self._det_header.setText(
            f"<span style='color:{color};font-weight:bold;'>#{pid}</span>"
            f"  —  {pedido.get('cliente_nombre','N/A')}"
        )
        self._det_sub.setText(
            f"📍 {pedido.get('direccion','Sin dirección')}  ·  "
            f"📞 {pedido.get('cliente_tel','')}  ·  "
            f"🛵 {pedido.get('driver_nombre','Sin repartidor')}"
        )

        # Cargar ítems desde BD
        self._det_tabla.setRowCount(0)
        try:
            rows = self.conexion.execute(
                "SELECT producto_nombre, cantidad, precio_unitario, subtotal "
                "FROM venta_items vi "
                "JOIN ventas v ON vi.venta_id = v.id "
                "JOIN delivery_orders d ON d.venta_id = v.id "
                "WHERE d.id = ? LIMIT 20",
                (pid,)
            ).fetchall()
            for i, r in enumerate(rows):
                self._det_tabla.insertRow(i)
                for j, val in enumerate(r):
                    item = QTableWidgetItem(
                        f"${val:.2f}" if j in (2,3) else
                        f"{val:.3f}" if j == 1 else str(val)
                    )
                    if j == 3:
                        item.setForeground(QColor(Colors.SUCCESS_BASE))
                    self._det_tabla.setItem(i, j, item)
        except Exception:
            pass  # Tabla no relacionada — pedido WA sin venta

        notas = pedido.get("notas", "") or ""
        self._det_notas.setText(f"📝 {notas}" if notas else "Sin notas")

        total = float(pedido.get("total") or 0)
        costo = float(pedido.get("costo_envio") or 0)
        self._det_total.setText(
            f"Total: <b>${total:.2f}</b>  ·  Envío: ${costo:.2f}"
            f"  ·  <span style='color:{color};'>{estado.upper()}</span>"
        )

        # Acciones contextuales
        # Limpiar acciones anteriores
        while self._det_acciones_layout.count():
            item = self._det_acciones_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        def _add_btn(label, fn, color_fn):
            b = color_fn(self, label, "")
            b.setFixedHeight(32)
            b.clicked.connect(lambda _, pid=pid, a=label: fn(pid, a))
            self._det_acciones_layout.addWidget(b)

        if estado == "pendiente":
            b = create_primary_button(self, "Asignar repartidor", "")
            b.setFixedHeight(32)
            b.clicked.connect(lambda _, p=pid: self.ejecutar_accion(p, "asignar"))
            self._det_acciones_layout.addWidget(b)

        if estado == "preparacion":
            b = create_primary_button(self, "→ En ruta", "")
            b.setFixedHeight(32)
            b.clicked.connect(lambda _, p=pid: self.ejecutar_accion(p, "en_ruta"))
            self._det_acciones_layout.addWidget(b)

        if estado == "en_ruta":
            b = create_success_button(self, "✓ Entregado", "")
            b.setFixedHeight(32)
            b.clicked.connect(lambda _, p=pid: self.ejecutar_accion(p, "entregado"))
            self._det_acciones_layout.addWidget(b)

        if estado not in ("entregado", "cancelado"):
            b = create_danger_button(self, "✕ Cancelar", "")
            b.setFixedHeight(32)
            b.clicked.connect(lambda _, p=pid: self.ejecutar_accion(p, "cancelado"))
            self._det_acciones_layout.addWidget(b)

        self._det_acciones_layout.addStretch()

    def _actualizar_lista_view(self, pedidos: list) -> None:
        """Repopula la QListWidget de la vista lista con los pedidos actuales."""
        self._lst_pedidos.clear()
        for pedido in pedidos:
            estado = pedido.get("estado", "pendiente")
            color  = ESTADO_COLOR.get(estado, Colors.TEXT_SECONDARY)
            pid    = pedido.get("id", "")
            nombre = pedido.get("cliente_nombre", "N/A")
            total  = float(pedido.get("total") or 0)
            notas  = (pedido.get("notas") or "")[:30]

            item = QListWidgetItem()
            item.setData(Qt.UserRole, pedido)
            item.setSizeHint(__import__('PyQt5.QtCore', fromlist=['QSize']).QSize(240, 68))

            # Widget tarjeta compacta
            card = QFrame()
            card.setStyleSheet(
                f"QFrame {{ border-left:3px solid {color};"
                f" background:transparent; padding:6px 10px; }}"
            )
            card_lay = QVBoxLayout(card)
            card_lay.setContentsMargins(8, 4, 8, 4)
            card_lay.setSpacing(2)

            row1 = QHBoxLayout()
            lbl_id = QLabel(f"<b>#{pid}</b>")
            lbl_id.setStyleSheet(f"color:{color}; font-size:11px;")
            lbl_total = QLabel(f"${total:.0f}")
            lbl_total.setStyleSheet(f"color:{Colors.SUCCESS_BASE}; font-weight:bold; font-size:12px;")
            row1.addWidget(lbl_id)
            row1.addStretch()
            row1.addWidget(lbl_total)

            lbl_nombre = QLabel(nombre)
            lbl_nombre.setStyleSheet("font-weight:600; font-size:12px;")

            row3 = QHBoxLayout()
            lbl_notas = QLabel(notas or "Sin notas")
            lbl_notas.setStyleSheet(f"color:{Colors.NEUTRAL.SLATE_500}; font-size:10px;")
            badge = QLabel(estado.upper())
            badge.setStyleSheet(
                f"color:{color}; font-size:9px; font-weight:700;"
                f" border:1px solid {color}; border-radius:4px; padding:1px 5px;")
            row3.addWidget(lbl_notas)
            row3.addStretch()
            row3.addWidget(badge)

            card_lay.addLayout(row1)
            card_lay.addWidget(lbl_nombre)
            card_lay.addLayout(row3)

            self._lst_pedidos.addItem(item)
            self._lst_pedidos.setItemWidget(item, card)

    def _auto_asignar_todos(self):
        """Asigna automáticamente todos los pedidos pendientes sin repartidor."""
        try:
            from delivery.asignacion_repartidor import AsignacionRepartidor
            asign = AsignacionRepartidor(self.conexion)
            pendientes = self.conexion.execute(
                "SELECT id FROM delivery_orders WHERE estado='pendiente' AND driver_id IS NULL "
                "AND sucursal_id=? ORDER BY fecha_solicitud",
                (self.sucursal_id,)
            ).fetchall()
            if not pendientes:
                Toast.info(self, "Auto-Asignación", "No hay pedidos pendientes sin repartidor.")
                return
            asignados = 0
            for row in pendientes:
                rep_id = asign.asignar_automatico(row[0])
                if rep_id:
                    asignados += 1
            Toast.success(
                self, "✅ Auto-Asignación",
                f"{asignados}/{len(pendientes)} pedidos asignados.",
            )
            self.cargar_pedidos()
        except Exception as e:
            # [spj-dedup] from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Error", str(e))

    def _init_tables(self):
        tables = [
            """CREATE TABLE IF NOT EXISTS drivers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                telefono TEXT,
                vehiculo TEXT,
                activo INTEGER DEFAULT 1,
                en_ruta INTEGER DEFAULT 0,
                sucursal_id INTEGER DEFAULT 1,
                usuario_id INTEGER
            )""",
            """CREATE TABLE IF NOT EXISTS delivery_orders (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid             TEXT UNIQUE DEFAULT (lower(hex(randomblob(16)))),
                venta_id         INTEGER,
                driver_id        INTEGER,
                cliente_id       INTEGER,
                cliente_nombre   TEXT,
                cliente_tel      TEXT,
                direccion        TEXT,
                estado           TEXT DEFAULT 'pendiente',
                notas            TEXT,
                tiempo_estimado  INTEGER DEFAULT 30,
                total            REAL DEFAULT 0,
                costo_envio      REAL DEFAULT 0,
                pago_metodo      TEXT DEFAULT '',
                pago_monto       REAL DEFAULT 0,
                fecha_solicitud  DATETIME DEFAULT (datetime('now')),
                fecha_asignacion DATETIME,
                fecha_entrega    DATETIME,
                sucursal_id      INTEGER DEFAULT 1
            )""",
            """CREATE TABLE IF NOT EXISTS driver_locations (
                chofer_id INTEGER PRIMARY KEY,
                lat REAL, lng REAL,
                timestamp DATETIME
            )""",
            # v13.30: Tabla de cortes de caja por repartidor
            """CREATE TABLE IF NOT EXISTS delivery_driver_cuts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                driver_id        INTEGER NOT NULL,
                driver_nombre    TEXT,
                turno_inicio     DATETIME,
                turno_fin        DATETIME DEFAULT (datetime('now')),
                entregas_total   INTEGER DEFAULT 0,
                efectivo_cobrado REAL DEFAULT 0,
                tarjeta_cobrado  REAL DEFAULT 0,
                transfer_cobrado REAL DEFAULT 0,
                total_cobrado    REAL DEFAULT 0,
                efectivo_entregado REAL DEFAULT 0,
                diferencia       REAL DEFAULT 0,
                usuario_corte    TEXT,
                sucursal_id      INTEGER DEFAULT 1,
                notas            TEXT,
                fecha            DATETIME DEFAULT (datetime('now'))
            )""",
        ]
        for sql in tables:
            try:
                self.conexion.execute(sql)
            except Exception as _e:
                logger.debug("_init_tables: %s", _e)
        # Ensure missing columns on existing tables (ALTER ADD is safe with IF NOT EXISTS pattern)
        for col in ["total REAL DEFAULT 0", "costo_envio REAL DEFAULT 0",
                     "pago_metodo TEXT DEFAULT ''", "pago_monto REAL DEFAULT 0"]:
            try:
                self.conexion.execute(f"ALTER TABLE delivery_orders ADD COLUMN {col}")
            except Exception:
                pass  # Column already exists
        try:
            self.conexion.execute(
                "CREATE INDEX IF NOT EXISTS idx_del_estado "
                "ON delivery_orders(estado, sucursal_id)")
            self.conexion.execute(
                "CREATE INDEX IF NOT EXISTS idx_del_driver_cuts "
                "ON delivery_driver_cuts(driver_id, fecha)")
        except Exception:
            pass
        try: self.conexion.commit()
        except Exception: pass
    def cargar_pedidos(self):
        filtro = self.combo_filtro.currentText()
        self._loading.show()
        visibles = 0
        # Clear kanban columns
        for estado, col_layout in self.columnas.items():
            while col_layout.count() > 1:
                item = col_layout.takeAt(0)
                if item.widget(): item.widget().deleteLater()
        try:
            filtro_repo = None if filtro == "Todos" else filtro
            pedidos = self.delivery_service.list_orders(filtro_repo)
            self._pedidos_cache = pedidos
            # Actualizar vista lista
            self._actualizar_lista_view(pedidos if filtro == "Todos" else
                                        [p for p in pedidos if p.get("estado") == filtro])
            counts = {e:0 for e in ESTADOS}
            for p in pedidos:
                estado = p.get("estado","pendiente")
                counts[estado] = counts.get(estado,0) + 1
                if filtro != "Todos" and estado != filtro: continue
                if estado in self.columnas:
                    card = TarjetaPedido(p)
                    card.accion_requerida.connect(self.ejecutar_accion)
                    self.columnas[estado].insertWidget(self.columnas[estado].count()-1, card)
                    visibles += 1
            stats = "  ".join(f"{ESTADO_COLOR.get(e,'#FFF')} {e}:{n}" for e,n in counts.items() if n>0)
            self.lbl_stats.setText(f"Pedidos activos: {sum(counts.get(e,0) for e in ['pendiente','preparacion','en_ruta'])}")
            self._empty.setVisible(visibles == 0)
        except Exception as e:
            logger.error("cargar_pedidos: %s", e)
            self._empty.setVisible(True)
        finally:
            self._loading.hide()

    def ejecutar_accion(self, pedido_id: int, accion: str):
        try:
            if accion == "asignar":
                dlg = AsignarDriverDialog(pedido_id, self)
                if dlg.exec_() != QDialog.Accepted: return
                data = dlg.get_data()
                if not data["driver_id"]:
                    QMessageBox.warning(self,"Sin repartidor","Primero registra repartidores."); return
                self.conexion.execute(
                    "UPDATE delivery_orders SET estado='preparacion',driver_id=?,tiempo_estimado=?,notas=?,fecha_asignacion=datetime('now') WHERE id=?",
                    (data["driver_id"],data["tiempo"],data["notas"],pedido_id))
                self.delivery_service.update_status(pedido_id, "preparacion", usuario=self.usuario)
            elif accion in ("en_ruta","entregado","cancelado"):
                fecha_col = "fecha_entrega" if accion == "entregado" else "fecha_asignacion"
                
                # If delivered, capture payment method and amount
                pago_metodo = ""
                pago_monto  = 0.0
                if accion == "entregado":
                    dlg_pago = QDialog(self)
                    dlg_pago.setWindowTitle("Registrar Cobro de Entrega")
                    dlg_pago.setMinimumWidth(320)
                    lay_pago = QVBoxLayout(dlg_pago)
                    form_pago = QFormLayout()
                    
                    # Get order total
                    try:
                        ord_row = self.conexion.execute(
                            "SELECT COALESCE(total,0) FROM delivery_orders WHERE id=?",
                            (pedido_id,)).fetchone()
                        total_pedido = float(ord_row[0]) if ord_row else 0.0
                    except Exception:
                        total_pedido = 0.0
                    
                    cmb_metodo = QComboBox()
                    cmb_metodo.addItems(["Efectivo","Tarjeta","Transferencia","Ya pagado (online)","Sin cobro"])
                    spin_monto = QDoubleSpinBox()
                    spin_monto.setRange(0, 99999); spin_monto.setDecimals(2)
                    spin_monto.setValue(total_pedido); spin_monto.setPrefix("$")
                    form_pago.addRow("Método de cobro:", cmb_metodo)
                    form_pago.addRow("Monto cobrado:", spin_monto)
                    lay_pago.addLayout(form_pago)
                    btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
                    btns.accepted.connect(dlg_pago.accept)
                    btns.rejected.connect(dlg_pago.reject)
                    lay_pago.addWidget(btns)
                    
                    if dlg_pago.exec_() != QDialog.Accepted:
                        return
                    pago_metodo = cmb_metodo.currentText()
                    pago_monto  = spin_monto.value()
                
                self.conexion.execute(
                    f"UPDATE delivery_orders SET estado=?, {fecha_col}=datetime('now'), "
                    "pago_metodo=?, pago_monto=? WHERE id=?",
                    (accion, pago_metodo, pago_monto, pedido_id))
                
                # Audit the delivery completion
                if accion == "entregado":
                    try:
                        from core.services.auto_audit import audit_write
                        audit_write(
                            self.container if hasattr(self,'container') else None,
                            modulo="DELIVERY", accion="ENTREGA_COMPLETADA",
                            entidad="delivery_orders", entidad_id=str(pedido_id),
                            usuario=getattr(self,'usuario_actual','Sistema'),
                            sucursal_id=getattr(self,'sucursal_id',1),
                            detalles=f"Cobrado: ${pago_monto:.2f} via {pago_metodo}"
                        )
                    except Exception: pass
                
                self.delivery_service.update_status(
                    pedido_id,
                    accion,
                    usuario=self.usuario,
                    responsable=(self.usuario if accion == "entregado" else ""),
                )
            try: self.conexion.commit()
            except Exception: pass
            self.cargar_pedidos()
            # Publicar evento para recarga reactiva en otros módulos
            try:
                from core.events.event_bus import get_bus
                get_bus().publish("PEDIDO_ACTUALIZADO", {
                    "pedido_id": pedido_id, "accion": accion,
                    "sucursal_id": getattr(self, 'sucursal_id', 1)
                })
            except Exception:
                pass
        except Exception as e:
            QMessageBox.critical(self,"Error",str(e))

    def _notificar_whatsapp(self, pedido_id, accion, data):
        try:
            row = self.conexion.execute(
                "SELECT cliente_nombre, cliente_tel FROM delivery_orders WHERE id=?",(pedido_id,)).fetchone()
            if not row or not row[1]: return
            from integrations.whatsapp_service import WhatsAppService
            wa = WhatsAppService(self.conexion)
            if accion == "en_ruta":
                dr = data.get("repartidor","Repartidor")
                wa.notificar_delivery_en_camino(row[1],row[0],str(pedido_id),dr,data.get("tiempo",30))
            elif accion == "entregado":
                wa.notificar_delivery_entregado(row[1],row[0],str(pedido_id))
        except Exception as e:
            logger.debug("WA notify: %s", e)

    def nuevo_pedido(self):
        dlg = NuevoPedidoDialog(self.delivery_service, self)
        if dlg.exec_() != QDialog.Accepted: return
        data = dlg.get_data()
        if not data["direccion"]:
            QMessageBox.warning(self,"Dirección requerida","Ingresa la dirección de entrega."); return
        try:
            self.delivery_service.create_order({
                "cliente_nombre": data["cliente"],
                "direccion": data["direccion"],
                "coords": data.get("coords"),
                "notas": data["notas"],
                "sucursal_id": data["sucursal_id"],
            }, usuario=self.usuario)
            self.cargar_pedidos()
            Toast.success(self, "Pedido creado", "Pedido de delivery creado exitosamente.")
        except Exception as e:
            QMessageBox.critical(self,"Error",str(e))

    def gestionar_drivers(self):
        dlg = GestorDriversDialog(self.conexion, self)
        dlg.exec_()
        self.cargar_pedidos()

    # ── v13.30: Corte de caja por repartidor ──────────────────────────────────

    def _corte_repartidor(self):
        """Muestra resumen financiero del repartidor y registra corte de caja."""
        from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QTableWidget,
                                      QTableWidgetItem, QAbstractItemView)

        dlg = QDialog(self)
        dlg.setWindowTitle("💰 Corte de Caja — Repartidor")
        dlg.setMinimumSize(700, 520)
        lay = QVBoxLayout(dlg)

        # Selector de repartidor
        form = QFormLayout()
        cmb_driver = QComboBox()
        try:
            rows = self.conexion.execute(
                "SELECT id, nombre FROM drivers WHERE activo=1 ORDER BY nombre").fetchall()
            for r in rows:
                cmb_driver.addItem(r[1], r[0])
        except Exception:
            pass
        form.addRow("Repartidor:", cmb_driver)
        lay.addLayout(form)

        # Tabla de entregas pendientes de corte
        lbl_info = QLabel("Entregas completadas sin corte:")
        lbl_info.setObjectName("subheading")
        lay.addWidget(lbl_info)

        tbl = QTableWidget()
        tbl.setColumnCount(6)
        tbl.setHorizontalHeaderLabels(["ID", "Cliente", "Total", "Método", "Cobrado", "Fecha"])
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        hh = tbl.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        tbl.setObjectName("tableView")
        lay.addWidget(tbl)

        # Resumen financiero
        grp_resumen = QGroupBox("Resumen del turno")
        grp_resumen.setObjectName("styledGroup")
        rf = QFormLayout(grp_resumen)
        lbl_entregas = QLabel("0")
        lbl_entregas.setObjectName("textPrimary")
        
        lbl_efectivo = QLabel("$0.00")
        lbl_efectivo.setObjectName("textDanger")
        lbl_efectivo.setStyleSheet(f"font-size: {Typography.LG}; font-weight: bold;")
        
        lbl_tarjeta  = QLabel("$0.00")
        lbl_tarjeta.setObjectName("textPrimary")
        
        lbl_transfer = QLabel("$0.00")
        lbl_transfer.setObjectName("textPrimary")
        
        lbl_total    = QLabel("$0.00")
        lbl_total.setObjectName("heading")
        lbl_total.setStyleSheet(f"font-weight: bold;")
        
        rf.addRow("Entregas:", lbl_entregas)
        rf.addRow("Efectivo cobrado:", lbl_efectivo)
        rf.addRow("Tarjeta:", lbl_tarjeta)
        rf.addRow("Transferencia:", lbl_transfer)
        rf.addRow("Total cobrado:", lbl_total)

        # Efectivo que entrega el repartidor
        spin_entregado = QDoubleSpinBox()
        spin_entregado.setRange(0, 99999); spin_entregado.setDecimals(2)
        spin_entregado.setPrefix("$ ")
        spin_entregado.setObjectName("inputField")
        rf.addRow("Efectivo entregado:", spin_entregado)
        
        lbl_diferencia = QLabel("$0.00")
        lbl_diferencia.setObjectName("textPrimary")
        lbl_diferencia.setStyleSheet(f"font-weight: bold;")
        rf.addRow("Diferencia:", lbl_diferencia)
        txt_notas_corte = QLineEdit()
        txt_notas_corte.setPlaceholderText("Notas del corte (opcional)")
        txt_notas_corte.setObjectName("inputField")
        rf.addRow("Notas:", txt_notas_corte)
        lay.addWidget(grp_resumen)

        # Datos internos
        _data = {"efectivo": 0.0, "tarjeta": 0.0, "transfer": 0.0, "entregas": 0,
                 "order_ids": [], "turno_inicio": ""}

        def _cargar_entregas():
            driver_id = cmb_driver.currentData()
            if not driver_id:
                return
            try:
                entregas = self.conexion.execute("""
                    SELECT id, cliente_nombre, COALESCE(total,0), COALESCE(pago_metodo,''),
                           COALESCE(pago_monto,0), fecha_entrega
                    FROM delivery_orders
                    WHERE driver_id=? AND estado='entregado'
                      AND id NOT IN (SELECT order_id FROM delivery_cut_items WHERE cut_id IS NOT NULL)
                    ORDER BY fecha_entrega DESC
                """, (driver_id,)).fetchall()
            except Exception:
                # Table delivery_cut_items might not exist yet; show all uncut
                try:
                    entregas = self.conexion.execute("""
                        SELECT id, cliente_nombre, COALESCE(total,0), COALESCE(pago_metodo,''),
                               COALESCE(pago_monto,0), fecha_entrega
                        FROM delivery_orders
                        WHERE driver_id=? AND estado='entregado'
                          AND COALESCE(corte_id,0)=0
                        ORDER BY fecha_entrega DESC
                    """, (driver_id,)).fetchall()
                except Exception:
                    entregas = []

            tbl.setRowCount(len(entregas))
            efe = tar = tra = 0.0
            ids = []
            inicio = ""
            for i, r in enumerate(entregas):
                for j, v in enumerate(r):
                    tbl.setItem(i, j, QTableWidgetItem(str(v) if v else ""))
                monto = float(r[4] or 0)
                metodo = str(r[3] or "").lower()
                if "efect" in metodo:
                    efe += monto
                elif "tarjeta" in metodo or "card" in metodo:
                    tar += monto
                elif "transfer" in metodo:
                    tra += monto
                ids.append(r[0])
                if r[5] and (not inicio or str(r[5]) < inicio):
                    inicio = str(r[5])

            _data["efectivo"] = efe
            _data["tarjeta"] = tar
            _data["transfer"] = tra
            _data["entregas"] = len(entregas)
            _data["order_ids"] = ids
            _data["turno_inicio"] = inicio

            lbl_entregas.setText(str(len(entregas)))
            lbl_efectivo.setText(f"${efe:.2f}")
            lbl_tarjeta.setText(f"${tar:.2f}")
            lbl_transfer.setText(f"${tra:.2f}")
            lbl_total.setText(f"${efe+tar+tra:.2f}")
            spin_entregado.setValue(efe)  # Sugerir el total en efectivo
            _actualizar_diferencia()

        def _actualizar_diferencia():
            entregado = spin_entregado.value()
            esperado = _data["efectivo"]
            diff = entregado - esperado
            lbl_diferencia.setText(f"${diff:.2f}")
            # Mantener solo el color dinámico, eliminar tamaño de fuente hardcodeado
            if abs(diff) < 0.01:
                lbl_diferencia.setStyleSheet(f"color: {Colors.SUCCESS_BASE}; font-weight: bold;")
            elif diff < 0:
                lbl_diferencia.setStyleSheet(f"color: {Colors.DANGER_BASE}; font-weight: bold;")
            else:
                lbl_diferencia.setStyleSheet(f"color: {Colors.WARNING_BASE}; font-weight: bold;")

        cmb_driver.currentIndexChanged.connect(lambda: _cargar_entregas())
        spin_entregado.valueChanged.connect(lambda: _actualizar_diferencia())
        if cmb_driver.count() > 0:
            _cargar_entregas()

        # Botones
        btns = QDialogButtonBox()
        btn_registrar = create_success_button(dlg, "✅ Registrar Corte", "Registrar corte de caja del repartidor")
        btn_registrar.setObjectName("btnRegistrarCorte")
        # Eliminar estilos hardcodeados - usar clases CSS del sistema
        btns.addButton(btn_registrar, QDialogButtonBox.AcceptRole)
        btns.addButton("Cancelar", QDialogButtonBox.RejectRole)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        def _registrar_corte():
            driver_id = cmb_driver.currentData()
            if not driver_id or _data["entregas"] == 0:
                QMessageBox.warning(dlg, "Aviso", "No hay entregas para hacer corte.")
                return
            entregado = spin_entregado.value()
            diferencia = entregado - _data["efectivo"]
            try:
                # Registrar corte
                self.conexion.execute("""
                    INSERT INTO delivery_driver_cuts
                    (driver_id, driver_nombre, turno_inicio, entregas_total,
                     efectivo_cobrado, tarjeta_cobrado, transfer_cobrado, total_cobrado,
                     efectivo_entregado, diferencia, usuario_corte, sucursal_id, notas)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    driver_id, cmb_driver.currentText(),
                    _data["turno_inicio"] or None,
                    _data["entregas"],
                    _data["efectivo"], _data["tarjeta"], _data["transfer"],
                    _data["efectivo"] + _data["tarjeta"] + _data["transfer"],
                    entregado, diferencia,
                    getattr(self, 'usuario', 'Sistema'),
                    getattr(self, 'sucursal_id', 1),
                    txt_notas_corte.text().strip(),
                ))
                # Marcar entregas como cortadas
                cut_id = self.conexion.execute("SELECT last_insert_rowid()").fetchone()[0]
                for oid in _data["order_ids"]:
                    try:
                        self.conexion.execute(
                            "UPDATE delivery_orders SET corte_id=? WHERE id=?",
                            (cut_id, oid))
                    except Exception:
                        pass  # Column might not exist yet
                try:
                    self.conexion.execute(
                        "ALTER TABLE delivery_orders ADD COLUMN corte_id INTEGER DEFAULT 0")
                except Exception:
                    pass
                for oid in _data["order_ids"]:
                    try:
                        self.conexion.execute(
                            "UPDATE delivery_orders SET corte_id=? WHERE id=?",
                            (cut_id, oid))
                    except Exception:
                        pass

                try:
                    self.conexion.commit()
                except Exception:
                    pass

                # Auditar
                try:
                    from core.services.auto_audit import audit_write
                    audit_write(
                        self.container if hasattr(self, 'container') else None,
                        modulo="DELIVERY", accion="CORTE_REPARTIDOR",
                        entidad="delivery_driver_cuts", entidad_id=str(cut_id),
                        usuario=getattr(self, 'usuario', 'Sistema'),
                        sucursal_id=getattr(self, 'sucursal_id', 1),
                        detalles=(f"Repartidor: {cmb_driver.currentText()} | "
                                  f"Entregas: {_data['entregas']} | "
                                  f"Efectivo: ${_data['efectivo']:.2f} | "
                                  f"Entregado: ${entregado:.2f} | "
                                  f"Diferencia: ${diferencia:.2f}")
                    )
                except Exception:
                    pass

                msg = (f"Corte registrado exitosamente.\n\n"
                       f"Repartidor: {cmb_driver.currentText()}\n"
                       f"Entregas: {_data['entregas']}\n"
                       f"Efectivo cobrado: ${_data['efectivo']:.2f}\n"
                       f"Efectivo entregado: ${entregado:.2f}\n"
                       f"Diferencia: ${diferencia:.2f}")
                if abs(diferencia) > 0.01:
                    msg += f"\n\n⚠️ DIFERENCIA DE ${abs(diferencia):.2f}"
                QMessageBox.information(dlg, "✅ Corte Registrado", msg)
                dlg.accept()
            except Exception as e:
                QMessageBox.critical(dlg, "Error", str(e))

        btn_registrar.clicked.connect(_registrar_corte)
        dlg.exec_()

    def _historial_cortes(self):
        """Muestra historial de cortes de caja de repartidores."""
        from PyQt5.QtWidgets import QDialog, QTableWidget, QTableWidgetItem, QAbstractItemView

        dlg = QDialog(self)
        dlg.setWindowTitle("📋 Historial de Cortes — Delivery")
        dlg.setMinimumSize(800, 450)
        lay = QVBoxLayout(dlg)

        tbl = QTableWidget()
        tbl.setColumnCount(10)
        tbl.setHorizontalHeaderLabels([
            "ID", "Repartidor", "Fecha", "Entregas",
            "Efectivo", "Tarjeta", "Transfer", "Entregado",
            "Diferencia", "Usuario"
        ])
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        tbl.setAlternatingRowColors(True)
        hh = tbl.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        lay.addWidget(tbl)

        try:
            rows = self.conexion.execute("""
                SELECT id, driver_nombre, fecha, entregas_total,
                       efectivo_cobrado, tarjeta_cobrado, transfer_cobrado,
                       efectivo_entregado, diferencia, usuario_corte
                FROM delivery_driver_cuts
                ORDER BY fecha DESC LIMIT 100
            """).fetchall()
            tbl.setRowCount(len(rows))
            for i, r in enumerate(rows):
                for j, v in enumerate(r):
                    val = v
                    if j in (4, 5, 6, 7, 8) and v is not None:
                        val = f"${float(v):.2f}"
                    item = QTableWidgetItem(str(val) if val is not None else "")
                    # Color diferencia
                    if j == 8 and v is not None:
                        diff = float(v)
                        if abs(diff) > 0.01:
                            item.setForeground(QColor("#e74c3c") if diff < 0 else QColor("#f39c12"))
                        else:
                            item.setForeground(QColor("#27ae60"))
                    tbl.setItem(i, j, item)
        except Exception as e:
            lay.addWidget(QLabel(f"Error cargando historial: {e}"))

        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.setObjectName("secondaryBtn")
        btn_cerrar.clicked.connect(dlg.accept)
        lay.addWidget(btn_cerrar)
        dlg.exec_()

class GestorDriversDialog(QDialog):
    """Gestionar repartidores: agregar, editar, eliminar, sucursales, WA phone."""

    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.setWindowTitle("Gestionar Repartidores")
        self.setMinimumSize(680, 480)
        self._build_ui()
        self._cargar()

    def _build_ui(self):
        from PyQt5.QtWidgets import (QFormLayout, QLineEdit, QComboBox, QLabel,
                                      QHBoxLayout, QHeaderView, QAbstractItemView)
        from modulos.spj_phone_widget import PhoneWidget
        lay = QVBoxLayout(self)

        # Tabla
        self.tabla = QTableWidget(); self.tabla.setColumnCount(5)
        self.tabla.setHorizontalHeaderLabels(["ID","Nombre","Teléfono WA","Sucursales","Activo"])
        hh = self.tabla.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.tabla.setColumnHidden(0, True)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        lay.addWidget(self.tabla)

        # Form para agregar/editar
        form = QFormLayout()
        self.txt_nombre  = QLineEdit(); self.txt_nombre.setPlaceholderText("Nombre completo")
        self.txt_tel     = PhoneWidget(default_country="+52")
        self.txt_suc     = QLineEdit(); self.txt_suc.setPlaceholderText("ID sucursales separadas por coma, ej: 1,2")
        self.cmb_activo  = QComboBox(); self.cmb_activo.addItems(["Activo","Inactivo"])
        form.addRow("Nombre:",       self.txt_nombre)
        form.addRow("Teléfono WA:",  self.txt_tel)
        form.addRow("Sucursales:",   self.txt_suc)
        form.addRow("Estado:",       self.cmb_activo)
        lay.addLayout(form)

        # Botones
        btn_row = QHBoxLayout()
        self.btn_add    = create_success_button(self, "➕ Agregar", "Agregar nuevo repartidor")
        self.btn_edit   = create_warning_button(self, "✏️ Guardar edición", "Guardar cambios del repartidor seleccionado"); self.btn_edit.setEnabled(False)
        self.btn_delete = create_danger_button(self, "🗑️ Eliminar", "Eliminar repartidor seleccionado"); self.btn_delete.setEnabled(False)
        btn_cerrar      = create_secondary_button(self, "Cerrar", "Cerrar ventana")
        btn_cerrar.clicked.connect(self.accept)
        btn_row.addWidget(self.btn_add); btn_row.addWidget(self.btn_edit)
        btn_row.addWidget(self.btn_delete); btn_row.addStretch(); btn_row.addWidget(btn_cerrar)
        lay.addLayout(btn_row)

        self.btn_add.clicked.connect(self._agregar)
        self.btn_edit.clicked.connect(self._guardar_edicion)
        self.btn_delete.clicked.connect(self._eliminar)
        self.tabla.itemSelectionChanged.connect(self._on_select)

    def _cargar(self):
        try:
            # Ensure columns
            for col in ["sucursales TEXT", "activo INTEGER DEFAULT 1"]:
                try: self.conn.execute(f"ALTER TABLE drivers ADD COLUMN {col}")
                except Exception: pass
            rows = self.conn.execute(
                "SELECT id,nombre,COALESCE(telefono,''),COALESCE(sucursales,''),COALESCE(activo,1) "
                "FROM drivers ORDER BY nombre"
            ).fetchall()
            self.tabla.setRowCount(0)
            for i, r in enumerate(rows):
                self.tabla.insertRow(i)
                from PyQt5.QtWidgets import QTableWidgetItem
                for j, v in enumerate(r):
                    self.tabla.setItem(i, j, QTableWidgetItem(str(v) if v is not None else ""))
                # Color inactive
                if not int(r[4]):
                    for j in range(5):
                        it = self.tabla.item(i, j)
                        if it: it.setForeground(__import__('PyQt5.QtGui',fromlist=['QColor']).QColor('#aaa'))
        except Exception as e:
            import logging; logging.getLogger("spj.delivery").warning("cargar drivers: %s", e)

    def _on_select(self):
        rows = self.tabla.selectedItems()
        has = bool(rows)
        self.btn_edit.setEnabled(has); self.btn_delete.setEnabled(has)
        if has:
            row = self.tabla.currentRow()
            self.txt_nombre.setText(self.tabla.item(row,1).text() if self.tabla.item(row,1) else "")
            self.txt_tel.set_phone(self.tabla.item(row,2).text() if self.tabla.item(row,2) else "")
            self.txt_suc.setText(   self.tabla.item(row,3).text() if self.tabla.item(row,3) else "")
            activo_val = self.tabla.item(row,4).text() if self.tabla.item(row,4) else "1"
            self.cmb_activo.setCurrentIndex(0 if activo_val == "1" else 1)

    def _validar(self):
        import re as _re
        nombre = self.txt_nombre.text().strip()
        tel    = self.txt_tel.get_e164().strip()
        if not nombre:
            QMessageBox.warning(self,"Aviso","El nombre es obligatorio."); return False
        # v13.30: Validar dígitos locales (10 para MX)
        digitos = _re.sub(r'\D', '', self.txt_tel.get_number())
        if tel and len(digitos) != 10:
            QMessageBox.warning(self,"Teléfono inválido",
                "El número debe tener 10 dígitos.\nEl código de país se agrega automáticamente."); return False
        return True

    def _agregar(self):
        if not self._validar(): return
        tel = self.txt_tel.get_e164().strip()
        suc = self.txt_suc.text().strip()
        activo = 1 if self.cmb_activo.currentIndex()==0 else 0
        self.conn.execute(
            "INSERT INTO drivers(nombre,telefono,sucursales,activo) VALUES(?,?,?,?)",
            (self.txt_nombre.text().strip(), tel, suc, activo))
        try: self.conn.commit()
        except Exception: pass
        self._limpiar_form(); self._cargar()

    def _guardar_edicion(self):
        if not self._validar(): return
        row = self.tabla.currentRow()
        driver_id = int(self.tabla.item(row,0).text())
        tel = self.txt_tel.get_e164().strip()
        suc = self.txt_suc.text().strip()
        activo = 1 if self.cmb_activo.currentIndex()==0 else 0
        self.conn.execute(
            "UPDATE drivers SET nombre=?,telefono=?,sucursales=?,activo=? WHERE id=?",
            (self.txt_nombre.text().strip(), tel, suc, activo, driver_id))
        try: self.conn.commit()
        except Exception: pass
        self._limpiar_form(); self._cargar()

    def _eliminar(self):
        # [spj-dedup] from PyQt5.QtWidgets import QMessageBox
        row = self.tabla.currentRow()
        driver_id = int(self.tabla.item(row,0).text())
        nombre    = self.tabla.item(row,1).text()
        if QMessageBox.question(self,"Confirmar",
            f"¿Eliminar al repartidor {nombre}?",
            QMessageBox.Yes|QMessageBox.No) != QMessageBox.Yes: return
        self.conn.execute("DELETE FROM drivers WHERE id=?", (driver_id,))
        try: self.conn.commit()
        except Exception: pass
        self._limpiar_form(); self._cargar()

    def _limpiar_form(self):
        self.txt_nombre.clear(); self.txt_tel.set_phone(""); self.txt_suc.clear()
        self.cmb_activo.setCurrentIndex(0)
        self.btn_edit.setEnabled(False); self.btn_delete.setEnabled(False)
        self.tabla.clearSelection()
