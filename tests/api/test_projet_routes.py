"""Fiche projet : création, édition, RefLists, formules jamais écrites."""

from app.repositories.types import TABLE_COLLECTIVITES, TABLE_PROJETS
from tests.conftest import connecter, extraire_csrf


def test_fiche_projet_affiche_donnees_liees(client):
    connecter(client, "editeur@exemple.fr")
    page = client.get("/projet/10")
    assert page.status_code == 200
    assert "Projet Lampadaires" in page.text
    assert "Éclairage intelligent" in page.text   # cas d'usage lié
    assert "Opérateur Réseau" in page.text        # partenaire lié
    assert "CCTP Éclairage" in page.text          # document lié
    assert "Jean Dupont" in page.text             # contact lié (par nom de projet)
    assert "LoRaWAN" in page.text                 # multi-sélection connectivités
    assert "Emergence" in page.text               # choix configurés (widgetOptions)


def test_creation_projet_lie_la_collectivite(client):
    connecter(client, "editeur@exemple.fr")
    page = client.get("/projet/nouveau?collectivite_id=5")
    assert "Ville Exemple" in page.text  # collectivité porteuse affichée
    reponse = client.post(
        "/projet/nouveau",
        data={
            "nom": "Projet Capteurs", "description": "Test",
            "avancement": "Emergence", "echelle": "", "mutualisation": "",
            "soutien": "", "collectivite_id": "5", "action": "save",
            "connectivites": ["70", "71"], "departements": ["1"],
            "csrf_token": extraire_csrf(page.text),
        },
        follow_redirects=False,
    )
    assert reponse.status_code == 303
    fake = client.fake_grist
    cree = next(
        r for r in fake.records[TABLE_PROJETS] if r.get("nom") == "Projet Capteurs"
    )
    assert cree["collectivites_porteuses"] == ["L", 5]
    assert cree["connectivites"] == ["L", 70, 71]
    assert cree["departements"] == ["L", 1]
    # Formules jamais écrites (piège n°5)
    for formule in ("themes", "region", "partenaires", "cas_usages"):
        assert formule not in cree
    # Liaison inverse collectivité → projet
    coll = next(r for r in fake.records[TABLE_COLLECTIVITES] if r["id"] == 5)
    assert cree["id"] in coll["projets"]


def test_creation_action_autre_reste_sur_le_formulaire(client):
    connecter(client, "editeur@exemple.fr")
    page = client.get("/projet/nouveau?collectivite_id=5")
    reponse = client.post(
        "/projet/nouveau",
        data={
            "nom": "Projet En Série", "collectivite_id": "5", "action": "autre",
            "csrf_token": extraire_csrf(page.text),
        },
        follow_redirects=False,
    )
    assert reponse.headers["location"] == "/projet/nouveau?collectivite_id=5"


def test_modification_projet(client):
    connecter(client, "editeur@exemple.fr")
    page = client.get("/projet/10")
    reponse = client.post(
        "/projet/10",
        data={
            "nom": "Projet Lampadaires V2", "description": "Maj",
            "avancement": "Exploitation nominale", "echelle": "Communale",
            "mutualisation": "Besoins internes", "soutien": "ADEME",
            "dev_interne": "1", "collectivite_id": "5",
            "solutions": ["90"], "contrats": ["80"],
            "csrf_token": extraire_csrf(page.text),
        },
    )
    assert "mis à jour" in reponse.text
    fake = client.fake_grist
    record = next(r for r in fake.records[TABLE_PROJETS] if r["id"] == 10)
    assert record["nom"] == "Projet Lampadaires V2"
    assert record["dev_interne"] is True
    assert record["solutions"] == ["L", 90]
    assert record["contrats"] == ["L", 80]


def test_renommage_projet_relie_les_contacts(client):
    """Revue 2026-06-13 : les contacts sont liés par NOM de projet (dette v1) —
    un renommage via l'app doit re-pointer leurs liaisons."""
    connecter(client, "editeur@exemple.fr")
    page = client.get("/projet/10")
    client.post(
        "/projet/10",
        data={
            "nom": "Projet Éclairage Renommé", "description": "",
            "avancement": "", "echelle": "", "mutualisation": "", "soutien": "",
            "collectivite_id": "5", "csrf_token": extraire_csrf(page.text),
        },
    )
    fake = client.fake_grist
    contact = next(r for r in fake.records["BDD_Contacts"] if r["id"] == 60)
    assert contact["projets"] == "Projet Éclairage Renommé"


def test_nom_obligatoire(client):
    connecter(client, "editeur@exemple.fr")
    page = client.get("/projet/nouveau?collectivite_id=5")
    reponse = client.post(
        "/projet/nouveau",
        data={
            "nom": "  ", "collectivite_id": "5", "action": "save",
            "csrf_token": extraire_csrf(page.text),
        },
    )
    assert "obligatoire" in reponse.text
