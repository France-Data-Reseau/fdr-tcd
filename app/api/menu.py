"""Menu principal (tuiles selon rôle) et supervision.

``/health`` ne fait AUCUNE I/O externe (ni Grist ni api-adresse) : c'est un
test de vivacité utilisé par le HEALTHCHECK Docker — une panne amont ne doit
pas provoquer de redémarrage en boucle d'une app saine.
"""

from fastapi import APIRouter, Depends, Request

from app.core.config import Settings
from app.core.templating import render
from app.dependencies import (
    get_settings,
    get_utilisateur_repository,
    require_auth,
)
from app.repositories.types import (
    DROIT_ADMINISTRATEUR,
    DROIT_EN_ATTENTE,
    UtilisateurRecord,
)

router = APIRouter()


@router.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict:
    return {"statut": "ok", "version": settings.GIT_SHA}


@router.get("/")
def menu(request: Request, utilisateur: UtilisateurRecord = Depends(require_auth)):
    pending_count = 0
    if utilisateur.get("droits") == DROIT_ADMINISTRATEUR:
        pending_count = sum(
            1
            for u in get_utilisateur_repository().list_all()
            if u.get("droits") == DROIT_EN_ATTENTE
        )
    return render(
        request, "menu.html", {"pending_count": pending_count}, user=utilisateur
    )
