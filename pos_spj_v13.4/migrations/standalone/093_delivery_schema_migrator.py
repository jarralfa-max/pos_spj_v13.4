"""Migración 093 — INERTE. El esquema legacy de Delivery ya no se crea.

Esta migración delegaba TODO su trabajo en
`core.delivery.infrastructure.delivery_schema_migrator.DeliverySchemaMigrator`,
clase que ya no existe: la reconstrucción en arquitectura nueva eliminó la
carpeta `core/`. No se recupera del historial de Git (§18) y tampoco se
reescribe, porque reescribirla significaría volver a crear un esquema que en
esta versión no lee nadie.

QUÉ SE MIDIÓ ANTES DE DEJARLA INERTE
------------------------------------
- La única tabla que aportaba y que no aporta ninguna otra migración es
  `pedidos`. Se comprobó ejecutando la cadena completa de migraciones sin
  093/094/095/096: se crean 743 tablas y la única ausente es `pedidos`.
- `pedidos` no tiene NINGÚN lector ni escritor en `backend/` ni en `frontend/`.
  Las apariciones que un `grep` superficial sugiere son de `pedidos_whatsapp`,
  que es otra tabla y la crea otra migración.
- Ninguna migración posterior hace ALTER ni INSERT sobre `pedidos`. La única
  referencia en toda la carpeta es una FOREIGN KEY declarada en la 036, que
  corre ANTES que ésta y que SQLite no valida al crear la tabla.
- `scripts/verify_tables.py`, el validador de esquema del arranque, no la
  exige.
- El dominio de pedidos y reparto vive ahora en el contexto acotado canónico
  `orders_delivery`, cuyo esquema real (`customer_orders`, `delivery_jobs`,
  `delivery_routes`, … 15 tablas) crea la migración 226 desde
  `backend/infrastructure/db/schema/orders_delivery_schema.py`.

ALCANCE DEL CAMBIO
------------------
Las instalaciones existentes conservan `pedidos` tal cual: la 093 ya figura
como ejecutada en su tabla de control y no vuelve a correr. El cambio sólo
afecta a instalaciones NUEVAS, que dejan de crear una tabla que nadie
consulta. No se hace DROP de nada.

Se conserva el archivo, y no se borra, porque su número tiene que seguir
existiendo en la cadena: eliminarlo cambiaría el control de versiones de
esquema en todas las bases ya migradas.
"""
from __future__ import annotations

import sqlite3

version = 93
description = "delivery schema migrator (inerte: superseded por 226/orders_delivery)"


def up(conn: sqlite3.Connection) -> None:
    """No hace nada, a propósito. Ver el docstring del módulo."""


run = up
