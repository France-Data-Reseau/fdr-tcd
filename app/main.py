"""Application FNCCR « Cartographie des Usages TCD » V2 — point d'entrée.

Fichier volontairement fin : middlewares + routers + handlers. Toute logique
vit dans services/ et repositories/ (voir docs_architecture/01_ARCHITECTURE.md).
"""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.api import (
    admin,
    auth,
    collectivites,
    completion,
    menu,
    projets,
    restitution,
    sous_objets,
)
from app.core.security import SecurityHeadersMiddleware, limiter
from app.core.templating import BASE_DIR, render
from app.dependencies import AuthRedirect, get_settings
from app.repositories.base import GristError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Vérification du schéma Grist au démarrage : alerte immédiate (CRITICAL)
    # si une table/colonne attendue a disparu — sans empêcher le démarrage.
    try:
        from app.dependencies import get_grist_api
        from scripts.check_grist_schema import verifier_schema

        divergences = await asyncio.to_thread(verifier_schema, get_grist_api())
        if divergences:
            for d in divergences:
                logger.critical("Schéma Grist : %s", d)
            logger.critical("Schéma Grist DIVERGENT (%d écarts) — corriger au plus vite",
                            len(divergences))
        else:
            logger.info("Schéma Grist conforme")
    except Exception as exc:  # jamais bloquant (Grist indisponible, tests…)
        logger.warning("Vérification du schéma Grist impossible au démarrage : %s",
                       type(exc).__name__)
    yield


app = FastAPI(lifespan=lifespan, debug=False, docs_url=None, redoc_url=None,
              openapi_url=None)

# L'ordre compte : les headers de sécurité enveloppent tout, la session est
# disponible pour les routes. SECRET_KEY exigée en production (config.py).
settings = get_settings()
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    https_only=settings.is_production,
    same_site="lax",
    max_age=settings.SESSION_MAX_AGE_SECONDS,
)

app.state.limiter = limiter

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

app.include_router(menu.router)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(completion.router)
app.include_router(collectivites.router)
app.include_router(projets.router)
app.include_router(sous_objets.router)
app.include_router(restitution.router)


@app.exception_handler(AuthRedirect)
async def auth_redirect_handler(request: Request, exc: AuthRedirect):
    return RedirectResponse(url=exc.url, status_code=303)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return render(request, "erreur.html", {
        "titre": "Trop de tentatives",
        "message": "Trop de tentatives — patientez une minute puis réessayez.",
    }, status_code=429)


@app.exception_handler(GristError)
async def grist_error_handler(request: Request, exc: GristError):
    # Message sobre : jamais de détail technique côté utilisateur
    logger.error("Erreur Grist remontée à l'utilisateur : %s", exc)
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            {"error": "Service de données momentanément indisponible"},
            status_code=503,
        )
    return render(request, "erreur.html", {
        "titre": "Service indisponible",
        "message": "Le service de données est momentanément indisponible. "
                   "Réessayez dans quelques instants.",
    }, status_code=503)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    # 404 (anti-IDOR, route inconnue) et 403 (CSRF) : page stylée pour le
    # navigateur, JSON pour l'API — parité avec grist_error_handler.
    detail = str(exc.detail) if exc.detail else ""
    if request.url.path.startswith("/api/"):
        return JSONResponse({"error": detail or "Erreur"}, status_code=exc.status_code)
    titres = {403: "Accès refusé", 404: "Page introuvable"}
    return render(request, "erreur.html", {
        "titre": titres.get(exc.status_code, "Erreur"),
        "message": detail or "Une erreur est survenue.",
    }, status_code=exc.status_code)
