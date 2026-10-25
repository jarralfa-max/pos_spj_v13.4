# 06 — Registro de riesgos de la migración

Gravedad: **Crítica** (pérdida o duplicación de dinero o datos) · **Alta** (bloquea el modelo) · **Media** ·
**Baja**.

| ID | Riesgo | Evidencia | Gravedad | Impacto | Mitigación |
|---|---|---|---|---|---|
| R-01 | **Atomicidad dependiente de la conexión.** Las 23 UoW nunca abren transacción; con el pool en autocommit (`connection.py:_new_connection`) un rollback no deshace nada | Prueba ejecutada sobre copia real: 3/3 filas sobreviven al rollback con `_new_connection`; 0/3 con la conexión del escritorio | **Crítica** | Un outbox «transaccional» escrito con la conexión equivocada publica eventos de cambios revertidos, o pierde eventos de cambios confirmados | Antes del Outbox: las UoW abren `BEGIN` / `SAVEPOINT` explícito, independiente del modo de conexión. Prueba de contrato por UoW con ambas conexiones |
| R-02 | **Claves foráneas desactivadas en la conexión del escritorio, salvo en el primer arranque** | `database_integrity_step.py` abre sin `PRAGMA foreign_keys` (medido: 0). Sólo las migraciones 016/026 lo activan, y sólo la vez que se ejecutan. En los arranques siguientes están marcadas como aplicadas y la conexión queda con FK OFF. El pool y la API sí las activan | Alta | La base local acepta huérfanos que PostgreSQL rechazará al ingerir → eventos en dead-letter | Activar `foreign_keys=ON` en la conexión del escritorio. `PRAGMA foreign_key_check` sobre la copia de la base real: **0 violaciones** (2026-10-23), así que activarlo hoy no rompe datos existentes |
| R-03 | **203 columnas de dinero o cantidad en `REAL`**, 32 en tablas de aspecto canónico | 03 | Crítica si se replican | Redondeo binario silencioso al convertir a `NUMERIC` | Replicar sólo tablas en decimal `TEXT`; migrar las 32 por expandir → copiar → contraer, o declararlas muertas |
| R-04 | **Tres motores de sincronización paralelos** | 01, 05 | Alta | Doble envío, cursores incompatibles, un cuarto motor | Consolidar en uno (CASH-19 como base) antes de cablear un transporte |
| R-05 | **WhatsApp abre el archivo SQLite del ERP** | `whatsapp_service/config/settings.py:52` | Alta | No funciona fuera de la estación; dos escritores WAL; credenciales locales | Modo `ERP_API_URL` obligatorio contra el central |
| R-06 | **Modelos duplicados** (heredado y canónico) para ventas, inventario, lotes y clientes | 03 | Alta | Replicar el heredado reproduce deuda en el central; BI mezcla fuentes | Replicar sólo el canónico; plan de retiro aparte |
| R-07 | **13 migraciones sin registrar**, con números duplicados (030, 032, 034, 048) | 03 | Media | Una instalación antigua pudo ejecutar el par «perdido»; el esquema real varía | Inventario de qué tablas crea cada una; comparar con bases de instalaciones reales antes de cualquier limpieza |
| R-08 | **Ronda FID 968e0bc sin cerrar** deja pruebas de Ventas en rojo | 00 | Media | No se puede certificar el slice de Ventas | Cerrarla antes del slice 8 |
| R-09 | **Relojes de estación.** Muchos defaults `datetime('now')` y hora local en payloads | 02 | Media | Orden causal falso si se usa la hora del dispositivo | Orden por secuencia de estación más versión de agregado; registrar también la hora del servidor |
| R-10 | **Trigger de inmutabilidad sólo en SQLite** (13) | 03 | Media | El central acepta UPDATE/DELETE sobre pagos o movimientos | Reproducir como reglas o triggers PG y revocar permisos de UPDATE/DELETE al rol de la API |
| R-11 | **Sin PostgreSQL ni Docker en la estación de desarrollo actual** | 00 | Media | Las pruebas de integración PG no pueden ejecutarse aquí todavía | Instalar PostgreSQL para Windows en desarrollo; CI con servicio PG |
| R-12 | **Credenciales en el cliente.** Hoy no las hay para un central | — | Crítica si se hace mal | Una caja robada expone la base central | Credencial de estación emitida por el central, revocable, sin acceso SQL; nunca `service_role` |
| R-13 | **Caída del central** | — | Alta | Ventas bloqueadas si algo exige el central | El POS no depende del central para vender; límites offline explícitos para cupones de uso único y crédito global (TRD §6) |
| R-14 | **Bandera de corte de Inventario** distinta por instalación | `canonical_cutover.py` | Media | Ledgers incompletos replicados | Exigir el corte activo como precondición para replicar inventario |
| R-15 | **Pruebas que importan paquetes borrados** (~20) | 00 | Baja | Ruido que esconde regresiones | Retirar o adaptar en la limpieza del slice correspondiente |

## Despliegue destructivo detenido

**Ninguno.** Esta fase no cambia código. La Fase 2 (persistencia) queda **bloqueada hasta cerrar R-01**: sin
atomicidad garantizada no hay Outbox transaccional (§6.2 del prompt).

## Estado (2026-10-24)

- **R-01 — CERRADO en código (Slice 0).** Una sola base, `TransactionalUnitOfWork`: `BEGIN` explícito en la
  UoW más externa y `SAVEPOINT` en las anidadas, sin depender del modo de la conexión. Lo prueban 93 pruebas
  de contrato con las dos conexiones reales. Detalle: `09_slice0_transactional_base.md`.
- **R-02 — CERRADO en código (Slice 0).** `ForeignKeyEnforcementStep` activa `foreign_keys=ON` después de
  migrar si `foreign_key_check` da 0; con huérfanos avisa y no bloquea el POS. Impacto medido: ninguna falla
  de código de producción con FK forzadas.
