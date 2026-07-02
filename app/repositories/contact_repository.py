"""Repository des contacts (table BDD_Contacts).

Liaison projet : ``projets`` de type TEXT contenant le NOM du projet —
dette v1 assumée (renommer un projet orpheline ses contacts), conservée
pour l'iso-fonctionnel. Voir README « Limites assumées ».
"""

from typing import Protocol

from app.repositories.base import BaseGristRepository
from app.repositories.types import TABLE_CONTACTS, ContactRecord


class ContactRepositoryProtocol(Protocol):
    def for_projet_nom(self, projet_nom: str) -> list[ContactRecord]: ...

    def create(self, fields: dict) -> int: ...

    def update_many(self, records: list[dict]) -> None: ...


class GristContactRepository(BaseGristRepository[ContactRecord]):
    table_id = TABLE_CONTACTS

    def for_projet_nom(self, projet_nom: str) -> list[ContactRecord]:
        if not projet_nom:
            return []
        return [r for r in self.list_all() if r.get("projets") == projet_nom]
