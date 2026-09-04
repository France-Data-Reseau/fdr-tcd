"""Types des records Grist (12 tables BDD_*) et constantes du domaine.

Les TypedDicts reflètent le schéma documenté dans KIT_REBUILD_V2/SCHEMA_GRIST.md
(état au 2026-06-11). pygrister renvoie des records « aplatis » : ``{'id': ..,
<colonne>: ..}``. Les champs Ref sont des ``int`` (0 = vide), les RefList des
listes ``['L', id1, id2…]`` — ces idiomes ne doivent JAMAIS remonter au-dessus
de la couche repositories (voir AGENTS.md).
"""

from typing import Any, NotRequired, TypedDict

# --- Noms réels des tables dans Grist (constantes internes, jamais d'entrée
# utilisateur dans un nom de table) ---
TABLE_CAS_USAGES = "BDD_CasUsages"
TABLE_COLLECTIVITES = "BDD_Collectivites"
TABLE_CONNECTIVITES = "BDD_Connectivites"
TABLE_CONTRATS = "BDD_Contrats"
TABLE_DEPARTEMENTS = "BDD_Departements"
TABLE_DOCUMENTS = "BDD_Documents"
TABLE_PARTENAIRES = "BDD_Partenaires"
TABLE_PROGRAMMES = "BDD_Programmes"
TABLE_PROJETS = "BDD_Projets"
TABLE_REGIONS = "BDD_Regions"
TABLE_SOLUTIONS = "BDD_Solutions"
TABLE_UTILISATEURS = "BDD_Utilisateurs"

# --- Droits : vocabulaire EXCLUSIVEMENT français dans l'application ---
# « Extention » (sic) : valeur présente dans les données Grist — ne PAS corriger
# l'orthographe, les contrôles d'accès reposent sur la valeur exacte.
DROIT_ADMINISTRATEUR = "Administrateur"
DROIT_EDITEUR = "Editeur"
DROIT_VISITEUR = "Visiteur"
DROIT_EXTENTION = "Extention"
DROIT_EN_ATTENTE = "En attente"
DROIT_LECTEUR = "Lecteur"

DROITS = (
    DROIT_ADMINISTRATEUR,
    DROIT_EDITEUR,
    DROIT_LECTEUR,
    DROIT_VISITEUR,   # legacy : conservé pour normalisation, plus attribué
    DROIT_EXTENTION,  # legacy : état transitoire, plus attribué
    DROIT_EN_ATTENTE,
)

# Normalisation des droits À LA LECTURE (jamais réécrite en base) : valeurs
# anglaises héritées + « Visiteur » (legacy) → « Lecteur ». Toute valeur inconnue
# ou vide est ramenée à « En attente » par le repository (aucun compte non assigné).
DROITS_EN_VERS_FR = {
    "Administrator": DROIT_ADMINISTRATEUR,
    "Editor": DROIT_EDITEUR,
    "Viewer": DROIT_LECTEUR,
    "Pending": DROIT_EN_ATTENTE,
    "Visiteur": DROIT_LECTEUR,
}

class UtilisateurRecord(TypedDict):
    id: int
    nom: str
    prenom: str
    email: str
    organisation: str
    droits: str
    collectivite: NotRequired[int]  # Ref:BDD_Collectivites (0 = aucune)
    date_inscription: NotRequired[str]


class CollectiviteRecord(TypedDict):
    id: int
    nom: str
    siren: NotRequired[float]
    logo: NotRequired[str]
    url_logo: NotRequired[str]
    statut: NotRequired[Any]  # ChoiceList ['L', …]
    couverture: NotRequired[str]
    num_dep: NotRequired[str]  # formule ($departement.num_dep) — jamais écrite
    departement: NotRequired[int]  # Ref:BDD_Departements
    region: NotRequired[str]  # formule ($departement.region) — jamais écrite
    site_web: NotRequired[str]
    adresse: NotRequired[str]
    latitude: NotRequired[str]
    longitude: NotRequired[str]
    projets: NotRequired[list]  # RefList:BDD_Projets
    fnccr: NotRequired[bool]
    num: NotRequired[bool]
    eau: NotRequired[bool]
    aode: NotRequired[bool]
    tre: NotRequired[bool]
    ep: NotRequired[bool]
    dec: NotRequired[bool]


class ProjetRecord(TypedDict):
    id: int
    nom: str
    collectivites_porteuses: NotRequired[list]  # RefList:BDD_Collectivites
    description: NotRequired[str]
    connectivites: NotRequired[list]  # RefList:BDD_Connectivites
    themes: NotRequired[Any]  # formule (thèmes des cas d'usage) — jamais écrite
    avancement: NotRequired[str]
    partenaires: NotRequired[list]  # formule (lookup) — jamais écrite
    dev_interne: NotRequired[bool]
    solutions: NotRequired[list]  # RefList:BDD_Solutions
    cas_usages: NotRequired[list]  # formule (lookup) — jamais écrite
    echelle: NotRequired[str]
    mutualisation: NotRequired[Any]  # ChoiceList
    soutien: NotRequired[str]
    programmes: NotRequired[list]  # RefList:BDD_Programmes
    contrats: NotRequired[list]  # RefList:BDD_Contrats
    departements: NotRequired[list]  # RefList:BDD_Departements
    region: NotRequired[str]  # formule — jamais écrite
    documents: NotRequired[list]  # RefList:BDD_Documents


class CasUsageRecord(TypedDict):
    id: int
    nom: str
    theme: NotRequired[Any]  # ChoiceList
    projets: NotRequired[list]  # RefList:BDD_Projets
    domaine: NotRequired[str]
    connectivites: NotRequired[list]  # RefList:BDD_Connectivites


class ConnectiviteRecord(TypedDict):
    id: int
    nom: str
    projets: NotRequired[list]


class ContratRecord(TypedDict):
    id: int
    nom: str


class DepartementRecord(TypedDict):
    id: int
    nom: str
    num_dep: str
    region: str
    latitude: NotRequired[float]   # coord. préfecture (repli géo) — éditable en Grist
    longitude: NotRequired[float]
    projets: NotRequired[list]  # formule (lookup) — jamais écrite


class RegionRecord(TypedDict):
    id: int
    nom: str
    latitude: NotRequired[float]
    longitude: NotRequired[float]


class DocumentRecord(TypedDict):
    id: int
    titre: str
    lien: NotRequired[str]
    projet: NotRequired[int]  # Ref:BDD_Projets
    type: NotRequired[Any]  # ChoiceList
    annee: NotRequired[float]


class PartenaireRecord(TypedDict):
    id: int
    nom: str
    roles: NotRequired[Any]  # ChoiceList
    url: NotRequired[str]
    projets: NotRequired[list]  # RefList:BDD_Projets


class ProgrammeRecord(TypedDict):
    id: int
    nom: str
    info_web: NotRequired[str]
    echelle: NotRequired[str]
    projets: NotRequired[list]  # RefList:BDD_Projets


class SolutionRecord(TypedDict):
    id: int
    nom: str
    type: NotRequired[str]
    partenaire: NotRequired[int]  # Ref:BDD_Partenaires
    projets: NotRequired[list]  # formule (lookup) — jamais écrite
