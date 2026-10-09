from enum import Enum

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB


JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


class approles(str, Enum):
    Rep = "Rep"
    Student = "Student"
    Admin = "Admin"


class transferattemptstat(str, Enum):
    pending = "pending"
    success = "success"
    failed = "failed"


class accstatus(str, Enum):
    active = "Active"
    suspended = "Suspended"


class hookstate(str, Enum):
    processed = "Processed"
    failed = "Failed"
    duplicate = "Duplicate"


class paymentstat(str, Enum):
    pending = "pending"
    approved = "approved"
    failed = "failed"


class deliverystat(str, Enum):
    awaiting_delivery = "awaiting_delivery"
    delivered = "delivered"


class accounttype(str, Enum):
    student_wallet = "student_wallet"
    rep_account = "rep_account"
    platform_revenue = "platform_revenue"
    external_paystack = "external_paystack"


class entrytype(str, Enum):
    debit = "debit"
    credit = "credit"


class kycstat(str, Enum):
    pending = "pending"
    verified = "verified"
    failed = "failed"
