"""Anti-IDOR (B2) : un Éditeur hors périmètre reçoit 404 — en GET ET en POST.

404 (pas 403) : la réponse ne confirme pas l'existence de la ressource,
et un identifiant inexistant produit la même réponse (uniformité).
"""

from tests.conftest import connecter, extraire_csrf


def test_editeur_get_collectivite_d_autrui_404(client):
    connecter(client, "editeur@exemple.fr")  # périmètre = collectivité 5
    assert client.get("/collectivite/6").status_code == 404


def test_editeur_get_collectivite_inexistante_404_uniforme(client):
    connecter(client, "editeur@exemple.fr")
    assert client.get("/collectivite/999").status_code == 404


def test_editeur_post_collectivite_d_autrui_404(client):
    connecter(client, "editeur@exemple.fr")
    page = client.get("/collectivite/5")
    reponse = client.post(
        "/collectivite/6",
        data={
            "nom": "Piratage", "siren": "0", "statut": "", "couverture": "",
            "departement": "0", "site_web": "", "adresse": "",
            "csrf_token": extraire_csrf(page.text),
        },
    )
    assert reponse.status_code == 404
    fake = client.fake_grist
    autre = next(r for r in fake.records["BDD_Collectivites"] if r["id"] == 6)
    assert autre["nom"] == "Agglo Test"  # intact


def test_admin_accede_a_tout(client):
    connecter(client, "admin@exemple.fr")
    assert client.get("/collectivite/5").status_code == 200
    assert client.get("/collectivite/6").status_code == 200
    assert client.get("/collectivite/999").status_code == 404  # inexistante


# --- Projets (le projet 11 appartient à la collectivité 6, pas à l'Éditeur) ---


def test_editeur_get_projet_d_autrui_404(client):
    connecter(client, "editeur@exemple.fr")
    assert client.get("/projet/11").status_code == 404
    assert client.get("/projet/999").status_code == 404  # uniforme


def test_editeur_post_projet_d_autrui_404(client):
    connecter(client, "editeur@exemple.fr")
    page = client.get("/projet/10")
    reponse = client.post(
        "/projet/11",
        data={
            "nom": "Piratage", "collectivite_id": "6",
            "csrf_token": extraire_csrf(page.text),
        },
    )
    assert reponse.status_code == 404
    fake = client.fake_grist
    projet = next(r for r in fake.records["BDD_Projets"] if r["id"] == 11)
    assert projet["nom"] == "Projet Eau Agglo"  # intact


def test_editeur_creation_projet_pour_collectivite_d_autrui_404(client):
    connecter(client, "editeur@exemple.fr")
    assert client.get("/projet/nouveau?collectivite_id=6").status_code == 404
    page = client.get("/projet/nouveau?collectivite_id=5")
    reponse = client.post(
        "/projet/nouveau",
        data={
            "nom": "Projet Pirate", "collectivite_id": "6", "action": "save",
            "csrf_token": extraire_csrf(page.text),
        },
    )
    assert reponse.status_code == 404


def test_editeur_sous_objets_d_un_projet_d_autrui_404(client):
    """Faiblesse v1 n°3 : les sous-objets sont couverts, GET et POST."""
    connecter(client, "editeur@exemple.fr")
    for route in ("cas-usage", "partenaire", "programme", "document", "contact"):
        assert client.get(f"/projet/11/{route}/nouveau").status_code == 404, route
    page = client.get("/projet/10/document/nouveau?collectivite_id=5")
    reponse = client.post(
        "/projet/11/document/nouveau",
        data={
            "titre": "Pirate", "collectivite_id": "6", "action": "retour",
            "csrf_token": extraire_csrf(page.text),
        },
    )
    assert reponse.status_code == 404


def test_admin_accede_aux_projets_de_tous(client):
    connecter(client, "admin@exemple.fr")
    assert client.get("/projet/10").status_code == 200
    assert client.get("/projet/11").status_code == 200
