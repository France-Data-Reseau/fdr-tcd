"""Configuration de l'application — tout vient du .env, zéro valeur en dur.

En production, l'application REFUSE de démarrer sans SECRET_KEY explicite.
"""

import logging
import secrets

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # Application
    ENVIRONMENT: str = "development" # "production", "test" ou "development"
    SECRET_KEY: str = ""
    APP_PUBLIC_URL: str = "http://localhost:8000"
    GIT_SHA: str = "dev"

    # Grist (source de données unique) — aucune valeur par défaut : tout en .env
    GRIST_API_KEY: str
    GRIST_DOC_ID: str
    GRIST_SERVER_URL: str

    # Client Grist
    GRIST_TIMEOUT_CONNECT: float = 5.0
    GRIST_TIMEOUT_READ: float = 30.0
    GRIST_RETRIES: int = 2
    CACHE_TTL_SECONDS: int = 300

    # Sessions
    SESSION_MAX_AGE_SECONDS: int = 3600

    # SSO OIDC (IdP de France Data Réseau — celui derrière l'instance Grist).
    # OIDC_CLIENT_SECRET est optionnel pour un client public avec PKCE.
    OIDC_ISSUER: str = ""
    OIDC_CLIENT_ID: str = ""
    OIDC_CLIENT_SECRET: str = ""
    # Sécurité : refuser les identités dont l'email n'est
    # pas marqué vérifié par l'IdP. ACTIVÉ par défaut.
    OIDC_REQUIRE_EMAIL_VERIFIED: bool = True

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @model_validator(mode="after")
    def _exiger_secrets_en_production(self) -> "Settings":
        if self.is_production:
            if not self.SECRET_KEY:
                raise ValueError(
                    "Refus de démarrer en production — variable manquante : SECRET_KEY"
                )
        elif not self.SECRET_KEY:
            # Hors production : clé éphémère (les sessions ne survivent pas au redémarrage)
            object.__setattr__(self, "SECRET_KEY", secrets.token_urlsafe(32))
            logger.warning("SECRET_KEY absente — clé éphémère générée (développement)")
        return self
