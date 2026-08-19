"""Types du domaine côté services : droits et modèles Pydantic des formulaires.

Les valeurs des droits vivent dans ``repositories/types.py`` (couche données,
qui en a besoin pour la normalisation) — re-exportées ici comme référence
unique pour les services, les dépendances d'accès et les templates.

Chaque formulaire HTML a son modèle : types, longueurs maximales, emails
valides (faiblesse v1 n°4). Les erreurs de validation produisent un flash
côté route, jamais de 500.
"""

from pydantic import BaseModel, EmailStr, Field, HttpUrl, field_validator

from app.repositories.types import (
    DROIT_ADMINISTRATEUR,
    DROIT_EDITEUR,
    DROIT_EN_ATTENTE,
    DROIT_EXTENTION,
    DROIT_VISITEUR,
    DROITS,
)


class InscriptionForm(BaseModel):
    prenom: str = Field(min_length=1, max_length=100)
    nom: str = Field(min_length=1, max_length=100)
    email: EmailStr
    organisation: str = Field(default="", max_length=200)
    collectivite_id: int = Field(default=0, ge=0)
    # Nom de la collectivité résolu par la route (pour l'email de notification)
    collectivite_nom: str = Field(default="", max_length=200)

    @field_validator("prenom", "nom", "organisation", mode="before")
    @classmethod
    def _nettoyer(cls, valeur: object) -> object:
        return valeur.strip() if isinstance(valeur, str) else valeur

def _url_http_ou_vide(valeur: str) -> str:
    """Champ URL optionnel : vide, ou http(s) exclusivement (anti
    ``javascript:`` — S8). Les URL sans schéma reçoivent https://."""
    valeur = valeur.strip()
    if not valeur:
        return ""
    if "://" not in valeur:
        valeur = f"https://{valeur}"
    if not valeur.lower().startswith(("http://", "https://")):
        raise ValueError("URL invalide : seuls http(s) sont acceptés")
    HttpUrl(valeur)  # validation structurelle complète
    return valeur


class CollectiviteForm(BaseModel):
    nom: str = Field(min_length=1, max_length=200)
    siren: int = Field(default=0, ge=0)
    statut: str = Field(default="", max_length=100)
    couverture: str = Field(default="", max_length=100)
    departement: int = Field(default=0, ge=0)  # Ref:BDD_Departements (0 = vide)
    site_web: str = Field(default="", max_length=300)
    adresse: str = Field(default="", max_length=300)

    @field_validator("nom", "statut", "couverture", "adresse", mode="before")
    @classmethod
    def _nettoyer(cls, valeur: object) -> object:
        return valeur.strip() if isinstance(valeur, str) else valeur

    @field_validator("site_web")
    @classmethod
    def _valider_url(cls, valeur: str) -> str:
        return _url_http_ou_vide(valeur)

    @field_validator("siren", "departement", mode="before")
    @classmethod
    def _entier_tolerant(cls, valeur: object) -> object:
        if valeur is None or (isinstance(valeur, str) and not valeur.strip()):
            return 0
        return valeur


class ProjetForm(BaseModel):
    """Fiche projet. Les listes sont des IDs de référence (entiers > 0) ;
    les champs formule (themes, region, partenaires, cas_usages) ne
    figurent volontairement PAS ici — jamais écrits."""

    nom: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    avancement: str = Field(default="", max_length=100)
    echelle: str = Field(default="", max_length=100)
    mutualisation: str = Field(default="", max_length=100)
    soutien: str = Field(default="", max_length=100)
    dev_interne: bool = False
    connectivites: list[int] = Field(default_factory=list)
    solutions: list[int] = Field(default_factory=list)
    contrats: list[int] = Field(default_factory=list)
    departements: list[int] = Field(default_factory=list)

    @field_validator("nom", "description", "avancement", "echelle",
                     "mutualisation", "soutien", mode="before")
    @classmethod
    def _nettoyer(cls, valeur: object) -> object:
        return valeur.strip() if isinstance(valeur, str) else valeur

    @field_validator("connectivites", "solutions", "contrats",
                     "departements")
    @classmethod
    def _ids_positifs(cls, ids: list[int]) -> list[int]:
        return [i for i in ids if i > 0]


class CasUsageSelectionForm(BaseModel):
    """Liaison de cas d'usage existants (mode « select »)."""

    cas_usage_ids: list[int] = Field(min_length=1)

    @field_validator("cas_usage_ids")
    @classmethod
    def _ids_positifs(cls, ids: list[int]) -> list[int]:
        ids = [i for i in ids if i > 0]
        if not ids:
            raise ValueError("aucun cas d'usage sélectionné")
        return ids


class CasUsageCreationForm(BaseModel):
    """Création d'un nouveau cas d'usage (mode « create »)."""

    nom: str = Field(min_length=1, max_length=200)
    theme: str = Field(default="", max_length=100)

    @field_validator("nom", "theme", mode="before")
    @classmethod
    def _nettoyer(cls, valeur: object) -> object:
        return valeur.strip() if isinstance(valeur, str) else valeur


class PartenaireForm(BaseModel):
    nom: str = Field(min_length=1, max_length=200)
    roles: str = Field(default="", max_length=100)
    url: str = Field(default="", max_length=300)

    @field_validator("nom", "roles", mode="before")
    @classmethod
    def _nettoyer(cls, valeur: object) -> object:
        return valeur.strip() if isinstance(valeur, str) else valeur

    @field_validator("url")
    @classmethod
    def _valider_url(cls, valeur: str) -> str:
        return _url_http_ou_vide(valeur)


class ProgrammeForm(BaseModel):
    nom: str = Field(min_length=1, max_length=200)
    info_web: str = Field(default="", max_length=300)
    echelle: str = Field(default="", max_length=100)

    @field_validator("nom", "echelle", mode="before")
    @classmethod
    def _nettoyer(cls, valeur: object) -> object:
        return valeur.strip() if isinstance(valeur, str) else valeur

    @field_validator("info_web")
    @classmethod
    def _valider_url(cls, valeur: str) -> str:
        return _url_http_ou_vide(valeur)


class DocumentForm(BaseModel):
    titre: str = Field(min_length=1, max_length=300)
    lien: str = Field(default="", max_length=300)
    type: str = Field(default="", max_length=100)

    @field_validator("titre", "type", mode="before")
    @classmethod
    def _nettoyer(cls, valeur: object) -> object:
        return valeur.strip() if isinstance(valeur, str) else valeur

    @field_validator("lien")
    @classmethod
    def _valider_url(cls, valeur: str) -> str:
        return _url_http_ou_vide(valeur)


class ContactForm(BaseModel):
    prenom: str = Field(min_length=1, max_length=100)
    nom: str = Field(min_length=1, max_length=100)
    elu: bool = False
    fonction: str = Field(default="", max_length=200)
    email: str = Field(default="", max_length=200)
    telephone: str = Field(default="", max_length=30)
    mobile: str = Field(default="", max_length=30)

    @field_validator("prenom", "nom", "fonction", "telephone", "mobile",
                     mode="before")
    @classmethod
    def _nettoyer(cls, valeur: object) -> object:
        return valeur.strip() if isinstance(valeur, str) else valeur

    @field_validator("email", mode="before")
    @classmethod
    def _email_ou_vide(cls, valeur: object) -> object:
        if isinstance(valeur, str):
            valeur = valeur.strip()
            if not valeur:
                return ""
            # Validation structurelle sans imposer EmailStr sur le champ
            # (le champ est optionnel)
            from pydantic import TypeAdapter

            TypeAdapter(EmailStr).validate_python(valeur)
        return valeur

# Droits attribuables depuis la console administrateur (parité v1 :
# « Extention » est un état transitoire demandé par l'utilisateur, pas attribué)
DROITS_ATTRIBUABLES = (
    DROIT_ADMINISTRATEUR,
    DROIT_EDITEUR,
    DROIT_VISITEUR,
    DROIT_EN_ATTENTE,
)

__all__ = [
    "DROITS",
    "DROITS_ATTRIBUABLES",
    "DROIT_ADMINISTRATEUR",
    "DROIT_EDITEUR",
    "DROIT_EN_ATTENTE",
    "DROIT_EXTENTION",
    "DROIT_VISITEUR",
]
