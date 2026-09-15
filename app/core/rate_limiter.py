import time
from collections import defaultdict
from fastapi import HTTPException, Request, status

class SimpleRateLimiter:
    def __init__(self, requests_per_minute: int = 10):
        self.requests_per_minute = requests_per_minute
        self.history = defaultdict(list)

    def __call__(self, request: Request):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        minute_ago = now - 60

        # Clean old requests
        self.history[client_ip] = [t for t in self.history[client_ip] if t > minute_ago]

        if len(self.history[client_ip]) >= self.requests_per_minute:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many authentication attempts. Please wait 1 minute before trying again.",
            )

        self.history[client_ip].append(now)

login_rate_limiter = SimpleRateLimiter(requests_per_minute=5)
claim_rate_limiter = SimpleRateLimiter(requests_per_minute=5)
lookup_rate_limiter = SimpleRateLimiter(requests_per_minute=15)
