"""OIDC service: PKCE and public-client behavior."""

from urllib.parse import parse_qs, urlparse

import pytest

from app.core.config import Settings
from app.services.oidc_service import OidcService


class _FakeRequest:
    def __init__(self):
        self.session: dict[str, str] = {}
        self.query_params: dict[str, str] = {}


def _settings(**kwargs) -> Settings:
    return Settings(
        _env_file=None,  # pyright: ignore[reportCallIssue]
        GRIST_API_KEY="x",
        GRIST_DOC_ID="y",
        GRIST_SERVER_URL="https://grist.exemple.test",
        OIDC_ISSUER="https://idp.exemple.test",
        OIDC_CLIENT_ID="tcd",
        OIDC_CLIENT_SECRET="",
        **kwargs,
    )


@pytest.mark.asyncio
async def test_authorize_redirect_url_inclut_pkce(monkeypatch):
    service = OidcService(_settings())

    async def _fake_metadata():
        return {
            "authorization_endpoint": "https://idp.exemple.test/authorize",
            "token_endpoint": "https://idp.exemple.test/token",
        }

    monkeypatch.setattr(service, "_get_metadata", _fake_metadata)

    request = _FakeRequest()
    url = await service.authorize_redirect_url(request)  # pyright: ignore[reportArgumentType]

    parsed = urlparse(url)
    qs = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "idp.exemple.test"
    assert qs["response_type"] == ["code"]
    assert qs["code_challenge_method"] == ["S256"]
    assert "code_challenge" in qs
    assert len(qs["code_challenge"][0]) >= 43

    verifier = request.session.get("oidc_pkce_verifier", "")
    assert verifier


@pytest.mark.asyncio
async def test_exchange_code_public_client_sans_secret(monkeypatch):
    service = OidcService(_settings())

    async def _fake_metadata():
        return {
            "authorization_endpoint": "https://idp.exemple.test/authorize",
            "token_endpoint": "https://idp.exemple.test/token",
        }

    monkeypatch.setattr(service, "_get_metadata", _fake_metadata)

    captured: dict[str, object] = {}

    class _FakeResponse:
        status_code = 200

        @staticmethod
        def json() -> dict[str, str]:
            return {"id_token": "id-token"}

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, data=None, headers=None):
            captured["url"] = url
            captured["data"] = dict(data or {})
            captured["headers"] = dict(headers or {})
            return _FakeResponse()

    monkeypatch.setattr("app.services.oidc_service.httpx.AsyncClient", _FakeClient)

    id_token = await service._exchange_code("code", "verifier")

    assert id_token == "id-token"
    data = captured["data"]
    assert isinstance(data, dict)
    assert data.get("code_verifier") == "verifier"
    assert "client_secret" not in data


def test_service_actif_sans_secret_sur_client_public():
    service = OidcService(_settings())
    assert service.enabled is True
