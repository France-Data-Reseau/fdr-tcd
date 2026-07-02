"""Fiche collectivité : choix des formulaires, projets liés, création/édition.

Règles :
- les champs FORMULE (num_dep, reg) ne sont JAMAIS écrits (piège Grist n°5) ;
- seuls les champs de la liste blanche du formulaire sont transmis ;
- les valeurs Choice sont contrôlées contre les choix configurés + utilisés.
"""

from app.repositories.base import extract_values, ref_ids
from app.repositories.collectivite_repository import CollectiviteRepositoryProtocol
from app.repositories.projet_repository import ProjetRepositoryProtocol
from app.repositories.reference_repository import ReferenceRepositoryProtocol
from app.repositories.types import TABLE_COLLECTIVITES, CollectiviteRecord, ProjetRecord
from app.services.types import CollectiviteForm


class CollectiviteService:
    def __init__(
        self,
        collectivites: CollectiviteRepositoryProtocol,
        projets: ProjetRepositoryProtocol,
        references: ReferenceRepositoryProtocol,
    ):
        self._collectivites = collectivites
        self._projets = projets
        self._references = references

    # --- Choix des formulaires ---

    def form_choices(self) -> dict:
        """Choix configurés (widgetOptions) complétés des valeurs utilisées,
        dans l'ordre configuré (comportement v1)."""
        configures = self._references.get_configured_choices(TABLE_COLLECTIVITES)
        records = self._collectivites.list_all()
        choix: dict[str, list[str]] = {}
        for champ in ("statut", "couverture"):
            utilises: set[str] = set()
            for record in records:
                utilises.update(extract_values(record.get(champ)))
            base = configures.get(champ, [])
            choix[champ] = list(base) + sorted(utilises - set(base))
        return {
            "statut": choix["statut"],
            "couverture": choix["couverture"],
            "departements": self._references.list_departements(),
        }

    def is_valid_choice(self, champ: str, valeur: str) -> bool:
        if not valeur:
            return True  # « — » (vide) toujours accepté
        return valeur in self.form_choices().get(champ, [])

    # --- Projets liés ---

    def projets_lies(self, collectivite: CollectiviteRecord) -> list[ProjetRecord]:
        """RefList directe + recherche inverse (robustesse v1 conservée)."""
        ids = set(ref_ids(collectivite.get("projets")))
        tous = self._projets.list_all()
        cid = collectivite["id"]
        for projet in tous:
            if cid in self._projets.collectivites_porteuses(projet):
                ids.add(projet["id"])
        return [p for p in tous if p["id"] in ids]

    # --- Écritures (liste blanche, jamais les formules) ---

    def create(self, formulaire: CollectiviteForm) -> int:
        return self._collectivites.create(self._fields(formulaire))

    def update(self, record_id: int, formulaire: CollectiviteForm) -> None:
        self._collectivites.update(record_id, self._fields(formulaire))

    @staticmethod
    def _fields(formulaire: CollectiviteForm) -> dict:
        # num_dep et region sont des formules Grist (déduites de departement) : exclues.
        return {
            "nom": formulaire.nom,
            "siren": formulaire.siren,
            "statut": formulaire.statut,
            "couverture": formulaire.couverture,
            "departement": formulaire.departement,
            "site_web": formulaire.site_web,
            "adresse": formulaire.adresse,
        }
