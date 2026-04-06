
# modulos/produccion_carnica.py (o produccion.py)
from modulos.spj_styles import spj_btn, apply_btn_styles
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt

class ModuloProduccionCarnica(QWidget):
    def __init__(self, container, parent=None):
        super().__init__(parent)
        self.container = container # 🧠 Nuestro orquestador central
        self.sucursal_id = 1
        self.usuario_actual = ""
        
        self.init_ui()

    def set_sucursal(self, sucursal_id: int, nombre_sucursal: str):
        self.sucursal_id = sucursal_id
        self.cargar_recetas_disponibles()

    def set_usuario_actual(self, usuario: str, rol: str):
        self.usuario_actual = usuario

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        self.lbl_titulo = QLabel("🔪 Módulo de Producción y Despiece")
        self.lbl_titulo.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(self.lbl_titulo)
        
        # --- FORMULARIO DE PRODUCCIÓN ---
        form_layout = QFormLayout()
        
        # 1. Seleccionar qué vamos a despiezar
        self.cmb_receta = QComboBox()
        form_layout.addRow("Proceso / Receta:", self.cmb_receta)
        
        # 2. Cantidad de Materia Prima a procesar
        self.txt_peso_entrada = QDoubleSpinBox()
        self.txt_peso_entrada.setRange(0.1, 9999.0)
        self.txt_peso_entrada.setDecimals(2)
        self.txt_peso_entrada.setSuffix(" kg")
        form_layout.addRow("Peso de Materia Prima:", self.txt_peso_entrada)
        
        # 3. Merma Real (Opcional: Si pesaron la basura/huesos)
        self.txt_merma_fisica = QDoubleSpinBox()
        self.txt_merma_fisica.setRange(0.0, 999.0)
        self.txt_merma_fisica.setDecimals(2)
        self.txt_merma_fisica.setSuffix(" kg")
        self.txt_merma_fisica.setToolTip("Dejar en 0 para usar merma teórica de la receta")
        form_layout.addRow("Merma Física (Opcional):", self.txt_merma_fisica)
        
        layout.addLayout(form_layout)
        
        # --- BOTÓN DE ACCIÓN ---
        self.btn_procesar = QPushButton("⚙️ Ejecutar Despiece")
        self.btn_procesar.setStyleSheet("background-color: #e67e22; color: white; font-weight: bold; padding: 10px;")
        layout.addWidget(self.btn_procesar)
        layout.addStretch()
        
        # Conectar eventos
        self.btn_procesar.clicked.connect(self.ejecutar_produccion)

    def cargar_recetas_disponibles(self):
        """Llena el ComboBox con las recetas activas (Ej. Despiece de Pollo Estándar)"""
        self.cmb_receta.clear()
        try:
            recetas = self.container.recipe_repo.get_all(include_inactive=False)
            for rec in recetas:
                self.cmb_receta.addItem(rec['nombre_receta'], rec['id'])
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudieron cargar las recetas: {e}")

    def ejecutar_produccion(self):
        """Envía la orden de producción al cerebro del ERP."""
        if self.cmb_receta.currentIndex() == -1:
            QMessageBox.warning(self, "Aviso", "Seleccione una receta primero.")
            return
            
        receta_id = self.cmb_receta.currentData()
        peso_entrada = self.txt_peso_entrada.value()
        merma_real = self.txt_merma_fisica.value()
        
        # Confirmación de seguridad
        resp = QMessageBox.question(
            self, "Confirmar Despiece", 
            f"¿Procesar {peso_entrada} kg con esta receta?\nEsto descontará la materia prima y generará los subproductos.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if resp == QMessageBox.No:
            return

        try:
            engine = self.container.recipe_engine
            resultado = engine.ejecutar_produccion(
                receta_id=receta_id,
                cantidad_base=peso_entrada,
                usuario=self.usuario_actual or "Sistema",
                sucursal_id=self.sucursal_id,
            )

            # Mostramos el desglose al usuario
            folio = f"#{resultado.produccion_id}"
            msg = f"✅ Producción exitosa. Folio: {folio}\n\nSe generaron:\n"
            for comp in resultado.componentes:
                if comp.tipo in ("salida", "subproducto", "corte"):
                    msg += f"• {comp.nombre}: {comp.cantidad:.2f} kg\n"
                
            QMessageBox.information(self, "Despiece Completado", msg)
            
            # Limpiamos el formulario
            self.txt_peso_entrada.setValue(0)
            self.txt_merma_fisica.setValue(0)
            
        except PermissionError as e:
            QMessageBox.warning(self, "Acceso Denegado", str(e))
        except ValueError as e: # Ej: No hay suficiente pollo entero en inventario
            QMessageBox.warning(self, "No se puede procesar", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Error Fatal", f"Ocurrió un error en el motor de producción:\n{str(e)}")