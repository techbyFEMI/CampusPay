# CampusPay — Complete Project Context & Technical State

> **Purpose**: This document provides an exhaustive, AI-ready technical summary of the **CampusPay** project. Give this context to any AI model, subagent, or developer so they immediately understand the application's architecture, data models, business logic, completed features, API surface, and current deployment state.

---

## 1. Executive Summary & Core Purpose

**CampusPay** is a production-grade campus fintech platform engineered for Nigerian university ecosystems. It eliminates trust deficits and payment friction between students and campus vendors by combining:
1. **Dynamic Virtual Accounts (DVAs)** via the **Nomba API** (providing dedicated bank account numbers for students to deposit funds into their campus wallet).
2. **QR Code Escrow Settlement**: When a student places an order, funds (item price + ₦20 platform fee) are locked in escrow. Upon physical pickup, the vendor scans the student's encrypted JWT QR code, releasing the escrow, refunding the ₦20 fee to the student, and triggering an instant real-time bank transfer payout to the vendor's traditional bank account.
3. **Automated No-Show Penalties**: If an order is uncollected after 24 hours, an automated background daemon unlocks the student's hold, refunds the item price, and transfers the ₦20 fee directly to the vendor's bank as compensation for held inventory.
4. **Immutable Double-Entry Financial Ledger & Daily Audit Reconciliation Engine**: Ensures zero discrepancy between database balances and real-world bank transfers.

---

## 2. Technology Stack

| Layer | Technology | Description |
|---|---|---|
| **Backend Framework** | **FastAPI** (Python 3.11+) | Async REST API, OpenAPI/Swagger generation, dependency injection |
| **Database** | **PostgreSQL** | Relational DB with JSONB support, strict foreign keys & indexed fields |
| **Database ORM** | **SQLAlchemy 2.0 (Async)** | Async ORM with `asyncpg` driver and transactional `SELECT FOR UPDATE` locking |
| **Database Migrations** | **Alembic** | Version-controlled schema migrations |
| **Authentication** | **Firebase Auth** | Client auth via Firebase SDK; JWT Bearer Token validation backend dependency |
| **Banking Core & Payouts** | **Nomba Financial Core API** | DVA provisioning (`/v1/accounts/virtual`), bank lookups, and bank transfers (`/v2/transfers/bank`) |
| **Webhook Security** | **HMAC-SHA256** | Signature verification using custom headers (`nomba-signature`, `nomba-timestamp`) |
| **QR & Order Security** | **PyJWT + Bcrypt** | HMAC-SHA256 signed QR payloads; Bcrypt hashing for student transaction PINs |
| **Frontend Tier** | **Vanilla HTML5, CSS3, Vanilla JS** | Lightweight PWA (Progressive Web App) with Service Worker offline caching |
| **Hosting & Deployment** | **Render & Vercel** | Backend hosted on Render (`campuspay-3f39.onrender.com`); Frontend on Vercel |

---

## 3. Repository Structure & Key Components

```
CampusPay/
├── main.py                     # App entry point, CORS middleware, lifespan events & background Expiry Daemon
├── requirements.txt            # Python dependencies (fastapi, sqlalchemy, asyncpg, alembic, pyjwt, bcrypt, etc.)
├── alembic.ini                 # Alembic DB migration configuration
├── migrations/                 # Database schema migration scripts
│
├── app/                        # Backend Application Core
│   ├── api/                    # API Route Handlers
│   │   ├── auth.py             # User profile sync & initial creation (/auth/sync)
│   │   ├── catalog.py          # Vendor store listing & product CRUD (/api/catalog)
│   │   ├── orders.py           # Order placement, QR scan verification, pending orders (/api/orders)
│   │   ├── profile.py          # User profile, PIN setup, bank list & vendor bank lookup (/api/profile)
│   │   ├── wallet.py           # Balance lookups and paginated ledger history (/api/wallet)
│   │   └── webhooks.py         # HTTP POST Webhook endpoint for Nomba deposit notifications (/webhook/nomba)
│   │
│   ├── core/                   # Shared Utilities & Settings
│   │   ├── config.py           # Pydantic Settings class loading environment variables
│   │   ├── database.py         # SQLAlchemy async engine & sessionmaker (`sessionLocal`)
│   │   ├── security.py         # Firebase ID token validation (`get_current_firebase_user`)
│   │   └── security_webhook.py # HMAC-SHA256 signature verification for Nomba webhooks
│   │
│   ├── models/                 # Database Schema
│   │   └── models.py           # SQLAlchemy ORM models (`users`, `accounts`, `wallets`, `orders`, `products`, `wallet_ledger`, `webhook_events`)
│   │
│   ├── schemas/                # Pydantic Input/Output Serializers
│   │   ├── auth.py, catalog.py, orders.py, profile.py, wallet.py
│   │
│   └── services/               # External Integration Services
│       ├── nomba.py            # Async client for Nomba API (OAuth token caching, DVAs, Bank Transfers, Lookups)
│       ├── reconciliation.py   # Audit engine verifying DB orders against live Nomba API payouts
│       └── user_service.py     # User creation logic & DVA auto-provisioning
│
└── Frontend/                   # Client PWA Application
    ├── manifest.json           # PWA metadata & icons definition
    ├── sw.js                   # Service worker caching strategy
    ├── index.html              # Landing redirect page
    ├── signup.html             # User registration & role selection (Student / Vendor)
    ├── dashboard.html          # Student dashboard (DVA account, balance, QR launcher, recent activity)
    ├── catalogue.html          # Campus store browser
    ├── purchase.html           # Vendor item selector & cart checkout
    ├── payment.html            # Dynamic QR code display page with live pickup countdown
    ├── pin.html                # PIN creation & verification modal UI
    ├── pending.html            # Active orders tracker for students
    ├── receipt.html            # Order completion receipt view
    ├── transactions.html       # Searchable ledger transaction history
    ├── vendor-dashboard.html   # Vendor sales stats, open/close toggle, QR code camera scanner
    ├── vendor-products.html    # Product inventory manager (add, edit, toggle stock)
    ├── vendor-profile.html     # Bank settlement account registration & lookup
    ├── scripts/                # Dynamic Page Controllers (`auth.js`, `pwa.js`, `firebaseAuth.js`, etc.)
    └── styles/                 # Sleek modern dark-mode CSS stylesheets
```

---

## 4. Complete Database Schema (SQLAlchemy Models)

### Enums
- `approles`: `"Vendor"`, `"Student"`, `"Admin"`
- `accstatus`: `"Active"`, `"Suspended"`
- `orderstat`: `"Pending"`, `"Confirmed"`, `"Expired"`, `"Refunded"`
- `payoutstat`: `"not_attempted"`, `"success"`, `"failed"`
- `hookstate`: `"Processed"`, `"Failed"`, `"Duplicate"`

### Data Models & Relationships

1. **`users` (`user` table)**:
   - `user_id` (PK, UUID string)
   - `firebase_uid` (String, Unique, Indexed)
   - `role` (`approles` Enum)
   - `full_name`, `email` (Unique), `phone` (Unique)
   - `vendor_bank_account`, `vendor_bank_code`, `vendor_bank_name` (Nullable, vendor payout destination)
   - `transaction_pin_hash` (Nullable, bcrypt hashed PIN for students)
   - `vendor_location`, `vendor_is_open` (Boolean, default False), `vendor_cover_image_url`
   - `created_at` (DateTime TZ)

2. **`accounts` (`account` table)**:
   - `dva_id` (PK, UUID string)
   - `student_id` (FK -> `user.user_id`)
   - `account_reference` (Text, Unique)
   - `bank_account_number`, `bank_name` (Nomba-assigned bank details)
   - `status` (`accstatus` Enum)
   - `created_at` (DateTime TZ)

3. **`wallets` (`wallet` table)**:
   - `wallet_id` (PK, UUID string)
   - `user_id` (FK -> `user.user_id`, Unique)
   - `available_balance` (Numeric 12,2)
   - `locked_balance` (Numeric 12,2 - Escrow hold)
   - `currency` (String "NGN")
   - `updated_at` (DateTime TZ)

4. **`orders` (`order` table)**:
   - `order_id` (PK, UUID string)
   - `student_id` (FK -> `user.user_id`)
   - `vendor_id` (FK -> `user.user_id`)
   - `item_description` (Text)
   - `item_amount` (Numeric 12,2)
   - `escrow_hold` (Numeric 12,2 - item_amount + ₦20 fee)
   - `order_status` (`orderstat` Enum: Pending | Confirmed | Expired | Refunded)
   - `qr_token` (Text, Unique - JWT signed payload)
   - `timer_expires_at` (DateTime TZ, default NOW + 24 Hours)
   - `nomba_transfer_ref` (Nullable string)
   - `penalty_status` ("pending" | "paid" | "failed")
   - `penalty_transfer_ref` (Nullable string)
   - `payout_status` (`payoutstat` Enum, default `not_attempted`)
   - `payout_last_error` (Text), `payout_attempts` (Integer)
   - `created_at` (DateTime TZ)

5. **`products` (`product` table)**:
   - `product_id` (PK, UUID string)
   - `vendor_id` (FK -> `user.user_id`)
   - `name`, `description`, `price` (Numeric 12,2), `image_url`
   - `is_available` (Boolean, default True)
   - `created_at` (DateTime TZ)

6. **`wallet_ledger` (`wallet_ledger` table)**:
   - `ledger_id` (PK, UUID string)
   - `wallet_id` (FK -> `wallet.wallet_id`, Indexed)
   - `user_id` (FK -> `user.user_id`, Indexed)
   - `direction` (String "credit" | "debit")
   - `amount`, `balance_before`, `balance_after` (Numeric 12,2)
   - `reference`, `order_id` (Nullable FK), `reason` (Text)
   - `created_at` (DateTime TZ)

7. **`webhook_events` (`webhookEvents` table)**:
   - `event_id` (PK, String - Nomba request/event ID for idempotency)
   - `event_type`, `account_reference`, `amount` (Numeric 12,2)
   - `status` (`hookstate` Enum: Processed | Failed | Duplicate)
   - `raw_payload` (JSONB)
   - `processed_at` (DateTime TZ)

---

## 5. Core FinTech Workflows & Business Logic

### A. Dynamic Virtual Account (DVA) & Automated Deposits
1. Student registers on frontend -> Auth token verified via Firebase -> `POST /auth/sync`.
2. Backend checks if user exists; if new, provisions a DVA via Nomba API (`POST /v1/accounts/virtual`).
3. Nomba returns a unique bank account number (e.g., Wema Bank / Nomba MFB) tied to the student's account reference.
4. Student transfers money from any external banking app.
5. Nomba dispatches an HTTP POST webhook to `/webhook/nomba`.
6. Webhook middleware verifies `nomba-signature` HMAC-SHA256 header.
7. Backend validates idempotency in `webhookEvents`. If new, locks student's `wallet` via `SELECT FOR UPDATE`, increments `available_balance`, records an immutable credit entry in `wallet_ledger`, and returns HTTP 200.

### B. Order Placement & Escrow Lock
1. Student selects items from catalog and clicks Pay.
2. Prompts for 4-digit Transaction PIN -> `POST /api/orders`.
3. Backend validates PIN against `users.transaction_pin_hash` (Bcrypt).
4. Locks student wallet (`SELECT FOR UPDATE`).
5. Total required = `item_amount + ₦20 platform fee`.
6. Checks if `available_balance >= required`. If valid:
   - Deducts total from `available_balance`.
   - Adds total to `locked_balance`.
   - Generates an encrypted JWT QR token containing `{ order_id, vendor_id, student_id, exp }`.
   - Records a debit ledger entry.
   - Saves `order` with status `Pending` and 24-hour expiration countdown (`timer_expires_at`).

### C. QR Scan & Bank Payout (Pickup Settlement)
1. Student shows QR code to vendor at store.
2. Vendor scans QR code using in-browser camera -> `POST /api/orders/{order_id}/scan`.
3. Backend verifies QR token JWT signature and verifies order status is `Pending`.
4. Locks student wallet (`SELECT FOR UPDATE`):
   - Deducts `escrow_hold` (`item_amount + ₦20`) from `locked_balance`.
   - Credits ₦20 platform fee back to student `available_balance` (refund).
   - Writes credit ledger entry for ₦20 refund.
   - Marks order status as `Confirmed`.
5. Calls Nomba Payout API (`POST /v2/transfers/bank`) to transfer `item_amount` directly into the vendor's external bank account (`vendor_bank_account`, `vendor_bank_code`).
6. Saves `nomba_transfer_ref` and updates `payout_status = success`.

### D. Automated Expiry Job & No-Show Penalties
1. Background task (`expiry_job`) runs every 5 minutes in `main.py`.
2. Queries all orders where `order_status == Pending` and `timer_expires_at <= NOW()`.
3. For each expired order:
   - Locks student wallet.
   - Deducts `escrow_hold` (`item_amount + ₦20`) from `locked_balance`.
   - Credits `item_amount` back to student `available_balance` (item price refunded).
   - Marks order status as `Expired`.
   - Initiates Nomba bank transfer of ₦20 to vendor's bank account as compensation for reserved inventory.
   - Updates `penalty_status = paid` and saves `penalty_transfer_ref`.

---

## 6. Complete API Surface Map

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| `POST` | `/auth/sync` | Bearer JWT | Syncs Firebase user profile & auto-provisions Nomba DVA for students |
| `POST` | `/webhook/nomba` | HMAC Signature | Receives bank deposit notifications from Nomba & credits wallet |
| `GET` | `/api/wallet` | Bearer JWT | Fetches available balance, locked balance, currency, and DVA details |
| `GET` | `/api/wallet/transactions` | Bearer JWT | Returns paginated list of ledger movements (credits/debits) |
| `GET` | `/api/profile` | Bearer JWT | Fetches user profile, role, PIN setup status, and bank config |
| `POST` | `/api/profile/set-pin` | Bearer JWT | Sets up or updates student's 4-digit transaction PIN (bcrypt hashed) |
| `GET` | `/api/profile/banks` | Bearer JWT | Fetches supported Commercial Banks list from Nomba |
| `POST` | `/api/profile/banks/lookup` | Bearer JWT | Verifies bank account number & account name against Nomba API |
| `PATCH` | `/api/profile/vendor-bank` | Bearer JWT | Updates vendor settlement bank details (account number, bank code, name) |
| `GET` | `/api/catalog/stores` | Optional | Lists open campus vendor stores & basic profile info |
| `GET` | `/api/catalog/stores/{vendor_id}/products` | Optional | Fetches all available products for a given vendor store |
| `POST` | `/api/catalog/products` | Bearer JWT (Vendor) | Adds a new product item to vendor catalog |
| `PUT` | `/api/catalog/products/{product_id}` | Bearer JWT (Vendor) | Updates existing product details/price/stock |
| `DELETE` | `/api/catalog/products/{product_id}` | Bearer JWT (Vendor) | Removes product from catalog |
| `POST` | `/api/orders` | Bearer JWT (Student) | Verifies PIN, locks funds in escrow, creates order & generates QR token |
| `POST` | `/api/orders/{order_id}/scan` | Bearer JWT (Vendor) | Scans student QR code, settles escrow, and triggers Nomba bank payout |
| `GET` | `/api/orders/{order_id}/transfer-status` | Bearer JWT | Queries live transfer status from Nomba API for a specific order payout |
| `GET` | `/api/orders/pending` | Bearer JWT (Student) | Fetches list of active pick-up ready orders for student |
| `GET` | `/api/orders/vendor/pending` | Bearer JWT (Vendor) | Fetches list of pending pick-up orders for vendor store |
| `GET` | `/api/admin/reconciliation` | Admin / Internal | Runs financial audit comparing confirmed orders against live Nomba API transfers |
| `GET` | `/health` | None | Service health check returning uptime, environment, and DB connectivity status |

---

## 7. Current Project Status & Verified State

- **Backend**: Fully functional FastAPI application with PostgreSQL database models, Alembic migrations, double-entry financial ledger, background expiry daemon, Nomba DVA & payout integration, Firebase auth verification, and audit reconciliation endpoint.
- **Frontend**: Full-featured PWA implemented in static HTML5, CSS3, and Vanilla JavaScript. Includes student dashboard, DVA account details, catalogue browser, checkout, dynamic QR rendering, vendor dashboard, camera QR code scanner, product manager, and settlement bank configuration.
- **Production Endpoints**:
  - Live API: `https://campuspay-3f39.onrender.com`
  - Interactive Swagger Docs: `https://campuspay-3f39.onrender.com/docs`
  - Client PWA Web Apps: `https://campuspay-web.vercel.app`, `https://campuspay-eta.vercel.app`

---

## 8. Guidance for AI / Developers Working on This Codebase

When making changes to CampusPay, adhere to the following key principles:
1. **Financial Integrity & Double-Spend Locks**: Always use PostgreSQL row-level locks (`SELECT ... WITH FOR UPDATE`) via `db.execute(select(...).with_for_update())` when modifying `wallet` balance rows or updating `order` escrow states.
2. **Double-Entry Ledger**: Any balance change (credit or debit) MUST be accompanied by a corresponding `wallet_ledger` insertion recording `balance_before`, `balance_after`, `amount`, `direction`, and `reference`.
3. **Nomba API Security**: Webhooks must be verified using HMAC-SHA256 signature verification in `security_webhook.py`. Nomba OAuth access tokens are cached and refreshed asynchronously in `app/services/nomba.py`.
4. **Offline QR Code Security**: QR codes contain signed JWTs (`HS256`). Always verify the JWT signature and timestamp backend-side during scanning; never rely on client-reported order IDs alone.
5. **Clean Decoupling**: Keep API routes in `app/api/`, database models in `app/models/models.py`, Pydantic schemas in `app/schemas/`, and business integrations in `app/services/`.
