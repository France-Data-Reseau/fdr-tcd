"""Repository des collectivités (table BDD_Collectivites).

Étape 2 : lectures pour l'inscription et le menu. Le CRUD complet
(fiche collectivité, projets liés) arrive avec l'étape complétion.
"""

from typing import Protocol

from app.repositories.base import BaseGristRepository
from app.repositories.types import TABLE_COLLECTIVITES, CollectiviteRecord


class CollectiviteRepositoryProtocol(Protocol):
    def list_all(self) -> list[CollectiviteRecord]: ...

    def list_sorted(self) -> list[CollectiviteRecord]: ...

    def get(self, record_id: int) -> CollectiviteRecord | None: ...

    def get_nom(self, record_id: int) -> str: ...

    def create(self, fields: dict) -> int: ...

    def update(self, record_id: int, fields: dict) -> None: ...

    def add_to_reflist(self, record_id: int, field: str, new_id: int) -> None: ...


class GristCollectiviteRepository(BaseGristRepository[CollectiviteRecord]):
    table_id = TABLE_COLLECTIVITES

    def list_sorted(self) -> list[CollectiviteRecord]:
        """Collectivités triées par nom (sélecteurs des formulaires)."""
        return sorted(
            self.list_all(), key=lambda r: str(r.get("nom") or "").lower()
        )

    def get_nom(self, record_id: int) -> str:
        record = self.get(record_id)
        if record is None:
            return ""
        return str(record.get("nom") or "")
