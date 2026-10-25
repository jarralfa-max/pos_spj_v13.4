"""AutoCodeBinder — código de catálogo que se llena solo desde el nombre (PROD-23).

UI only. Mientras quien captura no toque el campo «Código», éste muestra el
código que se generará (lo calcula el backend: del nombre, libre en su ámbito).
Si lo reescribe, se respeta; si lo borra, vuelve a ser automático. Al guardar,
un código automático viaja VACÍO para que el alta lo resuelva dentro de su
transacción (la vista previa no aparta nada).
"""

from __future__ import annotations

from typing import Callable

from PyQt5.QtCore import QObject

AUTO_PLACEHOLDER = "Automático (se genera del nombre)"
AUTO_TOOLTIP = ("Se genera del nombre. Puedes reescribirlo; si lo borras vuelve a "
                "generarse.")


class AutoCodeBinder(QObject):
    def __init__(self, name_edit, code_edit, suggest: Callable[[str], str],
                 parent=None) -> None:
        super().__init__(parent or code_edit)
        self._name = name_edit
        self._code = code_edit
        self._suggest = suggest
        self._last_auto = ""
        code_edit.setPlaceholderText(AUTO_PLACEHOLDER)
        code_edit.setToolTip(AUTO_TOOLTIP)
        name_edit.textChanged.connect(self._on_name_changed)
        code_edit.textEdited.connect(self._on_code_edited)  # sólo el usuario
        self.refresh()

    @property
    def is_manual(self) -> bool:
        """Manual = hay un código y no es el último que se sugirió."""
        text = self._code.text().strip()
        return bool(text) and text != self._last_auto

    def refresh(self) -> None:
        if self.is_manual:
            return
        name = self._name.text().strip()
        try:
            code = (self._suggest(name) or "") if name else ""
        except Exception:  # noqa: BLE001 — sin sugerencia, el alta lo genera igual
            code = ""
        self._last_auto = code
        self._code.setText(code)

    def code_for_save(self) -> str:
        """Lo escrito (mayúsculas) o ``""`` para que el alta lo genere."""
        return self._code.text().strip().upper() if self.is_manual else ""

    def _on_name_changed(self, _text: str) -> None:
        self.refresh()

    def _on_code_edited(self, text: str) -> None:
        if not text.strip():  # lo borró: vuelve a automático
            self.refresh()


def catalog_suggester(presenter, kind: str, *, scope_id: str | None = None
                      ) -> Callable[[str], str]:
    """``name → código sugerido`` vía ``presenter.suggest_catalog_code``."""
    suggest = getattr(presenter, "suggest_catalog_code", None)
    if suggest is None:
        return lambda _name: ""
    return lambda name: suggest(kind, name, scope_id=scope_id)
