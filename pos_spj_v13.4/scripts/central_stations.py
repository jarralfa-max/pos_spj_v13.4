"""Administración del servidor central desde la consola (arquitectura híbrida).

Se ejecuta EN el servidor central, con `SPJ_PG_DSN` en el entorno:

    python scripts/central_stations.py migrate
    python scripts/central_stations.py project      # reproyecta lo pendiente
    python scripts/central_stations.py register --station <uuid> --branch <uuid> --name "Caja 1 Centro"
    python scripts/central_stations.py suspend|reactivate|retire --station <uuid>

`register` imprime el secreto de la estación UNA sola vez: cópielo al instalador
de esa caja. El servidor sólo guarda su huella; si se pierde, se da de baja la
estación y se registra otra.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(argv: list[str] | None = None) -> int:
    from backend.application.sync.station_admin import CentralStationAdmin
    from backend.infrastructure.central.sync_inbox_repository import (
        PostgresCentralInboxRepository,
    )
    from backend.infrastructure.db.database import DatabaseSettings, create_connection_factory

    parser = argparse.ArgumentParser(description="Servidor central SPJ")
    parser.add_argument("command", choices=("migrate", "project", "register", "suspend",
                                            "reactivate", "retire"))
    parser.add_argument("--station")
    parser.add_argument("--branch")
    parser.add_argument("--name", default="")
    args = parser.parse_args(argv)

    conexion = create_connection_factory(DatabaseSettings.postgresql_from_env())()
    try:
        if args.command == "migrate":
            from migrations.engine import up_postgresql
            print(f"Migraciones aplicadas: {up_postgresql(conexion)}")
            return 0
        if args.command == "project":
            from backend.application.sync.central_projection import CentralProjector
            from backend.infrastructure.central.projection_repository import (
                PostgresCentralProjectionRepository,
            )
            total = CentralProjector(PostgresCentralProjectionRepository(conexion)).run_once(
                limit=100_000)
            print(f"Proyectados={total.projected} omitidos={total.skipped} errores={total.errors}")
            return 0
        if not args.station:
            parser.error("--station es obligatorio")
        admin = CentralStationAdmin(PostgresCentralInboxRepository(conexion))
        if args.command == "register":
            if not args.branch:
                parser.error("--branch es obligatorio para register")
            emitida = admin.register(station_id=args.station, branch_id=args.branch,
                                     display_name=args.name)
            print("Estación registrada. Secreto (se muestra UNA vez, guárdelo en el instalador):")
            print(emitida.secret)
            return 0
        getattr(admin, args.command)(args.station)
        print(f"Estación {args.station}: {args.command} aplicado.")
        return 0
    finally:
        conexion.close()


if __name__ == "__main__":
    raise SystemExit(main())
