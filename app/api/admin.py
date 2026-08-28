"""Console administrateur : liste des utilisateurs, validation, droits."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from app.core.flash import flash
from app.core.security import verify_csrf
from app.core.templating import render
from app.dependencies import (
    get_admin_service,
    get_collectivite_repository,
    require_admin,
)
from app.repositories.types import UtilisateurRecord
from app.services.types import DROITS_ATTRIBUABLES

router = APIRouter()


@router.get("/admin")
def admin_console(
    request: Request, admin: UtilisateurRecord = Depends(require_admin)
):
    service = get_admin_service()
    return render(
        request,
        "admin.html",
        {
            "users": service.list_users_sorted(),
            "collectivites": get_collectivite_repository().list_sorted(),
            "droits_options": list(DROITS_ATTRIBUABLES),
            "pending_count": service.pending_count(),
        },
        user=admin,
    )


@router.post("/admin/utilisateur/{user_id}")
def admin_update_user(
    request: Request,
    user_id: int,
    droits: str = Form(""),
    collectivite: str = Form("0"),
    csrf_token: str = Form(""),
    admin: UtilisateurRecord = Depends(require_admin),
):
    verify_csrf(request, csrf_token)
    try:
        collectivite_id = max(0, int(collectivite or 0))
    except ValueError:
        collectivite_id = 0
    succes, message = get_admin_service().update_user(
        admin, user_id, droits.strip(), collectivite_id
    )
    flash(request, message, "success" if succes else "error")
    return RedirectResponse(url="/admin", status_code=303)
