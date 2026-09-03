"""Sous-formulaires de projet : liaison/création des 5 types de sous-objets."""

from tests.conftest import connecter, extraire_csrf


def test_cas_usage_page_filtre_les_deja_lies(client):
    connecter(client, "editeur@exemple.fr")
    page = client.get("/projet/10/cas-usage/nouveau?collectivite_id=5")
    assert page.status_code == 200
    # Le cas 20 est déjà lié au projet 10 → non proposé ; le 21 est liable
    assert 'value="21"' in page.text
    assert 'value="20"' not in page.text


def test_cas_usage_liaison_multi_projets(client):
    connecter(client, "editeur@exemple.fr")
    page = client.get("/projet/10/cas-usage/nouveau?collectivite_id=5")
    reponse = client.post(
        "/projet/10/cas-usage/nouveau",
        data={
            "mode": "select", "cas_usage_ids": ["21", "22"],
            "collectivite_id": "5", "action": "retour",
            "csrf_token": extraire_csrf(page.text),
        },
    )
    # Jinja échappe l'apostrophe : « d&#39;usage »
    assert "2 cas d&#39;usage lié(s)" in reponse.text
    fake = client.fake_grist
    cas21 = next(r for r in fake.records["BDD_CasUsages"] if r["id"] == 21)
    cas22 = next(r for r in fake.records["BDD_CasUsages"] if r["id"] == 22)
    assert cas21["projets"] == ["L", 10]
    assert cas22["projets"] == ["L", 11, 10]  # AJOUTÉ à la liste existante


def test_cas_usage_creation(client):
    connecter(client, "editeur@exemple.fr")
    page = client.get("/projet/10/cas-usage/nouveau?collectivite_id=5")
    client.post(
        "/projet/10/cas-usage/nouveau",
        data={
            "mode": "create", "nouveau_nom": "Stationnement intelligent",
            "nouveau_theme": "Gestion des mobilités", "collectivite_id": "5",
            "action": "retour", "csrf_token": extraire_csrf(page.text),
        },
    )
    fake = client.fake_grist
    cree = next(
        r for r in fake.records["BDD_CasUsages"]
        if r.get("nom") == "Stationnement intelligent"
    )
    assert cree["projets"] == ["L", 10]
    assert cree["theme"] == "Gestion des mobilités"


def test_partenaire_liaison_existant(client):
    connecter(client, "editeur@exemple.fr")
    page = client.get("/projet/10/partenaire/nouveau?collectivite_id=5")
    assert "Bureau Études" in page.text
    client.post(
        "/projet/10/partenaire/nouveau",
        data={
            "partenaire_existant_id": "31", "collectivite_id": "5",
            "action": "retour", "csrf_token": extraire_csrf(page.text),
        },
    )
    fake = client.fake_grist
    partenaire = next(r for r in fake.records["BDD_Partenaires"] if r["id"] == 31)
    assert partenaire["projets"] == ["L", 10]


def test_partenaire_creation(client):
    connecter(client, "editeur@exemple.fr")
    page = client.get("/projet/10/partenaire/nouveau?collectivite_id=5")
    client.post(
        "/projet/10/partenaire/nouveau",
        data={
            "nom": "Intégrateur Local", "roles": "Intégrateur",
            "url": "integrateur.fr", "collectivite_id": "5", "action": "retour",
            "csrf_token": extraire_csrf(page.text),
        },
    )
    fake = client.fake_grist
    cree = next(
        r for r in fake.records["BDD_Partenaires"]
        if r.get("nom") == "Intégrateur Local"
    )
    assert cree["projets"] == ["L", 10]
    assert cree["url"] == "https://integrateur.fr"


def test_programme_creation_et_action_autre(client):
    connecter(client, "editeur@exemple.fr")
    page = client.get("/projet/10/programme/nouveau?collectivite_id=5")
    reponse = client.post(
        "/projet/10/programme/nouveau",
        data={
            "nom": "Programme Régional", "info_web": "", "echelle": "Nationale",
            "collectivite_id": "5", "action": "autre",
            "csrf_token": extraire_csrf(page.text),
        },
        follow_redirects=False,
    )
    # action=autre → on reste sur le sous-formulaire
    assert "/programme/nouveau" in reponse.headers["location"]
    fake = client.fake_grist
    cree = next(
        r for r in fake.records["BDD_Programmes"]
        if r.get("nom") == "Programme Régional"
    )
    assert cree["projets"] == ["L", 10]


def test_document_creation(client):
    connecter(client, "editeur@exemple.fr")
    page = client.get("/projet/10/document/nouveau?collectivite_id=5")
    client.post(
        "/projet/10/document/nouveau",
        data={
            "titre": "Présentation projet", "lien": "https://docs.fr/p1",
            "type": "Support de présentation", "collectivite_id": "5",
            "action": "retour", "csrf_token": extraire_csrf(page.text),
        },
    )
    fake = client.fake_grist
    cree = next(
        r for r in fake.records["BDD_Documents"]
        if r.get("titre") == "Présentation projet"
    )
    assert cree["projet"] == 10  # Ref simple
