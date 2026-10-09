import pytest
import uuid
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models.models import (
    users,
    accounts,
    products,
    orders,
    wallets,
    LedgerAccount,
    Journal,
    JournalEntry,
    TransferAttempt,
    IdempotencyKey,
    approles,
    paymentstat,
    deliverystat,
    transferattemptstat,
    accounttype,
    entrytype,
    kycstat,
    accstatus,
)


@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_user_dva_and_kyc_fields(in_memory_db):
    user_id = str(uuid.uuid4())
    u = users(
        user_id=user_id,
        full_name="Test Student",
        email="student@futa.edu.ng",
        role=approles.Student,
        nin_verification_ref="ref_nin_12345",
        nin_verification_status=kycstat.verified,
        bvn_verification_ref="ref_bvn_67890",
        bvn_verification_status=kycstat.verified,
    )
    dva = accounts(
        owner_user_id=user_id,
        account_reference="student-reference",
        bank_account_number="9988776655",
        bank_name="Wema Bank",
        status=accstatus.active,
    )
    in_memory_db.add_all([u, dva])
    in_memory_db.commit()

    saved_user = in_memory_db.query(users).filter_by(user_id=user_id).first()
    assert saved_user is not None
    assert saved_user.nin_verification_status == kycstat.verified
    saved_dva = in_memory_db.query(accounts).filter_by(owner_user_id=user_id).first()
    assert saved_dva.bank_account_number == "9988776655"


def test_product_price_kobo(in_memory_db):
    rep_id = str(uuid.uuid4())
    rep = users(
        user_id=rep_id,
        full_name="Department Rep",
        role=approles.Rep,
    )
    product_id = str(uuid.uuid4())
    p = products(
        product_id=product_id,
        rep_id=rep_id,
        name="CSC 301 Lab Manual",
        price_kobo=150000,
    )
    in_memory_db.add_all([rep, p])
    in_memory_db.commit()

    saved_product = in_memory_db.query(products).filter_by(product_id=product_id).first()
    assert saved_product is not None
    assert saved_product.price_kobo == 150000


def test_order_decoupled_states_and_kobo_shares(in_memory_db):
    student_id = str(uuid.uuid4())
    rep_id = str(uuid.uuid4())
    student = users(user_id=student_id, full_name="Student A", role=approles.Student)
    rep = users(user_id=rep_id, full_name="Rep B", role=approles.Rep)

    order_id = str(uuid.uuid4())
    product_id = str(uuid.uuid4())
    product = products(
        product_id=product_id,
        rep_id=rep_id,
        name="CSC 301 Lab Manual",
        price_kobo=150000,
    )
    o = orders(
        order_id=order_id,
        student_id=student_id,
        rep_id=rep_id,
        product_id=product_id,
        item_description="CSC 301 Lab Manual",
        item_price_kobo=150000,
        fee_kobo=5000,
        rep_share_kobo=2100,
        campuspay_share_kobo=1400,
        provider_cost_kobo=1500,
        payment_status=paymentstat.pending,
        delivery_status=deliverystat.awaiting_delivery,
        qr_token="qr_test_token_123",
    )
    in_memory_db.add_all([student, rep, product, o])
    in_memory_db.commit()

    saved_order = in_memory_db.query(orders).filter_by(order_id=order_id).first()
    assert saved_order is not None
    assert saved_order.payment_status == paymentstat.pending
    assert saved_order.delivery_status == deliverystat.awaiting_delivery
    assert saved_order.item_price_kobo == 150000
    assert saved_order.rep_share_kobo == 2100
    assert saved_order.campuspay_share_kobo == 1400


def test_double_entry_ledger_models(in_memory_db):
    account1_id = str(uuid.uuid4())
    account2_id = str(uuid.uuid4())

    acc1 = LedgerAccount(
        account_id=account1_id,
        account_type=accounttype.student_wallet,
        balance_kobo=100000,
    )
    acc2 = LedgerAccount(
        account_id=account2_id,
        account_type=accounttype.external_paystack,
        balance_kobo=0,
    )
    in_memory_db.add_all([acc1, acc2])
    in_memory_db.commit()

    journal_id = str(uuid.uuid4())
    j = Journal(
        journal_id=journal_id,
        reference="dep_001",
        reason="wallet_topup",
    )
    e1 = JournalEntry(
        entry_id=str(uuid.uuid4()),
        journal_id=journal_id,
        account_id=account2_id,
        entry_type=entrytype.debit,
        amount_kobo=50000,
    )
    e2 = JournalEntry(
        entry_id=str(uuid.uuid4()),
        journal_id=journal_id,
        account_id=account1_id,
        entry_type=entrytype.credit,
        amount_kobo=50000,
    )
    in_memory_db.add_all([j, e1, e2])
    in_memory_db.commit()

    saved_journal = in_memory_db.query(Journal).filter_by(journal_id=journal_id).first()
    assert saved_journal is not None
    entries = in_memory_db.query(JournalEntry).filter_by(journal_id=journal_id).all()
    assert len(entries) == 2


def test_transfer_attempt_tracking(in_memory_db):
    student_id = str(uuid.uuid4())
    rep_id = str(uuid.uuid4())
    student = users(user_id=student_id, full_name="Student X", role=approles.Student)
    rep = users(user_id=rep_id, full_name="Rep Y", role=approles.Rep)

    order_id = str(uuid.uuid4())
    product_id = str(uuid.uuid4())
    product = products(
        product_id=product_id,
        rep_id=rep_id,
        name="Course Notes",
        price_kobo=200000,
    )
    o = orders(
        order_id=order_id,
        student_id=student_id,
        rep_id=rep_id,
        product_id=product_id,
        item_description="Course Notes",
        item_price_kobo=200000,
        fee_kobo=5000,
        rep_share_kobo=0,
        campuspay_share_kobo=0,
        provider_cost_kobo=0,
        payment_status=paymentstat.pending,
        delivery_status=deliverystat.awaiting_delivery,
        qr_token="qr_test_2000",
    )
    in_memory_db.add_all([student, rep, product, o])
    in_memory_db.commit()

    attempt_id = str(uuid.uuid4())
    ta = TransferAttempt(
        transfer_attempt_id=attempt_id,
        order_id=order_id,
        attempt_number=1,
        provider_reference="TRF_PAYSTACK_001",
        status=transferattemptstat.pending,
    )
    in_memory_db.add(ta)
    in_memory_db.commit()

    saved_attempt = in_memory_db.query(TransferAttempt).filter_by(transfer_attempt_id=attempt_id).first()
    assert saved_attempt is not None
    assert saved_attempt.attempt_number == 1
    assert saved_attempt.status == transferattemptstat.pending


def test_idempotency_key_model(in_memory_db):
    idem_id = str(uuid.uuid4())
    ik = IdempotencyKey(
        id=idem_id,
        caller_user_id="user_123",
        idempotency_key="key_abc_456",
        payload_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",  # pragma: allowlist secret
        response_body={"status": "success", "order_id": "ord_100"},
        response_status=201,
    )
    in_memory_db.add(ik)
    in_memory_db.commit()

    saved_ik = in_memory_db.query(IdempotencyKey).filter_by(id=idem_id).first()
    assert saved_ik is not None
    assert saved_ik.caller_user_id == "user_123"
    assert saved_ik.response_status == 201
