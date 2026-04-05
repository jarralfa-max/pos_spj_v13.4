
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
            # Le pedimos al repositorio las recetas
            # Asumiendo un método get_all_active_recipes()
            recetas = self.container.recipe_repo.get_all_active_recipes()
            for rec in recetas:
                # Guardamos el ID de la receta (rec['id']) de forma invisible en el item
                self.cmb_receta.addItem(rec['nombre_receta'], rec['id'])
        except Exception as e:
            QMessageBox.warning(self, "Error", "No se pudieron cargar las recetas.")

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

        # 🚀 LA MAGIA ENTERPRISE: Le pasamos la "papa caliente" al Servicio
        try:
            # El ProductionService (que debes tener en core/services/production_service.py)
            # se encargará de:
            # 1. Validar RBAC.
            # 2. Descontar el pollo entero (InventoryService).
            # 3. Calcular porcentajes matemáticos (ProductionEngine).
            # 4. Sumar las piezas resultantes (InventoryService).
            # 5. Guardar la bitácora de auditoría.
            resultado = self.container.production_service.execute_production(
                recipe_id=receta_id,
                input_qty=peso_entrada,
                branch_id=self.sucursal_id,
                user_id=self.usuario_actual,
                actual_waste=merma_real if merma_real > 0 else None
            )
            
            # Mostramos el desglose al usuario
            msg = f"✅ Producción exitosa. Folio: {resultado['folio']}\n\nSe generaron:\n"
            for item in resultado['productos_generados']:
                msg += f"• {item['nombre']}: {item['cantidad']:.2f} kg\n"
                
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