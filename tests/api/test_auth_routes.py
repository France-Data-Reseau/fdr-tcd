"""Routes d'authentification : login par mot de passe, magic link, inscription."""

from app import dependencies
from app.repositories.types import TABLE_UTILISATEURS
from tests.conftest import MOT_DE_PASSE_TEST, connecter, extraire_csrf


def test_login_page_accessible(client):
    reponse = client.get("/login")
    assert reponse.status_code == 200
    assert "mot de passe" in reponse.text.lower()


# --- Login par mot de passe ---


def test_login_mot_de_passe_reussi(client):
    page = client.get("/login")
    reponse = client.post(
        "/login",
        data={"email": "admin@exemple.fr", "password": MOT_DE_PASSE_TEST,
              "csrf_token": extraire_csrf(page.text)},
        follow_redirects=False,
    )
    assert reponse.status_code == 303
    assert reponse.headers["location"] == "/"
    assert "Bienvenue, Alice" in client.get("/").text


def test_login_message_neutre_commun(client):
    """Email inconnu, mauvais mot de passe et compte sans hash → message
    identique (anti-énumération)."""
    page = client.get("/login")
    csrf = extraire_csrf(page.text)
    inconnu = client.post("/login", data={
        "email": "inconnu@exemple.fr", "password": "x" * 14, "csrf_token": csrf})
    mauvais = client.post("/login", data={
        "email": "admin@exemple.fr", "password": "mauvais-mdp-12", "csrf_token": csrf})
    sans_hash = client.post("/login", data={
        "email": "visiteur@exemple.fr", "password": MOT_DE_PASSE_TEST,
        "csrf_token": csrf})
    assert "incorrect" in inconnu.text
    assert "incorrect" in mauvais.text
    assert "incorrect" in sans_hash.text


def test_login_mauvais_mot_de_passe_ne_connecte_pas(client):
    page = client.get("/login")
    client.post("/login", data={
        "email": "admin@exemple.fr", "password": "pas-le-bon-mdp",
        "csrf_token": extraire_csrf(page.text)})
    accueil = client.get("/", follow_redirects=False)
    assert accueil.headers["location"] == "/login"


def test_login_en_attente_vers_acces_refuse(client):
    page = client.get("/login")
    reponse = client.post(
        "/login",
        data={"email": "attente@exemple.fr", "password": MOT_DE_PASSE_TEST,
              "csrf_token": extraire_csrf(page.text)},
        follow_redirects=False,
    )
    assert reponse.headers["location"] == "/acces-refuse"


def test_lien_email_indisponible_sans_smtp(client):
    """SMTP non configuré (cas des tests) : pas de bouton, et l'endpoint
    magic link répond 404."""
    page = client.get("/login")
    assert "lien par email" not in page.text.lower()
    reponse = client.post("/auth/lien-email", data={
        "email": "admin@exemple.fr", "csrf_token": extraire_csrf(page.text)})
    assert reponse.status_code == 404


# --- Magic link (mécanisme conservé, utilisé pour le reset futur) ---


def test_flux_magic_link_complet(client):
    connecter(client, "admin@exemple.fr")
    accueil = client.get("/")
    assert accueil.status_code == 200
    assert "Bienvenue, Alice" in accueil.text
    assert "Console Administrateur" in accueil.text


def test_jeton_invalide_redirige_vers_login(client):
    reponse = client.get("/auth/verifier?token=nimporte-quoi")
    assert reponse.status_code == 200  # après redirection vers /login
    assert "invalide" in reponse.text


def test_jeton_consomme_une_seule_fois(client):
    lien = dependencies.get_magic_link_service().generate_url("admin@exemple.fr")
    token = lien.split("token=", 1)[1]
    page = client.get(f"/auth/verifier?token={token}")
    csrf = extraire_csrf(page.text)
    premier = client.post(
        "/auth/verifier", data={"token": token, "csrf_token": csrf},
        follow_redirects=False,
    )
    assert premier.status_code == 303
    assert premier.headers["location"] == "/"
    client.get("/logout")
    page2 = client.get(f"/auth/verifier?token={token}", follow_redirects=False)
    assert page2.status_code == 303
    assert page2.headers["location"] == "/login"


def test_logout_ferme_la_session(client):
    connecter(client, "admin@exemple.fr")
    client.get("/logout")
    accueil = client.get("/", follow_redirects=False)
    assert accueil.status_code == 303
    assert accueil.headers["location"] == "/login"


# --- Inscription (définit le mot de passe) ---


def test_inscription_cree_un_compte_avec_hash(client):
    page = client.get("/inscription")
    assert "Ville Exemple" in page.text
    reponse = client.post(
        "/inscription",
        data={
            "prenom": "Nina", "nom": "Nouvelle", "email": "nina@exemple.fr",
            "organisation": "Mairie", "collectivite": "5",
            "password": "PhraseDePasse-Nina-2026",
            "password_confirm": "PhraseDePasse-Nina-2026",
            "csrf_token": extraire_csrf(page.text),
        },
    )
    assert "prise en compte" in reponse.text
    fake = client.fake_grist
    cree = [r for r in fake.records[TABLE_UTILISATEURS] if r.get("email") == "nina@exemple.fr"]
    assert len(cree) == 1
    assert cree[0]["droits"] == "En attente"
    assert cree[0]["collectivite"] == 5
    # Hash présent et jamais en clair
    assert cree[0]["password_hash"]
    assert "PhraseDePasse" not in cree[0]["password_hash"]


def test_inscription_mot_de_passe_faible_refuse(client):
    page = client.get("/inscription")
    reponse = client.post(
        "/inscription",
        data={
            "prenom": "X", "nom": "Y", "email": "faible@exemple.fr",
            "organisation": "", "collectivite": "0",
            "password": "court", "password_confirm": "court",
            "csrf_token": extraire_csrf(page.text),
        },
    )
    assert "12 caractères" in reponse.text
    fake = client.fake_grist
    assert not any(
        r.get("email") == "faible@exemple.fr" for r in fake.records[TABLE_UTILISATEURS]
    )


def test_inscription_confirmation_differente(client):
    page = client.get("/inscription")
    reponse = client.post(
        "/inscription",
        data={
            "prenom": "X", "nom": "Y", "email": "diff@exemple.fr",
            "organisation": "", "collectivite": "0",
            "password": "PhraseDePasse-2026", "password_confirm": "PhraseDePasse-AUTRE",
            "csrf_token": extraire_csrf(page.text),
        },
    )
    assert "confirmation" in reponse.text.lower()
    fake = client.fake_grist
    assert not any(
        r.get("email") == "diff@exemple.fr" for r in fake.records[TABLE_UTILISATEURS]
    )


def test_inscription_email_existant_reste_neutre_sans_doublon(client):
    page = client.get("/inscription")
    reponse = client.post(
        "/inscription",
        data={
            "prenom": "Alice", "nom": "Admin", "email": "admin@exemple.fr",
            "organisation": "", "collectivite": "0",
            "password": "PhraseDePasse-2026", "password_confirm": "PhraseDePasse-2026",
            "csrf_token": extraire_csrf(page.text),
        },
    )
    assert "prise en compte" in reponse.text
    fake = client.fake_grist
    comptes = [r for r in fake.records[TABLE_UTILISATEURS] if r.get("email") == "admin@exemple.fr"]
    assert len(comptes) == 1


# --- Changement de mot de passe (utilisateur connecté) ---


def test_changement_mot_de_passe(client):
    connecter(client, "admin@exemple.fr")
    fake = client.fake_grist
    avant = next(r for r in fake.records[TABLE_UTILISATEURS] if r["id"] == 1)["password_hash"]
    page = client.get("/mon-mot-de-passe")
    assert page.status_code == 200
    reponse = client.post(
        "/mon-mot-de-passe",
        data={"actuel": MOT_DE_PASSE_TEST, "nouveau": "NouvellePhrase-2026",
              "confirmation": "NouvellePhrase-2026",
              "csrf_token": extraire_csrf(page.text)},
        follow_redirects=False,
    )
    assert reponse.status_code == 303
    apres = next(r for r in fake.records[TABLE_UTILISATEURS] if r["id"] == 1)["password_hash"]
    assert apres != avant


def test_changement_mauvais_actuel(client):
    connecter(client, "admin@exemple.fr")
    page = client.get("/mon-mot-de-passe")
    reponse = client.post(
        "/mon-mot-de-passe",
        data={"actuel": "pas-le-bon", "nouveau": "NouvellePhrase-2026",
              "confirmation": "NouvellePhrase-2026",
              "csrf_token": extraire_csrf(page.text)},
    )
    assert "actuel est incorrect" in reponse.text


def test_changement_requiert_session(client):
    reponse = client.get("/mon-mot-de-passe", follow_redirects=False)
    assert reponse.status_code == 303
    assert reponse.headers["location"] == "/login"


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
