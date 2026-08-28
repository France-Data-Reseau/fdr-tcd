"""Configuration : refus de démarrer en production sans secrets (faiblesse v1 n°8)."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings

BASE = {
    "GRIST_API_KEY": "cle",
    "GRIST_DOC_ID": "doc",
    "GRIST_SERVER_URL": "https://grist.exemple.test",
}


def settings_sans_dotenv(**kwargs) -> Settings:
    """Construit Settings sans lire de fichier .env (isolation des tests)."""
    return Settings(_env_file=None, **BASE, **kwargs)  # pyright: ignore[reportCallIssue]


def test_production_sans_secret_key_refusee():
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        settings_sans_dotenv(ENVIRONMENT="production")


def test_production_sans_smtp_refusee():
    with pytest.raises(ValidationError, match="SMTP"):
        settings_sans_dotenv(ENVIRONMENT="production", SECRET_KEY="x" * 32)


def test_production_complete_demarre():
    settings = settings_sans_dotenv(
        ENVIRONMENT="production",
        SECRET_KEY="x" * 32,
        SMTP_HOST="smtp.exemple.fr",
        SMTP_USER="app",
        SMTP_PASSWORD="mdp",
    )
    assert settings.is_production


def test_developpement_genere_une_cle_ephemere():
    settings = settings_sans_dotenv(ENVIRONMENT="development")
    assert settings.SECRET_KEY  # générée, non vide
    assert not settings.is_production
