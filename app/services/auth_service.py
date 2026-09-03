"""Workflow de validation des comptes.

Toutes les réponses visibles par l'appelant sont NEUTRES : l'existence d'un
compte ne se déduit pas de l'inscription (anti-énumération).
"""

import logging
from datetime import datetime

from app.repositories.types import (
    DROIT_EXTENTION,
    DROIT_LECTEUR,
    DROIT_VISITEUR,
    UtilisateurRecord,
)
from app.repositories.utilisateur_repository import UtilisateurRepositoryProtocol
from app.services.types import InscriptionForm

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(
        self,
        utilisateurs: UtilisateurRepositoryProtocol,
    ):
        self._utilisateurs = utilisateurs

    def register(self, formulaire: InscriptionForm) -> None:
        """Crée une demande d'accès « En attente ». Réponse neutre.

        Si l'email a déjà un compte, on n'en crée pas un second.
        """
        existant = self._utilisateurs.get_by_email(formulaire.email)
        if existant is not None:
            logger.info("Inscription sur email existant — aucun doublon créé")
            return
        self._utilisateurs.create_pending(
            {
                "prenom": formulaire.prenom,
                "nom": formulaire.nom,
                "email": formulaire.email,
                "organisation": formulaire.organisation,
                "collectivite": formulaire.collectivite_id,
                "date_inscription": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
        )

    def request_elevation(self, utilisateur: UtilisateurRecord) -> bool:
        """Un Lecteur demande à devenir Éditeur (statut → Extention).

        « Visiteur » (legacy) reste accepté : un compte encore porteur de
        cette valeur en base peut demander l'élévation avant migration.
        """
        if utilisateur.get("droits") not in (DROIT_VISITEUR, DROIT_LECTEUR):
            return False
        self._utilisateurs.update(utilisateur["id"], {"droits": DROIT_EXTENTION})
        return True
