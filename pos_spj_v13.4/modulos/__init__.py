"""Compatibilidad de módulos UI del POS."""


def _patch_qcompleter_minimum_contents_length() -> None:
    """Evita crash por llamada legacy a QCompleter.setMinimumContentsLength.

    En PyQt5, QCompleter no tiene este método; pertenece a QComboBox. El módulo
    de ventas ya controla sugerencias desde 1 carácter con su propia validación,
    por lo que aquí sólo se conserva compatibilidad sin cambiar layout ni UX.
    """
    try:
        from PyQt5.QtWidgets import QCompleter
    except Exception:
        return

    if hasattr(QCompleter, "setMinimumContentsLength"):
        return

    def _set_minimum_contents_length(self, length: int) -> None:
        try:
            self._spj_minimum_contents_length = int(length or 0)
        except Exception:
            self._spj_minimum_contents_length = 0

    QCompleter.setMinimumContentsLength = _set_minimum_contents_length


_patch_qcompleter_minimum_contents_length()
