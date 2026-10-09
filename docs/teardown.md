# CampusPay Phase 0: System Teardown & Inventory Audit

> **Document Status**: Complete Read-Only Audit  
> **Target Scope**: Full inventory of routes, database models, services, external calls, background jobs, and security configurations.  
> **Focus**: Deep-dive audit on the money path (ledger, balances, virtual accounts, payments, auth tokens, KYC gating).

---

## 1. System Inventory Table

| Component Name / Asset | Component Type | Purpose & Scope | Layer Violations Identified | Money / Identity Risk | Action (Keep / Rewrite / Delete) | Rationale & Justification |
|---|---|---|---|---|---|---|
| `POST /api/orders` | Router Endpoint | Student places order for vendor item; debits student wallet, credits vendor wallet, creates order & QR code, writes ledger. | Contains heavy domain logic: bcrypt PIN verification, row locking, balance subtraction/addition, order status direct assignment, ledger creation, and explicit `db.commit()`. | **HIGH** | **Rewrite** | Uses Decimal/float money values; mutates balances in-place; lacks standardized idempotency storage (key+hash+response); single-entry ledger; router holds DB transaction boundary. |
| `POST /api/orders/{order_id}/scan` | Router Endpoint | Course Rep scans student QR code to mark item as physically collected. | Controller inspects JWT QR token, checks Rep DB role, directly mutates `order.is_collected` and `collected_at`, and calls `db.commit()`. | **MED** | **Rewrite** | Direct status mutation and DB commit inside controller; logic must move to `OrderService` behind a single Unit of Work. |
| `GET /api/orders/rep` & `GET /api/rep/orders` | Router Endpoint | Rep fetches incoming student orders with pagination. | Router executes SQLAlchemy queries directly. | **LOW** | **Rewrite** | Queries belong in repository/service layer; router should only validate DTO and call service. |
| `POST /webhook/nomba` | Router Endpoint | Ingests deposit notifications from Nomba to credit student wallet. | Router verifies signature, queries DVA, queries wallet, directly adds to `available_balance`, writes single-sided ledger row, and commits. | **HIGH** | **Rewrite** | Lacks raw inbox table pattern; mutates wallet balance in-place before transaction commit; relies on PK collision for dedupe; uses Decimal instead of integer kobo. |
| `POST /api/auth/claim` | Router Endpoint | Student claims account against department roster using matric number; creates user, wallet, and requests Nomba DVA. | Service handles account claim, password hashing, wallet creation, synchronous DVA creation via Nomba HTTP client, and mints custom tokens. | **HIGH** | **Rewrite** | Mixes auth, wallet creation, and DVA provisioning without atomic Unit of Work boundary; lacks brute-force lockout protection; custom claims carry role. |
| `POST /api/auth/login-matric` | Router Endpoint | Authenticates student or rep via matric number and password. | Service checks password hash, queries wallet, mints Firebase Custom Token directly. | **HIGH** | **Rewrite** | Lacks lockout after failed attempts; uses custom claims for role assertion; missing distributed rate limiting. |
| `POST /api/auth/sync` | Router Endpoint | Syncs user profile after auth. | Delegates to `get_or_create_user` service. | **MED** | **Rewrite** | Hardcodes `Student` role on creation; needs proper `IdentityProvider` protocol abstraction. |
| `POST /api/auth/lookup-matric` | Router Endpoint | Checks if matric number exists in department roster. | SQL query executed directly in service function. | **LOW** | **Keep / Rewrite** | Simple read operation; needs move to repository layer. |
| `POST /api/auth/bootstrap-rep` | Router Endpoint | Privileged endpoint to bootstrap initial Rep account and department. | Directly creates department, user, wallet, and roster entry in single service function using secret header check. | **HIGH** | **Rewrite** | Uses header-based secret bypass; creates wallet without Unit of Work pattern or integer kobo model. |
| `POST /api/auth/upload-roster` | Router Endpoint | Rep/Admin uploads class roster. | Service queries DB and mutates/adds roster rows directly with explicit commit. | **MED** | **Rewrite** | Logic belongs in repository/service layer; requires proper role check against DB. |
| `GET /api/auth/departments` | Router Endpoint | Fetches all departments with ETag caching. | Service queries DB directly for department list. | **LOW** | **Keep** | Functional read operation; refactor to repository layer during auth overhaul. |
| `GET /api/wallet` | Router Endpoint | Retrieves wallet balance and assigned DVA account details. | Router joins `users`, `wallets`, and `accounts` directly via SQL query. | **LOW** | **Rewrite** | Move query to `WalletRepository`; router should only invoke service. |
| `GET /api/wallet/transactions` | Router Endpoint | Paginated transaction history for student or rep. | Router constructs complex SQL `UNION ALL` across `webhookEvents` and `orders` tables directly. | **MED** | **Rewrite** | Constructs fake transaction history from order and webhook rows instead of reading from append-only double-entry ledger entries. |
| `GET /api/profile` | Router Endpoint | Returns user profile and bank setup state. | Direct SQL query in router. | **LOW** | **Keep / Rewrite** | Refactor router to call `UserService`. |
| `POST /api/profile/set-pin` | Router Endpoint | Sets user 4-digit transaction PIN. | Router hashes PIN using bcrypt, updates `users.transaction_pin_hash`, and commits directly. | **HIGH** | **Rewrite** | Direct mutation of user security pin hash and commit in controller; lacks rate-limiting. |
| `GET /api/profile/banks` | Router Endpoint | Returns list of supported banks from Nomba API. | Router calls `nomba.fetch_banks()` directly. | **LOW** | **Keep / Rewrite** | Wrap Nomba API behind `PaymentProvider` protocol adapter. |
| `POST /api/profile/banks/lookup` | Router Endpoint | Resolves account number to account name via Nomba. | Router calls `nomba.lookup_account()` directly. | **LOW** | **Keep / Rewrite** | Move external call behind `PaymentProvider` protocol adapter. |
| `PATCH /api/profile/vendor-bank` | Router Endpoint | Saves vendor payout bank account details. | Router updates user record directly without backend account name verification, and commits. | **HIGH** | **Rewrite** | Direct model mutation and commit in controller; allows unverified payout bank configuration. |
| `GET /api/catalog/vendors` | Router Endpoint | Lists all vendors (Reps/Admins) with open status filter. | Direct SQL query in router. | **LOW** | **Keep / Rewrite** | Non-money endpoint; refactor SQL out of controller. |
| `GET /api/catalog/vendors/{id}` | Router Endpoint | Gets vendor details and product catalogue. | Direct SQL query in router. | **LOW** | **Keep / Rewrite** | Non-money endpoint; refactor SQL out of controller. |
| `POST /api/catalog/products` | Router Endpoint | Creates catalog product. | Direct ORM insert & `db.commit()` in router. | **LOW** | **Keep / Rewrite** | Non-money endpoint; refactor DB operations to repository. |
| `PUT /api/catalog/products/{id}` | Router Endpoint | Updates catalog product. | Direct ORM update & `db.commit()` in router. | **LOW** | **Keep / Rewrite** | Non-money endpoint; refactor DB operations to repository. |
| `DELETE /api/catalog/products/{id}` | Router Endpoint | Deletes catalog product. | Direct ORM delete & `db.commit()` in router. | **LOW** | **Keep / Rewrite** | Non-money endpoint; refactor DB operations to repository. |
| `GET /health` | Router Endpoint | Service and DB health check. | Executes `SELECT 1` in router. | **LOW** | **Keep** | Standard health endpoint. |
| `GET /api/admin/reconciliation` | Router Endpoint | Triggers manual reconciliation audit between orders and Nomba payouts. | Calls `run_reconciliation` service function directly from router. | **HIGH** | **Rewrite** | Reconciliation checks order status against external API without auditing double-entry ledger entries. |
| `users` (`user`) | Database Table | Stores user profiles, authentication metadata, role, PIN hash, failed PIN attempts, vendor bank info. | Combines student identity, auth credentials, PIN security lockout, vendor store metadata, and payout bank details into single table. | **HIGH** | **Rewrite** | Missing mandatory KYC fields (NIN verification reference, status, timestamp, HMAC hash); mixes identity with vendor payout configuration. |
| `accounts` (`account`) | Database Table | Maps student to Nomba virtual account reference & bank account number. | Schema lacks audit timestamps, KYC tier linkage, and explicit status constraints. | **MED** | **Rewrite** | Add foreign key relationships, KYC status linkage, and proper DB constraints. |
| `wallets` (`wallet`) | Database Table | Stores user `available_balance` and `locked_balance`. | Uses `Numeric(12, 2)` / `Decimal` instead of integer kobo (`BIGINT`). Balances updated in-place via SQL updates. | **HIGH** | **Rewrite** | Violates Invariant 1 (must be integer kobo `BIGINT`) and Invariant 4 (balances derived from and updated atomically with append-only ledger entries). |
| `wallet_ledger` (`wallet_ledger`) | Database Table | Single-entry audit log for wallet balance movements. | Uses `Numeric(12, 2)` / `Decimal`, records `balance_before` / `balance_after` in single-entry format (one row per wallet) rather than true double-entry journal entries summing to zero. | **HIGH** | **Rewrite** | Violates Invariant 2 (append-only double-entry ledger) and Invariant 3 (journal entries sum to zero per transaction). |
| `orders` (`order`) | Database Table | Stores order records, status, QR token, payout status. | Uses `Numeric(12, 2)` / `Decimal` for `item_amount`. Direct assignment of `order_status`. Nullable `idempotency_key` with no request hash or cached response body. | **HIGH** | **Rewrite** | Violates Invariant 1 (kobo), Invariant 5 (state machine transition function), and Invariant 6 (idempotency contract). |
| `webhook_events` (`webhookEvents`) | Database Table | Stores raw Nomba webhook payloads. | Uses `Numeric(12, 2)` / `Decimal` for `amount`. Serves as both event inbox and deduplication key without explicit processing status state machine. | **HIGH** | **Rewrite** | Violates Invariant 9 (raw inbox table with `provider_event_id` and idempotent state transitions). |
| `departments` (`department`) | Database Table | Stores department metadata. | Clean model. | **LOW** | **Keep** | Standard reference table. |
| `rosters` (`roster`) | Database Table | Stores class roster for student matric number claim validation. | Clean model. | **MED** | **Keep** | Access gate for roster verification. |
| `products` (`product`) | Database Table | Stores vendor catalog products. | Uses `Numeric(12, 2)` / `Decimal` for price. | **LOW** | **Keep / Rewrite** | Convert price column to integer kobo `BIGINT`. |
| `app/services/nomba.py` | External Integration | Nomba API HTTP client (tokens, virtual accounts, bank transfers, lookups). | Directly imported by routers and domain services. Hardcoded endpoints, sends floats for money (`float(amount)`). | **HIGH** | **Rewrite** | Violates Invariant 4 (Ports and Adapters architecture) and Invariant 1 (never float). |
| `app/services/reconciliation.py` | Audit Engine | Compares confirmed orders against Nomba API status. | Directly inspects `orders` table instead of performing double-entry ledger reconciliation against Nomba API payouts. | **MED** | **Rewrite** | Violates Invariant 13 (reconciliation must audit ledger vs external provider). |
| `app/services/roster_auth_service.py` | Auth & Roster Service | Handles rep bootstrap, roster upload, matric lookup, account claim, matric login. | Mints Firebase tokens, talks to Nomba directly, manages DB transactions and commits inside service functions. | **HIGH** | **Rewrite** | Violates Ports/Adapters, Unit of Work transaction boundary, and role assertion security rules. |
| `app/services/user_service.py` | User Provisioning | Creates or retrieves users during auth sync, triggers DVA creation. | Directly calls Nomba service, manages DB session commits. | **MED** | **Rewrite** | Needs port interface and single Unit of Work boundary. |
| `app/core/security.py` | Auth Dependency | Decodes and verifies Supabase/Firebase JWT tokens. | Conflates Supabase JWT verification with Firebase Admin SDK verification. | **HIGH** | **Rewrite** | Needs clean `IdentityProvider` protocol adapter for Firebase Custom Auth. |
| `app/core/security_webhook.py` | Webhook Security | Validates Nomba HMAC-SHA256 signature and timestamp drift. | Parses JSON payload inside verification function. | **MED** | **Keep / Rewrite** | Refactor signature verification into Nomba webhook port/adapter. |
| `app/core/rate_limiter.py` | Rate Limiter Utility | Simple in-memory IP rate limiter. | In-memory dictionary stored on instance; fails across multi-worker deployments; keyed solely on client IP without proxy awareness. | **HIGH** | **Rewrite** | Replace with Redis-backed or atomic DB rate limiter with lockout tracking for auth/PIN endpoints. |
| `acckey.json` | Configuration File | Firebase Admin SDK service account key. | Committed in root workspace directory; contains unencrypted RSA private-key material. | **HIGH** | **Delete** | Critical security risk. Delete file from repository, add to `.gitignore`, rotate GCP key. |
| `.env` | Environment File | Application configuration & secrets. | Committed in repository root; contains production database credentials (with DB owner password), Nomba Client ID/Secret, and secret keys. | **HIGH** | **Delete from Git** | Critical security risk. Remove from Git index, add to `.gitignore`, load via system environment variables. |

---

## 2. Sketch of Money-Path Modules

The target architecture strictly separates HTTP controllers, application services, domain models, and external adapters via `typing.Protocol` interfaces.

```
+-----------------------------------------------------------------------------------+
|                                 ROUTER LAYER (HTTP)                               |
|   (app/api/orders.py, app/api/wallet.py, app/api/webhooks.py, app/api/auth.py)    |
|  - Parse and validate incoming requests using Pydantic DTO schemas.               |
|  - Resolve caller identity from authentication dependency.                        |
|  - Call EXACTLY ONE application service method per request.                       |
|  - Map domain exceptions to standardized HTTP responses (400, 401, 403, 409, 422).  |
+------------------------------------------+----------------------------------------+
                                           |
                                           v
+-----------------------------------------------------------------------------------+
|                               APPLICATION SERVICE LAYER                           |
|        (PaymentService, WalletService, AuthService, KycService)                   |
|  - Defines transaction boundaries (Unit of Work = 1 DB Transaction).               |
|  - Coordinates domain state transitions and ledger postings.                      |
|  - Depends ONLY on domain models, repositories, and Port Protocols.              |
+----+-----------------------+-----------------------+-----------------------+------+
     |                       |                       |                       |
     v                       v                       v                       v
+----------+            +----------+            +----------+            +----------+
|  DOMAIN  |            |  PORTS   |            |  PORTS   |            |  PORTS   |
|  Ledger  |            | Payment  |            | Identity |            |  KYC     |
|  Money   |            | Provider |            | Provider |            | Verifier |
|  States  |            | Protocol |            | Protocol |            | Protocol |
+----------+            +----+-----+            +----+-----+            +----+-----+
                             |                       |                       |
                             v                       v                       v
                        +----+-----+            +----+-----+            +----+-----+
                        | ADAPTER  |            | ADAPTER  |            | ADAPTER  |
                        | Nomba    |            | Firebase |            | NIN/BVN  |
                        | Client   |            | Auth     |            | Verifier |
                        +----------+            +----------+            +----------+
```

---

## 3. Ranked List of the Ten Most Dangerous Findings

### 1. Floating-Point & Decimal Representations Used for Money
- **Location**: `app/models/models.py` (`wallets.available_balance`, `orders.item_amount`, `wallet_ledger.amount`) & `app/services/nomba.py` (`float(amount)`).
- **Description**: Monetary values are stored as `Numeric(12, 2)` / `Decimal` in PostgreSQL and cast to `float` when calling the Nomba API.
- **Risk**: Floating-point conversions suffer from binary precision loss. Fractional rounding errors lead to drift over transaction volumes, breaking ledger balance reconciliation.
- **Invariant Violated**: **Invariant 1** (*Money is integer kobo (BIGINT) plus a currency column. Never float or Decimal*).
- **Skill Reference**: Citing `26. Payment System/README.md` Section *APIs for payment service* (Caveat: monetary values must be exact integer/string representations to prevent float truncation).

### 2. In-Place Balance Updates & Absence of Append-Only Double-Entry Ledger
- **Location**: `app/api/orders.py` (`student_wallet.available_balance -= total_charge`), `app/api/webhooks.py` (`wallet.available_balance += credit_amount`), and `app/models/models.py` (`wallet_ledger`).
- **Description**: Balances are updated via direct in-place mutation of table columns. `wallet_ledger` is a single-entry audit table that records `balance_before` and `balance_after` for a single wallet rather than balanced credit/debit entries across two accounts.
- **Risk**: If a balance column is mutated without a corresponding balanced entry, the database state corrupts permanently. There is no mathematical proof of zero-sum money movement.
- **Invariant Violated**: **Invariants 2, 3, & 4** (*Ledger is append-only double-entry; entries sum to zero; balances are derived/updated under row lock in same transaction*).
- **Skill Reference**: Citing `26. Payment System/README.md` Section *Double-entry ledger system* (Sum of all transaction entries must always equal zero to provide end-to-end traceability).

### 3. Committed Secrets & RSA Private Keys in Workspace
- **Location**: `acckey.json` and `.env` in repository root.
- **Description**: `acckey.json` contains a raw GCP/Firebase service account RSA private key. `.env` contains production Neon database credentials (with DB owner password), Nomba Client ID/Secret, and secret keys.
- **Risk**: Anyone with access to the source code repository can authenticate as GCP admin, compromise the PostgreSQL database, or trigger unauthorized Nomba API operations.
- **Invariant Violated**: **Section 10 Rules of Engagement & Invariant 12** (*Never store or log secrets or PII*).
- **Skill Reference**: Not covered by `skill.md` (Standard operational security rule).

### 4. Direct Status Assignment Without State Machine Transition Functions
- **Location**: `app/api/orders.py` (`order.order_status = orderstat.confirmed`, `order.is_collected = True`) and `app/api/webhooks.py` (`new_event.status = hookstate.processed`).
- **Description**: Order and webhook states are updated via direct property assignment in controllers.
- **Risk**: Out-of-order webhooks or race conditions can transition orders to invalid states (e.g., confirming a refunded or expired order), causing double payouts or inventory fraud.
- **Invariant Violated**: **Invariant 5** (*Payment status changes only through one domain transition function. Illegal transitions raise*).
- **Skill Reference**: Citing `26. Payment System/README.md` Section *Handling failed payments* (Tracking payment state transitions deterministically).

### 5. Flawed Idempotency Implementation & Missing Conflict Handling
- **Location**: `app/api/orders.py` (`place_order`) and `app/api/webhooks.py`.
- **Description**: `place_order` checks if `idempotency_key` exists for a student, but if re-sent with a different payload, it returns the existing order response instead of throwing an HTTP 409 Conflict. Webhooks rely on a primary key unique constraint on `webhookEvents.event_id` and catch `IntegrityError` after executing in-memory balance additions.
- **Risk**: A client re-using an idempotency key with a modified amount or product receives a stale response without error. Webhooks that fail midway through processing can leave ORM sessions corrupted.
- **Invariant Violated**: **Invariants 6 & 7** (*Idempotency record written in same DB transaction as effect; same key with different payload returns 409*).
- **Skill Reference**: Citing `26. Payment System/README.md` Section *Exactly-once delivery* (Idempotency keys must be unique per scope and detect payload conflicts).

### 6. Webhook Deposit Crediting Precedes Transaction Persistence (Non-Atomic Inbox)
- **Location**: `app/api/webhooks.py` (`nomba_webhook`).
- **Description**: Incoming webhooks mutate `wallet.available_balance` and construct `wallet_ledger` objects before calling `db.commit()`.
- **Risk**: If the DB connection drops or a crash occurs during `db.commit()`, the webhook payload is lost or the in-memory wallet modification produces partial side-effects. There is no raw inbox table persisting the un-processed payload first.
- **Invariant Violated**: **Invariant 9** (*Verify signature first, persist raw event in inbox table with provider_event_id, then process idempotently*).
- **Skill Reference**: Citing `26. Payment System/README.md` Section *Hosted payment page workflow* (Asynchronous webhooks must be recorded first before updating internal ledger).

### 7. Router Layer Violations, Business Logic Contamination, and Unbounded Commits
- **Location**: All router modules in `app/api/` (`orders.py`, `auth.py`, `webhooks.py`, `profile.py`, `catalog.py`).
- **Description**: Router functions execute SQL queries, row locks (`SELECT FOR UPDATE`), bcrypt hashing, Nomba API calls, and control database transactions via `await db.commit()`.
- **Risk**: Transactions are left open across external HTTP network calls or serialization phases. Unhandled exceptions leave open locks or inconsistent database state.
- **Invariant Violated**: **Section 4 Target Architecture** (*Routers parse/validate, call one service method; Services manage transaction boundaries*).
- **Skill Reference**: Citing `26. Payment System/README.md` Section *Communication among internal services* (Separation of execution and storage concerns).

### 8. In-Memory IP-Only Rate Limiting & Missing Brute-Force Lockouts
- **Location**: `app/core/rate_limiter.py` (`SimpleRateLimiter`).
- **Description**: Rate limiting uses an in-memory dictionary keyed strictly on `request.client.host`.
- **Risk**: Resets on app restart, fails across multi-worker or cloud deployments (Render), and gets bypassed by spoofed or proxied IP addresses. Auth and PIN endpoints lack account lockout mechanisms.
- **Invariant Violated**: **Invariant 11** (*`/auth/claim` and `/auth/login` have their own rate limiting and lockout*).
- **Skill Reference**: Not covered by `skill.md` (Standard authentication security requirement).

### 9. Tight Coupling to External SDKs/APIs Without Port Interfaces
- **Location**: `app/services/nomba.py`, `app/core/security.py`, and `app/services/roster_auth_service.py`.
- **Description**: Domain services import `httpx` Nomba clients and Firebase Admin SDK functions directly.
- **Risk**: System cannot be tested with mock adapters. Changes to Nomba API endpoints or Firebase configuration break core application logic.
- **Invariant Violated**: **Section 4 Target Architecture** (*Ports and adapters: typing.Protocol interfaces for IdentityProvider, PaymentProvider, KycVerifier*).
- **Skill Reference**: Citing `26. Payment System/README.md` Section *PSP Integration* (Decoupling payment service logic from specific PSP API schemas).

### 10. Complete Absence of KYC Gating, Tier Limits, and NIN/BVN Protections
- **Location**: `app/models/models.py` & `app/services/`.
- **Description**: The current codebase contains zero schema definitions or service checks for NIN verification, BVN collection, KYC tiers, or tier transaction limits.
- **Risk**: Un-gated accounts can perform unlimited transactions, violating regulatory requirements and exposing the system to financial fraud.
- **Invariant Violated**: **Invariants 8 & 12** (*Limit and balance checks lock user's row inside transaction; store only verification reference, status, timestamp, HMAC*).
- **Skill Reference**: Citing `26. Payment System/README.md` Section *Step 1: Design Scope* (Compliance and verification requirements).

---
