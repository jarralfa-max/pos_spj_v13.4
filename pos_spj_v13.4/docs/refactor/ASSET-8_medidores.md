# ASSET-8 — Medidores (Activos / EAM)

Ejecutado: 2026-09-02. §39 del prompt maestro.

## Qué se construyó

`backend/domain/assets/entities/asset_meter.py` — `AssetMeter` (medidor adjunto a un activo: horas, kilómetros, ciclos, energía o personalizado). Mantiene `current_reading` (Decimal) como acumulado vigente. `advance_to(new_reading)` es la única forma de avanzarlo — guarda que la nueva lectura no sea menor que la actual (`MeterReadingInvalidError`) y rechaza `float` explícitamente.

`backend/domain/assets/entities/asset_meter_reading.py` — `AssetMeterReading` (una lectura puntual, con `recorded_by`/`operation_id`/`reading_at`). Es el registro histórico; `AssetMeter.current_reading` es el snapshot vigente que una fase de aplicación posterior mantendrá sincronizado al grabar cada `AssetMeterReading`.

Nuevo enum: `AssetMeterType` (HOURS/KILOMETERS/CYCLES/ENERGY/CUSTOM). Excepciones: `AssetMeterNotFoundError`, `MeterReadingInvalidError`. Eventos: `ASSET_METER_REGISTERED`, `ASSET_METER_READING_RECORDED` (el prompt maestro no enumera eventos de medidores en §87; se agregaron siguiendo el mismo criterio usado en ASSET-5/6 — la §39 sí describe la capacidad "puede disparar mantenimiento preventivo", que necesita un evento para engancharse a `MaintenancePlan` con `frequency_type=METER_BASED`). Ports: `AssetMeterRepositoryPort`, `AssetMeterReadingRepositoryPort`.

## Decisión de diseño: sin reseteo de medidor todavía

`MeterReadingInvalidError` documenta explícitamente que un medidor reemplazado físicamente (que reinicia a 0) es un caso real pero no modelado en esta fase — un "reset" explícito de medidor queda para cuando la capa de aplicación lo necesite, en vez de debilitar el guard monotónico ahora mismo.

## Tests

`tests/unit/assets/test_asset_meter.py` — lectura inicial en cero, avanzar a lectura mayor, avanzar a lectura menor falla, `float` rechazado, creación de `AssetMeterReading` (negativa falla, float falla).

## Siguiente fase

ASSET-9 — Documentación, garantías y seguros.
