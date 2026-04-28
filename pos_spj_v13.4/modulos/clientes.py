
# modulos/clientes.py
import os
import re
from modulos.spj_phone_widget import PhoneWidget
from modulos.spj_styles import spj_btn, apply_btn_styles
from modulos.spj_refresh_mixin import RefreshMixin
from modulos.design_tokens import Colors, Spacing, Typography, Borders
from modulos.ui_components import (
    create_primary_button, create_success_button, create_danger_button, create_secondary_button,
    create_input_field, create_combo, create_card, apply_tooltip, create_heading,
    create_subheading, create_caption, create_table_with_columns, create_table_button,
    FilterBar, LoadingIndicator, EmptyStateWidget, confirm_action, create_standard_tabs,
    wrap_in_scroll_area, PageHeader, Toast,
)
from core.events.event_bus import VENTA_COMPLETADA, PUNTOS_ACUMULADOS, NIVEL_CAMBIADO
from core.services.auto_audit import audit_write
from core.events.event_bus import get_bus
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
                            QPushButton, QTableWidget, QTableWidgetItem, QMessageBox,
                            QDialog, QFormLayout, QSpinBox, QDoubleSpinBox, QCheckBox,
                            QTabWidget, QAbstractItemView, QComboBox)
from PyQt5.QtCore import Qt, QRandomGenerator
from PyQt5.QtGui import QPixmap, QColor, QIcon
import sqlite3
from .base import ModuloBase


class ModuloClientes(ModuloBase): 
    def __init__(self, conexion, main_window=None):
        super().__init__(conexion, parent=main_window)
        # Accept AppContainer or direct db connection
        if hasattr(conexion, 'db'):
            self.container = conexion
            self.conexion  = conexion.db
        else:
            self.container = None
            self.conexion  = conexion
        # ClienteRepository: capa de datos para operaciones CRUD
        try:
            from repositories.cliente_repository import ClienteRepository
            self.repo = ClienteRepository(conexion)
        except Exception:
            self.repo = None
        self.main_window = main_window
        self.cliente_actual = None
        self.filtro_activo = True
        self.init_ui()
        self.conectar_eventos()

    def set_sucursal(self, sucursal_id: int, sucursal_nombre: str):
        """Recibe la sucursal activa desde MainWindow."""
        self.sucursal_id     = sucursal_id
        self.sucursal_nombre = sucursal_nombre

        
    def set_usuario_actual(self, usuario, rol):
        """Establece el usuario actual para el módulo"""
        self.usuario_actual = usuario
        self.rol_usuario = rol
        
    def _on_refresh(self, event_type: str, data: dict) -> None:
        """Auto-refresh client list when sales or loyalty events occur."""
        try: self.cargar_clientes()
        except Exception: pass

    def obtener_usuario_actual(self):
        """Obtiene el usuario actual para registrar en movimientos"""
        return self.usuario_actual if self.usuario_actual else "Sistema"

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        # --- Encabezado (PageHeader) ---
        self.page_header = PageHeader(
            self,
            title="👥 Gestión de Clientes",
            subtitle="Cartera, fidelización y segmentación",
        )
        layout.addWidget(self.page_header)

        # --- Barra de herramientas ---
        toolbar = QHBoxLayout()
        self._filter_bar = FilterBar(
            self,
            placeholder="Buscar por nombre, teléfono, ID o código QR...",
            combo_filters={"estado": ["Activos", "Todos", "Inactivos"]},
        )
        self._filter_bar.filters_changed.connect(lambda _v: self.cargar_clientes())
        self.busqueda_cliente = self._filter_bar.search
        self.combo_filtro = self._filter_bar._combos.get("estado")
        self.btn_buscar_cliente = QPushButton()
        self.btn_buscar_cliente.setObjectName("secondaryBtn")
        self.btn_buscar_cliente.setIcon(self.obtener_icono("search.png"))
        self.btn_buscar_cliente.setToolTip("Buscar Cliente")
        
        self.btn_nuevo_cliente = QPushButton("Nuevo Cliente")
        self.btn_nuevo_cliente.setObjectName("primaryBtn")
        self.btn_nuevo_cliente.setIcon(self.obtener_icono("add.png"))
        
        toolbar.addWidget(self._filter_bar, 1)
        toolbar.addWidget(self.btn_buscar_cliente)
        toolbar.addStretch()
        toolbar.addWidget(self.btn_nuevo_cliente)
        layout.addLayout(toolbar)
        self._loading = LoadingIndicator("Cargando clientes…", self)
        self._loading.hide()
        layout.addWidget(self._loading)

        # --- Tabla de Clientes ---
        self.tabla_clientes = create_table_with_columns(
            self, 
            columns=["ID", "Nombre", "Apellido", "Teléfono", "Puntos", "Nivel", "Saldo", "Límite Crédito", "Estado"],
            show_grid=False,
            alternating_colors=True
        )
        self.tabla_clientes.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla_clientes.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.tabla_clientes)
        self._empty_state = EmptyStateWidget(
            "Sin clientes",
            "No se encontraron clientes para el filtro seleccionado.",
            "📭",
            self,
        )
        self._empty_state.hide()
        layout.addWidget(self._empty_state)

        # --- Barra de estado/botones de acción ---
        acciones_layout = QHBoxLayout()
        self.btn_editar_cliente = QPushButton("Editar")
        self.btn_editar_cliente.setObjectName("outlineBtn")
        self.btn_editar_cliente.setIcon(self.obtener_icono("edit.png"))
        self.btn_editar_cliente.setEnabled(False)

        self.btn_eliminar_cliente = QPushButton("Eliminar")
        self.btn_eliminar_cliente.setObjectName("dangerBtn")
        self.btn_eliminar_cliente.setIcon(self.obtener_icono("delete.png"))
        self.btn_eliminar_cliente.setEnabled(False)

        self.btn_ver_historial = QPushButton("Historial")
        self.btn_ver_historial.setObjectName("secondaryBtn")
        self.btn_ver_historial.setIcon(self.obtener_icono("history.png"))
        self.btn_ver_historial.setEnabled(False)

        self.btn_asignar_tarjeta = QPushButton("Asignar Tarjeta")
        self.btn_asignar_tarjeta.setObjectName("secondaryBtn")
        self.btn_asignar_tarjeta.setIcon(self.obtener_icono("card.png"))
        self.btn_asignar_tarjeta.setEnabled(False)

        self.btn_ver_tarjetas = QPushButton("💳 Tarjetas")
        self.btn_ver_tarjetas.setObjectName("secondaryBtn")
        self.btn_ver_tarjetas.setEnabled(False)
        
        acciones_layout.addWidget(self.btn_editar_cliente)
        acciones_layout.addWidget(self.btn_eliminar_cliente)
        acciones_layout.addWidget(self.btn_ver_historial)
        acciones_layout.addWidget(self.btn_asignar_tarjeta)
        self.btn_rfm = create_secondary_button(self, "📊 Segmentación RFM", "Analizar segmentación RFM de clientes")
        self.btn_rfm.clicked.connect(self._abrir_rfm)
        acciones_layout.addWidget(self.btn_ver_tarjetas)
        acciones_layout.addWidget(self.btn_rfm)
        acciones_layout.addStretch()
        layout.addLayout(acciones_layout)

        self.setLayout(layout)

        # --- Conexiones ---
        self.busqueda_cliente.returnPressed.connect(self.buscar_clientes)
        self.btn_buscar_cliente.clicked.connect(self.buscar_clientes)
        self.combo_filtro.currentIndexChanged.connect(self.cargar_clientes)
        self.btn_nuevo_cliente.clicked.connect(self.nuevo_cliente)
        self.btn_editar_cliente.clicked.connect(self.editar_cliente)
        self.btn_eliminar_cliente.clicked.connect(self.eliminar_cliente)
        self.btn_ver_historial.clicked.connect(self.ver_historial_cliente)
        self.btn_asignar_tarjeta.clicked.connect(self.asignar_tarjeta_cliente)
        self.btn_ver_tarjetas.clicked.connect(self.ver_tarjetas_cliente)
        self.tabla_clientes.itemSelectionChanged.connect(self.actualizar_botones)

        # --- Inicialización ---
        self.cargar_clientes()
        
    def conectar_eventos(self):
        """Conectar a los eventos del sistema"""
        if hasattr(self.main_window, 'registrar_evento'):
            # Registrar handlers para eventos de otros módulos
            self.main_window.registrar_evento('venta_realizada', self.on_venta_realizada)
            self.main_window.registrar_evento('producto_actualizado', self.on_datos_actualizados)
            self.main_window.registrar_evento('gasto_creado', self.on_datos_actualizados)

    def desconectar_eventos(self):
        """Desconectar eventos al cerrar el módulo"""
        if hasattr(self.main_window, 'desregistrar_evento'):
            self.main_window.desregistrar_evento('venta_realizada', self.on_venta_realizada)
            self.main_window.desregistrar_evento('producto_actualizado', self.on_datos_actualizados)
            self.main_window.desregistrar_evento('gasto_creado', self.on_datos_actualizados)

    def on_venta_realizada(self, datos):
        """Actualizar cuando se realiza una venta (para puntos del cliente)"""
        if datos and 'cliente_id' in datos and datos['cliente_id']:
            print(f"Cliente {datos['cliente_id']} realizó una compra")
            # Si estamos viendo el historial de este cliente, actualizarlo
            if (hasattr(self, 'dialogo_historial') and 
                self.dialogo_historial and 
                self.dialogo_historial.id_cliente == datos['cliente_id']):
                self.dialogo_historial.cargar_historial_compras()

    def on_datos_actualizados(self, datos):
        """Actualizar datos generales cuando otros módulos cambian información"""
        print("Datos actualizados en módulo clientes")
        # Podrías actualizar información específica si es necesario

    def obtener_icono(self, nombre_icono):
        """Obtiene un icono de la carpeta de recursos o usa uno por defecto."""
        if os.path.exists(f"iconos/{nombre_icono}"):
            return QIcon(f"iconos/{nombre_icono}")
        return QIcon.fromTheme("document")

    def mostrar_mensaje(self, titulo, mensaje, icono=QMessageBox.Information, botones=QMessageBox.Ok):
        """Muestra un mensaje al usuario."""
        msg = QMessageBox(self)
        msg.setWindowTitle(titulo)
        msg.setText(mensaje)
        msg.setIcon(icono)
        msg.setStandardButtons(botones)
        return msg.exec_()

    def cargar_clientes(self):
        """Carga los clientes en la tabla según el filtro seleccionado."""
        if hasattr(self, "_loading"):
            self._loading.show()
        try:
            try:
                cursor = self.conexion.cursor()
                
                filtro = self.combo_filtro.currentText() if self.combo_filtro else "Activos"
                if filtro == "Activos":
                    condicion = "WHERE activo = 1"
                    params = ()
                elif filtro == "Inactivos":
                    condicion = "WHERE activo = 0"
                    params = ()
                else:
                    condicion = ""
                    params = ()

                query = f"""
                    SELECT id, nombre, COALESCE(apellido,'') as apellido, telefono, puntos, nivel_fidelidad, 
                           COALESCE(saldo,0) as saldo, COALESCE(limite_credito,0) as limite_credito, COALESCE(activo,1) as activo
                    FROM clientes
                    {condicion}
                    ORDER BY nombre
                """
                
                cursor.execute(query, params)
                clientes = cursor.fetchall()
            except sqlite3.Error as e:
                self.mostrar_mensaje("Error", f"Error al cargar clientes: {str(e)}", QMessageBox.Critical)
                clientes = []

            self.tabla_clientes.setRowCount(len(clientes))
            for row, cliente in enumerate(clientes):
                for col, valor in enumerate(cliente):
                    if col == 8:  # Columna de estado
                        estado_texto = "Activo" if valor == 1 else "Inactivo"
                        item = QTableWidgetItem(estado_texto)
                        if valor != 1:
                            item.setForeground(QColor('red'))
                        self.tabla_clientes.setItem(row, col, item)
                    elif col in [6, 7]:  # Saldo y Límite de crédito
                        item = QTableWidgetItem(f"${valor:,.2f}" if valor is not None else "$0.00")
                        self.tabla_clientes.setItem(row, col, item)
                    else:
                        self.tabla_clientes.setItem(row, col, QTableWidgetItem(str(valor) if valor is not None else ""))
            if hasattr(self, "_empty_state"):
                self._empty_state.setVisible(len(clientes) == 0)
        finally:
            if hasattr(self, "_loading"):
                self._loading.hide()

    def buscar_clientes(self):
        """Busca clientes según el texto ingresado."""
        texto = self.busqueda_cliente.text().strip()
        if not texto:
            self.cargar_clientes()
            return

        if hasattr(self, "_loading"):
            self._loading.show()
        try:
            cursor = self.conexion.cursor()
            
            filtro = self.combo_filtro.currentText()
            condicion_activo = ""
            if filtro == "Activos":
                condicion_activo = "AND c.activo = 1"
            elif filtro == "Inactivos":
                condicion_activo = "AND c.activo = 0"

            # Determinar el tipo de búsqueda
            if texto.startswith("CLI-") or texto.startswith("QR-"):
                # Búsqueda por código QR o ID
                consulta = f"""
                    SELECT c.id, c.nombre, COALESCE(c.apellido,'') as apellido, c.telefono, 
                           c.puntos, c.nivel_fidelidad, COALESCE(c.saldo,0) as saldo, COALESCE(c.limite_credito,0) as limite_credito, COALESCE(c.activo,1) as activo
                    FROM clientes c
                    WHERE (c.codigo_qr = ? OR c.id = ?)
                    {condicion_activo}
                """
                params = (texto, texto.split('-')[-1] if '-' in texto else texto)
            else:
                # Búsqueda por nombre, apellido, teléfono o ID (parcial)
                consulta = f"""
                    SELECT c.id, c.nombre, COALESCE(c.apellido,'') as apellido, c.telefono, 
                           c.puntos, c.nivel_fidelidad, COALESCE(c.saldo,0) as saldo, COALESCE(c.limite_credito,0) as limite_credito, COALESCE(c.activo,1) as activo
                    FROM clientes c
                    WHERE (c.nombre LIKE ? OR COALESCE(c.apellido,'') LIKE ? OR c.telefono LIKE ? OR c.id = ?)
                    {condicion_activo}
                """
                params = (f"%{texto}%", f"%{texto}%", f"%{texto}%", texto)

            cursor.execute(consulta, params)
            clientes = cursor.fetchall()

            self.tabla_clientes.setRowCount(len(clientes))
            for row, cliente in enumerate(clientes):
                for col, valor in enumerate(cliente):
                    if col == 8:  # Columna de estado
                        estado_texto = "Activo" if valor == 1 else "Inactivo"
                        item = QTableWidgetItem(estado_texto)
                        if valor != 1:
                            item.setForeground(QColor('red'))
                        self.tabla_clientes.setItem(row, col, item)
                    elif col in [6, 7]:  # Saldo y Límite de crédito
                        item = QTableWidgetItem(f"${valor:,.2f}" if valor is not None else "$0.00")
                        self.tabla_clientes.setItem(row, col, item)
                    else:
                        self.tabla_clientes.setItem(row, col, QTableWidgetItem(str(valor) if valor is not None else ""))

            if hasattr(self, "_empty_state"):
                self._empty_state.setVisible(len(clientes) == 0)
        except sqlite3.Error as e:
            self.mostrar_mensaje("Error", f"Error en búsqueda: {str(e)}", QMessageBox.Critical)
        finally:
            if hasattr(self, "_loading"):
                self._loading.hide()

    def nuevo_cliente(self):
        """Abre el diálogo para crear un nuevo cliente."""
        _uc = getattr(self.container, 'uc_cliente', None) if self.container else None
        dialogo = DialogoCliente(self.conexion, self, uc_cliente=_uc)
        if dialogo.exec_() == QDialog.Accepted:
            self.cargar_clientes()
            # NOTIFICAR EVENTO
            if hasattr(self.main_window, 'notificar_evento'):
                self.main_window.notificar_evento('cliente_creado', {
                    'modulo': 'clientes',
                    'accion': 'crear'
                })
                
    def editar_cliente(self):
        """Abre el diálogo para editar un cliente seleccionado."""
        fila_seleccionada = self.tabla_clientes.currentRow()
        if fila_seleccionada < 0:
            self.mostrar_mensaje("Advertencia", "Seleccione un cliente para editar.")
            return

        try:
            id_cliente = int(self.tabla_clientes.item(fila_seleccionada, 0).text())
            cursor = self.conexion.cursor()
            cursor.execute("SELECT * FROM clientes WHERE id = ?", (id_cliente,))
            cliente_data = cursor.fetchone()
            
            if cliente_data:
                columnas = [description[0] for description in cursor.description]
                cliente_dict = dict(zip(columnas, cliente_data))
                
                _uc = getattr(self.container, 'uc_cliente', None) if self.container else None
                dialogo = DialogoCliente(self.conexion, self, cliente_dict, uc_cliente=_uc)
                if dialogo.exec_() == QDialog.Accepted:
                    self.cargar_clientes()
                    # NOTIFICAR EVENTO
                    if hasattr(self.main_window, 'notificar_evento'):
                        self.main_window.notificar_evento('cliente_actualizado', {
                            'id': id_cliente,
                            'modulo': 'clientes'
                        })
            else:
                self.mostrar_mensaje("Error", "Cliente no encontrado.")

        except ValueError:
            self.mostrar_mensaje("Error", "ID de cliente inválido.")
        except sqlite3.Error as e:
            self.mostrar_mensaje("Error", f"Error al cargar datos del cliente: {str(e)}", QMessageBox.Critical)

    def eliminar_cliente(self):
        """Elimina un cliente (lógicamente, cambiando su estado a inactivo)."""
        fila_seleccionada = self.tabla_clientes.currentRow()
        if fila_seleccionada < 0:
            self.mostrar_mensaje("Advertencia", "Seleccione un cliente para eliminar.")
            return

        try:
            id_cliente = int(self.tabla_clientes.item(fila_seleccionada, 0).text())
            nombre_cliente = self.tabla_clientes.item(fila_seleccionada, 1).text()
            
            if confirm_action(
                self,
                "Confirmar Desactivación",
                f"¿Desactivar al cliente '{nombre_cliente}'?\n"
                "No se eliminarán datos financieros ni de trazabilidad.",
                confirm_text="Desactivar",
                cancel_text="Cancelar",
            ):
                cursor = self.conexion.cursor()
                cursor.execute("UPDATE clientes SET activo = 0, fecha_inactivacion = date('now') WHERE id = ?", (id_cliente,))
                self.conexion.commit()
                try:
                    _uid = getattr(self,"usuario_actual",None) or getattr(self,"usuario","Sistema")
                    _sid = getattr(self,"sucursal_id",1)
                    _ctr = getattr(self,"container",None)
                    if _ctr: audit_write(_ctr,modulo="CLIENTES",accion="MODIFICAR_CLIENTE",entidad="clientes",usuario=_uid,detalles="Cliente modificado",sucursal_id=_sid)
                except Exception: pass
                self.mostrar_mensaje("Éxito", "Cliente desactivado correctamente.")
                self.cargar_clientes()
                # NOTIFICAR EVENTO
                if hasattr(self.main_window, 'notificar_evento'):
                    self.main_window.notificar_evento('cliente_eliminado', {
                        'id': id_cliente,
                        'modulo': 'clientes'
                    })
                    
        except ValueError:
            self.mostrar_mensaje("Error", "ID de cliente inválido.")
        except sqlite3.Error as e:
            self.conexion.rollback()
            self.mostrar_mensaje("Error", f"Error al desactivar cliente: {str(e)}", QMessageBox.Critical)

    def ver_historial_cliente(self):
        """Muestra el historial de un cliente (compras, puntos, créditos, etc.)."""
        fila_seleccionada = self.tabla_clientes.currentRow()
        if fila_seleccionada < 0:
            self.mostrar_mensaje("Advertencia", "Seleccione un cliente para ver su historial.")
            return

        try:
            id_cliente = int(self.tabla_clientes.item(fila_seleccionada, 0).text())
            nombre_cliente = self.tabla_clientes.item(fila_seleccionada, 1).text()
            apellido_cliente = self.tabla_clientes.item(fila_seleccionada, 2).text() if self.tabla_clientes.item(fila_seleccionada, 2) else ""
            nombre_completo = f"{nombre_cliente} {apellido_cliente}".strip()

            dialogo = DialogoHistorialCliente(self.conexion, id_cliente, nombre_completo, self)
            dialogo.exec_()

        except ValueError:
            self.mostrar_mensaje("Error", "ID de cliente inválido.")
        except Exception as e:
            self.mostrar_mensaje("Error", f"Error al abrir historial: {str(e)}", QMessageBox.Critical)

    def asignar_tarjeta_cliente(self):
        """Asigna una tarjeta libre al cliente seleccionado (v9)."""
        fila = self.tabla_clientes.currentRow()
        if fila < 0:
            self.mostrar_mensaje("Advertencia", "Seleccione un cliente para asignar una tarjeta.")
            return
        try:
            id_cliente     = int(self.tabla_clientes.item(fila, 0).text())
            nombre_cliente = self.tabla_clientes.item(fila, 1).text()

            from core.services.card_batch_engine import CardBatchEngine
            eng = CardBatchEngine(self.conexion, self.usuario_actual or "admin")

            dlg = _DialogoAsignarTarjetaCliente(
                id_cliente, nombre_cliente, self.conexion, self
            )
            if dlg.exec_() == QDialog.Accepted and dlg.tarjeta_id:
                res = eng.asignar_tarjeta(dlg.tarjeta_id, id_cliente,
                                           motivo="asignacion_desde_clientes")
                if res.exito:
                    self.mostrar_mensaje("Tarjeta Asignada",
                        f"Tarjeta asignada correctamente a {nombre_cliente}.")
                    self.cargar_clientes()
                else:
                    self.mostrar_mensaje("Error", res.mensaje, QMessageBox.Warning)
        except ImportError:
            self.mostrar_mensaje("Módulo no disponible",
                "CardBatchEngine no disponible. Actualice la base de datos a v14.")
        except Exception as exc:
            self.mostrar_mensaje("Error", str(exc), QMessageBox.Critical)

    def ver_tarjetas_cliente(self):
        """Muestra tarjetas asignadas, historial de asignaciones y opciones de bloqueo (v9)."""
        fila = self.tabla_clientes.currentRow()
        if fila < 0:
            self.mostrar_mensaje("Advertencia", "Seleccione un cliente.")
            return
        try:
            id_cliente     = int(self.tabla_clientes.item(fila, 0).text())
            nombre_cliente = self.tabla_clientes.item(fila, 1).text()
            dlg = _DialogoTarjetasCliente(id_cliente, nombre_cliente, self.conexion, self)
            dlg.exec_()
            self.cargar_clientes()
        except Exception as exc:
            self.mostrar_mensaje("Error", str(exc), QMessageBox.Critical)

    def actualizar_botones(self):
        """Habilita/deshabilita botones según la selección en la tabla."""
        seleccionado = len(self.tabla_clientes.selectedItems()) > 0
        self.btn_editar_cliente.setEnabled(seleccionado)
        self.btn_eliminar_cliente.setEnabled(seleccionado)
        self.btn_ver_historial.setEnabled(seleccionado)
        self.btn_asignar_tarjeta.setEnabled(seleccionado)
        if hasattr(self, 'btn_ver_tarjetas'):
            self.btn_ver_tarjetas.setEnabled(seleccionado)

    def actualizar_datos(self):
        """Actualiza los datos del módulo."""
        self.cargar_clientes()

   
    def registrar_actualizacion(self, tipo_evento, detalles=None, usuario=None):
        """
        Registra actualizaciones del módulo de clientes.
        
        Args:
            tipo_evento (str): Tipo de evento ('cliente_creado', 'cliente_actualizado', etc.)
            detalles (str/dict): Detalles específicos del evento
            usuario (str): Usuario que realizó la acción
        """
        try:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            usuario_info = usuario if usuario else "Sistema"
            
            # Construir mensaje
            mensaje = f"[{timestamp}] [{usuario_info}] [CLIENTES] Evento: {tipo_evento}"
            
            if detalles:
                if isinstance(detalles, dict):
                    detalles_str = ", ".join([f"{k}:{v}" for k, v in detalles.items()])
                    mensaje += f" - {detalles_str}"
                else:
                    mensaje += f" - {detalles}"
            
            print(mensaje)
            
            # Guardar en archivo de log
            log_dir = "logs"
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)
                
            with open(f"{log_dir}/clientes_actualizaciones.log", "a", encoding="utf-8") as f:
                f.write(mensaje + "\n")
                
        except Exception as e:
            print(f"Error al registrar actualización en clientes: {e}")

    def _abrir_rfm(self):
        """Abre la segmentacion RFM de clientes."""
        try:
            dlg = _DialogoRFM(self.conexion, self)
            dlg.exec_()
        except Exception as e:
            # [spj-dedup] from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "RFM", f"Error al abrir segmentacion RFM:\n{e}")


class DialogoCliente(QDialog):
    def __init__(self, conexion, parent=None, cliente_data=None, uc_cliente=None):
        super().__init__(parent)
        self.conexion = conexion
        self.cliente_data = cliente_data
        self.uc_cliente = uc_cliente  # v13.5: UC opcional para delegación
        self.setWindowTitle("Nuevo Cliente" if not cliente_data else "Editar Cliente")
        self.setFixedSize(400, 500)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(Spacing.MD)
        layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)

        # Encabezado
        layout.addWidget(create_heading(self, "Nuevo Cliente" if not self.cliente_data else "Editar Cliente"))
        
        # Card principal con formulario
        card = create_card(self, padding=Spacing.MD, with_layout=False)
        form_layout = QFormLayout()
        form_layout.setSpacing(Spacing.SM)
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        
        # v13.4: Campo ID Tarjeta
        self.edit_tarjeta_id = create_input_field(self, "Escanear QR de tarjeta o escribir ID")
        
        self.edit_nombre = create_input_field(self, "Nombre completo*")
        self.edit_apellido = create_input_field(self, "Apellido")
        self.edit_telefono = PhoneWidget(default_country="+52")
        # setInputMask removed — PhoneWidget handles international format internally
        
        self.edit_puntos = QSpinBox()
        self.edit_puntos.setRange(0, 999999)
        self.edit_nivel = create_combo(self, ["Bronce", "Plata", "Oro", "Platino"])
        self.edit_nivel.setEditable(True)
        self.edit_descuento = QDoubleSpinBox()
        self.edit_descuento.setRange(0.0, 100.0)
        self.edit_descuento.setSuffix(" %")
        
        self.edit_saldo = QDoubleSpinBox()
        self.edit_saldo.setRange(-999999.99, 999999.99)
        self.edit_saldo.setPrefix("$ ")
        self.edit_limite_credito = QDoubleSpinBox()
        self.edit_limite_credito.setRange(0.0, 999999.99)
        self.edit_limite_credito.setPrefix("$ ")
        
        self.chk_activo = QCheckBox("Activo")
        self.chk_activo.setChecked(True)

        if self.cliente_data:
            self.edit_nombre.setText(self.cliente_data.get('nombre', ''))
            self.edit_apellido.setText(self.cliente_data.get('apellido', ''))
            self.edit_telefono.set_phone(self.cliente_data.get('telefono', ''))
            self.edit_puntos.setValue(self.cliente_data.get('puntos', 0))
            self.edit_nivel.setCurrentText(self.cliente_data.get('nivel_fidelidad', 'Bronce'))
            self.edit_descuento.setValue(self.cliente_data.get('descuento', 0.0))
            self.edit_saldo.setValue(self.cliente_data.get('saldo', 0.0))
            self.edit_limite_credito.setValue(self.cliente_data.get('limite_credito', 0.0))
            self.chk_activo.setChecked(self.cliente_data.get('activo', 1) == 1)
            # v13.4: Cargar tarjeta si existe
            self.edit_tarjeta_id.setText(self.cliente_data.get('codigo_qr', '') or '')

        form_layout.addRow("ID Tarjeta:", self.edit_tarjeta_id)
        form_layout.addRow("Nombre*:", self.edit_nombre)
        form_layout.addRow("Apellido:", self.edit_apellido)
        form_layout.addRow("Teléfono:", self.edit_telefono)
        form_layout.addRow("Puntos:", self.edit_puntos)
        form_layout.addRow("Nivel Fidelidad:", self.edit_nivel)
        form_layout.addRow("Descuento (%):", self.edit_descuento)
        form_layout.addRow("Saldo Crédito:", self.edit_saldo)
        form_layout.addRow("Límite Crédito:", self.edit_limite_credito)
        form_layout.addRow("", self.chk_activo)
        
        card.setLayout(form_layout)
        layout.addWidget(card)

        # Botones de acción
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(Spacing.SM)
        self.btn_guardar = create_primary_button(self, "💾 Guardar", "Guardar datos del cliente")
        self.btn_cancelar = create_secondary_button(self, "Cancelar", "Cancelar sin guardar")
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancelar)
        btn_layout.addWidget(self.btn_guardar)

        layout.addLayout(btn_layout)
        self.setLayout(layout)

        self.btn_guardar.clicked.connect(self.guardar)
        self.btn_cancelar.clicked.connect(self.reject)

    def validar_formulario(self):
        """Valida los datos del formulario."""
        if not self.edit_nombre.text().strip():
            QMessageBox.warning(self, "Error", "El nombre es obligatorio.")
            return False
        
        telefono = self.edit_telefono.get_e164().strip()
        # v13.30 FIX: Validar solo dígitos locales (sin código de país)
        # get_e164() retorna "+52XXXXXXXXXX" (12+ dígitos) — no comparar con 10
        digitos_locales = re.sub(r'\D', '', self.edit_telefono.get_number())
        if telefono and len(digitos_locales) != 10:
            QMessageBox.warning(self, "Error", "El teléfono debe tener 10 dígitos.")
            return False
            
        return True

    def generar_id_cliente(self):
        """Genera un ID de cliente único de 4 dígitos."""
        cursor = self.conexion.cursor()
        while True:
            nuevo_id = f"{QRandomGenerator.global_().bounded(1000, 10000)}"
            cursor.execute("SELECT COUNT(*) FROM clientes WHERE id = ?", (nuevo_id,))
            if cursor.fetchone()[0] == 0:
                return nuevo_id

    def guardar(self):
        """Guarda el cliente en la base de datos."""
        if not self.validar_formulario():
            return

        # v13.5: Delegar al UC cuando está disponible
        if self.uc_cliente:
            try:
                from core.use_cases.cliente import DatosCliente
                nombre = self.edit_nombre.text().strip()
                apellido = self.edit_apellido.text().strip() or ""
                telefono = self.edit_telefono.get_e164().strip() if hasattr(self.edit_telefono, 'get_e164') else self.edit_telefono.text().strip()
                limite_credito = self.edit_limite_credito.value()
                datos = DatosCliente(
                    nombre=f"{nombre} {apellido}".strip(),
                    telefono=telefono,
                    allows_credit=(limite_credito > 0),
                    credit_limit=limite_credito,
                )
                if self.cliente_data:
                    campos = {
                        'nombre': nombre, 'apellido': apellido, 'telefono': telefono,
                        'limite_credito': limite_credito, 'saldo': self.edit_saldo.value(),
                        'activo': 1 if self.chk_activo.isChecked() else 0,
                    }
                    result = self.uc_cliente.actualizar_cliente(self.cliente_data['id'], campos, "sistema")
                else:
                    result = self.uc_cliente.crear_cliente(datos, 1, "sistema")
                if result.ok:
                    Toast.success(self, "Éxito", result.mensaje or "Guardado correctamente.")
                    self.accept()
                else:
                    QMessageBox.critical(self, "Error", result.error)
                return
            except Exception as _e:
                pass  # fallback al SQL directo si el UC falla

        try:
            cursor = self.conexion.cursor()
            
            nombre = self.edit_nombre.text().strip()
            apellido = self.edit_apellido.text().strip() or None
            telefono = self.edit_telefono.get_e164().strip() or None
            puntos = self.edit_puntos.value()
            # QComboBox no expone .text(); usar currentText para evitar fallos al guardar
            nivel = self.edit_nivel.currentText().strip() or None
            descuento = self.edit_descuento.value()
            saldo = self.edit_saldo.value()
            limite_credito = self.edit_limite_credito.value()
            activo = 1 if self.chk_activo.isChecked() else 0
            
            # v13.4: Parsear tarjeta ID
            import re
            tarjeta_raw = self.edit_tarjeta_id.text().strip()
            tarjeta_id = ""
            if tarjeta_raw:
                m = re.match(r'^(?:TF|TAR|CARD)-(.+)$', tarjeta_raw, re.IGNORECASE)
                if m:
                    tarjeta_id = m.group(1).strip()
                elif re.match(r'^CLT-(\d+)', tarjeta_raw, re.IGNORECASE):
                    tarjeta_id = re.match(r'^CLT-(\d+)', tarjeta_raw, re.IGNORECASE).group(1)
                else:
                    tarjeta_id = tarjeta_raw

            if self.cliente_data:  # Editar
                id_cliente = self.cliente_data['id']
                cursor.execute("""
                    UPDATE clientes 
                    SET nombre = ?, apellido = ?, telefono = ?, puntos = ?, nivel_fidelidad = ?,
                        descuento = ?, saldo = ?, limite_credito = ?, activo = ?,
                        codigo_qr = CASE WHEN ? != '' THEN ? ELSE codigo_qr END
                    WHERE id = ?
                """, (nombre, apellido, telefono, puntos, nivel, descuento, saldo, 
                      limite_credito, activo, tarjeta_id, tarjeta_id, id_cliente))
                
                # v13.4: Crear/actualizar tarjeta de fidelidad si se proporcionó
                if tarjeta_id:
                    try:
                        cursor.execute("""
                            INSERT INTO tarjetas_fidelidad (codigo, id_cliente, nivel, activa, fecha_emision)
                            VALUES (?, ?, COALESCE(?, 'Bronce'), 1, datetime('now'))
                            ON CONFLICT(codigo) DO UPDATE SET id_cliente = ?, activa = 1
                        """, (tarjeta_id, id_cliente, nivel, id_cliente))
                    except Exception:
                        pass
                
                self.conexion.commit()
                try: get_bus().publish("CLIENTE_ACTUALIZADO", {"event_type": "CLIENTE_ACTUALIZADO"})
                except Exception: pass
                Toast.success(self, "Éxito", "Cliente actualizado correctamente.")
                self.accept()
            else:  # Nuevo
                cursor.execute("""
                    SELECT COUNT(*) FROM clientes
                    WHERE nombre = ? AND COALESCE(apellido,'') = ? AND telefono = ?
                """, (nombre, apellido, telefono))
                if cursor.fetchone()[0] > 0:
                    respuesta = QMessageBox.question(
                        self, "Cliente Existente",
                        "Ya existe un cliente con estos datos. ¿Desea crearlo de todos modos?",
                        QMessageBox.Yes | QMessageBox.No
                    )
                    if respuesta == QMessageBox.No:
                        return
                
                id_cliente = self.generar_id_cliente()
                cursor.execute("""
                    INSERT INTO clientes (id, nombre, apellido, telefono, puntos, nivel_fidelidad, 
                                        descuento, saldo, limite_credito, activo, codigo_qr)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (id_cliente, nombre, apellido, telefono, puntos, nivel, descuento, 
                      saldo, limite_credito, activo, tarjeta_id or None))
                
                # v13.4: Crear tarjeta de fidelidad si se proporcionó ID
                if tarjeta_id:
                    try:
                        cursor.execute("""
                            INSERT OR IGNORE INTO tarjetas_fidelidad 
                                (codigo, id_cliente, nivel, activa, fecha_emision)
                            VALUES (?, ?, 'Bronce', 1, datetime('now'))
                        """, (tarjeta_id, id_cliente))
                    except Exception:
                        pass
                
                self.conexion.commit()
                Toast.success(self, "Cliente creado", f"ID: {id_cliente}")
                self.accept()

        except sqlite3.IntegrityError as e:
            self.conexion.rollback()
            QMessageBox.warning(self, "Error", f"Error de integridad: {str(e)}")
        except sqlite3.Error as e:
            self.conexion.rollback()
            QMessageBox.critical(self, "Error", f"Error en la base de datos: {str(e)}")
        except Exception as e:
            self.conexion.rollback()
            QMessageBox.critical(self, "Error", f"Error inesperado: {str(e)}")


class DialogoHistorialCliente(QDialog):
    def __init__(self, conexion, id_cliente, nombre_cliente, parent=None):
        super().__init__(parent)
        self.conexion = conexion
        self.id_cliente = id_cliente
        self.nombre_cliente = nombre_cliente
        self.setWindowTitle(f"Historial de {nombre_cliente}")
        self.resize(800, 600)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(Spacing.MD)
        layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)

        # Encabezado con información del cliente
        layout.addWidget(create_heading(self, f"Historial de {self.nombre_cliente}"))
        layout.addWidget(create_subheading(self, f"ID: {self.id_cliente}"))
        
        tabs = create_standard_tabs(self)
        tabs.setObjectName("historialTabs")
        
        # Pestaña de Compras
        self.tab_compras = QWidget()
        layout_compras = QVBoxLayout()
        layout_compras.setSpacing(Spacing.SM)
        layout_compras.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        
        layout_compras.addWidget(create_subheading(self, "Compras realizadas"))
        self.tabla_compras = create_table_with_columns(
            self, 
            columns=["Fecha", "Total", "Método Pago", "Puntos Ganados", "Detalles"],
            show_grid=False,
            alternating_colors=True
        )
        layout_compras.addWidget(self.tabla_compras)
        self.tab_compras.setLayout(layout_compras)
        tabs.addTab(self.tab_compras, "🛒 Compras")

        # Pestaña de Puntos
        self.tab_puntos = QWidget()
        layout_puntos = QVBoxLayout()
        layout_puntos.setSpacing(Spacing.SM)
        layout_puntos.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        
        layout_puntos.addWidget(create_subheading(self, "Movimientos de puntos"))
        self.tabla_puntos = create_table_with_columns(
            self,
            columns=["Fecha", "Tipo", "Puntos", "Saldo Actual", "Descripción"],
            show_grid=False,
            alternating_colors=True
        )
        layout_puntos.addWidget(self.tabla_puntos)
        self.tab_puntos.setLayout(layout_puntos)
        tabs.addTab(self.tab_puntos, "⭐ Puntos")

        # Pestaña de Créditos
        self.tab_creditos = QWidget()
        layout_creditos = QVBoxLayout()
        layout_creditos.setSpacing(Spacing.SM)
        layout_creditos.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
        
        layout_creditos.addWidget(create_subheading(self, "Movimientos de crédito"))
        self.tabla_creditos = create_table_with_columns(
            self,
            columns=["Fecha", "Tipo", "Monto", "Descripción", "Usuario"],
            show_grid=False,
            alternating_colors=True
        )
        layout_creditos.addWidget(self.tabla_creditos)
        self.tab_creditos.setLayout(layout_creditos)
        tabs.addTab(self.tab_creditos, "💳 Créditos")

        layout.addWidget(tabs)
        
        # Botón de cierre
        btn_cerrar = create_secondary_button(self, "Cerrar", "Cerrar ventana de historial")
        btn_cerrar.clicked.connect(self.close)
        row_cierre = QHBoxLayout()
        row_cierre.addStretch()
        row_cierre.addWidget(btn_cerrar)
        layout.addLayout(row_cierre)
        
        self.setLayout(layout)
        
        self.cargar_historial_compras()
        self.cargar_historial_puntos()
        self.cargar_historial_creditos()

    def cargar_historial_compras(self):
        """Carga el historial de compras del cliente."""
        try:
            cursor = self.conexion.cursor()
            cursor.execute("""
                SELECT fecha, total, metodo_pago, puntos_ganados 
                FROM ventas 
                WHERE cliente_id = ? 
                ORDER BY fecha DESC
            """, (self.id_cliente,))
            ventas = cursor.fetchall()
            
            self.tabla_compras.setRowCount(len(ventas))
            for row, venta in enumerate(ventas):
                for col, valor in enumerate(venta):
                    if col == 1:  # Total
                        self.tabla_compras.setItem(row, col, QTableWidgetItem(f"${valor:.2f}"))
                    elif col == 3:  # Puntos
                        self.tabla_compras.setItem(row, col, QTableWidgetItem(str(valor) if valor else "0"))
                    else:
                        self.tabla_compras.setItem(row, col, QTableWidgetItem(str(valor) if valor is not None else ""))
                        
        except sqlite3.Error as e:
            QMessageBox.critical(self, "Error", f"Error al cargar historial de compras: {str(e)}")

    def cargar_historial_puntos(self):
        """Carga el historial de puntos del cliente."""
        try:
            cursor = self.conexion.cursor()
            cursor.execute("""
                SELECT fecha, tipo, puntos, saldo_actual, descripcion 
                FROM historico_puntos 
                WHERE id_cliente = ? 
                ORDER BY fecha DESC
            """, (self.id_cliente,))
            puntos = cursor.fetchall()
            
            self.tabla_puntos.setRowCount(len(puntos))
            for row, punto in enumerate(puntos):
                for col, valor in enumerate(punto):
                    self.tabla_puntos.setItem(row, col, QTableWidgetItem(str(valor) if valor is not None else ""))
                        
        except sqlite3.Error as e:
            QMessageBox.critical(self, "Error", f"Error al cargar historial de puntos: {str(e)}")

    def cargar_historial_creditos(self):
        """Carga el historial de movimientos de crédito del cliente."""
        try:
            cursor = self.conexion.cursor()
            cursor.execute("""
                SELECT fecha, tipo, monto, descripcion, usuario 
                FROM movimientos_credito 
                WHERE cliente_id = ? 
                ORDER BY fecha DESC
            """, (self.id_cliente,))
            creditos = cursor.fetchall()
            
            self.tabla_creditos.setRowCount(len(creditos))
            for row, credito in enumerate(creditos):
                for col, valor in enumerate(credito):
                    if col == 2:  # Monto
                        self.tabla_creditos.setItem(row, col, QTableWidgetItem(f"${valor:.2f}"))
                    else:
                        self.tabla_creditos.setItem(row, col, QTableWidgetItem(str(valor) if valor is not None else ""))
                        
        except sqlite3.Error as e:
            QMessageBox.critical(self, "Error", f"Error al cargar historial de créditos: {str(e)}")

# ── v9: Diálogos Tarjetas desde Clientes ─────────────────────────────────────

class _DialogoAsignarTarjetaCliente(QDialog):
    """Selecciona una tarjeta libre para asignar al cliente."""

    def __init__(self, cliente_id, cliente_nombre, conexion, parent=None):
        super().__init__(parent)
        self.cliente_id   = cliente_id
        self.cliente_nombre = cliente_nombre
        self.conexion     = conexion
        self.tarjeta_id   = None
        self.setWindowTitle(f"Asignar Tarjeta — {cliente_nombre}")
        self.setMinimumWidth(440)
        self.setModal(True)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(Spacing.MD)
        layout.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)

        # Encabezado
        layout.addWidget(create_heading(self, f"Asignar Tarjeta"))
        layout.addWidget(create_subheading(self, f"Cliente: {self.cliente_nombre}"))

        # Card principal
        card = create_card(self, padding=Spacing.MD, with_layout=False)
        card_layout = QVBoxLayout()
        card_layout.setSpacing(Spacing.SM)

        # Tarjetas libres
        card_layout.addWidget(create_caption(self, "Tarjeta disponible:"))
        self.combo_tarjeta = create_combo(self, [])
        self._cargar_tarjetas_libres()
        card_layout.addWidget(self.combo_tarjeta)

        # O ingresar número manualmente
        card_layout.addWidget(create_subheading(self, "O buscar por número"))
        search_layout = QHBoxLayout()
        self.txt_numero = create_input_field(self, "Número de tarjeta…")
        btn_buscar = create_primary_button(self, "🔍 Buscar", "Buscar tarjeta por número")
        btn_buscar.clicked.connect(self._buscar_numero)
        search_layout.addWidget(self.txt_numero)
        search_layout.addWidget(btn_buscar)
        card_layout.addLayout(search_layout)

        self.lbl_estado_busqueda = create_caption(self, "")
        card_layout.addWidget(self.lbl_estado_busqueda)
        
        card.setLayout(card_layout)
        layout.addWidget(card)

        # Botones de acción
        btns = QHBoxLayout()
        btns.setSpacing(Spacing.SM)
        btn_ok = create_success_button(self, "✅ Asignar", "Asignar tarjeta al cliente")
        btn_ok.clicked.connect(self._confirmar)
        btn_cancel = create_secondary_button(self, "Cancelar", "Cancelar asignación")
        btn_cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_ok)
        layout.addLayout(btns)

    def _cargar_tarjetas_libres(self):
        try:
            rows = self.conexion.execute(
                "SELECT id, numero, COALESCE(nivel,'Bronce') FROM tarjetas_fidelidad "
                "WHERE estado IN ('libre','impresa','generada') ORDER BY id LIMIT 100"
            ).fetchall()
            self.combo_tarjeta.clear()
            for tid, num, nivel in rows:
                self.combo_tarjeta.addItem(f"{num} [{nivel}]", tid)
        except Exception:
            pass

    def _buscar_numero(self):
        numero = self.txt_numero.text().strip()
        if not numero:
            return
        row = self.conexion.execute(
            "SELECT id, numero, estado FROM tarjetas_fidelidad WHERE numero=? OR codigo_qr=?",
            (numero, numero)
        ).fetchone()
        if not row:
            self.lbl_estado_busqueda.setText("❌ No encontrada")
        elif row[2] == "asignada":
            self.lbl_estado_busqueda.setText(f"⚠ Tarjeta {row[1]} ya está asignada")
        elif row[2] == "bloqueada":
            self.lbl_estado_busqueda.setText("🔒 Tarjeta bloqueada")
        else:
            # Preseleccionar en combo si existe, si no agregar
            found = False
            for i in range(self.combo_tarjeta.count()):
                if self.combo_tarjeta.itemData(i) == row[0]:
                    self.combo_tarjeta.setCurrentIndex(i)
                    found = True
                    break
            if not found:
                self.combo_tarjeta.addItem(f"{row[1]} [búsqueda]", row[0])
                self.combo_tarjeta.setCurrentIndex(self.combo_tarjeta.count() - 1)
            self.lbl_estado_busqueda.setText(f"✓ {row[1]} — {row[2]}")

    def _confirmar(self):
        self.tarjeta_id = self.combo_tarjeta.currentData()
        if not self.tarjeta_id:
            # [spj-dedup] from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Error", "Seleccione una tarjeta")
            return
        self.accept()


class _DialogoTarjetasCliente(QDialog):
    """Vista de tarjetas asignadas a un cliente con opciones de gestión."""

    def __init__(self, cliente_id, cliente_nombre, conexion, parent=None):
        super().__init__(parent)
        self.cliente_id     = cliente_id
        self.cliente_nombre = cliente_nombre
        self.conexion       = conexion
        self.setWindowTitle(f"Tarjetas — {cliente_nombre}")
        self.setMinimumWidth(600)
        self.setMinimumHeight(480)
        self.setModal(True)
        self._build_ui()
        self._cargar_datos()

    def _build_ui(self):
        from PyQt5.QtWidgets import (
            QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
            QTabWidget, QWidget, QHBoxLayout, QPushButton, QHeaderView
        )
        from PyQt5.QtCore import Qt

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        layout.addWidget(QLabel(f"<b>Cliente:</b> {self.cliente_nombre} (ID: {self.cliente_id})"))

        tabs = create_standard_tabs(self)

        # Tab 1: Tarjetas actuales
        tab_tarjetas = QWidget()
        lay_t = QVBoxLayout(tab_tarjetas)
        cols_t = ["ID Tarjeta", "Número", "Estado", "Nivel", "Puntos", "Fecha Asignación"]
        self.tabla_tarjetas = create_table_with_columns(
            self, cols_t, show_grid=False, alternating_colors=True
        )
        lay_t.addWidget(wrap_in_scroll_area(self.tabla_tarjetas, self))

        btn_row = QHBoxLayout()
        self.btn_bloquear  = QPushButton("🔒 Bloquear")
        self.btn_bloquear.setObjectName("dangerBtn")
        self.btn_liberar   = QPushButton("🔓 Liberar")
        self.btn_liberar.setObjectName("successBtn")
        self.btn_bloquear.clicked.connect(self._bloquear_tarjeta)
        self.btn_liberar.clicked.connect(self._liberar_tarjeta)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_bloquear)
        btn_row.addWidget(self.btn_liberar)
        lay_t.addLayout(btn_row)
        tabs.addTab(tab_tarjetas, "Tarjetas Actuales")

        # Tab 2: Historial de asignaciones
        tab_hist = QWidget()
        lay_h = QVBoxLayout(tab_hist)
        cols_h = ["Acción", "Fecha", "Tarjeta", "Motivo", "Usuario"]
        self.tabla_historial = create_table_with_columns(
            self, cols_h, show_grid=False, alternating_colors=True
        )
        lay_h.addWidget(wrap_in_scroll_area(self.tabla_historial, self))
        tabs.addTab(tab_hist, "Historial de Asignaciones")

        # Tab 3: Score de fidelidad
        tab_score = QWidget()
        lay_s = QVBoxLayout(tab_score)
        self.lbl_score = QLabel("Cargando score de fidelidad…")
        self.lbl_score.setWordWrap(True)
        lay_s.addWidget(self.lbl_score)
        tabs.addTab(tab_score, "Score Fidelidad")

        layout.addWidget(tabs)

        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.setObjectName("secondaryBtn")
        btn_cerrar.clicked.connect(self.accept)
        row_cierre = QHBoxLayout()
        row_cierre.addStretch()
        row_cierre.addWidget(btn_cerrar)
        layout.addLayout(row_cierre)

    def _cargar_datos(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        # Tarjetas asignadas
        try:
            rows = self.conexion.execute(
                "SELECT id, numero, estado, COALESCE(nivel,'Bronce'), puntos_actuales, fecha_asignacion "
                "FROM tarjetas_fidelidad WHERE id_cliente = ? ORDER BY fecha_asignacion DESC",
                (self.cliente_id,)
            ).fetchall()
            self.tabla_tarjetas.setRowCount(len(rows))
            for i, r in enumerate(rows):
                for j, v in enumerate(r):
                    self.tabla_tarjetas.setItem(i, j, QTableWidgetItem(str(v or "")))
        except Exception:
            pass

        # Historial
        try:
            rows_h = self.conexion.execute(
                """
                SELECT h.accion, h.fecha, tf.numero, h.motivo, h.usuario
                FROM card_assignment_history h
                LEFT JOIN tarjetas_fidelidad tf ON tf.id = h.tarjeta_id
                WHERE h.cliente_id_nuevo = ? OR h.cliente_id_prev = ?
                ORDER BY h.fecha DESC LIMIT 100
                """,
                (self.cliente_id, self.cliente_id)
            ).fetchall()
            self.tabla_historial.setRowCount(len(rows_h))
            for i, r in enumerate(rows_h):
                for j, v in enumerate(r):
                    self.tabla_historial.setItem(i, j, QTableWidgetItem(str(v or "")))
        except Exception:
            pass

        # Score fidelidad
        try:
            score_row = self.conexion.execute(
                "SELECT score_total, nivel, visitas_periodo, importe_total, "
                "margen_generado, referidos, fecha_calculo "
                "FROM loyalty_scores WHERE cliente_id = ?",
                (self.cliente_id,)
            ).fetchone()
            if score_row:
                txt = (
                    f"<b>Score Total:</b> {score_row[0]:.1f}/100  |  "
                    f"<b>Nivel:</b> {score_row[1]}<br>"
                    f"<b>Visitas período:</b> {score_row[2]}<br>"
                    f"<b>Importe total:</b> ${score_row[3]:,.2f}<br>"
                    f"<b>Margen generado:</b> ${score_row[4]:,.2f}<br>"
                    f"<b>Referidos:</b> {score_row[5]}<br>"
                    f"<small>Calculado: {score_row[6]}</small>"
                )
                self.lbl_score.setText(txt)
            else:
                self.lbl_score.setText("Sin datos de score. Se calculará en la próxima venta.")
        except Exception:
            self.lbl_score.setText("Módulo de fidelidad no disponible.")

    def _tarjeta_seleccionada(self):
        fila = self.tabla_tarjetas.currentRow()
        if fila < 0:
            return None, None
        try:
            tid = int(self.tabla_tarjetas.item(fila, 0).text())
            num = self.tabla_tarjetas.item(fila, 1).text()
            return tid, num
        except Exception:
            return None, None

    def _bloquear_tarjeta(self):
        tid, num = self._tarjeta_seleccionada()
        if not tid:
            # [spj-dedup] from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Selección", "Seleccione una tarjeta")
            return
        # [spj-dedup] from PyQt5.QtWidgets import QInputDialog, QMessageBox
        motivo, ok = QInputDialog.getText(self, "Motivo", f"Motivo de bloqueo para {num}:")
        if not ok or not motivo.strip():
            return
        try:
            from core.services.card_batch_engine import CardBatchEngine
            eng = CardBatchEngine(self.conexion, "admin")
            res = eng.bloquear_tarjeta(tid, motivo.strip())
            if res.exito:
                self._cargar_datos()
                Toast.info(self, "Tarjeta bloqueada", f"Tarjeta {num} bloqueada.")
            else:
                QMessageBox.warning(self, "Error", res.mensaje)
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _liberar_tarjeta(self):
        tid, num = self._tarjeta_seleccionada()
        if not tid:
            # [spj-dedup] from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Selección", "Seleccione una tarjeta")
            return
        # [spj-dedup] from PyQt5.QtWidgets import QMessageBox
        res = QMessageBox.question(self, "Liberar",
            f"¿Liberar tarjeta {num}?\nSe desvinculará del cliente.")
        if res != QMessageBox.Yes:
            return
        try:
            from core.services.card_batch_engine import CardBatchEngine
            eng = CardBatchEngine(self.conexion, "admin")
            result = eng.liberar_tarjeta(tid, motivo="liberacion_manual")
            if result.exito:
                self._cargar_datos()
                Toast.info(self, "Tarjeta liberada", f"Tarjeta {num} liberada.")
            else:
                QMessageBox.warning(self, "Error", result.mensaje)
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))


# ══════════════════════════════════════════════════════════════════════════

    def _abrir_rfm(self):
        """Abre la segmentacion RFM de clientes."""
        try:
            dlg = _DialogoRFM(self.conexion, self)
            dlg.exec_()
        except Exception as e:
            # [spj-dedup] from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(self, "RFM", f"Error al abrir: {e}")


# DIÁLOGO RFM — Segmentación automática de clientes
# ══════════════════════════════════════════════════════════════════════════

class _DialogoRFM(QDialog):
    """
    Segmentación RFM (Recency, Frequency, Monetary) de clientes.

    Calcula un score 1-5 para cada dimensión:
      R = días desde la última compra   (5=muy reciente, 1=hace mucho)
      F = número de compras en período  (5=muy frecuente, 1=poco)
      M = gasto total en período        (5=alto gasto, 1=bajo)

    Segmentos resultantes:
      Champions       — R5 F5 M5 (mejores clientes)
      Leales          — F4-5 (compran mucho aunque no tan reciente)
      En riesgo       — R2-3 (compraban bien, dejaron de venir)
      Casi perdidos   — R1-2 F1-2 (no han vuelto)
      Nuevos          — R5 F1 (primer o segunda compra reciente)
    """

    SEGMENTOS = {
        "Champions":    {"r": (4,5), "f": (4,5), "m": (3,5), "color": "#27ae60", "icono": "👑"},
        "Leales":       {"r": (3,5), "f": (4,5), "m": (3,5), "color": "#2980b9", "icono": "⭐"},
        "Potenciales":  {"r": (4,5), "f": (2,3), "m": (2,4), "color": "#8e44ad", "icono": "🌱"},
        "Nuevos":       {"r": (4,5), "f": (1,1), "m": (1,3), "color": "#16a085", "icono": "🆕"},
        "En riesgo":    {"r": (2,3), "f": (3,5), "m": (3,5), "color": "#e67e22", "icono": "⚠️"},
        "Casi perdidos":{"r": (1,2), "f": (1,2), "m": (1,2), "color": "#e74c3c", "icono": "🚨"},
    }

    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.setWindowTitle("📊 Segmentación RFM de Clientes")
        self.setMinimumSize(900, 600)
        self._build_ui()
        self._calcular_rfm()

    def _build_ui(self):
        from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
            QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
            QComboBox, QSpinBox, QGroupBox, QScrollArea, QFrame)
        from PyQt5.QtCore import Qt

        lay = QVBoxLayout(self)

        # Header
        hdr = QHBoxLayout()
        t = create_heading(self, "📊 Segmentación RFM")
        self.cmb_periodo = create_combo(self, ["Últimos 90 días","Últimos 180 días","Últimos 365 días","Todo el tiempo"])
        self.cmb_periodo.currentIndexChanged.connect(self._calcular_rfm)
        btn_export = create_primary_button(self, "📥 Exportar Excel", "Exportar análisis RFM a Excel")
        btn_export.clicked.connect(self._exportar)
        hdr.addWidget(t); hdr.addStretch()
        hdr.addWidget(QLabel("Período:")); hdr.addWidget(self.cmb_periodo)
        hdr.addWidget(btn_export)
        lay.addLayout(hdr)

        # Resumen por segmento
        self.scroll_seg = QScrollArea(); self.scroll_seg.setMaximumHeight(120)
        self.scroll_seg.setWidgetResizable(True); self.scroll_seg.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        seg_w = QWidget(); seg_lay = QHBoxLayout(seg_w)
        self._seg_labels = {}
        for seg, cfg in self.SEGMENTOS.items():
            card = create_card(self, padding=Spacing.SM, with_layout=False)
            card.setFrameStyle(QFrame.Box)
            c_lay = QVBoxLayout(card)
            c_lay.setSpacing(Spacing.XS)
            c_lay.setContentsMargins(Spacing.SM, Spacing.SM, Spacing.SM, Spacing.SM)
            lbl_n = QLabel(f"{cfg['icono']} {seg}")
            lbl_n.setStyleSheet(f"font-weight:bold;color:{cfg['color']};")
            lbl_c = QLabel("0"); lbl_c.setObjectName("heading")
            lbl_c.setAlignment(Qt.AlignCenter)
            c_lay.addWidget(lbl_n); c_lay.addWidget(lbl_c)
            self._seg_labels[seg] = lbl_c
            seg_lay.addWidget(card)
        self.scroll_seg.setWidget(seg_w)
        lay.addWidget(self.scroll_seg)

        # Filter by segment
        flt = QHBoxLayout()
        self.cmb_seg_filter = create_combo(self, ["Todos los segmentos"] + list(self.SEGMENTOS.keys()))
        self.cmb_seg_filter.currentIndexChanged.connect(self._filtrar_tabla)
        flt.addWidget(QLabel("Filtrar:")); flt.addWidget(self.cmb_seg_filter); flt.addStretch()
        lay.addLayout(flt)

        # Main table
        self.tbl = QTableWidget(); self.tbl.setColumnCount(10)
        self.tbl.setHorizontalHeaderLabels([
            "Cliente","Teléfono","Última compra","Días (R)",
            "# Compras (F)","Total gastado (M)","Score R","Score F","Score M","Segmento"])
        hh = self.tbl.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1,10): hh.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.setObjectName("tableView")
        lay.addWidget(self.tbl)

        # Footer
        self.lbl_status = create_caption(self, "")
        lay.addWidget(self.lbl_status)

    def _dias_periodo(self) -> int:
        idx = self.cmb_periodo.currentIndex()
        return [90, 180, 365, 9999][idx]

    def _calcular_rfm(self):
        from PyQt5.QtWidgets import QTableWidgetItem
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QColor
        import math

        dias = self._dias_periodo()
        try:
            rows = self.conn.execute(f"""
                SELECT c.id, c.nombre, c.telefono,
                       MAX(v.fecha) as ultima_compra,
                       COUNT(v.id)  as num_compras,
                       SUM(v.total) as total_gastado
                FROM clientes c
                JOIN ventas v ON v.cliente_id = c.id
                WHERE v.estado = 'completada'
                  AND v.fecha >= date('now', '-{dias} days')
                GROUP BY c.id
                ORDER BY total_gastado DESC
                LIMIT 500
            """).fetchall()
        except Exception as e:
            self.lbl_status.setText(f"Error: {e}")
            return

        if not rows:
            self.lbl_status.setText("Sin datos de ventas en el período seleccionado.")
            self.tbl.setRowCount(0)
            return

        # Calculate percentiles for scoring
        from datetime import date as _date
        hoy = _date.today()

        def dias_desde(fecha_str):
            try:
                from datetime import datetime
                d = datetime.strptime(str(fecha_str)[:10], "%Y-%m-%d").date()
                return (hoy - d).days
            except Exception:
                return 999

        data = []
        for r in rows:
            dias_r  = dias_desde(r[3])
            freq    = int(r[4] or 0)
            monto   = float(r[5] or 0)
            data.append({
                "id": r[0], "nombre": r[1] or "", "telefono": r[2] or "",
                "ultima": str(r[3] or "")[:10], "dias_r": dias_r,
                "freq": freq, "monto": monto,
            })

        # Score 1-5 using quintiles
        def quintil_score(values, value, inverse=False):
            sorted_vals = sorted(values)
            n = len(sorted_vals)
            if n == 0: return 3
            percentile = sorted_vals.index(min(sorted_vals, key=lambda x: abs(x-value))) / n
            score = int(percentile * 4) + 1
            return (6 - score) if inverse else score

        all_dias = [d["dias_r"] for d in data]
        all_freq = [d["freq"]   for d in data]
        all_mon  = [d["monto"]  for d in data]

        seg_counts = {s: 0 for s in self.SEGMENTOS}
        enriched = []
        for d in data:
            # R: fewer days = better = higher score (inverse)
            r_score = max(1, min(5, 6 - int((d["dias_r"] / max(max(all_dias),1)) * 4) - 1))
            # F: more = better
            f_score = max(1, min(5, int((d["freq"] / max(max(all_freq),1)) * 4) + 1))
            # M: more = better
            m_score = max(1, min(5, int((d["monto"] / max(max(all_mon),1)) * 4) + 1))

            segmento = self._clasificar(r_score, f_score, m_score)
            seg_counts[segmento] = seg_counts.get(segmento, 0) + 1
            d.update({"r": r_score, "f": f_score, "m": m_score, "segmento": segmento})
            enriched.append(d)

        # Update segment cards
        for seg, lbl in self._seg_labels.items():
            lbl.setText(str(seg_counts.get(seg, 0)))

        # Fill table
        self._rfm_data = enriched
        self._fill_table(enriched)
        self.lbl_status.setText(
            f"{len(enriched)} clientes analizados · período: últimos {dias} días")

    def _clasificar(self, r, f, m) -> str:
        """Clasifica un cliente en su segmento RFM."""
        if r >= 4 and f >= 4 and m >= 3: return "Champions"
        if f >= 4 and m >= 3:             return "Leales"
        if r >= 4 and f == 1:             return "Nuevos"
        if r >= 4 and f <= 3 and m <= 4: return "Potenciales"
        if r <= 3 and f >= 3 and m >= 3: return "En riesgo"
        return "Casi perdidos"

    def _fill_table(self, data):
        from PyQt5.QtWidgets import QTableWidgetItem
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QColor

        self.tbl.setRowCount(len(data))
        for ri, d in enumerate(data):
            seg_cfg = self.SEGMENTOS.get(d["segmento"], {})
            color   = seg_cfg.get("color", "#888888")
            vals = [
                d["nombre"], d["telefono"], d["ultima"],
                str(d["dias_r"]),
                str(d["freq"]),
                f"${d['monto']:,.2f}",
                "★" * d["r"],
                "★" * d["f"],
                "★" * d["m"],
                f"{seg_cfg.get('icono','')} {d['segmento']}",
            ]
            for ci, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)
                if ci in (3,4): it.setTextAlignment(Qt.AlignRight|Qt.AlignVCenter)
                if ci == 9:
                    it.setForeground(QColor(color))
                    from PyQt5.QtGui import QFont as _QF
                    it.setFont(_QF("Arial", 9, _QF.Bold))
                self.tbl.setItem(ri, ci, it)

    def _filtrar_tabla(self):
        seg = self.cmb_seg_filter.currentText()
        if not hasattr(self, '_rfm_data'): return
        if seg == "Todos los segmentos":
            filtered = self._rfm_data
        else:
            filtered = [d for d in self._rfm_data if d["segmento"] == seg]
        self._fill_table(filtered)

    def _exportar(self):
        # [spj-dedup] from PyQt5.QtWidgets import QFileDialog, QMessageBox
        if not hasattr(self, '_rfm_data') or not self._rfm_data:
            QMessageBox.warning(self, "Sin datos", "No hay datos para exportar."); return
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Exportar RFM", "clientes_rfm.csv", "CSV (*.csv);;Excel (*.xlsx)")
        if not ruta: return
        try:
            if ruta.endswith('.xlsx'):
                import openpyxl
                wb = openpyxl.Workbook(); ws = wb.active
                ws.title = "RFM"
                ws.append(["Cliente","Teléfono","Última compra","Días R","Compras F",
                            "Total M","Score R","Score F","Score M","Segmento"])
                for d in self._rfm_data:
                    ws.append([d["nombre"],d["telefono"],d["ultima"],d["dias_r"],
                                d["freq"],d["monto"],d["r"],d["f"],d["m"],d["segmento"]])
                wb.save(ruta)
            else:
                with open(ruta,'w',encoding='utf-8') as f:
                    f.write("Cliente,Teléfono,Última compra,Días R,Compras F,Total M,Score R,Score F,Score M,Segmento\n")
                    for d in self._rfm_data:
                        f.write(f"{d['nombre']},{d['telefono']},{d['ultima']},"
                                f"{d['dias_r']},{d['freq']},{d['monto']:.2f},"
                                f"{d['r']},{d['f']},{d['m']},{d['segmento']}\n")
            Toast.success(self, "Exportado", f"Archivo: {ruta}")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
