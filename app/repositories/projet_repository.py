"""Repository des projets (table BDD_Projets).

Étape 4 : lectures pour la fiche collectivité (projets liés) et le contrôle
de périmètre. Le CRUD complet arrive avec la fiche projet (étape 5).
"""

from typing import Protocol

from app.repositories.base import BaseGristRepository, ref_ids
from app.repositories.types import TABLE_PROJETS, ProjetRecord


class ProjetRepositoryProtocol(Protocol):
    def list_all(self) -> list[ProjetRecord]: ...

    def get(self, record_id: int) -> ProjetRecord | None: ...

    def create(self, fields: dict) -> int: ...

    def update(self, record_id: int, fields: dict) -> None: ...

    def collectivites_porteuses(self, projet: ProjetRecord) -> list[int]: ...


class GristProjetRepository(BaseGristRepository[ProjetRecord]):
    table_id = TABLE_PROJETS

    @staticmethod
    def collectivites_porteuses(projet: ProjetRecord) -> list[int]:
        """IDs des collectivités porteuses d'un projet (RefList)."""
        return ref_ids(projet.get("collectivites_porteuses"))
