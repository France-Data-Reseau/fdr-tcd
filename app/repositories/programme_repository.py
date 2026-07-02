"""Repository des programmes (table BDD_Programmes).

Liaison projet : RefList ``projets`` côté programme (recherche inverse).
"""

from typing import Protocol

from app.repositories.base import BaseGristRepository, ref_ids
from app.repositories.types import TABLE_PROGRAMMES, ProgrammeRecord


class ProgrammeRepositoryProtocol(Protocol):
    def list_all(self) -> list[ProgrammeRecord]: ...

    def get(self, record_id: int) -> ProgrammeRecord | None: ...

    def for_projet(self, projet_id: int) -> list[ProgrammeRecord]: ...

    def create(self, fields: dict) -> int: ...

    def link_to_projet(self, programme_id: int, projet_id: int) -> bool: ...


class GristProgrammeRepository(BaseGristRepository[ProgrammeRecord]):
    table_id = TABLE_PROGRAMMES

    def for_projet(self, projet_id: int) -> list[ProgrammeRecord]:
        return [r for r in self.list_all() if projet_id in ref_ids(r.get("projets"))]

    def link_to_projet(self, programme_id: int, projet_id: int) -> bool:
        if self.get(programme_id) is None:
            return False
        self.add_to_reflist(programme_id, "projets", projet_id)
        return True
