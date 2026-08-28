"""Console administrateur : tri des utilisateurs, validation, garde-fous."""

import logging

from app.repositories.types import (
    DROIT_ADMINISTRATEUR,
    DROIT_EN_ATTENTE,
    UtilisateurRecord,
)
from app.repositories.utilisateur_repository import UtilisateurRepositoryProtocol
from app.services.types import DROITS_ATTRIBUABLES

logger = logging.getLogger(__name__)


class AdminService:
    def __init__(self, utilisateurs: UtilisateurRepositoryProtocol):
        self._utilisateurs = utilisateurs

    def list_users_sorted(self) -> list[UtilisateurRecord]:
        """Comptes « En attente » d'abord, puis ordre alphabétique (parité v1)."""
        return sorted(
            self._utilisateurs.list_all(),
            key=lambda u: (
                u.get("droits") != DROIT_EN_ATTENTE,
                str(u.get("nom") or "").lower(),
                str(u.get("prenom") or "").lower(),
            ),
        )

    def pending_count(self) -> int:
        return sum(
            1
            for u in self._utilisateurs.list_all()
            if u.get("droits") == DROIT_EN_ATTENTE
        )

    def update_user(
        self,
        admin: UtilisateurRecord,
        user_id: int,
        droits: str,
        collectivite_id: int,
    ) -> tuple[bool, str]:
        """Met à jour droits et collectivité. Retourne (succès, message).

        Garde-fou : un administrateur ne peut pas se retirer son propre rôle
        (sinon plus personne pour administrer).
        """
        if user_id == admin.get("id") and droits != DROIT_ADMINISTRATEUR:
            return False, "Vous ne pouvez pas retirer votre propre rôle Administrateur."
        if self._utilisateurs.get(user_id) is None:
            return False, "Utilisateur introuvable."
        fields: dict = {"collectivite": collectivite_id}
        if droits in DROITS_ATTRIBUABLES:
            fields["droits"] = droits
        self._utilisateurs.update(user_id, fields)
        return True, "Utilisateur mis à jour."
