# Fase 1 — Modelo organizacional (auditoría enterprise)

**Fecha:** 2026-10-25.

**Cierra:**
- **N06**: no había organización, entidad legal ni planta.
- **N12**: ninguna vía de la app daba de alta una sucursal nueva.

**Decisiones aplicadas:** D2 (un solo RFC, sin `legal_entities` por ahora).

## 1. Qué se construyó

| Capa | Archivo | Qué hace |
|---|---|---|
| Dominio | `backend/domain/organization/org_unit.py` | `OrgUnit`, tipos, estados, capacidades y reglas (jerarquía, ciclos, ciclo de vida, capacidades) |
| Migración | `migrations/standalone/351_organizational_structure.py` | Crea `org_units` y `org_unit_capabilities`, agrega la columna `org_unit_id` y respalda las sucursales existentes |
| Infraestructura | `backend/infrastructure/db/repositories/organization/org_unit_repository.py` | Repositorio y UoW; mantiene juntas la unidad y su fila de `sucursales` |
| Aplicación | `backend/application/organization/org_structure_service.py` | `OrgStructureQueryService` (lectura interna) y `OrgStructureService` (la única puerta de la UI: autoriza, abre la transacción y audita) |
| UI | `frontend/desktop/modules/configuracion/pages/empresa_page.py`, `dialogs/org_structure_dialogs.py` | Tarjeta «Estructura organizacional» dentro de *Empresa y sucursales* |
| Aprovisionamiento | `provision_installation_use_case.py` | La sucursal inicial nace también como unidad, con el mismo id |

## 2. Modelo

```
Organización = company_profiles (installation.company_id)
└─ org_units (parent_id)
   ├─ REGION              agrupa; no opera, sin fila de sucursal
   ├─ CORPORATE_OFFICE    sitio
   ├─ RETAIL_BRANCH       sitio
   ├─ PRODUCTION_PLANT    sitio
   ├─ DISTRIBUTION_CENTER sitio
   ├─ WAREHOUSE           sitio (puede colgar de planta, CEDIS o sucursal)
   └─ LOGISTICS_OPERATION sitio
```

**Sitio de operación = la misma fila con el mismo id en `org_units` y en `sucursales`.**

- Todo `branch_id` que ya usan Inventario, Caja, Ventas o Finanzas es el id de un sitio. No se renombró
  nada ni se reescribió ningún módulo.
- Crear un sitio crea su fila de `sucursales`.
- Renombrarlo, desactivarlo o cerrarlo actualiza `nombre` y `activa` de esa fila.

**Capacidades** (SALES, POS, CASH, INVENTORY, PURCHASING, RECEIVING, PRODUCTION, LOGISTICS, FINANCE,
CRM, BI):

- se guardan por unidad, nunca se deducen del tipo;
- al crear una unidad se *proponen* las de su tipo;
- cada cambio exige motivo y queda en `audit_logs`.

Reglas:
- Una región no puede tener capacidades de sitio.
- POS exige SALES y CASH.
- No se quita CASH con turnos de caja abiertos.

**Ciclo de vida.** ACTIVE ⇄ INACTIVE → CLOSED (definitivo, con fecha).
- No se desactiva ni se cierra una unidad con dependientes activas.
- Una unidad inactiva no recibe dependientes.
- No se reactiva una unidad cuyo superior está inactivo.
- No se desactiva ni se cierra la sucursal anclada a esta instalación, ni un sitio con turnos de caja
  abiertos.

## 3. Lo que NO cambia (preservación)

- **Las sucursales existentes conservan todas sus capacidades.** La 351 no le quita nada a nadie.
- **Ningún módulo lee todavía `org_unit_capabilities`.** Cerrar el POS en una planta, o bloquear la
  venta donde no hay SALES, es parte de la Fase 2 (sesión contextual). Hoy la capacidad queda
  registrada y es visible.
- **Almacenes.** La base real tiene 0 filas en `warehouses`: los módulos operan por sucursal. Un sitio
  nuevo queda igual que los existentes, así que no se aprovisiona almacén. Cuando los puentes pasen a
  almacén real, `ProvisionDefaultWarehouseUseCase` se llamará al crear el sitio.
- **El perfil de la sucursal** (`branch_profiles`: horario, tickets, logo) se sigue registrando con
  «Nueva sucursal». Al crear una unidad tipo sucursal, el mensaje lo indica.
- **Sin evento ni réplica.** El organigrama aún no viaja al servidor central; la bajada de datos
  maestros es posterior.

## 4. Autorización y auditoría

Todo se autoriza en la capa de aplicación (`OrgStructureService._require`), incluida la lectura del
árbol, con los códigos del catálogo existente, sin un sistema nuevo:

| Código | Permite |
|---|---|
| `CONFIGURACION.organizacion.ver` | Ver el árbol |
| `CONFIGURACION.organizacion.crear` | Dar de alta unidades |
| `CONFIGURACION.organizacion.editar` | Renombrar y mover |
| `CONFIGURACION.organizacion.cerrar` | Desactivar, reactivar y cerrar |
| `CONFIGURACION.organizacion.capacidades` | Cambiar capacidades |

Siembra de la 351:
- `system_owner` y `admin`: todo;
- `gerente`: ver.

Cada comando escribe en `audit_logs`:
- entidad `org_unit`;
- antes y después;
- motivo;
- `operation_id`.

## 5. Para las fases siguientes

- `OrgStructureQueryService.descendant_ids(unit)`: herencia de alcance en la Fase 2. Un alcance sobre
  una región cubre sus sitios.
- `operating_site_ids_under(unit)`: filtro de consolidación de Finanzas en la Fase 3.
- `has_capability(unit, cap)`: validar el sitio operativo de la sesión en la Fase 2.
- `cost_centers`, `profit_centers` y `hr_departments` tienen `org_unit_id`, todavía sin uso.

## 6. Evidencia

| Prueba | Resultado |
|---|---|
| `tests/unit/organization/test_org_unit.py` | 8 pasan |
| `tests/integration/organization/test_org_structure.py` | 14 pasan |
| `tests/unit/test_empresa_page_org_structure.py` | 4 pasan |
| Aprovisionamiento, catálogo de permisos de Configuración, 345 | pasan |

`tests/integration/organization/test_org_structure.py` cubre:
- respaldo e idempotencia de la migración;
- base sin empresa;
- siembra por rol;
- unidad del aprovisionamiento;
- alta de sitio con su fila de `sucursales`;
- unicidad de códigos;
- mover y auditar;
- bloqueos de cierre;
- capacidades atómicas;
- que todo comando y la lectura se rechacen sin permiso;
- que una falla no deje filas.

`tests/unit/test_empresa_page_org_structure.py` usa la composición real de Configuración.

En una copia de la base real:
- la migración va de 332 a 351;
- respalda «Principal» (`PRI`, el código de su perfil) y «Corregidora» (`CORREGIDORA`) con 11 capacidades
  cada una;
- `foreign_key_check` queda vacío;
- el arranque completo pasa sus seis etapas.

`tests/unit/test_configuracion_ui_workspace.py` ya fallaba antes de este cambio (29 pruebas, todas las
páginas). Su presentador falso no tiene sesión, y la política fail-closed de la auditoría de permisos
rechaza `load_page` con «Operación sin usuario autenticado». No se tocó.
