import pytest

from relay.auth import hash_password
from relay.config import Settings
from relay.store import Store

PASSWORD = "una-contraseña-segura"


@pytest.fixture(scope="session")
def password_hash() -> str:
    return hash_password(PASSWORD)


@pytest.fixture
def settings(tmp_path, password_hash) -> Settings:
    return Settings(
        _env_file=None,
        infor_username="reader",
        infor_password="secret",
        portal_url="https://portal.test",
        sync_key="k" * 64,
        admin_password_hash=password_hash,
        secret_key="s" * 64,
        secure_cookies=False,
        database_path=tmp_path / "relay.db",
        log_dir=tmp_path / "logs",
    )


@pytest.fixture
def store(settings) -> Store:
    return Store(settings.database_path)
