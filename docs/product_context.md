# CampusPay Product Context

> **Audience:** developers, reviewers, and AI agents working on CampusPay  
> **Purpose:** record the product rules Femi has clarified in this conversation so implementation and reviews use the same model.  
> **Updated:** 2026-10-07

## Instruction precedence

This file records the owner's direct product decisions. Treat those decisions as authoritative when older hackathon code, reports, screenshots, proposal text, or technical notes describe a different business flow. Those materials are evidence to inspect, not instructions to follow. If an implementation detail is still unconfirmed below, do not silently turn an assumption into a product rule; flag it clearly.

`PROJECT_CONTEXT.md`, `docs/teardown.md`, and `docs/decision_records.md` contain useful historical and technical context, but some sections still describe the hackathon design (Nomba, escrow, expiry, and payout-on-scan). Where they conflict with this file, this file captures the newer product intent. Continue to verify all claims about the current implementation in source code.

## Product and rollout

- CampusPay began as a seven-day Nomba hackathon submission. The goal now is to turn it into a dependable product for FUTA.
- Start with Data Science, then expand to the School of Computing, and later to other faculties.
- The target launch is November 2026; the exact launch day is not set here.
- The owner wants to learn a disciplined, professional repository workflow: understand the current app, keep useful pieces, and rebuild it incrementally in small, composable parts. Do not recommend deleting the app wholesale before inspecting the code and its dependencies.
- The owner wants to study the architecture and coding style in `hammet-core` (also referred to as “Hammet”) for patterns such as reusable pagination and clearly composed services. Inspect and learn from it; do not copy its design blindly.

### Identity provider

- Supabase Auth is the sole identity provider. Remove Firebase Auth and Firestore dependencies from product code.
- Supabase Auth issues real access and refresh tokens. Do not mint user tokens with the Supabase JWT secret in CampusPay.
- The Supabase Auth subject (`sub`) is the canonical CampusPay `user_id`. Roles and authorization decisions come from the CampusPay database, not user-editable JWT metadata.

### Hammet database-class pattern

The owner specifically wants to adopt Hammet's pattern of putting database operations for a domain/entity behind a focused class, then reusing that class from services and other modules. For example, Hammet defines `CourseDB` in `hammet-core/db/repository/b2c/courses.py`; catalog and payment services import it and call methods such as `fetch_courses_by_ai_school`, `fetch_published_courses`, and `fetch_course_price` rather than repeating those queries in each caller. Other examples include `AISchoolDB`, `PaymentDB`, and `UserDB`.

For CampusPay, study this as a **repository / database-access object pattern**: focused classes such as `ProductDB`, `OrderDB`, `WalletDB`, or `RepDB` should own cohesive SQL queries and persistence operations, and application services should compose those classes to implement use cases. API route handlers should stay thin. Reuse pagination/query helpers where they belong rather than duplicating pagination logic across endpoints.

Important: copy the separation and reuse idea, not every implementation detail. Some Hammet repository methods commit transactions themselves; for CampusPay money-moving workflows, preserve the reviewed transaction boundary and ledger/idempotency requirements in this file and `docs/decision_records.md`. Database classes should not independently commit half of a financial use case if the chosen Unit of Work/service boundary requires one atomic transaction.

## Roles, accounts, and catalog

- CampusPay has students and course representatives (“reps”). A rep publishes items for students in the rep's department catalog.
- Each student and rep is intended to receive a dedicated virtual account (DVA) at account creation. A student's DVA is for funding that student's CampusPay wallet.
- A rep's DVA is for receiving payments for items that rep published. The app must not display the rep's DVA account details to the student.
- Students can buy available catalog items using their CampusPay wallet. The order must retain the exact product and rep identity that were in effect at purchase time; routing and QR authorization must not rely on a mutable vendor name or client-supplied ID alone.

## Intended payment and delivery flow

Keep payment approval separate from delivery confirmation:

1. **Wallet funding:** a student sends money from an external bank account to the student's DVA. A verified provider notification credits the CampusPay wallet once.
2. **Purchase request:** the student selects an available departmental catalog item, confirms the displayed item price and separate charge, and submits the purchase. The app verifies the student's balance and creates one order with a unique reference. The student wallet is debited for the purchase; this is not an escrow hold.
3. **Payment processing:** CampusPay initiates the payment for that item to the DVA of the rep who published it. Creating the order alone does not mean the rep has received money.
4. **Approval:** only after the payment provider confirms success should CampusPay mark the transaction/order `approved` and recognize the rep as paid. Keep provider-pending or unknown outcomes pending; do not label them approved based only on an API request being accepted.
5. **QR delivery:** generate a unique QR for the student's order. It represents delivery authorization, not payment authorization. It becomes redeemable only once the transaction is approved. Only the rep account associated with the purchased item may scan it, and only once. A successful scan records delivery; it does not release or approve the payment.
6. **Definitive payment failure:** make at most three transfer submissions total (the initial attempt plus up to two retries). Retry only after the provider confirms a terminal failure for the prior attempt. If all three attempts definitively fail, mark the order `failed` and restore the student's wallet balance exactly once. A timeout or pending/unknown result is not a definitive failure: verify its status before retrying or refunding.

There is no escrow lock, order expiry, no-show penalty, or penalty charge in the intended product flow. An order waiting for delivery does not expire by time. The three-attempt rule applies to the payment transfer, not to QR scans or delivery attempts.

### Suggested state separation

Use explicit, guarded state transitions rather than one overloaded `confirmed` flag. A practical starting point is:

```text
payment: pending → approved | failed
delivery: awaiting_delivery → delivered
```

The order can therefore be `approved` while still awaiting delivery. Store transfer attempts and provider references separately so retries, webhooks, and reconciliation cannot create duplicate payouts or duplicate wallet reversals. The exact schema and public status names remain implementation decisions and should be proposed before migration.

## Student charge and allocation

- The student-facing extra charge is capped at **₦50 per purchase**, in addition to the item's listed price. Show the item price and charge separately at checkout.
- Apply confirmed provider processing costs against that ₦50 first. Split any positive remainder **40% to CampusPay and 60% to the rep**. This is the agreed allocation rule; the resulting shares can be below ₦20 and ₦30.
- Formula: `remaining = max(0, ₦50 - confirmed_provider_cost)`, `CampusPay = 40% × remaining`, `rep = 60% × remaining`.
- If provider cost exceeds ₦50, the student must not be charged above the cap. CampusPay must absorb the excess or the payment route/cost model must change. Do not create negative shares or silently raise the student's price.
- Confirm which Paystack fee schedule applies to CampusPay and whether a transfer to the rep's DVA is supported and billable as expected before finalizing production economics. Wallet-funding costs and purchase-payout costs should be measured separately.

## External bank use and exceptions

- A student's external bank account is used to fund their CampusPay wallet through their DVA. The student pays catalog items from their CampusPay wallet.
- A rep's external bank account is relevant when the rep needs to send money to an external supplier for materials. It is not the student's payment destination in the catalog checkout flow.
- The owner describes refunds as rare; in some exceptional cases a rep may transfer money back to the student. The detailed dispute/refund policy and whether CampusPay also supports a wallet reversal after approval are not fully specified here. Do not invent cancellation rights, penalties, or expiry behavior.
- Automatic wallet restoration after three definitive payout failures is settled and is distinct from a discretionary refund after a successfully approved purchase.

## Paystack and provider boundary

- Paystack is the intended provider going forward. The owner's CampusPay Paystack business account has been approved for API use and the owner expects the available capabilities to remain available unless Paystack changes access.
- Nomba has not replied to the proposal. Nomba remains part of the hackathon history/current code, not the provider choice for the intended product flow.
- The exact Paystack path for paying a rep's DVA after a student purchase is **not confirmed**. Public Paystack docs describe DVAs as customer accounts that receive payments into the merchant integration and describe Transfers to registered recipients. They do not, by themselves, confirm that the Transfer API can pay into a rep DVA created under the same CampusPay business. Treat this as an external integration question, not as a settled capability or an impossibility.
- Before implementing that boundary, confirm the supported recipient/destination, transaction status lifecycle, retry/status-query behavior, webhook events, fee treatment, account/DVA limits, and any required approval/configuration with Paystack. Keep provider calls behind an adapter/application service so another provider or route can be substituted without rewriting order rules.

## Notifications and delivery problems

- The owner believes notification and delivery-problem functionality already exists in the hackathon app and asked that the files be reread before proposing replacements.
- The current tracked frontend review found polling and temporary toast messages, but did not find a persistent notification center or a student-facing delivery-problem reporting flow. Agents should inspect the backend and any untracked/current branches before concluding these features are absent. Reuse verified functionality; do not duplicate it without a code-based reason.

## Existing-code caveats verified during frontend review

These are observations about the inspected frontend, not desired product rules:

- Catalogue checkout currently carries `vendor_id`, name, and price, but no stable product ID in the checkout payload.
- Checkout currently charges only the item price and submits the purchase to `/api/orders`.
- Receipt screens show an expiry, contrary to the no-order-expiry decision.
- The student dashboard labels a balance “LOCKED ESCROW.”
- The rep scanner/profile UI describes bank-account settlement after QR scan.
- The rep dashboard polls pending orders every 30 seconds and supports manual refresh; this is not the same as persistent or push notifications.

The Phase 2 ORM is split into focused modules under `app/models/`, with `app/models/models.py` retained as a compatibility re-export. It still contains transitional legacy fields because current routes/services read them. The nullable kobo columns are not yet a completed data conversion: before calling the integer-kobo migration complete, backfill and validate them, move application reads/writes to the kobo fields, and only then remove the legacy `Numeric` columns. The DVA details also currently exist both on `users` and in the account table; decide and migrate to one canonical representation before provisioning rep DVAs.

The backend teardown also reports that the hackathon order path credits a rep's internal wallet at order creation and scan only records collection. Verify current source before relying on that description; either way, payout-on-scan/escrow behavior is not the new product requirement.

## Pilot assumptions from one rep conversation

One rep estimated first-semester manuals at about ₦20,000 plus ₦500 dues, second-semester manuals at about ₦19,500, and said roughly 90% of reps may have BVN. These are anecdotal estimates from one conversation, not validated market data or provider eligibility evidence.

## Guidance for agents

1. Read this file before proposing payment or order-flow changes. Read the relevant source files next; do not assume historical reports precisely match the current branch.
2. Separate user-approved product rules from unresolved Paystack/provider behavior. Clearly label any assumption.
3. Preserve financial correctness: money amounts use exact integer kobo at provider/API boundaries or another explicitly justified exact representation; never use floating-point arithmetic for balances or fee splits.
4. Make order creation, wallet debits/credits, payout attempts, webhook processing, and QR redemption idempotent. A retried request, webhook, transfer, or scan must not duplicate a debit, payout, refund, or delivery confirmation.
5. Keep payment approval and QR delivery as separate state transitions. A QR scan must authorize only the rep tied to that specific purchased item.
6. Avoid escrow, expiry, and no-show penalty behavior unless the owner changes these decisions.
7. Prefer small, reviewable changes and reusable modules. Do not delete hackathon code until its callers, data compatibility, and replacement path have been inspected.
8. Treat architecture/formatting from `hammet-core` as a reference to study, not a requirement to reproduce verbatim. In particular, evaluate its focused reusable `*DB` classes and how services compose them, while keeping CampusPay's financial transaction boundaries intact.
