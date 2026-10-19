# Diseño integral SPJ ERP/POS

**Base revisada:** `claude/erp-financial-bounded-context-uqxz6b` @ `32cfbf278e9fdc600ae8953be842626a455c3b4a` (17 de octubre de 2026, UTC). **Enfoque:** especificación integral de un producto que comienza su desarrollo. El código de esa revisión aporta capacidades, nombres y riesgos; no se asume que cada flujo ya opera extremo a extremo. Investigación externa: [benchmark](BENCHMARK.md).

| Documento | Propósito |
| --- | --- |
| [PRD](PRD.md) | Problema, usuarios, alcance y criterios de aceptación. |
| [TRD](TRD.md) | Arquitectura, contratos, seguridad, integraciones y despliegue. |
| [UI/UX Design](UI_UX_DESIGN.md) | Navegación, componentes, estados y comportamiento de pantallas. |
| [Appflow](APPFLOW.md) | Recorridos de compra, transformación, venta y excepciones. |
| [Backend schema](BACKEND_SCHEMA.md) | Fuentes de verdad, esquema existente y relaciones objetivo. |
| [Plano maestro](MASTER_BLUEPRINT.md) | Arquitectura y límites de la plataforma completa. |
| [Catálogo de módulos](MODULE_CATALOG.md) | Funciones de todos los módulos y superficies. |
| [Aplicaciones web](WEB_APPS.md) | CRM, Compras, Finanzas y BI web. |
| [Microservicio WhatsApp](WHATSAPP_SERVICE.md) | Canal Meta, operación, credenciales, flujos y métricas. |
| [Benchmark](BENCHMARK.md) | Comparación con documentación oficial de productos similares. |
| [Plan de entrega](DELIVERY_PLAN.md) | Secuencia, dependencias y criterios verificables. |

**Convención:** «Existe» significa implementación identificable en el commit; «pendiente de verificar» exige una prueba integrada; «propuesto» es contrato de diseño nuevo. La presencia de una clase o tabla no demuestra disponibilidad en producción. La referencia local abarca `backend/`, `frontend/`, `migrations/`, `installer/` y el microservicio raíz `whatsapp_service/`. El objetivo incluye POS/ERP de escritorio, PWA logística y delivery, web CRM/Compras/Finanzas/BI y WhatsApp. El benchmark de mercado está citado en su documento; la arquitectura propuesta es una inferencia propia.
