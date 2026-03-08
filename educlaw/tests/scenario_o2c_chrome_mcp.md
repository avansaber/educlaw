# Chrome MCP Scenario: Order to Cash

**Generated:** 2026-03-05
**Base URL:** http://localhost:3000
**Steps:** 8 (with UX verification)
**Full workflow:** 17 steps

## Workflow: Full selling cycle: customer → quote → SO → delivery → invoice → payment

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

## S01: Setup: ensure company and COA exist
**Via Telegram only** — `status` on `erpclaw-setup`

---

## S02: Create a test customer
**Skill:** `erpclaw-selling` | **Action:** `add-customer`

### Chrome MCP Steps

1. `navigate_page` → `http://localhost:3000/skills/erpclaw-selling`
2. `take_snapshot` → find tab "Actions" → `click` its UID
3. `take_snapshot` → find button "add-customer" → `click`
4. `take_snapshot` → find input "Customer Name" → `fill` with `Acme Corp`
5. `take_snapshot` → find input "Email" → `fill` with `ar@acme.com`
6. **Search+Select link field** "Company":
   - `take_snapshot` → find "Company" combobox/input
   - `fill` with `Test` (triggers search)
   - `wait_for` dropdown results
   - `take_snapshot` → find matching option → `click`
   - Note: Type 'Test' in Company search, select from dropdown
7. `take_snapshot` → find Submit/Save/Execute button → `click`
8. **Assert** `wait_for` text containing "created"
9. **Assert** `take_snapshot` contains: `Acme Corp`, `ar@acme.com`

---

## S03: Verify items exist for ordering
**Via Telegram only** — `list-items` on `erpclaw-inventory`

---

## S04: Create a quotation with 2 line items
**Skill:** `erpclaw-selling` | **Action:** `add-quotation`

### Chrome MCP Steps

10. `navigate_page` → `http://localhost:3000/skills/erpclaw-selling`
11. `take_snapshot` → find tab "Actions" → `click` its UID
12. `take_snapshot` → find button "add-quotation" → `click`
13. **Search+Select link field** "Customer":
   - `take_snapshot` → find "Customer" combobox/input
   - `fill` with `Acme` (triggers search)
   - `wait_for` dropdown results
   - `take_snapshot` → find matching option → `click`
   - Note: Search 'Acme' in customer dropdown, select 'Acme Corp'
14. `take_snapshot` → find input "Quotation Date" → `fill` with `2026-03-01`
15. **Add child table row #1** in "Items":
   - `take_snapshot` → find "Add Row" or "+" button → `click`
   - **Search+Select** "Item": `fill` search → `wait_for` dropdown → `click` result
   - `fill` "Qty" = `10`
   - `fill` "Rate" = `50.00`
16. **Add child table row #2** in "Items":
   - `take_snapshot` → find "Add Row" or "+" button → `click`
   - **Search+Select** "Item": `fill` search → `wait_for` dropdown → `click` result
   - `fill` "Qty" = `5`
   - `fill` "Rate" = `100.00`
17. **Assert** "Net Total" shows `1,000.00`
   > Verify net total = (10*50) + (5*100) = 1000.00
18. `take_snapshot` → find Submit/Save/Execute button → `click`
19. **Assert** `wait_for` text containing "Quotation"
20. **Assert** `take_snapshot` contains: `QTN-`, `Acme Corp`, `1,000`
21. **Assert** child table has 2 row(s)

---

## S05: Submit the quotation
**Skill:** `erpclaw-selling` | **Action:** `submit-quotation`

### Chrome MCP Steps

22. `navigate_page` → detail view for `quotation` `{quotation_id}`
23. **Assert** status badge shows `Draft`
24. `take_snapshot` → find action button "Submit" → `click`
25. **Assert** confirmation dialog appeared
26. `take_snapshot` → find Confirm button in dialog → `click`
27. **Assert** status badge shows `Open`

---

## S06: Convert quotation to sales order
**Skill:** `erpclaw-selling` | **Action:** `convert-quotation-to-so`

### Chrome MCP Steps

28. `navigate_page` → detail view for `quotation` `{quotation_id}`
29. `take_snapshot` → find action button "Convert to Sales Order" → `click`
30. **Assert** `wait_for` text containing "Sales Order"
31. **Assert** redirected to `sales_order` detail view
32. **Assert** `take_snapshot` contains: `SO-`, `Acme Corp`, `1,000`
33. **Assert** child table has 2 row(s)
34. **Assert** status badge shows `Draft`

---

## S07: Submit sales order
**Via Telegram only** — `submit-sales-order` on `erpclaw-selling`

---

## S08: Create delivery note from SO (full delivery)
**Skill:** `erpclaw-selling` | **Action:** `create-delivery-note`

### Chrome MCP Steps

35. `navigate_page` → detail view for `sales_order` `{sales_order_id}`
36. **Assert** status badge shows `Confirmed`
37. `take_snapshot` → find action button "Create Delivery Note" → `click`
38. **Assert** `wait_for` text containing "Delivery Note"
39. **Assert** `take_snapshot` contains: `DN-`
40. **Assert** child table has 2 row(s)
   > All items from SO should be copied to DN

---

## S09: Submit delivery note (posts SLE + COGS GL)
**Via Telegram only** — `submit-delivery-note` on `erpclaw-selling`

---

## S10: Verify SO shows 100% delivered
**Skill:** `erpclaw-selling` | **Action:** `get-sales-order`

### Chrome MCP Steps

41. `navigate_page` → detail view for `sales_order` `{sales_order_id}`
42. **Assert** "% Delivered" = `100`
43. **Assert** status badge shows `Fully Delivered`
44. **Assert** "Linked Delivery Notes" section shows 1 linked record(s)

---

## S11: Create sales invoice from SO
**Skill:** `erpclaw-selling` | **Action:** `create-sales-invoice`

### Chrome MCP Steps

45. `navigate_page` → detail view for `sales_order` `{sales_order_id}`
46. `take_snapshot` → find action button "Create Invoice" → `click`
47. **Assert** `wait_for` text containing "Invoice"
48. **Assert** `take_snapshot` contains: `SINV-`, `1,000`

---

## S12: Submit sales invoice (posts Revenue + AR + Tax GL)
**Via Telegram only** — `submit-sales-invoice` on `erpclaw-selling`

---

## S13: Verify SO shows 100% invoiced
**Via Telegram only** — `get-sales-order` on `erpclaw-selling`

---

## S14: Record payment against invoice
**Via Telegram only** — `add-payment-entry` on `erpclaw-payments`

---

## S15: Submit payment (posts Cash/Bank GL, clears AR)
**Via Telegram only** — `submit-payment-entry` on `erpclaw-payments`

---

## S16: Verify invoice shows Paid
**Skill:** `erpclaw-selling` | **Action:** `get-sales-invoice`

### Chrome MCP Steps

49. `navigate_page` → detail view for `sales_invoice` `{sales_invoice_id}`
50. **Assert** status badge shows `Paid`
51. **Assert** "Outstanding" = `0.00`

---

## S17: Verify GL balances (debit = credit for all entries)
**Via Telegram only** — `check-gl-integrity` on `erpclaw-gl`

---
