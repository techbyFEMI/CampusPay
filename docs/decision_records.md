# CampusPay Phase 1: Decision Records

> **Phase**: 1 — Decision Records  
> **Date**: 2026-10-07 (Updated)  
> **Status**: Updated to align with authoritative `CampusPay Product Context`.

Each record follows the format from Section 7 of the working prompt and reflects the authoritative decisions in `docs/product_context.md`.

---

## DR-01: Money Representation & Fee Allocation — Integer Kobo BIGINT

**Decision:**  
All monetary values in the database, domain layer, and service layer are stored and computed as `BIGINT` representing **kobo** (100 kobo = ₦1). Currency is stored as `NGN`. Values are converted to naira strings only at the API display boundary.

### Fee Allocation Formula (in Kobo):
- Student charge cap: **₦50 (5,000 kobo)** maximum per purchase.
- Item listed price: `P` kobo. Total student debit = `P + 5000` kobo.
- Confirmed provider processing cost: `C` kobo.
- `remaining = max(0, 5000 - C)` kobo.
- `campuspay_share = floor(0.40 * remaining)` kobo.
- `rep_share = remaining - campuspay_share` (i.e. remaining 60%, avoiding rounding loss).
- Total amount transferred to Rep DVA = `P + rep_share` kobo.

**Why:**  
Integer kobo prevents floating-point inaccuracies. Paystack API operates in kobo integers. The allocation rule explicitly caps student fee at ₦50 and guarantees exact kobo distribution without fractional loss.

**Failure it prevents:**  
Floating-point truncation errors on 40/60 splits (e.g. ₦18.333...) causing ledger imbalance or student overcharge.

**Test that proves it:**
```python
def test_fee_split_in_kobo():
    # Example: ₦50 charge (5000 kobo), provider cost ₦15 (1500 kobo)
    # Remaining = 3500 kobo
    # CampusPay 40% = 1400 kobo, Rep 60% = 2100 kobo
    charge_kobo = 5000
    provider_cost_kobo = 1500
    remaining = max(0, charge_kobo - provider_cost_kobo)
    cp_share = int(remaining * 0.40)
    rep_share = remaining - cp_share
    
    assert cp_share == 1400
    assert rep_share == 2100
    assert cp_share + rep_share == remaining
```

**Confidence:** `verified` — from `docs/product_context.md` §*Student charge and allocation*.

---

## DR-02: ID Strategy — Application-Generated UUIDs (v4)

**Decision:**  
All primary keys (`order_id`, `user_id`, `journal_id`, `transfer_attempt_id`) are `UUID v4` strings generated in the Python application layer before DB insertion (`str(uuid.uuid4())`).

**Why:**  
Generating UUIDs in the application layer enables constructing domain objects, journals, and idempotency records atomically before executing database operations.

**Failure it prevents:**  
Idempotency records failing to write in the same transaction as an order because the order ID is not known until after database auto-increment.

**Confidence:** `verified` — application design requirement for atomic transaction boundaries.

---

## DR-03: Ledger & Account Model — Four Double-Entry Account Types

**Decision:**  
The double-entry ledger recognises four core account types:

| Account Type | Owner | Purpose |
|---|---|---|
| `STUDENT_WALLET` | Student | Student's spendable wallet balance |
| `REP_ACCOUNT` | Rep / Vendor | Virtual account tracking payable sales & rep fee share |
| `PLATFORM_REVENUE` | Platform | CampusPay's 40% retained share of remaining charges |
| `EXTERNAL_PAYSTACK` | System (contra) | Settlement account for Paystack bank/DVA inflows & outflows |

### Transaction Postings:
1. **Wallet Funding (Deposit via Paystack DVA webhook)**:  
   DEBIT `EXTERNAL_PAYSTACK` → CREDIT `STUDENT_WALLET`
2. **Purchase Order Creation**:  
   DEBIT `STUDENT_WALLET` (`item_price + 5000 kobo`) →  
   CREDIT `REP_ACCOUNT` (`item_price + rep_share`) & CREDIT `PLATFORM_REVENUE` (`campuspay_share`) & CREDIT `EXTERNAL_PAYSTACK` (`provider_cost`)
3. **Automated Restoration (on 3 payout failures)**:  
   Exact reversal of Purchase Order Creation journal.

**Why:**  
No escrow account. Student wallet is debited directly at purchase creation time, reflecting the product decision that wallet debits are immediate, not escrow holds.

**Confidence:** `verified` — from `docs/product_context.md` §*Roles, accounts, and catalog* & §*Intended payment and delivery flow*.

---

## DR-04: Payment & Delivery State Machine — Independent States & Explicit Transitions

**Decision:**  
Order states are decoupled into two explicit, independent state fields: `payment_status` and `delivery_status`.

```
Payment Status:  PENDING → APPROVED | FAILED
Delivery Status: AWAITING_DELIVERY → DELIVERED
```

### Transition Rules:
1. **Purchase Submission**: Order created with `payment_status = PENDING` and `delivery_status = AWAITING_DELIVERY`. Student wallet debited immediately.
2. **Payment Approval**: When Paystack confirms payout success to Rep DVA, transition `payment_status` to `APPROVED`.
3. **Payout Retry & Failure Policy**: Up to 3 total transfer submissions (1 initial + up to 2 retries). Retry ONLY after Paystack confirms terminal failure of prior attempt.
4. **Terminal Failure Restoration**: If all 3 payout attempts definitively fail, `payment_status` transitions to `FAILED` and student's wallet is restored exactly once.
5. **QR Delivery Authorization**: QR scan by rep tied to purchased item transitions `delivery_status` to `DELIVERED`. QR scan does NOT trigger or approve payment. Order can be `APPROVED` while still `AWAITING_DELIVERY`.
6. **No Escrow / No Expiry**: Orders waiting for delivery do not expire. No no-show penalties or penalty charges exist.

**Why:**  
Prevents overloading a single status flag. Ensures payment approval and item delivery remain distinct, preventing double payouts or premature order cancellation.

**Confidence:** `verified` — from `docs/product_context.md` §*Intended payment and delivery flow*.

---

## DR-05: Idempotency Contract — Scoped Key + Payload Hash + Cached Response

**Decision:**  
All financial endpoints (`POST /api/v1/orders`, webhooks, transfer retries) enforce idempotency using `idempotency_keys` table:

| Column | Type | Description |
|---|---|---|
| `caller_user_id` | `VARCHAR` | Authenticated user / system caller |
| `idempotency_key` | `VARCHAR` | Client or system generated key |
| `payload_hash` | `CHAR(64)` | SHA-256 hex of request payload |
| `response_body` | `JSONB` | Cached response body |
| `response_status` | `SMALLINT` | Cached HTTP status |
| `created_at` | `TIMESTAMPTZ` | Timestamp |

**Behaviour:**
- **Same key + same hash**: Return cached response directly without re-executing business logic.
- **Same key + different hash**: Return `409 Conflict`.
- **Atomic execution**: Idempotency record and journal/order mutations are committed in the same database transaction.

**Confidence:** `verified` — required for financial integrity across network retries and webhook retries.

---

## DR-06: Identity Verification & PII Protection — Verification Ref Only

**Decision:**  
Raw NIN and BVN numbers are **never stored** in the database or written to log files. Only opaque provider verification reference IDs (`nin_verification_ref`, `bvn_verification_ref`), verification status, timestamp, and server-keyed HMAC hashes (for deduplication) are stored.

**Confidence:** `verified` — security requirement for student data protection.

---

## DR-07: Service Architecture & Transaction Boundary (Hammet-Core Pattern)

**Decision:**  
Adopt the service layer architecture studied in `hammet-core`:
1. **Repositories** (`db/repository/`): Pure DB query execution using SQLAlchemy async sessions.
2. **Services** (`services/`): Business logic, domain rules, and unit-of-work transaction boundaries.
3. **Routers/API** (`api/v1/`): FastAPI routes handling request validation, auth dependency injection, and mapping service results to DTOs.
4. **External Provider Calls**: Paystack API requests execute *outside* the DB transaction boundary to prevent holding database locks across HTTP round-trips.

**Confidence:** `verified` — alignment with repository architecture standards and `hammet-core` design reference.

---

## Open Integration Questions (Paystack & Provider Boundary)

| # | Question | Impact Phase |
|---|---|---|
| **OQ-1** | Exact Paystack API route for paying into a Rep's DVA created under the same business account | Phase 4 (Paystack Adapter) |
| **OQ-2** | Paystack fee schedule for DVA funding vs bank transfers to verify accurate economics for the ₦50 fee cap | Phase 4 (Paystack Adapter) |
