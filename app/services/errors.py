class UserNotFoundError(Exception):
    """The authenticated user has no CampusPay profile."""


class AccessDeniedError(Exception):
    """The user is not allowed to perform the requested action."""


class ProductNotFoundError(Exception):
    """The requested product does not exist or is unavailable."""


class ProductOwnershipError(Exception):
    """The user does not own the requested product."""


class OrderNotFoundError(Exception):
    """The requested order does not exist."""


class InvalidQRTokenError(Exception):
    """The supplied delivery QR token is invalid or belongs to another order."""


class InvalidOrderStateError(Exception):
    """The requested action is invalid for the order's current state."""

