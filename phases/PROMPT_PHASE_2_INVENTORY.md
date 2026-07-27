Refactor inventory system into a movement-based ledger.

---

# 🧠 SOURCE OF TRUTH

Tests:
- test_inventory.py
- test_fase4_stock_validation.py
- test_fase_g_inventory_integrity.py

---

# 🎯 GOAL

ALL inventory changes must go through:

apply_movement()

---

# 🔍 STEP 1 — DETECT BAD PATTERNS

Search for:

- stock +=
- stock -=
- update stock directly in SQL

List all locations.

---

# 🧩 STEP 2 — DEFINE MODEL

Standard movement:

{
  product_id,
  quantity,
  movement_type,
  reference_id,
  branch_id,
  timestamp
}

---

# 🧩 STEP 3 — REFACTOR

Replace ALL direct mutations with:

apply_movement()

---

# 🧩 STEP 4 — EVENT INTEGRATION

Ensure handlers use:

INVENTORY_MOVEMENT

---

# 🧪 STEP 5 — VALIDATION

Tests must still pass:

- stock consistency
- no negative stock errors
- concurrency tests

---

# ⚠️ RULES

- DO NOT change DB schema unless necessary
- DO NOT break existing queries