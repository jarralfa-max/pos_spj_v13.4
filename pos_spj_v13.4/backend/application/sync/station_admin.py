"""Alta, suspensión y baja de estaciones en el servidor central (Slice 4).

Lo ejecuta el administrador en el servidor (script `scripts/central/stations.py`),
nunca una estación: dar de alta una caja requiere acceso al servidor, no una
credencial distribuida en los clientes. El secreto se muestra UNA vez y se
captura en el instalador de esa estación (Slice 10); el servidor guarda sólo su
huella.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from backend.application.sync.station_credentials import issue_station_secret
from backend.shared.ids import validate_uuidv7


@dataclass(frozen=True)
class IssuedStation:
    station_id: str
    branch_id: str
    secret: str


class CentralStationAdmin:
    def __init__(self, repository) -> None:
        self._repo = repository

    def register(self, *, station_id: str, branch_id: str,
                 display_name: str = "") -> IssuedStation:
        validate_uuidv7(station_id)
        validate_uuidv7(branch_id)
        if self._repo.get_station(station_id) is not None:
            raise ValueError("La estación ya está registrada; use rotate para una nueva credencial")
        secreto, huella = issue_station_secret()
        self._repo.register_station(station_id=station_id, branch_id=branch_id,
                                    display_name=display_name.strip(), credential_hash=huella)
        self._repo.commit()
        return IssuedStation(station_id, branch_id, secreto)

    def suspend(self, station_id: str) -> None:
        self._set(station_id, "SUSPENDED")

    def reactivate(self, station_id: str) -> None:
        self._set(station_id, "ACTIVE")

    def retire(self, station_id: str) -> None:
        """Baja definitiva (estación perdida o reemplazada): sus envíos se rechazan."""
        self._set(station_id, "RETIRED")

    def _set(self, station_id: str, status: str) -> None:
        estacion = self._repo.get_station(station_id)
        if estacion is None:
            raise LookupError("Estación no registrada")
        if estacion["status"] == "RETIRED":
            raise ValueError("Una estación dada de baja no se reactiva; registre una nueva")
        self._repo.set_station_status(station_id, status, now=datetime.now(timezone.utc))
        self._repo.commit()


__all__ = ["CentralStationAdmin", "IssuedStation"]
