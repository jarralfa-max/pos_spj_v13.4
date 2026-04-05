
# ui/dashboard.py — SPJ POS v12
"""
Dashboard principal del POS en tiempo real.
  - KPIs del día: ventas, tickets, productos top
  - Cola de pedidos WhatsApp pendientes
  - Alertas de stock bajo y lotes por caducar
  - Estado de repartidores activos
  - Acceso rápido a módulos clave
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

logger = logging.getLogger("spj.ui.dashboard")


class KPICard(QFrame):
    """Tarjeta de KPI individual."""
    clicked = pyqtSignal(str)

    def __init__(self, titulo: str, valor: str = "—",
                 color: str = "#3498DB", icono: str = "📊",
                 key: str = "", parent=None):
        super().__init__(parent)
        self._key = key
        self.setFrameStyle(QFrame.StyledPanel)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
            KPICard {{
                background: {color};
                border-radius: 12px;
                border: none;
            }}
            KPICard:hover {{
                background: {color}dd;
            }}
        """)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(100)

        lyt = QVBoxLayout(self)
        lyt.setContentsMargins(16, 12, 16, 12)

        top = QHBoxLayout()
        lbl_icono = QLabel(icono)
        lbl_icono.setStyleSheet("font-size: 26px; background: transparent;")
        top.addWidget(lbl_icono)
        top.addStretch()
        lyt.addLayout(top)

        self.lbl_valor = QLabel(valor)
        self.lbl_valor.setStyleSheet(
            "color: white; font-size: 26px; font-weight: 800; background: transparent;")
        lyt.addWidget(self.lbl_valor)

        lbl_titulo = QLabel(titulo)
        lbl_titulo.setStyleSheet(
            "color: rgba(255,255,255,0.85); font-size: 12px; background: transparent;")
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

    def mousePressEvent(self, event):
        self.clicked.emit(self._key)


class AlertaItem(QFrame):
    """Item de alerta en la lista lateral."""
    def __init__(self, texto: str, tipo: str = "info", parent=None):
        super().__init__(parent)
        colores = {
            "danger":  "#FDEDEC",
            "warning": "#FEF9E7",
            "success": "#EAFAF1",
            "info":    "#EBF5FB",
        }
        iconos = {"danger":"🔴","warning":"⚠️","success":"✅","info":"ℹ️"}
        self.setStyleSheet(f"""
            AlertaItem {{
                background: {colores.get(tipo,'#EBF5FB')};
                border-radius: 8px;
                border-left: 4px solid {'#E74C3C' if tipo=='danger' else '#F39C12' if tipo=='warning' else '#27AE60' if tipo=='success' else '#3498DB'};
            }}
        """)
        lyt = QHBoxLayout(self)
        lyt.setContentsMargins(10, 8, 10, 8)
        lbl = QLabel(f"{iconos.get(tipo,'•')} {texto}")
        lbl.setWordWrap(True)
        lbl.setStyleSheet("font-size: 12px; background: transparent;")
        lyt.addWidget(lbl)


class PedidoWAItem(QFrame):
    """Tarjeta de pedido WhatsApp en el dashboard."""
    ver_pedido = pyqtSignal(int)

    def __init__(self, pedido: dict, parent=None):
        super().__init__(parent)
        pid = pedido.get("id", 0)
        self.setStyleSheet("""
            PedidoWAItem {
                background: white;
                border-radius: 8px;
                border: 1px solid #E0E0E0;
            }
            PedidoWAItem:hover { border-color: #3498DB; }
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
        colores_estado = {"nuevo":"#E74C3C","confirmado":"#2980B9",
                          "pesando":"#F39C12","listo":"#27AE60"}
        badge = QLabel(estado.upper())
        badge.setStyleSheet(
            f"background:{colores_estado.get(estado,'#95A5A6')};"
            "color:white;padding:2px 8px;border-radius:10px;font-size:10px;")
        top.addWidget(badge)
        lyt.addLayout(top)

        lyt.addWidget(QLabel(pedido.get("cliente_nombre","—")))
        lyt.addWidget(QLabel(
            f"${float(pedido.get('total',0)):.2f} · "
            f"{pedido.get('tipo_entrega','mostrador')}"))

        btn = QPushButton("Ver detalle →")
        btn.setStyleSheet(
            "background: transparent; color: #3498DB; border: none; "
            "font-size: 11px; text-align: left; padding: 0;")
        btn.setCursor(Qt.PointingHandCursor)
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
        self.setStyleSheet("QWidget#Dashboard { background: #F0F4F8; }")

        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # ── Header ──────────────────────────────────────────────────
        header = QFrame()
        header.setStyleSheet("background: #1A237E; padding: 0;")
        header.setFixedHeight(60)
        hdr_lyt = QHBoxLayout(header)
        hdr_lyt.setContentsMargins(24, 0, 24, 0)
        lbl_titulo = QLabel("📊 Dashboard SPJ POS")
        lbl_titulo.setStyleSheet(
            "color: white; font-size: 20px; font-weight: 700;")
        hdr_lyt.addWidget(lbl_titulo)
        hdr_lyt.addStretch()
        self.lbl_hora = QLabel()
        self.lbl_hora.setStyleSheet(
            "color: rgba(255,255,255,0.8); font-size: 13px;")
        hdr_lyt.addWidget(self.lbl_hora)
        root.addWidget(header)

        # ── Cuerpo ───────────────────────────────────────────────────
        body = QHBoxLayout()
        body.setContentsMargins(16, 16, 16, 16)
        body.setSpacing(16)

        # Columna izquierda (KPIs + pedidos WA)
        left = QVBoxLayout()
        left.setSpacing(12)

        # KPIs grid
        kpi_grid = QGridLayout()
        kpi_grid.setSpacing(10)
        self._kpis = {
            "ventas_hoy":    KPICard("Ventas hoy",    "$0",  "#2ECC71", "💰", "ventas"),
            "tickets_hoy":   KPICard("Tickets",       "0",   "#3498DB", "🧾", "ventas"),
            "pedidos_wa":    KPICard("Pedidos WA",    "0",   "#E74C3C", "📲", "pedidos_whatsapp"),
            "productos_bajo": KPICard("Stock bajo",   "0",   "#E67E22", "⚠️", "inventario"),
        }
        for i, (key, card) in enumerate(self._kpis.items()):
            card.clicked.connect(self.abrir_modulo)
            kpi_grid.addWidget(card, i // 2, i % 2)
        left.addLayout(kpi_grid)

        # Cola pedidos WA
        lbl_wa = QLabel("📲 Pedidos WhatsApp pendientes")
        lbl_wa.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #2C3E50; margin-top: 8px;")
        left.addWidget(lbl_wa)

        self._scroll_wa = QScrollArea()
        self._scroll_wa.setWidgetResizable(True)
        self._scroll_wa.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._scroll_wa.setMinimumHeight(220)
        self._container_wa = QWidget()
        self._lyt_wa = QVBoxLayout(self._container_wa)
        self._lyt_wa.setSpacing(8)
        self._lyt_wa.setContentsMargins(0, 0, 0, 0)
        self._lyt_wa.addStretch()
        self._scroll_wa.setWidget(self._container_wa)
        left.addWidget(self._scroll_wa)

        # Accesos rápidos
        lbl_acc = QLabel("⚡ Acceso rápido")
        lbl_acc.setStyleSheet("font-size: 14px; font-weight: 700; color: #2C3E50;")
        left.addWidget(lbl_acc)
        acc_row = QHBoxLayout()
        acc_row.setSpacing(8)
        for texto, key, color in [
            ("🛒 Nueva Venta",    "ventas",           "#2ECC71"),
            ("📦 Inventario",     "inventario",        "#3498DB"),
            ("📲 Pedidos WA",     "pedidos_whatsapp",  "#E74C3C"),
            ("📊 Reportes",       "reportes",          "#9B59B6"),
        ]:
            btn = QPushButton(texto)
            btn.setMinimumHeight(44)
            btn.setStyleSheet(
                f"background:{color};color:white;border-radius:8px;"
                "font-weight:600;font-size:12px;")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, k=key: self.abrir_modulo.emit(k))
            acc_row.addWidget(btn)
        left.addLayout(acc_row)
        left.addStretch()

        # Columna derecha (alertas + repartidores)
        right = QVBoxLayout()
        right.setSpacing(12)
        right.setContentsMargins(0, 0, 0, 0)

        lbl_alertas = QLabel("🔔 Alertas")
        lbl_alertas.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #2C3E50;")
        right.addWidget(lbl_alertas)

        self._scroll_alertas = QScrollArea()
        self._scroll_alertas.setWidgetResizable(True)
        self._scroll_alertas.setFixedWidth(300)
        self._scroll_alertas.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }")
        self._container_alertas = QWidget()
        self._lyt_alertas = QVBoxLayout(self._container_alertas)
        self._lyt_alertas.setSpacing(6)
        self._lyt_alertas.setContentsMargins(0, 0, 0, 0)
        self._lyt_alertas.addStretch()
        self._scroll_alertas.setWidget(self._container_alertas)
        right.addWidget(self._scroll_alertas)

        lbl_reps = QLabel("🚚 Repartidores activos")
        lbl_reps.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #2C3E50;")
        right.addWidget(lbl_reps)
        self._lbl_reps = QLabel("Sin repartidores activos")
        self._lbl_reps.setWordWrap(True)
        self._lbl_reps.setStyleSheet(
            "color: #7F8C8D; font-size: 12px; background: white; "
            "border-radius: 8px; padding: 10px;")
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
                    "color:#7F8C8D;font-size:13px;padding:12px;"
                    "background:white;border-radius:8px;")
                self._lyt_wa.insertWidget(0, lbl)
                return
            for i, r in enumerate(rows):
                card = PedidoWAItem(dict(r))
                card.ver_pedido.connect(self._on_ver_pedido)
                self._lyt_wa.insertWidget(i, card)
        except Exception as e:
            logger.debug("pedidos_wa: %s", e)

    def _actualizar_alertas(self):
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
            alertas.append(("Sin alertas pendientes", "success"))
        for i, (texto, tipo) in enumerate(alertas):
            self._lyt_alertas.insertWidget(i, AlertaItem(texto, tipo))

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
