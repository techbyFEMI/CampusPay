from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    DATABASE_URL: str
    SECRET_KEY: str
    QR_SECRET_KEY: str
    ADMIN_BOOTSTRAP_SECRET: str | None = None

    SUPABASE_URL: str | None = None
    SUPABASE_JWT_SECRET: str | None = None
    SUPABASE_ANON_KEY: str | None = None
    SUPABASE_SERVICE_ROLE_KEY: str | None = None
    PAYSTACK_SECRET_KEY: str | None = None
    PAYSTACK_PUBLIC_KEY: str | None = None
    PAYSTACK_WEBHOOK_SECRET: str | None = None

settings = Settings()
