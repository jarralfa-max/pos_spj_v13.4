# TRF-16 — Sugerencias de redistribución

## Algoritmo migrado

- `TransferSuggestionService` conserva Días de Suministro (DOS), mediana objetivo y Coeficiente de Variación (CV) poblacional.
- Todos los cálculos usan `Decimal`; no existen `float`, infinito artificial ni redondeo previo a persistencia.
- La cantidad propuesta respeta exceso sobre DOS objetivo, déficit destino, stock mínimo, safety stock y fracción máxima configurable del origen.
- El modelo de suministro descuenta reservas y transferencias salientes, suma tránsito y órdenes entrantes, respeta mínimos/máximos y prioriza excedentes próximos a vencer.
- La demanda combina histórico y Forecast mediante un peso configurable.
- Un origen sin demanda usa un DOS finito configurable, nunca infinito ni un sentinel hardcodeado.

## Configuración

`TransferSuggestionSettingsQueryService` aporta, por alcance y tipo de transferencia:

- DOS mínimo;
- multiplicador y piso del DOS objetivo;
- umbral CV;
- cantidad y score mínimos;
- fracción máxima del stock origen;
- peso de Forecast;
- ventana histórica y DOS configurado para demanda cero;
- límite de resultados.

No existen defaults funcionales en UI ni en el servicio.

## Integración Forecast

- `ForecastTransferSuggestionRequestedHandler` consume `TRANSFER_SUGGESTION_REQUESTED`.
- La sugerencia queda `PROPOSED`; nunca crea, aprueba, reserva ni ejecuta una transferencia.
- Cada sugerencia usa UUIDv7, conserva `operation_id`, fuente y referencia de Forecast.
- Se publica `TRANSFER_SUGGESTION_CREATED` post-commit mediante el colector canónico.
