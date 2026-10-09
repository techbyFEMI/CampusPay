import hashlib
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security_webhook import verify_paystack_signature
from app.models.models import (
    Journal,
    JournalEntry,
    LedgerAccount,
    TransferAttempt,
    accounttype,
    accounts,
    entrytype,
    hookstate,
    orders,
    paymentstat,
    transferattemptstat,
    wallets,
    webhook_events,
)


logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/webhook/paystack")
async def paystack_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    raw_body = await request.body()
    signature = request.headers.get("x-paystack-signature")
    if not verify_paystack_signature(raw_body, signature):
        raise HTTPException(status_code=401, detail="Invalid Paystack signature")
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Malformed JSON payload") from exc

    event_type = payload.get("event", "unknown")
    data = payload.get("data") or {}
    provider_event_id = str(data.get("reference") or data.get("id") or hashlib.sha256(raw_body).hexdigest())
    event_id = f"{event_type}:{provider_event_id}"
    event = webhook_events(
        event_id=event_id,
        provider="paystack",
        event_type=event_type,
        status=hookstate.processed,
        raw_payload=payload,
    )
    db.add(event)

    if event_type == "charge.success":
        customer = data.get("customer") or {}
        customer_code = customer.get("customer_code")
        amount_kobo = data.get("amount")
        if not customer_code or not isinstance(amount_kobo, int) or amount_kobo <= 0:
            await db.rollback()
            raise HTTPException(status_code=400, detail="Malformed Paystack charge event")

        dva_result = await db.execute(
            select(accounts).where(accounts.provider_customer_code == customer_code)
        )
        dva = dva_result.scalar_one_or_none()
        if dva:
            wallet_result = await db.execute(
                select(wallets).where(wallets.user_id == dva.owner_user_id).with_for_update()
            )
            wallet = wallet_result.scalar_one_or_none()
            if wallet is None:
                await db.rollback()
                raise HTTPException(status_code=409, detail="Wallet not provisioned for this DVA")

            student_account_result = await db.execute(
                select(LedgerAccount).where(
                    LedgerAccount.user_id == dva.owner_user_id,
                    LedgerAccount.account_type == accounttype.student_wallet,
                    LedgerAccount.currency == "NGN",
                )
            )
            student_account = student_account_result.scalar_one_or_none()
            if student_account is None:
                student_account = LedgerAccount(
                    account_type=accounttype.student_wallet,
                    user_id=dva.owner_user_id,
                    currency="NGN",
                    balance_kobo=0,
                )
                db.add(student_account)
                await db.flush()

            provider_account_result = await db.execute(
                select(LedgerAccount).where(
                    LedgerAccount.account_type == accounttype.external_paystack,
                    LedgerAccount.user_id.is_(None),
                    LedgerAccount.currency == "NGN",
                )
            )
            provider_account = provider_account_result.scalar_one_or_none()
            if provider_account is None:
                provider_account = LedgerAccount(
                    account_type=accounttype.external_paystack,
                    user_id=None,
                    currency="NGN",
                    balance_kobo=0,
                )
                db.add(provider_account)
                await db.flush()

            reference = f"paystack:charge:{provider_event_id}"
            journal = Journal(reference=reference, reason="student_wallet_funding")
            db.add(journal)
            await db.flush()
            db.add_all(
                [
                    JournalEntry(
                        journal_id=journal.journal_id,
                        account_id=provider_account.account_id,
                        entry_type=entrytype.debit,
                        amount_kobo=amount_kobo,
                    ),
                    JournalEntry(
                        journal_id=journal.journal_id,
                        account_id=student_account.account_id,
                        entry_type=entrytype.credit,
                        amount_kobo=amount_kobo,
                    ),
                ]
            )
            wallet.balance_kobo += amount_kobo
            wallet.updated_at = datetime.now(timezone.utc)
            student_account.balance_kobo += amount_kobo
            provider_account.balance_kobo += amount_kobo
        else:
            logger.warning("Paystack charge has no matching CampusPay DVA customer: %s", customer_code)

    elif event_type in {"transfer.success", "transfer.failed", "transfer.reversed"}:
        transfer_reference = data.get("reference")
        attempt_result = await db.execute(
            select(TransferAttempt)
            .where(TransferAttempt.provider_reference == transfer_reference)
            .with_for_update()
        )
        attempt = attempt_result.scalar_one_or_none()
        if attempt:
            order_result = await db.execute(
                select(orders).where(orders.order_id == attempt.order_id).with_for_update()
            )
            order = order_result.scalar_one_or_none()
            if order and event_type == "transfer.success":
                attempt.status = transferattemptstat.success
                order.payment_status = paymentstat.approved
                provider_cost_kobo = data.get("fees")
                if isinstance(provider_cost_kobo, int) and provider_cost_kobo >= 0:
                    order.provider_cost_kobo = provider_cost_kobo
                    distributable_fee = max(order.fee_kobo - provider_cost_kobo, 0)
                    order.rep_share_kobo = distributable_fee * 60 // 100
                    order.campuspay_share_kobo = distributable_fee - order.rep_share_kobo
            elif order:
                attempt.status = transferattemptstat.failed
                attempt.failure_reason = data.get("reason") or event_type
                if attempt.attempt_number >= 3:
                    order.payment_status = paymentstat.failed

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return JSONResponse(content={"message": "Duplicate event acknowledged"}, status_code=200)
    except Exception:
        await db.rollback()
        logger.exception("Paystack webhook processing failed event_id=%s", event_id)
        raise HTTPException(status_code=500, detail="Webhook processing failed")

    return JSONResponse(content={"message": "Event acknowledged"}, status_code=200)
