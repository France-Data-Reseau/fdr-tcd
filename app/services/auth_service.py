"""Authentification : magic link + workflow de validation des comptes.

Toutes les réponses visibles par l'appelant sont NEUTRES : l'existence d'un
compte ne se déduit ni du login, ni de l'inscription (anti-énumération).
Le pipeline est conçu pour brancher l'OIDC ensuite : quelle que soit la preuve
d'identité (lien email ou IdP), on aboutit à un email vérifié, mappé sur
``BDD_Utilisateurs`` (référentiel des rôles).
"""

import logging
from datetime import datetime

from app.repositories.types import (
    COL_PASSWORD_HASH,
    DROIT_EXTENTION,
    DROIT_VISITEUR,
    UtilisateurRecord,
)
from app.repositories.utilisateur_repository import UtilisateurRepositoryProtocol
from app.services.magic_link_service import EmailRateLimiter, MagicLinkService
from app.services.notification_service import NotificationService
from app.services.password_service import (
    hash_password,
    verify_dummy,
    verify_password,
)
from app.services.types import InscriptionForm

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(
        self,
        utilisateurs: UtilisateurRepositoryProtocol,
        notifications: NotificationService,
        magic_links: MagicLinkService,
        email_limiter: EmailRateLimiter,
    ):
        self._utilisateurs = utilisateurs
        self._notifications = notifications
        self._magic_links = magic_links
        self._email_limiter = email_limiter

    def request_login(self, email: str) -> None:
        """Envoie un lien de connexion SI un compte existe. Toujours silencieux.

        Aucun retour exploitable : l'appelant affiche le même message neutre
        dans tous les cas. Le lien n'est jamais journalisé.
        """
        email = email.strip()
        if not email:
            return
        if not self._email_limiter.allow(email):
            logger.warning("Magic link : limite d'envois atteinte pour un email")
            return
        utilisateur = self._utilisateurs.get_by_email(email)
        if utilisateur is None:
            logger.info("Magic link : email sans compte — aucun envoi")
            return
        lien = self._magic_links.generate_url(email)
        envoye = self._notifications.send_magic_link(
            email, lien, self._magic_links.ttl_minutes
        )
        if not envoye:
            logger.error("Magic link : échec d'envoi SMTP")

    def complete_login(self, token: str) -> UtilisateurRecord | None:
        """Consomme le jeton et retourne l'utilisateur, ou None (motif tu)."""
        email = self._magic_links.verify_and_consume(token)
        if email is None:
            return None
        utilisateur = self._utilisateurs.get_by_email(email)
        if utilisateur is None:
            # Compte supprimé entre l'envoi et le clic
            logger.info("Magic link valide mais compte inexistant")
            return None
        return utilisateur

    def authenticate(self, email: str, password: str) -> UtilisateurRecord | None:
        """Login par mot de passe. Retourne l'utilisateur, ou None.

        Temps de réponse ~constant (anti-énumération) : un dummy-verify est
        exécuté quand l'email est inconnu ou n'a pas encore de hash. La route
        affiche un message neutre commun à tous les échecs.
        """
        email = email.strip()
        utilisateur = self._utilisateurs.get_by_email(email) if email else None
        if utilisateur is None:
            verify_dummy(password)
            return None
        stored = str(utilisateur.get(COL_PASSWORD_HASH) or "")
        if not stored:
            # Compte sans mot de passe (existant non initialisé) : pas de fuite
            verify_dummy(password)
            return None
        if not verify_password(stored, password):
            return None
        return utilisateur

    def set_password(self, user_id: int, new_password: str) -> None:
        """Définit/remplace le mot de passe d'un compte (hash argon2id)."""
        self._utilisateurs.set_password_hash(user_id, hash_password(new_password))

    def verify_current_password(
        self, utilisateur: UtilisateurRecord, password: str
    ) -> bool:
        """Vrai si `password` est le mot de passe actuel de l'utilisateur."""
        stored = str(utilisateur.get(COL_PASSWORD_HASH) or "")
        return bool(stored) and verify_password(stored, password)

    def register(self, formulaire: InscriptionForm) -> None:
        """Crée une demande d'accès « En attente ». Réponse neutre.

        Si l'email a déjà un compte, on n'en crée pas un second et on envoie
        un lien de connexion à la place — l'extérieur ne voit aucune différence.
        """
        existant = self._utilisateurs.get_by_email(formulaire.email)
        if existant is not None:
            logger.info("Inscription sur email existant — lien de connexion envoyé")
            self.request_login(formulaire.email)
            return
        self._utilisateurs.create_pending(
            {
                "prenom": formulaire.prenom,
                "nom": formulaire.nom,
                "email": formulaire.email,
                "organisation": formulaire.organisation,
                "collectivite": formulaire.collectivite_id,
                "date_inscription": datetime.now().strftime("%Y-%m-%d %H:%M"),
                COL_PASSWORD_HASH: hash_password(formulaire.password),
            }
        )
        self._notifications.notify_new_user(
            prenom=formulaire.prenom,
            nom=formulaire.nom,
            email=formulaire.email,
            organisation=formulaire.organisation,
            collectivite=formulaire.collectivite_nom,
        )

    def request_elevation(self, utilisateur: UtilisateurRecord) -> bool:
        """Un Visiteur demande à devenir Éditeur (statut → Extention)."""
        if utilisateur.get("droits") != DROIT_VISITEUR:
            return False
        self._utilisateurs.update(utilisateur["id"], {"droits": DROIT_EXTENTION})
        return True
