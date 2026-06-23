"""Application service for hardware settings writes.

Keeps SQL, schema creation and ``commit()`` out of the PyQt hardware panel. The
UI builds plain config dicts and delegates persistence to this service, which
owns the transaction boundary (until the UnitOfWork lands in a later phase).
Reads stay tolerant: the canonical ``hardware_config`` table is created by the
migration engine (``m000``/``m050``), not by the UI.
"""

from __future__ import annotations

from typing import Any, Dict

from core.repositories.hardware_config_repository import HardwareConfigRepository

# Canonical hardware domains rendered by the hardware panel, in display order.
HARDWARE_TYPES = ("bascula", "ticket", "etiquetas", "cajon", "scanner", "red")


class HardwareSettingsService:
    """Read/write application service over the canonical hardware repository."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self._repository = HardwareConfigRepository(connection)

    def load_all(self) -> Dict[str, Dict[str, Any]]:
        """Return the parsed config for every hardware domain."""
        return {tipo: self._repository.get_config(tipo) for tipo in HARDWARE_TYPES}

    def save_all(self, configs: Dict[str, Dict[str, Any]]) -> None:
        """Persist every provided hardware config in a single transaction."""
        for tipo, config in configs.items():
            self._persist(tipo, config)
        self._commit()

    def save_one(self, tipo: str, config: Dict[str, Any]) -> None:
        """Persist a single hardware domain config (e.g. the ticket printer)."""
        self._persist(tipo, config)
        self._commit()

    # -- internals ---------------------------------------------------------
    def _persist(self, tipo: str, config: Dict[str, Any]) -> None:
        nombre = HardwareConfigRepository.DEFAULT_TYPES.get(tipo, tipo.capitalize())
        self._repository.save_config(tipo, nombre, config, activo=1)

    def _commit(self) -> None:
        commit = getattr(self._connection, "commit", None)
        if callable(commit):
            commit()
