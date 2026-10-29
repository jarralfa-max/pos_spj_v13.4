---
description: "SDLC etapa 1 — Plan: triage de defectos, brechas contra la arquitectura objetivo o un intent puntual (uso: /sdlc-plan triage | /sdlc-plan arquitectura | /sdlc-plan <problema>)"
argument-hint: "triage [área] | arquitectura [ruta de requisitos] | <descripción del problema>"
---

Etapa **Plan** del SDLC de SPJ ERP. Argumento: `$ARGUMENTS`

Lee primero `pos_spj_v13.4/docs/sdlc/README.md` y `pos_spj_v13.4/docs/sdlc/BACKLOG.md`. En esta etapa **no modificas código**: solo lees, ejecutas pruebas y escribes en `docs/sdlc/`.

## Modo A — `triage` (barrido de toda la app)

Objetivo: convertir "todo lo que está mal" en un backlog priorizado de ítems pequeños, cada uno con evidencia.

1. **Línea base de pruebas.** Desde `pos_spj_v13.4/`, ejecuta los segmentos de `.github/workflows/ci-segmented.yml` en este orden y guarda el resumen (pasan/fallan/errores de colección) en `docs/sdlc/baseline/<fecha>.md`:
   `python -m compileall -q .` · `python -m pytest tests/architecture -q` · `python -m pytest tests/unit -q` · `python -m pytest tests/unit/security tests/integration/security -q` · `python -m pytest tests/integration -q`.
   Si un segmento no corre por dependencias faltantes, regístralo como hallazgo (`SDLC-CORE`) en lugar de instalar cosas al azar.
2. **Barrido por bounded context en paralelo.** Lanza subagentes `Explore` (uno por grupo) sobre `backend/`, `frontend/`, `modulos/`, `core/`, `migrations/`, `sync/`, `installer/`. Grupos sugeridos: (a) caja/ventas/crédito/finanzas, (b) inventario/transferencias/compras/producción/mermas, (c) sync/seguridad/permisos/sesiones/actualizador/instalador, (d) CRM/lealtad/pedidos/WhatsApp, (e) BI/UI/configuración. Pide a cada uno: defectos con ruta:línea, `NotImplementedError`/stubs/`TODO`, SQL en UI, duplicaciones de servicios o de fuente de verdad, IDs no UUIDv7 (ver `docs/skills/SPJ_REFACTOR_SKILL.md`), escrituras directas entre contextos, operaciones de dinero sin asiento balanceado. Solo conclusiones con evidencia, sin volcar archivos.
3. **Trabajo previo.** Lee `docs/refactor/work_queue.json` y los `*_validacion_final*`/`*_final_validation*` de `docs/refactor/` y `docs/audits/`. Un problema ya cubierto por un lote `DONE` solo entra si hay evidencia nueva de regresión; uno `IN_PROGRESS` se referencia, no se duplica.
4. **Consolidar.** Agrupa hallazgos que comparten causa raíz. Cada ítem debe poder resolverse en una rama con un PR revisable (si no, divídelo).
5. **Escribir.** Por cada ítem: fila en `BACKLOG.md` (etapa `intent-borrador`) y `docs/sdlc/items/<ID>/intent.md` desde `_templates/intent.md`. Prioridad: P0 = pérdida de dinero/datos, duplicados, seguridad o app que no arranca; P1 = flujo de negocio roto; P2 = deuda que bloquea arquitectura; P3 = resto. Nivel de riesgo según la tabla del README.
6. Si `$ARGUMENTS` trae un área (`triage CASH`), limita el barrido a esa área.

## Modo C — `arquitectura [ruta]` (brechas contra un documento de requisitos)

Objetivo: comparar la app real contra un documento de requisitos y convertir cada brecha en ítems. El modo `triage` encuentra defectos; este modo encuentra lo que **falta o no cumple** lo que pide el documento.

- Sin ruta: usa `pos_spj_v13.4/docs/sdlc/inputs/requisitos-arquitectura.md` y escribe la matriz en `docs/sdlc/arquitectura/matriz-brechas.md`.
- Con ruta (por ejemplo `docs/sdlc/inputs/mercado-pago.md` o `docs/sdlc/inputs/ui-ux.md`): usa ese documento y escribe la matriz en `docs/sdlc/arquitectura/matriz-<nombre del archivo>.md`. Si el documento pide entregables propios (por ejemplo `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`), esa matriz cumple ese papel: créala en la ruta que pide el documento y enlázala desde `docs/sdlc/arquitectura/`.
- Si el documento trae su propio orden de fases, respétalo como orden de dependencias de los ítems, pero cada fase se ejecuta como ítems del SDLC (intent → spec → plan → build → test → deploy), nunca como una corrida larga.

1. Lee completo el documento. Extrae cada requisito verificable (en el de arquitectura, secciones 2 a 15: arquitectura híbrida, roles/permisos, ámbitos, terminales, login entre sucursales, multiusuario, caja y turno compartidos, offline y servicio local, sincronización e idempotencia, PostgreSQL/FastAPI, auth offline, concurrencia, instalador/actualizador, seguridad/auditoría, pruebas de aceptación).
2. Para cada requisito, verifica el estado real en el código con subagentes `Explore` en paralelo (agrúpalos por sección). Busca en `backend/`, `core/`, `sync/`, `migrations/`, `installer/`, `frontend/`, `modulos/` y `tests/`. Pide ruta:línea como evidencia. No des por implementado algo solo porque existe un módulo, una abstracción, un documento o un stub.
3. Escribe la matriz con una fila por requisito: § · requisito · estado (`implementado y probado` · `parcial` · `documentado no implementado` · `defectuoso` · `duplicado` · `ausente`) · evidencia · prueba que lo cubre (o "ninguna").
4. Todo lo que no esté en `implementado y probado` se convierte en ítem. Agrupa por épica (una por sección del documento) y divide cada épica en ítems que quepan en un PR. ID con área `ARQ`, `PAY` (Mercado Pago), `UI` o el área del módulo (`SDLC-ARQ-PERM-001`, `SDLC-PAY-003`, `SDLC-UI-010`…). En el intent, `Origen: <documento> §N`, y en "Depende de" el orden lógico (por ejemplo, identidad de terminal antes que login entre sucursales; fuente canónica del turno antes que caja compartida).
5. Antes de crear un ítem, revisa si `BACKLOG.md` ya tiene uno del triage que cubra lo mismo; si sí, enlázalo en lugar de duplicarlo.
6. Prioridad: P0 si la brecha permite dinero o inventario duplicado, operar sin autorización o perder datos (idempotencia, turno duplicado, permisos solo en UI, sesión heredada); P1 si bloquea la operación multi-terminal o multi-sucursal; P2 lo demás estructural; P3 documentación.
7. Todas las decisiones de negocio que el documento deja abiertas (precedencia rol/usuario, vigencia de permisos offline, máquina anfitriona del servicio local) van a "Preguntas abiertas" del backlog.

## Modo B — un problema puntual

1. Actúa como analista: si la descripción es ambigua, hazme hasta 3 preguntas concretas antes de escribir.
2. Reproduce o localiza el problema en el código y en las pruebas; reúne evidencia.
3. Busca en `BACKLOG.md`, `work_queue.json` y `docs/refactor/` si ya existe; si existe, actualiza ese ítem en vez de crear otro.
4. Crea `docs/sdlc/items/<ID>/intent.md` y su fila en el backlog.

## Al terminar

- Resume: cuántos ítems por prioridad y nivel, los 10 primeros, y las preguntas abiertas.
- Haz commit solo de `docs/sdlc/` con mensaje `sdlc(plan): …`.
- Detente. El siguiente paso es que yo apruebe intents (cambiando su estado a `intent-aprobado`) y ejecute `/sdlc-design <ID>`.
