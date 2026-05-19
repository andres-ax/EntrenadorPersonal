"""Tests del Settings v2."""

import os


def test_settings_normaliza_postgres():
    """postgresql:// se convierte a postgresql+asyncpg://."""
    os.environ["DATABASE_URL"] = "postgresql://u:p@localhost/dbtest"
    from importlib import reload

    import src.config as cfg_mod

    reload(cfg_mod)
    assert "postgresql+asyncpg" in str(cfg_mod.settings.database_url)


def test_settings_acepta_asyncpg_directo():
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://u:p@localhost/dbtest"
    from importlib import reload

    import src.config as cfg_mod

    reload(cfg_mod)
    assert str(cfg_mod.settings.database_url).startswith("postgresql+asyncpg://")


def test_secret_str_no_se_imprime():
    from src.config import settings

    s = str(settings.telegram_token)
    assert "SecretStr" in s or "**" in s
