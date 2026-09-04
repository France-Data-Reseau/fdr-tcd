"""Restitution : page cartographique et API de données.

L'API exige une session valide (401 JSON sinon — parité v1), répond en
``Cache-Control: private`` (pas de cache intermédiaire) et est rate-limitée
modérément (anti-scraping). Le payload ne contient JAMAIS les emails ni
téléphones des contacts.
"""

import asyncio

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.core.security import limiter
from app.core.templating import render
from app.dependencies import (
    get_collectivite_repository,
    get_current_user,
    get_restitution_service,
    require_auth,
)
from app.repositories.types import DROIT_EN_ATTENTE, UtilisateurRecord

router = APIRouter()


@router.get("/cartographie")
def restitution_page(
    request: Request, utilisateur: UtilisateurRecord = Depends(require_auth)
):
    return render(
        request,
        "restitution.html",
        {"collectivites": get_collectivite_repository().list_sorted()},
        user=utilisateur,
    )


@router.get("/api/cartographie/donnees")
@limiter.limit("30/minute")
async def api_restitution_donnees(request: Request):
    # Route async (gather interne) : la résolution du rôle, synchrone,
    # part dans un thread pour ne pas bloquer l'event loop.
    utilisateur = await asyncio.to_thread(get_current_user, request)
    if utilisateur is None or utilisateur.get("droits") == DROIT_EN_ATTENTE:
        return JSONResponse({"error": "Non autorisé"}, status_code=401)
    data = await get_restitution_service().build_payload()
    return JSONResponse(data, headers={"Cache-Control": "private"})
