from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:password@localhost:5432/hpqms"
    )

    TEST_DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:password@localhost/hospital_test"
    )

    SECRET_KEY: str = "change-this-to-a-real-secret-in-production"
    ALGORITHM: str = "HS256"

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    AFRICAS_TALKING_API_KEY: str = ""
    AFRICAS_TALKING_USERNAME: str = "sandbox"

    PRINTER_HOST: str = ""
    PRINTER_PORT: int = 9100

    USE_WINDOWS_SPOOLER: bool = False
    WINDOWS_PRINTER_NAME: str = ""

    PA_CONTROLLER_URL: str = ""

    # Shared only with managed kiosk devices. Do not expose this value in
    # browser-delivered JavaScript or commit it to source control.
    KIOSK_INTERNAL_API_KEY: str = ""

    ENVIRONMENT: str = "development"

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
