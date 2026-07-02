"""Environnement Jinja2 (autoescape actif par défaut) et contexte commun.

Les templates reçoivent toujours : request, messages (flash), csrf_token,
user (vue utilisateur ou None).
"""

from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.core.flash import get_flashed_messages
from app.core.security import get_csrf_token
from app.repositories.base import first_value, ref_ids
from app.repositories.types import UtilisateurRecord

BASE_DIR = Path(__file__).resolve().parent.parent.parent

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
# Helpers v1 conservés (adaptés aux records aplatis pygrister)
templates.env.globals["grist_field"] = first_value
templates.env.globals["ref_ids_of"] = lambda record, field: ref_ids(
    record.get(field) if record else None
)


def user_view(record: UtilisateurRecord | None) -> dict | None:
    """Vue utilisateur pour les templates (mêmes clés que la session v1)."""
    if record is None:
        return None
    return {
        "id": record.get("id", 0),
        "email": record.get("email", ""),
        "prenom": record.get("prenom", ""),
        "nom": record.get("nom", ""),
        "organisation": record.get("organisation", ""),
        "droits": record.get("droits", ""),
        "collectivite_id": record.get("collectivite", 0) or 0,
    }


def render(
    request: Request,
    template: str,
    contexte: dict[str, Any] | None = None,
    user: UtilisateurRecord | None = None,
    status_code: int = 200,
):
    """Rend un template avec le contexte commun (messages, csrf, user)."""
    commun: dict[str, Any] = {
        "messages": get_flashed_messages(request),
        "csrf_token": get_csrf_token(request),
        "user": user_view(user),
    }
    if contexte:
        commun.update(contexte)
    return templates.TemplateResponse(
        request, template, commun, status_code=status_code
    )
