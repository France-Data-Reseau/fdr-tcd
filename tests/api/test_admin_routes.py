"""Console admin : accès réservé, validation des comptes, garde-fous."""

from app.repositories.types import TABLE_UTILISATEURS
from tests.conftest import connecter, extraire_csrf


def test_admin_reserve_aux_administrateurs(client):
    connecter(client, "visiteur@exemple.fr")
    reponse = client.get("/admin", follow_redirects=False)
    assert reponse.status_code == 303
    assert reponse.headers["location"] == "/"


def test_admin_sans_session_redirige_login(client):
    reponse = client.get("/admin", follow_redirects=False)
    assert reponse.status_code == 303
    assert reponse.headers["location"] == "/login"


def test_admin_liste_en_attente_en_premier(client):
    connecter(client, "admin@exemple.fr")
    page = client.get("/admin")
    assert page.status_code == 200
    # Paul Pending (En attente) apparaît avant les autres utilisateurs
    assert page.text.index("Pending") < page.text.index("Editeur")
    assert "À valider" in page.text


def test_admin_valide_un_compte_en_attente(client):
    connecter(client, "admin@exemple.fr")
    page = client.get("/admin")
    reponse = client.post(
        "/admin/utilisateur/4",
        data={
            "droits": "Lecteur", "collectivite": "6",
            "csrf_token": extraire_csrf(page.text),
        },
    )
    assert "mis à jour" in reponse.text
    fake = client.fake_grist
    paul = next(r for r in fake.records[TABLE_UTILISATEURS] if r["id"] == 4)
    assert paul["droits"] == "Lecteur"
    assert paul["collectivite"] == 6


def test_admin_droits_inconnus_ignores(client):
    connecter(client, "admin@exemple.fr")
    page = client.get("/admin")
    client.post(
        "/admin/utilisateur/3",
        data={
            "droits": "SuperAdmin", "collectivite": "0",
            "csrf_token": extraire_csrf(page.text),
        },
    )
    fake = client.fake_grist
    vera = next(r for r in fake.records[TABLE_UTILISATEURS] if r["id"] == 3)
    assert vera["droits"] == "Visiteur"  # inchangé


def test_admin_ne_peut_pas_se_retrograder(client):
    connecter(client, "admin@exemple.fr")
    page = client.get("/admin")
    reponse = client.post(
        "/admin/utilisateur/1",
        data={
            "droits": "Lecteur", "collectivite": "0",
            "csrf_token": extraire_csrf(page.text),
        },
    )
    assert "propre rôle" in reponse.text
    fake = client.fake_grist
    alice = next(r for r in fake.records[TABLE_UTILISATEURS] if r["id"] == 1)
    assert alice["droits"] == "Administrateur"


def test_admin_post_sans_csrf_rejete(client):
    connecter(client, "admin@exemple.fr")
    reponse = client.post(
        "/admin/utilisateur/4", data={"droits": "Visiteur", "collectivite": "0"}
    )
    assert reponse.status_code == 403


def test_admin_utilisateur_inexistant(client):
    connecter(client, "admin@exemple.fr")
    page = client.get("/admin")
    reponse = client.post(
        "/admin/utilisateur/999",
        data={
            "droits": "Visiteur", "collectivite": "0",
            "csrf_token": extraire_csrf(page.text),
        },
    )
    assert "introuvable" in reponse.text
