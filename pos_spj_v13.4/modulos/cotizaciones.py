
# modulos/cotizaciones.py — SPJ POS v12
# ── Módulo de Cotizaciones / Presupuestos ─────────────────────────────────────
# Para clientes institucionales (restaurantes, escuelas) que piden presupuesto
# antes de confirmar pedido.  Flujo: Crear → Aprobar → Convertir a Venta.
from __future__ import annotations
from core.events.event_bus import get_bus
import logging
from typing import Dict, List, Optional

from modulos.spj_phone_widget import PhoneWidget
from modulos.design_tokens import Colors, Spacing, Typography, Borders
from modulos.ui_components import (
    create_primary_button, create_success_button, create_danger_button,
    create_secondary_button, create_card, create_input, create_combo,
    apply_tooltip, create_heading, create_subheading,
    FilterBar, LoadingIndicator, EmptyStateWidget, confirm_action
)
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QTableWidget, QTableWidgetItem, QAbstractItemView,
    QHeaderView, QDialog, QFormLayout, QDoubleSpinBox, QSpinBox,
    QTextEdit, QMessageBox, QGroupBox, QSplitter, QFrame, QSizePolicy
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor

from .base import ModuloBase

logger = logging.getLogger("spj.ui.cotizaciones")

_C_VERDE  = "#27ae60"
_C_AZUL   = "#2980b9"
_C_NARANJ = "#e67e22"
_C_ROJO   = "#e74c3c"
_C_GRIS   = "#95a5a6"

_STATUS_COLOR = {
    "pendiente":   _C_AZUL,
    "aprobada":    _C_VERDE,
    "rechazada":   _C_ROJO,
    "vencida":     _C_GRIS,
    "convertida":  "#8e44ad",
}


class ModuloCotizaciones(ModuloBase):

    def __init__(self, container, parent=None):
        super().__init__(container.db, parent)
        try:
            from modulos.spj_refresh_mixin import RefreshMixin
            if isinstance(self, RefreshMixin):
                self._init_refresh(container, ["COTIZACION_ACTUALIZADA", "CLIENTE_ACTUALIZADO"])
        except Exception: pass
        self.container      = container
        self.conexion       = container.db
        self.sucursal_id    = 1
        self.usuario_actual = "Sistema"
        self._svc           = self._get_service()
        self._init_ui()
        QTimer.singleShot(0, self._cargar_lista)

    def _get_service(self):
        try:
            from core.services.cotizacion_service import CotizacionService
            return CotizacionService(
                conn=self.conexion,
                sucursal_id=self.sucursal_id,
                usuario=self.usuario_actual,
                container=self.container,  # Full service chain for convertir_en_venta
            )
        except Exception as e:
            logger.error("CotizacionService: %s", e)
            return None

    def _on_refresh(self, event_type: str, data: dict) -> None:
        try: self._cargar_lista()
        except Exception: pass

    def set_sucursal(self, sid: int, nombre: str) -> None:
        self.sucursal_id = sid
        if self._svc:
            self._svc.sucursal_id = sid
        QTimer.singleShot(0, self._cargar_lista)

    def set_usuario_actual(self, usuario: str, rol: str) -> None:
        self.usuario_actual = usuario or "Sistema"
        if self._svc:
            self._svc.usuario = usuario or "Sistema"

    def obtener_usuario_actual(self) -> str:
        return self.usuario_actual

    # ── UI ────────────────────────────────────────────────────────────────────

    def _init_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        # Header
        hdr = QHBoxLayout()
        lbl = QLabel("📋 Cotizaciones / Presupuestos")
        f = lbl.font(); f.setPointSize(15); f.setBold(True); lbl.setFont(f)
        hdr.addWidget(lbl); hdr.addStretch()
        self._lbl_suc = QLabel()
        self._lbl_suc.setObjectName("textSecondary")
        hdr.addWidget(self._lbl_suc)
        root.addLayout(hdr)

        # KPI row
        kpi_row = QHBoxLayout()
        self._kpi_pend  = self._kpi("Pendientes",   "0", Colors.PRIMARY_BASE)
        self._kpi_aprob = self._kpi("Aprobadas",    "0", Colors.SUCCESS_BASE)
        self._kpi_venc  = self._kpi("Vencidas hoy", "0", Colors.DANGER_BASE)
        self._kpi_conv  = self._kpi("Convertidas",  "0", Colors.ACCENT_BASE)
        for k in (self._kpi_pend, self._kpi_aprob, self._kpi_venc, self._kpi_conv):
            kpi_row.addWidget(k)
        root.addLayout(kpi_row)

        # Filtros + botón nueva
        fb = QHBoxLayout()
        self._filter_bar = FilterBar(
            self,
            placeholder="Buscar cliente o folio…",
            combo_filters={"estado": ["pendiente", "aprobada", "rechazada", "vencida", "convertida"]},
        )
        self._filter_bar.filters_changed.connect(lambda _: self._cargar_lista())
        fb.addWidget(self._filter_bar, 1)
        fb.addStretch()
        btn_nueva = create_primary_button(self, "➕ Nueva Cotización", "Crear una nueva cotización o presupuesto")
        btn_nueva.clicked.connect(self._nueva_cotizacion)
        btn_vencer = QPushButton("⏰ Vencer expiradas")
        btn_vencer.setToolTip("Marca como vencidas las cotizaciones cuya fecha límite ya pasó")
        btn_vencer.clicked.connect(self._vencer_expiradas)
        fb.addWidget(btn_vencer); fb.addWidget(btn_nueva)
        root.addLayout(fb)

        self._loading = LoadingIndicator("Cargando cotizaciones…", self)
        self._loading.hide()
        root.addWidget(self._loading)

        # Tabla principal
        self._tbl = QTableWidget()
        self._tbl.setColumnCount(8)
        self._tbl.setHorizontalHeaderLabels([
            "Folio", "Cliente", "Total", "Estado",
            "Vigencia", "Vencimiento", "Usuario", "Fecha"
        ])
        self._tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setAlternatingRowColors(True)
        h = self._tbl.horizontalHeader()
        for i in range(8): h.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        self._tbl.itemSelectionChanged.connect(self._on_sel)
        self._tbl.itemDoubleClicked.connect(lambda _: self._ver_detalle())
        root.addWidget(self._tbl)
        self._empty_state = EmptyStateWidget(
            "Sin cotizaciones",
            "No se encontraron cotizaciones para los filtros seleccionados.",
            "📭",
            self,
        )
        self._empty_state.hide()
        root.addWidget(self._empty_state)

        # Botones de acción
        ab = QHBoxLayout()
        self._btn_aprobar = create_success_button(self, "✓ Aprobar", "Aprobar esta cotización")
        self._btn_rechazar = create_danger_button(self, "✗ Rechazar", "Rechazar esta cotización")
        self._btn_convertir = create_primary_button(self, "➤ Convertir a Venta", "Convertir cotización aprobada en venta")
        self._btn_detalle = create_secondary_button(self, "🔍 Ver Detalle", "Ver detalle de la cotización")
        self._btn_imprimir = create_secondary_button(self, "🖨️ Imprimir / PDF", "Imprimir o exportar cotización")
        self._btn_detalle.setObjectName("secondaryBtn")
        self._btn_imprimir.setObjectName("secondaryBtn")
        for b in (self._btn_aprobar, self._btn_rechazar,
                  self._btn_convertir, self._btn_detalle, self._btn_imprimir):
            b.setEnabled(False)
            ab.addWidget(b)
        ab.addStretch()
        self._btn_aprobar.clicked.connect(self._aprobar)
        self._btn_rechazar.clicked.connect(self._rechazar)
        self._btn_convertir.clicked.connect(self._convertir_en_venta)
        self._btn_detalle.clicked.connect(self._ver_detalle)
        self._btn_imprimir.clicked.connect(self._imprimir)
        root.addLayout(ab)

    def _kpi(self, titulo: str, valor: str, color: str) -> QFrame:
        """
        Crea una tarjeta KPI para mostrar métricas.
        
        Args:
            titulo: Título del KPI
            valor: Valor a mostrar
            color: Color del texto del valor
        
        Returns:
            QFrame configurado como tarjeta KPI
        """
        # CORRECCIÓN: Usar create_card con with_layout=False para evitar conflicto de layouts
        card = create_card(self, padding=Spacing.SM, with_layout=False)
        card.setObjectName("statCard")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        card.setFixedHeight(68)
        lay = QVBoxLayout(card); lay.setContentsMargins(10, 4, 10, 4)
        lt = QLabel(titulo); lt.setObjectName("caption")
        lv = QLabel(valor)
        lv.setStyleSheet(f"color:{color};font-size:18px;font-weight:bold;")
        lay.addWidget(lt); lay.addWidget(lv)
        card._val = lv
        return card

    # ── Datos ─────────────────────────────────────────────────────────────────

    def _cargar_lista(self) -> None:
        if not self._svc:
            if hasattr(self, "_loading"):
                self._loading.hide()
            return
        self._loading.show()
        try:
            filtros = self._filter_bar.values() if hasattr(self, "_filter_bar") else {}
            estado = filtros.get("estado", "Todos") or "Todos"
            buscar = filtros.get("search", "").strip().lower()
            estado = None if estado == "Todos" else estado
            try:
                rows = self._svc.get_cotizaciones(estado=estado, limit=200)
            except Exception as e:
                logger.error("get_cotizaciones: %s", e)
                rows = []

            if buscar:
                rows = [r for r in rows if
                        buscar in str(r.get("folio", "")).lower() or
                        buscar in str(r.get("cliente_nombre", "")).lower()]

            # KPIs
            conteos = {"pendiente": 0, "aprobada": 0, "vencida": 0, "convertida": 0}
            for r in (self._svc.get_cotizaciones(limit=500) or []):
                est = r.get("estado", "")
                if est in conteos:
                    conteos[est] += 1
            self._kpi_pend._val.setText(str(conteos["pendiente"]))
            self._kpi_aprob._val.setText(str(conteos["aprobada"]))
            self._kpi_venc._val.setText(str(conteos["vencida"]))
            self._kpi_conv._val.setText(str(conteos["convertida"]))

            # Tabla
            self._tbl.setRowCount(len(rows))
            for ri, r in enumerate(rows):
                estado_r = r.get("estado", "")
                color    = _STATUS_COLOR.get(estado_r, "#333")
                vals = [
                    r.get("folio", ""),
                    r.get("cliente_nombre", "—"),
                    f"${float(r.get('total', 0)):.2f}",
                    estado_r,
                    f"{r.get('vigencia_dias', 7)} días",
                    str(r.get("fecha_vencimiento", ""))[:10],
                    r.get("usuario", ""),
                    str(r.get("fecha", ""))[:16],
                ]
                for ci, v in enumerate(vals):
                    it = QTableWidgetItem(str(v))
                    it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    if ci == 0:
                        it.setData(Qt.UserRole, r.get("id"))
                    if ci == 3:
                        it.setForeground(QColor(color))
                        it.setTextAlignment(Qt.AlignCenter)
                    if ci == 2:
                        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    self._tbl.setItem(ri, ci, it)
            if hasattr(self, "_empty_state"):
                self._empty_state.setVisible(len(rows) == 0)
        finally:
            self._loading.hide()

    def _on_sel(self) -> None:
        row = self._tbl.currentRow()
        has = row >= 0
        for b in (self._btn_aprobar, self._btn_rechazar,
                  self._btn_convertir, self._btn_detalle, self._btn_imprimir):
            b.setEnabled(has)
        if has:
            est_it = self._tbl.item(row, 3)
            est = est_it.text() if est_it else ""
            self._btn_aprobar.setEnabled(est == "pendiente")
            self._btn_rechazar.setEnabled(est == "pendiente")
            self._btn_convertir.setEnabled(est == "aprobada")

    def _get_sel_id(self) -> Optional[int]:
        row = self._tbl.currentRow()
        if row < 0:
            return None
        it = self._tbl.item(row, 0)
        return it.data(Qt.UserRole) if it else None

    # ── Acciones ──────────────────────────────────────────────────────────────

    def _nueva_cotizacion(self) -> None:
        dlg = DialogoNuevaCotizacion(self.conexion, self.usuario_actual, self, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self._cargar_lista()

    def _aprobar(self) -> None:
        cid = self._get_sel_id()
        if not cid:
            return
        if not confirm_action(
            self, "Aprobar cotización",
            "¿Aprobar esta cotización y habilitar su conversión en venta?",
            confirm_text="Aprobar",
            cancel_text="Cancelar",
        ):
            return
        try:
            self.conexion.execute(
                "UPDATE cotizaciones SET estado='aprobada' WHERE id=?", (cid,))
            self.conexion.commit()
            try:
                get_bus().publish("COTIZACION_ACTUALIZADA", {"event_type": "COTIZACION_ACTUALIZADA"})
            except Exception: pass
            QMessageBox.information(self, "✅", "Cotización aprobada.")
            self._cargar_lista()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _rechazar(self) -> None:
        cid = self._get_sel_id()
        if not cid:
            return
        if not confirm_action(
            self, "Rechazar cotización",
            "¿Rechazar esta cotización? Esta acción no elimina trazabilidad.",
            confirm_text="Rechazar",
            cancel_text="Cancelar",
        ):
            return
        try:
            self.conexion.execute(
                "UPDATE cotizaciones SET estado='rechazada' WHERE id=?", (cid,))
            self.conexion.commit()
            self._cargar_lista()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _convertir_en_venta(self) -> None:
        cid = self._get_sel_id()
        if not cid or not self._svc:
            return
        if not confirm_action(
            self, "Convertir en venta",
            "Esta acción crea una venta a partir de la cotización aprobada.\n¿Continuar?",
            confirm_text="Convertir",
            cancel_text="Cancelar",
        ):
            return
        try:
            venta_id = self._svc.convertir_en_venta(cid)
            try:
                from core.services.auto_audit import audit_write
                audit_write(
                    self.container if hasattr(self,'container') else self._svc._container if hasattr(self._svc,'_container') else None,
                    modulo="COTIZACIONES", accion="CONVERTIR_EN_VENTA",
                    entidad="cotizaciones", entidad_id=str(cid),
                    usuario=getattr(self,'usuario_actual','Sistema'),
                    detalles=f"Cotizacion {cid} convertida en venta {venta_id}"
                )
            except Exception: pass
            QMessageBox.information(
                self, "✅ Convertida",
                f"Venta #{venta_id} creada correctamente.")
            self._cargar_lista()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _ver_detalle(self) -> None:
        cid = self._get_sel_id()
        if not cid:
            return
        try:
            row = self.conexion.execute(
                "SELECT * FROM cotizaciones WHERE id=?", (cid,)).fetchone()
            items = self.conexion.execute(
                "SELECT * FROM cotizaciones_detalle WHERE cotizacion_id=?", (cid,)
            ).fetchall()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e)); return
        dlg = DialogoDetalleCotizacion(dict(row), [dict(i) for i in items], parent=self)
        dlg.exec_()

    def _imprimir(self) -> None:
        cid = self._get_sel_id()
        if not cid:
            return
        try:
            from PyQt5.QtWidgets import QFileDialog
            import os, datetime
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")
            ruta, _ = QFileDialog.getSaveFileName(
                self, "Guardar PDF", f"cotizacion_{cid}_{ts}.pdf", "PDF (*.pdf)")
            if not ruta:
                return
            self._generar_pdf_cotizacion(cid, ruta)
            QMessageBox.information(self, "✅", f"PDF guardado:\n{ruta}")
            if os.name == "nt":
                os.startfile(ruta)
        except Exception as e:
            QMessageBox.critical(self, "Error PDF", str(e))


    def _enviar_cotizacion_wa(self) -> None:
        # [spj-dedup] from PyQt5.QtWidgets import QMessageBox
        from PyQt5.QtCore import Qt
        row = self.tabla_cotizaciones.currentRow() if hasattr(self,'tabla_cotizaciones') else -1
        if row < 0:
            QMessageBox.information(self, "Aviso", "Selecciona una cotizacion primero."); return
        try:
            it = self.tabla_cotizaciones.item(row, 0)
            if not it: return
            cot_id = it.data(Qt.UserRole) or it.text()
            sql = ("SELECT c.folio,c.total,c.fecha_vencimiento,cl.nombre,cl.telefono "
                   "FROM cotizaciones c LEFT JOIN clientes cl ON cl.id=c.cliente_id "
                   "WHERE c.id=? OR c.folio=?")
            rd = self.container.db.execute(sql,(cot_id,str(cot_id))).fetchone()
            if not rd: QMessageBox.warning(self,"","Cotizacion no encontrada."); return
            folio,total,venc,nombre_cli,telefono = rd
            if not telefono:
                QMessageBox.warning(self,"Sin telefono",
                    f"El cliente '{nombre_cli}' no tiene telefono."); return
            items = self.container.db.execute(
                "SELECT nombre,cantidad,precio_unitario,subtotal "
                "FROM cotizaciones_detalle WHERE cotizacion_id=?",
                (cot_id,)).fetchall()
            detalle = "\n".join(
                f"• {r[0]} {float(r[1]):.1f}kg x ${float(r[2]):.2f} = ${float(r[3]):.2f}"
                for r in items)
            try:
                nr = self.container.db.execute(
                    "SELECT valor FROM configuraciones WHERE clave='nombre_empresa'"
                ).fetchone()
                neg = nr[0] if nr else "SPJ"
            except Exception: neg = "SPJ"
            msg = (f"Hola {nombre_cli or 'cliente'}, aqui tu cotizacion de {neg}:\n\n"
                   f"Cotizacion {folio}\n{detalle}\n\nTotal: ${float(total):.2f}\n"
                   f"Valida hasta: {str(venc or '')[:10]}\n"
                   f"\nConfirmas tu pedido? Responde SI.")
            wa = getattr(self.container,'whatsapp_service',None)
            if not wa:
                QMessageBox.warning(self,"WhatsApp","Servicio WA no configurado."); return
            wa.send_message(phone_number=telefono, message=msg)
            QMessageBox.information(self,"Enviado",f"Cotizacion {folio} enviada a {nombre_cli}.")
        except Exception as e:
            QMessageBox.critical(self,"Error",str(e))

    def _generar_pdf_cotizacion(self, cid: int, ruta: str) -> None:
        row   = self.conexion.execute(
            "SELECT * FROM cotizaciones WHERE id=?", (cid,)).fetchone()
        items = self.conexion.execute(
            "SELECT * FROM cotizaciones_detalle WHERE cotizacion_id=?", (cid,)
        ).fetchall()
        row = dict(row); items = [dict(i) for i in items]
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib import colors
            from reportlab.platypus import (
                SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer)
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import cm
            doc  = SimpleDocTemplate(ruta, pagesize=A4)
            styles = getSampleStyleSheet()
            story = []
            story.append(Paragraph(f"<b>COTIZACIÓN {row['folio']}</b>", styles["Title"]))
            story.append(Paragraph(
                f"Cliente: {row.get('cliente_nombre','—')}  |  "
                f"Vigencia: {row.get('vigencia_dias',7)} días  |  "
                f"Vence: {row.get('fecha_vencimiento','—')}",
                styles["Normal"]))
            story.append(Spacer(1, 0.5*cm))
            data = [["Producto", "Cantidad", "Unidad", "Precio U.", "Subtotal"]]
            for it in items:
                data.append([
                    it.get("nombre", ""),
                    f"{float(it.get('cantidad',0)):.3f}",
                    it.get("unidad", "kg"),
                    f"${float(it.get('precio_unitario',0)):.2f}",
                    f"${float(it.get('subtotal',0)):.2f}",
                ])
            data.append(["", "", "", "TOTAL:", f"${float(row.get('total',0)):.2f}"])
            t = Table(data, colWidths=[8*cm, 2.5*cm, 2*cm, 2.5*cm, 2.5*cm])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#2980b9")),
                ("TEXTCOLOR",  (0,0), (-1,0), colors.white),
                ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
                ("GRID",       (0,0), (-1,-1), 0.5, colors.grey),
                ("ALIGN",      (1,1), (-1,-1), "RIGHT"),
                ("FONTNAME",   (0,-1), (-1,-1), "Helvetica-Bold"),
            ]))
            story.append(t)
            if row.get("notas"):
                story.append(Spacer(1, 0.3*cm))
                story.append(Paragraph(f"<b>Notas:</b> {row['notas']}", styles["Normal"]))
            doc.build(story)
        except ImportError:
            # Fallback TXT si no hay reportlab
            with open(ruta.replace(".pdf", ".txt"), "w", encoding="utf-8") as f:
                f.write(f"COTIZACIÓN {row['folio']}\n")
                f.write(f"Cliente: {row.get('cliente_nombre','—')}\n")
                f.write(f"Total: ${float(row.get('total',0)):.2f}\n\n")
                for it in items:
                    f.write(f"  {it.get('nombre')} x {it.get('cantidad')} = ${it.get('subtotal'):.2f}\n")

    def _vencer_expiradas(self) -> None:
        if not self._svc:
            return
        try:
            n = self._svc.vencer_expiradas()
            msg = f"{n} cotización(es) marcada(s) como vencida." if n else "Sin cotizaciones expiradas."
            QMessageBox.information(self, "Vencidas", msg)
            self._cargar_lista()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


# ── Diálogo Nueva Cotización ──────────────────────────────────────────────────

class DialogoNuevaCotizacion(QDialog):

    def __init__(self, db, usuario: str, modulo, parent=None):
        super().__init__(parent)
        self._db     = db
        self._usuario = usuario
        self._modulo  = modulo
        self._items: List[Dict] = []
        self.setWindowTitle("Nueva Cotización / Presupuesto")
        self.setMinimumWidth(700); self.setMinimumHeight(560)
        self._build()

    def _build(self) -> None:
        lay = QVBoxLayout(self)

        # Cliente
        grp_cli = QGroupBox("Cliente")
        fl = QFormLayout(grp_cli)
        self._txt_cliente = QLineEdit(); self._txt_cliente.setPlaceholderText("Nombre del cliente o empresa")
        self._txt_notas   = QTextEdit(); self._txt_notas.setMaximumHeight(50)
        self._txt_notas.setPlaceholderText("Notas o condiciones de la cotización…")
        self._spin_vigencia = QSpinBox(); self._spin_vigencia.setRange(1, 90); self._spin_vigencia.setValue(7)
        self._spin_vigencia.setSuffix(" días")
        fl.addRow("Cliente / Empresa*:", self._txt_cliente)
        fl.addRow("Vigencia:",           self._spin_vigencia)
        fl.addRow("Notas:",              self._txt_notas)
        lay.addWidget(grp_cli)

        # Ítems
        grp_items = QGroupBox("Productos a cotizar")
        gl = QVBoxLayout(grp_items)
        self._tbl = QTableWidget()
        self._tbl.setColumnCount(5)
        self._tbl.setHorizontalHeaderLabels(
            ["Producto", "Cantidad", "Unidad", "Precio Unit. ($)", "Subtotal ($)"])
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setAlternatingRowColors(True)
        hdr = self._tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1,2,3,4): hdr.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        gl.addWidget(self._tbl)

        # Agregar ítem
        ar = QHBoxLayout()
        self._cmb_prod = QComboBox(); self._cmb_prod.setMinimumWidth(200)
        self._cargar_productos()
        self._cmb_prod.currentIndexChanged.connect(self._on_prod_change)
        self._spin_qty   = QDoubleSpinBox(); self._spin_qty.setRange(0.001, 99999); self._spin_qty.setDecimals(3)
        self._spin_precio = QDoubleSpinBox(); self._spin_precio.setRange(0, 999999); self._spin_precio.setDecimals(2)
        self._spin_precio.setPrefix("$")
        btn_add = create_primary_button(self, "➕ Agregar", "Agregar producto a la cotización")
        btn_add.clicked.connect(self._agregar_item)
        btn_rm  = create_secondary_button(self, "🗑 Quitar", "Quitar producto seleccionado")
        btn_rm.clicked.connect(self._quitar_item)
        for w in (QLabel("Producto:"), self._cmb_prod, QLabel("Cant:"),
                  self._spin_qty, QLabel("Precio:"), self._spin_precio, btn_add, btn_rm):
            ar.addWidget(w)
        gl.addLayout(ar)
        lay.addWidget(grp_items)

        # Total
        self._lbl_total = QLabel("Total estimado: $0.00")
        self._lbl_total.setObjectName("subheading")
        lay.addWidget(self._lbl_total)

        # Botones
        bl = QHBoxLayout()
        btn_ok = create_success_button(self, "📋 Crear Cotización", "Crear nueva cotización con los productos agregados")
        btn_ok.clicked.connect(self._crear)
        btn_no = create_secondary_button(self, "Cancelar", "Cerrar sin crear cotización")
        btn_no.clicked.connect(self.reject)
        bl.addStretch(); bl.addWidget(btn_ok); bl.addWidget(btn_no)
        lay.addLayout(bl)

    def _cargar_productos(self) -> None:
        self._cmb_prod.clear()
        self._cmb_prod.addItem("— Seleccionar producto —", None)
        try:
            rows = self._db.execute(
                "SELECT id, nombre, precio, unidad FROM productos WHERE activo=1 ORDER BY nombre"
            ).fetchall()
            for r in rows:
                self._cmb_prod.addItem(f"{r[1]} (${float(r[2]):.2f}/{r[3] or 'kg'})", r[0])
                self._cmb_prod.setItemData(self._cmb_prod.count()-1, {
                    "precio": float(r[2]), "unidad": r[3] or "kg"
                }, Qt.UserRole+1)
        except Exception:
            pass

    def _on_prod_change(self, idx: int) -> None:
        datos = self._cmb_prod.itemData(idx, Qt.UserRole+1)
        if datos:
            self._spin_precio.setValue(datos.get("precio", 0))

    def _agregar_item(self) -> None:
        prod_id = self._cmb_prod.currentData()
        if not prod_id:
            return
        qty    = self._spin_qty.value()
        precio = self._spin_precio.value()
        nombre = self._cmb_prod.currentText().split(" ($")[0]
        datos  = self._cmb_prod.currentData(Qt.UserRole+1) or {}
        if any(i["producto_id"] == prod_id for i in self._items):
            QMessageBox.warning(self, "Dup.", "Ese producto ya está en la lista."); return
        self._items.append({
            "producto_id":    prod_id,
            "nombre":         nombre,
            "cantidad":       qty,
            "precio_unitario": precio,
            "unidad":         datos.get("unidad", "kg"),
        })
        self._refrescar_tabla()

    def _quitar_item(self) -> None:
        row = self._tbl.currentRow()
        if row >= 0:
            self._items.pop(row); self._refrescar_tabla()

    def _refrescar_tabla(self) -> None:
        self._tbl.setRowCount(len(self._items))
        total = 0.0
        for ri, it in enumerate(self._items):
            sub = round(it["cantidad"] * it["precio_unitario"], 2)
            total += sub
            for ci, v in enumerate([
                it["nombre"], f"{it['cantidad']:.3f}", it["unidad"],
                f"${it['precio_unitario']:.2f}", f"${sub:.2f}"
            ]):
                item = QTableWidgetItem(str(v))
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                if ci > 0:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self._tbl.setItem(ri, ci, item)
        self._lbl_total.setText(f"Total estimado: ${total:.2f}")

    def _crear(self) -> None:
        cliente = self._txt_cliente.text().strip()
        if not cliente:
            QMessageBox.warning(self, "Aviso", "Escribe el nombre del cliente."); return
        if not self._items:
            QMessageBox.warning(self, "Aviso", "Agrega al menos un producto."); return
        try:
            svc = self._modulo._svc
            result = svc.crear(
                items=self._items,
                cliente_nombre=cliente,
                notas=self._txt_notas.toPlainText().strip(),
                vigencia_dias=self._spin_vigencia.value(),
            )
            QMessageBox.information(
                self, "✅ Cotización creada",
                f"Folio: {result['folio']}\n"
                f"Total: ${result['total']:.2f}\n"
                f"Vence: {result['vencimiento']}"
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


# ── Diálogo Detalle ───────────────────────────────────────────────────────────

class DialogoDetalleCotizacion(QDialog):

    def __init__(self, cotizacion: Dict, items: List[Dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Detalle — {cotizacion.get('folio','')}")
        self.setMinimumWidth(580)
        lay = QVBoxLayout(self)

        info = QGroupBox("Datos de la Cotización")
        il = QFormLayout(info)
        for label, key in [
            ("Folio", "folio"), ("Cliente", "cliente_nombre"),
            ("Estado", "estado"), ("Total", "total"),
            ("Vigencia", "vigencia_dias"), ("Vencimiento", "fecha_vencimiento"),
            ("Notas", "notas"), ("Usuario", "usuario"),
        ]:
            val = str(cotizacion.get(key, "—") or "—")
            if key == "total": val = f"${float(cotizacion.get(key,0)):.2f}"
            if key == "vigencia_dias": val = f"{val} días"
            il.addRow(f"{label}:", QLabel(val))
        lay.addWidget(info)

        grp = QGroupBox("Productos")
        gl = QVBoxLayout(grp)
        tbl = QTableWidget(); tbl.setColumnCount(5)
        tbl.setHorizontalHeaderLabels(
            ["Producto", "Cantidad", "Unidad", "Precio U.", "Subtotal"])
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.verticalHeader().setVisible(False)
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.setRowCount(len(items))
        for ri, it in enumerate(items):
            for ci, v in enumerate([
                it.get("nombre",""),
                f"{float(it.get('cantidad',0)):.3f}",
                it.get("unidad","kg"),
                f"${float(it.get('precio_unitario',0)):.2f}",
                f"${float(it.get('subtotal',0)):.2f}",
            ]):
                t = QTableWidgetItem(v)
                t.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                if ci > 0: t.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                tbl.setItem(ri, ci, t)
        gl.addWidget(tbl); lay.addWidget(grp)
        btn = QPushButton("Cerrar"); btn.setObjectName("secondaryBtn"); btn.clicked.connect(self.accept)
        lay.addWidget(btn)
