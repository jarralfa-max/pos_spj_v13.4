
# modulos/planeacion_compras.py
from modulos.spj_styles import spj_btn, apply_btn_styles
from modulos.design_tokens import Colors, Spacing, Typography, Borders
from modulos.ui_components import create_primary_button, create_success_button, create_secondary_button, create_heading, create_subheading, create_card, apply_tooltip
import sys
from PyQt5.QtWidgets import *
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor
import matplotlib
matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import logging

logger = logging.getLogger(__name__)

class ModuloPlaneacionCompras(QWidget):
    """
    Dashboard Predictivo de Inteligencia Comercial.
    Utiliza el ForecastService para proyectar la demanda futura.
    """
    def __init__(self, container, parent=None):
        super().__init__(parent)
        self.container = container # 🧠 Inyectamos el Ecosistema
        self.sucursal_id = 1
        self.init_ui()

    def set_usuario_actual(self, usuario: str, rol: str = "cajero") -> None:
        """Recibe el usuario activo al cambiar de sesión."""
        self.usuario_actual = usuario
        self.rol_actual = rol

    def set_sucursal(self, sucursal_id: int, nombre: str = "") -> None:
        """Recibe la sucursal activa."""
        self.sucursal_id = sucursal_id

    def set_sucursal(self, sucursal_id: int, nombre_sucursal: str):
        self.sucursal_id = sucursal_id
        self.cargar_productos()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Título
        lbl_titulo = QLabel("🧠 Planeación Inteligente de Compras (Machine Learning)")
        lbl_titulo.setObjectName("heading")
        layout.addWidget(lbl_titulo)

        # --- PANEL DE CONFIGURACIÓN ---
        panel_config = QGroupBox("Parámetros del Modelo Predictivo")
        config_layout = QHBoxLayout(panel_config)

        self.cmb_producto = QComboBox()
        self.cmb_producto.setMinimumWidth(200)
        self.cmb_producto.setObjectName("inputField")

        self.spin_historial = QSpinBox()
        self.spin_historial.setRange(7, 365)
        self.spin_historial.setValue(30)
        self.spin_historial.setSuffix(" días")
        self.spin_historial.setToolTip("Días de historia a analizar")
        self.spin_historial.setObjectName("inputField")

        self.spin_pronostico = QSpinBox()
        self.spin_pronostico.setRange(1, 30)
        self.spin_pronostico.setValue(7)
        self.spin_pronostico.setSuffix(" días")
        self.spin_pronostico.setToolTip("Días al futuro a predecir")
        self.spin_pronostico.setObjectName("inputField")

        self.spin_seguridad = QDoubleSpinBox()
        self.spin_seguridad.setRange(0, 9999)
        self.spin_seguridad.setValue(10.0)
        self.spin_seguridad.setSuffix(" kg/pza")
        self.spin_seguridad.setToolTip("Inventario base que nunca debe faltar")
        self.spin_seguridad.setObjectName("inputField")

        btn_generar = create_primary_button(self, "🔮 Generar Pronóstico", "Ejecutar modelo predictivo de compras")
        btn_generar.clicked.connect(self.ejecutar_pronostico)

        config_layout.addWidget(QLabel("Producto:"))
        config_layout.addWidget(self.cmb_producto)
        config_layout.addWidget(QLabel("Analizar últimos:"))
        config_layout.addWidget(self.spin_historial)
        config_layout.addWidget(QLabel("Predecir próximos:"))
        config_layout.addWidget(self.spin_pronostico)
        config_layout.addWidget(QLabel("Stock de Seguridad:"))
        config_layout.addWidget(self.spin_seguridad)
        config_layout.addWidget(btn_generar)
        config_layout.addStretch()

        layout.addWidget(panel_config)

        # --- CONTENEDOR PRINCIPAL: GRÁFICO Y RESUMEN ---
        h_layout = QHBoxLayout()

        # 1. Gráfica Matplotlib
        self.figure = Figure(figsize=(8, 5), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        h_layout.addWidget(self.canvas, stretch=3)

        # 2. Panel de Resultados y Recomendación
        panel_resultados = QFrame()
        panel_resultados.setObjectName("card")
        res_layout = QVBoxLayout(panel_resultados)

        lbl_res_titulo = QLabel("📊 Recomendación de Compra")
        lbl_res_titulo.setAlignment(Qt.AlignCenter)
        lbl_res_titulo.setObjectName("subheading")
        
        self.lbl_stock_actual = QLabel("Stock Actual: 0.00")
        self.lbl_stock_actual.setObjectName("textSecondary")
        self.lbl_venta_proyectada = QLabel("Demanda Proyectada: 0.00")
        self.lbl_venta_proyectada.setObjectName("textSecondary")
        
        self.lbl_recomendacion = QLabel("COMPRAR: 0.00")
        self.lbl_recomendacion.setAlignment(Qt.AlignCenter)
        self.lbl_recomendacion.setObjectName("heading")
        # El padding se maneja vía CSS global, no se necesita setStyleSheet inline

        btn_enviar_compras = create_success_button(self, "🛒 Generar Orden de Compra", "Crear orden de compra automática")
        btn_enviar_compras.clicked.connect(self.enviar_a_modulo_compras)

        res_layout.addWidget(lbl_res_titulo)
        res_layout.addWidget(self.lbl_stock_actual)
        res_layout.addWidget(self.lbl_venta_proyectada)
        res_layout.addStretch()
        res_layout.addWidget(self.lbl_recomendacion)
        res_layout.addWidget(btn_enviar_compras)

        h_layout.addWidget(panel_resultados, stretch=1)
        layout.addLayout(h_layout)

    def cargar_productos(self):
        self.cmb_producto.clear()
        try:
            cursor = self.container.db.cursor()
            # Cargar productos que tengan ventas previas para evitar modelos vacíos
            rows = cursor.execute("SELECT id, nombre FROM productos WHERE activo = 1 ORDER BY nombre").fetchall()
            for row in rows:
                self.cmb_producto.addItem(row['nombre'], row['id'])
        except Exception as e:
            logger.error(f"Error cargando productos para pronóstico: {e}")

    def ejecutar_pronostico(self):
        producto_id = self.cmb_producto.currentData()
        if not producto_id: return

        try:
            # 🚀 MAGIA ENTERPRISE: El servicio de IA hace los cálculos de Pandas y Statsmodels
            if hasattr(self.container, 'forecast_service'):
                resultado = self.container.forecast_service.generar_plan_compras(
                    producto_id=producto_id,
                    sucursal_id=self.sucursal_id,
                    dias_historial=self.spin_historial.value(),
                    dias_pronostico=self.spin_pronostico.value(),
                    stock_seguridad=self.spin_seguridad.value()
                )
                
                self.dibujar_grafica(resultado)
                self.actualizar_recomendacion(resultado['metricas'])
            else:
                QMessageBox.warning(self, "Servicio Inactivo", "El motor de pronósticos no está disponible.")

        except ValueError as ve:
            QMessageBox.warning(self, "Faltan Datos", str(ve)) # Ej: "No hay historial suficiente"
            self.figure.clear()
            self.canvas.draw()
        except RuntimeError as re:
            QMessageBox.critical(self, "Error de Entorno", str(re)) # Ej: "statsmodels no instalado"
        except Exception as e:
            QMessageBox.critical(self, "Error Fatal", f"Fallo al procesar el modelo: {str(e)}")

    def dibujar_grafica(self, data: dict):
        """Usa Matplotlib para renderizar la serie de tiempo recibida del backend."""
        self.figure.clear()
        ax = self.figure.add_subplot(111)

        # Datos históricos
        x_hist = data['historial_fechas']
        y_hist = data['historial_valores']
        
        # Datos proyectados
        x_pred = data['pronostico_fechas']
        y_pred = data['pronostico_valores']

        # Dibujar
        ax.plot(x_hist, y_hist, label='Ventas Históricas', color='#2980b9', marker='o')
        
        # Para que la línea se conecte, añadimos el último punto histórico a la predicción
        if x_hist and x_pred:
            x_pred_plot = [x_hist[-1]] + x_pred
            y_pred_plot = [y_hist[-1]] + y_pred
            ax.plot(x_pred_plot, y_pred_plot, label='Pronóstico IA', color='#e74c3c', linestyle='--', marker='x')

        ax.set_title(f"Pronóstico de Demanda: {self.cmb_producto.currentText()}")
        ax.set_ylabel("Cantidad Vendida")
        ax.grid(True, linestyle='--', alpha=0.7)
        ax.legend()
        
        # Rotar fechas si son muchas
        if len(x_hist) + len(x_pred) > 15:
            ax.set_xticks(ax.get_xticks()[::3]) # Mostrar cada 3 días
            
        self.figure.autofmt_xdate()
        self.canvas.draw()

    def actualizar_recomendacion(self, metricas: dict):
        """Actualiza el panel lateral con la decisión del algoritmo."""
        self.lbl_stock_actual.setText(f"Stock Actual en Bodega: <b>{metricas['stock_actual']:.2f}</b>")
        self.lbl_venta_proyectada.setText(f"Demanda Proyectada ({self.spin_pronostico.value()} días): <b>{metricas['venta_proyectada']:.2f}</b>")
        
        compra = metricas['compra_recomendada']
        self.lbl_recomendacion.setText(f"COMPRAR:\n{compra:.2f}")
        
        # Actualizar color dinámicamente según el resultado usando objectName en lugar de setStyleSheet
        if compra <= 0:
            self.lbl_recomendacion.setObjectName("textSecondary")
            self.lbl_recomendacion.setText("STOCK\nSUFICIENTE")
        else:
            self.lbl_recomendacion.setObjectName("textSuccess")
        
        # Forzar actualización de estilo
        self.lbl_recomendacion.style().unpolish(self.lbl_recomendacion)
        self.lbl_recomendacion.style().polish(self.lbl_recomendacion)

    def enviar_a_modulo_compras(self):
        """Crea un puente entre la predicción y la acción real de comprar."""
        compra_texto = self.lbl_recomendacion.text().replace("COMPRAR:\n", "")
        if "SUFICIENTE" in compra_texto:
            QMessageBox.information(self, "Aviso", "No necesitas comprar este producto actualmente.")
            return
            
        QMessageBox.information(self, "Redirección", f"En un flujo completo, esto enviaría {compra_texto} de {self.cmb_producto.currentText()} directamente al Módulo de Compras (compras_pro.py).")