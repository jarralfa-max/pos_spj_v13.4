# SDLC-WA-026 — Horarios del canal sin zona horaria, abiertos ante error y con aviso de cerrado que no detiene el pedido

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §64 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-013

## Problema
Se lee una ventana por sucursal y día con `datetime.now()` sin zona; sin configuración o ante error la sucursal cuenta como abierta; no hay feriados ni horarios de agentes; el próximo horario empieza a buscar mañana. Solo se revisa al elegir categoría, con sucursal `or 1`, y tras avisar que está cerrado el flujo sigue. La política de horario del flujo de pedido nunca corre porque el flujo se construye sin horarios.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `whatsapp_service/config/schedules.py:24,33,39,43,57-58`
- `whatsapp_service/router/message_router.py:143-147`; `flows/pedido_flow.py:355-369`
- Canon sin uso: `whatsapp_service/domain/whatsapp/entities/channel_number.py:30,44` (zona y locale)
- Prueba: ninguna (las del router usan `DummySchedules`)

## Impacto
Pedidos aceptados fuera de horario sin decirlo; horas equivocadas en el servidor central.

## Objetivo
- Horarios con zona de la sucursal, feriados y agentes; error = desconocido, no abierto.
- Fuera de horario: confirmar recepción, mostrar horario, ofrecer pedido programado o handoff pendiente.

## Alcance
- **Incluye:** Política de horarios del canal.
- **No incluye:** —

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
—

## Preguntas abiertas
- ¿Los horarios de sucursal son del ERP (Configuración/Sucursales) y el canal solo los consulta, o el canal conserva `wa_horarios_sucursal`?
