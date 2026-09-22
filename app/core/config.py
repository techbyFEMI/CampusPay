from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    NOMBA_CLIENT_ID:str
    NOMBA_CLIENT_SECRET:str
    NOMBA_ACCOUNT_ID:str
    NOMBA_SUB_ACCOUNT_ID: str
    NOMBA_BASE_URL:str
    DATABASE_URL:str
    SECRET_KEY:str
    QR_SECRET_KEY: str | None = None          # Independent signing key for QR tokens; falls back to SECRET_KEY if not set in env

    GOOGLE_PROJECT_ID: str
    GOOGLE_CLIENT_EMAIL:str
    GOOGLE_PRIVATE_KEY:str
    FIREBASE_CREDENTIALS_PATH:str
    TOKEN_URL:str
    WEBHOOK_SECRET:str
    FIREBASE_CREDENTIALS:str
    

    class Config:
        env_file= ".env"

settings=Settings()