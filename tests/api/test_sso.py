"""SSO OIDC : désactivé par défaut, flux callback (service stubé, zéro réseau)."""

import pytest

from tests.conftest import connecter  # noqa: F401  (cohérence des fixtures)


class OidcStub:
    """Double du OidcService : pas d'IdP réel dans les tests."""

    def __init__(self, email=None, enabled=True):
        self.enabled = enabled
        self._email = email

    async def authorize_redirect_url(self, request):
        return "https://idp.exemple.test/authorize?state=x"

    async def fetch_verified_email(self, request):
        return self._email


@pytest.fixture
def sso(monkeypatch):
    """Active un SSO stubé pour les routes (retourne le setter d'email)."""

    def _configurer(email=None, enabled=True):
        stub = OidcStub(email=email, enabled=enabled)
        monkeypatch.setattr("app.api.auth.get_oidc_service", lambda: stub)
        return stub

    return _configurer


def test_sso_desactive_par_defaut(client):
    page = client.get("/login")
    assert "France Data Réseau" not in page.text
    assert client.get("/auth/sso", follow_redirects=False).status_code == 404
    assert client.get("/auth/callback", follow_redirects=False).status_code == 404


def test_bouton_visible_quand_sso_actif(client, sso):
    sso()
    page = client.get("/login")
    assert "Se connecter avec France Data Réseau" in page.text
    assert 'href="/auth/sso"' in page.text


def test_sso_redirige_vers_l_idp(client, sso):
    sso()
    reponse = client.get("/auth/sso", follow_redirects=False)
    assert reponse.status_code == 303
    assert reponse.headers["location"].startswith("https://idp.exemple.test/")


def test_sso_indisponible_retour_login(client, sso):
    class BrokenOidcStub(OidcStub):
        async def authorize_redirect_url(self, request):
            raise ValueError("metadata OIDC incomplètes")

    stub = BrokenOidcStub(email=None, enabled=True)
    from app.api import auth as auth_routes

    original = auth_routes.get_oidc_service
    try:
        auth_routes.get_oidc_service = lambda: stub
        reponse = client.get("/auth/sso", follow_redirects=False)
    finally:
        auth_routes.get_oidc_service = original

    assert reponse.status_code == 303
    assert reponse.headers["location"] == "/login"


def test_callback_compte_connu_ouvre_la_session(client, sso):
    sso(email="editeur@exemple.fr")
    reponse = client.get("/auth/callback", follow_redirects=False)
    assert reponse.status_code == 303
    assert reponse.headers["location"] == "/"
    accueil = client.get("/")
    assert "Bienvenue, Eric" in accueil.text  # session ouverte, rôle re-résolu


def test_callback_compte_en_attente_vers_acces_refuse(client, sso):
    sso(email="attente@exemple.fr")
    reponse = client.get("/auth/callback", follow_redirects=False)
    assert reponse.headers["location"] == "/acces-refuse"


def test_callback_email_inconnu_refuse_vers_login(client, sso):
    # Liste fermée : un email non provisionné par un admin n'ouvre aucune session
    # et n'est PLUS orienté vers l'inscription — retour à /login.
    sso(email="nouveau@exemple.fr")
    reponse = client.get("/auth/callback", follow_redirects=False)
    assert reponse.status_code == 303
    assert reponse.headers["location"] == "/login"
    # Pas de session ouverte : l'IdP a vérifié l'identité mais aucun compte autorisé
    assert client.get("/", follow_redirects=False).headers["location"] == "/login"


def test_callback_echec_idp_retour_login(client, sso):
    sso(email=None)
    reponse = client.get("/auth/callback", follow_redirects=False)
    assert reponse.headers["location"] == "/login"
    page = client.get("/login")
    assert "a échoué" in page.text


def test_service_reel_desactive_sans_configuration():
    from app.core.config import Settings
    from app.services.oidc_service import OidcService

    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        GRIST_API_KEY="x", GRIST_DOC_ID="y",
        GRIST_SERVER_URL="https://grist.exemple.test",
    )
    assert OidcService(settings).enabled is False


def test_service_reel_redirect_uri_sur_app_public_url():
    from app.core.config import Settings
    from app.services.oidc_service import OidcService

    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        GRIST_API_KEY="x", GRIST_DOC_ID="y",
        GRIST_SERVER_URL="https://grist.exemple.test",
        APP_PUBLIC_URL="https://app.example.org/",
        OIDC_ISSUER="https://idp.francedatareseau.fr",
        OIDC_CLIENT_ID="fdr2", OIDC_CLIENT_SECRET="secret",
    )
    service = OidcService(settings)
    assert service.enabled is True
    assert service.redirect_uri == "https://app.example.org/auth/callback"


def test_service_reel_actif_sans_secret_client_public():
    from app.core.config import Settings
    from app.services.oidc_service import OidcService

    settings = Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        GRIST_API_KEY="x", GRIST_DOC_ID="y",
        GRIST_SERVER_URL="https://grist.exemple.test",
        OIDC_ISSUER="https://idp.francedatareseau.fr",
        OIDC_CLIENT_ID="fdr2", OIDC_CLIENT_SECRET="",
    )
    assert OidcService(settings).enabled is True