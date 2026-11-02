# SDLC-WA-027 — Audio, video, sticker y contactos se descartan sin respuesta; imagen y documento sin pipeline de media seguro

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §62, §63, §15 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-019

## Problema
Los tipos no declarados hacen fallar el parseo y el mensaje se descarta sin respuesta ni registro. Imagen y documento pasan pero sin extraer el id de media y terminan como intención desconocida. `download_media` devuelve bytes sin validar MIME, tamaño, hash ni nombre, y nadie lo llama. No existe `WhatsAppMediaReference`.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `whatsapp_service/models/message.py:12-20,67,108-109`; `webhook/whatsapp.py:110-112`
- `whatsapp_service/parser/intent_parser.py:74-75`
- `whatsapp_service/infrastructure/providers/meta_cloud_api/gateway.py:113-130`
- `whatsapp_service/domain/whatsapp/enums.py:85-98` — sin STICKER
- Prueba: `whatsapp_service/tests/test_meta_cloud_api_gateway.py::TestDownloadMedia::test_two_step_download` (solo transporte)

## Impacto
Clientes que mandan nota de voz o foto no reciben respuesta; riesgo de archivos maliciosos cuando se habilite media.

## Objetivo
- Todo tipo de mensaje se registra y recibe respuesta (aunque sea "no soportado").
- Media: descarga → validación MIME real, extensión, tamaño, hash, nombre seguro → almacenamiento → referencia; ejecutables y doble extensión bloqueados.

## Alcance
- **Incluye:** Parseo de tipos y pipeline de media.
- **No incluye:** Ubicación como dirección (SDLC-WA-032).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
—

## Preguntas abiertas
- Ninguna por ahora.
