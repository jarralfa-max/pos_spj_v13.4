# modulos/compras_pro.py — SPJ POS v13.2
"""
Compras a Proveedores.
  - Busca productos por nombre, código, barcode o ID
  - Carrito editable (doble clic = editar, botón = eliminar)
  - Alerta si el costo varía >20% respecto al histórico
  - Procesa recetas al ingresar insumos que tengan receta
  - Auto-refresca lista de productos via EventBus
"""
from __future__ import annotations

from modulos.design_tokens import Colors, Spacing, Typography, Borders
from modulos.ui_components import (
    create_primary_button, create_success_button, create_secondary_button,
    create_danger_button, create_input, create_combo, create_card,
    create_heading, create_subheading, create_caption, apply_tooltip
)
from modulos.spj_refresh_mixin import RefreshMixin
from core.services.auto_audit import audit_write
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QComboBox, QLineEdit, QPushButton, QDoubleSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QMessageBox, QInputDialog, QTabWidget, QMenu, QAction, QSizePolicy,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QCursor
from datetime import datetime
import logging

logger = logging.getLogger("spj.compras")


class ModuloComprasPro(QWidget, RefreshMixin):
    """Módulo Enterprise para Recepción de Mercancía."""

    def __init__(self, container, parent=None):
        super().__init__(parent)
        self.container       = container
        self.sucursal_id     = 1
        self.usuario_actual  = ""
        self.carrito_compra: list[dict] = []

        # EventBus: auto-refresh when products or purchases change
        try:
            self._init_refresh(container, [
                "COMPRA_REGISTRADA", "RECEPCION_CONFIRMADA",
                "PRODUCTO_CREADO",   "PRODUCTO_ACTUALIZADO",
                "PROVEEDOR_CREADO",  "PROVEEDOR_ACTUALIZADO",
            ])
        except Exception:
            pass

        self._build_ui()
        QTimer.singleShot(200, self.cargar_proveedores)

    # ── Propagation ──────────────────────────────────────────────────────────
    def set_sucursal(self, sucursal_id: int, nombre: str = "") -> None:
        self.sucursal_id = sucursal_id
        self.cargar_proveedores()
        # Update ProductSearchWidget db ref (same connection, already live)
        if hasattr(self, '_buscador'):
            self._buscador.set_db(self.container.db)

    def set_usuario_actual(self, usuario: str, rol: str = "") -> None:
        self.usuario_actual = usuario

    def _on_refresh(self, event_type: str, data: dict) -> None:
        """Auto-refresh: update product search and provider list."""
        if hasattr(self, '_buscador'):
            self._buscador.set_db(self.container.db)  # re-point to live DB
        self.cargar_proveedores()

    # ── UI ───────────────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)

        # Tabs: Tradicional | QR
        self._tabs = QTabWidget()
        root.addWidget(self._tabs)

        tab_trad = QWidget()
        self._tabs.addTab(tab_trad, "🛒 Compra Tradicional")
        self._build_tab_tradicional(tab_trad)

        tab_qr = QWidget()
        self._tabs.addTab(tab_qr, "📦 Recepción con QR")
        self._build_tab_qr(tab_qr)

        tab_hist = QWidget()
        self._tabs.addTab(tab_hist, "📋 Historial de Compras")
        self._build_tab_historial(tab_hist)

        self._tabs.currentChanged.connect(self._on_tab_change)

    def _build_tab_tradicional(self, parent: QWidget) -> None:
        lay = QVBoxLayout(parent)
        lay.setSpacing(8)

        # ── Encabezado del documento ──────────────────────────────────────────
        grp_doc = QGroupBox("📄 Datos del Documento")
        grp_doc.setObjectName("styledGroup")
        form = QFormLayout(grp_doc)

        self.cmb_proveedor = create_combo(self, min_width=260)

        self.txt_factura = QLineEdit()
        self.txt_factura.setPlaceholderText("Ej. FAC-001 / REM-00129 (opcional)")

        # Sucursal destino — ¿a qué almacén llega esta mercancía?
        self.cmb_sucursal_destino = QComboBox()
        self.cmb_sucursal_destino.setToolTip(
            "Sucursal a la que ingresará el inventario de esta compra")
        self._cargar_sucursales_compra()

        form.addRow("Proveedor:*", self.cmb_proveedor)
        form.addRow("No. Factura/Remisión:", self.txt_factura)
        form.addRow("Sucursal destino:*", self.cmb_sucursal_destino)
        lay.addWidget(grp_doc)

        # ── Buscador con scanner ──────────────────────────────────────────────
        from modulos.spj_product_search import ProductSearchWidget
        self._buscador = ProductSearchWidget(
            db=self.container.db,
            placeholder="🔍 Buscar por nombre, código interno, ID o escanear barcode...",
            show_stock=True,
        )
        self._buscador.producto_seleccionado.connect(self._agregar_producto)
        lay.addWidget(self._buscador)

        # ── Carrito editable ──────────────────────────────────────────────────
        grp_cart = QGroupBox("🛒 Carrito de compra  "
                             "(doble clic = editar · clic derecho = opciones)")
        grp_cart.setObjectName("styledGroup")
        cart_lay = QVBoxLayout(grp_cart)

        self.tabla = QTableWidget()
        self.tabla.setColumnCount(6)
        self.tabla.setHorizontalHeaderLabels(
            ["ID", "Producto", "Cantidad", "Costo Unit.", "Subtotal", ""])
        hh = self.tabla.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        for c in (0, 2, 3, 4, 5):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.doubleClicked.connect(self._editar_fila)
        self.tabla.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tabla.customContextMenuRequested.connect(self._menu_fila)
        self.tabla.setObjectName("tableView")
        cart_lay.addWidget(self.tabla)

        # Toolbar del carrito
        cart_tb = QHBoxLayout()
        btn_clear = create_danger_button(self, "🗑 Limpiar carrito", "Vaciar carrito de compras")
        btn_clear.clicked.connect(self._limpiar_carrito)
        cart_tb.addWidget(btn_clear)
        cart_tb.addStretch()

        self.lbl_total = QLabel("Total: $0.00")
        self.lbl_total.setObjectName("heading")
        cart_tb.addWidget(self.lbl_total)
        cart_lay.addLayout(cart_tb)
        lay.addWidget(grp_cart)

        # ── Footer: forma de pago + procesar ─────────────────────────────────
        footer = QHBoxLayout()
        self.cmb_pago = create_combo(self)
        self.cmb_pago.addItems([
            "CONTADO (Efectivo)", "CREDITO (Cuentas por Pagar)",
            "TRANSFERENCIA", "CHEQUE",
        ])

        btn_proc = create_success_button(self, "📥 PROCESAR COMPRA E INGRESAR AL INVENTARIO", 
                                         "Procionar compra y actualizar inventario")
        btn_proc.clicked.connect(self._procesar_compra)

        footer.addWidget(QLabel("Pago:"))
        footer.addWidget(self.cmb_pago)
        footer.addStretch()
        footer.addWidget(btn_proc)
        lay.addLayout(footer)

    def _build_tab_qr(self, parent: QWidget) -> None:
        from PyQt5.QtWidgets import QVBoxLayout
        from modulos.recepcion_qr_widget import RecepcionQRWidget
        lay = QVBoxLayout(parent)
        lay.setContentsMargins(0, 0, 0, 0)
        self._recv_qr = RecepcionQRWidget(
            conexion=self.container.db,
            sucursal_id=self.sucursal_id,
            usuario=self.usuario_actual or "Sistema",
            parent=parent,
        )
        lay.addWidget(self._recv_qr)

    # ── Providers ────────────────────────────────────────────────────────────
    def _cargar_sucursales_compra(self) -> None:
        """Carga sucursales activas. La del usuario corriente queda seleccionada por defecto."""
        try:
            self.cmb_sucursal_destino.clear()
            rows = self.container.db.execute(
                "SELECT id, nombre FROM sucursales WHERE activo=1 ORDER BY nombre"
            ).fetchall()
            if rows:
                for r in rows:
                    pid  = r['id']     if hasattr(r,'keys') else r[0]
                    name = r['nombre'] if hasattr(r,'keys') else r[1]
                    self.cmb_sucursal_destino.addItem(str(name), pid)
                # Select the user's current branch by default
                for i in range(self.cmb_sucursal_destino.count()):
                    if self.cmb_sucursal_destino.itemData(i) == self.sucursal_id:
                        self.cmb_sucursal_destino.setCurrentIndex(i)
                        break
            else:
                # No sucursales table or empty — add default
                self.cmb_sucursal_destino.addItem("Sucursal Principal", 1)
        except Exception:
            self.cmb_sucursal_destino.clear()
            self.cmb_sucursal_destino.addItem("Sucursal Principal", 1)

    def cargar_proveedores(self) -> None:
        try:
            prev = self.cmb_proveedor.currentData()
            self.cmb_proveedor.clear()
            rows = self.container.db.execute(
                "SELECT id, nombre FROM proveedores WHERE activo=1 ORDER BY nombre"
            ).fetchall()
            for r in rows:
                self.cmb_proveedor.addItem(r['nombre'], r['id'])
            # Restore selection
            if prev:
                for i in range(self.cmb_proveedor.count()):
                    if self.cmb_proveedor.itemData(i) == prev:
                        self.cmb_proveedor.setCurrentIndex(i)
                        break
        except Exception as e:
            logger.debug("cargar_proveedores: %s", e)

    # ── Cart management ───────────────────────────────────────────────────────
    def _agregar_producto(self, prod: dict) -> None:
        """Agrega producto al carrito con validación de precio y duplicados."""
        nombre = prod.get('nombre', '')
        costo_hist = float(prod.get('precio_compra', 0) or 0)

        # Check if already in cart → offer to update quantity instead
        for i, item in enumerate(self.carrito_compra):
            if item['producto_id'] == prod['id']:
                resp = QMessageBox.question(
                    self, "Producto ya en carrito",
                    f"'{nombre}' ya está en el carrito.\n¿Agregar más cantidad?",
                    QMessageBox.Yes | QMessageBox.No)
                if resp == QMessageBox.Yes:
                    extra, ok = QInputDialog.getDouble(
                        self, "Cantidad adicional",
                        f"¿Cuántas unidades adicionales de '{nombre}'?",
                        value=1.0, min=0.001, max=99999.0, decimals=3)
                    if ok:
                        self.carrito_compra[i]['cantidad'] += extra
                        self.carrito_compra[i]['subtotal'] = (
                            self.carrito_compra[i]['cantidad'] *
                            self.carrito_compra[i]['costo_unitario'])
                        self._refresh_tabla()
                return

        # Ask quantity
        cantidad, ok = QInputDialog.getDouble(
            self, "Cantidad recibida",
            f"¿Cuántas unidades de '{nombre}' llegaron?",
            value=1.0, min=0.001, max=99999.0, decimals=3)
        if not ok:
            return

        # Ask cost (prefilled with historical)
        costo, ok2 = QInputDialog.getDouble(
            self, "Costo unitario",
            f"Costo unitario de '{nombre}':",
            value=costo_hist, min=0.0, max=999999.0, decimals=4)
        if not ok2:
            return

        # Price variance alert ≥ 20%
        if costo_hist > 0 and costo > 0:
            variacion = abs(costo - costo_hist) / costo_hist * 100
            if variacion >= 20:
                dir_txt = "▲ SUBIÓ" if costo > costo_hist else "▼ BAJÓ"
                msg = (f"VARIACION DE PRECIO: {nombre}\n"
                       f"Anterior: ${costo_hist:.2f}  Nuevo: ${costo:.2f}\n"
                       f"{dir_txt} {variacion:.1f}% — ¿Confirmar?")
                if QMessageBox.question(self, "Alerta de Precio", msg,
                                        QMessageBox.Yes | QMessageBox.No) == QMessageBox.No:
                    return
                try:
                    audit_write(self.container, modulo="COMPRAS",
                                accion="VARIACION_PRECIO", entidad="productos",
                                entidad_id=str(prod['id']),
                                usuario=self.usuario_actual,
                                detalles=f"{nombre}: ${costo_hist:.2f}→${costo:.2f} ({dir_txt} {variacion:.1f}%)",
                                before={"precio_compra": costo_hist},
                                after={"precio_compra": costo},
                                sucursal_id=self.sucursal_id)
                except Exception:
                    pass

        self.carrito_compra.append({
            'producto_id':     prod['id'],
            'nombre':          nombre,
            'cantidad':        cantidad,
            'costo_unitario':  costo,
            'subtotal':        round(cantidad * costo, 4),
            'precio_historico': costo_hist,
        })
        self._refresh_tabla()
        self._buscador.clear()

    def _editar_fila(self, index) -> None:
        """Doble clic: edita cantidad y costo del ítem."""
        row = index.row()
        if row < 0 or row >= len(self.carrito_compra):
            return
        item = self.carrito_compra[row]

        cantidad, ok1 = QInputDialog.getDouble(
            self, "Editar cantidad",
            f"Nueva cantidad para '{item['nombre']}':",
            value=item['cantidad'], min=0.001, max=99999.0, decimals=3)
        if not ok1:
            return

        costo, ok2 = QInputDialog.getDouble(
            self, "Editar costo",
            f"Nuevo costo unitario para '{item['nombre']}':",
            value=item['costo_unitario'], min=0.0, max=999999.0, decimals=4)
        if not ok2:
            return

        self.carrito_compra[row]['cantidad']       = cantidad
        self.carrito_compra[row]['costo_unitario'] = costo
        self.carrito_compra[row]['subtotal']       = round(cantidad * costo, 4)
        self._refresh_tabla()

    def _menu_fila(self, pos) -> None:
        """Clic derecho: menú contextual por fila."""
        row = self.tabla.rowAt(pos.y())
        if row < 0:
            return
        menu = QMenu(self)
        act_edit = menu.addAction("✏️ Editar cantidad / costo")
        act_del  = menu.addAction("🗑 Eliminar del carrito")
        act = menu.exec_(QCursor.pos())
        if act == act_edit:
            self.tabla.doubleClicked.emit(self.tabla.model().index(row, 0))
        elif act == act_del:
            self.carrito_compra.pop(row)
            self._refresh_tabla()

    def _limpiar_carrito(self) -> None:
        if not self.carrito_compra:
            return
        if QMessageBox.question(self, "Limpiar", "¿Limpiar todo el carrito?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.carrito_compra.clear()
            self._refresh_tabla()

    def _refresh_tabla(self) -> None:
        """Reconstruye la tabla del carrito con botones de eliminar por fila."""
        self.tabla.setRowCount(0)
        total = 0.0
        for row, item in enumerate(self.carrito_compra):
            self.tabla.insertRow(row)
            vals = [
                str(item['producto_id']),
                item['nombre'],
                f"{item['cantidad']:.3f}",
                f"${item['costo_unitario']:.4f}",
                f"${item['subtotal']:.2f}",
            ]
            for col, val in enumerate(vals):
                it = QTableWidgetItem(val)
                it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self.tabla.setItem(row, col, it)

            # Delete button in last column
            btn_del = create_danger_button(self, "✕", "Eliminar producto del carrito")
            btn_del.setFixedWidth(36)
            btn_del.clicked.connect(lambda _, r=row: self._eliminar_fila(r))
            self.tabla.setCellWidget(row, 5, btn_del)
            total += item['subtotal']

        self.lbl_total.setText(f"Total: ${total:,.2f}")

    def _eliminar_fila(self, row: int) -> None:
        if 0 <= row < len(self.carrito_compra):
            self.carrito_compra.pop(row)
            self._refresh_tabla()

    # ── Process purchase ─────────────────────────────────────────────────────
    def _procesar_compra(self) -> None:
        if not self.carrito_compra:
            QMessageBox.warning(self, "Aviso", "El carrito está vacío.")
            return
        if self.cmb_proveedor.currentIndex() < 0:
            QMessageBox.warning(self, "Aviso", "Selecciona un proveedor.")
            return

        proveedor_id  = self.cmb_proveedor.currentData()
        proveedor_nom = self.cmb_proveedor.currentText()
        doc_ref = self.txt_factura.text().strip() or "Sin Ref"
        pago    = ("CREDITO" if "CREDITO" in self.cmb_pago.currentText()
                   else self.cmb_pago.currentText().split()[0])
        total   = sum(i['subtotal'] for i in self.carrito_compra)

        # Check for recipes among purchased items
        items_con_receta = self._detectar_recetas()

        # Show detailed summary dialog before processing
        if not self._mostrar_resumen_compra(proveedor_nom, doc_ref, pago, total, items_con_receta):
            return

        try:
            # Build items in format expected by PurchaseService
            items_svc = [
                {
                    'product_id': i['producto_id'],
                    'qty':        i['cantidad'],
                    'unit_cost':  i['costo_unitario'],
                    'nombre':     i['nombre'],
                }
                for i in self.carrito_compra
            ]

            svc = getattr(self.container, 'purchase_service', None)
            if not svc:
                raise RuntimeError(
                    "PurchaseService no disponible.\n"
                    "Reinicia la aplicación o contacta al administrador.")
            branch_dest = (self.cmb_sucursal_destino.currentData()
                           if hasattr(self, 'cmb_sucursal_destino')
                           else self.sucursal_id) or self.sucursal_id
            folio = svc.register_purchase(
                provider_id=proveedor_id,
                branch_id=branch_dest,
                user=self.usuario_actual,
                items=items_svc,
                payment_method=pago,
                amount_paid=(total if pago != "CREDITO" else 0),
                notes=doc_ref,
            )

            # ── Actualización de existencia via ApplicationService ──────────
            app_svc = getattr(self.container, 'app_service', None)
            for _item in items_svc:
                try:
                    if app_svc:
                        app_svc.registrar_compra(
                            producto_id=_item['product_id'],
                            cantidad=_item['qty'],
                            costo_unitario=_item['unit_cost'],
                            usuario=self.usuario_actual,
                            referencia=doc_ref,
                            sucursal_id=branch_dest,
                            proveedor_id=proveedor_id)
                    else:
                        self.container.db.execute(
                            "UPDATE productos SET existencia = existencia + ?, "
                            "precio_compra = ? WHERE id = ?",
                            (_item['qty'], _item['unit_cost'], _item['product_id'])
                        )
                except Exception as _e:
                    import logging as _lg
                    _lg.getLogger(__name__).error(
                        "Direct stock update failed prod=%s: %s",
                        _item['product_id'], _e)

            # Process recipes for purchased items
            recetas_procesadas = []
            if items_con_receta:
                recetas_procesadas = self._procesar_recetas(items_con_receta)

            # Audit
            try:
                audit_write(self.container, modulo="COMPRAS",
                            accion="COMPRA_REGISTRADA", entidad="compras",
                            entidad_id=str(folio),
                            usuario=self.usuario_actual,
                            detalles=(f"Folio {folio} | {proveedor_nom} | "
                                      f"${total:.2f} | {pago}"),
                            sucursal_id=self.sucursal_id)
            except Exception:
                pass

            msg_ok = f"Compra registrada.\nFolio: {folio}"
            if recetas_procesadas:
                msg_ok += f"\n\n✅ Recetas procesadas: {', '.join(recetas_procesadas)}"
            QMessageBox.information(self, "✅ Éxito", msg_ok)

            # Clear UI
            self.carrito_compra.clear()
            self._refresh_tabla()
            self.txt_factura.clear()

        except Exception as e:
            QMessageBox.critical(self, "Error al procesar", str(e))
            logger.error("_procesar_compra: %s", e)

    def _mostrar_resumen_compra(self, proveedor: str, doc_ref: str,
                                pago: str, total: float,
                                items_receta: list) -> bool:
        """
        Muestra diálogo de resumen antes de procesar la compra.
        Retorna True si el usuario confirma, False si cancela.
        """
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QHBoxLayout

        dlg = QDialog(self)
        dlg.setWindowTitle("Confirmar Compra")
        dlg.setMinimumWidth(480)
        lay = QVBoxLayout(dlg)

        # Summary HTML
        rows = ""
        for it in self.carrito_compra:
            rows += (f"<tr><td>{it['nombre']}</td>"
                     f"<td align='right'>{it['cantidad']:.3f}</td>"
                     f"<td align='right'>${it['costo_unitario']:.4f}</td>"
                     f"<td align='right'>${it['subtotal']:.2f}</td></tr>")

        receta_aviso = ""
        if items_receta:
            nombres = ", ".join(i['nombre'] for i in items_receta)
            receta_aviso = (f"<p style='background:#fffbea;padding:6px;border-radius:4px;'>"
                            f"<b>Productos con receta:</b> {nombres}<br>"
                            f"Se procesará la producción automáticamente.</p>")

        html = f"""<html><body style='font-family:sans-serif;font-size:12px;'>
        <h3>Resumen de Compra</h3>
        <p><b>Proveedor:</b> {proveedor} &nbsp;|&nbsp;
           <b>Ref:</b> {doc_ref} &nbsp;|&nbsp;
           <b>Pago:</b> {pago}</p>
        <table width='100%' cellspacing='4' style='border-collapse:collapse;'>
        <tr style='background:#2c3e50;color:white;'>
          <th align='left' style='padding:4px;'>Producto</th>
          <th style='padding:4px;'>Cantidad</th>
          <th style='padding:4px;'>Costo Unit.</th>
          <th style='padding:4px;'>Subtotal</th></tr>
        {rows}
        </table>
        <hr>
        <p style='font-size:14px;font-weight:bold;'>
          Total: ${total:,.2f}</p>
        {receta_aviso}
        </body></html>"""

        browser = QTextBrowser()
        browser.setHtml(html)
        browser.setMinimumHeight(300)
        lay.addWidget(browser)

        btn_row = QHBoxLayout()
        btn_cancel = create_secondary_button(self, "✕ Cancelar", "Cancelar y cerrar")
        btn_ok = create_success_button(self, "✅ Confirmar y Procesar", "Confirmar edición de compra")
        btn_cancel.clicked.connect(dlg.reject)
        btn_ok.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_cancel); btn_row.addStretch(); btn_row.addWidget(btn_ok)
        lay.addLayout(btn_row)

        return dlg.exec_() == QDialog.Accepted

    def _detectar_recetas(self) -> list[dict]:
        """Retorna los ítems del carrito que tienen receta registrada."""
        result = []
        try:
            for item in self.carrito_compra:
                r = self.container.db.execute(
                    """SELECT COUNT(*) as n FROM recetas
                       WHERE producto_id=? AND activa=1""",
                    (item['producto_id'],)
                ).fetchone()
                if r and r['n'] > 0:
                    result.append(item)
        except Exception:
            pass
        return result

    def _procesar_recetas(self, items: list[dict]) -> list[str]:
        """Ejecuta la receta de cada producto comprado que la tenga."""
        nombres = []
        for item in items:
            try:
                # Use RecipeEngine if available
                engine = getattr(self.container, 'recipe_engine', None)
                if engine and hasattr(engine, 'ejecutar_receta'):
                    engine.ejecutar_receta(
                        producto_id=item['producto_id'],
                        cantidad=item['cantidad'],
                        usuario=self.usuario_actual,
                        sucursal_id=self.sucursal_id,
                    )
                    nombres.append(item['nombre'])
                else:
                    # Fallback: use canonical product_recipe_components
                    receta = self.container.db.execute("""
                        SELECT rc.component_product_id AS insumo_id,
                               COALESCE(rc.cantidad, 0) AS cantidad_insumo,
                               p.nombre AS insumo_nombre
                        FROM product_recipe_components rc
                        JOIN product_recipes r ON r.id = rc.recipe_id
                        JOIN productos p ON p.id = rc.component_product_id
                        WHERE r.base_product_id=? AND r.is_active=1
                    """, (item['producto_id'],)).fetchall()
                    if receta:
                        _app = getattr(self.container, 'app_service', None)
                        for comp in receta:
                            consumo = float(comp['cantidad_insumo'] or 0) * item['cantidad']
                            if consumo > 0:
                                if _app:
                                    _app.registrar_salida_produccion(
                                        producto_id=comp['insumo_id'],
                                        cantidad=consumo,
                                        usuario=getattr(self, 'usuario_actual', ''),
                                        sucursal_id=self.sucursal_id)
                                else:
                                    self.container.db.execute(
                                        "UPDATE productos SET existencia=existencia-? WHERE id=?",
                                        (consumo, comp['insumo_id']))
                        try: self.container.db.commit()
                        except Exception: pass
                        nombres.append(item['nombre'])
            except Exception as e:
                logger.warning("_procesar_recetas %s: %s", item['nombre'], e)
        return nombres

    def _on_tab_change(self, idx: int) -> None:
        if idx == 2:  # Historial tab
            self._cargar_historial_compras()

    def _build_tab_historial(self, parent: QWidget) -> None:
        """Tab con historial de todas las compras a proveedores."""
        lay = QVBoxLayout(parent)
        lay.setContentsMargins(8, 8, 8, 8)

        # Toolbar
        hdr = QHBoxLayout()
        lbl = create_subheading(self, "Historial de Compras a Proveedores")
        hdr.addWidget(lbl)
        hdr.addStretch()

        from PyQt5.QtWidgets import QDateEdit
        from PyQt5.QtCore import QDate
        self._hist_desde = QDateEdit(QDate.currentDate().addDays(-30))
        self._hist_desde.setCalendarPopup(True)
        self._hist_hasta = QDateEdit(QDate.currentDate())
        self._hist_hasta.setCalendarPopup(True)
        btn_ref = create_primary_button(self, "🔄 Actualizar", "Actualizar historial de compras")
        btn_ref.clicked.connect(self._cargar_historial_compras)
        hdr.addWidget(QLabel("Desde:"))
        hdr.addWidget(self._hist_desde)
        hdr.addWidget(QLabel("Hasta:"))
        hdr.addWidget(self._hist_hasta)
        hdr.addWidget(btn_ref)
        lay.addLayout(hdr)

        # Table
        self._tbl_hist = QTableWidget()
        self._tbl_hist.setColumnCount(7)
        self._tbl_hist.setHorizontalHeaderLabels(
            ["Folio", "Fecha", "Proveedor", "Usuario", "Total", "Estado", ""])
        hh = self._tbl_hist.horizontalHeader()
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        for c in (0,1,3,4,5,6):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self._tbl_hist.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_hist.setAlternatingRowColors(True)
        self._tbl_hist.verticalHeader().setVisible(False)
        self._tbl_hist.setObjectName("tableView")
        lay.addWidget(self._tbl_hist)

        # KPI bar
        kpi_row = QHBoxLayout()
        self.lbl_hist_total_compras = QLabel("Total período: $0.00")
        self.lbl_hist_total_compras.setObjectName("badgeSuccess")
        self.lbl_hist_num_compras = QLabel("0 compras")
        self.lbl_hist_num_compras.setObjectName("badgeInfo")
        kpi_row.addWidget(self.lbl_hist_total_compras)
        kpi_row.addWidget(self.lbl_hist_num_compras)
        kpi_row.addStretch()
        lay.addLayout(kpi_row)

    def _cargar_historial_compras(self) -> None:
        """Carga el historial de compras en la tabla."""
        if not hasattr(self, '_tbl_hist'):
            return
        self._tbl_hist.setRowCount(0)
        try:
            desde = self._hist_desde.date().toString("yyyy-MM-dd")
            hasta = self._hist_hasta.date().toString("yyyy-MM-dd") + " 23:59:59"
            rows = self.container.db.execute("""
                SELECT c.folio, c.fecha, COALESCE(p.nombre,'(sin proveedor)') as proveedor,
                       c.usuario, c.total, c.estado, c.id
                FROM compras c
                LEFT JOIN proveedores p ON p.id=c.proveedor_id
                WHERE c.sucursal_id=? AND c.fecha BETWEEN ? AND ?
                ORDER BY c.fecha DESC LIMIT 200
            """, (self.sucursal_id, desde, hasta)).fetchall()
        except Exception as e:
            rows = []
            logger.debug("_cargar_historial_compras: %s", e)

        total_periodo = 0.0
        for ri, r in enumerate(rows):
            self._tbl_hist.insertRow(ri)
            vals = [
                str(r[0] or ""), str(r[1] or "")[:16],
                str(r[2] or ""), str(r[3] or ""),
                f"${float(r[4] or 0):,.2f}", str(r[5] or ""),
            ]
            for ci, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                if str(r[5]) == "credito":
                    it.setForeground(__import__('PyQt5.QtGui', fromlist=['QColor']).QColor('#e74c3c'))
                self._tbl_hist.setItem(ri, ci, it)
            total_periodo += float(r[4] or 0)

            # Detail button
            compra_id = r[6]
            btn_det = create_secondary_button(self, "🔍 Ver detalle", "Ver detalles de esta compra")
            btn_det.clicked.connect(lambda _, cid=compra_id: self._ver_detalle_compra(cid))
            self._tbl_hist.setCellWidget(ri, 6, btn_det)

        self.lbl_hist_total_compras.setText(f"Total período: ${total_periodo:,.2f}")
        self.lbl_hist_num_compras.setText(f"{len(rows)} compra(s)")

    def _ver_detalle_compra(self, compra_id: int) -> None:
        """Muestra el detalle completo de una compra con opción de reimprimir."""
        try:
            c = self.container.db.execute(
                "SELECT * FROM compras WHERE id=?", (compra_id,)).fetchone()
            if not c: return
            items = self.container.db.execute("""
                SELECT dd.cantidad, dd.costo_unitario, dd.subtotal,
                       p.nombre
                FROM detalles_compra dd
                JOIN productos p ON p.id=dd.producto_id
                WHERE dd.compra_id=?
            """, (compra_id,)).fetchall()

            # Build HTML receipt
            html = self._generar_html_compra(dict(c), [dict(i) for i in items])

            # Show in dialog
            from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QHBoxLayout
            from PyQt5.QtPrintSupport import QPrinter, QPrintDialog
            from PyQt5.QtGui import QTextDocument

            dlg = QDialog(self)
            dlg.setWindowTitle(f"Compra {c['folio'] if c else compra_id}")
            dlg.setMinimumSize(480, 540)
            lay_d = QVBoxLayout(dlg)

            browser = QTextBrowser()
            browser.setHtml(html)
            lay_d.addWidget(browser)

            btn_row = QHBoxLayout()
            btn_print = create_primary_button(self, "🖨️ Imprimir", "Imprimir comprobante de compra")
            btn_close2 = create_secondary_button(self, "Cerrar", "Cerrar vista previa")

            def _do_print2():
                printer = QPrinter(QPrinter.HighResolution)
                if QPrintDialog(printer, dlg).exec_() == QPrintDialog.Accepted:
                    doc = QTextDocument(); doc.setHtml(html)
                    doc.print_(printer)

            btn_print.clicked.connect(_do_print2)
            btn_close2.clicked.connect(dlg.accept)
            btn_row.addWidget(btn_print); btn_row.addStretch(); btn_row.addWidget(btn_close2)
            lay_d.addLayout(btn_row)
            dlg.exec_()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _generar_html_compra(self, compra: dict, items: list) -> str:
        """Genera el ticket HTML de una compra para impresión."""
        rows_html = ""
        for it in items:
            rows_html += (f"<tr><td>{it.get('nombre','')}</td>"
                          f"<td align='right'>{float(it.get('cantidad',0)):.3f}</td>"
                          f"<td align='right'>${float(it.get('costo_unitario',0)):.4f}</td>"
                          f"<td align='right'>${float(it.get('subtotal',0)):.2f}</td></tr>")
        return f"""
        <html><body style='font-family:monospace;font-size:12px;'>
        <h3 style='text-align:center;'>RECIBO DE COMPRA</h3>
        <p>Folio: <b>{compra.get('folio','?')}</b></p>
        <p>Fecha: {str(compra.get('fecha',''))[:16]}</p>
        <p>Proveedor ID: {compra.get('proveedor_id','?')}</p>
        <p>Usuario: {compra.get('usuario','?')}</p>
        <p>Condición: {compra.get('estado','?').upper()}</p>
        <hr>
        <table width='100%' border='0' cellspacing='4'>
        <tr><th align='left'>Producto</th><th>Cant.</th><th>Costo</th><th>Subtotal</th></tr>
        {rows_html}
        </table>
        <hr>
        <p style='font-size:14px;'><b>Total: ${float(compra.get('total',0)):,.2f}</b></p>
        </body></html>"""

    def _on_refresh(self, event_type: str, data: dict) -> None:
        """Auto-refresh: update product search and provider list."""
        if hasattr(self, '_buscador'):
            self._buscador.set_db(self.container.db)
        self.cargar_proveedores()
        # Also refresh historial if it's the active tab
        if hasattr(self, '_tbl_hist') and self._tabs.currentIndex() == 2:
            self._cargar_historial_compras()

    def _fallback_compra_directa(self, proveedor_id, doc_ref, pago, total,
                                  items) -> str:
        """Registro directo en BD cuando PurchaseService no está disponible."""
        import uuid
        from core.db.connection import transaction
        folio = f"C{datetime.now().strftime('%Y%m%d%H%M%S')}"
        op_id = str(uuid.uuid4())
        db = self.container.db
        with transaction(db):
            db.execute(
                """INSERT INTO compras (proveedor_id, sucursal_id, usuario,
                   total, estado, observaciones, forma_pago, factura, fecha)
                   VALUES (?,?,?,?,?,?,?,?,datetime('now'))""",
                (proveedor_id, self.sucursal_id, self.usuario_actual,
                 total, "completada", doc_ref, pago, op_id))
            compra_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            for it in items:
                db.execute(
                    """INSERT INTO detalles_compra
                       (compra_id, producto_id, cantidad, costo_unitario, subtotal)
                       VALUES (?,?,?,?,?)""",
                    (compra_id, it['product_id'], it['qty'],
                     it['unit_cost'], it['qty'] * it['unit_cost']))
                _app = getattr(self.container, 'app_service', None)
                if _app:
                    _app.registrar_compra(
                        producto_id=it['product_id'], cantidad=it['qty'],
                        costo_unitario=it['unit_cost'],
                        usuario=self.usuario_actual,
                        sucursal_id=self.sucursal_id)
                else:
                    db.execute(
                        "UPDATE productos SET existencia=existencia+?, precio_compra=? WHERE id=?",
                        (it['qty'], it['unit_cost'], it['product_id']))
        return folio
