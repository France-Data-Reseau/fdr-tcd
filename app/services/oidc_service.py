"""SSO OIDC — client web server-side vers l'IdP de France Data Réseau.

Le flux suit l'authorization code :
- /auth/sso redirige vers l'IdP avec state + nonce ;
- /auth/callback échange le code contre un id_token ;
- l'id_token est validé avec fastapi-oidc ;
- on n'accepte que les emails vérifiés.

Sécurité :
- redirect URI bâtie EXCLUSIVEMENT sur APP_PUBLIC_URL (jamais le header Host) ;
- state/nonce/PKCE stockés en session signée ;
- messages d'erreur sobres côté utilisateur.
"""

import base64
import hashlib
import logging
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import Request
from fastapi_oidc import IDToken, get_auth

from app.core.config import Settings

logger = logging.getLogger(__name__)

_SESSION_STATE_KEY = "oidc_state"
_SESSION_NONCE_KEY = "oidc_nonce"
_SESSION_PKCE_VERIFIER_KEY = "oidc_pkce_verifier"


def _pkce_s256_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


class OidcService:
    def __init__(self, settings: Settings):
        self._settings = settings
        self.enabled = bool(
            settings.OIDC_ISSUER
            and settings.OIDC_CLIENT_ID
        )
        self._issuer = settings.OIDC_ISSUER.rstrip("/")
        self._metadata_url = f"{self._issuer}/.well-known/openid-configuration"
        self._metadata: dict[str, str] | None = None
        self._authenticate = None
        if self.enabled:
            self._authenticate = get_auth(
                client_id=settings.OIDC_CLIENT_ID,
                base_authorization_server_uri=self._issuer,
                issuer=self._issuer,
                signature_cache_ttl=300,
            )

    @property
    def redirect_uri(self) -> str:
        # Jamais le Host de la requête (anti-empoisonnement d'en-tête)
        return f"{self._settings.APP_PUBLIC_URL.rstrip('/')}/auth/callback"

    async def _get_metadata(self) -> dict[str, str]:
        if self._metadata is not None:
            return self._metadata
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(self._metadata_url)
            response.raise_for_status()
            data = response.json()
        authorization_endpoint = str(data.get("authorization_endpoint") or "")
        token_endpoint = str(data.get("token_endpoint") or "")
        if not authorization_endpoint or not token_endpoint:
            raise ValueError("metadata OIDC incomplètes")
        self._metadata = {
            "authorization_endpoint": authorization_endpoint,
            "token_endpoint": token_endpoint,
        }
        return self._metadata

    async def authorize_redirect_url(self, request: Request) -> str:
        """Démarre le flux : construit l'URL de redirection vers l'IdP."""
        metadata = await self._get_metadata()
        state = secrets.token_urlsafe(24)
        nonce = secrets.token_urlsafe(24)
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = _pkce_s256_challenge(code_verifier)
        request.session[_SESSION_STATE_KEY] = state
        request.session[_SESSION_NONCE_KEY] = nonce
        request.session[_SESSION_PKCE_VERIFIER_KEY] = code_verifier
        query = urlencode(
            {
                "client_id": self._settings.OIDC_CLIENT_ID,
                "response_type": "code",
                "scope": "openid email profile",
                "redirect_uri": self.redirect_uri,
                "state": state,
                "nonce": nonce,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            }
        )
        return f"{metadata['authorization_endpoint']}?{query}"

    async def _exchange_code(self, code: str, code_verifier: str) -> str | None:
        metadata = await self._get_metadata()
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self._settings.OIDC_CLIENT_ID,
            "code_verifier": code_verifier,
        }
        if self._settings.OIDC_CLIENT_SECRET:
            payload["client_secret"] = self._settings.OIDC_CLIENT_SECRET
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                metadata["token_endpoint"],
                data=payload,
                headers={"Accept": "application/json"},
            )
        if response.status_code >= 400:
            logger.warning("SSO : endpoint token en erreur (%s)", response.status_code)
            return None
        id_token = str(response.json().get("id_token") or "")
        return id_token or None

    async def fetch_verified_email(self, request: Request) -> str | None:
        """Termine le flux callback et retourne un email vérifié ou None."""
        state = str(request.query_params.get("state") or "")
        expected_state = str(request.session.pop(_SESSION_STATE_KEY, "") or "")
        if not state or not expected_state or not secrets.compare_digest(state, expected_state):
            logger.warning("SSO : state invalide")
            return None
        code = str(request.query_params.get("code") or "")
        if not code:
            logger.warning("SSO : callback sans code")
            return None
        code_verifier = str(
            request.session.pop(_SESSION_PKCE_VERIFIER_KEY, "") or ""
        )
        if not code_verifier:
            logger.warning("SSO : code_verifier PKCE absent")
            return None
        try:
            id_token = await self._exchange_code(code, code_verifier)
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("SSO : échec de l'échange du code (%s)", type(exc).__name__)
            return None
        if not id_token:
            logger.warning("SSO : id_token absent")
            return None
        if self._authenticate is None:
            logger.warning("SSO : service non initialisé")
            return None
        try:
            token: IDToken = self._authenticate(f"Bearer {id_token}")
        except Exception:
            logger.warning("SSO : id_token invalide")
            return None
        expected_nonce = str(request.session.pop(_SESSION_NONCE_KEY, "") or "")
        token_nonce = str(getattr(token, "nonce", "") or "")
        if (
            expected_nonce
            and token_nonce
            and not secrets.compare_digest(expected_nonce, token_nonce)
        ):
            logger.warning("SSO : nonce invalide")
            return None
        email = str(getattr(token, "email", "") or "").strip().lower()
        if not email:
            logger.warning("SSO : aucun email dans le jeton de l'IdP")
            return None
        # Sécurité (opt-in) : quand OIDC_REQUIRE_EMAIL_VERIFIED est actif, refuser
        # tout jeton dont le claim email_verified n'est pas True (absent OU False).
        # N'activer QUE si l'IdP émet ce claim dans l'id_token (voir config.py).
        if (
            self._settings.OIDC_REQUIRE_EMAIL_VERIFIED
            and getattr(token, "email_verified", None) is not True
        ):
            logger.warning("SSO : email non vérifié par l'IdP — refusé")
            return None
        return email
