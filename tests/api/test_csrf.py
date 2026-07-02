"""CSRF : tout POST sans jeton (ou avec un jeton invalide) est rejeté en 403."""

import pytest

from tests.conftest import connecter

POSTS_PUBLICS = ["/login", "/inscription", "/auth/verifier"]


@pytest.mark.parametrize("route", POSTS_PUBLICS)
def test_post_sans_csrf_rejete(client, route):
    reponse = client.post(route, data={"email": "x@exemple.fr", "token": "t"})
    assert reponse.status_code == 403


@pytest.mark.parametrize("route", POSTS_PUBLICS)
def test_post_avec_csrf_invalide_rejete(client, route):
    client.get("/login")  # ouvre une session avec un vrai jeton
    reponse = client.post(
        route, data={"email": "x@exemple.fr", "token": "t", "csrf_token": "falsifie"}
    )
    assert reponse.status_code == 403


def test_post_authentifie_sans_csrf_rejete(client):
    connecter(client, "visiteur@exemple.fr")
    reponse = client.post("/demande-modification", data={})
    assert reponse.status_code == 403


def test_headers_de_securite_presents(client):
    reponse = client.get("/login")
    assert "Content-Security-Policy" in reponse.headers
    assert "'self'" in reponse.headers["Content-Security-Policy"]
    assert reponse.headers["X-Content-Type-Options"] == "nosniff"
    assert reponse.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    # HSTS appartient à Caddy (un seul émetteur par header)
    assert "Strict-Transport-Security" not in reponse.headers


def test_rate_limit_inscription(client):
    """5/minute sur l'inscription : la 6e tentative est refusée (429)."""
    from tests.conftest import extraire_csrf

    page = client.get("/inscription")
    csrf = extraire_csrf(page.text)
    donnees = {
        "prenom": "A", "nom": "B", "email": "spam@exemple.fr",
        "organisation": "", "collectivite": "0", "csrf_token": csrf,
    }
    statuts = [
        client.post("/inscription", data=donnees, follow_redirects=False).status_code
        for _ in range(6)
    ]
    assert statuts[:5] == [303] * 5
    assert statuts[5] == 429
