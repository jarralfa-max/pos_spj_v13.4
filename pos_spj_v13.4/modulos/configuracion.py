
# modulos/configuracion.py
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QMessageBox, QFormLayout, QGroupBox,
    QTableWidget, QTableWidgetItem, QDialog, QDialogButtonBox, QHeaderView,
    QAbstractItemView, QSplitter, QListWidget, QListWidgetItem,
    QDateEdit, QTabWidget,
    QCheckBox, QTextEdit, QFileDialog, QStackedWidget, QScrollArea
)
from PyQt5.QtCore import Qt
from .base import ModuloBase

# Design System Imports
from modulos.ui_components import PageHeader, create_danger_button, apply_tooltip

from core.services.configuration_settings_service import SettingsModuleServices
from modulos.components.address_autocomplete_input import AddressAutocompleteInput
from frontend.desktop.components.integer_input import IntegerInput
from frontend.desktop.components.percent_input import PercentInput
from modulos.spj_phone_widget import PhoneWidget
from backend.shared.ids import new_uuid

class ModuloConfiguracion(ModuloBase):
    def __init__(self, conexion, parent=None):
        if hasattr(conexion, 'db'):
            self.container = conexion
            super().__init__(conexion.db, parent)
        else:
            self.container = None
            super().__init__(conexion, parent)

        event_bus = getattr(self.container, "event_bus", None) if self.container is not None else None
        self.settings_module_services = SettingsModuleServices.from_connection(self.conexion, event_bus)
        services = self.settings_module_services
        self.settings_application_service = services.settings_application_service
        self.system_settings_service = services.system_settings_service
        self.company_profile_service = services.company_profile_service
        self.email_settings_service = services.email_settings_service
        self.payment_provider_settings_service = services.payment_provider_settings_service
        self.closing_period_service = services.closing_period_service
        self.happy_hour_settings_service = services.happy_hour_settings_service
        self.user_management_service = services.user_management_service
        self.role_management_service = services.role_management_service
        self.permission_query_service = services.permission_query_service
        self.module_access_service = services.module_access_service
        self.permission_event_publisher = services.permission_event_publisher
        try:
            self.settings_application_service.assert_ready()
        except RuntimeError as exc:
            QMessageBox.critical(self, "Configuración incompleta", str(exc))
            raise
        self.init_ui()

    def set_usuario_actual(self, usuario: str, rol: str = "cajero") -> None:
        """Recibe el usuario activo al cambiar de sesión."""
        self.usuario_actual = usuario
        self.rol_actual = rol

    def set_sucursal(self, sucursal_id: int, sucursal_nombre: str):
        """Recibe la sucursal activa desde MainWindow."""
        self.sucursal_id     = sucursal_id
        self.sucursal_nombre = sucursal_nombre

    def _operation_id(self) -> str:
        return new_uuid()

    def _actor_name(self) -> str:
        return getattr(self, "usuario_actual", "Sistema")

    def _enable_combo_search(self, combo: QComboBox) -> None:
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        completer = combo.completer()
        if completer is not None:
            completer.setFilterMode(Qt.MatchContains)

    def _on_nav_changed(self, row: int) -> None:
        """Sync stack with nav selection."""
        if 0 <= row < self._page_stack.count():
            self._page_stack.setCurrentIndex(row)

    def _setup_table_defaults(self, table: QTableWidget, actions_column: int | None = None) -> None:
        """Apply standard settings for readable settings tables."""
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(44)
        if actions_column is not None:
            table.setColumnWidth(actions_column, 120)
            table.horizontalHeader().setSectionResizeMode(actions_column, QHeaderView.ResizeToContents)

    def _create_action_button(self, icon: str, tooltip: str, kind: str) -> QPushButton:
        """Create a colored compact action button for table rows."""
        button = QPushButton(icon)
        object_names = {
            "edit": "warningBtn",
            "warning": "warningBtn",
            "activate": "successBtn",
            "success": "successBtn",
            "deactivate": "dangerBtn",
            "delete": "dangerBtn",
            "danger": "dangerBtn",
            "primary": "primaryBtn",
            "secondary": "secondaryBtn",
        }
        button.setObjectName(object_names.get(kind, "secondaryBtn"))
        button.setMinimumSize(36, 32)
        button.setCursor(Qt.PointingHandCursor)
        apply_tooltip(button, tooltip)
        return button

    def _style_dialog_buttons(
        self,
        button_box: QDialogButtonBox,
        *,
        accept_text: str = "Guardar",
        cancel_text: str = "Cancelar",
        accept_object_name: str = "primaryBtn",
    ) -> QDialogButtonBox:
        """Apply Spanish labels and design-system object names to dialog buttons."""
        accept_roles = (QDialogButtonBox.Save, QDialogButtonBox.Ok)
        for standard_button in accept_roles:
            button = button_box.button(standard_button)
            if button is None:
                continue
            button.setText("Aceptar" if standard_button == QDialogButtonBox.Ok else accept_text)
            button.setObjectName(accept_object_name)
            button.setCursor(Qt.PointingHandCursor)
            apply_tooltip(button, button.text())

        cancel_button = button_box.button(QDialogButtonBox.Cancel)
        if cancel_button is not None:
            cancel_button.setText(cancel_text)
            cancel_button.setObjectName("secondaryBtn")
            cancel_button.setCursor(Qt.PointingHandCursor)
            apply_tooltip(cancel_button, cancel_text)
        return button_box

    def init_ui(self):
        """Inicializa la interfaz de usuario"""
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)

        header = PageHeader(
            self,
            title="⚙️ Configuración",
            subtitle="Empresa, usuarios, permisos, pagos, Happy Hour y cierre mensual.",
            compact=True,
        )
        layout.addWidget(header)

        # ── Navegación vertical (submenú lateral) ────────────────────────

        content_splitter = QSplitter(Qt.Horizontal)

        # Sidebar de categorías (SIEMPRE OSCURO - estilo del sistema)
        self._nav_list = QListWidget()
        self._nav_list.setFixedWidth(200)
        self._nav_list.setObjectName("sidebarNav")  # Usar clase CSS en lugar de inline
        self._nav_list.currentRowChanged.connect(self._on_nav_changed)

        # Stack de páginas
        self.tabs_config = QStackedWidget()
        self._page_stack = self.tabs_config

        content_splitter.addWidget(self._nav_list)
        content_splitter.addWidget(self._page_stack)
        content_splitter.setStretchFactor(1, 1)
        layout.addWidget(content_splitter)

        def _add_page(label: str, widget: QWidget):
            item = QListWidgetItem(label)
            self._nav_list.addItem(item)
            self._page_stack.addWidget(widget)

        class _TabShim:
            def __init__(self_s, stack, nav):
                self_s._stack = stack
                self_s._nav = nav
            def addTab(self_s, widget, label):
                _add_page(label, widget)
            def setCurrentIndex(self_s, idx):
                self_s._stack.setCurrentIndex(idx)
                self_s._nav.setCurrentRow(idx)
        self.tabs_config = _TabShim(self._page_stack, self._nav_list)

        self.tab_empresa = QWidget()
        self.tab_usuarios_roles = QWidget()
        self.tab_email = QWidget()
        self.tab_mercadopago = QWidget()
        self.tab_happy_hour = QWidget()
        self.tab_cierre_mensual = QWidget()

        self.tabs_config.addTab(self.tab_empresa, "🏢 Empresa / Fiscal")
        self.tabs_config.addTab(self.tab_usuarios_roles, "👤 Usuarios y Roles")
        self.tabs_config.addTab(self.tab_email, "📧 Email / SMTP")
        self.tabs_config.addTab(self.tab_mercadopago, "💳 Mercado Pago")
        self.tabs_config.addTab(self.tab_happy_hour, "⏰ Happy Hour")
        self.tabs_config.addTab(self.tab_cierre_mensual, "📅 Cierre Mensual")

        self.setLayout(layout)

        self._setup_tab_empresa()
        self._setup_tab_usuarios_roles()
        self._setup_tab_email()
        self._setup_tab_mercadopago()
        self._setup_tab_happy_hour()
        self._setup_tab_cierre_mensual()
        self._cargar_usuarios_v13()


    def _setup_tab_cierre_mensual(self) -> None:
        """UI para ejecutar el cierre contable mensual y bloquear períodos."""
        from PyQt5.QtWidgets import (QVBoxLayout, QHBoxLayout, QGroupBox,
                                      QLabel, QPushButton)
        from PyQt5.QtCore import QDate

        lay = QVBoxLayout(self.tab_cierre_mensual)
        lay.setContentsMargins(12, 12, 12, 12)

        info = QLabel(
            "El cierre mensual consolida las ventas, compras y mermas del período "
            "y bloquea esos registros para que no puedan modificarse retroactivamente.")
        info.setWordWrap(True)
        info.setObjectName("infoBox")
        lay.addWidget(info)

        # ── Ejecutar cierre ───────────────────────────────────────────────────
        grp_exec = QGroupBox("Ejecutar Cierre del Mes")
        grp_exec.setObjectName("styledGroup")
        exec_lay = QHBoxLayout(grp_exec)

        lbl_periodo = QLabel("Mes a cerrar:")
        self._dte_cierre = QDateEdit()
        self._dte_cierre.setDate(QDate.currentDate().addMonths(-1))
        self._dte_cierre.setDisplayFormat("yyyy-MM")
        self._dte_cierre.setCalendarPopup(True)
        self._dte_cierre.setObjectName("inputField")

        btn_cerrar = QPushButton("🔒 Ejecutar Cierre Mensual")
        btn_cerrar = create_danger_button(self, btn_cerrar.text(), "Ejecutar cierre mensual de forma irreversible")
        btn_cerrar.clicked.connect(self._ejecutar_cierre_mensual)

        self._lbl_cierre_status = QLabel("")
        exec_lay.addWidget(lbl_periodo)
        exec_lay.addWidget(self._dte_cierre)
        exec_lay.addWidget(btn_cerrar)
        exec_lay.addWidget(self._lbl_cierre_status)
        exec_lay.addStretch()
        lay.addWidget(grp_exec)

        # ── Historial de cierres ──────────────────────────────────────────────
        grp_hist = QGroupBox("Historial de Cierres")
        grp_hist.setObjectName("styledGroup")
        hist_lay = QVBoxLayout(grp_hist)

        self._tbl_cierres = QTableWidget()
        self._tbl_cierres.setColumnCount(6)
        self._tbl_cierres.setHorizontalHeaderLabels(
            ["Período","Cerrado por","Fecha cierre","Ventas","Compras","Merma"])
        hh = self._tbl_cierres.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        for c in (2,3,4,5): hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self._setup_table_defaults(self._tbl_cierres)
        hist_lay.addWidget(self._tbl_cierres)
        lay.addWidget(grp_hist)

        self._cargar_historial_cierres()

    def _ejecutar_cierre_mensual(self) -> None:
        """Calcula y guarda el cierre del período seleccionado."""
        from PyQt5.QtWidgets import QMessageBox
        periodo = self._dte_cierre.date().toString("yyyy-MM")
        usuario = getattr(self, 'usuario_actual', 'Sistema')

        try:
            already_closed = self.closing_period_service.period_exists(periodo)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudo validar el período: {exc}")
            return
        if already_closed:
            QMessageBox.warning(self, "Ya cerrado",
                f"El período {periodo} ya fue cerrado anteriormente.")
            return

        # Confirm
        resp = QMessageBox.question(
            self, "Confirmar Cierre",
            f"Ejecutar el cierre contable de {periodo}\n\n"
            "Esto consolidara ventas, compras y mermas del mes.\n"
            "Los registros quedaran bloqueados.",
            QMessageBox.Yes | QMessageBox.No)
        if resp != QMessageBox.Yes:
            return

        try:
            # Calculate totals for the period
            inicio = f"{periodo}-01"
            if periodo[5:] == "12":
                fin = f"{int(periodo[:4])+1}-01-01"
            else:
                fin = f"{periodo[:4]}-{int(periodo[5:])+1:02d}-01"

            totals = self.closing_period_service.calculate_totals(inicio, fin)
            total_ventas = totals["sales"]
            total_compras = totals["purchases"]
            total_merma = totals["waste"]

            self.closing_period_service.close_period(
                period=periodo,
                closed_by=usuario,
                totals=totals,
                branch_id=getattr(self, 'sucursal_id', 1),
            )

            self._lbl_cierre_status.setText(
                f"✅ {periodo} cerrado — Ventas ${total_ventas:,.2f}")
            self._lbl_cierre_status.setObjectName("textSuccess")
            self._cargar_historial_cierres()
            from PyQt5.QtWidgets import QMessageBox as _QMB
            _QMB.information(self, "Cierre ejecutado",
                f"Periodo {periodo} cerrado. "
                f"Ventas: ${total_ventas:,.2f} | "
                f"Compras: ${total_compras:,.2f} | "
                f"Merma: ${total_merma:,.2f}")
        except Exception as e:
            from PyQt5.QtWidgets import QMessageBox as _QMB
            _QMB.critical(self, "Error", str(e))
            self._lbl_cierre_status.setText(f"❌ {e}")
            self._lbl_cierre_status.setObjectName("textDanger")

    def _cargar_historial_cierres(self) -> None:
        """Loads the cierre_mensual history table."""
        if not hasattr(self, '_tbl_cierres'):
            return
        self._tbl_cierres.setRowCount(0)
        try:
            rows = self.closing_period_service.history(limit=24)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudo cargar el historial de cierres: {exc}")
            return
        for ri, r in enumerate(rows):
            self._tbl_cierres.insertRow(ri)
            vals = [
                str(r[0] or ""), str(r[1] or ""),
                str(r[2] or "")[:16],
                f"${float(r[3] or 0):,.2f}",
                f"${float(r[4] or 0):,.2f}",
                f"${float(r[5] or 0):,.2f}",
            ]
            from PyQt5.QtCore import Qt
            for ci, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self._tbl_cierres.setItem(ri, ci, it)


    def actualizar_datos(self):
        """Actualiza los datos visibles del módulo."""
        self._cargar_sucursales_v13()
        self._cargar_usuarios_v13()
        self._cargar_roles_v13()
        self._cargar_happy_hour_rules()

    def _setup_tab_empresa(self) -> None:
        from PyQt5.QtWidgets import QScrollArea as _SA
        _outer = QVBoxLayout(self.tab_empresa)
        _outer.setContentsMargins(0, 0, 0, 0)
        _scroll = _SA()
        _scroll.setWidgetResizable(True)
        _scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        _inner = QWidget()
        _scroll.setWidget(_inner)
        _outer.addWidget(_scroll)
        lay = QVBoxLayout(_inner)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(10)

        grp1 = QGroupBox("Datos del negocio")
        f1 = QFormLayout(grp1)
        self.emp_nombre = QLineEdit()
        self.emp_nombre.setPlaceholderText("Nombre del negocio")
        self.emp_eslogan = QLineEdit()
        self.emp_eslogan.setPlaceholderText("Eslogan o tagline")
        self.emp_telefono = PhoneWidget(parent=self)
        self.emp_email = QLineEdit()
        self.emp_web = QLineEdit()
        self.emp_direccion = AddressAutocompleteInput(self)
        f1.addRow("Nombre:*", self.emp_nombre)
        f1.addRow("Eslogan:", self.emp_eslogan)
        f1.addRow("Teléfono:", self.emp_telefono)
        f1.addRow("Email:", self.emp_email)
        f1.addRow("Web:", self.emp_web)
        f1.addRow("Dirección:", self.emp_direccion)
        lay.addWidget(grp1)

        grp2 = QGroupBox("Datos fiscales")
        f2 = QFormLayout(grp2)
        self.emp_rfc = QLineEdit()
        self.emp_rfc.setPlaceholderText("RFC del negocio")
        self.emp_regimen = QLineEdit()
        self.emp_regimen.setPlaceholderText("Ej: 601 - General de Ley")
        self.emp_tasa_iva = PercentInput(self)
        self.emp_tasa_iva.setToolTip("IVA configurado para la empresa")
        f2.addRow("RFC:", self.emp_rfc)
        f2.addRow("Régimen fiscal:", self.emp_regimen)
        f2.addRow("Tasa IVA (%):", self.emp_tasa_iva)
        lay.addWidget(grp2)

        grp3 = QGroupBox("Logo")
        f3 = QFormLayout(grp3)
        self.emp_logo_path = QLineEdit()
        self.emp_logo_path.setReadOnly(True)
        self.emp_logo_path.setPlaceholderText("(sin logo cargado)")
        btn_logo = QPushButton("📁 Seleccionar logo...")
        btn_logo.clicked.connect(self._seleccionar_logo)
        logo_row = QHBoxLayout()
        logo_row.addWidget(self.emp_logo_path, 1)
        logo_row.addWidget(btn_logo)
        f3.addRow("Archivo:", logo_row)
        lay.addWidget(grp3)

        grp4 = QGroupBox("📍 Sucursal de esta terminal")
        f4 = QFormLayout(grp4)
        self.cmb_sucursal_inst = QComboBox()
        self._enable_combo_search(self.cmb_sucursal_inst)
        self.cmb_sucursal_inst.setToolTip(
            "Define a qué sucursal pertenece esta computadora.\n"
            "Todos los usuarios que inicien sesión aquí operarán en esta sucursal.")
        f4.addRow("Sucursal:", self.cmb_sucursal_inst)
        lbl_info_suc = QLabel(
            "⚠️ Esta configuración determina la sucursal para TODA esta terminal.\n"
            "Inventario, ventas y caja se filtrarán por esta sucursal.")
        lbl_info_suc.setWordWrap(True)
        lbl_info_suc.setObjectName("textWarning")
        f4.addRow("", lbl_info_suc)
        lay.addWidget(grp4)

        btn_save = QPushButton("💾 Guardar datos de empresa")
        btn_save.setObjectName("successBtn")
        apply_tooltip(btn_save, "Guardar configuración de empresa")
        btn_save.clicked.connect(self._guardar_empresa)
        lay.addWidget(btn_save, 0, Qt.AlignRight)
        lay.addStretch()
        self._cargar_empresa()

    def _cargar_empresa(self):
        text_fields = {
            'nombre_empresa': self.emp_nombre,
            'eslogan_empresa': self.emp_eslogan,
            'email_empresa': self.emp_email,
            'web_empresa': self.emp_web,
            'rfc': self.emp_rfc,
            'regimen_fiscal': self.emp_regimen,
            'logo_path': self.emp_logo_path,
        }
        keys = list(text_fields.keys()) + [
            'direccion', 'telefono_empresa', 'tasa_iva', 'sucursal_instalacion_id',
        ]
        settings = self.system_settings_service.get_many(keys)
        for clave, widget in text_fields.items():
            if settings.get(clave):
                widget.setText(str(settings[clave]))
        if settings.get('direccion'):
            self.emp_direccion.set_manual_value(str(settings['direccion']))
        if settings.get('telefono_empresa'):
            self.emp_telefono.set_phone(str(settings['telefono_empresa']))
        if settings.get('tasa_iva'):
            try:
                self.emp_tasa_iva.setValue(float(settings['tasa_iva']) * 100)
            except ValueError as exc:
                QMessageBox.warning(self, "Dato fiscal inválido", f"La tasa IVA guardada no es válida: {exc}")
        self.cmb_sucursal_inst.clear()
        self.cmb_sucursal_inst.addItem("-- Selecciona sucursal --", None)
        sucs = self.company_profile_service.branches_for_company_settings()
        if not sucs:
            QMessageBox.warning(self, "Sucursales", "No hay sucursales activas configuradas.")
        for sid, nombre in sucs:
            self.cmb_sucursal_inst.addItem(nombre, sid)
        configured_branch = settings.get('sucursal_instalacion_id')
        if configured_branch:
            stored = str(configured_branch).strip()
            self.cmb_sucursal_inst.blockSignals(True)
            try:
                # findData matches itemData by string equality (itemData is str from active_branches_for_selector)
                idx = self.cmb_sucursal_inst.findData(stored)
                if idx < 0 and stored.isdigit():
                    # Legacy path: stored is integer string, itemData may also be integer string
                    for i in range(self.cmb_sucursal_inst.count()):
                        d = self.cmb_sucursal_inst.itemData(i)
                        if d is not None and str(d) == stored:
                            idx = i
                            break
                if idx >= 0:
                    self.cmb_sucursal_inst.setCurrentIndex(idx)
                else:
                    import logging
                    logging.getLogger(__name__).warning(
                        "_cargar_empresa: configured branch '%s' not found in selector", stored
                    )
            finally:
                self.cmb_sucursal_inst.blockSignals(False)

    def _guardar_empresa(self):
        nombre = self.emp_nombre.text().strip()
        if not nombre:
            QMessageBox.warning(self, "Aviso", "El nombre del negocio es obligatorio.")
            return
        suc_id = self.cmb_sucursal_inst.currentData() if hasattr(self, 'cmb_sucursal_inst') else None
        if suc_id is None:
            QMessageBox.warning(self, "Aviso", "Selecciona la sucursal de esta terminal.")
            return
        datos = {
            'nombre_empresa': nombre,
            'eslogan_empresa': self.emp_eslogan.text().strip(),
            'telefono_empresa': self.emp_telefono.get_e164(),
            'email_empresa': self.emp_email.text().strip(),
            'web_empresa': self.emp_web.text().strip(),
            'direccion': self.emp_direccion.value(),
            'rfc': self.emp_rfc.text().strip().upper(),
            'regimen_fiscal': self.emp_regimen.text().strip(),
            'logo_path': self.emp_logo_path.text().strip(),
            'tasa_iva': str(float(self.emp_tasa_iva.value()) / 100),
            'sucursal_instalacion_id': str(suc_id),
        }
        if hasattr(self, 'cmb_sucursal_inst'):
            suc_id = self.cmb_sucursal_inst.currentData()
            if suc_id:
                datos['sucursal_instalacion_id'] = str(suc_id)
        try:
            self.system_settings_service.save_many(datos)
            QMessageBox.information(self, "✅ Guardado",
                "Datos de empresa guardados.\n"
                "La sucursal de esta terminal se aplicará en el próximo inicio de sesión.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _seleccionar_logo(self):
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar logo", "", "Imágenes (*.png *.jpg *.jpeg *.svg)")
        if ruta:
            self.emp_logo_path.setText(ruta)

    # ══════════════════════════════════════════════════════════════════════
    # TAB: 📧 Email / SMTP
    # ══════════════════════════════════════════════════════════════════════
    def _setup_tab_email(self) -> None:
        from PyQt5.QtWidgets import (
            QVBoxLayout, QFormLayout, QGroupBox, QLineEdit, QPushButton, QHBoxLayout,
            QCheckBox
        )
        lay = QVBoxLayout(self.tab_email)
        lay.setContentsMargins(12,10,12,10); lay.setSpacing(10)

        grp = QGroupBox("Configuración SMTP para reportes por email")
        form = QFormLayout(grp)
        self.smtp_host    = QLineEdit(); self.smtp_host.setPlaceholderText("smtp.gmail.com")
        self.smtp_port    = IntegerInput(self, minimum=0, maximum=65535)
        self.smtp_user    = QLineEdit(); self.smtp_user.setPlaceholderText("usuario@gmail.com")
        self.smtp_pass    = QLineEdit(); self.smtp_pass.setEchoMode(QLineEdit.Password)
        self.smtp_pass.setPlaceholderText("Contraseña o App Password")
        self.smtp_tls     = QCheckBox("Usar TLS (recomendado)"); self.smtp_tls.setChecked(True)
        self.smtp_gerente = QLineEdit(); self.smtp_gerente.setPlaceholderText("gerente@empresa.com")
        form.addRow("Host SMTP:",         self.smtp_host)
        form.addRow("Puerto:",            self.smtp_port)
        form.addRow("Usuario:",           self.smtp_user)
        form.addRow("Contraseña:",        self.smtp_pass)
        form.addRow("",                   self.smtp_tls)
        form.addRow("Email del gerente:", self.smtp_gerente)
        lay.addWidget(grp)

        btn_row = QHBoxLayout()
        btn_test = QPushButton("📧 Enviar correo de prueba")
        btn_test.clicked.connect(self._test_smtp)
        btn_save = QPushButton("💾 Guardar")
        btn_save.setObjectName("successBtn")
        apply_tooltip(btn_save, "Guardar configuración SMTP")
        btn_save.clicked.connect(self._guardar_smtp)
        btn_row.addWidget(btn_test); btn_row.addStretch(); btn_row.addWidget(btn_save)
        lay.addLayout(btn_row)
        lay.addStretch()
        self._cargar_smtp()

    def _cargar_smtp(self):
        values = self.email_settings_service.get_settings()
        if values.get('smtp_host'):
            self.smtp_host.setText(str(values['smtp_host']))
        if values.get('smtp_port'):
            try:
                self.smtp_port.setValue(int(float(values['smtp_port'])))
            except (ValueError, TypeError):
                pass
        if values.get('smtp_user'):
            self.smtp_user.setText(str(values['smtp_user']))
        if values.get('smtp_password'):
            self.smtp_pass.setText(str(values['smtp_password']))
        if values.get('email_gerente'):
            self.smtp_gerente.setText(str(values['email_gerente']))
        self.smtp_tls.setChecked(str(values.get('smtp_tls', '0')) == '1')

    def _guardar_smtp(self):
        datos = {
            'smtp_host':     self.smtp_host.text().strip(),
            'smtp_port':     str(self.smtp_port.value()),
            'smtp_user':     self.smtp_user.text().strip(),
            'smtp_password': self.smtp_pass.text(),
            'smtp_tls':      '1' if self.smtp_tls.isChecked() else '0',
            'email_gerente': self.smtp_gerente.text().strip(),
        }
        try:
            self.email_settings_service.save_settings(datos)
            QMessageBox.information(self, "✅", "Configuración SMTP guardada.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _test_smtp(self):
        host  = self.smtp_host.text().strip()
        port  = self.smtp_port.value()
        user  = self.smtp_user.text().strip()
        pwd   = self.smtp_pass.text()
        dest  = self.smtp_gerente.text().strip() or user
        if not host or not user:
            QMessageBox.warning(self, "Aviso", "Completa host y usuario primero."); return
        try:
            import smtplib, ssl
            from email.mime.text import MIMEText
            msg = MIMEText("Correo de prueba desde SPJ POS v13. Todo funciona correctamente.")
            msg['Subject'] = "SPJ POS — Prueba de correo"
            msg['From']    = user
            msg['To']      = dest
            ctx = ssl.create_default_context()
            with smtplib.SMTP(host, port, timeout=10) as s:
                s.ehlo()
                if self.smtp_tls.isChecked():
                    s.starttls(context=ctx)
                s.login(user, pwd)
                s.sendmail(user, [dest], msg.as_string())
            QMessageBox.information(self, "✅ Enviado",
                f"Correo de prueba enviado a {dest}.")
        except Exception as e:
            QMessageBox.critical(self, "Error SMTP", str(e))

    # ══════════════════════════════════════════════════════════════════════
    # TAB: 💳 Mercado Pago
    # ══════════════════════════════════════════════════════════════════════
    def _setup_tab_mercadopago(self) -> None:
        from PyQt5.QtWidgets import (
            QVBoxLayout, QFormLayout, QGroupBox, QLabel,
            QLineEdit, QPushButton, QHBoxLayout
        )
        lay = QVBoxLayout(self.tab_mercadopago)
        lay.setContentsMargins(12,10,12,10); lay.setSpacing(10)

        info = QLabel(
            "Configura tus credenciales de Mercado Pago para recibir pagos con link.\n"
            "Obtén el Access Token en: https://www.mercadopago.com.mx/developers/panel"
        )
        info.setWordWrap(True)
        info.setObjectName("caption")
        lay.addWidget(info)

        grp = QGroupBox("Credenciales API")
        form = QFormLayout(grp)
        self.mp_token       = QLineEdit(); self.mp_token.setEchoMode(QLineEdit.Password)
        self.mp_token.setPlaceholderText("APP_USR-xxxx...")
        btn_show = QPushButton("👁")
        btn_show.setFixedWidth(32)
        btn_show.setCheckable(True)
        btn_show.toggled.connect(
            lambda on: self.mp_token.setEchoMode(
                QLineEdit.Normal if on else QLineEdit.Password))
        token_row = QHBoxLayout()
        token_row.addWidget(self.mp_token,1); token_row.addWidget(btn_show)
        self.mp_webhook_url = QLineEdit(); self.mp_webhook_url.setPlaceholderText("https://tudominio.com/mp/webhook")
        self.mp_return_url  = QLineEdit(); self.mp_return_url.setPlaceholderText("https://tudominio.com/mp/gracias")
        self.mp_sandbox     = QLineEdit(); self.mp_sandbox.setPlaceholderText("Vacío = producción; TEST = sandbox")
        form.addRow("Access Token:", token_row)
        form.addRow("URL Webhook:", self.mp_webhook_url)
        form.addRow("URL Retorno:", self.mp_return_url)
        form.addRow("Modo:", self.mp_sandbox)
        lay.addWidget(grp)

        btn_row = QHBoxLayout()
        btn_verify = QPushButton("🔍 Verificar token")
        btn_verify.clicked.connect(self._verificar_mp_token)
        btn_save = QPushButton("💾 Guardar")
        btn_save.setObjectName("accentBtn")
        apply_tooltip(btn_save, "Guardar credenciales de Mercado Pago")
        btn_save.clicked.connect(self._guardar_mp)
        btn_row.addWidget(btn_verify); btn_row.addStretch(); btn_row.addWidget(btn_save)
        lay.addLayout(btn_row)

        self.mp_status_lbl = QLabel("")
        self.mp_status_lbl.setObjectName("caption")
        lay.addWidget(self.mp_status_lbl)
        lay.addStretch()
        self._cargar_mp()

    def _cargar_mp(self):
        claves = {
            'mp_access_token': self.mp_token,
            'mp_webhook_url':  self.mp_webhook_url,
            'mp_return_url':   self.mp_return_url,
        }
        values = self.payment_provider_settings_service.get_mercado_pago_settings()
        for clave, widget in claves.items():
            if values.get(clave):
                widget.setText(str(values[clave]))

    def _guardar_mp(self):
        datos = {
            'mp_access_token': self.mp_token.text().strip(),
            'mp_webhook_url':  self.mp_webhook_url.text().strip(),
            'mp_return_url':   self.mp_return_url.text().strip(),
        }
        if not datos['mp_access_token']:
            QMessageBox.warning(self, "Aviso", "El Access Token es obligatorio."); return
        try:
            self.payment_provider_settings_service.save_mercado_pago_settings(datos)
            QMessageBox.information(self, "✅", "Credenciales de Mercado Pago guardadas.")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _verificar_mp_token(self):
        token = self.mp_token.text().strip()
        if not token:
            self.mp_status_lbl.setText("❌ Ingresa el Access Token primero.")
            self.mp_status_lbl.setObjectName("textDanger")
            return
        self.mp_status_lbl.setText("⏳ Verificando...")
        try:
            import urllib.request, json
            req = urllib.request.Request(
                "https://api.mercadopago.com/v1/payment_methods",
                headers={"Authorization": f"Bearer {token}"}
            )
            resp = urllib.request.urlopen(req, timeout=8)
            data = json.loads(resp.read())
            if isinstance(data, list) and len(data) > 0:
                self.mp_status_lbl.setText(f"✅ Token válido — {len(data)} métodos de pago disponibles.")
                self.mp_status_lbl.setObjectName("textSuccess")
            else:
                self.mp_status_lbl.setText("⚠️ Respuesta inesperada del servidor.")
                self.mp_status_lbl.setObjectName("textWarning")
        except Exception as e:
            self.mp_status_lbl.setText(f"❌ Error: {str(e)[:80]}")
            self.mp_status_lbl.setObjectName("textDanger")

    # ══════════════════════════════════════════════════════════════════════
    # TAB: ⏰ Happy Hour
    # ══════════════════════════════════════════════════════════════════════
    def _setup_tab_happy_hour(self) -> None:
        lay = QVBoxLayout(self.tab_happy_hour)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(10)

        header = QHBoxLayout()
        header.addWidget(QLabel("Reglas de descuento por horario"))
        header.addStretch()
        btn_new = QPushButton("➕ Nueva regla")
        btn_new.setObjectName("successBtn")
        btn_new.clicked.connect(lambda: self._editar_happy_hour_rule(None))
        header.addWidget(btn_new)
        lay.addLayout(header)

        self._tbl_happy_hour = QTableWidget()
        self._tbl_happy_hour.setColumnCount(7)
        self._tbl_happy_hour.setHorizontalHeaderLabels(
            ["Nombre", "Horario", "Días", "Descuento", "Aplica a", "Estado", "Acciones"])
        hh = self._tbl_happy_hour.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for index in (1, 2, 3, 4, 5, 6):
            hh.setSectionResizeMode(index, QHeaderView.ResizeToContents)
        self._setup_table_defaults(self._tbl_happy_hour, actions_column=6)
        lay.addWidget(self._tbl_happy_hour)
        self._cargar_happy_hour_rules()

    def _cargar_happy_hour_rules(self) -> None:
        if not hasattr(self, "_tbl_happy_hour"):
            return
        try:
            rules = self.happy_hour_settings_service.list_rules()
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudieron cargar reglas Happy Hour: {exc}")
            rules = []
        self._tbl_happy_hour.setRowCount(len(rules))
        for row_index, rule in enumerate(rules):
            days = str(rule.get("dias_semana") or "")
            day_count = len([day for day in days.split(",") if day])
            values = [
                rule.get("nombre") or "",
                f"{rule.get('hora_inicio') or ''}–{rule.get('hora_fin') or ''}",
                f"{day_count} días/sem",
                f"{float(rule.get('valor') or 0):.2f} %" if rule.get("tipo_descuento") == "porcentaje" else f"${float(rule.get('valor') or 0):.2f}",
                rule.get("aplica_a") or "",
                "✅ Activa" if rule.get("activo") else "❌ Inactiva",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self._tbl_happy_hour.setItem(row_index, column, item)
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(2, 2, 2, 2)
            rule_id = int(rule["id"])
            active = bool(rule.get("activo"))
            btn_edit = self._create_action_button("✏️", "Editar regla Happy Hour", "edit")
            btn_edit.clicked.connect(lambda _, rid=rule_id: self._editar_happy_hour_rule(rid))
            btn_toggle = self._create_action_button(
                "⏸" if active else "▶",
                "Desactivar regla" if active else "Activar regla",
                "deactivate" if active else "activate",
            )
            btn_toggle.clicked.connect(lambda _, rid=rule_id, new_state=not active: self._toggle_happy_hour_rule(rid, new_state))
            actions_layout.addWidget(btn_edit)
            actions_layout.addWidget(btn_toggle)
            self._tbl_happy_hour.setCellWidget(row_index, 6, actions_widget)

    def _editar_happy_hour_rule(self, rule_id: int | None) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Regla Happy Hour")
        dlg.setMinimumWidth(520)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()

        txt_name = QLineEdit()
        txt_name.setPlaceholderText("Nombre de la regla")
        txt_start = QLineEdit()
        txt_start.setPlaceholderText("HH:MM")
        txt_end = QLineEdit()
        txt_end.setPlaceholderText("HH:MM")
        spin_discount = PercentInput(dlg)
        combo_type = QComboBox()
        combo_type.addItem("Porcentaje", "porcentaje")
        combo_type.addItem("Monto fijo", "monto_fijo")
        combo_scope = QComboBox()
        combo_scope.addItem("Todos", "todos")
        combo_scope.addItem("Categoría", "categoria")
        combo_scope.addItem("Producto ID", "producto_id")
        txt_scope_value = QLineEdit()
        txt_scope_value.setPlaceholderText("Vacío si aplica a todos")
        combo_branch = QComboBox()
        self._enable_combo_search(combo_branch)
        for branch_id, branch_name in self.role_management_service.active_branches_for_selector():
            combo_branch.addItem(branch_name, branch_id)
        days_widget = QWidget()
        days_layout = QHBoxLayout(days_widget)
        days_layout.setContentsMargins(0, 0, 0, 0)
        days = {}
        for index, label in enumerate(["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]):
            check = QCheckBox(label)
            days[index] = check
            days_layout.addWidget(check)
        txt_message = QTextEdit()
        txt_message.setMaximumHeight(70)
        txt_message.setPlaceholderText("Mensaje interno opcional")
        chk_active = QCheckBox("Regla activa")

        form.addRow("Nombre*:", txt_name)
        form.addRow("Hora inicio*:", txt_start)
        form.addRow("Hora fin*:", txt_end)
        form.addRow("Tipo:", combo_type)
        form.addRow("Descuento:", spin_discount)
        form.addRow("Aplica a:", combo_scope)
        form.addRow("Valor aplica:", txt_scope_value)
        form.addRow("Sucursal:", combo_branch)
        form.addRow("Días:", days_widget)
        form.addRow("Mensaje:", txt_message)
        form.addRow("", chk_active)
        lay.addLayout(form)

        if rule_id is not None:
            try:
                rule = self.happy_hour_settings_service.get_rule(rule_id)
            except Exception as exc:
                QMessageBox.critical(self, "Error", f"No se pudo cargar la regla: {exc}")
                return
            if not rule:
                QMessageBox.warning(self, "Aviso", "La regla seleccionada no existe.")
                return
            txt_name.setText(rule.get("nombre") or "")
            txt_start.setText(rule.get("hora_inicio") or "")
            txt_end.setText(rule.get("hora_fin") or "")
            spin_discount.setValue(float(rule.get("valor") or 0))
            type_index = combo_type.findData(rule.get("tipo_descuento"))
            if type_index >= 0:
                combo_type.setCurrentIndex(type_index)
            scope_index = combo_scope.findData(rule.get("aplica_a"))
            if scope_index >= 0:
                combo_scope.setCurrentIndex(scope_index)
            txt_scope_value.setText(rule.get("aplica_valor") or "")
            for day in str(rule.get("dias_semana") or "").split(","):
                if day.isdigit() and int(day) in days:
                    days[int(day)].setChecked(True)
            txt_message.setPlainText(rule.get("message") or "")
            chk_active.setChecked(bool(rule.get("activo")))
            branch_index = combo_branch.findData(rule.get("sucursal_id"))
            if branch_index >= 0:
                combo_branch.setCurrentIndex(branch_index)

        btns = self._style_dialog_buttons(QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel))
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        if dlg.exec_() != QDialog.Accepted:
            return
        selected_days = ",".join(str(day) for day, check in days.items() if check.isChecked())
        if not txt_name.text().strip() or not txt_start.text().strip() or not txt_end.text().strip():
            QMessageBox.warning(dlg, "Aviso", "Nombre, hora inicio y hora fin son obligatorios.")
            return
        if not selected_days:
            QMessageBox.warning(dlg, "Aviso", "Selecciona al menos un día.")
            return
        try:
            self.happy_hour_settings_service.save_rule({
                "id": rule_id,
                "nombre": txt_name.text().strip(),
                "hora_inicio": txt_start.text().strip(),
                "hora_fin": txt_end.text().strip(),
                "dias_semana": selected_days,
                "tipo_descuento": combo_type.currentData(),
                "valor": float(spin_discount.value()),
                "aplica_a": combo_scope.currentData(),
                "aplica_valor": txt_scope_value.text().strip(),
                "message": txt_message.toPlainText().strip(),
                "activo": chk_active.isChecked(),
                "sucursal_id": combo_branch.currentData(),
            })
            self._cargar_happy_hour_rules()
        except Exception as exc:
            QMessageBox.critical(dlg, "Error", str(exc))

    def _toggle_happy_hour_rule(self, rule_id: int, active: bool) -> None:
        try:
            self.happy_hour_settings_service.set_rule_active(rule_id, active)
            self._cargar_happy_hour_rules()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    # ══════════════════════════════════════════════════════════════════════
    # TAB: 👤 Usuarios y Roles
    # ══════════════════════════════════════════════════════════════════════
    def _setup_tab_usuarios_roles(self) -> None:
        from PyQt5.QtWidgets import (
            QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
            QWidget
        )
        lay = QVBoxLayout(self.tab_usuarios_roles)
        lay.setContentsMargins(0,0,0,0)

        sub_tabs = QTabWidget()
        lay.addWidget(sub_tabs)

        # ── Sub-tab: Sucursales ──────────────────────────────────────────
        tab_suc = QWidget(); suc_lay = QVBoxLayout(tab_suc)
        suc_hdr = QHBoxLayout()
        suc_hdr.addWidget(QLabel("Sucursales del sistema con horarios de atención"))
        suc_hdr.addStretch()
        btn_new_suc = QPushButton("➕ Nueva sucursal")
        btn_new_suc.setObjectName("successBtn")
        apply_tooltip(btn_new_suc, "Crear nueva sucursal")
        btn_new_suc.clicked.connect(self._nueva_sucursal_v13)
        suc_hdr.addWidget(btn_new_suc)
        suc_lay.addLayout(suc_hdr)

        self._tbl_suc_v13 = QTableWidget()
        self._tbl_suc_v13.setColumnCount(6)
        self._tbl_suc_v13.setHorizontalHeaderLabels(
            ["Nombre","Dirección","Horario","Días","Estado","Acciones"])
        hh = self._tbl_suc_v13.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        for i in (0,2,3,4): hh.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self._setup_table_defaults(self._tbl_suc_v13, actions_column=5)
        suc_lay.addWidget(self._tbl_suc_v13)
        sub_tabs.addTab(tab_suc, "🏪 Sucursales")

        # ── Sub-tab: Usuarios ────────────────────────────────────────────
        tab_usr = QWidget(); usr_lay = QVBoxLayout(tab_usr)
        usr_hdr = QHBoxLayout()
        usr_hdr.addWidget(QLabel("Usuarios del sistema vinculados a empleados RRHH"))
        usr_hdr.addStretch()
        btn_new_usr = QPushButton("➕ Nuevo usuario")
        btn_new_usr.setObjectName("primaryBtn")
        apply_tooltip(btn_new_usr, "Crear nuevo usuario")
        btn_new_usr.clicked.connect(self._nuevo_usuario_v13)
        usr_hdr.addWidget(btn_new_usr)
        usr_lay.addLayout(usr_hdr)

        self._tbl_usr_v13 = QTableWidget()
        self._tbl_usr_v13.setColumnCount(6)
        self._tbl_usr_v13.setHorizontalHeaderLabels(
            ["Usuario","Nombre","Rol","Sucursal","Estado","Acciones"])
        hh2 = self._tbl_usr_v13.horizontalHeader()
        hh2.setSectionResizeMode(1, QHeaderView.Stretch)
        for i in (0,2,3,4): hh2.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self._setup_table_defaults(self._tbl_usr_v13, actions_column=5)
        usr_lay.addWidget(self._tbl_usr_v13)
        sub_tabs.addTab(tab_usr, "👤 Usuarios")

        # ── Sub-tab: Roles ───────────────────────────────────────────────
        tab_roles = QWidget(); roles_lay = QVBoxLayout(tab_roles)
        roles_lay.addWidget(QLabel("Roles con sus permisos por módulo. Los roles del sistema no se pueden eliminar."))
        self._tbl_roles_v13 = QTableWidget()
        self._tbl_roles_v13.setColumnCount(4)
        self._tbl_roles_v13.setHorizontalHeaderLabels(
            ["Nombre","Descripción","# Usuarios","Acciones"])
        hh3 = self._tbl_roles_v13.horizontalHeader()
        hh3.setSectionResizeMode(1, QHeaderView.Stretch)
        self._setup_table_defaults(self._tbl_roles_v13, actions_column=3)
        roles_lay.addWidget(self._tbl_roles_v13)
        sub_tabs.addTab(tab_roles, "🔑 Roles")

        # ── Sub-tab: Auditoría ───────────────────────────────────────────
        tab_audit = QWidget(); audit_lay = QVBoxLayout(tab_audit)
        audit_lay.addWidget(QLabel("Últimas 200 acciones registradas en el sistema"))
        self._tbl_audit_v13 = QTableWidget()
        self._tbl_audit_v13.setColumnCount(5)
        self._tbl_audit_v13.setHorizontalHeaderLabels(
            ["Fecha","Usuario","Módulo","Acción","Detalle"])
        hh4 = self._tbl_audit_v13.horizontalHeader()
        hh4.setSectionResizeMode(4, QHeaderView.Stretch)
        self._setup_table_defaults(self._tbl_audit_v13)
        audit_lay.addWidget(self._tbl_audit_v13)
        sub_tabs.addTab(tab_audit, "📋 Auditoría")

        sub_tabs.currentChanged.connect(self._on_usuarios_roles_tab_change)
        self._cargar_sucursales_v13()

    def _on_usuarios_roles_tab_change(self, idx):
        if idx == 0: self._cargar_sucursales_v13()
        elif idx == 1: self._cargar_usuarios_v13()
        elif idx == 2: self._cargar_roles_v13()
        elif idx == 3: self._cargar_auditoria_v13()

    def _cargar_sucursales_v13(self):
        from PyQt5.QtWidgets import QWidget, QHBoxLayout
        try:
            rows = self.company_profile_service.list_branch_delivery_rows()
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudieron cargar sucursales: {exc}")
            rows = []
        self._tbl_suc_v13.setRowCount(len(rows))
        for ri, r in enumerate(rows):
            dias_n = str(r[5]).count(',') + 1 if r[5] else 0
            vals = [r[1], r[2], f"{r[3]}–{r[4]}", f"{dias_n} días/sem",
                    "✅ Activa" if r[6] else "❌ Inactiva"]
            for ci, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                if ci == 0:
                    it.setData(Qt.UserRole, r[0])
                self._tbl_suc_v13.setItem(ri, ci, it)
            suc_id = r[0]
            btn_w = QWidget()
            bl = QHBoxLayout(btn_w)
            bl.setContentsMargins(2, 2, 2, 2)
            btn_ed = self._create_action_button("✏️", "Editar sucursal", "edit")
            btn_ed.clicked.connect(lambda _, sid=suc_id: self._editar_sucursal_v13(sid))
            bl.addWidget(btn_ed)
            self._tbl_suc_v13.setCellWidget(ri, 5, btn_w)

    def _nueva_sucursal_v13(self):
        self._editar_sucursal_v13(None)

    def _editar_sucursal_v13(self, sucursal_id):
        from PyQt5.QtWidgets import QDialog, QFormLayout, QCheckBox, QVBoxLayout, QHBoxLayout
        dlg = QDialog(self)
        dlg.setWindowTitle("Sucursal")
        dlg.setMinimumWidth(460)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        txt_nombre = QLineEdit()
        txt_dir = AddressAutocompleteInput()
        txt_tel = PhoneWidget()
        txt_abre = QLineEdit()
        txt_abre.setPlaceholderText("HH:MM")
        txt_cierra = QLineEdit()
        txt_cierra.setPlaceholderText("HH:MM")
        dias_chks = {}
        dias_nombres = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
        dias_w = QWidget()
        dias_lay = QHBoxLayout(dias_w)
        dias_lay.setContentsMargins(0, 0, 0, 0)
        for i, dn in enumerate(dias_nombres, 1):
            chk = QCheckBox(dn)
            dias_chks[i] = chk
            dias_lay.addWidget(chk)
        chk_acepta = QCheckBox("Aceptar pedidos fuera de horario (se programan)")
        txt_msg = QTextEdit()
        txt_msg.setMaximumHeight(60)
        txt_msg.setPlaceholderText("Mensaje al cliente fuera de horario")
        form.addRow("Nombre*:", txt_nombre)
        form.addRow("Dirección:", txt_dir)
        form.addRow("Teléfono:", txt_tel)
        form.addRow("Abre:", txt_abre)
        form.addRow("Cierra:", txt_cierra)
        form.addRow("Días:", dias_w)
        form.addRow("", chk_acepta)
        form.addRow("Msg. cierre:", txt_msg)
        lay.addLayout(form)

        if sucursal_id:
            try:
                row = self.company_profile_service.get_branch_delivery_profile(sucursal_id)
                if row:
                    txt_nombre.setText(row.get("nombre") or "")
                    txt_dir.set_manual_value(row.get("direccion") or "")
                    txt_tel.set_phone(row.get("telefono") or "")
                    txt_abre.setText(row.get("hora_apertura") or "")
                    txt_cierra.setText(row.get("hora_cierre") or "")
                    dias_sel = (row.get("dias_operacion") or "").split(",")
                    for n, chk in dias_chks.items():
                        chk.setChecked(str(n) in dias_sel)
                    chk_acepta.setChecked(bool(row.get("acepta_pedidos_fuera_horario")))
                    if row.get("mensaje_fuera_horario"):
                        txt_msg.setPlainText(row.get("mensaje_fuera_horario"))
            except Exception as exc:
                QMessageBox.warning(self, "Configuración incompleta", f"No se pudo cargar la sucursal: {exc}")

        btns = self._style_dialog_buttons(QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel))
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        if dlg.exec_() != QDialog.Accepted:
            return
        nombre = txt_nombre.text().strip()
        if not nombre:
            QMessageBox.warning(self, "Aviso", "El nombre es obligatorio.")
            return
        dias = ",".join(str(n) for n, chk in dias_chks.items() if chk.isChecked())
        try:
            self.company_profile_service.save_branch_delivery_profile(
                name=nombre,
                address=txt_dir.value(),
                phone=txt_tel.get_e164(),
                opening_time=txt_abre.text().strip(),
                closing_time=txt_cierra.text().strip(),
                operation_days=dias,
                accepts_after_hours_orders=chk_acepta.isChecked(),
                after_hours_message=txt_msg.toPlainText().strip(),
                branch_id=sucursal_id,
            )
            self._cargar_sucursales_v13()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _cargar_usuarios_v13(self):
        from PyQt5.QtWidgets import QWidget, QHBoxLayout
        from PyQt5.QtCore import Qt
        try:
            rows = self.user_management_service.list_users()
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudieron cargar usuarios: {exc}")
            rows = []
        self._tbl_usr_v13.setRowCount(len(rows))
        for ri, r in enumerate(rows):
            vals = [r[1], r[2] or "", r[3], r[4],
                    "✅ Activo" if r[5] else "❌ Inactivo"]
            for ci, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                it.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)
                if ci == 0: it.setData(Qt.UserRole, r[0])
                self._tbl_usr_v13.setItem(ri, ci, it)
            uid = r[0]
            btn_w = QWidget(); bl = QHBoxLayout(btn_w); bl.setContentsMargins(2,2,2,2)
            btn_ed = self._create_action_button("✏️", "Editar usuario", "edit")
            btn_ed.clicked.connect(lambda _, uid=uid: self._editar_usuario_v13(uid))
            btn_tog = self._create_action_button(
                "✅" if r[5] else "❌",
                "Desactivar usuario" if r[5] else "Activar usuario",
                "deactivate" if r[5] else "activate",
            )
            btn_tog.clicked.connect(
                lambda _, uid=uid, a=r[5]: self._toggle_usuario(uid, not a))
            bl.addWidget(btn_ed); bl.addWidget(btn_tog)
            self._tbl_usr_v13.setCellWidget(ri, 5, btn_w)

    def _nuevo_usuario_v13(self):
        self._editar_usuario_v13(None)

    def _editar_usuario_v13(self, usuario_id):
        from PyQt5.QtWidgets import (QDialog, QFormLayout,
                                      QLineEdit, QVBoxLayout,
                                      QMessageBox, QCheckBox, QLabel)
        dlg = QDialog(self); dlg.setWindowTitle("Usuario"); dlg.setMinimumWidth(440)
        lay = QVBoxLayout(dlg)
        form = QFormLayout()
        txt_usuario  = QLineEdit()
        txt_nombre   = QLineEdit()
        txt_email    = QLineEdit()
        txt_pass     = QLineEdit(); txt_pass.setEchoMode(QLineEdit.Password)
        txt_pass.setPlaceholderText("(dejar vacío para no cambiar)" if usuario_id else "Contraseña")
        cmb_rol      = QComboBox()
        cmb_sucursal = QComboBox()
        self._enable_combo_search(cmb_rol)
        self._enable_combo_search(cmb_sucursal)
        chk_activo   = QCheckBox("Activo"); chk_activo.setChecked(True)
        cmb_empleado = QComboBox(); cmb_empleado.addItem("(ninguno)", None)
        self._enable_combo_search(cmb_empleado)
        lbl_emp_hint = QLabel("Vincula este usuario a un empleado de RRHH")
        lbl_emp_hint.setObjectName("caption")

        try:
            for rn in self.role_management_service.role_names():
                cmb_rol.addItem(rn)
            for sid, nombre in self.role_management_service.active_branches_for_selector():
                cmb_sucursal.addItem(nombre, sid)
            for emp_id, label in self.role_management_service.active_employees_for_selector():
                cmb_empleado.addItem(label, emp_id)
        except Exception as exc:
            QMessageBox.critical(self, "Configuración incompleta", f"No se pudieron cargar selectores de usuario: {exc}")
            return

        form.addRow("Usuario*:", txt_usuario)
        form.addRow("Nombre:", txt_nombre)
        form.addRow("Email:", txt_email)
        form.addRow("Contraseña:", txt_pass)
        form.addRow("Rol:", cmb_rol)
        form.addRow("Sucursal:", cmb_sucursal)
        form.addRow("Empleado RRHH:", cmb_empleado)
        form.addRow("", lbl_emp_hint)
        form.addRow("", chk_activo)
        lay.addLayout(form)

        if usuario_id:
            try:
                row = self.user_management_service.get_user_form_data(usuario_id)
                if row:
                    txt_usuario.setText(row[0] or ""); txt_nombre.setText(row[1] or "")
                    txt_email.setText(row[2] or "")
                    idx = cmb_rol.findText(row[3] or "cajero")
                    if idx >= 0: cmb_rol.setCurrentIndex(idx)
                    for i in range(cmb_sucursal.count()):
                        if cmb_sucursal.itemData(i) == row[4]:
                            cmb_sucursal.setCurrentIndex(i); break
                    chk_activo.setChecked(bool(row[5]))
                    if row[6]:
                        for i in range(cmb_empleado.count()):
                            if cmb_empleado.itemData(i) == row[6]:
                                cmb_empleado.setCurrentIndex(i); break
            except Exception as exc:
                QMessageBox.critical(self, "Error", f"No se pudo cargar el usuario: {exc}")
                return

        btns = self._style_dialog_buttons(QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel))
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        if dlg.exec_() != QDialog.Accepted: return
        uname = txt_usuario.text().strip()
        if not uname:
            QMessageBox.warning(self, "Aviso", "El nombre de usuario es obligatorio."); return
        try:
            import bcrypt as _bcrypt
        except ImportError:
            _bcrypt = None
        try:
            pwd_raw = txt_pass.text()
            suc_id  = cmb_sucursal.currentData() or 1
            emp_id  = cmb_empleado.currentData()
            pwd_hash = None
            if pwd_raw:
                pwd_hash = (_bcrypt.hashpw(pwd_raw.encode(), _bcrypt.gensalt()).decode()
                            if _bcrypt else pwd_raw)
            elif not usuario_id:
                QMessageBox.warning(self, "Aviso", "La contraseña es obligatoria."); return
            self.user_management_service.save_user(
                user_id=usuario_id,
                username=uname,
                name=txt_nombre.text().strip(),
                email=txt_email.text().strip(),
                role=cmb_rol.currentText(),
                branch_id=suc_id,
                active=chk_activo.isChecked(),
                employee_id=emp_id,
                password_hash=pwd_hash,
                operation_id=self._operation_id(),
                actor=self._actor_name(),
            )
            self._cargar_usuarios_v13()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _toggle_usuario(self, uid, activo):
        try:
            self.user_management_service.set_user_active(uid, bool(activo), operation_id=self._operation_id(), actor=self._actor_name())
            self._cargar_usuarios_v13()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _cargar_roles_v13(self):
        from PyQt5.QtWidgets import QWidget, QHBoxLayout
        from PyQt5.QtCore import Qt
        try:
            rows = self.role_management_service.list_roles()
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudieron cargar roles: {exc}")
            rows = []
        self._tbl_roles_v13.setRowCount(len(rows))
        for ri, r in enumerate(rows):
            vals = [r[1], r[2] or "", str(r[3])]
            for ci, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)
                self._tbl_roles_v13.setItem(ri, ci, it)
            btn_w = QWidget(); bl = QHBoxLayout(btn_w); bl.setContentsMargins(2,2,2,2)
            btn_perm = self._create_action_button("🔑 Permisos", f"Editar permisos del rol {r[1]}", "primary")
            btn_perm.clicked.connect(
                lambda _, rid=r[0], rnom=r[1]: self._editar_permisos_rol(rid, rnom))
            bl.addWidget(btn_perm)
            self._tbl_roles_v13.setCellWidget(ri, 3, btn_w)

    def _editar_permisos_rol(self, rol_id, rol_nombre):
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QCheckBox
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Permisos — {rol_nombre}")
        dlg.setMinimumSize(700, 520)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(f"Configura permisos para el rol: <b>{rol_nombre}</b>"))

        try:
            permission_matrix = self.permission_query_service.permission_matrix()
            existing = self.permission_query_service.role_permissions(rol_id)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudieron cargar permisos: {exc}")
            return
        if not permission_matrix:
            QMessageBox.warning(self, "Permisos no configurados", "No hay permisos registrados para configurar.")
            return

        actions = []
        for _module, module_actions in permission_matrix:
            for action in module_actions:
                if action not in actions:
                    actions.append(action)

        tbl = QTableWidget(len(permission_matrix), len(actions) + 1)
        tbl.setHorizontalHeaderLabels(["Módulo"] + actions)
        tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        chks = {}
        for row_index, (module, module_actions) in enumerate(permission_matrix):
            module_item = QTableWidgetItem(module)
            module_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            tbl.setItem(row_index, 0, module_item)
            for column_index, action in enumerate(actions, 1):
                if action not in module_actions:
                    empty = QTableWidgetItem("")
                    empty.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    tbl.setItem(row_index, column_index, empty)
                    continue
                chk = QCheckBox()
                chk.setChecked(existing.get((module, action), False))
                chks[(module, action)] = chk
                tbl.setCellWidget(row_index, column_index, chk)

        scroll = QScrollArea()
        scroll.setWidget(tbl)
        scroll.setWidgetResizable(True)
        lay.addWidget(scroll)

        btns = self._style_dialog_buttons(QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel))
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        if dlg.exec_() != QDialog.Accepted:
            return
        try:
            self.module_access_service.save_role_permissions(
                rol_id,
                {(module, action): chk.isChecked() for (module, action), chk in chks.items()},
                operation_id=self._operation_id(),
                actor=self._actor_name(),
            )
            self._refresh_main_menu_access()
            QMessageBox.information(dlg, "✅", f"Permisos de '{rol_nombre}' guardados.")
        except Exception as e:
            QMessageBox.critical(dlg, "Error", str(e))

    def _refresh_main_menu_access(self) -> None:
        main_window = self.window()
        if hasattr(main_window, "refresh_module_access"):
            main_window.refresh_module_access()
        else:
            QMessageBox.information(
                self,
                "Permisos actualizados",
                "Los permisos se aplicarán al cambiar de sesión.",
            )

    def _cargar_auditoria_v13(self):
        from PyQt5.QtCore import Qt
        try:
            rows = self.permission_query_service.audit_log_rows(limit=200)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"No se pudo cargar auditoría: {exc}")
            rows = []
        self._tbl_audit_v13.setRowCount(len(rows))
        for ri, r in enumerate(rows):
            for ci, v in enumerate(r):
                it = QTableWidgetItem(str(v)[:60])
                it.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)
                self._tbl_audit_v13.setItem(ri, ci, it)


    def closeEvent(self, event):
        """Maneja el cierre del módulo"""
        self.registrar_actualizacion("modulo_cerrado", {"modulo": "configuraciones"})
        super().closeEvent(event)



# =============================================================================
# DIÁLOGO PARA CREAR / EDITAR SUCURSAL
# =============================================================================
