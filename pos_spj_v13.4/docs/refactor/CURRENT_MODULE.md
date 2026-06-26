# Módulo actual

## Código

```text
VENTAS
```

## Nombre

Ventas.

## Estado

```text
DONE
```

## Iteración

```text
1
```

## Objetivo

Lote UUIDv7 obligatorio (REGLA CERO) sobre la cadena canónica de venta:
UI → `SalesApplicationService` / `ProcesarVentaUC` → `SalesService.execute_sale_result`
→ `_execute_sale_core` → repositorio de persistencia.

## Hallazgos abiertos

- Refactor arquitectónico completo de `modulos/ventas.py` (230 KB) — extracción de
  SQL/lógica restante de UI y SearchSelector/PhoneInput — queda fuera del lote
  UUID y se retomará en una pasada de UI dedicada.

## Tests requeridos

- `tests/unit/test_sales_application_refactor.py` (identidad UUID end-to-end del use case).
- `tests/integration/test_sqlite_sales_repository_uuid.py` (persistencia UUID-native, sin lastrowid).
- `tests/test_ventas_cleanup_regression.py` (contrato ticket_payload con venta_id UUID).

## Bloqueos

Ninguno registrado.

## Próxima acción

Seleccionar el siguiente módulo PENDING de la cola.
