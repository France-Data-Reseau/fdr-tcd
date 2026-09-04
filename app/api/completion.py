"""Accueil de la complétion : choix de la collectivité.

Un Éditeur est redirigé directement sur SA collectivité (anti-IDOR par
construction) ; un Administrateur voit le sélecteur complet.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from app.core.flash import flash
from app.core.templating import render
from app.dependencies import get_collectivite_repository, require_editor
from app.repositories.types import DROIT_EDITEUR, UtilisateurRecord

router = APIRouter()


@router.get("/contribution")
def completion(
    request: Request, utilisateur: UtilisateurRecord = Depends(require_editor)
):
    if utilisateur.get("droits") == DROIT_EDITEUR:
        collectivite_id = utilisateur.get("collectivite") or 0
        if collectivite_id:
            return RedirectResponse(
                url=f"/collectivite/{collectivite_id}", status_code=303
            )
        flash(
            request,
            "Votre compte n'est associé à aucune collectivité. "
            "Contactez un administrateur.",
            "error",
        )
        return RedirectResponse(url="/", status_code=303)

    return render(
        request,
        "accueil.html",
        {"collectivites": get_collectivite_repository().list_sorted()},
        user=utilisateur,
    )
