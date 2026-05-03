
# ui/ventana_pedidos.py — SPJ POS v11
"""
Ventana de gestión de pedidos WhatsApp en el POS.
  - Cola de pedidos pendientes en tiempo real
  - Ajuste de peso por ítem
  - Botón confirmar → notifica al cliente via WA
  - Asignación de repartidor
  - Vista de mapa de entrega
"""
from __future__ import annotations
import logging
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QDialog, QFormLayout, QDoubleSpinBox,
    QMessageBox, QComboBox, QGroupBox, QHeaderView, QFrame,
    QSplitter, QTextEdit, QScrollArea,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont
from core.db.connection import get_connection

logger = logging.getLogger("spj.ui.pedidos")


class VentanaPedidos(QWidget):
    """Módulo de cola de pedidos WhatsApp integrado al POS."""

    def __init__(self, conn=None, whatsapp_svc=None, parent=None):
        super().__init__(parent)
        self.conn    = conn or get_connection()
        self.wa_svc  = whatsapp_svc
        self._setup_ui()
        self._timer  = QTimer(self)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self.cargar_pedidos)
        self._timer.start()
        self.cargar_pedidos()

    # ── UI ─────────────────────────────────────────────────────────
    def _setup_ui(self):
        self.setWindowTitle("Pedidos WhatsApp")
        self.setMinimumSize(1000, 620)

        lyt = QVBoxLayout(self)
        lyt.setSpacing(8)

        # Header
        hdr = QHBoxLayout()
        titulo = QLabel("📲 Cola de Pedidos WhatsApp")
        titulo.setFont(QFont("Arial", 16, QFont.Bold))
        hdr.addWidget(titulo)
        hdr.addStretch()
        self.lbl_count = QLabel("0 pendientes")
        self.lbl_count.setStyleSheet("color:#E74C3C; font-weight:bold; font-size:14px;")
        hdr.addWidget(self.lbl_count)
        btn_refresh = QPushButton("🔄 Actualizar")
        btn_refresh.clicked.connect(self.cargar_pedidos)
        hdr.addWidget(btn_refresh)
        lyt.addLayout(hdr)

        # Tabla
        self.tabla = QTableWidget()
        self.tabla.setColumnCount(8)
        self.tabla.setHorizontalHeaderLabels([
            "#", "Cliente", "Teléfono", "Estado", "Total", "Entrega", "Pago", "Fecha"
        ])
        self.tabla.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.tabla.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tabla.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabla.itemDoubleClicked.connect(self._abrir_detalle)
        lyt.addWidget(self.tabla)

        # Botones
        btn_row = QHBoxLayout()
        for text, fn, color in [
            ("⚖️ Ajustar Peso",   self._ajustar_peso,    "#2ECC71"),
            ("✅ Confirmar",       self._confirmar_pedido,"#27AE60"),
            ("🚚 Asignar Reparto", self._asignar_reparto, "#3498DB"),
            ("❌ Cancelar",        self._cancelar_pedido, "#E74C3C"),
        ]:
            btn = QPushButton(text)
            btn.setMinimumHeight(40)
            btn.setStyleSheet(f"background:{color};color:white;font-weight:bold;border-radius:6px;")
            btn.clicked.connect(fn)
            btn_row.addWidget(btn)
        lyt.addLayout(btn_row)

    # ── Datos ──────────────────────────────────────────────────────
    def cargar_pedidos(self):
        rows = self.conn.execute("""
            SELECT id, cliente_nombre, numero_whatsapp, estado,
                   total, tipo_entrega, forma_pago, fecha
            FROM pedidos_whatsapp
            WHERE estado NOT IN ('entregado','cancelado')
            ORDER BY CASE estado
                WHEN 'nuevo'      THEN 0
                WHEN 'confirmado' THEN 1
                WHEN 'pesando'    THEN 2
                WHEN 'listo'      THEN 3
                ELSE 9 END, fecha DESC
            LIMIT 100""").fetchall()

        self.tabla.setRowCount(len(rows))
        pendientes = 0
        COLORES = {
            "nuevo":     "#FDEDEC",
            "confirmado":"#EBF5FB",
            "pesando":   "#FEF9E7",
            "listo":     "#EAFAF1",
        }
        for i, row in enumerate(rows):
            vals = [str(row[0]), row[1] or "—", row[2] or "—",
                    row[3] or "—", f"${float(row[4] or 0):.2f}",
                    row[5] or "mostrador", row[6] or "—",
                    str(row[7] or "")[:16]]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignCenter)
                color = COLORES.get(row[3], "#FFFFFF")
                item.setBackground(QColor(color))
                self.tabla.setItem(i, j, item)
            if row[3] == "nuevo":
                pendientes += 1

        self.lbl_count.setText(
            f"{pendientes} nuevo{'s' if pendientes != 1 else ''}" if pendientes
            else "Sin pedidos nuevos")

    def _get_pedido_seleccionado(self) -> int | None:
        row = self.tabla.currentRow()
        if row < 0:
            QMessageBox.information(self, "Info", "Selecciona un pedido primero.")
            return None
        item = self.tabla.item(row, 0)
        return int(item.text()) if item else None

    # ── Acciones ──────────────────────────────────────────────────
    def _ajustar_peso(self):
        pid = self._get_pedido_seleccionado()
        if not pid: return
        dlg = DialogAjustePeso(pid, self.conn, self)
        if dlg.exec_() == QDialog.Accepted:
            self._notificar_cliente_ajuste(pid)
            self.cargar_pedidos()

    def _confirmar_pedido(self):
        pid = self._get_pedido_seleccionado()
        if not pid: return
        self.conn.execute(
            "UPDATE pedidos_whatsapp SET estado='listo',fecha_confirmacion=datetime('now') WHERE id=?",
            (pid,))
        try: self.conn.commit()
        except Exception: pass
        self._notificar_cliente_listo(pid)
        self.cargar_pedidos()
        QMessageBox.information(self, "Pedido", f"Pedido #{pid} marcado como LISTO ✅")

    def _asignar_reparto(self):
        pid = self._get_pedido_seleccionado()
        if not pid: return
        dlg = DialogAsignarRepartidor(pid, self.conn, self)
        if dlg.exec_() == QDialog.Accepted:
            self._notificar_cliente_en_camino(pid, dlg.repartidor_nombre)
            self.cargar_pedidos()

    def _cancelar_pedido(self):
        pid = self._get_pedido_seleccionado()
        if not pid: return
        if QMessageBox.question(self,"Cancelar",
            f"¿Cancelar pedido #{pid}?",
            QMessageBox.Yes|QMessageBox.No) == QMessageBox.Yes:
            self.conn.execute(
                "UPDATE pedidos_whatsapp SET estado='cancelado' WHERE id=?", (pid,))
            try: self.conn.commit()
            except Exception: pass
            self.cargar_pedidos()

    def _abrir_detalle(self, item):
        row = item.row()
        pid = int(self.tabla.item(row, 0).text())
        dlg = DialogDetallePedido(pid, self.conn, self)
        dlg.exec_()

    # ── Notificaciones WA ──────────────────────────────────────────
    def _notificar_cliente_ajuste(self, pedido_id: int):
        if not self.wa_svc: return
        try:
            pedido = self.conn.execute(
                "SELECT numero_whatsapp, total FROM pedidos_whatsapp WHERE id=?",
                (pedido_id,)).fetchone()
            if pedido:
                items = self.conn.execute("""
                    SELECT nombre_producto, cantidad_pesada, precio_unitario, subtotal
                    FROM pedidos_whatsapp_items WHERE pedido_id=?""",
                    (pedido_id,)).fetchall()
                detalle = "\n".join(
                    f"• {r[0]}: {float(r[1] or 0):.3f}kg = ${float(r[3] or 0):.2f}"
                    for r in items)
                msg = (f"⚖️ *Peso real de tu pedido #{pedido_id}:*\n\n"
                       f"{detalle}\n\n"
                       f"💰 *Total actualizado: ${float(pedido[1]):.2f}*\n\n"
                       "¿Confirmas con este total? (sí/no)")
                self.wa_svc.send_message(pedido[0], msg)
        except Exception as e:
            logger.error("notificar_ajuste: %s", e)

    def _notificar_cliente_listo(self, pedido_id: int):
        if not self.wa_svc: return
        try:
            pedido = self.conn.execute(
                "SELECT numero_whatsapp, cliente_nombre, total, tipo_entrega, forma_pago FROM pedidos_whatsapp WHERE id=?",
                (pedido_id,)).fetchone()
            if pedido:
                if pedido[3] == "delivery":
                    msg = (f"📦 *Pedido #{pedido_id} listo para envío*\n"
                           f"Total: ${float(pedido[4]):.2f}\n"
                           "En breve asignamos repartidor 🚚")
                else:
                    msg = (f"✅ *Tu pedido #{pedido_id} está listo*\n"
                           f"Total: *${float(pedido[4]):.2f}*\n"
                           "Pasa a recogerlo cuando gustes.")
                self.wa_svc.send_message(pedido[0], msg)
        except Exception as e:
            logger.error("notificar_listo: %s", e)

    def _notificar_cliente_en_camino(self, pedido_id: int, rep_nombre: str):
        if not self.wa_svc: return
        try:
            pedido = self.conn.execute(
                "SELECT numero_whatsapp FROM pedidos_whatsapp WHERE id=?",
                (pedido_id,)).fetchone()
            if pedido:
                msg = (f"🚚 *Tu pedido #{pedido_id} está en camino*\n"
                       f"Repartidor: *{rep_nombre}*\n"
                       "Te avisamos al llegar.")
                self.wa_svc.send_message(pedido[0], msg)
        except Exception as e:
            logger.error("notificar_en_camino: %s", e)

    # ── API para notificaciones externas ──────────────────────────
    def on_pedido_nuevo(self, pedido: dict):
        """Llamado por GestorNotificaciones cuando llega pedido nuevo."""
        self.cargar_pedidos()

    def set_sesion(self, usuario: str, rol: str):
        pass


class DialogAjustePeso(QDialog):
    """Permite al cajero ajustar el peso real pesado de cada ítem."""
    def __init__(self, pedido_id: int, conn, parent=None):
        super().__init__(parent)
        self.pedido_id = pedido_id
        self.conn      = conn
        self.setWindowTitle(f"⚖️ Ajustar Peso — Pedido #{pedido_id}")
        self.setMinimumWidth(560)
        self._setup()

    def _setup(self):
        lyt   = QVBoxLayout(self)
        items = self.conn.execute(
            "SELECT * FROM pedidos_whatsapp_items WHERE pedido_id=?",
            (self.pedido_id,)).fetchall()
        self._spins = {}
        form = QFormLayout()
        for item in items:
            item = dict(item)
            spin = QDoubleSpinBox()
            spin.setRange(0.001, 9999.0)
            spin.setDecimals(3)
            spin.setSuffix(" kg")
            spin.setValue(float(item.get("cantidad_pesada") or item.get("cantidad_pedida") or 0))
            self._spins[item["id"]] = (spin, float(item["precio_unitario"]))
            form.addRow(item["nombre_producto"], spin)
        lyt.addLayout(form)
        row = QHBoxLayout()
        for text, result in [("✅ Guardar", QDialog.Accepted), ("Cancelar", QDialog.Rejected)]:
            btn = QPushButton(text)
            btn.clicked.connect(lambda _, r=result: self.done(r) if r == QDialog.Rejected else self._guardar())
            row.addWidget(btn)
        lyt.addLayout(row)

    def _guardar(self):
        total_nuevo = 0.0
        for item_id, (spin, precio) in self._spins.items():
            peso    = spin.value()
            subtotal = round(peso * precio, 2)
            total_nuevo += subtotal
            self.conn.execute("""UPDATE pedidos_whatsapp_items
                SET cantidad_pesada=?, subtotal=? WHERE id=?""",
                (peso, subtotal, item_id))
        self.conn.execute(
            "UPDATE pedidos_whatsapp SET total=?, estado='pesando' WHERE id=?",
            (total_nuevo, self.pedido_id))
        try: self.conn.commit()
        except Exception: pass
        self.accept()


class DialogAsignarRepartidor(QDialog):
    def __init__(self, pedido_id: int, conn, parent=None):
        super().__init__(parent)
        self.pedido_id = pedido_id
        self.conn      = conn
        self.repartidor_nombre = ""
        self.setWindowTitle(f"🚚 Asignar Repartidor — Pedido #{pedido_id}")
        self._setup()

    def _setup(self):
        lyt  = QVBoxLayout(self)
        rows = self.conn.execute(
            "SELECT id, nombre FROM drivers WHERE activo=1").fetchall()
        self.combo = QComboBox()
        for r in rows:
            self.combo.addItem(r[1], r[0])
        lyt.addWidget(QLabel("Selecciona el repartidor:"))
        lyt.addWidget(self.combo)
        row = QHBoxLayout()
        for text, result in [("Asignar", QDialog.Accepted), ("Cancelar", QDialog.Rejected)]:
            btn = QPushButton(text)
            btn.clicked.connect(lambda _, r=result: self._asignar() if r == QDialog.Accepted else self.reject())
            row.addWidget(btn)
        lyt.addLayout(row)

    def _asignar(self):
        rep_id   = self.combo.currentData()
        rep_name = self.combo.currentText()
        if rep_id:
            self.conn.execute("""UPDATE pedidos_whatsapp
                SET repartidor_id=?, estado='listo' WHERE id=?""",
                (rep_id, self.pedido_id))
            try: self.conn.commit()
            except Exception: pass
            self.repartidor_nombre = rep_name
            self.accept()


class DialogDetallePedido(QDialog):
    def __init__(self, pedido_id: int, conn, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Detalle Pedido #{pedido_id}")
        self.setMinimumSize(500, 400)
        lyt = QVBoxLayout(self)
        pedido = conn.execute(
            "SELECT * FROM pedidos_whatsapp WHERE id=?", (pedido_id,)).fetchone()
        if pedido:
            pedido = dict(pedido)
            info = QTextEdit()
            info.setReadOnly(True)
            items = conn.execute(
                "SELECT * FROM pedidos_whatsapp_items WHERE pedido_id=?",
                (pedido_id,)).fetchall()
            txt = f"Pedido #{pedido_id}\nCliente: {pedido.get('cliente_nombre','—')}\n"
            txt += f"Tel: {pedido.get('numero_whatsapp','')}\n"
            txt += f"Estado: {pedido.get('estado','')}\n"
            txt += f"Entrega: {pedido.get('tipo_entrega','mostrador')}\n"
            txt += f"Pago: {pedido.get('forma_pago','')}\n"
            txt += f"Dir: {pedido.get('direccion_entrega','')}\n\n"
            txt += "PRODUCTOS:\n"
            for i in items:
                i = dict(i)
                peso = float(i.get("cantidad_pesada") or i.get("cantidad_pedida") or 0)
                txt += f"  • {i['nombre_producto']}: {peso:.3f}kg x ${float(i['precio_unitario']):.2f} = ${float(i['subtotal']):.2f}\n"
            txt += f"\nTOTAL: ${float(pedido.get('total',0)):.2f}"
            info.setText(txt)
            lyt.addWidget(info)
        btn = QPushButton("Cerrar")
        btn.clicked.connect(self.accept)
        lyt.addWidget(btn)
