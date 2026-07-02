"""Lectures des tables de référence : connectivités, départements, contrats,
solutions — et choix configurés (widgetOptions) des colonnes Choice/ChoiceList.

Tables quasi statiques, servies depuis le cache TTL. Lecture seule.
"""

import json
import logging
from typing import Protocol

from app.repositories.base import BaseGristRepository, GristClientProtocol, R
from app.repositories.cache import TableCache
from app.repositories.types import (
    TABLE_CONNECTIVITES,
    TABLE_CONTRATS,
    TABLE_DEPARTEMENTS,
    TABLE_SOLUTIONS,
    ConnectiviteRecord,
    ContratRecord,
    DepartementRecord,
    SolutionRecord,
)

logger = logging.getLogger(__name__)


class ReferenceRepositoryProtocol(Protocol):
    def list_connectivites(self) -> list[ConnectiviteRecord]: ...

    def list_departements(self) -> list[DepartementRecord]: ...

    def list_contrats(self) -> list[ContratRecord]: ...

    def list_solutions(self) -> list[SolutionRecord]: ...

    def get_configured_choices(self, table_id: str) -> dict[str, list[str]]: ...


class _TableReader(BaseGristRepository[R]):
    """Lecteur générique d'une table de référence (pas d'écriture)."""

    def __init__(self, table_id: str, grist: GristClientProtocol, cache: TableCache):
        self.table_id = table_id
        super().__init__(grist, cache)


class GristReferenceRepository(ReferenceRepositoryProtocol):
    def __init__(self, grist: GristClientProtocol, cache: TableCache):
        self._grist = grist
        self._cache = cache
        self._connectivites = _TableReader[ConnectiviteRecord](
            TABLE_CONNECTIVITES, grist, cache
        )
        self._departements = _TableReader[DepartementRecord](
            TABLE_DEPARTEMENTS, grist, cache
        )
        self._contrats = _TableReader[ContratRecord](TABLE_CONTRATS, grist, cache)
        self._solutions = _TableReader[SolutionRecord](TABLE_SOLUTIONS, grist, cache)

    def get_configured_choices(self, table_id: str) -> dict[str, list[str]]:
        """Choix CONFIGURÉS des colonnes Choice/ChoiceList (piège Grist n°7 :
        lire widgetOptions, pas seulement les valeurs utilisées)."""
        cle_cache = f"__choices__{table_id}"
        en_cache = self._cache.get(cle_cache)
        if en_cache is not None:
            return en_cache[0] if en_cache else {}
        try:
            status, colonnes = self._grist.list_cols(table_id, hidden=True)
        except Exception as exc:
            # Dégradation douce : un formulaire sans liste de choix vaut mieux
            # qu'une page en erreur (comportement v1)
            logger.warning("Choix configurés indisponibles (%s) : %s",
                           table_id, type(exc).__name__)
            return {}
        if status >= 300:
            logger.warning("Choix configurés indisponibles (%s) : HTTP %s",
                           table_id, status)
            return {}
        resultat: dict[str, list[str]] = {}
        for colonne in colonnes:
            options = colonne.get("fields", {}).get("widgetOptions")
            if not options:
                continue
            try:
                choix = json.loads(options).get("choices")
            except (ValueError, TypeError):
                continue
            if choix:
                resultat[colonne["id"]] = [str(c) for c in choix]
        self._cache.set(cle_cache, [resultat])
        return resultat

    def list_connectivites(self) -> list[ConnectiviteRecord]:
        return self._connectivites.list_all()

    def list_departements(self) -> list[DepartementRecord]:
        return sorted(
            self._departements.list_all(), key=lambda d: str(d.get("num_dep", ""))
        )

    def list_contrats(self) -> list[ContratRecord]:
        return self._contrats.list_all()

    def list_solutions(self) -> list[SolutionRecord]:
        return self._solutions.list_all()
