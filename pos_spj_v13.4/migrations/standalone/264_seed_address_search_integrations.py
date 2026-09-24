"""264 — Mapbox y OpenStreetMap aparecen en Configuración → Integraciones.

Decisión del usuario: la búsqueda de direcciones usa una API de mapas (Mapbox)
**configurable desde Configuración**, con respaldo a Nominatim y después captura
manual.

El mecanismo ya existía y no hacía falta inventar otro: Integraciones tiene CRUD
real de definiciones, instancias y credenciales, `IntegrationCategory.LOCATION`
ya estaba en el enum, y el token se guarda en el almacén de secretos. Lo que
faltaba era que las dos integraciones EXISTIERAN, para que el administrador las
encuentre en la lista en vez de tener que crearlas a mano adivinando el código
exacto que la aplicación busca.

QUÉ SIEMBRA
-----------
* MAPBOX, con su instancia **INACTIVA**: todavía no hay token. Activarla sin
  token no rompería nada (la fábrica la ignora), pero la mostraría encendida sin
  funcionar. Pasos del administrador: Integraciones → Mapbox → Credenciales →
  `mapbox_access_token` → pegar el token → Activar.
  Configuración por omisión: país `mx`, idioma `es`, límite 5, `permanent`
  verdadero (este ERP GUARDA las coordenadas, y los resultados "temporales" de
  Mapbox no pueden guardarse según sus condiciones).
* NOMINATIM (OpenStreetMap), **ACTIVA**: no requiere token y es el respaldo que
  pidió el usuario. `contact_email` queda vacío; conviene llenarlo, la política
  de uso de Nominatim pide identificarse.

IDEMPOTENTE: se busca por código; si la integración ya existe no se toca — ni su
estado ni su configuración ni su credencial, que el administrador puede haber
cambiado.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.264")

_SEEDS = (
    {
        "code": "MAPBOX", "name": "Mapbox (direcciones)",
        "credentials": ("mapbox_access_token",),
        "instance": "Mapbox",
        "config": {"country": "mx", "language": "es", "limit": 5, "permanent": True},
        "credential_references": {"mapbox_access_token": "mapbox_access_token"},
        "instance_active": False,
    },
    {
        "code": "NOMINATIM", "name": "OpenStreetMap / Nominatim (direcciones, respaldo)",
        "credentials": (),
        "instance": "OpenStreetMap",
        "config": {"country": "mx", "language": "es", "limit": 5, "contact_email": ""},
        "credential_references": {},
        "instance_active": True,
    },
)


def _table_exists(conn, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def run(conn) -> None:
    if not (_table_exists(conn, "integration_definitions")
            and _table_exists(conn, "integration_instances")):
        logger.info("264: el esquema de integraciones (219) no existe; nada que sembrar.")
        return

    from backend.domain.integrations.entities.integration_definition import (
        IntegrationDefinition,
    )
    from backend.domain.integrations.entities.integration_instance import IntegrationInstance
    from backend.domain.integrations.enums import IntegrationCategory
    from backend.infrastructure.db.repositories.integrations.integration_definition_repository import (
        SqliteIntegrationDefinitionRepository,
    )
    from backend.infrastructure.db.repositories.integrations.integration_instance_repository import (
        SqliteIntegrationInstanceRepository,
    )

    definiciones = SqliteIntegrationDefinitionRepository(conn)
    instancias = SqliteIntegrationInstanceRepository(conn)
    sembradas = 0
    for semilla in _SEEDS:
        if definiciones.get_by_code(semilla["code"]) is not None:
            continue
        definicion = IntegrationDefinition.create(
            code=semilla["code"], name=semilla["name"],
            category=IntegrationCategory.LOCATION,
            required_credential_names=semilla["credentials"])
        definiciones.save(definicion)
        instancia = IntegrationInstance.create(
            definition_id=definicion.id, name=semilla["instance"],
            config=dict(semilla["config"]),
            credential_references=dict(semilla["credential_references"]))
        if not semilla["instance_active"]:
            instancia.deactivate()
        instancias.save(instancia)
        sembradas += 1
    conn.commit()
    logger.info("264: %s integraciones de direcciones sembradas.", sembradas)


up = run
