
# modulos/productos.py
from modulos.spj_styles import spj_btn, apply_btn_styles
from modulos.design_tokens import Colors, Spacing, Typography, Borders
from modulos.ui_components import (
    create_primary_button, create_success_button, create_danger_button, 
    create_secondary_button, create_input_field, create_input, create_combo,
    create_heading, create_subheading, create_caption, apply_tooltip
)
import os
import shutil
from datetime import datetime
from modulos.spj_refresh_mixin import RefreshMixin
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QMessageBox, QFormLayout, QDoubleSpinBox, QGroupBox,
    QTableWidget, QTableWidgetItem, QDialog, QDialogButtonBox, QHeaderView,
    QAbstractItemView, QFrame, QSplitter, QGridLayout, QListWidget,
    QListWidgetItem, QCompleter, QDateEdit, QTimeEdit, QTabWidget,
    QRadioButton, QButtonGroup, QCheckBox, QSpinBox, QTextEdit, QMenu,
    QAction, QToolBar, QStatusBar, QProgressBar, QSlider, QDial,
    QCalendarWidget, QColorDialog, QFontDialog, QFileDialog, QInputDialog,
    QErrorMessage, QProgressDialog, QSplashScreen, QSystemTrayIcon,
    QStyleFactory, QApplication, QSizePolicy, QStackedWidget, QScrollArea
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QPixmap
import logging

logger = logging.getLogger(__name__)

# Asegurar que el directorio de imágenes exista
os.makedirs("imagenes_productos", exist_ok=True)

class DialogoProducto(QDialog):
    """
    Formulario Modal Enterprise para Crear/Editar Productos.
    Soporta Productos Simples, Compuestos, Subproductos e Imágenes.
    """
    def __init__(self, container, producto_id=None, parent=None):
        super().__init__(parent)
        self.container = container
        self.producto_id = producto_id
        self.ruta_imagen_actual = None
        
        self.setWindowTitle("Nuevo Producto" if not producto_id else f"Editar Producto #{producto_id}")
        self.setMinimumSize(650, 500)
        self.setModal(True)
        
        self.init_ui()
        if self.producto_id:
            self.cargar_datos_producto()

    def keyPressEvent(self, event):
        """
        Override: Ignore Enter/Return so the dialog does NOT auto-accept.
        Enter is used by scanner HID — we don't want it to trigger Save.
        The user must explicitly click the Save button.
        """
        from PyQt5.QtCore import Qt
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            # Absorb the event — do nothing
            event.accept()
            return
        super().keyPressEvent(event)

    def init_ui(self):
        layout_principal = QVBoxLayout(self)
        
        # --- TABS DEL FORMULARIO ---
        tabs = QTabWidget()
        tab_general = QWidget()
        self.tab_compuesto = QWidget() # Se oculta/muestra según el tipo
        
        tabs.addTab(tab_general, "Datos Generales")
        tabs.addTab(self.tab_compuesto, "Componentes (Si es Compuesto)")
        
        # ================= TAB GENERAL =================
        layout_general = QHBoxLayout(tab_general)
        
        # Columna Izquierda: Formulario
        form_layout = QFormLayout()
        
        self.cmb_tipo = QComboBox()
        self.cmb_tipo.addItems(["Simple", "Compuesto", "Subproducto"])
        self.cmb_tipo.currentTextChanged.connect(self.al_cambiar_tipo)
        
        self.txt_nombre = QLineEdit()
        self.txt_codigo = QLineEdit()
        self.txt_codigo_barras = QLineEdit()
        
        self.cmb_categoria = QComboBox()
        self.cmb_categoria.setEditable(True)
        self.cargar_categorias()
        
        self.txt_precio = QDoubleSpinBox()
        self.txt_precio.setRange(0.0, 999999.0)
        self.txt_precio.setPrefix("$ ")
        
        self.txt_costo = QDoubleSpinBox()
        self.txt_costo.setRange(0.0, 999999.0)
        self.txt_costo.setPrefix("$ ")
        
        self.cmb_unidad = QComboBox()
        self.cmb_unidad.addItems(["kg", "pza", "litro", "paquete", "caja"])
        
        self.txt_stock_minimo = QDoubleSpinBox()
        self.txt_stock_minimo.setRange(0.0, 99999.0)
        
        form_layout.addRow("Tipo de Producto:", self.cmb_tipo)
        form_layout.addRow("Nombre:*", self.txt_nombre)
        form_layout.addRow("Código Interno:", self.txt_codigo)
        form_layout.addRow("Código de Barras:", self.txt_codigo_barras)
        form_layout.addRow("Categoría:", self.cmb_categoria)
        form_layout.addRow("Precio de Venta:*", self.txt_precio)
        form_layout.addRow("Costo de Compra:", self.txt_costo)

        # Precio mínimo (protección financiera)
        self.txt_precio_minimo = QDoubleSpinBox()
        self.txt_precio_minimo.setRange(0, 999999)
        self.txt_precio_minimo.setDecimals(2)
        self.txt_precio_minimo.setPrefix("$")
        self.txt_precio_minimo.setToolTip("Precio mínimo de venta. Por debajo de este precio el sistema bloquea el descuento.")
        form_layout.addRow("Precio mínimo:", self.txt_precio_minimo)
        form_layout.addRow("Unidad de Medida:", self.cmb_unidad)
        form_layout.addRow("Stock Mínimo:", self.txt_stock_minimo)
        
        # Columna Derecha: Imagen
        panel_imagen = QVBoxLayout()
        self.lbl_imagen = QLabel("Sin Imagen")
        self.lbl_imagen.setAlignment(Qt.AlignCenter)
        self.lbl_imagen.setFixedSize(180, 180)
        self.lbl_imagen.setObjectName("imagePlaceholder")
        self.lbl_imagen.setToolTip("Vista previa de la imagen del producto. Haga clic en 'Subir Imagen' para cargar una.")
        
        btn_cargar_img = create_secondary_button(self, "📸 Subir Imagen", "Cargar una imagen desde su computadora")
        btn_cargar_img.clicked.connect(self.cargar_imagen)
        
        btn_quitar_img = create_danger_button(self, "❌ Quitar", "Eliminar la imagen actual del producto")
        btn_quitar_img.clicked.connect(self.quitar_imagen)
        
        panel_imagen.addWidget(self.lbl_imagen)
        panel_imagen.addWidget(btn_cargar_img)
        panel_imagen.addWidget(btn_quitar_img)
        panel_imagen.addStretch()
        
        layout_general.addLayout(form_layout, 2)
        layout_general.addLayout(panel_imagen, 1)
        
        # ================= TAB COMPUESTOS =================
        layout_compuesto = QVBoxLayout(self.tab_compuesto)
        layout_compuesto.addWidget(QLabel("<i>Agregue los productos que conforman este paquete/combo.</i>"))
        # Aquí iría un QTableWidget para agregar componentes si el usuario elige "Compuesto"
        self.tabla_componentes = QTableWidget()
        self.tabla_componentes.setColumnCount(3)
        self.tabla_componentes.setHorizontalHeaderLabels(["ID Prod.", "Nombre", "Cantidad"])
        layout_compuesto.addWidget(self.tabla_componentes)
        
        # --- BOTONES DE ACCIÓN ---
        layout_principal.addWidget(tabs)
        
        btn_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        # Remove default button so Enter doesn't auto-accept (prevents scanner auto-save)
        save_btn = btn_box.button(QDialogButtonBox.Save)
        if save_btn:
            save_btn.setText("Guardar")
            save_btn.setObjectName("primaryBtn")
            save_btn.setDefault(False)
            save_btn.setAutoDefault(False)
        cancel_btn = btn_box.button(QDialogButtonBox.Cancel)
        if cancel_btn:
            cancel_btn.setText("Cancelar")
            cancel_btn.setObjectName("secondaryBtn")
        btn_box.accepted.connect(self.guardar_producto)
        btn_box.rejected.connect(self.reject)
        layout_principal.addWidget(btn_box)

    def al_cambiar_tipo(self, tipo):
        """Habilita o deshabilita la pestaña de compuestos."""
        self.tab_compuesto.setEnabled(tipo == "Compuesto")

    def cargar_categorias(self):
        """Carga las categorías únicas existentes."""
        try:
            cursor = self.container.db.cursor()
            cats = cursor.execute("SELECT DISTINCT categoria FROM productos WHERE categoria IS NOT NULL").fetchall()
            self.cmb_categoria.addItems([c[0] for c in cats])
        except: pass

    def cargar_imagen(self):
        """Abre el diálogo para seleccionar una imagen."""
        ruta, _ = QFileDialog.getOpenFileName(self, "Seleccionar Imagen", "", "Imágenes (*.png *.jpg *.jpeg *.webp)")
        if ruta:
            # Copiar a la carpeta local del proyecto
            nombre_archivo = f"prod_{datetime.now().strftime('%Y%m%d%H%M%S')}{os.path.splitext(ruta)[1]}"
            ruta_destino = os.path.join("imagenes_productos", nombre_archivo)
            
            try:
                shutil.copy(ruta, ruta_destino)
                self.ruta_imagen_actual = ruta_destino
                self.mostrar_imagen_previa(ruta_destino)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"No se pudo copiar la imagen: {e}")

    def mostrar_imagen_previa(self, ruta):
        if ruta and os.path.exists(ruta):
            pixmap = QPixmap(ruta).scaled(180, 180, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.lbl_imagen.setPixmap(pixmap)
        else:
            self.quitar_imagen()

    def quitar_imagen(self):
        self.ruta_imagen_actual = None
        self.lbl_imagen.clear()
        self.lbl_imagen.setText("Sin Imagen")

    def cargar_datos_producto(self):
        """Si estamos editando, carga los datos actuales del producto."""
        try:
            cursor = self.container.db.cursor()
            prod = cursor.execute("SELECT * FROM productos WHERE id = ?", (self.producto_id,)).fetchone()
            if prod:
                p = dict(prod)
                self.txt_nombre.setText(p.get('nombre', ''))
                self.txt_codigo.setText(p.get('codigo', ''))
                self.txt_codigo_barras.setText(p.get('codigo_barras', ''))
                self.cmb_categoria.setCurrentText(p.get('categoria', ''))
                self.txt_precio.setValue(p.get('precio', 0.0))
                self.txt_costo.setValue(p.get('precio_compra', 0.0) or p.get('costo', 0.0))
                self.cmb_unidad.setCurrentText(p.get('unidad', 'pza'))
                self.txt_stock_minimo.setValue(p.get('stock_minimo', 0.0))
                
                tipo = p.get('tipo_producto', 'simple')
                if p.get('es_compuesto'): tipo = "Compuesto"
                if p.get('es_subproducto'): tipo = "Subproducto"
                self.cmb_tipo.setCurrentText(tipo.capitalize())
                
                self.ruta_imagen_actual = p.get('imagen_path')
                self.mostrar_imagen_previa(self.ruta_imagen_actual)
        except Exception as e:
            logger.error(f"Error cargando producto {self.producto_id}: {e}")

    def _auto_calcular_precio_minimo(self) -> None:
        """Auto-calcula el precio mínimo como costo × (1 + margen_objetivo%)."""
        try:
            costo = self.txt_costo.value()
            if costo > 0 and hasattr(self, 'txt_precio_minimo'):
                # Get margen_objetivo from DB or default to 30%
                margen = 30.0
                try:
                    r = self.container.db.execute(
                        "SELECT COALESCE(AVG(margen_objetivo_pct),30) FROM productos WHERE id=?",
                        (self.producto_id or 0,)).fetchone()
                    if r and r[0]: margen = float(r[0])
                except Exception:
                    pass
                precio_min = round(costo * (1 + margen / 100), 2)
                # Only auto-set if currently empty or lower than cost
                current = self.txt_precio_minimo.value()
                if current < costo:
                    self.txt_precio_minimo.setValue(precio_min)
        except Exception:
            pass

    def guardar_producto(self):
        nombre = self.txt_nombre.text().strip()
        precio = self.txt_precio.value()
        
        if not nombre:
            QMessageBox.warning(self, "Validación", "El nombre es obligatorio.")
            return
            
        tipo = self.cmb_tipo.currentText()
        es_compuesto = 1 if tipo == "Compuesto" else 0
        es_subproducto = 1 if tipo == "Subproducto" else 0
        tipo_str = "compuesto" if es_compuesto else "subproducto" if es_subproducto else "simple"

        # codigo_val must be defined before the if/else so both branches can use it
        codigo_val = self.txt_codigo.text().strip() or None

        # v13.30: Auto-generar código único si está vacío
        if not codigo_val:
            import uuid as _uuid
            codigo_val = f"P-{_uuid.uuid4().hex[:8].upper()}"

        try:
            cursor = self.container.db.cursor()
            if self.producto_id:
                # UPDATE — check for duplicate codigo (excluding self)
                if codigo_val:
                    existing = cursor.execute(
                        "SELECT id FROM productos WHERE codigo=? AND id!=?",
                        (codigo_val, self.producto_id)
                    ).fetchone()
                    if existing:
        # [spj-dedup removed local QMessageBox import]
                        QMessageBox.warning(self, "Código duplicado",
                            f"El código '{codigo_val}' ya está en uso por otro producto.")
                        return
                query = """
                    UPDATE productos SET 
                        nombre=?, codigo=?, codigo_barras=?, categoria=?, precio=?, precio_compra=?, precio_minimo_venta=?, 
                        unidad=?, stock_minimo=?, tipo_producto=?, es_compuesto=?, es_subproducto=?, 
                        imagen_path=?, ultima_actualizacion=datetime('now')
                    WHERE id=?
                """
                cursor.execute(query, (
                    nombre, codigo_val, self.txt_codigo_barras.text(), self.cmb_categoria.currentText(),
                    precio, self.txt_costo.value(), getattr(self, "txt_precio_minimo", type("x", (), {"value": lambda s: 0})()).value(), self.cmb_unidad.currentText(), self.txt_stock_minimo.value(),
                    tipo_str, es_compuesto, es_subproducto, self.ruta_imagen_actual, self.producto_id
                ))
            else:
                # INSERT
                # v13.30: Verificar duplicado por código
                existing = cursor.execute(
                    "SELECT id, nombre FROM productos WHERE codigo=?", (codigo_val,)
                ).fetchone()
                if existing:
                    QMessageBox.warning(
                        self, "Código duplicado",
                        f"El código '{codigo_val}' ya existe (Producto: {existing[1]}).\n"
                        "Usa un código diferente o deja el campo vacío para autogenerar."
                    )
                    return

                # v13.30: Verificar duplicado por nombre (evitar productos repetidos)
                dup_nombre = cursor.execute(
                    "SELECT id, codigo FROM productos WHERE LOWER(TRIM(nombre))=LOWER(TRIM(?)) AND activo=1",
                    (nombre,)
                ).fetchone()
                if dup_nombre:
                    resp = QMessageBox.question(
                        self, "⚠️ Producto similar existe",
                        f"Ya existe un producto activo con el nombre '{nombre}'\n"
                        f"(Código: {dup_nombre[1]}, ID: {dup_nombre[0]})\n\n"
                        "¿Deseas guardarlo de todas formas?",
                        QMessageBox.Yes | QMessageBox.No)
                    if resp != QMessageBox.Yes:
                        return

                query = """
                    INSERT INTO productos (
                        nombre, codigo, codigo_barras, categoria, precio, precio_compra, 
                        unidad, stock_minimo, tipo_producto, es_compuesto, es_subproducto, 
                        imagen_path, existencia, oculto, activo
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 1)
                """
                cursor.execute(query, (
                    nombre, codigo_val, self.txt_codigo_barras.text().strip(), self.cmb_categoria.currentText(),
                    precio, self.txt_costo.value(), self.cmb_unidad.currentText(), self.txt_stock_minimo.value(),
                    tipo_str, es_compuesto, es_subproducto, self.ruta_imagen_actual
                ))
                
            # ── Validate composite product has a recipe ──────────────────────────
            if es_compuesto:
                nuevo_id = self.producto_id
                if not nuevo_id:
                    row_id = cursor.execute("SELECT last_insert_rowid()").fetchone()
                    nuevo_id = row_id[0] if row_id else None
                if nuevo_id:
                    rec = self.container.db.execute(
                        "SELECT id FROM product_recipes WHERE base_product_id=? AND is_active=1",
                        (nuevo_id,)).fetchone()
                    if not rec:
                        from PyQt5.QtWidgets import QMessageBox as _QMB
                        _QMB.information(
                            self, "Receta pendiente",
                            "El producto fue guardado como compuesto.\n\n"
                            "⚠️  Aún no tiene una receta activa.\n"
                            "Ve al módulo Recetas y crea la receta para este producto "
                            "antes de procesarlo en ventas o producción.")

            self.container.db.commit()

            # Registrar en Auditoría
            if hasattr(self.container, 'audit_service'):
                accion = "ACTUALIZAR_PRODUCTO" if self.producto_id else "CREAR_PRODUCTO"
                self.container.audit_service.log_change(
                    usuario="Sistema", accion=accion, modulo="PRODUCTOS",
                    entidad="productos", entidad_id=str(self.producto_id)
                )

            # Publicar al EventBus — actualiza dashboard y sugerencias de forma reactiva
            try:
                from core.events.event_bus import get_bus
                get_bus().publish(
                    "PRODUCTO_MODIFICADO",
                    {
                        "producto_id": self.producto_id,
                        "nombre": nombre,
                        "precio": precio,
                        "sucursal_id": getattr(self.container, 'sucursal_id', 1),
                        "accion": "actualizar" if self.producto_id else "crear",
                    }
                )
            except Exception:
                pass  # EventBus opcional — no bloquea el guardado

            # EventBus: notificar cambio de producto
            try:
                from core.events.event_bus import get_bus, PRODUCTO_ACTUALIZADO, PRODUCTO_CREADO
                evento = PRODUCTO_ACTUALIZADO if self.producto_id else PRODUCTO_CREADO
                get_bus().publish(evento, {
                    "producto_id": self.producto_id,
                    "nombre":      nombre,
                    "precio":      precio,
                }, async_=True)
            except Exception: pass

            self.accept()
    
        except Exception as e:
            self.container.db.rollback()
            QMessageBox.critical(self, "Error BD", f"No se pudo guardar: {e}")

# ==============================================================================
# MODULO PRINCIPAL (Centro de Productos y Producción)
# ==============================================================================

class ModuloProductos(QWidget, RefreshMixin):
    """
    Centro de Gestión de Productos, Recetas y Procesamiento de Carne (Despiece).
    Integra todo el ciclo de vida del producto en un solo lugar.
    """
    def __init__(self, container, parent=None):
        super().__init__(parent)
        try: self._init_refresh(container, ["PRODUCTO_ACTUALIZADO", "PRODUCTO_CREADO", "COMPRA_REGISTRADA"])
        except Exception: pass
        self.container = container # 🧠 Recibimos el Cerebro
        # Extraemos la db para mantener compatibilidad si algo lo requiere
        self.conexion = container.db if hasattr(container, 'db') else container
        self.sucursal_id = 1
        self.usuario_actual = ""

        # ── Scanner de código de barras ───────────────────────────────────────
        # Captura input de lectores HID (teclado-emulado).
        # Si el código existe → selecciona y muestra el producto.
        # Si NO existe       → abre DialogoProducto con el código pre-cargado.
        self._scanner_buffer: str = ""
        self._scanner_timer = QTimer(self)
        self._scanner_timer.setSingleShot(True)
        self._scanner_timer.setInterval(80)
        self._scanner_timer.timeout.connect(self._procesar_scanner_producto)

        self.init_ui()

    def set_sucursal(self, sucursal_id: int, nombre_sucursal: str):
        self.sucursal_id = sucursal_id
        self.cargar_catalogo()

    def set_usuario_actual(self, usuario: str, rol: str):
        self.usuario_actual = usuario

    def init_ui(self):
        layout_principal = QVBoxLayout(self)
        
        self.lbl_titulo = create_heading(self, "🥩 Centro de Productos y Procesamiento Cárnico")
        layout_principal.addWidget(self.lbl_titulo)
        
        # --- PESTAÑAS DEL MÓDULO ---
        self.tabs = QTabWidget()
        self.tabs.setObjectName("tabWidget")
        
        self.tab_catalogo = QWidget()
        self.tab_sucursales = QWidget()

        self.tabs.addTab(self.tab_catalogo,   "📦 Catálogo de Productos")
        self.tabs.addTab(self.tab_sucursales, "🏪 Activación por Sucursal")

        self.setup_tab_catalogo()
        self.setup_tab_sucursales()
        
        layout_principal.addWidget(self.tabs)
        self.tabs.currentChanged.connect(self.al_cambiar_pestana)

    def al_cambiar_pestana(self, index):
        if index == 0: self.cargar_catalogo()

    # =========================================================
    # PESTAÑA 1: CATÁLOGO DE PRODUCTOS (CRUD ENTERPRISE)
    # =========================================================
    def setup_tab_catalogo(self):
        layout = QVBoxLayout(self.tab_catalogo)
        
        # ── Barra de búsqueda + filtros ───────────────────────────────────
        filtros_layout = QHBoxLayout()
        self.txt_buscar_prod = create_input(self, "🔍 Buscar por nombre, código o barras...", "Ingrese términos de búsqueda para filtrar productos")
        self.txt_buscar_prod.returnPressed.connect(self.cargar_catalogo)
        
        btn_buscar = create_primary_button(self, "🔍 Buscar", "Ejecutar búsqueda de productos")
        btn_buscar.clicked.connect(self.cargar_catalogo)

        # v13.30: Filtro de categoría
        self.cmb_filtro_cat = QComboBox()
        self.cmb_filtro_cat.addItem("📁 Todas")
        self.cmb_filtro_cat.setMinimumWidth(140)
        self.cmb_filtro_cat.currentIndexChanged.connect(self.cargar_catalogo)
        try:
            db = self.container.db if hasattr(self.container, 'db') else self.conexion
            cats = db.execute(
                "SELECT DISTINCT categoria FROM productos WHERE categoria IS NOT NULL AND categoria!='' ORDER BY categoria"
            ).fetchall()
            for r in cats:
                self.cmb_filtro_cat.addItem(r[0])
        except Exception:
            pass

        # v13.30: Filtro de estado
        self.cmb_filtro_estado = QComboBox()
        self.cmb_filtro_estado.addItems(["✅ Activos", "❌ Eliminados", "📋 Todos"])
        self.cmb_filtro_estado.setMinimumWidth(130)
        self.cmb_filtro_estado.currentIndexChanged.connect(self.cargar_catalogo)
        
        btn_nuevo = create_success_button(self, "➕ Nuevo Producto", "Crear un nuevo producto en el catálogo")
        btn_nuevo.clicked.connect(self.abrir_nuevo_producto)
        
        btn_historial_precio = create_secondary_button(self, "📈 Historial Precios", "Ver el historial de cambios de precio del producto seleccionado")
        btn_historial_precio.clicked.connect(self._ver_historial_precio)

        btn_importar = create_secondary_button(self, "📥 Importar Excel", 
            "Importar productos desde Excel (.xlsx)\nColumnas requeridas: nombre, precio\nOpcionales: codigo, codigo_barras, categoria, precio_compra, unidad, stock_minimo")
        btn_importar.clicked.connect(self._importar_excel)

        filtros_layout.addWidget(self.txt_buscar_prod, 2)
        filtros_layout.addWidget(self.cmb_filtro_cat)
        filtros_layout.addWidget(self.cmb_filtro_estado)
        filtros_layout.addWidget(btn_buscar)
        filtros_layout.addWidget(btn_nuevo)
        filtros_layout.addWidget(btn_historial_precio)
        filtros_layout.addWidget(btn_importar)
        layout.addLayout(filtros_layout)

        # v13.30: Contador de resultados
        self.lbl_conteo = create_caption(self, "")
        layout.addWidget(self.lbl_conteo)
        
        # Tabla de Catálogo
        self.tabla_productos = QTableWidget()
        self.tabla_productos.setColumnCount(9)
        self.tabla_productos.setHorizontalHeaderLabels(
            ["ID", "Código", "Cód.Barras", "Nombre", "Categoría", "Precio", "Stock", "Estado", "Acciones"])
        self.tabla_productos.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.tabla_productos.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla_productos.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla_productos.setAlternatingRowColors(True)
        self.tabla_productos.verticalHeader().setVisible(False)
        layout.addWidget(self.tabla_productos)

    def _on_refresh(self, event_type: str, data: dict) -> None:
        """Auto-refresh catalog on product or purchase events."""
        try: self.cargar_catalogo()
        except Exception: pass

    def cargar_catalogo(self):
        # Ensure codigo_barras column exists on any existing DB
        try:
            db = self.container.db if hasattr(self.container, 'db') else self.conexion
            db.execute("ALTER TABLE productos ADD COLUMN codigo_barras TEXT DEFAULT ''")
            try: db.commit()
            except Exception: pass
        except Exception: pass

        busqueda = self.txt_buscar_prod.text().strip()

        # v13.30: Leer filtros
        filtro_cat = ""
        if hasattr(self, 'cmb_filtro_cat'):
            cat_text = self.cmb_filtro_cat.currentText()
            if not cat_text.startswith("📁"):
                filtro_cat = cat_text

        filtro_estado = 0  # 0=activos, 1=eliminados, 2=todos
        if hasattr(self, 'cmb_filtro_estado'):
            filtro_estado = self.cmb_filtro_estado.currentIndex()

        try:
            query = ("SELECT id, codigo, COALESCE(codigo_barras,'') as codigo_barras, "
                     "nombre, categoria, precio, existencia, COALESCE(activo,1) as activo "
                     "FROM productos WHERE 1=1")
            params = []

            # Filtro estado
            if filtro_estado == 0:
                query += " AND COALESCE(activo,1)=1"
            elif filtro_estado == 1:
                query += " AND COALESCE(activo,1)=0"
            # else: todos

            # Filtro categoría
            if filtro_cat:
                query += " AND categoria=?"
                params.append(filtro_cat)

            # Búsqueda texto
            if busqueda:
                query += " AND (nombre LIKE ? OR codigo LIKE ? OR COALESCE(codigo_barras,'') LIKE ?)"
                params.extend([f'%{busqueda}%', f'%{busqueda}%', f'%{busqueda}%'])

            query += " ORDER BY activo DESC, nombre ASC LIMIT 1000"

            cursor = self.container.db.cursor() if hasattr(self.container, 'db') else self.conexion.cursor()
            rows = cursor.execute(query, params).fetchall()

            self.tabla_productos.setRowCount(0)
            from PyQt5.QtGui import QColor as _QC
            from PyQt5.QtWidgets import QHBoxLayout as _HL, QWidget as _QW

            for row_idx, row_data in enumerate(rows):
                self.tabla_productos.insertRow(row_idx)
                prod_id = row_data['id']
                activo = int(row_data['activo']) if 'activo' in row_data.keys() else 1
                is_deleted = not activo

                # Color de fondo para productos eliminados
                bg_color = _QC("#fde8e8") if is_deleted else None

                self.tabla_productos.setItem(row_idx, 0, QTableWidgetItem(str(prod_id)))
                self.tabla_productos.setItem(row_idx, 1, QTableWidgetItem(str(row_data['codigo'] or '')))
                self.tabla_productos.setItem(row_idx, 2, QTableWidgetItem(
                    str(row_data['codigo_barras'] if 'codigo_barras' in row_data.keys() else '')))
                self.tabla_productos.setItem(row_idx, 3, QTableWidgetItem(str(row_data['nombre'])))
                self.tabla_productos.setItem(row_idx, 4, QTableWidgetItem(str(row_data['categoria'] or '')))
                self.tabla_productos.setItem(row_idx, 5, QTableWidgetItem(f"${row_data['precio']:.2f}"))
                self.tabla_productos.setItem(row_idx, 6, QTableWidgetItem(f"{row_data['existencia']:.3f}"))

                # v13.30: Estado con color y texto claro
                estado_txt = "✅ Activo" if activo else "❌ Eliminado"
                estado_item = QTableWidgetItem(estado_txt)
                if is_deleted:
                    estado_item.setForeground(_QC("#e74c3c"))
                else:
                    estado_item.setForeground(_QC("#27ae60"))
                self.tabla_productos.setItem(row_idx, 7, estado_item)

                # v13.30: Colorear toda la fila si está eliminado
                if bg_color:
                    for ci in range(8):
                        it = self.tabla_productos.item(row_idx, ci)
                        if it:
                            it.setBackground(bg_color)
                            it.setForeground(_QC("#999"))

                # ── Acciones ──────────────────────────────────────────────
                _cell = _QW(); _lay = _HL(_cell)
                _lay.setContentsMargins(2, 2, 2, 2); _lay.setSpacing(2)

                btn_editar = create_secondary_button(self, "✏️", "Editar producto")
                btn_editar.setFixedWidth(30)
                btn_editar.clicked.connect(lambda _, pid=prod_id: self.abrir_editar_producto(pid))
                _lay.addWidget(btn_editar)

                if activo:
                    # Producto activo: ocultar + eliminar
                    btn_toggle = create_secondary_button(self, "🙈", "Ocultar del POS")
                    btn_toggle.setFixedWidth(30)
                    btn_toggle.clicked.connect(
                        lambda _, pid=prod_id, a=activo: self._toggle_activo(pid, a))
                    _lay.addWidget(btn_toggle)

                    btn_del = create_danger_button(self, "🗑️", "Eliminar (soft delete)")
                    btn_del.setFixedWidth(30)
                    btn_del.clicked.connect(
                        lambda _, pid=prod_id, nom=row_data['nombre']: self.eliminar_producto(pid, nom))
                    _lay.addWidget(btn_del)
                else:
                    # v13.30: Producto eliminado: botón RESTAURAR
                    btn_restaurar = create_success_button(self, "♻️", "Restaurar producto")
                    btn_restaurar.setFixedWidth(30)
                    btn_restaurar.clicked.connect(
                        lambda _, pid=prod_id, nom=row_data['nombre']: self._restaurar_producto(pid, nom))
                    _lay.addWidget(btn_restaurar)

                self.tabla_productos.setCellWidget(row_idx, 8, _cell)

            # v13.30: Actualizar conteo
            if hasattr(self, 'lbl_conteo'):
                total = len(rows)
                activos = sum(1 for r in rows if int(r['activo'] if 'activo' in r.keys() else 1))
                self.lbl_conteo.setText(
                    f"Mostrando {total} productos ({activos} activos, {total - activos} eliminados)")

        except Exception as e:
            logger.error(f"Error cargando catálogo: {e}")

    def abrir_nuevo_producto(self):
        # v13.30: Verificar permiso
        try:
            from core.permissions import verificar_permiso
            if not verificar_permiso(self.container, "productos.crear", self):
                return
        except Exception: pass
        dlg = DialogoProducto(self.container, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self.cargar_catalogo()

    def abrir_editar_producto(self, producto_id):
        try:
            from core.permissions import verificar_permiso
            if not verificar_permiso(self.container, "productos.editar", self):
                return
        except Exception: pass
        dlg = DialogoProducto(self.container, producto_id=producto_id, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self.cargar_catalogo()

    def eliminar_producto(self, producto_id, nombre):
        """Aplica un SOFT DELETE. Nunca borramos registros con historial financiero."""
        # v13.30: Verificar permiso
        try:
            from core.permissions import verificar_permiso
            if not verificar_permiso(self.container, "productos.eliminar", self):
                return
        except Exception: pass
        resp = QMessageBox.question(
            self, "Confirmar Borrado", 
            f"¿Está seguro de eliminar el producto '{nombre}'?\n(Se ocultará del catálogo pero se mantendrá en el historial).",
            QMessageBox.Yes | QMessageBox.No
        )
        if resp == QMessageBox.Yes:
            try:
                cursor = self.container.db.cursor() if hasattr(self.container, 'db') else self.conexion.cursor()
                # SOFT DELETE
                cursor.execute("UPDATE productos SET oculto = 1, activo = 0 WHERE id = ?", (producto_id,))
                
                if hasattr(self.container, 'db'): self.container.db.commit()
                else: self.conexion.commit()
                
                QMessageBox.information(self, "Éxito", "Producto eliminado correctamente.")
                self.cargar_catalogo()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"No se pudo eliminar: {e}")

    # =========================================================
    # PESTAÑA 2: INGENIERÍA DE RECETAS (Estructura Base)
    # =========================================================
    def setup_tab_recetas(self):
        layout = QHBoxLayout(self.tab_recetas)
        
        panel_lista = QGroupBox("Recetas de Despiece (Cortes)")
        layout_lista = QVBoxLayout(panel_lista)
        self.lista_recetas = QListWidget()
        layout_lista.addWidget(self.lista_recetas)
        layout_lista.addWidget(QPushButton("📝 Crear Nueva Receta"))
        
        panel_detalle = QGroupBox("Configuración de Rendimiento")
        layout_detalle = QVBoxLayout(panel_detalle)
        layout_detalle.addWidget(QLabel("Seleccione una receta a la izquierda para ver su configuración.\n\nEjemplo: 'Despiece Pollo Estándar' -> 30% Pechuga, 20% Pierna, 5% Merma."))
        layout_detalle.addStretch()
        
        layout.addWidget(panel_lista, 1)
        layout.addWidget(panel_detalle, 2)

    def cargar_recetas(self):
        # Aquí se cargarán las recetas usando tu RecipeRepository en el futuro
        self.lista_recetas.clear()
        self.lista_recetas.addItem("Despiece Pollo Estándar (Teórico)")

    # =========================================================
    # PESTAÑA 3: PROCESAMIENTO CÁRNICO (EJECUCIÓN DE DESPIECE)
    # =========================================================
    def setup_tab_procesamiento(self):
        layout = QVBoxLayout(self.tab_procesamiento)
        
        instrucciones = create_caption(self, "Seleccione una receta e ingrese el peso de la materia prima para ejecutar el despiece en el inventario.")
        layout.addWidget(instrucciones)
        
        panel_proc = QGroupBox("Orden de Producción")
        panel_proc.setObjectName("styledGroup")
        form_proc = QFormLayout(panel_proc)
        
        self.cmb_receta_ejecutar = create_combo(self, ["Seleccione una receta..."])
        self.txt_peso_entrada = QDoubleSpinBox()
        self.txt_peso_entrada.setRange(0.1, 9999.0)
        self.txt_peso_entrada.setSuffix(" kg")
        self.txt_peso_entrada.setDecimals(2)
        self.txt_peso_entrada.setObjectName("inputField")
        
        self.txt_merma_real = QDoubleSpinBox()
        self.txt_merma_real.setRange(0.0, 999.0)
        self.txt_merma_real.setSuffix(" kg")
        self.txt_merma_real.setObjectName("inputField")
        self.txt_merma_real.setToolTip("Pese la merma real (huesos, sangre). Dejar en 0 usa el teórico.")
        
        form_proc.addRow("Receta a Ejecutar:", self.cmb_receta_ejecutar)
        form_proc.addRow("Peso de Materia Prima (Pollo Entero):", self.txt_peso_entrada)
        form_proc.addRow("Merma Física Real (Opcional):", self.txt_merma_real)
        
        layout.addWidget(panel_proc)
        
        self.btn_ejecutar_despiece = create_primary_button(self, "⚙️ Iniciar Despiece y Actualizar Inventario", 
            "Ejecutar el despiece de la receta seleccionada y actualizar el inventario automáticamente")
        self.btn_ejecutar_despiece.clicked.connect(self.ejecutar_produccion)
        layout.addWidget(self.btn_ejecutar_despiece)
        
        layout.addStretch()

    def cargar_recetas_para_procesamiento(self):
        self.cmb_receta_ejecutar.clear()
        try:
            cursor = self.container.db.cursor() if hasattr(self.container, 'db') else self.conexion.cursor()
            rows = cursor.execute("SELECT id, nombre_receta FROM product_recipes WHERE activa = 1").fetchall()
            for row in rows:
                self.cmb_receta_ejecutar.addItem(row['nombre_receta'], row['id'])
        except Exception as e:
            pass

    def ejecutar_produccion(self):
        if self.cmb_receta_ejecutar.currentIndex() == -1:
            QMessageBox.warning(self, "Aviso", "Seleccione una receta primero.")
            return
            
        receta_id = self.cmb_receta_ejecutar.currentData()
        peso_entrada = self.txt_peso_entrada.value()
        
        resp = QMessageBox.question(
            self, "Confirmar Despiece", 
            f"¿Procesar {peso_entrada} kg de materia prima?\nEsto descontará el producto base y generará los subproductos en el inventario.",
            QMessageBox.Yes | QMessageBox.No
        )
        if resp == QMessageBox.No: return

        try:
            if hasattr(self.container, 'production_service'):
                resultado = self.container.production_service.execute_production(
                    recipe_id=receta_id, input_qty=peso_entrada, branch_id=self.sucursal_id, user_id=self.usuario_actual
                )
                QMessageBox.information(self, "Despiece Completado", f"Producción exitosa. Lote: {resultado.get('folio', 'N/A')}")
                self.txt_peso_entrada.setValue(0)
            else:
                QMessageBox.warning(self, "Aviso", "ProductionService no está conectado aún.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Ocurrió un error:\n{e}")

    def setup_tab_sucursales(self) -> None:
        """
        Pestaña para gestionar activación de productos por sucursal.
        Permite: activar/desactivar, precio local, stock mínimo local.
        """
        from PyQt5.QtWidgets import (
            QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
            QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
            QDoubleSpinBox, QMessageBox, QGroupBox
        )
        lay = QVBoxLayout(self.tab_sucursales)
        lay.setContentsMargins(12, 10, 12, 10); lay.setSpacing(10)

        # ── Info ──────────────────────────────────────────────────────────────
        lbl_info = QLabel(
            "Controla en qué sucursales está disponible cada producto, "
            "su precio local y su stock mínimo local. "
            "Precio/stock en blanco = usar valor global del catálogo."
        )
        lbl_info.setWordWrap(True)
        lbl_info.setObjectName("textSecondary")
        lay.addWidget(lbl_info)

        # ── Filtro por sucursal ───────────────────────────────────────────────
        top = QHBoxLayout()
        top.addWidget(QLabel("Ver sucursal:"))
        self._combo_suc_filter = create_combo(self, ["— Todas —"])
        self._combo_suc_filter.addItem("— Todas —", None)
        self._cargar_sucursales_combo_bp()
        self._combo_suc_filter.currentIndexChanged.connect(self._cargar_tabla_branch_products)
        top.addWidget(self._combo_suc_filter)
        top.addStretch()
        btn_refresh = create_secondary_button(self, "🔄 Actualizar", "Recargar la tabla de productos por sucursal")
        btn_refresh.clicked.connect(self._cargar_tabla_branch_products)
        top.addWidget(btn_refresh)
        lay.addLayout(top)

        # ── Tabla principal ───────────────────────────────────────────────────
        self._tbl_bp = QTableWidget()
        self._tbl_bp.setColumnCount(7)
        self._tbl_bp.setHorizontalHeaderLabels([
            "Sucursal", "Producto", "Activa", "Precio Local", "Stock Mín. Local",
            "Precio Global", "Sucursales inactivas"
        ])
        self._tbl_bp.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl_bp.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl_bp.verticalHeader().setVisible(False)
        self._tbl_bp.setAlternatingRowColors(True)
        hdr = self._tbl_bp.horizontalHeader()
        hdr.setSectionResizeMode(6, QHeaderView.Stretch)
        for i in range(6): hdr.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        lay.addWidget(self._tbl_bp)

        # ── Acciones ──────────────────────────────────────────────────────────
        grp = QGroupBox("Editar selección")
        grp_lay = QHBoxLayout(grp)
        grp_lay.addWidget(QLabel("Activo:"))
        self._combo_bp_activo = QComboBox()
        self._combo_bp_activo.addItems(["✅ Sí", "❌ No"])
        grp_lay.addWidget(self._combo_bp_activo)
        grp_lay.addWidget(QLabel("  Precio local ($):"))
        self._spin_bp_precio = QDoubleSpinBox()
        self._spin_bp_precio.setRange(0, 999999); self._spin_bp_precio.setDecimals(2)
        self._spin_bp_precio.setSpecialValueText("(global)")
        grp_lay.addWidget(self._spin_bp_precio)
        grp_lay.addWidget(QLabel("  Stock mínimo:"))
        self._spin_bp_stock_min = QDoubleSpinBox()
        self._spin_bp_stock_min.setRange(0, 999999); self._spin_bp_stock_min.setDecimals(3)
        self._spin_bp_stock_min.setSpecialValueText("(global)")
        grp_lay.addWidget(self._spin_bp_stock_min)
        grp_lay.addStretch()
        btn_guardar_bp = create_success_button(self, "💾 Guardar Cambios", "Guardar los cambios de activación, precio y stock mínimo del producto seleccionado")
        btn_guardar_bp.clicked.connect(self._guardar_branch_product)
        grp_lay.addWidget(btn_guardar_bp)
        lay.addWidget(grp)

        # Cargar datos iniciales
        self._cargar_tabla_branch_products()

    def _cargar_sucursales_combo_bp(self) -> None:
        try:
            conn = self.conexion
            rows = conn.execute(
                "SELECT id, nombre FROM sucursales WHERE activa=1 ORDER BY id"
            ).fetchall()
            for r in rows:
                self._combo_suc_filter.addItem(f"🏪 {r[1]}", r[0])
        except Exception as e:
            pass

    def _cargar_tabla_branch_products(self) -> None:
        from PyQt5.QtWidgets import QTableWidgetItem
        from PyQt5.QtGui import QColor
        from PyQt5.QtCore import Qt
        try:
            branch_id = self._combo_suc_filter.currentData()
            conn = self.conexion

            if branch_id:
                rows = conn.execute("""
                    SELECT s.nombre as suc_nombre, p.nombre as prod_nombre,
                           bp.activo, bp.precio_local, bp.stock_min_local,
                           p.precio as precio_global,
                           bp.branch_id, bp.product_id
                    FROM branch_products bp
                    JOIN sucursales s ON s.id = bp.branch_id
                    JOIN productos   p ON p.id = bp.product_id
                    WHERE bp.branch_id = ? AND p.activo = 1
                    ORDER BY p.nombre
                """, (branch_id,)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT s.nombre as suc_nombre, p.nombre as prod_nombre,
                           bp.activo, bp.precio_local, bp.stock_min_local,
                           p.precio as precio_global,
                           bp.branch_id, bp.product_id
                    FROM branch_products bp
                    JOIN sucursales s ON s.id = bp.branch_id
                    JOIN productos   p ON p.id = bp.product_id
                    WHERE p.activo = 1
                    ORDER BY s.nombre, p.nombre
                """).fetchall()

            self._tbl_bp.setRowCount(len(rows))
            for ri, r in enumerate(rows):
                # Calcular en qué sucursales está inactivo este producto
                inact = conn.execute("""
                    SELECT GROUP_CONCAT(s2.nombre, ', ')
                    FROM sucursales s2
                    LEFT JOIN branch_products bp2
                        ON bp2.branch_id = s2.id AND bp2.product_id = ?
                    WHERE s2.activa = 1
                      AND (bp2.activo = 0 OR bp2.activo IS NULL)
                """, (r["product_id"],)).fetchone()
                inact_txt = inact[0] if inact and inact[0] else "—"

                vals = [
                    r["suc_nombre"], r["prod_nombre"],
                    "✅ Sí" if r["activo"] else "❌ No",
                    f"${r['precio_local']:.2f}" if r["precio_local"] else "(global)",
                    f"{r['stock_min_local']:.3f}" if r["stock_min_local"] else "(global)",
                    f"${r['precio_global']:.2f}",
                    inact_txt,
                ]
                for ci, v in enumerate(vals):
                    it = QTableWidgetItem(str(v))
                    it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    if ci == 2 and "No" in str(v):
                        it.setForeground(QColor("#e74c3c"))
                    elif ci == 6 and v != "—":
                        it.setForeground(QColor("#e67e22"))
                    # Store branch_id/product_id for editing
                    if ci == 0:
                        it.setData(Qt.UserRole, (r["branch_id"], r["product_id"]))
                    self._tbl_bp.setItem(ri, ci, it)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("_cargar_tabla_branch_products: %s", e)

    def _guardar_branch_product(self) -> None:
        from PyQt5.QtCore import Qt
        # [spj-dedup removed local QMessageBox import]
        row = self._tbl_bp.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Aviso", "Selecciona una fila primero.")
            return
        item_data = self._tbl_bp.item(row, 0)
        if not item_data: return
        branch_id, product_id = item_data.data(Qt.UserRole)
        activo      = 1 if self._combo_bp_activo.currentIndex() == 0 else 0
        precio_local = self._spin_bp_precio.value() if self._spin_bp_precio.value() > 0 else None
        stock_min    = self._spin_bp_stock_min.value() if self._spin_bp_stock_min.value() > 0 else None
        try:
            self.conexion.execute("""
                INSERT INTO branch_products(branch_id, product_id, activo, precio_local, stock_min_local)
                VALUES(?,?,?,?,?)
                ON CONFLICT(branch_id, product_id) DO UPDATE SET
                    activo=excluded.activo,
                    precio_local=excluded.precio_local,
                    stock_min_local=excluded.stock_min_local,
                    updated_at=datetime('now')
            """, (branch_id, product_id, activo, precio_local, stock_min))
            self.conexion.commit()
            QMessageBox.information(self, "Guardado", "Configuración actualizada.")
            self._cargar_tabla_branch_products()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))


    def _ver_historial_precio(self) -> None:
        """Muestra el historial de cambios de precio del producto seleccionado."""
        from PyQt5.QtWidgets import (
            QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem,
            QHeaderView, QLabel, QPushButton, QMessageBox
        )
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QColor

        # Obtener producto seleccionado de la tabla
        tabla = self.tab_catalogo.findChild(QTableWidget)
        if not tabla or tabla.currentRow() < 0:
            QMessageBox.information(self, "Aviso",
                "Selecciona un producto en la tabla primero."); return

        item_id = tabla.item(tabla.currentRow(), 0)
        if not item_id: return
        prod_id  = int(item_id.text()) if item_id.text().isdigit() else None
        if not prod_id: return

        try:
            prod_row = self.conexion.execute(
                "SELECT nombre, precio, precio_compra FROM productos WHERE id=?",
                (prod_id,)
            ).fetchone()
            if not prod_row: return
            nombre_prod = prod_row[0]
            precio_actual = float(prod_row[1] or 0)

            rows = self.conexion.execute("""
                SELECT campo, precio_anterior, precio_nuevo,
                       diferencia_pct, usuario, changed_at
                FROM historial_precios
                WHERE producto_id=?
                ORDER BY changed_at DESC LIMIT 50
            """, (prod_id,)).fetchall()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudo cargar el historial: {e}")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"📈 Historial de Precios — {nombre_prod}")
        dlg.setMinimumWidth(620)
        lay = QVBoxLayout(dlg)

        lbl = create_subheading(self, f"<b>{nombre_prod}</b>  |  Precio actual: <b>${precio_actual:.2f}</b>")
        lay.addWidget(lbl)

        if not rows:
            lay.addWidget(QLabel(
                "Sin cambios registrados aún.\n"
                "Los cambios se registran automáticamente desde ahora."
            ))
        else:
            tbl = QTableWidget()
            tbl.setColumnCount(6)
            tbl.setHorizontalHeaderLabels([
                "Campo", "Precio anterior", "Precio nuevo",
                "Variación %", "Usuario", "Fecha"
            ])
            tbl.setEditTriggers(0)
            tbl.verticalHeader().setVisible(False)
            tbl.setAlternatingRowColors(True)
            hdr = tbl.horizontalHeader()
            hdr.setSectionResizeMode(5, QHeaderView.Stretch)
            for i in range(5): hdr.setSectionResizeMode(i, QHeaderView.ResizeToContents)
            tbl.setRowCount(len(rows))
            for ri, r in enumerate(rows):
                diff_pct = float(r[3] or 0)
                color = QColor("#e74c3c") if diff_pct > 10 else                         QColor("#27ae60") if diff_pct < 0 else None
                vals = [
                    str(r[0]), f"${float(r[1]):.2f}", f"${float(r[2]):.2f}",
                    f"{diff_pct:+.1f}%", str(r[4] or "—"), str(r[5] or "")[:16]
                ]
                for ci, v in enumerate(vals):
                    it = QTableWidgetItem(v)
                    it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    if ci > 0: it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    if ci == 3 and color:
                        it.setForeground(color)
                    tbl.setItem(ri, ci, it)
            lay.addWidget(tbl)

        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.setObjectName("secondaryBtn")
        btn_cerrar.clicked.connect(dlg.accept)
        lay.addWidget(btn_cerrar)
        dlg.exec_()


    def _importar_excel(self) -> None:
        """Importa productos masivamente desde un archivo Excel (.xlsx)."""
        from PyQt5.QtWidgets import QFileDialog, QProgressDialog
        from PyQt5.QtCore import Qt

        ruta, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar archivo Excel", "",
            "Excel (*.xlsx *.xls *.csv)")
        if not ruta:
            return

        try:
            import openpyxl
        except ImportError:
            QMessageBox.critical(
                self, "Dependencia faltante",
                "Instala openpyxl para importar Excel:\n  pip install openpyxl")
            return

        try:
            wb = openpyxl.load_workbook(ruta, read_only=True)
            ws = wb.active
            headers = [str(c.value or "").strip().lower() for c in next(ws.iter_rows(max_row=1))]

            # Mapeo flexible de columnas
            col = {}
            for req, aliases in {
                'nombre':        ['nombre','name','producto','descripcion'],
                'precio':        ['precio','price','precio_venta','pvp'],
                'codigo':        ['codigo','code','sku','clave'],
                'codigo_barras': ['codigo_barras','barcode','ean','upc'],
                'categoria':     ['categoria','category','departamento'],
                'precio_compra': ['precio_compra','costo','cost'],
                'unidad':        ['unidad','unit','um'],
                'stock_minimo':  ['stock_minimo','stock_min','minimo'],
            }.items():
                for alias in aliases:
                    if alias in headers:
                        col[req] = headers.index(alias)
                        break

            if 'nombre' not in col or 'precio' not in col:
                QMessageBox.warning(
                    self, "Formato incorrecto",
                    f"El archivo debe tener columnas 'nombre' y 'precio'.\n"
                    f"Columnas encontradas: {', '.join(headers)}")
                return

            rows = list(ws.iter_rows(min_row=2, values_only=True))
            total = len(rows)
            if total == 0:
                QMessageBox.information(self, "Sin datos", "El archivo no tiene filas de datos.")
                return

            prog = QProgressDialog(f"Importando {total} productos…", "Cancelar", 0, total, self)
            prog.setWindowModality(Qt.WindowModal)

            nuevos = actualizados = errores = 0
            for i, row in enumerate(rows):
                prog.setValue(i)
                if prog.wasCanceled():
                    break
                try:
                    nombre = str(row[col['nombre']] or "").strip()
                    precio = float(row[col['precio']] or 0)
                    if not nombre or precio < 0:
                        errores += 1; continue

                    vals = {
                        'nombre':        nombre,
                        'precio':        precio,
                        'codigo':        str(row[col['codigo']] or "") if 'codigo' in col else "",
                        'codigo_barras': str(row[col['codigo_barras']] or "") if 'codigo_barras' in col else "",
                        'categoria':     str(row[col['categoria']] or "General") if 'categoria' in col else "General",
                        'precio_compra': float(row[col['precio_compra']] or 0) if 'precio_compra' in col else 0.0,
                        'unidad':        str(row[col['unidad']] or "kg") if 'unidad' in col else "kg",
                        'stock_minimo':  float(row[col['stock_minimo']] or 5) if 'stock_minimo' in col else 5.0,
                    }

                    # Check if exists
                    existing = self.container.db.execute(
                        "SELECT id FROM productos WHERE nombre=? OR (codigo!='' AND codigo=?)",
                        (vals['nombre'], vals['codigo'])
                    ).fetchone()

                    if existing:
                        self.container.db.execute("""
                            UPDATE productos SET precio=?, precio_compra=?, categoria=?,
                                unidad=?, stock_minimo=? WHERE id=?
                        """, (vals['precio'], vals['precio_compra'], vals['categoria'],
                              vals['unidad'], vals['stock_minimo'], existing[0]))
                        actualizados += 1
                    else:
                        self.container.db.execute("""
                            INSERT INTO productos
                                (nombre,codigo,codigo_barras,categoria,precio,precio_compra,
                                 unidad,stock_minimo,existencia,activo)
                            VALUES(?,?,?,?,?,?,?,?,0,1)
                        """, (vals['nombre'], vals['codigo'], vals['codigo_barras'],
                              vals['categoria'], vals['precio'], vals['precio_compra'],
                              vals['unidad'], vals['stock_minimo']))
                        nuevos += 1
                except Exception:
                    errores += 1

            self.container.db.commit()
            prog.setValue(total)

            QMessageBox.information(
                self, "✅ Importación completa",
                f"Productos nuevos: {nuevos}\n"
                f"Actualizados:     {actualizados}\n"
                f"Con errores:      {errores}")
            self.cargar_catalogo()

        except Exception as e:
            QMessageBox.critical(self, "Error al importar", str(e))


    # ─────────────────────────────────────────────────────────────────────────
    # SCANNER DE CÓDIGO DE BARRAS
    # Captura input HID (lector emula teclado rápido).
    # Si existe → selecciona fila en tabla. Si no existe → abre diálogo nuevo.
    # ─────────────────────────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        """
        Intercepta el scanner HID SOLO cuando ningún campo de texto tiene el foco.
        Si un QLineEdit/QPlainTextEdit/QSpinBox tiene foco, deja que Qt
        maneje el evento normalmente para no interferir con la edición.
        """
        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import QLineEdit, QPlainTextEdit, QDoubleSpinBox, QSpinBox, QTextEdit

        focused = self.focusWidget()
        # If a text-input widget has focus, don't intercept
        if isinstance(focused, (QLineEdit, QPlainTextEdit, QDoubleSpinBox, QSpinBox, QTextEdit)):
            super().keyPressEvent(event)
            return

        text = event.text()
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self._scanner_buffer:
                self._scanner_timer.stop()
                self._procesar_scanner_producto()
                return
        if text and text.isprintable():
            self._scanner_buffer += text
            self._scanner_timer.start()
            return
        super().keyPressEvent(event)

    def _toggle_activo(self, producto_id: int, activo_actual: int) -> None:
        """Activa o inactiva (oculta del POS) un producto."""
        nuevo = 0 if activo_actual else 1
        label = "activado" if nuevo else "ocultado del POS"
        try:
            db = self.container.db if hasattr(self.container,'db') else self.conexion
            db.execute("UPDATE productos SET activo=? WHERE id=?", (nuevo, producto_id))
            try: db.commit()
            except Exception: pass
            self.cargar_catalogo()
        except Exception as e:
        # [spj-dedup removed local QMessageBox import]
            QMessageBox.critical(self, "Error", str(e))

    def _restaurar_producto(self, producto_id: int, nombre: str) -> None:
        """v13.30: Restaura un producto eliminado (soft delete → activo)."""
        resp = QMessageBox.question(
            self, "♻️ Restaurar Producto",
            f"¿Restaurar el producto '{nombre}'?\n\n"
            "Se volverá a mostrar en el POS y catálogo.",
            QMessageBox.Yes | QMessageBox.No)
        if resp != QMessageBox.Yes:
            return
        try:
            db = self.container.db if hasattr(self.container, 'db') else self.conexion
            db.execute("UPDATE productos SET activo=1, oculto=0 WHERE id=?", (producto_id,))
            try:
                db.commit()
            except Exception:
                pass
            QMessageBox.information(self, "✅ Restaurado",
                f"Producto '{nombre}' restaurado correctamente.")
            self.cargar_catalogo()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _procesar_scanner_producto(self) -> None:
        """
        Lógica principal del scanner en módulo Productos:
          1. Busca el código en la tabla productos.
          2. Si EXISTE  → selecciona y resalta la fila en la tabla del catálogo.
          3. Si NO existe → abre DialogoProducto con el código pre-cargado.
             El diálogo actual se conserva intacto; solo se pre-llena el campo.
        """
        codigo = self._scanner_buffer.strip()
        self._scanner_buffer = ""
        if not codigo:
            return

        try:
            conn = self.conexion
            row = conn.execute(
                """SELECT id FROM productos
                   WHERE (COALESCE(codigo_barras,'') = ? OR codigo = ?)
                   LIMIT 1""",
                (codigo, codigo)
            ).fetchone()

            if row:
                # Producto encontrado → seleccionar en la tabla
                self._seleccionar_producto_por_id(row[0])
            else:
                # Producto NO encontrado → abrir diálogo nuevo con código pre-cargado
                self._abrir_nuevo_producto_con_codigo(codigo)

        except Exception as e:
            logger.warning("Scanner productos: %s", e)

    def _seleccionar_producto_por_id(self, producto_id: int) -> None:
        """Resalta la fila del producto en la tabla del catálogo."""
        from PyQt5.QtWidgets import QTableWidget
        try:
            # Buscar QTableWidget en el tab_catalogo
            tabla = self.tab_catalogo.findChild(QTableWidget)
            if not tabla:
                return
            # Recargar para asegurar datos frescos
            if hasattr(self, "cargar_catalogo"):
                self.cargar_catalogo()
            for row_idx in range(tabla.rowCount()):
                item = tabla.item(row_idx, 0)
                if item and str(item.text()) == str(producto_id):
                    tabla.selectRow(row_idx)
                    tabla.scrollToItem(item)
                    # Cambiar al tab catálogo
                    if hasattr(self, "tabs"):
                        self.tabs.setCurrentWidget(self.tab_catalogo)
                    break
        except Exception as e:
            logger.warning("_seleccionar_producto_por_id: %s", e)

    def _abrir_nuevo_producto_con_codigo(self, codigo: str) -> None:
        """
        Abre el diálogo DialogoProducto existente con el código de barras
        pre-cargado. NO modifica el diálogo — solo pre-llena el campo.
        """
        from PyQt5.QtWidgets import QDialog
        try:
            dlg = DialogoProducto(self.container, parent=self)
            # Pre-llenar el campo de código de barras con el código escaneado
            if hasattr(dlg, "txt_codigo_barras"):
                dlg.txt_codigo_barras.setText(codigo)
            if dlg.exec_() == QDialog.Accepted:
                if hasattr(self, "cargar_catalogo"):
                    self.cargar_catalogo()
        except Exception as e:
            logger.warning("_abrir_nuevo_producto_con_codigo: %s", e)
    def closeEvent(self, event):
        """Detiene timers activos al cerrar el módulo."""
        try: self._scanner_timer.stop()
        except Exception: pass
        super().closeEvent(event)
