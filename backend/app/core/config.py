from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    DATABASE_URL: str = Field(min_length=1)

    SECRET_KEY: str = Field(min_length=32)
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

    # Route rate limiting (see app/core/rate_limit.py). Disabled
    # automatically under ENVIRONMENT=test so test suites are not
    # throttled by shared limiter state.
    RATE_LIMIT_ENABLED: bool = True

    # Allowed browser origins. Keep the public hostname in sync with Caddyfile.
    CORS_ORIGIN_REGEX: str = (
        r"(https://(hpqms\.cloud|hpqms\.internal|"
        r"(192\.168|10(\.\d+){2}|172\.(1[6-9]|2\d|3[01])(\.\d+){2}))|"
        r"http://(localhost|127\.0\.0\.1|"
        r"(192\.168|10(\.\d+){2}|172\.(1[6-9]|2\d|3[01])(\.\d+){2}))(:\d+)?)"
    )

    ENVIRONMENT: str = "development"

    # Used by bootstrap_admin.py to create the first administrator.
    INITIAL_ADMIN_EMPLOYEE_ID: str | None = None
    INITIAL_ADMIN_PASSWORD: str | None = None
    DEMO_STAFF_PASSWORD: str | None = None

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
