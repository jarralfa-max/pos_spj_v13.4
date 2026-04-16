
# modulos/activos.py
from core.services.auto_audit import audit_write
from modulos.spj_styles import spj_btn, apply_btn_styles
from modulos.design_tokens import Colors, Spacing, Typography, Borders
from modulos.ui_components import create_primary_button, create_danger_button, create_success_button, create_secondary_button, create_card, apply_tooltip
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, 
                             QLabel, QLineEdit, QPushButton, QTableWidget, QTabWidget, 
                             QTableWidgetItem, QHeaderView, QMessageBox, 
                             QComboBox, QAbstractItemView, QDateEdit, QDialog, QDoubleSpinBox, QDialogButtonBox)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QIcon, QFont
import sqlite3
from datetime import datetime
from fpdf import FPDF
import os

from .base import ModuloBase

# =
# 1. DIÁLOGOS CRUD DE ACTIVOS Y MANTENIMIENTOS
# =

class DialogoActivo(QDialog):
    def __init__(self, conexion, parent=None, activo_id=None):
        super().__init__(parent)
        self.conexion = conexion
        self.activo_id = activo_id
        self.setWindowTitle("Nuevo Activo" if not activo_id else "Editar Activo")
        self.setFixedSize(500, 450)
        self.init_ui()
        if activo_id:
            self.cargar_datos()

    def init_ui(self):
        layout = QFormLayout(self)
        
        self.txt_nombre = QLineEdit()
        self.cmb_categoria = QComboBox()
        self.cmb_categoria.addItems(["Equipo de Computo", "Mobiliario", "Vehículos", "Maquinaria", "Cámara Frigorífica", "Báscula", "Otros"])
        self.cmb_categoria.setEditable(True)
        self.txt_serie = QLineEdit()
        
        self.spin_valor = QDoubleSpinBox()
        self.spin_valor.setRange(0, 10000000)
        self.spin_valor.setPrefix("$ ")
        
        self.spin_vida = QDoubleSpinBox()
        self.spin_vida.setRange(1, 100)
        self.spin_vida.setSuffix(" años")
        
        self.spin_depreciacion = QDoubleSpinBox()
        self.spin_depreciacion.setRange(0, 1000000)
        self.spin_depreciacion.setPrefix("$ ")
        
        self.txt_ubicacion = QLineEdit()
        self.cmb_estado = QComboBox()
        self.cmb_estado.addItems(["activo", "inactivo", "en reparacion", "baja"])
        
        self.txt_notas = QLineEdit()

        layout.addRow("Nombre:*", self.txt_nombre)
        layout.addRow("Categoría:", self.cmb_categoria)
        layout.addRow("No. Serie:", self.txt_serie)
        layout.addRow("Valor Adquisición:", self.spin_valor)
        layout.addRow("Vida Útil:", self.spin_vida)
        layout.addRow("Depreciación Anual:", self.spin_depreciacion)
        layout.addRow("Ubicación:", self.txt_ubicacion)
        layout.addRow("Estado:", self.cmb_estado)
        layout.addRow("Notas:", self.txt_notas)

        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.guardar)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)

    def cargar_datos(self):
        cursor = self.conexion.cursor()
        cursor.execute("SELECT * FROM activos WHERE id=?", (self.activo_id,))
        activo = cursor.fetchone()
        if activo:
            self.txt_nombre.setText(activo['nombre'])
            self.cmb_categoria.setCurrentText(activo['categoria'])
            self.txt_serie.setText(activo['numero_serie'])
            self.spin_valor.setValue(activo['valor_adquisicion'] or 0)
            self.spin_vida.setValue(activo['vida_util_anios'] or 1)
            self.spin_depreciacion.setValue(activo['depreciacion_anual'] or 0)
            self.txt_ubicacion.setText(activo['ubicacion'])
            self.cmb_estado.setCurrentText(activo['estado'])
            self.txt_notas.setText(activo['notas'])

    def guardar(self):
        if not self.txt_nombre.text().strip():
            QMessageBox.warning(self, "Error", "El nombre es obligatorio")
            return
            
        cursor = self.conexion.cursor()
        datos = (
            self.txt_nombre.text(), self.cmb_categoria.currentText(), self.txt_serie.text(),
            self.spin_valor.value(), self.spin_vida.value(), self.spin_depreciacion.value(),
            self.txt_ubicacion.text(), self.cmb_estado.currentText(), self.txt_notas.text()
        )
        
        if self.activo_id:
            cursor.execute("""
                UPDATE activos SET nombre=?, categoria=?, numero_serie=?, valor_adquisicion=?,
                vida_util_anios=?, depreciacion_anual=?, ubicacion=?, estado=?, notas=?
                WHERE id=?
            """, datos + (self.activo_id,))
        else:
            cursor.execute("""
                INSERT INTO activos (nombre, categoria, numero_serie, valor_adquisicion,
                vida_util_anios, depreciacion_anual, ubicacion, estado, notas, fecha_adquisicion)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, date('now'))
            """, datos)
            
        self.conexion.commit()
        self.accept()


class DialogoMantenimiento(QDialog):
    """Diálogo para Agendar un mantenimiento (Sin pagarlo todavía)"""
    def __init__(self, conexion, parent=None, mant_id=None):
        super().__init__(parent)
        self.conexion = conexion
        self.mant_id = mant_id
        self.setWindowTitle("Agendar Mantenimiento" if not mant_id else "Editar Agenda")
        self.setFixedSize(400, 350)
        self.init_ui()
        self.cargar_activos()
        if mant_id:
            self.cargar_datos()

    def init_ui(self):
        layout = QFormLayout(self)
        
        self.cmb_activo = QComboBox()
        self.cmb_tipo = QComboBox()
        self.cmb_tipo.addItems(["preventivo", "correctivo"])
        self.txt_desc = QLineEdit()
        self.date_prog = QDateEdit()
        self.date_prog.setCalendarPopup(True)
        self.date_prog.setDate(QDate.currentDate())

        # v13.2: tipo de servicio interno / externo
        self.cmb_origen = QComboBox()
        self.cmb_origen.addItems(["Interno (tecnico propio)", "Externo (Proveedor)"])
        self.cmb_origen.currentIndexChanged.connect(self._toggle_proveedor)

        self.txt_tecnico  = QLineEdit()
        self.txt_tecnico.setPlaceholderText("Nombre del tecnico interno")
        self.cmb_proveedor = QComboBox()
        self.lbl_proveedor = QLabel("Proveedor:")

        layout.addRow("Activo:*", self.cmb_activo)
        layout.addRow("Tipo:", self.cmb_tipo)
        layout.addRow("Descripcion:", self.txt_desc)
        layout.addRow("Fecha Prog:", self.date_prog)
        layout.addRow("Tipo servicio:", self.cmb_origen)
        layout.addRow("Tecnico:", self.txt_tecnico)
        layout.addRow(self.lbl_proveedor, self.cmb_proveedor)
        self.lbl_proveedor.setVisible(False)
        self.cmb_proveedor.setVisible(False)

        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.guardar)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)

    def cargar_activos(self):
        cursor = self.conexion.cursor()
        # Solo cargar los que no están dados de baja
        cursor.execute("SELECT id, nombre FROM activos WHERE estado != 'baja'")
        for row in cursor.fetchall():
            self.cmb_activo.addItem(row['nombre'], row['id'])

    def cargar_datos(self):
        cursor = self.conexion.cursor()
        cursor.execute("SELECT * FROM mantenimientos WHERE id=?", (self.mant_id,))
        mant = cursor.fetchone()
        if mant:
            index = self.cmb_activo.findData(mant['activo_id'])
            if index >= 0: self.cmb_activo.setCurrentIndex(index)
            self.cmb_tipo.setCurrentText(mant['tipo'])
            self.txt_desc.setText(mant['descripcion'])
            self.date_prog.setDate(QDate.fromString(mant['fecha_prog'], "yyyy-MM-dd"))
            self.txt_tecnico.setText(mant['realizado_por'] or "")

    def _toggle_proveedor(self, idx):
        externo = (idx == 1)
        self.txt_tecnico.setVisible(not externo)
        self.lbl_proveedor.setVisible(externo)
        self.cmb_proveedor.setVisible(externo)

    def _cargar_proveedores(self):
        try:
            rows = self.conexion.execute(
                "SELECT id, nombre FROM proveedores WHERE activo=1 ORDER BY nombre"
            ).fetchall()
            self.cmb_proveedor.addItem("-- Seleccionar --", None)
            for r in rows:
                n = r["nombre"] if hasattr(r,"keys") else r[1]
                i = r["id"]    if hasattr(r,"keys") else r[0]
                self.cmb_proveedor.addItem(n, i)
        except Exception:
            pass

    def guardar(self):
        activo_id = self.cmb_activo.currentData()
        if not activo_id:
            QMessageBox.warning(self, "Error", "Debe seleccionar un activo")
            return
        externo = self.cmb_origen.currentIndex() == 1
        if externo:
            realizado_por = "Proveedor: " + self.cmb_proveedor.currentText()
        else:
            realizado_por = self.txt_tecnico.text()
        cursor = self.conexion.cursor()
        datos = (
            activo_id, self.cmb_tipo.currentText(), self.txt_desc.text(),
            self.date_prog.date().toString("yyyy-MM-dd"), realizado_por
        )
        if self.mant_id:
            cursor.execute(
                "UPDATE mantenimientos SET activo_id=?, tipo=?, descripcion=?,"
                "fecha_prog=?, realizado_por=? WHERE id=?",
                datos + (self.mant_id,))
        else:
            cursor.execute(
                "INSERT INTO mantenimientos "
                "(activo_id, tipo, descripcion, fecha_prog, realizado_por, estado)"
                " VALUES (?, ?, ?, ?, ?, 'pendiente')",
                datos)
        self.conexion.commit()
        self.accept()

# =
# 2. DIÁLOGO FINANCIERO DE PAGO (MAGIA ENTERPRISE)
# =

class DialogoPagoMantenimiento(QDialog):
    """Diálogo para capturar el costo real y elegir si se paga de contado o a crédito."""
    def __init__(self, mant_id, equipo, parent=None):
        super().__init__(parent)
        self.mant_id = mant_id
        self.equipo = equipo
        self.setWindowTitle(f"Finalizar y Pagar: {equipo}")
        self.setFixedSize(400, 300)
        self.init_ui()

    def init_ui(self):
        layout = QFormLayout(self)
        
        lbl_info = QLabel("El mantenimiento ha concluido. Registre el costo final para la Tesorería.")
        lbl_info.setWordWrap(True)
        # Tooltip: Explica el propósito del mensaje
        apply_tooltip(lbl_info, "Información sobre el cierre del mantenimiento")
        layout.addRow(lbl_info)
        
        self.txt_tecnico = QLineEdit()
        self.txt_tecnico.setPlaceholderText("Nombre del Taller o Técnico")
        
        self.spin_costo = QDoubleSpinBox()
        self.spin_costo.setRange(0.01, 9999999.0)
        self.spin_costo.setPrefix("$ ")
        self.spin_costo.setDecimals(2)
        
        self.cmb_metodo = QComboBox()
        # 🚀 OPCIONES FINANCIERAS: Las que no son crédito se van a OPEX (Caja), Crédito se va a Cuentas por Pagar
        self.cmb_metodo.addItems(["Transferencia", "Efectivo (De Caja)", "Tarjeta", "CREDITO (Pagar después)"])
        apply_tooltip(self.cmb_metodo, "Seleccione el método de pago para registrar en tesorería")
        
        layout.addRow("Técnico Final:", self.txt_tecnico)
        layout.addRow("Costo Total Factura:", self.spin_costo)
        layout.addRow("Método de Pago:", self.cmb_metodo)
        
        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Save).setText("Procesar Pago y Finalizar")
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)

    def get_datos_pago(self):
        return {
            "costo": self.spin_costo.value(),
            "tecnico": self.txt_tecnico.text().strip() or "Técnico Externo",
            "metodo_pago": self.cmb_metodo.currentText()
        }

# =
# 3. MÓDULO PRINCIPAL (UNIFICADO)
# =


def calcular_depreciacion_mensual(db, sucursal_id: int = 1) -> list:
    """
    Aplica depreciación mensual a todos los activos activos.
    Llamar desde el scheduler nocturno el último día del mes.
    Retorna lista de activos depreciados con nuevos valores.
    """
    import logging
    from datetime import datetime
    logger = logging.getLogger("spj.activos.depreciacion")
    resultados = []
    try:
        # Asegurar que la columna valor_residual existe (puede faltar en DBs antiguas)
        try:
            db.execute("ALTER TABLE activos ADD COLUMN valor_residual REAL DEFAULT 0")
            try: db.commit()
            except Exception: pass
        except Exception:
            pass  # La columna ya existe o la tabla no existe aún

        activos = db.execute("""
            SELECT id, nombre, valor_actual, depreciacion_anual, vida_util_anios,
                   COALESCE(valor_residual, 0) as valor_residual
            FROM activos
            WHERE estado='activo'
              AND depreciacion_anual > 0
              AND COALESCE(valor_actual, 0) > COALESCE(valor_residual, 0)
        """).fetchall()

        mes_actual = datetime.now().strftime("%Y-%m")

        for a in activos:
            depreciacion_mensual = a['depreciacion_anual'] / 12
            nuevo_valor = max(
                float(a['valor_residual']),
                float(a['valor_actual']) - depreciacion_mensual
            )
            # Check if already depreciated this month
            ya_dep = db.execute("""
                SELECT id FROM activos_depreciacion
                WHERE activo_id=? AND strftime('%Y-%m', fecha)=?
            """, (a['id'], mes_actual)).fetchone()
            if ya_dep:
                continue

            db.execute("""
                UPDATE activos SET valor_actual=? WHERE id=?
            """, (nuevo_valor, a['id']))
            db.execute("""
                INSERT INTO activos_depreciacion
                (activo_id, monto, valor_antes, valor_despues, fecha, sucursal_id)
                VALUES (?,?,?,?,datetime('now'),?)
            """, (a['id'], depreciacion_mensual,
                  float(a['valor_actual']), nuevo_valor, sucursal_id))
            resultados.append({
                'id': a['id'], 'nombre': a['nombre'],
                'depreciacion': depreciacion_mensual,
                'valor_nuevo': nuevo_valor
            })
            logger.info("Depreciacion: %s — $%.2f → $%.2f",
                        a['nombre'], a['valor_actual'], nuevo_valor)

        try: db.commit()
        except Exception: pass
    except Exception as e:
        logger.error("calcular_depreciacion_mensual: %s", e)
    return resultados


class ModuloActivos(ModuloBase):
    """
    Gestión de Activos y Mantenimiento Corporativo (EAM).
    Combina el catálogo físico, impresión de etiquetas y enlace a Tesorería.
    """
    # 🛠️ FIX ENTERPRISE: Recibimos el container
    def __init__(self, container, parent=None):
        # Ensure depreciation table exists
        try:
            container.db.execute("""CREATE TABLE IF NOT EXISTS activos_depreciacion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activo_id INTEGER, monto REAL, valor_antes REAL, valor_despues REAL,
                fecha DATETIME DEFAULT (datetime('now')), sucursal_id INTEGER DEFAULT 1
            )""")
            try: container.db.commit()
            except Exception: pass
        except Exception: pass
        super().__init__(container.db, parent)
        self.container = container
        self.sucursal_id = 1
        self.usuario_actual = "Sistema"
        self.init_ui()

    def set_sucursal(self, sucursal_id: int, nombre_sucursal: str):
        self.sucursal_id = sucursal_id

    def set_usuario_actual(self, usuario: str, rol: str):
        self.usuario_actual = usuario

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        titulo = QLabel("🚜 Gestión Empresarial de Activos y Mantenimiento")
        titulo.setObjectName("heading")
        apply_tooltip(titulo, "Módulo completo de gestión de activos fijos y mantenimientos")
        layout.addWidget(titulo)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("tabWidget")
        
        self.tab_activos = QWidget()
        self.tab_mantenimiento = QWidget()
        self.tab_depreciacion = QWidget()

        self.tabs.addTab(self.tab_activos, "📋 Inventario de Equipos")
        self.tabs.addTab(self.tab_mantenimiento, "🔧 Agenda y Ordenes de Servicio")
        self.tabs.addTab(self.tab_depreciacion, "📊 Depreciación Acumulada")

        self.setup_activos()
        self.setup_mantenimiento()
        self.setup_depreciacion()
        
        layout.addWidget(self.tabs)

    def setup_activos(self):
        layout = QVBoxLayout(self.tab_activos)
        
        # Controles superiores
        controles = QHBoxLayout()
        btn_nuevo = QPushButton("➕ Nuevo Equipo")
        btn_nuevo = create_success_button(self, btn_nuevo, "Crear un nuevo activo fijo")
        btn_nuevo.clicked.connect(self.agregar_activo)
        
        btn_refrescar = QPushButton("🔄 Refrescar")
        btn_refrescar = create_secondary_button(self, btn_refrescar, "Actualizar lista de activos")
        btn_refrescar.clicked.connect(self.cargar_activos)
        
        btn_pdf = QPushButton("📄 Exportar PDF")
        btn_pdf = create_danger_button(self, btn_pdf, "Generar reporte PDF del inventario")
        btn_pdf.clicked.connect(self.exportar_pdf_activos)
        
        controles.addWidget(btn_nuevo)
        controles.addWidget(btn_refrescar)
        controles.addStretch()
        controles.addWidget(btn_pdf)
        layout.addLayout(controles)
        
        # Tabla
        self.tabla_activos = QTableWidget()
        self.tabla_activos.setColumnCount(10)
        # 🚀 MODIFICACIÓN: Mostrar el "Código Corporativo" en lugar del simple ID
        self.tabla_activos.setHorizontalHeaderLabels([
            "Etiqueta", "Nombre", "Categoría", "No. Serie", "Valor Compra", 
            "Depreciación", "Ubicación", "Estado", "Imprimir", "Acciones"
        ])
        self.tabla_activos.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tabla_activos.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla_activos.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.tabla_activos)
        
        self.cargar_activos()

    def cargar_activos(self):
        self.tabla_activos.setRowCount(0)
        try:
            cursor = self.conexion.cursor()
            # Ocultamos los que están dados de baja
            cursor.execute("SELECT * FROM activos WHERE estado != 'baja' ORDER BY id DESC LIMIT 500")
            activos = cursor.fetchall()
            
            for i, activo in enumerate(activos):
                self.tabla_activos.insertRow(i)
                
                # 🚀 GENERACIÓN DE CÓDIGO ETIQUETA EAM
                codigo_etiqueta = f"ACT-{str(activo['id']).zfill(5)}"
                
                self.tabla_activos.setItem(i, 0, QTableWidgetItem(codigo_etiqueta))
                self.tabla_activos.setItem(i, 1, QTableWidgetItem(activo['nombre']))
                self.tabla_activos.setItem(i, 2, QTableWidgetItem(activo['categoria']))
                self.tabla_activos.setItem(i, 3, QTableWidgetItem(activo['numero_serie']))
                self.tabla_activos.setItem(i, 4, QTableWidgetItem(f"${activo['valor_adquisicion']:,.2f}"))
                self.tabla_activos.setItem(i, 5, QTableWidgetItem(f"${activo['depreciacion_anual']:,.2f}"))
                self.tabla_activos.setItem(i, 6, QTableWidgetItem(activo['ubicacion']))
                
                estado_item = QTableWidgetItem(activo['estado'].upper())
                if activo['estado'] == 'inactivo':
                    estado_item.setForeground(Qt.red)
                self.tabla_activos.setItem(i, 7, estado_item)
                
                # Botón Imprimir QR/Etiqueta
                btn_print = QPushButton("🏷️")
                btn_print.setToolTip("Imprimir Etiqueta Código de Barras")
                btn_print.clicked.connect(lambda _, c=codigo_etiqueta, n=activo['nombre']: self.imprimir_etiqueta(c, n))
                self.tabla_activos.setCellWidget(i, 8, btn_print)

                # Acciones
                acciones = QWidget()
                lay = QHBoxLayout(acciones)
                lay.setContentsMargins(0,0,0,0)
                
                btn_edit = QPushButton("✏️")
                btn_edit.clicked.connect(lambda _, id=activo['id']: self.editar_activo(id))
                
                btn_del = QPushButton("❌")
                btn_del.clicked.connect(lambda _, id=activo['id'], n=activo['nombre']: self.eliminar_activo(id, n))
                
                lay.addWidget(btn_edit)
                lay.addWidget(btn_del)
                self.tabla_activos.setCellWidget(i, 9, acciones)
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al cargar activos: {e}")

    def imprimir_etiqueta(self, codigo, nombre):
        """Simula o ejecuta la impresión de una etiqueta ZPL/ESC-POS del equipo."""
        QMessageBox.information(self, "Impresión de Etiquetas", 
            f"Se ha enviado a la impresora de etiquetas:\n\n[|||||||||||||||||]\n{codigo}\n{nombre}")

    def agregar_activo(self):
        dialogo = DialogoActivo(self.conexion, self)
        if dialogo.exec_() == QDialog.Accepted:
            self.cargar_activos()
            self.cargar_mantenimientos() # Actualizar listas dependientes

    def editar_activo(self, activo_id):
        dialogo = DialogoActivo(self.conexion, self, activo_id)
        if dialogo.exec_() == QDialog.Accepted:
            self.cargar_activos()

    def eliminar_activo(self, activo_id, nombre):
        """🚀 SOFT DELETE: NUNCA borramos un activo, solo lo damos de baja contable."""
        respuesta = QMessageBox.question(
            self, "Confirmar Baja", 
            f"¿Seguro que desea dar de BAJA el equipo '{nombre}'?\n\n(Se mantendrá en el historial contable, pero no aparecerá en las listas activas)",
            QMessageBox.Yes | QMessageBox.No
        )
        if respuesta == QMessageBox.Yes:
            try:
                cursor = self.conexion.cursor()
                cursor.execute("UPDATE activos SET estado = 'baja' WHERE id=?", (activo_id,))
                self.conexion.commit()
                self.cargar_activos()
                QMessageBox.information(self, "Éxito", "Equipo dado de baja correctamente.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"No se pudo dar de baja: {e}")

    def setup_mantenimiento(self):
        layout = QVBoxLayout(self.tab_mantenimiento)
        
        controles = QHBoxLayout()
        btn_nuevo = QPushButton("📅 Agendar Mantenimiento")
        btn_nuevo = create_primary_button(self, btn_nuevo, "Programar nuevo mantenimiento preventivo o correctivo")
        btn_nuevo.clicked.connect(self.agregar_mantenimiento)
        
        btn_refrescar = QPushButton("🔄 Refrescar")
        btn_refrescar = create_secondary_button(self, btn_refrescar, "Actualizar agenda de mantenimientos")
        btn_refrescar.clicked.connect(self.cargar_mantenimientos)
        
        btn_pdf = QPushButton("📄 Exportar Agenda")
        btn_pdf = create_danger_button(self, btn_pdf, "Generar reporte PDF de la agenda")
        btn_pdf.clicked.connect(self.exportar_pdf_mantenimientos)
        
        controles.addWidget(btn_nuevo)
        controles.addWidget(btn_refrescar)
        controles.addStretch()
        controles.addWidget(btn_pdf)
        layout.addLayout(controles)
        
        self.tabla_mant = QTableWidget()
        self.tabla_mant.setColumnCount(8)
        self.tabla_mant.setHorizontalHeaderLabels([
            "Folio", "Equipo", "Tipo", "Descripción", 
            "Fecha Prog.", "Técnico", "Estado", "Acciones Financieras"
        ])
        self.tabla_mant.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.tabla_mant.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.tabla_mant)
        
        self.cargar_mantenimientos()

    # ── Tab 3: Depreciación Acumulada ─────────────────────────────────────

    def setup_depreciacion(self):
        """Reporte de depreciación acumulada por activo y periodo (tabla depreciacion_acumulada)."""
        layout = QVBoxLayout(self.tab_depreciacion)

        controles = QHBoxLayout()
        btn_actualizar = QPushButton("📊 Cargar Reporte")
        btn_actualizar = create_secondary_button(self, btn_actualizar,
                                                 "Cargar datos de depreciación acumulada")
        btn_actualizar.clicked.connect(self.cargar_depreciacion)
        controles.addWidget(btn_actualizar)
        controles.addStretch()
        layout.addLayout(controles)

        info = QLabel(
            "Depreciación en línea recta NIF B-2. "
            "Los montos se registran mensualmente via accrual_depreciacion_mensual()."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#555; font-size:11px; background:#fffbea; padding:5px; border-radius:4px;")
        layout.addWidget(info)

        self.tabla_dep = QTableWidget()
        self.tabla_dep.setColumnCount(6)
        self.tabla_dep.setHorizontalHeaderLabels([
            "Activo ID", "Nombre Activo", "Periodo", "Cargo Mes $",
            "Acumulado $", "Registrado"
        ])
        hh = self.tabla_dep.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        self.tabla_dep.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla_dep.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla_dep.setAlternatingRowColors(True)
        layout.addWidget(self.tabla_dep)

        self.cargar_depreciacion()

    def cargar_depreciacion(self):
        """Carga datos de depreciacion_acumulada con JOIN a activos."""
        self.tabla_dep.setRowCount(0)
        try:
            rows = self.conexion.execute("""
                SELECT da.activo_id,
                       COALESCE(a.nombre, '—') AS nombre,
                       da.periodo,
                       da.monto_mes,
                       da.acumulado,
                       da.created_at
                FROM depreciacion_acumulada da
                LEFT JOIN activos a ON a.id = da.activo_id
                ORDER BY da.periodo DESC, a.nombre ASC
                LIMIT 500
            """).fetchall()
        except Exception:
            rows = []
        for i, r in enumerate(rows):
            self.tabla_dep.insertRow(i)
            vals = [str(r[0]), str(r[1]), str(r[2]),
                    f"${float(r[3] or 0):,.2f}",
                    f"${float(r[4] or 0):,.2f}",
                    str(r[5] or "")[:16]]
            for j, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self.tabla_dep.setItem(i, j, item)

    def cargar_mantenimientos(self):
        self.tabla_mant.setRowCount(0)
        try:
            cursor = self.conexion.cursor()
            query = """
                SELECT m.*, a.nombre as activo_nombre 
                FROM mantenimientos m
                JOIN activos a ON m.activo_id = a.id ORDER BY CASE WHEN m.estado = 'pendiente' THEN 0 ELSE 1 END, m.fecha_prog DESC LIMIT 500
            """
            cursor.execute(query)
            mantenimientos = cursor.fetchall()
            
            for i, mant in enumerate(mantenimientos):
                self.tabla_mant.insertRow(i)
                
                self.tabla_mant.setItem(i, 0, QTableWidgetItem(f"OS-{mant['id']}"))
                self.tabla_mant.setItem(i, 1, QTableWidgetItem(mant['activo_nombre']))
                self.tabla_mant.setItem(i, 2, QTableWidgetItem(mant['tipo']))
                self.tabla_mant.setItem(i, 3, QTableWidgetItem(mant['descripcion']))
                self.tabla_mant.setItem(i, 4, QTableWidgetItem(mant['fecha_prog']))
                self.tabla_mant.setItem(i, 5, QTableWidgetItem(mant['realizado_por'] or 'Sin asignar'))
                
                estado_item = QTableWidgetItem(mant['estado'].upper())
                if mant['estado'] == 'pendiente':
                    estado_item.setForeground(Qt.red)
                else:
                    estado_item.setForeground(Qt.darkGreen)
                self.tabla_mant.setItem(i, 6, estado_item)
                
                # 🚀 ACCIONES FINANCIERAS Y OPERATIVAS
                acciones = QWidget()
                lay = QHBoxLayout(acciones)
                lay.setContentsMargins(0,0,0,0)
                
                if mant['estado'] == 'pendiente':
                    btn_completar = QPushButton("✅ Pagar y Finalizar")
                    btn_completar = create_success_button(self, btn_completar, "Registrar pago y cerrar orden de mantenimiento")
                    btn_completar.clicked.connect(lambda _, id=mant['id'], eq=mant['activo_nombre']: self.marcar_completado_enterprise(id, eq))
                    lay.addWidget(btn_completar)
                    
                    btn_del = QPushButton("❌")
                    apply_tooltip(btn_del, "Eliminar esta orden de mantenimiento")
                    btn_del.setObjectName("dangerBtn")
                    btn_del.clicked.connect(lambda _, id=mant['id']: self.eliminar_mantenimiento(id))
                    lay.addWidget(btn_del)
                else:
                    lbl = QLabel(f"Pagado: ${mant['costo']:,.2f}")
                    lbl.setObjectName("textSuccess")
                    lay.addWidget(lbl)
                    
                self.tabla_mant.setCellWidget(i, 7, acciones)
                
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error al cargar mantenimientos: {e}")

    def agregar_mantenimiento(self):
        dialogo = DialogoMantenimiento(self.conexion, self)
        if dialogo.exec_() == QDialog.Accepted:
            self.cargar_mantenimientos()

    def eliminar_mantenimiento(self, mant_id):
        """Como está pendiente y no se ha pagado, sí podemos eliminar la orden."""
        respuesta = QMessageBox.question(self, "Confirmar", "¿Eliminar esta orden de mantenimiento pendiente?", QMessageBox.Yes | QMessageBox.No)
        if respuesta == QMessageBox.Yes:
            try:
                cursor = self.conexion.cursor()
                cursor.execute("DELETE FROM mantenimientos WHERE id=?", (mant_id,))
                self.conexion.commit()
                self.cargar_mantenimientos()
            except Exception as e:
                QMessageBox.critical(self, "Error", str(e))

    def marcar_completado_enterprise(self, mant_id, equipo):
        """🚀 MAGIA ENTERPRISE: Conexión con el AssetService y TreasuryService"""
        dlg = DialogoPagoMantenimiento(mant_id, equipo, self)
        if dlg.exec_() == QDialog.Accepted:
            datos = dlg.get_datos_pago()
            try:
                if hasattr(self.container, 'asset_service'):
                    self.container.asset_service.completar_y_pagar_mantenimiento(
                        mantenimiento_id=mant_id,
                        costo=datos['costo'],
                        tecnico=datos['tecnico'],
                        metodo_pago=datos['metodo_pago'],
                        usuario=self.usuario_actual,
                        sucursal_id=self.sucursal_id
                    )
                    QMessageBox.information(self, "Orden Completada", "Mantenimiento pagado y registrado en la Tesorería.")
                    self.cargar_mantenimientos()
                else:
                    # Fallback si aún no inyectas el servicio
                    QMessageBox.warning(self, "Advertencia", "El AssetService no está conectado.")
            except Exception as e:
                QMessageBox.critical(self, "Error Crítico", str(e))

    # =
    # FUNCIONES DE EXPORTACIÓN A PDF (Manteniendo tu excelente código original)
    # =
    def exportar_pdf_activos(self):
        try:
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", 'B', 16)
            pdf.cell(200, 10, "Reporte de Activos Fijos", ln=True, align='C')
            pdf.ln(10)
            
            pdf.set_font("Arial", 'B', 10)
            headers = ["ID Etiqueta", "Nombre", "Categoría", "Estado", "Valor"]
            col_widths = [30, 60, 40, 30, 30]
            
            for i, header in enumerate(headers):
                pdf.cell(col_widths[i], 10, header, border=1)
            pdf.ln()
            
            pdf.set_font("Arial", '', 9)
            cursor = self.conexion.cursor()
            cursor.execute("SELECT id, nombre, categoria, estado, valor_adquisicion FROM activos WHERE estado != 'baja'")
            activos = cursor.fetchall()
            
            for activo in activos:
                pdf.cell(col_widths[0], 10, f"ACT-{str(activo['id']).zfill(5)}", border=1)
                pdf.cell(col_widths[1], 10, str(activo['nombre'])[:30], border=1)
                pdf.cell(col_widths[2], 10, str(activo['categoria'])[:20], border=1)
                pdf.cell(col_widths[3], 10, str(activo['estado']).upper(), border=1)
                pdf.cell(col_widths[4], 10, f"${activo['valor_adquisicion']:.2f}", border=1)
                pdf.ln()
            
            if not os.path.exists("reportes"):
                os.makedirs("reportes")
                
            nombre_archivo = f"reportes/Activos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            pdf.output(nombre_archivo)
            QMessageBox.information(self, "Éxito", f"Reporte exportado a:\n{nombre_archivo}")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo generar el PDF:\n{e}")

    def exportar_pdf_mantenimientos(self):
        try:
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", 'B', 16)
            pdf.cell(200, 10, "Agenda de Mantenimientos", ln=True, align='C')
            pdf.ln(10)
            
            pdf.set_font("Arial", 'B', 10)
            headers = ["OS", "Equipo", "Tipo", "Fecha Prog", "Estado", "Costo"]
            col_widths = [15, 60, 30, 30, 25, 30]
            
            for i, header in enumerate(headers):
                pdf.cell(col_widths[i], 10, header, border=1)
            pdf.ln()
            
            pdf.set_font("Arial", '', 9)
            cursor = self.conexion.cursor()
            cursor.execute("""
                SELECT m.id, a.nombre, m.tipo, m.fecha_prog, m.estado, m.costo 
                FROM mantenimientos m JOIN activos a ON m.activo_id = a.id ORDER BY m.fecha_prog DESC
             LIMIT 500""")
            mantenimientos = cursor.fetchall()
            
            for mant in mantenimientos:
                pdf.cell(col_widths[0], 10, str(mant['id']), border=1)
                pdf.cell(col_widths[1], 10, str(mant['nombre'])[:30], border=1)
                pdf.cell(col_widths[2], 10, str(mant['tipo'])[:15], border=1)
                pdf.cell(col_widths[3], 10, str(mant['fecha_prog']), border=1)
                pdf.cell(col_widths[4], 10, str(mant['estado']).upper(), border=1)
                
                costo_str = f"${mant['costo']:.2f}" if mant['costo'] else "N/A"
                pdf.cell(col_widths[5], 10, costo_str, border=1)
                pdf.ln()
            
            if not os.path.exists("reportes"):
                os.makedirs("reportes")
                
            nombre_archivo = f"reportes/Mantenimientos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            pdf.output(nombre_archivo)
            QMessageBox.information(self, "Éxito", f"Reporte exportado a:\n{nombre_archivo}")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo generar el PDF:\n{e}")