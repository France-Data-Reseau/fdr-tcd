"""Repository des partenaires (table BDD_Partenaires).

Liaison projet : RefList ``Projets`` côté partenaire (recherche inverse).
"""

from typing import Protocol

from app.repositories.base import BaseGristRepository, ref_ids
from app.repositories.types import TABLE_PARTENAIRES, PartenaireRecord


class PartenaireRepositoryProtocol(Protocol):
    def list_all(self) -> list[PartenaireRecord]: ...

    def get(self, record_id: int) -> PartenaireRecord | None: ...

    def for_projet(self, projet_id: int) -> list[PartenaireRecord]: ...

    def create(self, fields: dict) -> int: ...

    def link_to_projet(self, partenaire_id: int, projet_id: int) -> bool: ...


class GristPartenaireRepository(BaseGristRepository[PartenaireRecord]):
    table_id = TABLE_PARTENAIRES

    def for_projet(self, projet_id: int) -> list[PartenaireRecord]:
        return [r for r in self.list_all() if projet_id in ref_ids(r.get("projets"))]

    def link_to_projet(self, partenaire_id: int, projet_id: int) -> bool:
        if self.get(partenaire_id) is None:
            return False
        self.add_to_reflist(partenaire_id, "projets", projet_id)
        return True
