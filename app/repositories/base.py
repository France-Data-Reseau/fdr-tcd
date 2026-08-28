"""Repository générique au-dessus de pygrister.

Règles (voir AGENTS.md) :
- les idiomes Grist — tuples ``(status, data)``, listes ``['L', id…]`` — ne
  remontent JAMAIS au-dessus de cette couche ;
- l'invalidation du cache est déclenchée ICI, dans les méthodes d'écriture,
  jamais par les services ;
- les erreurs sont reformulées sans doc ID, URL ni clé API (GristError).

Pièges Grist couverts (BRIEF §5) :
- n°2 : PATCH par lots à champs homogènes, repli unitaire en cas de 400 ;
- n°3 : RefList ``['L', id1, id2…]``, Ref simple = int (0 = vide) ;
- n°5 : les champs formule ne sont jamais envoyés (responsabilité des appelants,
  les TypedDicts de ``types.py`` les signalent) ;
- n°6 : extraction tolérante (les formules renvoient parfois des listes simples).
"""

import logging
from collections.abc import Mapping
from typing import Any, Generic, Protocol, TypeVar, cast

import requests

from app.repositories.cache import TableCache

logger = logging.getLogger(__name__)


class GristClientProtocol(Protocol):
    """Surface minimale du client Grist utilisée par les repositories.

    pygrister.GristApi la satisfait ; les tests fournissent des doubles.
    """

    def list_records(self, table_id: str) -> tuple[int, Any]: ...

    def add_records(self, table_id: str, records: list[dict]) -> tuple[int, Any]: ...

    def update_records(self, table_id: str, records: list[dict]) -> tuple[int, Any]: ...

    def list_cols(self, table_id: str, hidden: bool = False) -> tuple[int, Any]: ...


R = TypeVar("R", bound=Mapping[str, Any])


class GristError(Exception):
    """Erreur d'accès à Grist — message sobre, sans détail sensible."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------------------
# Helpers Ref / RefList / ChoiceList
# ---------------------------------------------------------------------------


def ref_ids(value: Any) -> list[int]:
    """IDs d'un champ Ref/RefList : ``['L', id…]`` (RefList), int (Ref) ou None."""
    if isinstance(value, list) and value and value[0] == "L":
        return [x for x in value[1:] if isinstance(x, int) and x]
    if isinstance(value, int) and not isinstance(value, bool) and value:
        return [value]
    return []


def to_reflist(ids: list[int]) -> list:
    """Format d'écriture d'une RefList : ``['L', id1, id2…]``."""
    return ["L"] + [int(i) for i in ids]


def extract_values(value: Any) -> list[str]:
    """Valeurs d'un champ ChoiceList/Text, tolérant aux listes simples (formules)."""
    if not value:
        return []
    if isinstance(value, list):
        items = value[1:] if value[0] == "L" else value
        return [str(item).strip() for item in items if item and str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def first_value(record: dict, field: str) -> str:
    """Première valeur d'un champ (pour les comparaisons dans les templates)."""
    values = extract_values(record.get(field))
    return values[0] if values else ""


# ---------------------------------------------------------------------------
# Repository de base
# ---------------------------------------------------------------------------


class BaseGristRepository(Generic[R]):
    """CRUD générique sur une table Grist, avec cache TTL et erreurs sobres.

    ``R`` est le TypedDict du record de la table (voir ``types.py``).
    """

    table_id: str = ""

    def __init__(self, grist: GristClientProtocol, cache: TableCache):
        if not self.table_id:
            raise ValueError("table_id doit être défini par la sous-classe")
        self._grist = grist
        self._cache = cache

    # --- Lectures ---

    def list_all(self) -> list[R]:
        """Tous les records de la table (cache TTL)."""
        cached = self._cache.get(self.table_id)
        if cached is not None:
            return cast(list[R], cached)
        status, records = self._call("lecture", self._grist.list_records, self.table_id)
        self._check(status, records, "lecture")
        self._cache.set(self.table_id, records)
        return cast(list[R], records)

    def get(self, record_id: int) -> R | None:
        """Un record par son id, ou None s'il n'existe pas."""
        for record in self.list_all():
            if record.get("id") == record_id:
                return record
        return None

    # --- Écritures (invalident le cache de la table) ---

    def create(self, fields: dict) -> int:
        """Crée un record, retourne son id."""
        status, result = self._call(
            "création", self._grist.add_records, self.table_id, [dict(fields)]
        )
        self._check(status, result, "création")
        self._cache.invalidate(self.table_id)
        return int(result[0])

    def update(self, record_id: int, fields: dict) -> None:
        """Met à jour un record."""
        record = {"id": record_id, **fields}
        status, result = self._call(
            "mise à jour", self._grist.update_records, self.table_id, [record]
        )
        self._check(status, result, "mise à jour")
        self._cache.invalidate(self.table_id)

    def update_many(self, records: list[dict]) -> None:
        """Met à jour plusieurs records.

        L'API Grist exige que tous les records d'un lot PATCH aient les MÊMES
        champs (piège n°2) : on regroupe par jeu de champs homogène, et en cas
        de 400 résiduel on retombe en écriture unitaire.
        """
        groups: dict[frozenset[str], list[dict]] = {}
        for record in records:
            key = frozenset(record.keys()) - {"id"}
            groups.setdefault(key, []).append(record)

        for batch in groups.values():
            # update_records mutile ses entrées (pop('id')) : toujours des copies
            status, result = self._call(
                "mise à jour", self._grist.update_records, self.table_id,
                [dict(r) for r in batch],
            )
            if status == 400:
                logger.warning(
                    "PATCH par lot refusé sur %s — repli en écriture unitaire (%d records)",
                    self.table_id, len(batch),
                )
                for record in batch:
                    status_u, result_u = self._call(
                        "mise à jour", self._grist.update_records, self.table_id,
                        [dict(record)],
                    )
                    self._check(status_u, result_u, "mise à jour")
            else:
                self._check(status, result, "mise à jour")
        self._cache.invalidate(self.table_id)

    def add_to_reflist(self, record_id: int, field: str, new_id: int) -> None:
        """Ajoute un id à un champ RefList sans écraser les valeurs existantes."""
        record = self.get(record_id)
        if record is None:
            raise GristError(f"Record {record_id} introuvable ({self.table_id})", 404)
        ids = ref_ids(record.get(field))
        if new_id in ids:
            return
        ids.append(new_id)
        self.update(record_id, {field: to_reflist(ids)})

    # --- Interne ---

    def _call(self, action: str, fn, *args, **kwargs) -> tuple[int, Any]:
        """Exécute un appel pygrister en reformulant les erreurs réseau."""
        try:
            return fn(*args, **kwargs)
        except requests.RequestException as exc:
            # Jamais l'URL ni le doc ID dans le message remonté
            logger.error("Grist injoignable (%s sur %s) : %s",
                         action, self.table_id, type(exc).__name__)
            raise GristError(f"Service de données indisponible ({action})") from exc

    def _check(self, status: int, data: Any, action: str) -> None:
        if status >= 300:
            logger.error("Erreur Grist %s (%s sur %s)", status, action, self.table_id)
            raise GristError(f"Échec {action} ({status})", status)
