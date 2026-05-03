You are working on a complex ERP:

https://github.com/jarralfa-max/pos_spj_v13.4

This system already contains:

- legacy architecture (core/, services/, modulos/)
- partial clean architecture (domain/, application/)
- event system (core/events, sync)
- API (FastAPI)
- WebApp
- WhatsApp microservice

---

CRITICAL:

This is NOT a greenfield project.

You MUST:

- refactor progressively
- NOT break existing functionality
- NOT delete blindly
- migrate logic step by step

---

GOAL:

Unify architecture into:

/domain
/application
/infrastructure
/ui

---

STRICT RULES:

- NO business logic in modulos/
- NO business logic in repositories/
- core/services must be decomposed
- domain must be source of truth
- events must drive state changes