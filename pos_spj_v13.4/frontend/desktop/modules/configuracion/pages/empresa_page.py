"""Empresa page — 5th section with REAL CRUD wired for Configuración
(SET-5 follow-up): edit the company profile (get-or-create singleton —
`SaveCompanyProfileUseCase`) and register/edit branch governance profiles
(`RegisterBranchProfileUseCase`/`UpdateBranchProfileUseCase`, SET-5).

The main table (from `base_page.py`) lists `BranchProfile` rows; the
company profile is a single summary panel above it, since there's only
ever one (a UI-level convention — the domain itself doesn't enforce a
singleton, see `SaveCompanyProfileUseCase`'s own docstring).
"""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QLabel, QMessageBox, QWidget

from frontend.desktop.components import (
    SectionCard, create_primary_button, create_secondary_button,
)
from frontend.desktop.modules.configuracion.dialogs import (
    BranchProfileCreateDialog,
    BranchProfileEditDialog,
    CompanyProfileDialog,
    SetInstallationBranchDialog,
)
from frontend.desktop.themes.tokens import Spacing

from .base_page import ConfiguracionWorkspacePage


class EmpresaPage(ConfiguracionWorkspacePage):
    page_id = "config_empresa"
    title = "Empresa y sucursales"
    subtitle = "Perfil de la empresa y gobierno de sucursales."

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(presenter, parent)

        self.company_card = SectionCard(self, title="Empresa")
        self.company_summary_label = QLabel("", self.company_card)
        self.company_summary_label.setWordWrap(True)
        self.company_card.add(self.company_summary_label)
        self.edit_company_button = create_primary_button(self.company_card, "Editar empresa")
        self.company_card.add(self.edit_company_button)
        self.installation_summary_label = QLabel("", self.company_card)
        self.installation_summary_label.setWordWrap(True)
        self.company_card.add(self.installation_summary_label)
        self.anchor_installation_button = create_secondary_button(
            self.company_card, "Anclar sucursal de esta instalación")
        self.company_card.add(self.anchor_installation_button)
        self.layout().insertWidget(1, self.company_card)

        # Logo para tickets (comparativa de tickets, 2026-10-16): empresa y,
        # opcionalmente, cada sucursal (si no tiene el suyo, hereda).
        self.logo_card = SectionCard(self, title="Logo para tickets")
        logo_row = QWidget(self.logo_card)
        logo_layout = QHBoxLayout(logo_row)
        logo_layout.setContentsMargins(0, 0, 0, 0)
        self.logo_preview = QLabel(logo_row)
        self.logo_preview.setFixedSize(160, 90)
        self.logo_preview.setAlignment(Qt.AlignCenter)
        self.logo_preview.setProperty("role", "imagePreview")
        logo_layout.addWidget(self.logo_preview)
        self.logo_status = QLabel("", logo_row)
        self.logo_status.setWordWrap(True)
        logo_layout.addWidget(self.logo_status, stretch=1)
        self.logo_card.add(logo_row)
        self.load_logo_button = create_primary_button(self.logo_card, "Cargar logo de la empresa")
        self.remove_logo_button = create_secondary_button(self.logo_card, "Quitar logo")
        self.logo_card.add(self.load_logo_button)
        self.logo_card.add(self.remove_logo_button)
        self.layout().insertWidget(2, self.logo_card)

        actions = QWidget(self)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(Spacing.SM)
        self.new_branch_button = create_primary_button(actions, "Nueva sucursal")
        self.edit_branch_button = create_secondary_button(actions, "Editar sucursal")
        self.branch_logo_button = create_secondary_button(actions, "Logo de la sucursal…")
        actions_layout.addWidget(self.new_branch_button)
        actions_layout.addWidget(self.edit_branch_button)
        actions_layout.addWidget(self.branch_logo_button)
        actions_layout.addStretch(1)
        self.layout().insertWidget(3, actions)

        self.edit_company_button.clicked.connect(self._on_edit_company)
        self.anchor_installation_button.clicked.connect(self._on_anchor_installation)
        self.new_branch_button.clicked.connect(self._on_new_branch)
        self.edit_branch_button.clicked.connect(self._on_edit_branch)
        self.load_logo_button.clicked.connect(self._on_load_company_logo)
        self.remove_logo_button.clicked.connect(self._on_remove_company_logo)
        self.branch_logo_button.clicked.connect(self._on_branch_logo)

        self._reload_company_summary()
        self._reload_installation_summary()
        self._reload_logo()

    def reload(self, search: str = "") -> None:
        super().reload(search)
        self._reload_company_summary()
        self._reload_installation_summary()
        if hasattr(self, "logo_card"):
            self._reload_logo()

    # ── logo para tickets ────────────────────────────────────────────────
    def _reload_logo(self) -> None:
        path, source = self._presenter.current_logo(None)
        if path:
            pixmap = QPixmap(path)
            self.logo_preview.setPixmap(pixmap.scaled(160, 90, Qt.KeepAspectRatio,
                                                      Qt.SmoothTransformation))
            self.logo_status.setText("Logo de la empresa cargado. Para imprimirlo, activa el "
                                     "bloque «Logo» en el diseño del ticket (Documentos).")
        else:
            self.logo_preview.clear()
            self.logo_status.setText("Sin logo. Cárgalo aquí; cada sucursal puede tener el suyo.")
        self.remove_logo_button.setEnabled(bool(path))

    def _logo_dialog(self, title: str, *, branch_scope: bool):
        from frontend.desktop.modules.configuracion.dialogs.logo_upload_dialog import (
            LogoUploadDialog,
        )
        dialog = LogoUploadDialog(self._presenter, title=title, branch_scope=branch_scope,
                                  parent=self)
        return dialog if dialog.exec_() == QDialog.Accepted else None

    def _on_load_company_logo(self) -> None:
        dialog = self._logo_dialog("Logo de la empresa", branch_scope=False)
        if dialog is None or not dialog.source_path:
            return
        ok, message = self._presenter.assign_logo(
            source_path=dialog.source_path, remove_background=dialog.remove_background,
            tolerance=dialog.tolerance)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Logo", message)
        self._reload_logo()

    def _on_remove_company_logo(self) -> None:
        ok, message = self._presenter.assign_logo(source_path=None)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Logo", message)
        self._reload_logo()

    def _on_branch_logo(self) -> None:
        branch_id = self._selected_branch_id()
        if not branch_id:
            return
        dialog = self._logo_dialog("Logo de la sucursal", branch_scope=True)
        if dialog is None:
            return
        if dialog.use_company_logo:
            ok, message = self._presenter.assign_logo(source_path=None, branch_id=branch_id)
        elif dialog.source_path:
            ok, message = self._presenter.assign_logo(
                source_path=dialog.source_path, remove_background=dialog.remove_background,
                tolerance=dialog.tolerance, branch_id=branch_id)
        else:
            return
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Logo", message)

    def _reload_company_summary(self) -> None:
        company = self._presenter.get_company_profile()
        if company is None:
            self.company_summary_label.setText("Empresa no configurada todavía.")
        else:
            parts = [company.legal_name]
            if company.commercial_name:
                parts.append(f"«{company.commercial_name}»")
            parts.append(f"{company.default_currency} · {company.default_timezone} · {company.default_locale}")
            self.company_summary_label.setText(" — ".join(parts))

    def _reload_installation_summary(self) -> None:
        installation = self._presenter.get_installation_branch()
        if installation:
            self.installation_summary_label.setText(f"📍 Esta instalación: {installation[1]}")
        else:
            self.installation_summary_label.setText("📍 Instalación sin sucursal asignada")

    def _on_edit_company(self) -> None:
        company = self._presenter.get_company_profile()
        dlg = CompanyProfileDialog(
            self, profile=company,
            address_search_service=self._presenter.address_search_service())
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["legal_name"] or not values["default_currency"] or not values["default_timezone"] or not values["default_locale"]:
            QMessageBox.warning(
                self, "Empresa",
                "Razón social, moneda, zona horaria y configuración regional son obligatorios.",
            )
            return
        ok, message = self._presenter.save_company_profile(**values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Empresa", message)
        if ok:
            self._reload_company_summary()

    def _on_anchor_installation(self) -> None:
        branches = self._presenter.list_branches_for_user_selector()
        if not branches:
            QMessageBox.warning(self, "Sucursal de la instalación", "No hay sucursales activas disponibles.")
            return
        dlg = SetInstallationBranchDialog(self, branch_options=branches)
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        branch_id = values["branch_id"]
        if not branch_id:
            QMessageBox.warning(self, "Sucursal de la instalación", "Selecciona una sucursal.")
            return
        branch_name = next((name for bid, name in branches if bid == branch_id), branch_id)
        confirm = QMessageBox.question(
            self, "Sucursal de la instalación",
            f"¿Usar «{branch_name}» como la sucursal de esta instalación?\n\n"
            "El login y los módulos operarán sobre esa sucursal.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        ok, message = self._presenter.set_installation_branch(branch_id)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Sucursal de la instalación", message)
        if not ok:
            return
        self._reload_installation_summary()
        main_win = self.window()
        if main_win is not None and hasattr(main_win, "aplicar_sucursal_activa"):
            try:
                main_win.aplicar_sucursal_activa(branch_id, branch_name)
            except Exception:
                pass

    def _selected_branch_id(self) -> str | None:
        row_id = self.table.selected_row_id() if self.table is not None else None
        if not row_id:
            QMessageBox.warning(self, "Sucursales", "Selecciona una sucursal primero.")
        return row_id

    def _on_new_branch(self) -> None:
        branches = self._presenter.list_unregistered_branches()
        if not branches:
            QMessageBox.warning(
                self, "Sucursales",
                "No hay sucursales sin perfil de gobierno registrado — todas ya lo tienen.",
            )
            return
        dlg = BranchProfileCreateDialog(
            self, branch_options=branches,
            address_search_service=self._presenter.address_search_service())
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["branch_id"] or not values["code"] or not values["name"]:
            QMessageBox.warning(self, "Sucursales", "Sucursal, código y nombre son obligatorios.")
            return
        ok, message = self._presenter.register_branch_profile(**values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Sucursales", message)
        if ok:
            self.reload(self.search.text())

    def _on_edit_branch(self) -> None:
        branch_id = self._selected_branch_id()
        if not branch_id:
            return
        profile = self._presenter.get_branch_profile(branch_id)
        if profile is None:
            QMessageBox.warning(self, "Sucursales", "La sucursal ya no existe.")
            return
        dlg = BranchProfileEditDialog(
            self, profile=profile,
            address_search_service=self._presenter.address_search_service())
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["name"]:
            QMessageBox.warning(self, "Sucursales", "El nombre es obligatorio.")
            return
        ok, message = self._presenter.update_branch_profile(branch_id=branch_id, **values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Sucursales", message)
        if ok:
            self.reload(self.search.text())


__all__ = ["EmpresaPage"]
