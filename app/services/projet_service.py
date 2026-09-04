"""Fiche projet et sous-objets : choix, agrégation, création/édition, liaisons.

Règles :
- les champs FORMULE (themes, region, partenaires, cas_usages) ne sont
  JAMAIS écrits (piège Grist n°5) ;
- pas de transactions Grist : à la création d'un projet, l'objet est créé
  PUIS lié à la collectivité — un échec de liaison est journalisé et n'annule
  pas la création (état atteint tracé, voir AGENTS.md) ;
- les RefList s'écrivent ['L', id…] via les helpers de la couche repository.
"""

import logging

from app.repositories.base import extract_values, to_reflist
from app.repositories.cas_usage_repository import CasUsageRepositoryProtocol
from app.repositories.collectivite_repository import CollectiviteRepositoryProtocol
from app.repositories.document_repository import DocumentRepositoryProtocol
from app.repositories.partenaire_repository import PartenaireRepositoryProtocol
from app.repositories.programme_repository import ProgrammeRepositoryProtocol
from app.repositories.projet_repository import ProjetRepositoryProtocol
from app.repositories.reference_repository import ReferenceRepositoryProtocol
from app.repositories.types import TABLE_PROJETS, ProjetRecord
from app.services.types import (
    CasUsageCreationForm,
    DocumentForm,
    PartenaireForm,
    ProgrammeForm,
    ProjetForm,
)

logger = logging.getLogger(__name__)


class ProjetService:
    def __init__(
        self,
        projets: ProjetRepositoryProtocol,
        collectivites: CollectiviteRepositoryProtocol,
        references: ReferenceRepositoryProtocol,
        cas_usages: CasUsageRepositoryProtocol,
        partenaires: PartenaireRepositoryProtocol,
        programmes: ProgrammeRepositoryProtocol,
        documents: DocumentRepositoryProtocol,
    ):
        self._projets = projets
        self._collectivites = collectivites
        self._references = references
        self._cas_usages = cas_usages
        self._partenaires = partenaires
        self._programmes = programmes
        self._documents = documents

    # --- Choix des formulaires ---

    def form_choices(self) -> dict:
        """Choix configurés (widgetOptions) + valeurs utilisées, et tables de
        référence pour les multi-sélections (comportement v1)."""
        configures = self._references.get_configured_choices(TABLE_PROJETS)
        records = self._projets.list_all()
        choix: dict[str, list[str]] = {}
        for champ in ("avancement", "echelle", "mutualisation", "soutien"):
            utilises: set[str] = set()
            for record in records:
                utilises.update(extract_values(record.get(champ)))
            base = configures.get(champ, [])
            choix[champ] = list(base) + sorted(utilises - set(base))
        return {
            **choix,
            "connectivites": self._references.list_connectivites(),
            "solutions": self._references.list_solutions(),
            "contrats": self._references.list_contrats(),
            "departements": self._references.list_departements(),
        }

    # --- Sous-formulaires (compteurs + listes de la fiche) ---

    def sous_formulaires(self, projet: ProjetRecord) -> dict:
        projet_id = projet["id"]
        return {
            "cas_usages": self._cas_usages.for_projet(projet_id),
            "partenaires": self._partenaires.for_projet(projet_id),
            "programmes": self._programmes.for_projet(projet_id),
            "documents": self._documents.for_projet(projet_id),
        }

    # --- Création / édition du projet ---

    def create(self, formulaire: ProjetForm, collectivite_id: int) -> int:
        fields = self._fields(formulaire)
        if collectivite_id:
            fields["collectivites_porteuses"] = to_reflist([collectivite_id])
        new_id = self._projets.create(fields)
        # Liaison inverse collectivité → projet (pas de transaction : un échec
        # ici laisse le projet créé, la recherche inverse le retrouvera)
        if collectivite_id:
            try:
                self._collectivites.add_to_reflist(
                    collectivite_id, "projets", new_id
                )
            except Exception as exc:
                # Tag stable pour la supervision : record créé sans sa liaison
                # inverse (pas de transaction Grist) — intervention admin possible,
                # la recherche inverse reste fonctionnelle entre-temps.
                logger.critical(
                    "RECORD_ORPHELIN projet=%s collectivite=%s liaison projets "
                    "échouée (%s)",
                    new_id, collectivite_id, type(exc).__name__,
                )
        return new_id

    def update(self, record_id: int, formulaire: ProjetForm) -> None:
        self._projets.update(record_id, self._fields(formulaire))

    @staticmethod
    def _fields(formulaire: ProjetForm) -> dict:
        # themes, region, partenaires, cas_usages : formules — exclues.
        return {
            "nom": formulaire.nom,
            "description": formulaire.description,
            "avancement": formulaire.avancement,
            "echelle": formulaire.echelle,
            "mutualisation": formulaire.mutualisation,
            "soutien": formulaire.soutien,
            "dev_interne": formulaire.dev_interne,
            "connectivites": to_reflist(formulaire.connectivites),
            "solutions": to_reflist(formulaire.solutions),
            "contrats": to_reflist(formulaire.contrats),
            "departements": to_reflist(formulaire.departements),
        }

    # --- Cas d'usage ---

    def cas_usage_page_data(self, projet_id: int) -> dict:
        """Tous les thèmes (même vides après filtrage) + cas liables
        (non déjà liés à CE projet) — comportement v1."""
        deja_lies = {c["id"] for c in self._cas_usages.for_projet(projet_id)}
        par_theme = self._cas_usages.by_theme()
        themes = self._cas_usages.themes()
        return {
            "themes": themes,
            "cas_usage_by_theme": {
                theme: [
                    c for c in par_theme.get(theme, []) if c["id"] not in deja_lies
                ]
                for theme in themes
            },
        }

    def link_cas_usages(self, projet_id: int, cas_ids: list[int]) -> int:
        """Lie des cas d'usage existants au projet. Retourne le nombre lié."""
        lies = 0
        for cas_id in cas_ids:
            if self._cas_usages.link_to_projet(cas_id, projet_id):
                lies += 1
        return lies

    def create_cas_usage(
        self, projet_id: int, formulaire: CasUsageCreationForm
    ) -> int:
        return self._cas_usages.create_for_projet(
            formulaire.nom, formulaire.theme, projet_id
        )

    # --- Partenaires ---

    def link_partenaire(self, projet_id: int, partenaire_id: int) -> bool:
        return self._partenaires.link_to_projet(partenaire_id, projet_id)

    def create_partenaire(
        self, projet_id: int, formulaire: PartenaireForm
    ) -> int:
        return self._partenaires.create(
            {
                "nom": formulaire.nom,
                "roles": formulaire.roles,
                "url": formulaire.url,
                "projets": to_reflist([projet_id]),
            }
        )

    def partenaire_choices(self) -> dict:
        roles: set[str] = set()
        for record in self._partenaires.list_all():
            roles.update(extract_values(record.get("roles")))
        return {
            "partenaires_existants": self._partenaires.list_all(),
            "roles": sorted(roles),
        }

    # --- Programmes ---

    def link_programme(self, projet_id: int, programme_id: int) -> bool:
        return self._programmes.link_to_projet(programme_id, projet_id)

    def create_programme(self, projet_id: int, formulaire: ProgrammeForm) -> int:
        return self._programmes.create(
            {
                "nom": formulaire.nom,
                "info_web": formulaire.info_web,
                "echelle": formulaire.echelle,
                "projets": to_reflist([projet_id]),
            }
        )

    def programme_choices(self) -> dict:
        echelles: set[str] = set()
        for record in self._programmes.list_all():
            echelles.update(extract_values(record.get("echelle")))
        return {
            "programmes_existants": self._programmes.list_all(),
            "echelle": sorted(echelles),
        }

    # --- Documents ---

    def create_document(self, projet_id: int, formulaire: DocumentForm) -> int:
        return self._documents.create(
            {
                "titre": formulaire.titre,
                "lien": formulaire.lien,
                "type": formulaire.type,
                "projet": projet_id,
            }
        )
