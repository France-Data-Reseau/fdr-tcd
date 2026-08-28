"""Repository des utilisateurs (table BDD_Utilisateurs).

Les droits sont EXCLUSIVEMENT français dans l'application : les valeurs
anglaises héritées (Administrator, Editor…) sont normalisées à la lecture
et ne sont jamais écrites.
"""

from typing import Protocol, cast

from app.repositories.base import BaseGristRepository
from app.repositories.types import (
    DROIT_EN_ATTENTE,
    DROITS_EN_VERS_FR,
    TABLE_UTILISATEURS,
    UtilisateurRecord,
)


class UtilisateurRepositoryProtocol(Protocol):
    def list_all(self) -> list[UtilisateurRecord]: ...

    def get(self, record_id: int) -> UtilisateurRecord | None: ...

    def get_by_email(self, email: str) -> UtilisateurRecord | None: ...

    def create_pending(self, fields: dict) -> int: ...

    def update(self, record_id: int, fields: dict) -> None: ...


class GristUtilisateurRepository(BaseGristRepository[UtilisateurRecord]):
    table_id = TABLE_UTILISATEURS

    def list_all(self) -> list[UtilisateurRecord]:
        return [self._normalise(r) for r in super().list_all()]

    def get(self, record_id: int) -> UtilisateurRecord | None:
        record = super().get(record_id)
        return self._normalise(record) if record else None

    def get_by_email(self, email: str) -> UtilisateurRecord | None:
        """Recherche par email, insensible à la casse (comportement v1)."""
        cherche = email.strip().lower()
        if not cherche:
            return None
        for record in self.list_all():
            if str(record.get("email", "")).strip().lower() == cherche:
                return record
        return None

    def create_pending(self, fields: dict) -> int:
        """Crée un utilisateur en attente de validation admin."""
        fields = dict(fields)
        fields["droits"] = DROIT_EN_ATTENTE
        return self.create(fields)

    @staticmethod
    def _normalise(record: UtilisateurRecord) -> UtilisateurRecord:
        """Normalise les droits anglais hérités vers le français."""
        droits = record.get("droits", "")
        if droits in DROITS_EN_VERS_FR:
            record = cast(
                UtilisateurRecord, {**record, "droits": DROITS_EN_VERS_FR[droits]}
            )
        return record
