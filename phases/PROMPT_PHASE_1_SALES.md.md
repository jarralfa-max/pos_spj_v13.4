You are refactoring a large ERP/POS system.

Your goal is to migrate the SALES flow to event-driven architecture WITHOUT breaking tests.

---

# 🧠 SOURCE OF TRUTH

Tests are the source of truth.

You MUST:
- Read all tests related to sales:
  - test_sales.py
  - test_flujo_completo.py
  - test_inventory.py
  - test_fase0_ventas_*
- Infer expected behavior from them

DO NOT assume current implementation is correct.

---

# 🎯 GOAL

Decouple sales from:
- inventory
- finance

---

# 🔍 STEP 1 — ANALYSIS

1. Locate:
   - sales_service.py
   - ventas_facade.py
   - unified_sales_service.py

2. Detect:
   - direct calls to inventory_service
   - direct calls to finance_service
   - DB writes related to stock or finance

List all findings before modifying code.

---

# 🧩 STEP 2 — EVENT MODEL

Create:

core/events/event_factory.py

Add:

SALE_CREATED event with payload:
- sale_id
- items
- total
- branch_id
- payments

---

# 🧩 STEP 3 — REFACTOR SALES

Modify sales flow:

- REMOVE direct inventory/finance calls
- EMIT event via event_bus

DO NOT change:
- method signatures
- return values

---

# 🧩 STEP 4 — HANDLERS

Create:

core/events/handlers/inventory_handler.py  
core/events/handlers/finance_handler.py  

Handlers must:
- replicate EXACT previous behavior
- use repositories/services internally

---

# 🧩 STEP 5 — WIRING

Update:

core/events/wiring.py

---

# 🧪 STEP 6 — VALIDATION

Run tests mentally:

If a test expects:
- stock reduction → ensure handler does it
- financial record → ensure handler does it

---

# ⚠️ RULES

- DO NOT duplicate logic
- MOVE logic, don’t rewrite
- DO NOT break tests

---

# 📦 OUTPUT

1. Files modified
2. Code diffs
3. Explanation of equivalence with previous behavior