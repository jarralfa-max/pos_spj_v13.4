"""Dialogs for the "Offline" section — Expiration pillar only
(`CacheExpirationPolicy`). Built entirely on `FormDialog`, same
convention as every other dialog in this package. `OfflineCacheEntry`
has no dialogs — it is a read-only diagnostic listing, no create/edit
flow (see `offline_page.py`'s module docstring).
"""

from __future__ import annotations

from frontend.desktop.components import FormDialog, StandardLineEdit, apply_tooltip


def _parse_int(text: str, default: int) -> int:
    try:
        return int(text.strip() or str(default))
    except ValueError:
        return default


class CacheExpirationPolicyCreateDialog(FormDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Nueva política de expiración")
        self.entity_type = StandardLineEdit(self)
        self.entity_type.setAccessibleName("Tipo de entidad")
        apply_tooltip(self.entity_type, "Ej. «customer», «product» — el tipo de entidad que se cachea.")
        self.form.addRow("Tipo de entidad:", self.entity_type)

        self.ttl_seconds = StandardLineEdit(self)
        self.ttl_seconds.setText("3600")
        self.ttl_seconds.setAccessibleName("TTL en segundos")
        self.form.addRow("TTL (segundos):", self.ttl_seconds)

        self.add_button_box(ok_text="Crear política")

    def values(self) -> dict:
        return {
            "entity_type": self.entity_type.text().strip(),
            "ttl_seconds": _parse_int(self.ttl_seconds.text(), 3600),
        }


class CacheExpirationPolicyEditDialog(FormDialog):
    """Edits only `ttl_seconds` — `entity_type` is the identity field,
    same boundary every other create/edit pair in this package draws."""

    def __init__(self, parent=None, *, ttl_seconds: int = 3600) -> None:
        super().__init__(parent, title="Editar política de expiración")
        self.ttl_seconds = StandardLineEdit(self)
        self.ttl_seconds.setText(str(ttl_seconds))
        self.ttl_seconds.setAccessibleName("TTL en segundos")
        self.form.addRow("TTL (segundos):", self.ttl_seconds)
        self.add_button_box(ok_text="Guardar")

    def values(self) -> dict:
        return {"ttl_seconds": _parse_int(self.ttl_seconds.text(), 3600)}
