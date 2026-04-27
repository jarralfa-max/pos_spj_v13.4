
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
    QGraphicsDropShadowEffect,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QColor
from core.db.connection import get_connection

# Importar design tokens para consistencia
from modulos.design_tokens import Colors, Spacing, Typography, Borders, Shadows
from modulos.ui_components import (
    LoadingIndicator, EmptyStateWidget, PageHeader,
)

logger = logging.getLogger("spj.ui.dashboard")


_VARIANT_ACCENT = {
    "primary": Colors.PRIMARY.BASE,
    "success": Colors.SUCCESS.BASE,
    "danger":  Colors.DANGER.BASE,
    "warning": Colors.WARNING.BASE,
    "info":    Colors.INFO.BASE,
}


class KPICard(QFrame):
    """
    Tarjeta KPI moderna: accent bar superior, sombra suave, delta opcional.

    Resuelve el color del accent vía KPIColorEngine si se provee metric_key
    (semáforo dinámico verde/amarillo/rojo según umbrales del negocio); en
    caso contrario usa el color de la variante.

    Hover y fondo dependen del tema (theme-aware vía objectName "kpiCard"
    cuyo QSS se define en modulos.qss_builder._block_kpi_card).

    API pública preservada:
        clicked: pyqtSignal(str)        # emitido en clic
        set_valor(str)                   # actualiza valor mostrado
        set_estado(value, prev)          # actualiza color + tendencia desde KPIColorEngine
    """
    clicked = pyqtSignal(str)

    def __init__(self, titulo: str, valor: str = "—",
                 color: str = "",          # legacy, se ignora si metric_key
                 icono: str = "📊",
                 key: str = "",
                 metric_key: str = "",
                 metric_value: float = 0,
                 metric_prev: float = 0,
                 tendencia: str = "",
                 variant: str = "primary",
                 parent=None):
        super().__init__(parent)
        self._key = key
        self._metric_key = metric_key
        self._variant = variant

        accent = self._resolve_accent(metric_key, metric_value, metric_prev, variant)
        if metric_key and not tendencia:
            tendencia = self._resolve_tendencia(metric_key, metric_value, metric_prev)
        self._current_color = accent

        self.setObjectName("kpiCard")
        self.setProperty("variant", variant)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(96)

        # Sombra
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 32))
        self.setGraphicsEffect(shadow)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Accent bar superior
        self._accent_bar = QFrame(self)
        self._accent_bar.setFixedHeight(3)
        self._accent_bar.setStyleSheet(
            f"background-color: {accent};"
            f" border-top-left-radius: {Borders.RADIUS_LG}px;"
            f" border-top-right-radius: {Borders.RADIUS_LG}px;"
            f" border: none;"
        )
        outer.addWidget(self._accent_bar)

        # Cuerpo
        body = QHBoxLayout()
        body.setContentsMargins(16, 12, 16, 12)
        body.setSpacing(8)
        outer.addLayout(body)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        lbl_titulo = QLabel(titulo.upper(), self)
        lbl_titulo.setStyleSheet(
            f"color: {Colors.NEUTRAL.SLATE_500};"
            f" font-size: {Typography.SIZE_XS};"
            f" font-weight: {Typography.WEIGHT_SEMIBOLD};"
            f" letter-spacing: 0.05em;"
            f" background: transparent; border: none;"
        )
        text_col.addWidget(lbl_titulo)

        self.lbl_valor = QLabel(valor, self)
        self.lbl_valor.setObjectName("kpiValue")
        self.lbl_valor.setStyleSheet(
            f"font-size: 22px;"
            f" font-weight: {Typography.WEIGHT_BOLD};"
            f" letter-spacing: -0.02em;"
            f" background: transparent; border: none;"
        )
        text_col.addWidget(self.lbl_valor)

        # Tendencia: pill con color según signo
        self.lbl_tendencia = QLabel("", self)
        self.lbl_tendencia.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self._set_tendencia_text(tendencia)
        text_col.addWidget(self.lbl_tendencia, alignment=Qt.AlignLeft)

        body.addLayout(text_col, 1)

        # Ícono con tinte
        lbl_icono = QLabel(icono, self)
        lbl_icono.setFixedSize(40, 40)
        lbl_icono.setAlignment(Qt.AlignCenter)
        lbl_icono.setStyleSheet(
            f"font-size: 22px;"
            f" background-color: {accent}1F;"  # alpha 12%
            f" border-radius: {Borders.RADIUS_LG}px;"
            f" border: none;"
        )
        body.addWidget(lbl_icono, 0, alignment=Qt.AlignTop)

    # ── Helpers de color/tendencia (KPIColorEngine opcional) ──────────────
    @staticmethod
    def _resolve_accent(metric_key, metric_value, metric_prev, variant) -> str:
        if metric_key:
            try:
                from core.services.kpi_color_engine import get_kpi_color_engine
                cfg = get_kpi_color_engine().kpi_config(metric_key, metric_value, metric_prev)
                return cfg["color"]
            except Exception:
                pass
        return _VARIANT_ACCENT.get(variant, Colors.PRIMARY.BASE)

    @staticmethod
    def _resolve_tendencia(metric_key, metric_value, metric_prev) -> str:
        if not metric_prev:
            return ""
        try:
            from core.services.kpi_color_engine import get_kpi_color_engine
            cfg = get_kpi_color_engine().kpi_config(metric_key, metric_value, metric_prev)
            return cfg.get("tendencia", "")
        except Exception:
            return ""

    def _set_tendencia_text(self, text: str) -> None:
        """Actualiza la pill de tendencia. Detecta signo desde el texto (+/-/↑/↓)."""
        if not text:
            self.lbl_tendencia.setText("")
            self.lbl_tendencia.setVisible(False)
            return
        # Determinar color por signo
        is_positive = ("↑" in text) or text.lstrip().startswith("+")
        is_negative = ("↓" in text) or text.lstrip().startswith("-")
        if is_positive:
            color, bg = Colors.SUCCESS.BASE, Colors.SUCCESS.BG_SOFT
        elif is_negative:
            color, bg = Colors.DANGER.BASE, Colors.DANGER.BG_SOFT
        else:
            color, bg = Colors.NEUTRAL.SLATE_500, Colors.NEUTRAL.SLATE_100
        self.lbl_tendencia.setText(text)
        self.lbl_tendencia.setStyleSheet(
            f"color: {color}; background-color: {bg};"
            f" font-size: {Typography.SIZE_XS};"
            f" font-weight: {Typography.WEIGHT_SEMIBOLD};"
            f" border-radius: {Borders.RADIUS_FULL}px;"
            f" padding: 2px 8px; border: none;"
        )
        self.lbl_tendencia.setVisible(True)

    # ── API pública ────────────────────────────────────────────────────────
    def set_valor(self, valor: str):
        self.lbl_valor.setText(valor)

    def set_estado(self, metric_value: float, metric_prev: float = 0) -> None:
        """Actualiza accent bar + tendencia delegando a KPIColorEngine."""
        if not self._metric_key:
            return
        try:
            from core.services.kpi_color_engine import get_kpi_color_engine
            cfg = get_kpi_color_engine().kpi_config(self._metric_key, metric_value, metric_prev)
            _color = cfg["color"]
            self._current_color = _color
            self._accent_bar.setStyleSheet(
                f"background-color: {_color};"
                f" border-top-left-radius: {Borders.RADIUS_LG}px;"
                f" border-top-right-radius: {Borders.RADIUS_LG}px;"
                f" border: none;"
            )
            self._set_tendencia_text(cfg.get("tendencia", ""))
        except Exception:
            pass

    def mousePressEvent(self, event):
        self.clicked.emit(self._key)
        super().mousePressEvent(event)


_ALERTA_VARIANT = {
    # tipo: (bg_soft, accent, icon)
    "danger":  (Colors.DANGER.BG_SOFT,  Colors.DANGER.BASE,  "🔴"),
    "warning": (Colors.WARNING.BG_SOFT, Colors.WARNING.BASE, "⚠️"),
    "success": (Colors.SUCCESS.BG_SOFT, Colors.SUCCESS.BASE, "✅"),
    "info":    (Colors.PRIMARY.LIGHT,   Colors.PRIMARY.BASE, "ℹ️"),
}

_PEDIDO_BADGE_COLOR = {
    "nuevo":      Colors.DANGER.BASE,
    "confirmado": Colors.PRIMARY.BASE,
    "pesando":    Colors.WARNING.BASE,
    "listo":      Colors.SUCCESS.BASE,
}


class AlertaItem(QFrame):
    """Item de alerta con border-left de color según severidad.

    Estilos via tokens; antes usaba var(--xxx) que Qt QSS no soporta y
    los estilos no se aplicaban (caía a defaults).
    """
    def __init__(self, texto: str, tipo: str = "info", parent=None):
        super().__init__(parent)
        bg, accent, icon = _ALERTA_VARIANT.get(tipo, _ALERTA_VARIANT["info"])
        self.setObjectName("alertaItem")
        self.setStyleSheet(
            f"QFrame#alertaItem {{"
            f"  background: {bg};"
            f"  border-radius: {Borders.RADIUS_LG}px;"
            f"  border: 1px solid {accent}33;"  # alpha 20%
            f"  border-left: 4px solid {accent};"
            f"}}"
            f"QFrame#alertaItem QLabel {{"
            f"  background: transparent; border: none;"
            f"  color: {Colors.NEUTRAL.SLATE_900};"
            f"  font-size: {Typography.SIZE_MD};"
            f"}}"
        )
        lyt = QHBoxLayout(self)
        lyt.setContentsMargins(10, 8, 10, 8)
        lbl = QLabel(f"{icon}  {texto}", self)
        lbl.setWordWrap(True)
        lyt.addWidget(lbl)


class PedidoWAItem(QFrame):
    """Tarjeta de pedido WhatsApp pendiente.

    Estilos via tokens (antes con var(--xxx) inutilizables en Qt QSS).
    """
    ver_pedido = pyqtSignal(int)

    def __init__(self, pedido: dict, parent=None):
        super().__init__(parent)
        pid = pedido.get("id", 0)

        self.setObjectName("pedidoWAItem")
        self.setStyleSheet(
            f"QFrame#pedidoWAItem {{"
            f"  background: {Colors.NEUTRAL.WHITE};"
            f"  border-radius: {Borders.RADIUS_LG}px;"
            f"  border: 1px solid {Colors.NEUTRAL.SLATE_200};"
            f"}}"
            f"QFrame#pedidoWAItem:hover {{"
            f"  border-color: {Colors.PRIMARY.BASE};"
            f"}}"
            f"QFrame#pedidoWAItem QLabel {{"
            f"  background: transparent; border: none;"
            f"  color: {Colors.NEUTRAL.SLATE_900};"
            f"}}"
        )
        lyt = QVBoxLayout(self)
        lyt.setContentsMargins(12, 10, 12, 10)
        lyt.setSpacing(4)

        top = QHBoxLayout()
        lbl_id = QLabel(f"📲 Pedido #{pid}", self)
        lbl_id.setStyleSheet(
            f"font-weight: {Typography.WEIGHT_BOLD};"
            f" font-size: {Typography.SIZE_LG};"
            f" background: transparent; border: none;"
        )
        top.addWidget(lbl_id)
        top.addStretch()

        estado = pedido.get("estado", "nuevo")
        badge_color = _PEDIDO_BADGE_COLOR.get(estado, Colors.NEUTRAL.SLATE_500)
        badge = QLabel(estado.upper(), self)
        badge.setStyleSheet(
            f"background: {badge_color}; color: white;"
            f" padding: 3px 8px;"
            f" border-radius: {Borders.RADIUS_MD}px;"
            f" font-size: {Typography.SIZE_XS};"
            f" font-weight: {Typography.WEIGHT_SEMIBOLD};"
            f" border: none;"
        )
        top.addWidget(badge)
        lyt.addLayout(top)

        lbl_cliente = QLabel(pedido.get("cliente_nombre", "—"), self)
        lbl_cliente.setStyleSheet(
            f"font-size: {Typography.SIZE_MD};"
            f" color: {Colors.NEUTRAL.SLATE_700};"
            f" background: transparent; border: none;"
        )
        lyt.addWidget(lbl_cliente)

        lbl_resumen = QLabel(
            f"${float(pedido.get('total', 0)):.2f}  ·  "
            f"{pedido.get('tipo_entrega', 'mostrador')}",
            self,
        )
        lbl_resumen.setStyleSheet(
            f"font-size: {Typography.SIZE_SM};"
            f" color: {Colors.NEUTRAL.SLATE_500};"
            f" background: transparent; border: none;"
        )
        lyt.addWidget(lbl_resumen)

        btn = QPushButton("Ver detalle →", self)
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
        # Sin background hardcodeado — el QSS global controla colores por tema.

        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(16, 12, 16, 12)

        # ── Header (PageHeader reutilizable) ─────────────────────────
        self._page_header = PageHeader(
            self,
            title="📊 Dashboard SPJ POS",
            subtitle="Resumen operativo en tiempo real",
            with_separator=True,
        )
        self.lbl_hora = QLabel("", self)
        self.lbl_hora.setObjectName("dashboardTime")
        self.lbl_hora.setStyleSheet(
            f"color: {Colors.NEUTRAL.SLATE_500};"
            f" font-size: {Typography.SIZE_SM};"
            f" background: transparent; border: none;"
        )
        self._page_header.add_action(self.lbl_hora)
        root.addWidget(self._page_header)

        # ── Cuerpo ───────────────────────────────────────────────────
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(12)

        # Columna izquierda (KPIs + pedidos WA)
        left = QVBoxLayout()
        left.setSpacing(12)

        # KPIs en grid 4 columnas (4x2 = 8 KPIs)
        # Cada KPI tiene una metric_key conocida por KPIColorEngine para
        # resolver el color del semáforo según umbrales del negocio.
        kpi_grid = QGridLayout()
        kpi_grid.setSpacing(10)
        self._kpis = {
            "ventas_hoy":    KPICard("Ventas hoy",     "$0",  icono="💰", key="ventas",            metric_key="ventas",           variant="primary"),
            "tickets_hoy":   KPICard("Tickets",        "0",   icono="🧾", key="ventas",            metric_key="ventas",           variant="success"),
            "ticket_prom":   KPICard("Ticket promedio","$0",  icono="📊", key="ventas",            metric_key="ticket_promedio",  variant="info"),
            "clientes_hoy":  KPICard("Clientes hoy",   "0",   icono="👥", key="clientes",          metric_key="clientes",         variant="primary"),
            "margen_hoy":    KPICard("Margen bruto",   "0%",  icono="📈", key="reportes",          metric_key="margen_bruto",     variant="success"),
            "vs_ayer":       KPICard("vs Ayer",        "—",   icono="⏱️", key="reportes",          metric_key="ventas",           variant="warning"),
            "pedidos_wa":    KPICard("Pedidos WA",     "0",   icono="📲", key="pedidos_whatsapp",  metric_key="pedidos_whatsapp", variant="info"),
            "productos_bajo":KPICard("Stock bajo",     "0",   icono="⚠️",  key="inventario",        metric_key="inventario",       variant="warning"),
        }
        for i, (_key, card) in enumerate(self._kpis.items()):
            card.clicked.connect(self.abrir_modulo)
            kpi_grid.addWidget(card, i // 4, i % 4)  # 4 columnas
        # Distribuir las 4 columnas equitativamente
        for col in range(4):
            kpi_grid.setColumnStretch(col, 1)
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
            self._kpis["margen_hoy"].set_valor(f"{margen:.1f}%")
            # set_estado pinta accent bar + tendencia delegando a KPIColorEngine
            self._kpis["margen_hoy"].set_estado(margen)
        except Exception: pass

        # ── Comparativo vs ayer ───────────────────────────────────────────────
        try:
            ayer = float(self.conn.execute("""
                SELECT COALESCE(SUM(total),0) FROM ventas
                WHERE DATE(fecha)=DATE('now','-1 day') AND estado='completada'""").fetchone()[0])
            if ayer > 0:
                delta = ((ventas_hoy - ayer) / ayer * 100)
                sign  = "↑ +" if delta >= 0 else "↓ "
                self._kpis["vs_ayer"].set_valor(f"{sign}{delta:.1f}%")
                # Pasar el delta a set_estado para que la pill se coloree
                self._kpis["vs_ayer"].set_estado(ventas_hoy, ayer)
            else:
                self._kpis["vs_ayer"].set_valor("—")
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

    # ── Estado de sesión (consumido por main_window via hasattr) ───────────
    def set_sucursal(self, sucursal_id: int, nombre: str = "") -> None:
        """Cambia la sucursal activa y refresca KPIs filtrados."""
        self.sucursal_id = sucursal_id
        self._nombre_sucursal = nombre
        if nombre:
            self._page_header.set_subtitle(f"Resumen operativo · {nombre}")
        try:
            self.actualizar()
        except Exception as e:
            logger.debug("set_sucursal refresh: %s", e)

    def set_usuario_actual(self, usuario: str, rol: str = "") -> None:
        """Almacena el usuario activo (afecta filtrado por rol en KPIs)."""
        self.usuario_actual = usuario
        self.rol_actual = rol.lower() if rol else "cajero"
        try:
            self.actualizar()
        except Exception as e:
            logger.debug("set_usuario_actual refresh: %s", e)

    def set_sesion(self, usuario: str, rol: str) -> None:
        """Compatibilidad legacy — delega a set_usuario_actual."""
        self.set_usuario_actual(usuario, rol)


class DashboardWidget(Dashboard):
    """Alias de Dashboard para compatibilidad con main_window.py."""
    pass
