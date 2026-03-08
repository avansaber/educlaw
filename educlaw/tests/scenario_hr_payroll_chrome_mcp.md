# Chrome MCP Scenario: HR and Payroll

**Generated:** 2026-03-05
**Base URL:** http://localhost:3000
**Steps:** 0 (with UX verification)
**Full workflow:** 6 steps

## Workflow: Employee onboarding → attendance → leave → expense → payroll → GL

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

## H01: Add employee
**Via Telegram only** — `add-employee` on `erpclaw-hr`

---

## H02: Add salary structure
**Via Telegram only** — `add-salary-structure` on `erpclaw-payroll`

---

## H03: Assign salary structure to employee
**Via Telegram only** — `add-salary-structure-assignment` on `erpclaw-payroll`

---

## H04: Create payroll entry for March 2026
**Via Telegram only** — `create-payroll-entry` on `erpclaw-payroll`

---

## H05: Submit payroll (posts salary GL)
**Via Telegram only** — `submit-payroll-entry` on `erpclaw-payroll`

---

## H06: Verify GL balanced
**Via Telegram only** — `check-gl-integrity` on `erpclaw-gl`

---
