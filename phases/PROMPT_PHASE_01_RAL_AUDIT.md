Read PROMPT_PHASE_00_RAL_CONTEX.md

Execute DEEP AUDIT

---

Analyze:

1. core/services → classify each service:
   - domain logic
   - application logic
   - infrastructure

2. modulos/ → detect hidden business logic

3. repositories/ → detect logic violations

4. duplicated systems:
   - domain vs core/domain
   - services vs application

---

Output:

- list of services to split
- list of duplicated logic
- list of critical violations

- PRIORITIZED refactor plan:
  (what to fix first to avoid breaking system)