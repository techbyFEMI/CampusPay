from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    NOMBA_CLIENT_ID: str
    NOMBA_CLIENT_SECRET: str
    NOMBA_ACCOUNT_ID: str
    NOMBA_SUB_ACCOUNT_ID: str
    NOMBA_BASE_URL: str
    DATABASE_URL: str
    SECRET_KEY: str
    ADMIN_BOOTSTRAP_SECRET: str | None = None  # Required to call /bootstrap-rep
    QR_SECRET_KEY: str | None = None          # Independent signing key for QR tokens; falls back to SECRET_KEY if not set in env

    # Supabase Auth
    SUPABASE_URL: str | None = None
    SUPABASE_JWT_SECRET: str | None = None
    SUPABASE_ANON_KEY: str | None = None

    # Legacy Firebase (optional)
    GOOGLE_PROJECT_ID: str | None = None
    GOOGLE_CLIENT_EMAIL: str | None = None
    GOOGLE_PRIVATE_KEY: str | None = None
    FIREBASE_CREDENTIALS_PATH: str | None = None
    TOKEN_URL: str | None = None
    WEBHOOK_SECRET: str
    FIREBASE_CREDENTIALS: str | None = None
    

    class Config:
        env_file = ".env"

settings = Settings()