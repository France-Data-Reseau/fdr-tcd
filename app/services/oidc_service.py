"""SSO OIDC — Relying Party vers l'IdP de France Data Réseau.

« Se connecter avec son compte Grist » : l'instance grist.francedatareseau.fr
n'est pas un fournisseur d'identité, mais elle s'appuie sur un IdP OIDC chez
France Data Réseau — c'est sur LUI que l'app se branche. Tout est configuré
en .env (OIDC_ISSUER, OIDC_CLIENT_ID, OIDC_CLIENT_SECRET) : tant que ces
variables sont vides, le SSO est désactivé et le magic link reste le seul
moyen de connexion ; quand elles sont renseignées, le bouton apparaît sur la
page de login. Le pipeline aval est COMMUN aux deux méthodes : email vérifié
→ mapping BDD_Utilisateurs (référentiel des rôles).

Sécurité :
- redirect URI bâtie EXCLUSIVEMENT sur APP_PUBLIC_URL (jamais le header Host) ;
- state/nonce gérés par authlib via la session signée (anti-CSRF du flux) ;
- seuls les emails VÉRIFIÉS par l'IdP sont acceptés.
"""

import logging

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import Request

from app.core.config import Settings

logger = logging.getLogger(__name__)


class OidcService:
    def __init__(self, settings: Settings):
        self._settings = settings
        self.enabled = bool(
            settings.OIDC_ISSUER
            and settings.OIDC_CLIENT_ID
            and settings.OIDC_CLIENT_SECRET
        )
        self._oauth = OAuth()
        if self.enabled:
            issuer = settings.OIDC_ISSUER.rstrip("/")
            self._oauth.register(
                name="fdr",
                client_id=settings.OIDC_CLIENT_ID,
                client_secret=settings.OIDC_CLIENT_SECRET,
                server_metadata_url=f"{issuer}/.well-known/openid-configuration",
                client_kwargs={"scope": "openid email profile"},
            )

    @property
    def redirect_uri(self) -> str:
        # Jamais le Host de la requête (anti-empoisonnement d'en-tête)
        return f"{self._settings.APP_PUBLIC_URL.rstrip('/')}/auth/callback"

    async def authorize_redirect(self, request: Request):
        """Démarre le flux : redirection vers l'IdP (state posé en session)."""
        return await self._oauth.fdr.authorize_redirect(request, self.redirect_uri)

    async def fetch_verified_email(self, request: Request) -> str | None:
        """Termine le flux (callback) : échange le code, retourne l'email
        vérifié — ou None (motif journalisé sobrement, jamais détaillé à
        l'utilisateur)."""
        try:
            token = await self._oauth.fdr.authorize_access_token(request)
        except OAuthError as exc:
            logger.warning("SSO : échec d'échange du code (%s)", exc.error)
            return None
        userinfo = token.get("userinfo")
        if not userinfo:
            try:
                userinfo = await self._oauth.fdr.userinfo(token=token)
            except OAuthError as exc:
                logger.warning("SSO : userinfo inaccessible (%s)", exc.error)
                return None
        email = str(userinfo.get("email") or "").strip().lower()
        if not email:
            logger.warning("SSO : aucun email dans le jeton de l'IdP")
            return None
        # email_verified peut être absent selon l'IdP : on ne refuse que le
        # faux explicite
        if userinfo.get("email_verified") is False:
            logger.warning("SSO : email non vérifié par l'IdP — refusé")
            return None
        return email
