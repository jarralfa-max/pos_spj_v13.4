
# ui/dashboard.py — SPJ POS v13.4
"""
Dashboard principal del POS en tiempo real.
  - KPIs del día: ventas, tickets, ticket promedio, margen, clientes
  - Cola de pedidos WhatsApp pendientes
  - Alertas de stock bajo y lotes por caducar
  - Feed de actividad reciente
  - Estado de repartidores activos
  - Acceso rápido a módulos clave

Enterprise UI v13.5 — modular, touch-first, operational clarity.
Hero KPIs · Activity Feed · Quick Actions · Compact Alerts
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

from modulos.design_tokens import Colors, Spacing, Typography, Borders, Shadows
from modulos.ui_components import (
    LoadingIndicator, EmptyStateWidget, PageHeader,
)

logger = logging.getLogger("spj.ui.dashboard")

# ── Semantic color maps ──────────────────────────────────────────────────────

_VARIANT_ACCENT = {
    "primary": Colors.PRIMARY.BASE,
    "success": Colors.SUCCESS.BASE,
    "danger":  Colors.DANGER.BASE,
    "warning": Colors.WARNING.BASE,
    "info":    Colors.INFO.BASE,
}

_ALERTA_VARIANT = {
    "danger":  (Colors.DANGER.BG_SOFT,  Colors.DANGER.BASE,  "●"),
    "warning": (Colors.WARNING.BG_SOFT, Colors.WARNING.BASE, "▲"),
    "success": (Colors.SUCCESS.BG_SOFT, Colors.SUCCESS.BASE, "✓"),
    "info":    (Colors.PRIMARY.LIGHT,   Colors.PRIMARY.BASE, "i"),
}

_PEDIDO_BADGE_COLOR = {
    "nuevo":      Colors.DANGER.BASE,
    "confirmado": Colors.PRIMARY.BASE,
    "pesando":    Colors.WARNING.BASE,
    "listo":      Colors.SUCCESS.BASE,
}

_ACTIVITY_ICON = {
    "venta":   ("💰", Colors.SUCCESS.BASE),
    "pedido":  ("📲", Colors.PRIMARY.BASE),
    "alerta":  ("⚠️",  Colors.WARNING.BASE),
    "sistema": ("⚙️",  Colors.INFO.BASE),
    "stock":   ("📦", Colors.DANGER.BASE),
}

# ── Low-level helpers ────────────────────────────────────────────────────────




def _add_shadow(widget: QWidget, blur: int = 20, dy: int = 3, alpha: int = 40) -> None:
    eff = QGraphicsDropShadowEffect(widget)
    eff.setBlurRadius(blur)
    eff.setOffset(0, dy)
    eff.setColor(QColor(0, 0, 0, alpha))
    widget.setGraphicsEffect(eff)


def _section_label(text: str, parent=None) -> QLabel:
    lbl = QLabel(text.upper(), parent)
    lbl.setObjectName("sectionLabel")
    lbl.setStyleSheet(
        f"color: {Colors.NEUTRAL.SLATE_500};"
        f" font-size: {Typography.SIZE_XS};"
        f" font-weight: {Typography.WEIGHT_SEMIBOLD};"
        f" letter-spacing: 0.1em;"
        f" background: transparent; border: none;"
    )
    return lbl


def _divider(parent=None) -> QFrame:
    line = QFrame(parent)
    line.setFrameShape(QFrame.HLine)
    line.setFixedHeight(1)
    line.setStyleSheet(f"background-color: rgba(255,255,255,10); border: none;")
    return line


# ── KPICard ──────────────────────────────────────────────────────────────────

class KPICard(QFrame):
    """
    Tarjeta KPI: accent bar superior, sombra, delta opcional.

    hero=True → tarjeta grande (hero section), valor 28 px, padding mayor.
    hero=False → tarjeta compacta (secondary grid), valor 22 px.

    API pública preservada (backward compat):
        clicked: pyqtSignal(str)
        set_valor(str)
        set_estado(value, prev)
    """
    clicked = pyqtSignal(str)

    def __init__(
        self,
        titulo: str,
        valor: str = "—",
        color: str = "",
        icono: str = "📊",
        key: str = "",
        metric_key: str = "",
        metric_value: float = 0,
        metric_prev: float = 0,
        tendencia: str = "",
        variant: str = "primary",
        hero: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self._key = key
        self._metric_key = metric_key
        self._variant = variant
        self._hero = hero

        accent = self._resolve_accent(metric_key, metric_value, metric_prev, variant)
        if metric_key and not tendencia:
            tendencia = self._resolve_tendencia(metric_key, metric_value, metric_prev)
        self._current_color = accent

        self.setObjectName("kpiCard")
        self.setProperty("variant", variant)
        self.setProperty("hero", "true" if hero else "false")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(126 if hero else 90)

        _add_shadow(self, blur=24 if hero else 14, dy=4 if hero else 2, alpha=45 if hero else 28)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Accent bar
        self._accent_bar = QFrame(self)
        self._accent_bar.setFixedHeight(4 if hero else 3)
        self._accent_bar.setStyleSheet(
            f"background-color: {accent};"
            f" border-top-left-radius: {Borders.RADIUS_XL}px;"
            f" border-top-right-radius: {Borders.RADIUS_XL}px;"
            f" border: none;"
        )
        outer.addWidget(self._accent_bar)

        # Body
        body = QHBoxLayout()
        h_pad = Spacing.XL if hero else Spacing.LG
        v_pad = 14 if hero else 10
        body.setContentsMargins(h_pad, v_pad, h_pad, v_pad)
        body.setSpacing(Spacing.MD)
        outer.addLayout(body)

        text_col = QVBoxLayout()
        text_col.setSpacing(3)

        lbl_titulo = QLabel(titulo.upper(), self)
        lbl_titulo.setStyleSheet(
            f"color: {Colors.NEUTRAL.SLATE_500};"
            f" font-size: {Typography.SIZE_XS};"
            f" font-weight: {Typography.WEIGHT_SEMIBOLD};"
            f" letter-spacing: 0.08em;"
            f" background: transparent; border: none;"
        )
        text_col.addWidget(lbl_titulo)

        val_size = "28px" if hero else "22px"
        self.lbl_valor = QLabel(valor, self)
        self.lbl_valor.setObjectName("kpiValue")
        self.lbl_valor.setStyleSheet(
            f"font-size: {val_size};"
            f" font-weight: {Typography.WEIGHT_BOLD};"
            f" letter-spacing: -0.02em;"
            f" background: transparent; border: none;"
        )
        text_col.addWidget(self.lbl_valor)

        self.lbl_tendencia = QLabel("", self)
        self.lbl_tendencia.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self._set_tendencia_text(tendencia)
        text_col.addWidget(self.lbl_tendencia, alignment=Qt.AlignLeft)

        body.addLayout(text_col, 1)

        # Icon badge
        icon_sz = 46 if hero else 36
        icon_font = "24px" if hero else "18px"
        lbl_icono = QLabel(icono, self)
        lbl_icono.setFixedSize(icon_sz, icon_sz)
        lbl_icono.setAlignment(Qt.AlignCenter)
        lbl_icono.setStyleSheet(
            f"font-size: {icon_font};"
            f" background-color: {accent}1A;"
            f" border-radius: {icon_sz // 2}px;"
            f" border: none;"
        )
        body.addWidget(lbl_icono, 0, alignment=Qt.AlignTop)

    # ── Color/trend resolution ────────────────────────────────────────────

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
        if not text:
            self.lbl_tendencia.setText("")
            self.lbl_tendencia.setVisible(False)
            return
        is_pos = ("↑" in text) or text.lstrip().startswith("+")
        is_neg = ("↓" in text) or text.lstrip().startswith("-")
        if is_pos:
            fg, bg = Colors.SUCCESS.BASE, Colors.SUCCESS.BG_SOFT
        elif is_neg:
            fg, bg = Colors.DANGER.BASE, Colors.DANGER.BG_SOFT
        else:
            fg, bg = Colors.NEUTRAL.SLATE_500, Colors.NEUTRAL.SLATE_100
        self.lbl_tendencia.setText(text)
        self.lbl_tendencia.setStyleSheet(
            f"color: {fg}; background-color: {bg};"
            f" font-size: {Typography.SIZE_XS};"
            f" font-weight: {Typography.WEIGHT_SEMIBOLD};"
            f" border-radius: {Borders.RADIUS_FULL}px;"
            f" padding: 2px 8px; border: none;"
        )
        self.lbl_tendencia.setVisible(True)

    # ── Public API ────────────────────────────────────────────────────────

    def set_valor(self, valor: str):
        self.lbl_valor.setText(valor)

    def set_estado(self, metric_value: float, metric_prev: float = 0) -> None:
        if not self._metric_key:
            return
        try:
            from core.services.kpi_color_engine import get_kpi_color_engine
            cfg = get_kpi_color_engine().kpi_config(
                self._metric_key, metric_value, metric_prev
            )
            _color = cfg["color"]
            self._current_color = _color
            self._accent_bar.setStyleSheet(
                f"background-color: {_color};"
                f" border-top-left-radius: {Borders.RADIUS_XL}px;"
                f" border-top-right-radius: {Borders.RADIUS_XL}px;"
                f" border: none;"
            )
            self._set_tendencia_text(cfg.get("tendencia", ""))
        except Exception:
            pass

    def mousePressEvent(self, event):
        self.clicked.emit(self._key)
        super().mousePressEvent(event)


# ── AlertaItem ───────────────────────────────────────────────────────────────

class AlertaItem(QFrame):
    """Compact alert card with left accent bar and severity icon."""

    def __init__(self, texto: str, tipo: str = "info", timestamp: str = "", parent=None):
        super().__init__(parent)
        bg, accent, icon = _ALERTA_VARIANT.get(tipo, _ALERTA_VARIANT["info"])

        self.setObjectName("alertaItem")
        self.setStyleSheet(
            f"QFrame#alertaItem {{"
            f"  background: {bg};"
            f"  border-radius: {Borders.RADIUS_MD}px;"
            f"  border: 1px solid {accent}33;"
            f"  border-left: 4px solid {accent};"
            f"}}"
            f"QFrame#alertaItem QLabel {{"
            f"  background: transparent; border: none;"
            f"  font-size: {Typography.SIZE_SM};"
            f"}}"
        )

        lyt = QHBoxLayout(self)
        lyt.setContentsMargins(10, 7, 10, 7)
        lyt.setSpacing(8)

        lbl_icon = QLabel(icon, self)
        lbl_icon.setFixedWidth(14)
        lbl_icon.setStyleSheet(f"color: {accent}; font-size: 11px;")
        lyt.addWidget(lbl_icon, 0, alignment=Qt.AlignTop)

        col = QVBoxLayout()
        col.setSpacing(1)

        lbl_txt = QLabel(texto, self)
        lbl_txt.setWordWrap(True)
        lbl_txt.setStyleSheet(f"color: {Colors.NEUTRAL.SLATE_900};")
        col.addWidget(lbl_txt)

        if timestamp:
            lbl_ts = QLabel(timestamp, self)
            lbl_ts.setStyleSheet(
                f"color: {Colors.NEUTRAL.SLATE_500}; font-size: {Typography.SIZE_XS};"
            )
            col.addWidget(lbl_ts)

        lyt.addLayout(col, 1)


# ── PedidoWAItem ─────────────────────────────────────────────────────────────

class PedidoWAItem(QFrame):
    """Compact WhatsApp order card with status badge."""

    ver_pedido = pyqtSignal(int)

    def __init__(self, pedido: dict, parent=None):
        super().__init__(parent)
        pid = pedido.get("id", 0)

        self.setObjectName("pedidoWAItem")
        # Background/border/labels handled by global QSS (_block_dash_cards)

        lyt = QHBoxLayout(self)
        lyt.setContentsMargins(12, 9, 12, 9)
        lyt.setSpacing(10)

        # Left: icon
        lbl_icon = QLabel("📲", self)
        lbl_icon.setFixedSize(32, 32)
        lbl_icon.setAlignment(Qt.AlignCenter)
        lbl_icon.setStyleSheet(
            f"font-size: 16px;"
            f" background: {Colors.PRIMARY.BASE}1A;"
            f" border-radius: 16px; border: none;"
        )
        lyt.addWidget(lbl_icon, 0, alignment=Qt.AlignVCenter)

        # Center: info
        info = QVBoxLayout()
        info.setSpacing(1)

        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        lbl_id = QLabel(f"Pedido #{pid}", self)
        lbl_id.setStyleSheet(
            f"font-weight: {Typography.WEIGHT_SEMIBOLD};"
            f" font-size: {Typography.SIZE_MD};"
        )
        top_row.addWidget(lbl_id)

        estado = pedido.get("estado", "nuevo")
        badge_color = _PEDIDO_BADGE_COLOR.get(estado, Colors.NEUTRAL.SLATE_500)
        badge = QLabel(estado.upper(), self)
        badge.setStyleSheet(
            f"background: {badge_color}; color: white;"
            f" padding: 2px 7px;"
            f" border-radius: {Borders.RADIUS_MD}px;"
            f" font-size: {Typography.SIZE_XS};"
            f" font-weight: {Typography.WEIGHT_SEMIBOLD}; border: none;"
        )
        top_row.addWidget(badge)
        top_row.addStretch()

        total_txt = f"${float(pedido.get('total', 0)):,.0f}"
        lbl_total = QLabel(total_txt, self)
        lbl_total.setStyleSheet(
            f"font-weight: {Typography.WEIGHT_BOLD};"
            f" font-size: {Typography.SIZE_MD};"
            f" color: {Colors.SUCCESS.BASE};"
        )
        top_row.addWidget(lbl_total)

        info.addLayout(top_row)

        sub = QLabel(
            f"{pedido.get('cliente_nombre','—')}  ·  {pedido.get('tipo_entrega','mostrador')}",
            self,
        )
        sub.setStyleSheet(
            f"font-size: {Typography.SIZE_SM};"
            f" color: {Colors.NEUTRAL.SLATE_500};"
        )
        info.addWidget(sub)

        lyt.addLayout(info, 1)

        # Right: action
        btn = QPushButton("Ver →", self)
        btn.setObjectName("primaryBtn")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedWidth(56)
        btn.setToolTip(f"Ver detalles del pedido #{pid}")
        btn.clicked.connect(lambda: self.ver_pedido.emit(pid))
        lyt.addWidget(btn, 0, alignment=Qt.AlignVCenter)


# ── MiniGraficaVentas ─────────────────────────────────────────────────────────

class MiniGraficaVentas(QWidget):
    """
    7-day sales bar chart via QPainter.
    Today's bar: solid primary blue with gradient.
    Past bars: translucent blue.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._datos: list = []
        self.setMinimumHeight(140)
        self.setMaximumHeight(160)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setToolTip("Ventas de los últimos 7 días")

    def set_datos(self, datos: list) -> None:
        self._datos = datos
        self.update()

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainter, QBrush, QPen, QLinearGradient, QFont as _QF
        if not self._datos:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        W, H = self.width(), self.height()
        PAD_L, PAD_R, PAD_T, PAD_B = 8, 8, 24, 26
        chart_h = H - PAD_T - PAD_B

        values = [d[1] for d in self._datos]
        max_v = max(values) if max(values) > 0 else 1
        n = len(self._datos)
        total_w = W - PAD_L - PAD_R
        bar_w = total_w / (n * 1.6)
        gap = (total_w - bar_w * n) / (n + 1)

        BLUE_SOLID = QColor(37, 99, 235)
        BLUE_SOFT  = QColor(59, 130, 246, 70)
        TEXT_TODAY = QColor(226, 232, 240)
        TEXT_DIM   = QColor(100, 116, 139)

        for i, (label, val) in enumerate(self._datos):
            is_today = (i == n - 1)
            bar_h = max(int((val / max_v) * chart_h), 4)
            x = int(PAD_L + gap + i * (bar_w + gap))
            y = H - PAD_B - bar_h

            grad = QLinearGradient(x, y, x, H - PAD_B)
            if is_today:
                grad.setColorAt(0, QColor(37, 99, 235))
                grad.setColorAt(1, QColor(37, 99, 235, 30))
            else:
                grad.setColorAt(0, QColor(59, 130, 246, 75))
                grad.setColorAt(1, QColor(59, 130, 246, 10))

            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(x, y, int(bar_w), bar_h, 4, 4)

            if val > 0:
                val_str = f"${val/1000:.1f}k" if val >= 1000 else f"${val:.0f}"
                p.setPen(QPen(TEXT_TODAY if is_today else TEXT_DIM))
                p.setFont(_QF("Segoe UI", 7, 700 if is_today else 400))
                p.drawText(x, y - 16, int(bar_w), 14, Qt.AlignCenter, val_str)

            p.setPen(QPen(BLUE_SOLID if is_today else TEXT_DIM))
            p.setFont(_QF("Segoe UI", 8, 700 if is_today else 400))
            p.drawText(x, H - PAD_B + 6, int(bar_w), 16, Qt.AlignCenter, label)

        p.end()


# ── ActivityFeedItem ─────────────────────────────────────────────────────────

class ActivityFeedItem(QFrame):
    """Single row in the live activity feed."""

    def __init__(self, tipo: str, descripcion: str, monto: str = "",
                 hora: str = "", parent=None):
        super().__init__(parent)
        icon, color = _ACTIVITY_ICON.get(tipo, ("●", Colors.NEUTRAL.SLATE_500))

        self.setObjectName("actFeedItem")
        self.setStyleSheet(
            f"QFrame#actFeedItem {{"
            f"  background: transparent; border: none;"
            f"  border-bottom: 1px solid rgba(255,255,255,6);"
            f"}}"
            f"QFrame#actFeedItem QLabel {{ background: transparent; border: none; }}"
        )

        lyt = QHBoxLayout(self)
        lyt.setContentsMargins(0, 7, 0, 7)
        lyt.setSpacing(10)

        # Dot indicator
        dot = QLabel(icon, self)
        dot.setFixedWidth(20)
        dot.setAlignment(Qt.AlignCenter)
        dot.setStyleSheet(f"color: {color}; font-size: 10px;")
        lyt.addWidget(dot, 0, alignment=Qt.AlignVCenter)

        # Description
        lbl_desc = QLabel(descripcion, self)
        lbl_desc.setStyleSheet(
            f"font-size: {Typography.SIZE_SM}; color: {Colors.NEUTRAL.SLATE_100};"
        )
        lyt.addWidget(lbl_desc, 1)

        # Amount (right-aligned)
        if monto:
            lbl_monto = QLabel(monto, self)
            lbl_monto.setStyleSheet(
                f"font-size: {Typography.SIZE_SM};"
                f" font-weight: {Typography.WEIGHT_SEMIBOLD};"
                f" color: {Colors.SUCCESS.BASE};"
            )
            lyt.addWidget(lbl_monto, 0, alignment=Qt.AlignVCenter)

        # Timestamp
        if hora:
            lbl_hora = QLabel(hora, self)
            lbl_hora.setFixedWidth(44)
            lbl_hora.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            lbl_hora.setStyleSheet(
                f"font-size: {Typography.SIZE_XS};"
                f" color: {Colors.NEUTRAL.SLATE_500};"
            )
            lyt.addWidget(lbl_hora)


def _make_quick_action_btn(icono: str, label: str, accent: str, parent=None) -> QPushButton:
    """
    Native QPushButton styled as a touch-friendly action card.
    QPushButton.clicked is the only reliable click mechanism on QFrame children.
    """
    btn = QPushButton(f"{icono}  {label}", parent)
    btn.setObjectName("quickActionBtn")
    btn.setCursor(Qt.PointingHandCursor)
    btn.setMinimumHeight(72)
    btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    # Per-button accent hover only — base card style comes from global QSS
    btn.setStyleSheet(
        f"QPushButton#quickActionBtn:hover {{"
        f"  background-color: {accent}1A;"
        f"  border-color: {accent}55;"
        f"}}"
    )
    return btn


# ── DriverCard ────────────────────────────────────────────────────────────────

class DriverCard(QFrame):
    """Compact driver status card."""

    def __init__(self, nombre: str, en_ruta: bool, pedidos: int, parent=None):
        super().__init__(parent)
        self.setObjectName("driverCard")
        self.setStyleSheet(
            f"QFrame#driverCard {{"
            f"  background: transparent;"
            f"  border: none;"
            f"  border-bottom: 1px solid rgba(255,255,255,6);"
            f"}}"
            f"QFrame#driverCard QLabel {{ background: transparent; border: none; }}"
        )

        lyt = QHBoxLayout(self)
        lyt.setContentsMargins(0, 7, 0, 7)
        lyt.setSpacing(8)

        # Status dot
        dot_color = Colors.SUCCESS.BASE if en_ruta else Colors.NEUTRAL.SLATE_500
        dot = QLabel("●", self)
        dot.setStyleSheet(f"color: {dot_color}; font-size: 9px;")
        lyt.addWidget(dot, 0, alignment=Qt.AlignVCenter)

        # Name
        lbl_nom = QLabel(nombre, self)
        lbl_nom.setStyleSheet(
            f"font-size: {Typography.SIZE_SM};"
            f" color: {Colors.NEUTRAL.SLATE_100};"
        )
        lyt.addWidget(lbl_nom, 1)

        # Status text
        status_txt = "En ruta" if en_ruta else "Disponible"
        lbl_status = QLabel(status_txt, self)
        lbl_status.setStyleSheet(
            f"font-size: {Typography.SIZE_XS};"
            f" color: {dot_color};"
            f" font-weight: {Typography.WEIGHT_SEMIBOLD};"
        )
        lyt.addWidget(lbl_status, 0, alignment=Qt.AlignVCenter)

        # Pedidos count
        if pedidos > 0:
            lbl_p = QLabel(f"{pedidos}", self)
            lbl_p.setFixedSize(20, 20)
            lbl_p.setAlignment(Qt.AlignCenter)
            lbl_p.setStyleSheet(
                f"background: {Colors.PRIMARY.BASE}; color: white;"
                f" border-radius: 10px; font-size: {Typography.SIZE_XS};"
                f" font-weight: {Typography.WEIGHT_BOLD}; border: none;"
            )
            lyt.addWidget(lbl_p, 0, alignment=Qt.AlignVCenter)


# ── Dashboard ─────────────────────────────────────────────────────────────────

class Dashboard(QWidget):
    """Enterprise operational dashboard — SPJ POS v13.5."""

    abrir_modulo = pyqtSignal(str)

    def __init__(self, container_or_conn=None, parent=None):
        if hasattr(container_or_conn, "db"):
            conn = container_or_conn.db
            self._container = container_or_conn
        else:
            conn = container_or_conn
            self._container = None
        super().__init__(parent)
        self.conn = conn or get_connection()
        self._setup_ui()

        # 60s fallback timer
        self._timer = QTimer(self)
        self._timer.setInterval(60_000)
        self._timer.timeout.connect(self.actualizar)
        self._timer.start()

        # EventBus subscriptions
        try:
            from core.events.event_bus import get_bus, VENTA_COMPLETADA, STOCK_BAJO_MINIMO
            from PyQt5.QtCore import QTimer as _QT
            bus = get_bus()
            bus.subscribe(
                VENTA_COMPLETADA,
                lambda _p: _QT.singleShot(0, self.actualizar),
                label="dashboard.venta",
            )
            bus.subscribe(
                STOCK_BAJO_MINIMO,
                lambda _p: _QT.singleShot(0, self.actualizar),
                label="dashboard.stock_bajo",
            )
        except Exception as _e:
            logger.debug("EventBus dashboard: %s", _e)

        self.actualizar()

    # ── UI Construction ───────────────────────────────────────────────────────

    def _setup_ui(self):
        self.setObjectName("Dashboard")

        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # Outer scroll area — allows full-page scroll on smaller screens
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { width: 6px; background: transparent; }"
            "QScrollBar::handle:vertical { background: rgba(255,255,255,18);"
            " border-radius: 3px; min-height: 24px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        root.addWidget(scroll)

        inner = QWidget()
        inner.setObjectName("DashboardInner")
        scroll.setWidget(inner)

        layout = QVBoxLayout(inner)
        layout.setSpacing(Spacing.LG)
        layout.setContentsMargins(Spacing.XL, Spacing.LG, Spacing.XL, Spacing.XL)

        # 1. Header
        layout.addWidget(self._build_header())

        # 2. Hero KPIs (ventas + margen)
        layout.addWidget(self._build_hero_kpis())

        # 3. Secondary KPI grid (6 cards, 3 cols × 2 rows)
        layout.addWidget(self._build_secondary_kpis())

        # 4. Body: left (chart + WA queue) + right (actions + alerts + delivery)
        body = QHBoxLayout()
        body.setSpacing(Spacing.LG)

        body.addWidget(self._build_left_column(), 3)
        body.addWidget(self._build_right_column(), 2)

        layout.addLayout(body)
        layout.addStretch()

    # ── Section builders ──────────────────────────────────────────────────────

    def _build_header(self) -> QWidget:
        container = QWidget(self)
        lyt = QHBoxLayout(container)
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.setSpacing(Spacing.MD)

        # Title block
        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        lbl_title = QLabel("Dashboard Operativo", self)
        lbl_title.setStyleSheet(
            f"font-size: 20px;"
            f" font-weight: {Typography.WEIGHT_BOLD};"
            f" letter-spacing: -0.01em;"
            f" background: transparent; border: none;"
        )
        title_col.addWidget(lbl_title)

        self._lbl_subtitle = QLabel("Resumen en tiempo real", self)
        self._lbl_subtitle.setStyleSheet(
            f"font-size: {Typography.SIZE_MD};"
            f" color: {Colors.NEUTRAL.SLATE_500};"
            f" background: transparent; border: none;"
        )
        title_col.addWidget(self._lbl_subtitle)

        lyt.addLayout(title_col, 1)

        # System status
        self._status_dot = QLabel("● En línea", self)
        self._status_dot.setStyleSheet(
            f"color: {Colors.SUCCESS.BASE};"
            f" font-size: {Typography.SIZE_SM};"
            f" font-weight: {Typography.WEIGHT_SEMIBOLD};"
            f" background: transparent; border: none;"
        )
        lyt.addWidget(self._status_dot, 0, alignment=Qt.AlignVCenter)

        # Clock
        self.lbl_hora = QLabel("", self)
        self.lbl_hora.setObjectName("dashboardTime")
        self.lbl_hora.setStyleSheet(
            f"color: {Colors.NEUTRAL.SLATE_500};"
            f" font-size: {Typography.SIZE_SM};"
            f" background: transparent; border: none;"
        )
        lyt.addWidget(self.lbl_hora, 0, alignment=Qt.AlignVCenter)

        # Keep PageHeader reference for backward compat with set_subtitle
        self._page_header = _PageHeaderCompat(self._lbl_subtitle)

        return container

    def _build_hero_kpis(self) -> QWidget:
        container = QWidget(self)
        lyt = QHBoxLayout(container)
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.setSpacing(Spacing.LG)

        hero_ventas = KPICard(
            "Ventas hoy", "$0",
            icono="💰", key="ventas",
            metric_key="ventas", variant="primary",
            hero=True,
        )
        hero_ventas.clicked.connect(self.abrir_modulo)

        hero_margen = KPICard(
            "Margen bruto", "0%",
            icono="📈", key="reportes",
            metric_key="margen_bruto", variant="success",
            hero=True,
        )
        hero_margen.clicked.connect(self.abrir_modulo)

        lyt.addWidget(hero_ventas)
        lyt.addWidget(hero_margen)

        # Store in _kpis for update methods
        self._kpis = {
            "ventas_hoy":  hero_ventas,
            "margen_hoy":  hero_margen,
        }

        return container

    def _build_secondary_kpis(self) -> QWidget:
        container = QWidget(self)
        grid = QGridLayout(container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(Spacing.MD)

        secondary = [
            ("tickets_hoy",    "Tickets",         "0",  "🧾", "ventas",           "ventas",           "success"),
            ("ticket_prom",    "Ticket promedio",  "$0", "📊", "ventas",           "ticket_promedio",  "info"),
            ("clientes_hoy",   "Clientes hoy",     "0",  "👥", "clientes",         "clientes",         "primary"),
            ("vs_ayer",        "vs Ayer",           "—",  "⏱️", "reportes",         "ventas",           "warning"),
            ("pedidos_wa",     "Pedidos WA",        "0",  "📲", "pedidos_whatsapp", "pedidos_whatsapp", "info"),
            ("productos_bajo", "Stock bajo",        "0",  "⚠️", "inventario",       "inventario",       "warning"),
        ]

        for i, (key, titulo, valor, icono, nav_key, metric_k, var) in enumerate(secondary):
            card = KPICard(
                titulo, valor,
                icono=icono, key=nav_key,
                metric_key=metric_k, variant=var,
            )
            card.clicked.connect(self.abrir_modulo)
            self._kpis[key] = card
            grid.addWidget(card, i // 3, i % 3)

        for col in range(3):
            grid.setColumnStretch(col, 1)

        return container

    def _build_left_column(self) -> QWidget:
        container = QWidget(self)
        lyt = QVBoxLayout(container)
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.setSpacing(Spacing.LG)

        # Chart card
        chart_card = QFrame(self)
        chart_card.setObjectName("dashChartCard")
        _add_shadow(chart_card)

        chart_lyt = QVBoxLayout(chart_card)
        chart_lyt.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        chart_lyt.setSpacing(Spacing.MD)

        chart_header = QHBoxLayout()
        chart_header.addWidget(_section_label("Ventas — últimos 7 días"))
        chart_header.addStretch()
        chart_lyt.addLayout(chart_header)

        self._grafica = MiniGraficaVentas(chart_card)
        chart_lyt.addWidget(self._grafica)

        lyt.addWidget(chart_card)

        # Activity feed card
        lyt.addWidget(self._build_activity_card())

        # WA Queue card
        lyt.addWidget(self._build_wa_queue_card())

        return container

    def _build_activity_card(self) -> QFrame:
        card = QFrame(self)
        card.setObjectName("dashActCard")
        _add_shadow(card)

        lyt = QVBoxLayout(card)
        lyt.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        lyt.setSpacing(Spacing.SM)

        hdr = QHBoxLayout()
        hdr.addWidget(_section_label("Actividad reciente"))
        hdr.addStretch()
        lyt.addLayout(hdr)

        lyt.addWidget(_divider(card))

        self._lyt_actividad = QVBoxLayout()
        self._lyt_actividad.setSpacing(0)
        lyt.addLayout(self._lyt_actividad)

        self._empty_actividad = QLabel("Sin actividad reciente hoy.", card)
        self._empty_actividad.setStyleSheet(
            f"color: {Colors.NEUTRAL.SLATE_500}; font-size: {Typography.SIZE_SM};"
            f" padding: 12px 0;"
        )
        self._empty_actividad.hide()
        lyt.addWidget(self._empty_actividad)

        return card

    def _build_wa_queue_card(self) -> QFrame:
        card = QFrame(self)
        card.setObjectName("dashWACard")
        _add_shadow(card)

        lyt = QVBoxLayout(card)
        lyt.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        lyt.setSpacing(Spacing.SM)

        hdr = QHBoxLayout()
        hdr.addWidget(_section_label("Cola WhatsApp"))
        hdr.addStretch()

        btn_wa = QPushButton("Ver todos →", card)
        btn_wa.setObjectName("secondaryBtn")
        btn_wa.setCursor(Qt.PointingHandCursor)
        btn_wa.clicked.connect(lambda: self.abrir_modulo.emit("pedidos_whatsapp"))
        hdr.addWidget(btn_wa)
        lyt.addLayout(hdr)

        lyt.addWidget(_divider(card))

        scroll = QScrollArea(card)
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(160)
        scroll.setMaximumHeight(240)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { width: 4px; background: transparent; }"
            "QScrollBar::handle:vertical { background: rgba(255,255,255,20);"
            " border-radius: 2px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )

        self._container_wa = QWidget()
        self._lyt_wa = QVBoxLayout(self._container_wa)
        self._lyt_wa.setSpacing(6)
        self._lyt_wa.setContentsMargins(0, 4, 0, 4)
        self._lyt_wa.addStretch()
        scroll.setWidget(self._container_wa)
        lyt.addWidget(scroll)

        self._loading_wa = LoadingIndicator("Cargando pedidos WA…", card)
        self._loading_wa.hide()
        lyt.addWidget(self._loading_wa)

        self._empty_wa = EmptyStateWidget(
            "Sin pedidos pendientes",
            "No hay pedidos de WhatsApp en cola.",
            "✅",
            card,
        )
        self._empty_wa.hide()
        lyt.addWidget(self._empty_wa)

        # Keep scroll reference for legacy compat
        self._scroll_wa = scroll
        return card

    def _build_right_column(self) -> QWidget:
        container = QWidget(self)
        lyt = QVBoxLayout(container)
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.setSpacing(Spacing.LG)

        # Quick actions
        lyt.addWidget(self._build_quick_actions_card())

        # Alerts
        lyt.addWidget(self._build_alerts_card())

        # Delivery
        lyt.addWidget(self._build_delivery_card())

        return container

    def _build_quick_actions_card(self) -> QFrame:
        card = QFrame(self)
        card.setObjectName("dashQACard")
        _add_shadow(card)

        lyt = QVBoxLayout(card)
        lyt.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        lyt.setSpacing(Spacing.MD)

        lyt.addWidget(_section_label("Acciones rápidas"))
        lyt.addWidget(_divider(card))

        actions = [
            ("🛒", "Nueva Venta",  "ventas",           Colors.PRIMARY.BASE),
            ("📦", "Inventario",   "inventario",        Colors.INFO.BASE),
            ("💳", "Abrir Caja",   "caja",              Colors.SUCCESS.BASE),
            ("📲", "WhatsApp",     "pedidos_whatsapp",  Colors.SUCCESS.BASE),
            ("🚚", "Delivery",     "delivery",          Colors.WARNING.BASE),
            ("📊", "Reportes",     "reportes",          Colors.PRIMARY.BASE),
        ]

        grid = QGridLayout()
        grid.setSpacing(Spacing.SM)

        for i, (icon, label, key, color) in enumerate(actions):
            btn = _make_quick_action_btn(icon, label, color, parent=card)
            btn.clicked.connect(lambda _checked=False, k=key: self.abrir_modulo.emit(k))
            grid.addWidget(btn, i // 2, i % 2)

        lyt.addLayout(grid)
        return card

    def _build_alerts_card(self) -> QFrame:
        card = QFrame(self)
        card.setObjectName("dashAlertCard")
        _add_shadow(card)

        lyt = QVBoxLayout(card)
        lyt.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        lyt.setSpacing(Spacing.SM)

        hdr = QHBoxLayout()
        hdr.addWidget(_section_label("Alertas"))
        self._lbl_alerts_count = QLabel("", card)
        self._lbl_alerts_count.setStyleSheet(
            f"color: {Colors.DANGER.BASE};"
            f" font-size: {Typography.SIZE_XS};"
            f" font-weight: {Typography.WEIGHT_BOLD};"
        )
        hdr.addWidget(self._lbl_alerts_count)
        hdr.addStretch()
        lyt.addLayout(hdr)

        lyt.addWidget(_divider(card))

        scroll = QScrollArea(card)
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(120)
        scroll.setMaximumHeight(200)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { width: 4px; background: transparent; }"
            "QScrollBar::handle:vertical { background: rgba(255,255,255,20);"
            " border-radius: 2px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )

        self._container_alertas = QWidget()
        self._lyt_alertas = QVBoxLayout(self._container_alertas)
        self._lyt_alertas.setSpacing(4)
        self._lyt_alertas.setContentsMargins(0, 2, 0, 2)
        self._lyt_alertas.addStretch()
        scroll.setWidget(self._container_alertas)
        lyt.addWidget(scroll)

        self._loading_alertas = LoadingIndicator("Cargando alertas…", card)
        self._loading_alertas.hide()
        lyt.addWidget(self._loading_alertas)

        self._empty_alertas = EmptyStateWidget(
            "Sin alertas",
            "Sistema operando normalmente.",
            "✅",
            card,
        )
        self._empty_alertas.hide()
        lyt.addWidget(self._empty_alertas)

        self._scroll_alertas = scroll
        return card

    def _build_delivery_card(self) -> QFrame:
        card = QFrame(self)
        card.setObjectName("dashDelivCard")
        _add_shadow(card)

        lyt = QVBoxLayout(card)
        lyt.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        lyt.setSpacing(Spacing.SM)

        lyt.addWidget(_section_label("Repartidores"))
        lyt.addWidget(_divider(card))

        self._lyt_drivers = QVBoxLayout()
        self._lyt_drivers.setSpacing(0)
        lyt.addLayout(self._lyt_drivers)

        # Legacy label kept for backward compat (set by _actualizar_repartidores fallback)
        self._lbl_reps = QLabel("", card)
        self._lbl_reps.setWordWrap(True)
        self._lbl_reps.setObjectName("repartidorStatus")
        self._lbl_reps.hide()
        lyt.addWidget(self._lbl_reps)

        return card

    # ── Data refresh ──────────────────────────────────────────────────────────

    def actualizar(self):
        self.lbl_hora.setText(datetime.now().strftime("%d/%m/%Y  %H:%M"))
        self._actualizar_kpis()
        self._actualizar_grafica()
        self._actualizar_actividad()
        self._actualizar_pedidos_wa()
        self._actualizar_alertas()
        self._actualizar_repartidores()

    def _actualizar_grafica(self) -> None:
        DIAS_ES = ["L", "M", "X", "J", "V", "S", "D"]
        datos = []
        try:
            rows = self.conn.execute("""
                SELECT DATE('now', printf('-%d days', 6-seq)) AS dia,
                       COALESCE(SUM(v.total), 0) AS total
                FROM (SELECT 0 AS seq UNION SELECT 1 UNION SELECT 2
                      UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 UNION SELECT 6) d
                LEFT JOIN ventas v
                    ON DATE(v.fecha) = DATE('now', printf('-%d days', 6-d.seq))
                   AND v.estado = 'completada'
                GROUP BY dia
                ORDER BY dia
            """).fetchall()
            for row in rows:
                try:
                    import datetime as _dt
                    d = _dt.date.fromisoformat(row[0])
                    etiqueta = DIAS_ES[d.weekday()]
                except Exception:
                    etiqueta = "?"
                datos.append((etiqueta, float(row[1])))
        except Exception as e:
            logger.debug("_actualizar_grafica: %s", e)
            datos = [(d, 0.0) for d in DIAS_ES]
        self._grafica.set_datos(datos)

    def _actualizar_kpis(self):
        ventas_hoy = tickets_hoy = 0.0

        # Ventas del día
        try:
            es_gerente = getattr(self, "rol_actual", "cajero") in (
                "admin", "administrador", "gerente"
            )
            suc_filter = (
                ""
                if es_gerente
                else f"AND sucursal_id={getattr(self,'sucursal_id',1)}"
            )
            row = self.conn.execute(f"""
                SELECT COALESCE(SUM(total),0), COUNT(*)
                FROM ventas WHERE DATE(fecha)=DATE('now') AND estado='completada'
                {suc_filter}
            """).fetchone()
            ventas_hoy  = float(row[0])
            tickets_hoy = int(row[1])
            self._kpis["ventas_hoy"].set_valor(f"${ventas_hoy:,.0f}")
            self._kpis["tickets_hoy"].set_valor(str(tickets_hoy))
            ticket_prom = ventas_hoy / tickets_hoy if tickets_hoy > 0 else 0
            self._kpis["ticket_prom"].set_valor(f"${ticket_prom:,.0f}")
        except Exception:
            pass

        # Margen bruto
        try:
            r = self.conn.execute("""
                SELECT COALESCE(SUM(vd.cantidad * vd.precio_unitario),0),
                       COALESCE(SUM(vd.cantidad * COALESCE(p.precio_compra,0)),0)
                FROM ventas v
                JOIN detalles_venta vd ON vd.venta_id=v.id
                JOIN productos p ON p.id=vd.producto_id
                WHERE DATE(v.fecha)=DATE('now') AND v.estado='completada'
            """).fetchone()
            ingresos = float(r[0] or 0)
            costos   = float(r[1] or 0)
            margen   = ((ingresos - costos) / ingresos * 100) if ingresos > 0 else 0
            self._kpis["margen_hoy"].set_valor(f"{margen:.1f}%")
            self._kpis["margen_hoy"].set_estado(margen)
        except Exception:
            pass

        # vs Ayer
        try:
            ayer = float(
                self.conn.execute("""
                    SELECT COALESCE(SUM(total),0) FROM ventas
                    WHERE DATE(fecha)=DATE('now','-1 day') AND estado='completada'
                """).fetchone()[0]
            )
            if ayer > 0:
                delta = (ventas_hoy - ayer) / ayer * 100
                sign  = "↑ +" if delta >= 0 else "↓ "
                self._kpis["vs_ayer"].set_valor(f"{sign}{delta:.1f}%")
                self._kpis["vs_ayer"].set_estado(ventas_hoy, ayer)
            else:
                self._kpis["vs_ayer"].set_valor("—")
        except Exception:
            pass

        # Clientes
        try:
            n = self.conn.execute("""
                SELECT COUNT(DISTINCT COALESCE(cliente_id,0)) FROM ventas
                WHERE DATE(fecha)=DATE('now') AND estado='completada'
                  AND cliente_id IS NOT NULL
            """).fetchone()[0]
            self._kpis["clientes_hoy"].set_valor(str(n))
        except Exception:
            pass

        # Pedidos WA
        try:
            n = self.conn.execute("""
                SELECT COUNT(*) FROM pedidos_whatsapp
                WHERE estado NOT IN ('entregado','cancelado')
            """).fetchone()[0]
            self._kpis["pedidos_wa"].set_valor(str(n))
        except Exception:
            pass

        # Stock bajo
        try:
            n = self.conn.execute("""
                SELECT COUNT(*) FROM productos
                WHERE existencia <= COALESCE(stock_minimo,5) AND activo=1
            """).fetchone()[0]
            self._kpis["productos_bajo"].set_valor(str(n))
        except Exception:
            pass

    def _actualizar_actividad(self) -> None:
        """Populate activity feed from recent sales and WA orders."""
        # Clear existing items
        while self._lyt_actividad.count():
            item = self._lyt_actividad.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        eventos = []

        try:
            rows = self.conn.execute("""
                SELECT 'venta' as tipo, total, fecha, 'completada' as extra
                FROM ventas
                WHERE DATE(fecha)=DATE('now') AND estado='completada'
                ORDER BY fecha DESC LIMIT 5
            """).fetchall()
            for r in rows:
                try:
                    ts = datetime.fromisoformat(str(r[2]))
                    hora = ts.strftime("%H:%M")
                except Exception:
                    hora = ""
                eventos.append(("venta", f"Venta completada", f"${float(r[1]):,.0f}", hora))
        except Exception:
            pass

        try:
            rows = self.conn.execute("""
                SELECT 'pedido' as tipo, total, fecha, estado
                FROM pedidos_whatsapp
                WHERE DATE(fecha)=DATE('now')
                ORDER BY fecha DESC LIMIT 4
            """).fetchall()
            for r in rows:
                try:
                    ts = datetime.fromisoformat(str(r[2]))
                    hora = ts.strftime("%H:%M")
                except Exception:
                    hora = ""
                eventos.append(("pedido", f"Pedido WA — {r[3]}", f"${float(r[1]):,.0f}", hora))
        except Exception:
            pass

        # Sort by timestamp desc (rough, based on hora string)
        eventos.sort(key=lambda e: e[3], reverse=True)
        eventos = eventos[:8]

        if not eventos:
            self._empty_actividad.show()
            return

        self._empty_actividad.hide()
        for tipo, desc, monto, hora in eventos:
            item = ActivityFeedItem(tipo, desc, monto, hora, self)
            self._lyt_actividad.addWidget(item)

    def _actualizar_pedidos_wa(self):
        self._loading_wa.show()
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
                LIMIT 8
            """).fetchall()
            if not rows:
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
            if item.widget():
                item.widget().deleteLater()

        alertas = []
        try:
            rows = self.conn.execute("""
                SELECT nombre FROM productos
                WHERE existencia <= COALESCE(stock_minimo,5) AND activo=1
                LIMIT 5
            """).fetchall()
            for r in rows:
                alertas.append((f"Stock bajo: {r[0]}", "danger"))
        except Exception:
            pass

        try:
            rows = self.conn.execute("""
                SELECT p.nombre FROM lotes l
                JOIN productos p ON p.id=l.producto_id
                WHERE l.caducidad <= DATE('now','+3 days')
                  AND l.estado='activo' AND l.cantidad_disponible > 0
                LIMIT 5
            """).fetchall()
            for r in rows:
                alertas.append((f"Caducidad próxima: {r[0]}", "warning"))
        except Exception:
            pass

        try:
            rows = self.conn.execute("""
                SELECT titulo, tipo FROM alertas_log
                WHERE leida=0 AND tipo != 'ok'
                ORDER BY fecha DESC LIMIT 10
            """).fetchall()
            for r in rows:
                t = "warning" if r[1] in ("stock_bajo", "caducidad_proxima") else "info"
                alertas.append((r[0], t))
        except Exception:
            pass

        # Update badge count
        if alertas:
            danger_count = sum(1 for _, t in alertas if t == "danger")
            if danger_count:
                self._lbl_alerts_count.setText(f"  {len(alertas)} activas")
            else:
                self._lbl_alerts_count.setText(f"  {len(alertas)}")
        else:
            self._lbl_alerts_count.setText("")

        if not alertas:
            self._empty_alertas.show()
            self._loading_alertas.hide()
            return

        self._empty_alertas.hide()
        for i, (texto, tipo) in enumerate(alertas):
            self._lyt_alertas.insertWidget(i, AlertaItem(texto, tipo))
        self._loading_alertas.hide()

    def _actualizar_repartidores(self):
        # Clear existing driver cards
        while self._lyt_drivers.count():
            item = self._lyt_drivers.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        try:
            rows = self.conn.execute("""
                SELECT d.nombre, d.en_ruta, COUNT(p.id) as pedidos_activos
                FROM drivers d
                LEFT JOIN pedidos_whatsapp p
                    ON p.repartidor_id=d.id AND p.estado='listo'
                WHERE d.activo=1
                GROUP BY d.id
                ORDER BY d.nombre
            """).fetchall()
            if not rows:
                no_driver = QLabel("Sin repartidores registrados", self)
                no_driver.setStyleSheet(
                    f"color: {Colors.NEUTRAL.SLATE_500};"
                    f" font-size: {Typography.SIZE_SM}; padding: 8px 0;"
                )
                self._lyt_drivers.addWidget(no_driver)
                return
            for r in rows:
                card = DriverCard(r[0], bool(r[1]), int(r[2]), self)
                self._lyt_drivers.addWidget(card)
        except Exception:
            pass

    def _on_ver_pedido(self, pedido_id: int):
        self.abrir_modulo.emit("pedidos_whatsapp")

    # ── Session state (consumed by main_window via hasattr) ───────────────────

    def set_sucursal(self, sucursal_id: int, nombre: str = "") -> None:
        self.sucursal_id = sucursal_id
        self._nombre_sucursal = nombre
        if nombre:
            self._lbl_subtitle.setText(f"Resumen operativo · {nombre}")
        try:
            self.actualizar()
        except Exception as e:
            logger.debug("set_sucursal refresh: %s", e)

    def set_usuario_actual(self, usuario: str, rol: str = "") -> None:
        self.usuario_actual = usuario
        self.rol_actual = rol.lower() if rol else "cajero"
        try:
            self.actualizar()
        except Exception as e:
            logger.debug("set_usuario_actual refresh: %s", e)

    def set_sesion(self, usuario: str, rol: str) -> None:
        self.set_usuario_actual(usuario, rol)


# ── Compatibility shims ───────────────────────────────────────────────────────

class _PageHeaderCompat:
    """Thin shim so legacy callers to self._page_header.set_subtitle() still work."""

    def __init__(self, subtitle_label: QLabel):
        self._lbl = subtitle_label

    def set_subtitle(self, text: str) -> None:
        self._lbl.setText(text)

    def add_action(self, widget) -> None:
        pass  # Header rebuilt; actions wired directly in _build_header


class DashboardWidget(Dashboard):
    """Alias of Dashboard for compatibility with main_window.py."""
    pass
