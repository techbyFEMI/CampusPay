# CampusPay

CampusPay is a FUTA pilot for course representatives to publish department catalog items that students can buy with their CampusPay wallet.

## Project layout

```text
app/
  api/             FastAPI routes and HTTP error mapping
  core/            Settings, database session, security, and rate limits
  models/           SQLAlchemy models grouped by domain
  repositories/     Database queries and persistence
  schemas/          Request and response contracts
  services/         Application and domain workflows
  main.py           FastAPI application entry point
migrations/         Alembic revisions
tests/              Unit and API tests
docs/               Product rules, decisions, and archived references
Frontend/           CampusPay web client
landingPage/        Public landing page
```

Routes should validate HTTP input and translate application errors. Services coordinate use cases; repositories own database queries. Keep provider calls behind a service or adapter and keep financial updates in one transaction.

Read [the product context](docs/product_context.md) before changing auth, catalog, wallet, order, or payment behavior. `docs/archive/` contains superseded hackathon materials for reference only.

## Local setup

Use Python 3.12 or newer and PostgreSQL.

```bash
python -m venv campuspay
source campuspay/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set the database and Supabase values in `.env`. Keep real credentials out of source control.

Create or update the database schema with Alembic, then start the API:

```bash
alembic upgrade head
uvicorn app.main:app --reload
```

The app does not create or alter tables on startup; migrations own schema changes.

Run the tests with:

```bash
pytest
```

## Current implementation status

- Supabase Auth is the identity provider. CampusPay roles are loaded from its database.
- Catalog, wallet reads, profile, and auth use service and repository layers.
- Money fields use integer kobo, with separate payment and delivery states.
- Paystack is the intended payment provider. The purchase transfer route to a rep DVA, wallet debit and restoration rules, and retry workflow are still being implemented. Do not treat order processing as production-ready until those flows are complete and verified.
- The client-side catalog cache belongs to the frontend; it has not been added here.
