"""SideNav — barra de navegación lateral enterprise (DS).

Lista vertical de secciones (icono opcional + etiqueta) que emite ``navigated(int)``
al cambiar la selección. Diseñada para acompañar un ``QStackedWidget``: el índice de
la sección coincide con el índice de la página apilada. Sólo presentación —
estilizable por QSS vía ``objectName`` (``sideNav`` / ítems).
"""

from __future__ import annotations

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtWidgets import QListWidget, QListWidgetItem, QMenu

from frontend.desktop.components.buttons import create_icon_button
from frontend.desktop.components.icons import IconProvider, Icons
from frontend.desktop.themes.theme_manager import ThemeManager
from frontend.desktop.themes.tokens import density_metrics


class NavItem(QListWidgetItem):
    """A permitted destination rendered by the canonical sidebar."""


class NavGroup(QListWidgetItem):
    """Interactive header whose children retain stable page-row addresses."""


class SideNav(QListWidget):
    #: Emitido con el índice de la sección seleccionada.
    navigated = pyqtSignal(int)

    def __init__(self, parent=None, *, toggle_visible: bool = True,
                 settings=None, settings_key: str = "", group_flyouts: bool = True) -> None:
        super().__init__(parent)
        self.setObjectName("sideNav")
        self.setProperty("component", "moduleSidebar")
        self.setAccessibleName("Navegación del módulo")
        self.setFocusPolicy(Qt.StrongFocus)
        self.setUniformItemSizes(True)
        self.setIconSize(QSize(18, 18))
        self.setMinimumWidth(180)
        self.setMaximumWidth(240)
        self._settings = settings
        self._settings_key = settings_key
        self._collapsed = False
        self._expanded_widths = (180, 240)
        self._toggle_visible = toggle_visible
        self._group_flyouts = group_flyouts
        self._toggle = create_icon_button(self, Icons.CHEVRON_LEFT, "Contraer navegación del módulo")
        self._toggle.clicked.connect(lambda: self.set_collapsed(not self._collapsed))
        self._toggle.setVisible(toggle_visible)
        self._flyout = None
        self.currentRowChanged.connect(self._on_row_changed)
        self.itemClicked.connect(self._on_item_clicked)
        ThemeManager.instance().density_changed.connect(self._apply_density)
        ThemeManager.instance().theme_changed.connect(self._refresh_icons)
        self._apply_density()
        if self._settings is not None and self._settings_key:
            self.set_collapsed(self._settings.value(f"{self._settings_key}/collapsed", False, type=bool))

    _BASE_LABEL_ROLE = Qt.UserRole + 20
    _BADGE_ROLE = Qt.UserRole + 21
    _GROUP_ROLE = Qt.UserRole + 22
    _EXPANDED_ROLE = Qt.UserRole + 23
    _ICON_ROLE = Qt.UserRole + 24

    def add_section(self, label: str, icon=None, *, badge: int = 0) -> None:
        item = NavItem()
        item.setData(self._BASE_LABEL_ROLE, label)
        item.setData(self._GROUP_ROLE, False)
        if icon is None or isinstance(icon, str):
            item.setData(self._ICON_ROLE, icon or Icons.HOME)
            item.setIcon(IconProvider.icon(icon or Icons.HOME))
        else:
            item.setIcon(icon)
        item.setToolTip(label)
        item.setSizeHint(QSize(0, density_metrics().sidebar_item_height))
        self.addItem(item)
        self.set_badge(self.count() - 1, badge)
        self._apply_group_visibility()

    def set_badge(self, row: int, count: int) -> None:
        item = self.item(row)
        if item is None or not bool(item.flags() & Qt.ItemIsEnabled):
            return
        count = max(0, int(count or 0))
        label = str(item.data(self._BASE_LABEL_ROLE) or item.text())
        item.setData(self._BADGE_ROLE, count)
        item.setText("" if self._collapsed else (f"{label}  ·  {count}" if count else label))
        item.setData(Qt.AccessibleTextRole,
                     f"{label}, {count} pendientes" if count else label)

    def add_group(self, label: str, icon: str = Icons.HOME, *, badge: int = 0) -> None:
        """Interactive group; hiding children preserves existing page indices."""
        item = NavGroup(label)
        item.setData(self._BASE_LABEL_ROLE, label)
        item.setData(self._GROUP_ROLE, True)
        expanded = True
        if self._settings is not None and self._settings_key:
            expanded = self._settings.value(f"{self._settings_key}/groups/{label}", True, type=bool)
        item.setData(self._EXPANDED_ROLE, expanded)
        item.setData(self._ICON_ROLE, icon)
        item.setData(self._BADGE_ROLE, max(0, badge))
        item.setData(Qt.AccessibleTextRole, label)
        item.setToolTip(label)
        item.setSizeHint(QSize(0, density_metrics().sidebar_item_height))
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        self.addItem(item)
        self._refresh_group(item)

    def _on_row_changed(self, row: int) -> None:
        if row >= 0 and not self.item(row).data(self._GROUP_ROLE):
            self.navigated.emit(row)

    def select(self, index: int) -> None:
        if 0 <= index < self.count():
            if not self.item(index).data(self._GROUP_ROLE):
                for row in range(index - 1, -1, -1):
                    if self.item(row).data(self._GROUP_ROLE):
                        self.item(row).setData(self._EXPANDED_ROLE, True)
                        self._refresh_group(self.item(row))
                        break
                self._apply_group_visibility()
            self.setCurrentRow(index)

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool) -> None:
        collapsed = bool(collapsed)
        if collapsed and not self._collapsed:
            self._expanded_widths = (self.minimumWidth(), self.maximumWidth())
        self._collapsed = collapsed
        if collapsed:
            self.setMinimumWidth(60)
            self.setMaximumWidth(64)
        else:
            self.setMinimumWidth(self._expanded_widths[0])
            self.setMaximumWidth(self._expanded_widths[1])
        IconProvider.bind(self._toggle, Icons.CHEVRON_RIGHT if collapsed else Icons.CHEVRON_LEFT)
        text = "Expandir navegación del módulo" if collapsed else "Contraer navegación del módulo"
        self._toggle.setToolTip(text)
        self._toggle.setAccessibleName(text)
        for row in range(self.count()):
            item = self.item(row)
            if item.data(self._GROUP_ROLE):
                self._refresh_group(item)
            else:
                self.set_badge(row, item.data(self._BADGE_ROLE) or 0)
        self._apply_group_visibility()
        self._apply_density()
        if self._settings is not None and self._settings_key:
            self._settings.setValue(f"{self._settings_key}/collapsed", collapsed)

    def set_persistence(self, settings, settings_key: str) -> None:
        """Attach the shell's user/terminal scope after a module builds its rows."""
        if settings is self._settings and settings_key == self._settings_key:
            return
        self._settings, self._settings_key = settings, settings_key
        for row in range(self.count()):
            item = self.item(row)
            if item.data(self._GROUP_ROLE):
                item.setData(self._EXPANDED_ROLE, settings.value(
                    f"{settings_key}/groups/{item.data(self._BASE_LABEL_ROLE)}", True, type=bool,
                ))
                self._refresh_group(item)
        self.set_collapsed(settings.value(f"{settings_key}/collapsed", False, type=bool))

    def toggle_group(self, row: int) -> None:
        item = self.item(row)
        if item is None or not item.data(self._GROUP_ROLE):
            return
        if self._collapsed:
            self._flyout = self.group_menu(row)
            self._flyout.popup(self.viewport().mapToGlobal(self.visualItemRect(item).topRight()))
            return
        expanded = not bool(item.data(self._EXPANDED_ROLE))
        item.setData(self._EXPANDED_ROLE, expanded)
        self._refresh_group(item)
        self._apply_group_visibility()
        if self._settings is not None and self._settings_key:
            self._settings.setValue(f"{self._settings_key}/groups/{item.data(self._BASE_LABEL_ROLE)}", expanded)

    def group_menu(self, row: int) -> QMenu:
        """Build the reduced group's flyout from its already permitted rows."""
        menu = QMenu(str(self.item(row).data(self._BASE_LABEL_ROLE)), self)
        for child_row in range(row + 1, self.count()):
            child = self.item(child_row)
            if child.data(self._GROUP_ROLE):
                break
            action = menu.addAction(child.icon(), str(child.data(self._BASE_LABEL_ROLE)))
            if child.data(self._ICON_ROLE):
                IconProvider.bind(action, child.data(self._ICON_ROLE), size=self.iconSize().width())
            action.setEnabled(bool(child.flags() & Qt.ItemIsEnabled))
            action.triggered.connect(lambda checked=False, index=child_row: self._activate_flyout_row(index))
        return menu

    def _activate_flyout_row(self, row: int) -> None:
        if self.currentRow() == row:
            self.navigated.emit(row)
        else:
            self.setCurrentRow(row)

    def _on_item_clicked(self, item) -> None:
        if item.data(self._GROUP_ROLE):
            self.toggle_group(self.row(item))

    def keyPressEvent(self, event) -> None:  # noqa: N802
        item = self.currentItem()
        if item is not None and item.data(self._GROUP_ROLE) and event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.toggle_group(self.currentRow())
            event.accept()
            return
        super().keyPressEvent(event)

    def _refresh_group(self, item) -> None:
        expanded = bool(item.data(self._EXPANDED_ROLE))
        icon = item.data(self._ICON_ROLE) if self._collapsed else (Icons.CHEVRON_DOWN if expanded else Icons.CHEVRON_RIGHT)
        item.setIcon(IconProvider.icon(icon))
        label = str(item.data(self._BASE_LABEL_ROLE))
        count = item.data(self._BADGE_ROLE) or 0
        item.setText("" if self._collapsed else (f"{label}  ·  {count}" if count else label))
        item.setData(Qt.AccessibleTextRole, f"{label}, {'expandido' if expanded else 'contraído'}")

    def _apply_group_visibility(self) -> None:
        group = None
        for row in range(self.count()):
            item = self.item(row)
            if item.data(self._GROUP_ROLE):
                group = item
                item.setHidden(self._collapsed and not self._group_flyouts)
            else:
                hide_group = self._collapsed and self._group_flyouts
                hide_children = not self._collapsed and not bool(group.data(self._EXPANDED_ROLE)) if group else False
                item.setHidden(group is not None and (hide_group or hide_children))

    def _apply_density(self, *_args) -> None:
        height = density_metrics().sidebar_item_height
        for row in range(self.count()):
            self.item(row).setSizeHint(QSize(0, height))
        self.setViewportMargins(0, height + 8 if self._toggle_visible else 0, 0, 0)
        self._toggle.move(6, 4)

    def _refresh_icons(self, *_args) -> None:
        for row in range(self.count()):
            item = self.item(row)
            if item.data(self._GROUP_ROLE):
                self._refresh_group(item)
            elif item.data(self._ICON_ROLE):
                item.setIcon(IconProvider.icon(item.data(self._ICON_ROLE)))


# Existing modules retain their row-based API; both names resolve to one class.
ModuleSidebar = SideNav
