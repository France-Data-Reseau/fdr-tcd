"""Sécurité HTTP : headers, CSRF, session, rate limiting.

Répartition des headers (un seul émetteur par header — voir 03_SECURITE.md) :
- l'app pose CSP, X-Content-Type-Options, Referrer-Policy, Permissions-Policy ;
- Caddy pose HSTS (il termine TLS).

Session : on n'y stocke que l'IDENTITÉ (email). Le rôle est re-résolu à chaque
requête via le repository utilisateurs (cache 5 min) — une rétrogradation par
l'admin prend effet en quelques minutes, malgré des cookies non révocables.
"""

import secrets

from fastapi import HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

SESSION_EMAIL = "email"

# Politique CSP : scripts externalisés (zéro inline), styles inline tolérés
# (attributs style= des templates v1), tuiles carte OpenStreetMap, logos des
# collectivités en https (url_logo), polices Google (base.html v1).
_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: https:; "
    "connect-src 'self'; "
    "frame-ancestors 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response: Response = await call_next(request)
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = _CSP
        return response


# --- Rate limiting ---
# Derrière Caddy, l'IP réelle vient du proxy : uvicorn est lancé avec
# --proxy-headers --forwarded-allow-ips=* (réseau interne Docker uniquement),
# ce qui fait pointer request.client sur l'IP transmise par X-Forwarded-For.
limiter = Limiter(key_func=get_remote_address)


# --- CSRF (jeton de session, vérifié sur tous les POST) ---


def get_csrf_token(request: Request) -> str:
    if "csrf_token" not in request.session:
        request.session["csrf_token"] = secrets.token_urlsafe(32)
    return request.session["csrf_token"]


def verify_csrf(request: Request, token: str | None) -> None:
    session_token = request.session.get("csrf_token", "")
    if not token or not session_token or not secrets.compare_digest(token, session_token):
        raise HTTPException(
            status_code=403,
            detail="Jeton CSRF invalide — rechargez la page et réessayez.",
        )


# --- Session (identité seule) ---


def open_user_session(request: Request, email: str) -> None:
    """Ouvre la session après authentification prouvée.

    La session est entièrement régénérée (anti-fixation) : tout contenu
    antérieur, y compris le jeton CSRF, est remplacé.
    """
    request.session.clear()
    request.session[SESSION_EMAIL] = email


def close_user_session(request: Request) -> None:
    request.session.clear()


def session_email(request: Request) -> str | None:
    return request.session.get(SESSION_EMAIL)
