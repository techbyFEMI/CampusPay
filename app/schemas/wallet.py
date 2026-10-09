from pydantic import BaseModel


class WalletResponse(BaseModel):
    user_id: str
    role: str
    full_name: str
    balance_kobo: int
    bank_account_number: str | None = None
    bank_name: str | None = None


class TransactionItem(BaseModel):
    type: str
    description: str
    amount_kobo: int
    direction: str
    status: str
    created_at: str
