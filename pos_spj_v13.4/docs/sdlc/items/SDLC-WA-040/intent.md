# SDLC-WA-040 — Alertas internas por WhatsApp sin llamadores y sin política de severidad ni escalamiento

- **Prioridad:** P3
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §51 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-037

## Problema
El microservicio tiene alertas a personal en tres severidades sin llamadores. Del lado ERP, existencia mínima y transferencias mandan WhatsApp opcional junto a la bandeja interna, pero no hay política de escalamiento en ningún contexto ni alertas de dispositivo fuera de línea o pago fallido.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `whatsapp_service/notifications/alerts.py:17-87`
- `backend/application/inventory/notifications/stock_minimum_monitor.py:32,71,76`; `backend/domain/transfers/policies/transfer_notification_policy.py:6-43`
- Búsqueda de "escalat" en `backend/` sin resultados
- Prueba: ninguna para el camino de alertas por WhatsApp

## Impacto
Alertas críticas sin escalamiento; riesgo de usar WhatsApp como sustituto de la bandeja interna.

## Objetivo
- Política de severidad y escalamiento en Notificaciones; WhatsApp solo como canal complementario de la bandeja.

## Alcance
- **Incluye:** Política de alertas internas.
- **No incluye:** Destinatarios por rol de las alertas de existencia (SDLC-INV-008).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
SDLC-INV-008.

## Preguntas abiertas
- Ninguna por ahora.
