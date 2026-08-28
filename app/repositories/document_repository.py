"""Repository des documents (table BDD_Documents).

Liaison projet : Ref simple ``projet``. Le sous-objet « document » est un
LIEN (titre + URL) — aucun upload de fichier (le champ Attachments de Grist
n'est pas exposé par l'application, comme en v1).
"""

from typing import Protocol

from app.repositories.base import BaseGristRepository
from app.repositories.types import TABLE_DOCUMENTS, DocumentRecord


class DocumentRepositoryProtocol(Protocol):
    def list_all(self) -> list[DocumentRecord]: ...

    def for_projet(self, projet_id: int) -> list[DocumentRecord]: ...

    def create(self, fields: dict) -> int: ...


class GristDocumentRepository(BaseGristRepository[DocumentRecord]):
    table_id = TABLE_DOCUMENTS

    def for_projet(self, projet_id: int) -> list[DocumentRecord]:
        return [r for r in self.list_all() if r.get("projet") == projet_id]
