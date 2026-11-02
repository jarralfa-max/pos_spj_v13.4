# SDLC-WA-033 — Fidelidad por WhatsApp: SQL directo a loyalty_snapshots y ningún flujo la ofrece

- **Prioridad:** P3
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §43 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-003

## Problema
El cliente de lealtad del canal consulta `loyalty_snapshots` con SQL y evita a propósito la consulta del contexto. Ningún flujo vivo muestra puntos, nivel, tarjeta digital, QR, cupones ni sorteos.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `whatsapp_service/infrastructure/erp_clients/loyalty_client.py:34-37`
- Dueños sin uso: `backend/application/loyalty/queries/customer_summary_query.py:37`; `loyalty_cards/use_cases/digital_card_use_cases.py:94`; `commercial_instruments/use_cases/coupon_use_cases.py:125`
- Pruebas: `whatsapp_service/tests/test_loyalty_client.py`, `test_loyalty_service.py`

## Impacto
El cliente no puede consultar puntos ni tarjeta por WhatsApp.

## Objetivo
- Resumen, tarjeta digital, cupones y participaciones vía consultas de Loyalty; el canal no calcula ni emite instrumentos.

## Alcance
- **Incluye:** Consultas de lealtad desde el canal.
- **No incluye:** Canje de puntos por WhatsApp (recortado en WA-15).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
LOY-29 (memoria); WA-15.

## Preguntas abiertas
- Ninguna por ahora.
