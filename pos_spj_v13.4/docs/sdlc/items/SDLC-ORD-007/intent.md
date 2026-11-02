# SDLC-ORD-007 — PWA de repartidor: sin ubicación en ruta y evidencia de entrega siempre vacía

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/refactor/ORD-30_validacion_final.md` → "Pendiente" §4 (endpoint de ubicación GPS en la PWA, ORD-25), re-verificado en código (`/sdlc-plan` Modo B, 2026-10-31)
- **Estado:** borrador
- **Depende de:** —

## Problema
La PWA de repartidor no tiene forma de informar la ubicación durante la ruta. La API tampoco tiene un endpoint para eso. Además, al registrar un intento de entrega, la PWA manda siempre `latitude`, `longitude`, `signatureReference`, `photoReference` en `null` y `pinVerified=false`, aunque la API y el dominio (`DeliveryEvidence`, ORD-18) ya aceptan esos datos. Ninguna entrega tiene prueba de dónde ni a quién se entregó, más allá del nombre que teclea el repartidor.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Verificado directamente el 2026-10-31 sobre `ed026f7b`.

- `frontend/web/delivery/app.js:185-194`: `openAttemptForm` envía `signatureReference: null, photoReference: null, pinVerified: false, latitude: null, longitude: null`. El nombre de quien recibe se pide con `window.prompt`.
- Grep de `geoloc` en `frontend/web/delivery/`: cero resultados. La PWA nunca llama a `navigator.geolocation`.
- `backend/api/routers/driver_logistics.py:77-148`: rutas `jobs`, `assignments/*`, `dispatch`, `depart`, `arrive`, `attempts`, `cash-collections/*/record`. No hay ruta de ubicación. La de `attempts` (`:134-145`) sí acepta `latitude`/`longitude`.
- Grep de `driver_location|DriverLocation|record_location|track_location` en `backend/`: cero resultados.
- La pantalla de escritorio "Seguimiento" (`frontend/desktop/modules/orders_delivery/orders_delivery_routes.py:45,187`) muestra un registro por estado, sin posición.
- La PWA nunca se probó en un navegador o dispositivo real (ORD-30 §5). Eso queda en SDLC-ORD-009.

## Impacto
Gerente y sucursal no pueden ver dónde va un pedido ni demostrar una entrega en caso de disputa. El repartidor no tiene firma, foto ni PIN para respaldar la entrega o el cobro en efectivo.

## Objetivo
- La PWA captura la ubicación en el intento de entrega (con permiso del usuario y degradando sin señal) y la API la persiste.
- Hay un endpoint de ubicación en ruta, idempotente, con frecuencia y retención definidas, que respeta la cola offline de la PWA (`sync.js`).
- La PWA puede adjuntar al menos una de estas evidencias: PIN de entrega, foto o firma, según lo que decida el responsable.
- Hay pruebas de API para ubicación y evidencia y una prueba del armado del cuerpo en la PWA.

## Alcance
- **Incluye:** Captura en la PWA, endpoint de ubicación, persistencia de la evidencia y pruebas.
- **No incluye:** Mapa en vivo en escritorio (ítem posterior si se pide) ni la validación manual en dispositivo (SDLC-ORD-009).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Coordenadas como `REAL` solo por ser dato geográfico (excepción ya documentada en ORD-30, auditoría Decimal).

## Trabajo previo relacionado
ORD-18 (`DeliveryEvidence`), ORD-25 (API + PWA); LOG-INT 2026-10-17 (PWA con jsQR y HTTPS autofirmado, memoria).

## Preguntas abiertas
- ¿Qué evidencia exige el negocio en cada entrega: PIN, foto, firma, o solo en pedidos cobrados en efectivo?
- ¿Se rastrea la posición del repartidor durante toda la ruta, o solo se registra al llegar o entregar? Esto afecta privacidad, batería y retención.
