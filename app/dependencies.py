"""Injection de dépendances et contrôle d'accès.

- Fabriques @lru_cache : singletons du processus (les tests appellent
  ``reset_singletons()`` — voir conftest.py).
- Dépendances d'accès : ``require_auth`` / ``require_editor`` /
  ``require_admin`` lèvent ``AuthRedirect`` (convertie en 303 par le handler
  de main.py). Le rôle est re-résolu à CHAQUE requête via le repository
  (cache 5 min) : la session ne contient que l'identité.
"""

import logging
from collections.abc import Mapping
from functools import lru_cache

from fastapi import HTTPException, Request
from pygrister.api import GristApi

from app.core.config import Settings
from app.core.security import session_email
from app.repositories.cache import TableCache
from app.repositories.cas_usage_repository import (
    CasUsageRepositoryProtocol,
    GristCasUsageRepository,
)
from app.repositories.collectivite_repository import (
    CollectiviteRepositoryProtocol,
    GristCollectiviteRepository,
)
from app.repositories.document_repository import (
    DocumentRepositoryProtocol,
    GristDocumentRepository,
)
from app.repositories.grist_session import build_grist_api
from app.repositories.partenaire_repository import (
    GristPartenaireRepository,
    PartenaireRepositoryProtocol,
)
from app.repositories.programme_repository import (
    GristProgrammeRepository,
    ProgrammeRepositoryProtocol,
)
from app.repositories.projet_repository import (
    GristProjetRepository,
    ProjetRepositoryProtocol,
)
from app.repositories.reference_repository import (
    GristReferenceRepository,
    ReferenceRepositoryProtocol,
)
from app.repositories.types import (
    DROIT_ADMINISTRATEUR,
    DROIT_EN_ATTENTE,
    DROIT_EXTENTION,
    DROIT_VISITEUR,
    UtilisateurRecord,
)
from app.repositories.utilisateur_repository import (
    GristUtilisateurRepository,
    UtilisateurRepositoryProtocol,
)
from app.services.admin_service import AdminService
from app.services.auth_service import AuthService
from app.services.collectivite_service import CollectiviteService
from app.services.geocode_client import GeocodeClient
from app.services.notification_service import NotificationService
from app.services.oidc_service import OidcService
from app.services.projet_service import ProjetService
from app.services.restitution_service import RestitutionService

_logger = logging.getLogger(__name__)

# --- Fabriques ---


@lru_cache
def get_settings() -> Settings:
    # Les champs requis (GRIST_*) sont fournis par l'environnement / le .env
    return Settings()  # pyright: ignore[reportCallIssue]


@lru_cache
def get_grist_api() -> GristApi:
    return build_grist_api(get_settings())


@lru_cache
def get_table_cache() -> TableCache:
    return TableCache(ttl_seconds=get_settings().CACHE_TTL_SECONDS)


@lru_cache
def get_utilisateur_repository() -> UtilisateurRepositoryProtocol:
    return GristUtilisateurRepository(get_grist_api(), get_table_cache())


@lru_cache
def get_collectivite_repository() -> CollectiviteRepositoryProtocol:
    return GristCollectiviteRepository(get_grist_api(), get_table_cache())


@lru_cache
def get_reference_repository() -> ReferenceRepositoryProtocol:
    return GristReferenceRepository(get_grist_api(), get_table_cache())


@lru_cache
def get_notification_service() -> NotificationService:
    return NotificationService(get_settings())


@lru_cache
def get_auth_service() -> AuthService:
    return AuthService(
        get_utilisateur_repository(),
        get_notification_service(),
    )


@lru_cache
def get_admin_service() -> AdminService:
    return AdminService(get_utilisateur_repository())


@lru_cache
def get_projet_repository() -> ProjetRepositoryProtocol:
    return GristProjetRepository(get_grist_api(), get_table_cache())


@lru_cache
def get_collectivite_service() -> CollectiviteService:
    return CollectiviteService(
        get_collectivite_repository(),
        get_projet_repository(),
        get_reference_repository(),
    )


@lru_cache
def get_cas_usage_repository() -> CasUsageRepositoryProtocol:
    return GristCasUsageRepository(get_grist_api(), get_table_cache())


@lru_cache
def get_partenaire_repository() -> PartenaireRepositoryProtocol:
    return GristPartenaireRepository(get_grist_api(), get_table_cache())


@lru_cache
def get_programme_repository() -> ProgrammeRepositoryProtocol:
    return GristProgrammeRepository(get_grist_api(), get_table_cache())


@lru_cache
def get_document_repository() -> DocumentRepositoryProtocol:
    return GristDocumentRepository(get_grist_api(), get_table_cache())


@lru_cache
def get_oidc_service() -> OidcService:
    return OidcService(get_settings())


@lru_cache
def get_geocode_client() -> GeocodeClient:
    # Singleton : porte le cache des résultats de géocodage
    return GeocodeClient()


@lru_cache
def get_restitution_service() -> RestitutionService:
    return RestitutionService(
        get_collectivite_repository(),
        get_projet_repository(),
        get_cas_usage_repository(),
        get_partenaire_repository(),
        get_programme_repository(),
        get_document_repository(),
        get_reference_repository(),
        get_geocode_client(),
    )


@lru_cache
def get_projet_service() -> ProjetService:
    return ProjetService(
        get_projet_repository(),
        get_collectivite_repository(),
        get_reference_repository(),
        get_cas_usage_repository(),
        get_partenaire_repository(),
        get_programme_repository(),
        get_document_repository(),
    )


def reset_singletons() -> None:
    """Vide toutes les fabriques — réservé aux tests (isolation)."""
    for factory in (
        get_settings,
        get_grist_api,
        get_table_cache,
        get_utilisateur_repository,
        get_collectivite_repository,
        get_reference_repository,
        get_notification_service,
        get_auth_service,
        get_admin_service,
        get_projet_repository,
        get_collectivite_service,
        get_cas_usage_repository,
        get_partenaire_repository,
        get_programme_repository,
        get_document_repository,
        get_projet_service,
        get_geocode_client,
        get_restitution_service,
        get_oidc_service,
    ):
        factory.cache_clear()


# --- Contrôle d'accès ---


class AuthRedirect(Exception):
    """Levée par les dépendances d'accès — convertie en redirection 303."""

    def __init__(self, url: str):
        super().__init__(url)
        self.url = url


def get_current_user(request: Request) -> UtilisateurRecord | None:
    """Utilisateur de la requête : identité en session, rôle re-résolu."""
    email = session_email(request)
    if not email:
        return None
    return get_utilisateur_repository().get_by_email(email)


def require_auth(request: Request) -> UtilisateurRecord:
    """Session valide exigée ; « En attente » est renvoyé vers acces-refuse."""
    utilisateur = get_current_user(request)
    if utilisateur is None:
        raise AuthRedirect("/login")
    if utilisateur.get("droits") == DROIT_EN_ATTENTE:
        raise AuthRedirect("/acces-refuse")
    return utilisateur


def require_editor(request: Request) -> UtilisateurRecord:
    """Droits d'édition exigés (Éditeur/Administrateur) — parité v1."""
    utilisateur = require_auth(request)
    if utilisateur.get("droits") in (DROIT_VISITEUR, DROIT_EXTENTION):
        raise AuthRedirect("/")
    return utilisateur


def require_admin(request: Request) -> UtilisateurRecord:
    utilisateur = require_auth(request)
    if utilisateur.get("droits") != DROIT_ADMINISTRATEUR:
        raise AuthRedirect("/")
    return utilisateur


def require_collectivite_ownership(
    utilisateur: UtilisateurRecord, collectivite_id: int
) -> None:
    """Anti-IDOR (B2) : un Éditeur n'accède qu'à SA collectivité — en lecture
    (GET) comme en écriture. Hors périmètre → 404 (ne confirme pas
    l'existence de l'identifiant). Administrateur exempté.
    """
    if utilisateur.get("droits") == DROIT_ADMINISTRATEUR:
        return
    if (utilisateur.get("collectivite") or 0) != collectivite_id:
        # 404 côté client (ne confirme pas l'existence) ; alerte explicite
        # côté serveur pour la supervision sécurité
        _logger.warning(
            "TENTATIVE_IDOR collectivite=%s par utilisateur=%s",
            collectivite_id, utilisateur.get("email", "?"),
        )
        raise HTTPException(status_code=404, detail="Page introuvable")


def require_projet_ownership(
    utilisateur: UtilisateurRecord, projet: Mapping[str, object] | None
) -> None:
    """Anti-IDOR projet : le projet doit appartenir au périmètre de
    l'utilisateur (une de ses collectivités porteuses). 404 sinon —
    y compris pour un projet inexistant (réponse uniforme).
    """
    if projet is None:
        raise HTTPException(status_code=404, detail="Page introuvable")
    if utilisateur.get("droits") == DROIT_ADMINISTRATEUR:
        return
    from app.repositories.base import ref_ids

    porteuses = ref_ids(projet.get("collectivites_porteuses"))
    if (utilisateur.get("collectivite") or 0) not in porteuses:
        _logger.warning(
            "TENTATIVE_IDOR projet=%s par utilisateur=%s",
            projet.get("id", "?"), utilisateur.get("email", "?"),
        )
        raise HTTPException(status_code=404, detail="Page introuvable")
