# SDLC-WA-030 — Cantidades por WhatsApp sin gramos, paquete ni caja; la unidad que pide el cliente se ignora

- **Prioridad:** P3
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §35 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-021

## Problema
El parser reconoce kg y pieza; no gramos, paquete, caja ni unidad comercial. Si el cliente pide en una unidad distinta, el flujo usa la del producto sin convertir.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `whatsapp_service/parser/patterns.py:59-77`; `ai/catalog_entity_extractor.py:207-213`; `flows/pedido_flow.py:168`
- Prueba: ninguna

## Impacto
"500 g" puede registrarse como 500 kg o 500 piezas.

## Objetivo
- Unidades y conversiones las provee Productos; el canal solo extrae cantidad y unidad y pide confirmación.

## Alcance
- **Incluye:** Extracción y confirmación de unidades.
- **No incluye:** —

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
SALES-23 (KG agregados como 1 PZA, mismo tipo de defecto).

## Preguntas abiertas
- Ninguna por ahora.
