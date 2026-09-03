"""Fixtures communes.

- Variables d'environnement minimales posées AVANT tout import de l'app
  (Settings exige les variables Grist) — valeurs factices, jamais réelles.
- Isolation : les fabriques @lru_cache de dependencies.py sont des singletons
  de processus → reset systématique entre les tests.
"""

import os

os.environ.setdefault("GRIST_API_KEY", "cle-factice-pour-tests")
os.environ.setdefault("GRIST_DOC_ID", "doc-factice")
os.environ.setdefault("GRIST_SERVER_URL", "https://grist.exemple.test")
os.environ.setdefault("ENVIRONMENT", "test")
# Hermétisme : neutraliser tout SMTP/OIDC du .env local (os.environ > .env)
# pour que les tests ne dépendent pas de la configuration réelle du poste.
for _var in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM",
             "ADMIN_NOTIFY_EMAILS", "OIDC_ISSUER", "OIDC_CLIENT_ID",
             "OIDC_CLIENT_SECRET"):
    os.environ.setdefault(_var, "")

import re  # noqa: E402
from copy import deepcopy  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import dependencies  # noqa: E402
from app.core.security import limiter  # noqa: E402
from app.repositories.cache import TableCache  # noqa: E402


@pytest.fixture(autouse=True)
def _isolation_singletons():
    dependencies.reset_singletons()
    limiter.reset()
    yield
    dependencies.reset_singletons()
    limiter.reset()


class FakeGristApi:
    """Double de pygrister.GristApi : retours (status, data), records aplatis.

    - ``records`` : {table_id: [{'id': .., <colonne>: ..}, ...]}
    - ``echec_batch`` : si True, update_records renvoie 400 pour les lots de
      plus d'un record (simule le piège PATCH hétérogène).
    - ``statuts_forces`` : {méthode: status} pour simuler des erreurs HTTP.
    """

    def __init__(self, records: dict[str, list[dict]] | None = None):
        self.records: dict[str, list[dict]] = deepcopy(records or {})
        self.calls: list[tuple] = []
        self.echec_batch = False
        self.statuts_forces: dict[str, int] = {}
        # {table: {colonne: widgetOptions (chaîne JSON)}} — piège Grist n°7
        self.widget_options: dict[str, dict[str, str]] = {}
        self._prochain_id = 1000

    def list_records(self, table_id, **kwargs):
        self.calls.append(("list_records", table_id))
        force = self.statuts_forces.get("list_records")
        if force:
            return force, {"error": "interdit"}
        return 200, deepcopy(self.records.get(table_id, []))

    def add_records(self, table_id, records, **kwargs):
        self.calls.append(("add_records", table_id, deepcopy(records)))
        force = self.statuts_forces.get("add_records")
        if force:
            return force, {"error": "refus"}
        ids = []
        for fields in records:
            self._prochain_id += 1
            self.records.setdefault(table_id, []).append(
                {"id": self._prochain_id, **fields}
            )
            ids.append(self._prochain_id)
        return 200, ids

    def update_records(self, table_id, records, **kwargs):
        self.calls.append(("update_records", table_id, deepcopy(records)))
        force = self.statuts_forces.get("update_records")
        if force:
            return force, {"error": "refus"}
        if self.echec_batch and len(records) > 1:
            return 400, {"error": "Invalid payload"}
        for rec in records:
            rec = dict(rec)
            rid = rec.pop("id")
            for stocke in self.records.get(table_id, []):
                if stocke["id"] == rid:
                    stocke.update(rec)
        return 200, None

    def list_tables(self):
        self.calls.append(("list_tables",))
        return 200, [{"id": t} for t in self.records]

    def list_cols(self, table_id, hidden=False):
        self.calls.append(("list_cols", table_id))
        colonnes: set[str] = set()
        for rec in self.records.get(table_id, []):
            colonnes.update(k for k in rec if k != "id")
        options = self.widget_options.get(table_id, {})
        return 200, [
            {"id": c, "fields": {"widgetOptions": options.get(c, "")}}
            for c in sorted(colonnes | set(options))
        ]


@pytest.fixture
def fake_grist():
    return FakeGristApi()


@pytest.fixture
def cache():
    return TableCache(ttl_seconds=300)


# --- Fixtures applicatives (routes) ---

UTILISATEURS_TEST = [
    {"id": 1, "email": "admin@exemple.fr", "droits": "Administrateur",
    "prenom": "Alice", "nom": "Admin", "organisation": "FNCCR", "collectivite": 0},
    {"id": 2, "email": "editeur@exemple.fr", "droits": "Editeur",
    "prenom": "Eric", "nom": "Editeur", "organisation": "", "collectivite": 5},
    {"id": 3, "email": "visiteur@exemple.fr", "droits": "Visiteur",
     "prenom": "Vera", "nom": "Visiteuse", "organisation": "", "collectivite": 0},
    {"id": 4, "email": "attente@exemple.fr", "droits": "En attente",
    "prenom": "Paul", "nom": "Pending", "organisation": "", "collectivite": 0},
]

COLLECTIVITES_TEST = [
    # lat/long STOCKÉS : les tests ne déclenchent jamais de géocodage réseau
    {"id": 5, "nom": "Ville Exemple", "projets": ["L", 10], "statut": ["L", "EPCI"],
     "couverture": "Communale", "departement": 1, "num_dep": "33", "region": "Nouvelle-Aquitaine",
     "siren": 123456789, "site_web": "https://ville.exemple.fr", "adresse": "",
     "latitude": "44.85", "longitude": "-0.58", "url_logo": ""},
    {"id": 6, "nom": "Agglo Test", "projets": [], "statut": ["L", "Syndicat"],
     "couverture": "", "departement": 0, "num_dep": "", "region": "", "siren": 0,
     "site_web": "", "adresse": "", "latitude": "47.08", "longitude": "2.40", "url_logo": ""},
]

DEPARTEMENTS_TEST = [
    {"id": 1, "nom": "Gironde", "num_dep": "33", "region": "Nouvelle-Aquitaine"},
    {"id": 2, "nom": "Cher", "num_dep": "18", "region": "Centre-Val de Loire"},
]

PROJETS_TEST = [
    {"id": 10, "nom": "Projet Lampadaires", "collectivites_porteuses": ["L", 5],
     "description": "Éclairage public connecté", "avancement": "Emergence",
     "connectivites": ["L", 70], "echelle": "Communale",
     "themes": ["L", "Gestion de l'éclairage public"]},
    {"id": 11, "nom": "Projet Eau Agglo", "collectivites_porteuses": ["L", 6],
     "description": "", "avancement": "", "connectivites": [],
     "echelle": "", "themes": []},
]

CAS_USAGES_TEST = [
    {"id": 20, "nom": "Éclairage intelligent", "theme": ["L", "Gestion de l'éclairage public"],
     "projets": ["L", 10]},
    {"id": 21, "nom": "Capteurs de remplissage", "theme": ["L", "Gestion des déchets"],
     "projets": []},
    {"id": 22, "nom": "Télérelève des compteurs", "theme": ["L", "Gestion de l'eau"],
     "projets": ["L", 11]},
]

PARTENAIRES_TEST = [
    {"id": 30, "nom": "Opérateur Réseau", "roles": ["L", "Opérateur"],
     "url": "https://operateur.fr", "projets": ["L", 10]},
    {"id": 31, "nom": "Bureau Études", "roles": ["L", "AMO / Étude"],
     "url": "", "projets": []},
]

PROGRAMMES_TEST = [
    {"id": 40, "nom": "Programme National", "info_web": "", "echelle": "Nationale",
     "projets": []},
]

DOCUMENTS_TEST = [
    {"id": 50, "titre": "CCTP Éclairage", "lien": "", "type": ["L", "CCTP"],
     "projet": 10},
]

CONNECTIVITES_TEST = [
    {"id": 70, "nom": "LoRaWAN", "projets": ["L", 10]},
    {"id": 71, "nom": "5G", "projets": []},
]

CONTRATS_TEST = [{"id": 80, "nom": "Contrat Cadre"}]

SOLUTIONS_TEST = [
    {"id": 90, "nom": "Plateforme Hypervision", "type": "Plateforme", "partenaire": 30},
]

WIDGET_OPTIONS_TEST = {
    "BDD_Collectivites": {
        "statut": '{"choices": ["Commune", "Syndicat", "EPCI"]}',
        "couverture": '{"choices": ["Départementale", "Communale"]}',
    },
    "BDD_Projets": {
        "avancement": '{"choices": ["Emergence", "Expérimentation", "Exploitation nominale"]}',
        "echelle": '{"choices": ["Communale", "Départementale"]}',
        "mutualisation": '{"choices": ["Besoins internes", "Besoins externes"]}',
        "soutien": '{"choices": ["ADEME", "France 2030"]}',
    },
}


@pytest.fixture
def client(fake_grist, monkeypatch):
    """TestClient avec l'API Grist remplacée par le fake (cookies persistants)."""
    fake_grist.records["BDD_Utilisateurs"] = deepcopy(UTILISATEURS_TEST)
    fake_grist.records["BDD_Collectivites"] = deepcopy(COLLECTIVITES_TEST)
    fake_grist.records["BDD_Departements"] = deepcopy(DEPARTEMENTS_TEST)
    fake_grist.records["BDD_Projets"] = deepcopy(PROJETS_TEST)
    fake_grist.records["BDD_CasUsages"] = deepcopy(CAS_USAGES_TEST)
    fake_grist.records["BDD_Partenaires"] = deepcopy(PARTENAIRES_TEST)
    fake_grist.records["BDD_Programmes"] = deepcopy(PROGRAMMES_TEST)
    fake_grist.records["BDD_Documents"] = deepcopy(DOCUMENTS_TEST)
    fake_grist.records["BDD_Connectivites"] = deepcopy(CONNECTIVITES_TEST)
    fake_grist.records["BDD_Contrats"] = deepcopy(CONTRATS_TEST)
    fake_grist.records["BDD_Solutions"] = deepcopy(SOLUTIONS_TEST)
    fake_grist.widget_options = deepcopy(WIDGET_OPTIONS_TEST)
    monkeypatch.setattr(dependencies, "get_grist_api", lambda: fake_grist)
    from app.main import app

    test_client = TestClient(app)
    test_client.fake_grist = fake_grist  # type: ignore[attr-defined]
    return test_client


def extraire_csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "csrf_token absent de la page"
    return match.group(1)


def connecter(client: TestClient, email: str) -> None:
    """Ouvre une session en simulant un callback OIDC vérifié."""

    class _OidcStub:
        enabled = True

        async def fetch_verified_email(self, request):
            return email

        async def authorize_redirect_url(self, request):
            return "https://idp.exemple.test/authorize"

    import app.api.auth as auth_routes

    original = auth_routes.get_oidc_service
    try:
        auth_routes.get_oidc_service = lambda: _OidcStub()
        reponse = client.get("/auth/callback", follow_redirects=False)
    finally:
        auth_routes.get_oidc_service = original
    assert reponse.status_code == 303
