
# ui/dashboard.py — SPJ POS v13.4
"""
Dashboard principal del POS en tiempo real.
  - KPIs del día: ventas, tickets, productos top
  - Cola de pedidos WhatsApp pendientes
  - Alertas de stock bajo y lotes por caducar
  - Estado de repartidores activos
  - Acceso rápido a módulos clave

UI OPTIMIZADA v13.4: Usa design_tokens y ui_components para consistencia global.
Sistema de diseño centralizado con variables CSS y clases semánticas.
"""
from __future__ import annotations
import logging
from datetime import datetime
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QFrame, QScrollArea, QSizePolicy,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QColor
from core.db.connection import get_connection

# Importar design tokens para consistencia
from modulos.design_tokens import Colors, Spacing, Typography, Borders, Shadows
from modulos.ui_components import LoadingIndicator, EmptyStateWidget

logger = logging.getLogger("spj.ui.dashboard")

# Variables CSS para reutilización (design tokens - modo claro por defecto)
CSS_VARS = """
    --bg-card: #FFFFFF;
    --bg-hover: #F8FAFC;
    --border: #E2E8F0;
    --border-active: #2563EB;
    --text-primary: #0F172A;
    --text-secondary: #64748B;
    --text-muted: #94A3B8;
    --primary: #2563EB;
    --primary-hover: #E600E6;
    --success: #16A34A;
    --warning: #D97706;
    --danger: #DC2626;
    --bg-danger-soft: #FEF2F2;
    --bg-warning-soft: #FEF3C7;
    --bg-success-soft: #DCFCE7;
    --bg-info-soft: #DBEAFE;
"""


class KPICard(QFrame):
    """
    Tarjeta de KPI individual.
    Diseño optimizado: fondo neutro con indicador de color, no card saturada.
    Usa variables CSS para consistencia.
    """
    clicked = pyqtSignal(str)

    def __init__(self, titulo: str, valor: str = "—",
                 color: str = "",          # deprecated: se ignora si metric_key dado
                 icono: str = "📊",
                 key: str = "",
                 metric_key: str = "",     # clave para KPIColorEngine
                 metric_value: float = 0,  # valor numérico actual
                 metric_prev: float = 0,   # valor período anterior (para tendencia)
                 tendencia: str = "",      # override manual de tendencia
                 parent=None):
        super().__init__(parent)
        self._key = key
        self._metric_key = metric_key

        # Resolver color via KPIColorEngine si se provee metric_key
        if metric_key:
            try:
                from core.services.kpi_color_engine import get_kpi_color_engine
                _eng = get_kpi_color_engine()
                cfg = _eng.kpi_config(metric_key, metric_value, metric_prev)
                _color = cfg["color"]
                _text_sub = cfg["text_sub_color"]
                if not tendencia and metric_prev:
                    tendencia = cfg["tendencia"]
            except Exception:
                _color = "#2563EB"  # Default azul primario
                _text_sub = "#64748B"
        else:
            _color = "#2563EB"  # Default azul primario
            _text_sub = "#64748B"

        self.setFrameStyle(QFrame.StyledPanel)
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("kpiCard")
        self.setProperty("variant", "card")
        self._current_color = _color
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(80)  # Reducido de 100 a 80px

        lyt = QVBoxLayout(self)
        lyt.setContentsMargins(12, 8, 12, 8)  # Padding reducido

        top = QHBoxLayout()
        lbl_icono = QLabel(icono)
        lbl_icono.setStyleSheet(f"font-size: 20px; background: transparent; color: {_color};")
        top.addWidget(lbl_icono)
        top.addStretch()
        # Tendencia — muestra % de cambio si disponible
        if tendencia:
            self.lbl_tendencia = QLabel(tendencia)
            self.lbl_tendencia.setStyleSheet(
                f"color: {_text_sub}; font-size: 10px; "
                "font-weight: 600; background: transparent;")
            top.addWidget(self.lbl_tendencia)
        else:
            self.lbl_tendencia = None
        lyt.addLayout(top)

        self.lbl_valor = QLabel(valor)
        self.lbl_valor.setObjectName("kpiValue")
        self.lbl_valor.setStyleSheet(
            "font-size: 18px; font-weight: 700; background: transparent;")
        lyt.addWidget(self.lbl_valor)

        lbl_titulo = QLabel(titulo)
        lbl_titulo.setStyleSheet(
            f"color: {_text_sub}; font-size: 11px; background: transparent;")
        lyt.addWidget(lbl_titulo)

    def set_sucursal(self, sucursal_id: int, nombre: str = "") -> None:
        self.sucursal_id = sucursal_id
        self._nombre_sucursal = nombre
        if hasattr(self, '_lbl_titulo_dash') and nombre:
            self._lbl_titulo_dash.setText(f"📈 Dashboard — {nombre}")
        try: self._refrescar()
        except Exception: pass

    def set_usuario_actual(self, usuario: str, rol: str = "") -> None:
        self.usuario_actual = usuario
        self.rol_actual = rol.lower() if rol else "cajero"
        # Re-run actualizar to filter by role
        try: self.actualizar()
        except Exception: pass


    def set_valor(self, valor: str):
        self.lbl_valor.setText(valor)

    def set_estado(self, metric_value: float, metric_prev: float = 0) -> None:
        """
        Actualiza color y tendencia según el nuevo valor.
        Llama a KPIColorEngine — sin lógica de color aquí.
        """
        if not self._metric_key:
            return
        try:
            from core.services.kpi_color_engine import get_kpi_color_engine
            _eng = get_kpi_color_engine()
            cfg = _eng.kpi_config(self._metric_key, metric_value, metric_prev)
            _color = cfg["color"]
            _text_sub = cfg["text_sub_color"]
            self.setStyleSheet(f"""
                KPICard {{ background: {_color}; border-radius: 12px; border: none; }}
                KPICard:hover {{ background: {_color}dd; }}
            """)
            self._current_color = _color
            if self.lbl_tendencia and cfg.get("tendencia"):
                self.lbl_tendencia.setText(cfg["tendencia"])
                self.lbl_tendencia.setStyleSheet(
                    f"color: {_text_sub}; font-size: 10px; "
                    "font-weight: 600; background: transparent;")
        except Exception:
            pass

    def mousePressEvent(self, event):
        self.clicked.emit(self._key)


class AlertaItem(QFrame):
    """Item de alerta en la lista lateral. Usa variables CSS para consistencia."""
    def __init__(self, texto: str, tipo: str = "info", parent=None):
        super().__init__(parent)
        colores_bg = {
            "danger":  "var(--bg-danger-soft)",
            "warning": "var(--bg-warning-soft)",
            "success": "var(--bg-success-soft)",
            "info":    "var(--bg-info-soft)",
        }
        colores_border = {
            "danger":  "var(--danger)",
            "warning": "var(--warning)",
            "success": "var(--success)",
            "info":    "var(--primary)",
        }
        iconos = {"danger":"🔴","warning":"⚠️","success":"✅","info":"ℹ️"}
        self.setStyleSheet(f"""
            AlertaItem {{
                background: {colores_bg.get(tipo,'var(--bg-info-soft)')};
                border-radius: 8px;
                border-left: 4px solid {colores_border.get(tipo,'var(--primary)')};
            }}
        """)
        lyt = QHBoxLayout(self)
        lyt.setContentsMargins(10, 8, 10, 8)
        lbl = QLabel(f"{iconos.get(tipo,'•')} {texto}")
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size: 12px; background: transparent;")
        lyt.addWidget(lbl)


class PedidoWAItem(QFrame):
    """Tarjeta de pedido WhatsApp en el dashboard. Usa variables CSS."""
    ver_pedido = pyqtSignal(int)

    def __init__(self, pedido: dict, parent=None):
        super().__init__(parent)
        pid = pedido.get("id", 0)
        self.setStyleSheet("""
            PedidoWAItem {
                background: var(--bg-card);
                border-radius: 8px;
                border: 1px solid var(--border);
            }
            PedidoWAItem:hover { border-color: var(--primary); }
        """)
        lyt = QVBoxLayout(self)
        lyt.setContentsMargins(12, 10, 12, 10)
        lyt.setSpacing(4)

        top = QHBoxLayout()
        lbl_id = QLabel(f"📲 Pedido #{pid}")
        lbl_id.setStyleSheet("font-weight: 700; font-size: 13px;")
        top.addWidget(lbl_id)
        top.addStretch()
        estado = pedido.get("estado","nuevo")
        colores_estado = {
            "nuevo": "var(--danger)",
            "confirmado": "#2563EB",
            "pesando": "var(--warning)",
            "listo": "var(--success)"
        }
        badge = QLabel(estado.upper())
        badge.setStyleSheet(
            f"background:{colores_estado.get(estado,'var(--text-muted)')};"
            "color:white;padding:4px 8px;border-radius:6px;font-size:10px;font-weight:600;")
        top.addWidget(badge)
        lyt.addLayout(top)

        lyt.addWidget(QLabel(pedido.get("cliente_nombre","—")))
        lyt.addWidget(QLabel(
            f"${float(pedido.get('total',0)):.2f} · "
            f"{pedido.get('tipo_entrega','mostrador')}"))

        btn = QPushButton("Ver detalle →")
        btn.setObjectName("primaryBtn")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip(f"Ver detalles del pedido #{pid}")
        btn.clicked.connect(lambda: self.ver_pedido.emit(pid))
        lyt.addWidget(btn)


class Dashboard(QWidget):
    """Dashboard principal con KPIs, alertas y cola de pedidos."""

    abrir_modulo = pyqtSignal(str)   # key del módulo a abrir

    def __init__(self, container_or_conn=None, parent=None):
        # Accept either AppContainer or raw conn
        if hasattr(container_or_conn, 'db'):
            conn = container_or_conn.db
            self._container = container_or_conn
        else:
            conn = container_or_conn
            self._container = None
        super().__init__(parent)
        self.conn = conn or get_connection()
        self._setup_ui()
        # Fallback timer: cada 60s (solo si no llega evento del bus)
        self._timer = QTimer(self)
        self._timer.setInterval(60_000)
        self._timer.timeout.connect(self.actualizar)
        self._timer.start()

        # EventBus: actualización INMEDIATA tras cada venta o alerta
        try:
            from core.events.event_bus import get_bus, VENTA_COMPLETADA, STOCK_BAJO_MINIMO
            from PyQt5.QtCore import QTimer as _QT
            bus = get_bus()
            bus.subscribe(
                VENTA_COMPLETADA,
                lambda _p: _QT.singleShot(0, self.actualizar),
                label="dashboard.venta"
            )
            bus.subscribe(
                STOCK_BAJO_MINIMO,
                lambda _p: _QT.singleShot(0, self.actualizar),
                label="dashboard.stock_bajo"
            )
        except Exception as _e:
            logger.debug("EventBus dashboard: %s", _e)

        self.actualizar()

    def _setup_ui(self):
        self.setObjectName("Dashboard")
        # No hardcoded background — global QSS (dark: #0F172A, light: #F8FAFC) controls it

        root = QVBoxLayout(self)
        root.setSpacing(8)  # Reducido de 16 a 8
        root.setContentsMargins(0, 0, 0, 0)

        # ── Header ──────────────────────────────────────────────────
        header = QFrame()
        header.setObjectName("dashboardHeader")
        header.setFixedHeight(50)  # Reducido de 60 a 50
        hdr_lyt = QHBoxLayout(header)
        hdr_lyt.setContentsMargins(16, 0, 16, 0)
        lbl_titulo = QLabel("📊 Dashboard SPJ POS")
        lbl_titulo.setObjectName("dashboardTitle")
        hdr_lyt.addWidget(lbl_titulo)
        hdr_lyt.addStretch()
        self.lbl_hora = QLabel()
        self.lbl_hora.setObjectName("dashboardTime")
        hdr_lyt.addWidget(self.lbl_hora)
        root.addWidget(header)

        # ── Cuerpo ───────────────────────────────────────────────────
        body = QHBoxLayout()
        body.setContentsMargins(12, 12, 12, 12)  # Padding reducido
        body.setSpacing(12)

        # Columna izquierda (KPIs + pedidos WA)
        left = QVBoxLayout()
        left.setSpacing(12)

        # KPIs grid
        kpi_grid = QGridLayout()
        kpi_grid.setSpacing(8)  # Reducido de 10 a 8
        self._kpis = {
            "ventas_hoy":    KPICard("Ventas hoy",    "$0",  "#2563EB", "💰", "ventas"),
            "tickets_hoy":   KPICard("Tickets",       "0",   "#2563EB", "🧾", "ventas"),
            "pedidos_wa":    KPICard("Pedidos WA",    "0",   "#2563EB", "📲", "pedidos_whatsapp"),
            "productos_bajo": KPICard("Stock bajo",   "0",   "#2563EB", "⚠️", "inventario"),
        }
        for i, (key, card) in enumerate(self._kpis.items()):
            card.clicked.connect(self.abrir_modulo)
            kpi_grid.addWidget(card, i // 2, i % 2)
        left.addLayout(kpi_grid)

        # Cola pedidos WA
        lbl_wa = QLabel("📲 Pedidos WhatsApp pendientes")
        lbl_wa.setObjectName("sectionLabel")
        left.addWidget(lbl_wa)

        self._scroll_wa = QScrollArea()
        self._scroll_wa.setWidgetResizable(True)
        self._scroll_wa.setMinimumHeight(180)  # Reducido de 220 a 180
        self._container_wa = QWidget()
        self._lyt_wa = QVBoxLayout(self._container_wa)
        self._lyt_wa.setSpacing(6)  # Reducido de 8 a 6
        self._lyt_wa.setContentsMargins(0, 0, 0, 0)
        self._lyt_wa.addStretch()
        self._scroll_wa.setWidget(self._container_wa)
        left.addWidget(self._scroll_wa)
        self._loading_wa = LoadingIndicator("Cargando pedidos WA…", self)
        self._loading_wa.hide()
        left.addWidget(self._loading_wa)
        self._empty_wa = EmptyStateWidget(
            "Sin pedidos pendientes",
            "No hay pedidos de WhatsApp en cola.",
            "✅",
            self,
        )
        self._empty_wa.hide()
        left.addWidget(self._empty_wa)

        # Accesos rápidos
        lbl_acc = QLabel("⚡ Acceso rápido")
        lbl_acc.setObjectName("sectionLabel")
        left.addWidget(lbl_acc)
        acc_row = QHBoxLayout()
        acc_row.setSpacing(6)  # Reducido de 8 a 6
        for texto, key, color in [
            ("🛒 Nueva Venta",    "ventas",           "#2563EB"),  # Azul primario
            ("📦 Inventario",     "inventario",        "#2563EB"),
            ("📲 Pedidos WA",     "pedidos_whatsapp",  "#2563EB"),
            ("📊 Reportes",       "reportes",          "#2563EB"),
        ]:
            btn = QPushButton(texto)
            btn.setObjectName("primaryBtn")  # Usar estilo global
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(f"Ir al módulo de {texto.lower()}")  # Tooltip agregado
            btn.clicked.connect(lambda _, k=key: self.abrir_modulo.emit(k))
            acc_row.addWidget(btn)
        left.addLayout(acc_row)
        left.addStretch()

        # Columna derecha (alertas + repartidores)
        right = QVBoxLayout()
        right.setSpacing(12)
        right.setContentsMargins(0, 0, 0, 0)

        lbl_alertas = QLabel("🔔 Alertas")
        lbl_alertas.setObjectName("sectionLabelBold")
        right.addWidget(lbl_alertas)

        self._scroll_alertas = QScrollArea()
        self._scroll_alertas.setWidgetResizable(True)
        self._scroll_alertas.setFixedWidth(300)
        self._container_alertas = QWidget()
        self._lyt_alertas = QVBoxLayout(self._container_alertas)
        self._lyt_alertas.setSpacing(6)
        self._lyt_alertas.setContentsMargins(0, 0, 0, 0)
        self._lyt_alertas.addStretch()
        self._scroll_alertas.setWidget(self._container_alertas)
        right.addWidget(self._scroll_alertas)
        self._loading_alertas = LoadingIndicator("Cargando alertas…", self)
        self._loading_alertas.hide()
        right.addWidget(self._loading_alertas)
        self._empty_alertas = EmptyStateWidget(
            "Sin alertas",
            "No hay alertas pendientes por revisar.",
            "🔕",
            self,
        )
        self._empty_alertas.hide()
        right.addWidget(self._empty_alertas)

        lbl_reps = QLabel("🚚 Repartidores activos")
        lbl_reps.setObjectName("sectionLabelBold")
        right.addWidget(lbl_reps)
        self._lbl_reps = QLabel("Sin repartidores activos")
        self._lbl_reps.setWordWrap(True)
        self._lbl_reps.setObjectName("repartidorStatus")
        right.addWidget(self._lbl_reps)
        right.addStretch()

        body.addLayout(left, 3)
        body.addLayout(right, 1)
        root.addLayout(body, 1)

    # ── Actualización ──────────────────────────────────────────────
    def actualizar(self):
        self.lbl_hora.setText(datetime.now().strftime("%d/%m/%Y %H:%M"))
        self._actualizar_kpis()
        self._actualizar_pedidos_wa()
        self._actualizar_alertas()
        self._actualizar_repartidores()

    def _actualizar_kpis(self):
        # ── Ventas del día ────────────────────────────────────────────────────
        ventas_hoy = tickets_hoy = 0.0
        try:
            es_gerente = getattr(self, 'rol_actual', 'cajero') in ('admin','administrador','gerente')
            suc_filter = "" if es_gerente else f"AND sucursal_id={getattr(self,'sucursal_id',1)}"
            row = self.conn.execute(f"""
                SELECT COALESCE(SUM(total),0), COUNT(*)
                FROM ventas WHERE DATE(fecha)=DATE('now') AND estado='completada'
                {suc_filter}""").fetchone()
            ventas_hoy  = float(row[0])
            tickets_hoy = int(row[1])
            self._kpis["ventas_hoy"].set_valor(f"${ventas_hoy:,.0f}")
            self._kpis["tickets_hoy"].set_valor(str(tickets_hoy))
            ticket_prom = ventas_hoy / tickets_hoy if tickets_hoy > 0 else 0
            self._kpis["ticket_prom"].set_valor(f"${ticket_prom:,.0f}")
        except Exception: pass

        # ── Margen bruto del día ──────────────────────────────────────────────
        try:
            r = self.conn.execute("""
                SELECT COALESCE(SUM(vd.cantidad * vd.precio_unitario),0) as ingresos,
                       COALESCE(SUM(vd.cantidad * COALESCE(p.precio_compra,0)),0) as costos
                FROM ventas v
                JOIN detalles_venta vd ON vd.venta_id=v.id
                JOIN productos p ON p.id=vd.producto_id
                WHERE DATE(v.fecha)=DATE('now') AND v.estado='completada'""").fetchone()
            ingresos = float(r[0] or 0)
            costos   = float(r[1] or 0)
            margen   = ((ingresos - costos) / ingresos * 100) if ingresos > 0 else 0
            color    = "#27AE60" if margen >= 20 else "#E67E22" if margen >= 10 else "#E74C3C"
            self._kpis["margen_hoy"].set_valor(f"{margen:.1f}%")
            self._kpis["margen_hoy"].setStyleSheet(
                self._kpis["margen_hoy"].styleSheet().replace("background", f"background"))
        except Exception: pass

        # ── Comparativo vs ayer ───────────────────────────────────────────────
        try:
            ayer = float(self.conn.execute("""
                SELECT COALESCE(SUM(total),0) FROM ventas
                WHERE DATE(fecha)=DATE('now','-1 day') AND estado='completada'""").fetchone()[0])
            if ayer > 0:
                delta = ((ventas_hoy - ayer) / ayer * 100)
                sign  = "+" if delta >= 0 else ""
                color = "#27AE60" if delta >= 0 else "#E74C3C"
                self._kpis["vs_ayer"].set_valor(f"{sign}{delta:.1f}%")
        except Exception: pass

        # ── Clientes atendidos hoy ────────────────────────────────────────────
        try:
            n_clientes = self.conn.execute("""
                SELECT COUNT(DISTINCT COALESCE(cliente_id,0)) FROM ventas
                WHERE DATE(fecha)=DATE('now') AND estado='completada'
                  AND cliente_id IS NOT NULL""").fetchone()[0]
            self._kpis["clientes_hoy"].set_valor(str(n_clientes))
        except Exception: pass

        # ── Pedidos WA pendientes ─────────────────────────────────────────────
        try:
            n = self.conn.execute("""
                SELECT COUNT(*) FROM pedidos_whatsapp
                WHERE estado NOT IN ('entregado','cancelado')""").fetchone()[0]
            self._kpis["pedidos_wa"].set_valor(str(n))
        except Exception: pass

        # ── Stock bajo mínimo ─────────────────────────────────────────────────
        try:
            n = self.conn.execute("""
                SELECT COUNT(*) FROM productos
                WHERE existencia <= COALESCE(stock_minimo,5) AND activo=1""").fetchone()[0]
            self._kpis["productos_bajo"].set_valor(str(n))
        except Exception: pass

    def _actualizar_pedidos_wa(self):
        self._loading_wa.show()
        # Limpiar
        while self._lyt_wa.count() > 1:
            item = self._lyt_wa.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        try:
            rows = self.conn.execute("""
                SELECT id, cliente_nombre, numero_whatsapp, estado,
                       total, tipo_entrega, fecha
                FROM pedidos_whatsapp
                WHERE estado NOT IN ('entregado','cancelado')
                ORDER BY CASE estado
                    WHEN 'nuevo' THEN 0 WHEN 'confirmado' THEN 1
                    WHEN 'pesando' THEN 2 ELSE 3 END, fecha DESC
                LIMIT 8""").fetchall()
            if not rows:
                lbl = QLabel("✅ Sin pedidos pendientes")
                lbl.setStyleSheet(
                    "color:#94A3B8;font-size:13px;padding:12px;"
                    "background:#1E293B;border-radius:8px;")
                self._lyt_wa.insertWidget(0, lbl)
                self._empty_wa.show()
                return
            for i, r in enumerate(rows):
                card = PedidoWAItem(dict(r))
                card.ver_pedido.connect(self._on_ver_pedido)
                self._lyt_wa.insertWidget(i, card)
            self._empty_wa.hide()
        except Exception as e:
            logger.debug("pedidos_wa: %s", e)
            self._empty_wa.show()
        finally:
            self._loading_wa.hide()

    def _actualizar_alertas(self):
        self._loading_alertas.show()
        while self._lyt_alertas.count() > 1:
            item = self._lyt_alertas.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        alertas = []
        try:
            rows = self.conn.execute("""
                SELECT nombre FROM productos
                WHERE existencia <= COALESCE(stock_minimo,5) AND activo=1
                LIMIT 5""").fetchall()
            for r in rows:
                alertas.append((f"Stock bajo: {r[0]}", "danger"))
        except Exception: pass
        try:
            rows = self.conn.execute("""
                SELECT p.nombre FROM lotes l
                JOIN productos p ON p.id=l.producto_id
                WHERE l.caducidad <= DATE('now','+3 days')
                  AND l.estado='activo' AND l.cantidad_disponible > 0
                LIMIT 5""").fetchall()
            for r in rows:
                alertas.append((f"Caducidad próxima: {r[0]}", "warning"))
        except Exception: pass
        try:
            rows = self.conn.execute("""
                SELECT titulo, tipo FROM alertas_log
                WHERE leida=0 AND tipo != 'ok'
                ORDER BY fecha DESC LIMIT 10""").fetchall()
            for r in rows:
                t = "warning" if r[1] in ("stock_bajo","caducidad_proxima") else "info"
                alertas.append((r[0], t))
        except Exception: pass
        if not alertas:
            self._empty_alertas.show()
            self._loading_alertas.hide()
            return
        self._empty_alertas.hide()
        for i, (texto, tipo) in enumerate(alertas):
            self._lyt_alertas.insertWidget(i, AlertaItem(texto, tipo))
        self._loading_alertas.hide()

    def _actualizar_repartidores(self):
        try:
            rows = self.conn.execute("""
                SELECT d.nombre, d.en_ruta,
                    COUNT(p.id) as pedidos_activos
                FROM drivers d
                LEFT JOIN pedidos_whatsapp p
                    ON p.repartidor_id=d.id AND p.estado='listo'
                WHERE d.activo=1
                GROUP BY d.id
                ORDER BY d.nombre""").fetchall()
            if not rows:
                self._lbl_reps.setText("Sin repartidores registrados")
                return
            lines = []
            for r in rows:
                estado = "🟢 En ruta" if r[1] else "⚪ Disponible"
                lines.append(
                    f"• {r[0]}  {estado}  ({r[2]} pedidos)")
            self._lbl_reps.setText("\n".join(lines))
        except Exception:
            pass

    def _on_ver_pedido(self, pedido_id: int):
        self.abrir_modulo.emit("pedidos_whatsapp")

    def set_sesion(self, usuario: str, rol: str):
        pass


class DashboardWidget(Dashboard):
    """Alias de Dashboard para compatibilidad con main_window.py."""
    pass
