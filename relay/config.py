"""Settings read from the environment or the .env file next to the project."""

from functools import lru_cache
from pathlib import Path

from pydantic import HttpUrl, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

# Shorter keys are easy to guess; generate one with:
# python -c "import secrets; print(secrets.token_hex(32))"
MIN_KEY_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    # Infor LX (IBM i) through ODBC, read only
    infor_dsn: str = "Driver={iSeries Access ODBC Driver};System=192.168.200.7;"
    infor_username: str
    infor_password: SecretStr
    infor_library: str = "LX834F01"
    infor_custom_library: str = "LX834FU01"

    # Supplier portal (Laravel) that receives the data
    portal_url: HttpUrl
    sync_key: SecretStr
    portal_verify_tls: bool = True
    portal_timeout: float = 120

    # What is sent
    calendar_facility: str = "YK1"
    calendar_work_center: int = 0

    # Admin screen
    admin_username: str = "admin"
    admin_password_hash: str
    secret_key: SecretStr
    secure_cookies: bool = True

    database_path: Path = BASE_DIR / "data" / "relay.db"
    log_dir: Path = BASE_DIR / "logs"

    @field_validator("sync_key", "secret_key")
    @classmethod
    def long_enough(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < MIN_KEY_LENGTH:
            raise ValueError(f"must have at least {MIN_KEY_LENGTH} characters")
        return value

    @field_validator("infor_library", "infor_custom_library", "calendar_facility")
    @classmethod
    def plain_name(cls, value: str) -> str:
        # These names go inside the SQL text, so only letters, digits and underscore
        if not value.isascii() or not value.replace("_", "").isalnum() or len(value) > 10:
            raise ValueError("only letters, digits and underscore, up to 10 characters")
        return value.upper()

    @property
    def portal_base(self) -> str:
        return str(self.portal_url).rstrip("/")


@lru_cache
def get_settings() -> Settings:
    return Settings()
