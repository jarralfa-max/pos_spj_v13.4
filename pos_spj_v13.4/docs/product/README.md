# Diseño integral SPJ ERP/POS

**Base revisada:** `claude/erp-financial-bounded-context-uqxz6b` @ `32cfbf278e9fdc600ae8953be842626a455c3b4a` (17 de octubre de 2026, UTC). **Estado:** especificación de producto y técnica; no certifica que cada flujo ya opere extremo a extremo.

| Documento | Propósito |
| --- | --- |
| [PRD](PRD.md) | Problema, usuarios, alcance y criterios de aceptación. |
| [TRD](TRD.md) | Arquitectura, contratos, seguridad, integraciones y despliegue. |
| [UI/UX Design](UI_UX_DESIGN.md) | Navegación, componentes, estados y comportamiento de pantallas. |
| [Appflow](APPFLOW.md) | Recorridos de compra, transformación, venta y excepciones. |
| [Backend schema](BACKEND_SCHEMA.md) | Fuentes de verdad, esquema existente y relaciones objetivo. |

**Convención:** «Existe» significa que hay implementación identificable en el commit indicado; «pendiente de verificar» exige una prueba integrada; «propuesto» es el contrato de diseño. La presencia de una clase o tabla no demuestra disponibilidad de una función en producción. Los documentos se basan en código y DDL de `backend/`, `frontend/`, `migrations/` e `installer/`, no en los reportes de auditoría existentes.
