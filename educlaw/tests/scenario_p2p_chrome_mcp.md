# Chrome MCP Scenario: Procure to Pay

**Generated:** 2026-03-05
**Base URL:** http://localhost:3000
**Steps:** 2 (with UX verification)
**Full workflow:** 10 steps

## Workflow: Full buying cycle: supplier → PO → receipt → invoice → payment

### Prerequisites
1. Webclaw server running at `http://localhost:3000`
2. Chrome DevTools MCP connected
3. Test company with COA and seed data
4. Test items in inventory

### What This Tests (UX-Critical Paths)
- **Link field search/select:** Customer dropdown, item search in child table
- **Child table interaction:** Add rows, fill item/qty/rate, verify computed amounts
- **Calculated fields:** Net total, tax, grand total update in real-time
- **Status transitions:** Draft → Submitted → Delivered → Invoiced → Paid
- **Detail view verification:** Correct data after each step
- **Cross-document navigation:** SO detail shows linked DNs and invoices

---

## P01: Create a test supplier
**Skill:** `erpclaw-buying` | **Action:** `add-supplier`

### Chrome MCP Steps

1. `navigate_page` → `http://localhost:3000/skills/erpclaw-buying`
2. `take_snapshot` → find tab "Actions" → `click` its UID
3. `take_snapshot` → find button "add-supplier" → `click`
4. `take_snapshot` → find input "Supplier Name" → `fill` with `Parts Unlimited`
5. `take_snapshot` → find input "Email" → `fill` with `ap@partsunlimited.com`
6. **Search+Select link field** "Company":
   - `take_snapshot` → find "Company" combobox/input
   - `fill` with `Test` (triggers search)
   - `wait_for` dropdown results
   - `take_snapshot` → find matching option → `click`
7. `take_snapshot` → find Submit/Save/Execute button → `click`
8. **Assert** `wait_for` text containing "created"

---

## P02: Create purchase order with 2 items
**Skill:** `erpclaw-buying` | **Action:** `add-purchase-order`

### Chrome MCP Steps

9. `navigate_page` → `http://localhost:3000/skills/erpclaw-buying`
10. `take_snapshot` → find tab "Actions" → `click` its UID
11. `take_snapshot` → find button "add-purchase-order" → `click`
12. **Search+Select link field** "Supplier":
   - `take_snapshot` → find "Supplier" combobox/input
   - `fill` with `Parts` (triggers search)
   - `wait_for` dropdown results
   - `take_snapshot` → find matching option → `click`
13. `take_snapshot` → find input "Order Date" → `fill` with `2026-03-01`
14. **Add child table row #1** in "Items":
   - `take_snapshot` → find "Add Row" or "+" button → `click`
   - **Search+Select** "Item": `fill` search → `wait_for` dropdown → `click` result
   - `fill` "Qty" = `20`
   - `fill` "Rate" = `25.00`
15. **Add child table row #2** in "Items":
   - `take_snapshot` → find "Add Row" or "+" button → `click`
   - **Search+Select** "Item": `fill` search → `wait_for` dropdown → `click` result
   - `fill` "Qty" = `10`
   - `fill` "Rate" = `80.00`
16. **Assert** "Net Total" shows `1,300.00`
17. `take_snapshot` → find Submit/Save/Execute button → `click`
18. **Assert** `wait_for` text containing "Purchase Order"

---

## P03: Submit purchase order
**Via Telegram only** — `submit-purchase-order` on `erpclaw-buying`

---

## P04: Create purchase receipt from PO
**Via Telegram only** — `create-purchase-receipt` on `erpclaw-buying`

---

## P05: Submit purchase receipt (posts SLE + stock-in GL)
**Via Telegram only** — `submit-purchase-receipt` on `erpclaw-buying`

---

## P06: Create purchase invoice from PO
**Via Telegram only** — `create-purchase-invoice` on `erpclaw-buying`

---

## P07: Submit purchase invoice (posts Expense + AP GL)
**Via Telegram only** — `submit-purchase-invoice` on `erpclaw-buying`

---

## P08: Record payment to supplier
**Via Telegram only** — `add-payment-entry` on `erpclaw-payments`

---

## P09: Submit payment (clears AP)
**Via Telegram only** — `submit-payment-entry` on `erpclaw-payments`

---

## P10: Verify GL balanced
**Via Telegram only** — `check-gl-integrity` on `erpclaw-gl`

---
