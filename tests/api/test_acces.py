"""Matrice d'accès : sans session → login ; rôles re-résolus à chaque requête."""

from app.repositories.types import TABLE_UTILISATEURS
from tests.conftest import connecter


def test_sans_session_redirige_vers_login(client):
    reponse = client.get("/", follow_redirects=False)
    assert reponse.status_code == 303
    assert reponse.headers["location"] == "/login"


def test_login_deja_connecte_redirige_vers_menu(client):
    connecter(client, "admin@exemple.fr")
    reponse = client.get("/login", follow_redirects=False)
    assert reponse.status_code == 303
    assert reponse.headers["location"] == "/"


def test_menu_selon_role_visiteur(client):
    connecter(client, "visiteur@exemple.fr")
    accueil = client.get("/")
    assert "Demande de modification" in accueil.text
    assert "Console Administrateur" not in accueil.text


def test_retrogradation_admin_prend_effet(client):
    """S5 : le rôle est re-résolu à chaque requête (≤ TTL du cache)."""
    connecter(client, "admin@exemple.fr")
    assert "Console Administrateur" in client.get("/").text
    # L'admin est rétrogradé directement dans Grist (autre admin, script…)
    fake = client.fake_grist
    for record in fake.records[TABLE_UTILISATEURS]:
        if record["email"] == "admin@exemple.fr":
            record["droits"] = "Visiteur"
    # On invalide le cache comme le ferait une écriture passée par l'app
    from app import dependencies

    dependencies.get_table_cache().invalidate(TABLE_UTILISATEURS)
    assert "Console Administrateur" not in client.get("/").text


def test_compte_supprime_session_devient_invalide(client):
    connecter(client, "visiteur@exemple.fr")
    fake = client.fake_grist
    fake.records[TABLE_UTILISATEURS] = [
        r for r in fake.records[TABLE_UTILISATEURS] if r["email"] != "visiteur@exemple.fr"
    ]
    from app import dependencies

    dependencies.get_table_cache().invalidate(TABLE_UTILISATEURS)
    reponse = client.get("/", follow_redirects=False)
    assert reponse.status_code == 303
    assert reponse.headers["location"] == "/login"
