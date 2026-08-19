"""Routes d'authentification : OIDC, inscription, session."""

from app.repositories.types import TABLE_UTILISATEURS
from tests.conftest import connecter, extraire_csrf


def test_login_page_accessible(client):
    reponse = client.get("/login")
    assert reponse.status_code == 200
    assert "france data" in reponse.text.lower()


def test_login_page_ne_contient_pas_formulaire_magic_link(client):
    page = client.get("/login")
    assert "name=\"csrf_token\"" not in page.text
    assert "lien de connexion par email" not in page.text.lower()


# --- OIDC ---


def test_oidc_desactive_routes_inaccessibles(client):
    reponse = client.get("/auth/sso")
    assert reponse.status_code == 404

    callback = client.get("/auth/callback")
    assert callback.status_code == 404


# --- Ouverture/fermeture de session ---


def test_flux_sso_complet(client):
    connecter(client, "admin@exemple.fr")
    accueil = client.get("/")
    assert accueil.status_code == 200
    assert "Bienvenue, Alice" in accueil.text
    assert "Console Administrateur" in accueil.text


def test_logout_ferme_la_session(client):
    connecter(client, "admin@exemple.fr")
    client.get("/logout")
    accueil = client.get("/", follow_redirects=False)
    assert accueil.status_code == 303
    assert accueil.headers["location"] == "/login"


# --- Inscription (sans mot de passe) ---


def test_inscription_cree_un_compte_en_attente(client):
    page = client.get("/inscription")
    assert "Ville Exemple" in page.text
    reponse = client.post(
        "/inscription",
        data={
            "prenom": "Nina",
            "nom": "Nouvelle",
            "email": "nina@exemple.fr",
            "organisation": "Mairie",
            "collectivite": "5",
            "csrf_token": extraire_csrf(page.text),
        },
    )
    assert "prise en compte" in reponse.text
    fake = client.fake_grist
    cree = [r for r in fake.records[TABLE_UTILISATEURS] if r.get("email") == "nina@exemple.fr"]
    assert len(cree) == 1
    assert cree[0]["droits"] == "En attente"
    assert cree[0]["collectivite"] == 5


def test_inscription_email_existant_reste_neutre_sans_doublon(client):
    page = client.get("/inscription")
    reponse = client.post(
        "/inscription",
        data={
            "prenom": "Alice",
            "nom": "Admin",
            "email": "admin@exemple.fr",
            "organisation": "",
            "collectivite": "0",
            "csrf_token": extraire_csrf(page.text),
        },
    )
    assert "prise en compte" in reponse.text
    fake = client.fake_grist
    comptes = [r for r in fake.records[TABLE_UTILISATEURS] if r.get("email") == "admin@exemple.fr"]
    assert len(comptes) == 1


# --- Demande de modification ---


def test_demande_modification_visiteur(client):
    connecter(client, "visiteur@exemple.fr")
    accueil = client.get("/")
    reponse = client.post(
        "/demande-modification",
        data={"csrf_token": extraire_csrf(accueil.text)},
    )
    assert "demande de modification" in reponse.text.lower()
    fake = client.fake_grist
    visiteur = next(r for r in fake.records[TABLE_UTILISATEURS] if r["id"] == 3)
    assert visiteur["droits"] == "Extention"
