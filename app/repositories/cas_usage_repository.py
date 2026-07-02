"""Repository des cas d'usage (table BDD_CasUsages).

Un cas d'usage peut être lié à PLUSIEURS projets (RefList ``projets``) :
la liaison AJOUTE le projet à la liste existante, sans écraser.
"""

from typing import Protocol

from app.repositories.base import (
    BaseGristRepository,
    extract_values,
    ref_ids,
    to_reflist,
)
from app.repositories.types import TABLE_CAS_USAGES, CasUsageRecord


class CasUsageRepositoryProtocol(Protocol):
    def list_all(self) -> list[CasUsageRecord]: ...

    def get(self, record_id: int) -> CasUsageRecord | None: ...

    def for_projet(self, projet_id: int) -> list[CasUsageRecord]: ...

    def themes(self) -> list[str]: ...

    def by_theme(self) -> dict[str, list[CasUsageRecord]]: ...

    def create_for_projet(self, nom: str, theme: str, projet_id: int) -> int: ...

    def link_to_projet(self, cas_id: int, projet_id: int) -> bool: ...


class GristCasUsageRepository(BaseGristRepository[CasUsageRecord]):
    table_id = TABLE_CAS_USAGES

    def for_projet(self, projet_id: int) -> list[CasUsageRecord]:
        return [
            r for r in self.list_all() if projet_id in ref_ids(r.get("projets"))
        ]

    def themes(self) -> list[str]:
        """Thèmes présents dans les cas d'usage (triés — comportement v1)."""
        themes: set[str] = set()
        for record in self.list_all():
            themes.update(extract_values(record.get("theme")))
        return sorted(themes)

    def by_theme(self) -> dict[str, list[CasUsageRecord]]:
        """Cas d'usage groupés par thème (un cas multi-thèmes apparaît
        dans chaque groupe)."""
        groupes: dict[str, list[CasUsageRecord]] = {}
        for record in self.list_all():
            if not record.get("nom"):
                continue
            for theme in extract_values(record.get("theme")):
                groupes.setdefault(theme, []).append(record)
        return groupes

    def create_for_projet(self, nom: str, theme: str, projet_id: int) -> int:
        return self.create(
            {"nom": nom, "theme": theme, "projets": to_reflist([projet_id])}
        )

    def link_to_projet(self, cas_id: int, projet_id: int) -> bool:
        """Ajoute le projet à la RefList du cas. False si cas inconnu ou déjà lié."""
        cas = self.get(cas_id)
        if cas is None:
            return False
        if projet_id in ref_ids(cas.get("projets")):
            return False
        self.add_to_reflist(cas_id, "projets", projet_id)
        return True
