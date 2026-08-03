from backend.domain.losses.enums import MaterialDispositionKind


class LossClassificationPolicy:
    """Protect the semantic boundary between loss and recoverable outputs."""

    _LOSS_MATERIALS = frozenset({MaterialDispositionKind.WASTE})

    def is_loss_material(self, material_kind: MaterialDispositionKind) -> bool:
        return material_kind in self._LOSS_MATERIALS
