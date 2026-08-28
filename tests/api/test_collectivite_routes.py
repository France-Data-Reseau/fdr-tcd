"""Complétion et fiche collectivité : parcours, validation, choix configurés."""

from app.repositories.types import TABLE_COLLECTIVITES
from tests.conftest import connecter, extraire_csrf


def test_completion_admin_voit_le_selecteur(client):
    connecter(client, "admin@exemple.fr")
    page = client.get("/completion")
    assert page.status_code == 200
    assert "Ville Exemple" in page.text
    assert "Agglo Test" in page.text


def test_completion_editeur_redirige_vers_sa_collectivite(client):
    connecter(client, "editeur@exemple.fr")
    reponse = client.get("/completion", follow_redirects=False)
    assert reponse.status_code == 303
    assert reponse.headers["location"] == "/collectivite/5"


def test_completion_visiteur_renvoye_au_menu(client):
    connecter(client, "visiteur@exemple.fr")
    reponse = client.get("/completion", follow_redirects=False)
    assert reponse.status_code == 303
    assert reponse.headers["location"] == "/"


def test_fiche_collectivite_affiche_choix_configures(client):
    """Piège Grist n°7 : les choix viennent de widgetOptions, pas seulement
    des valeurs utilisées."""
    connecter(client, "admin@exemple.fr")
    page = client.get("/collectivite/5")
    assert page.status_code == 200
    assert "Commune" in page.text  # configuré mais non utilisé
    assert "Projet Lampadaires" in page.text  # projets liés


def test_creation_par_editeur_redirige_vers_menu(client):
    """Un Éditeur peut créer une collectivité (décision Victor) ; il est
    redirigé vers le menu (pas la fiche, hors de son périmètre tant qu'un
    admin ne l'a pas rattaché) et le record est créé."""
    connecter(client, "editeur@exemple.fr")
    page = client.get("/collectivite/nouveau")
    assert page.status_code == 200
    reponse = client.post(
        "/collectivite/nouveau",
        data={
            "nom": "Commune Editeur", "siren": "", "statut": "Commune",
            "couverture": "", "departement": "0", "site_web": "", "adresse": "",
            "csrf_token": extraire_csrf(page.text),
        },
        follow_redirects=False,
    )
    assert reponse.status_code == 303
    assert reponse.headers["location"] == "/"
    fake = client.fake_grist
    assert any(
        r.get("nom") == "Commune Editeur" for r in fake.records[TABLE_COLLECTIVITES]
    )


def test_creation_refusee_au_visiteur(client):
    connecter(client, "visiteur@exemple.fr")
    reponse = client.get("/collectivite/nouveau", follow_redirects=False)
    assert reponse.status_code == 303  # renvoyé au menu (require_editor)


def test_creation_collectivite(client):
    connecter(client, "admin@exemple.fr")
    page = client.get("/collectivite/nouveau")
    reponse = client.post(
        "/collectivite/nouveau",
        data={
            "nom": "Nouvelle Ville", "siren": "987654321", "statut": "Commune",
            "couverture": "Communale", "departement": "2", "site_web": "exemple.org",
            "adresse": "1 rue Test", "csrf_token": extraire_csrf(page.text),
        },
        follow_redirects=False,
    )
    assert reponse.status_code == 303
    fake = client.fake_grist
    cree = next(
        r for r in fake.records[TABLE_COLLECTIVITES] if r.get("nom") == "Nouvelle Ville"
    )
    assert cree["departement"] == 2
    assert cree["site_web"] == "https://exemple.org"  # schéma ajouté
    # Les champs formule ne sont JAMAIS écrits (piège n°5)
    assert "num_dep" not in cree
    assert "region" not in cree


def test_modification_collectivite(client):
    connecter(client, "editeur@exemple.fr")
    page = client.get("/collectivite/5")
    reponse = client.post(
        "/collectivite/5",
        data={
            "nom": "Ville Exemple Modifiée", "siren": "123456789", "statut": "EPCI",
            "couverture": "Communale", "departement": "1", "site_web": "",
            "adresse": "", "csrf_token": extraire_csrf(page.text),
        },
    )
    assert "mise à jour" in reponse.text
    fake = client.fake_grist
    record = next(r for r in fake.records[TABLE_COLLECTIVITES] if r["id"] == 5)
    assert record["nom"] == "Ville Exemple Modifiée"


def test_statut_hors_liste_refuse(client):
    connecter(client, "admin@exemple.fr")
    page = client.get("/collectivite/5")
    reponse = client.post(
        "/collectivite/5",
        data={
            "nom": "Ville Exemple", "siren": "0", "statut": "Injection",
            "couverture": "", "departement": "0", "site_web": "", "adresse": "",
            "csrf_token": extraire_csrf(page.text),
        },
    )
    assert "non autorisée" in reponse.text


def test_site_web_javascript_refuse(client):
    """S8 : un champ URL n'accepte que http(s)."""
    connecter(client, "admin@exemple.fr")
    page = client.get("/collectivite/5")
    reponse = client.post(
        "/collectivite/5",
        data={
            "nom": "Ville Exemple", "siren": "0", "statut": "", "couverture": "",
            "departement": "0", "site_web": "javascript:alert(1)", "adresse": "",
            "csrf_token": extraire_csrf(page.text),
        },
    )
    assert "invalide" in reponse.text
    fake = client.fake_grist
    record = next(r for r in fake.records[TABLE_COLLECTIVITES] if r["id"] == 5)
    assert record["site_web"] == "https://ville.exemple.fr"  # inchangé
