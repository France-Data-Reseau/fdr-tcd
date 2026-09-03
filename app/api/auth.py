"""Routes d'authentification : OIDC, inscription, élévation, logout.

Sécurité (voir 02_AUTHENTIFICATION.md / 03_SECURITE.md) :
- réponses NEUTRES à l'inscription (anti-énumération) ;
- callback OIDC sobre en cas d'échec ;
- CSRF vérifié sur tous les POST ; routes synchrones (threadpool FastAPI).
"""

import asyncio
import logging

import httpx
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

from app.core.flash import flash
from app.core.security import (
    close_user_session,
    limiter,
    open_user_session,
    verify_csrf,
)
from app.core.templating import render
from app.dependencies import (
    get_auth_service,
    get_collectivite_repository,
    get_current_user,
    get_oidc_service,
    get_utilisateur_repository,
    require_auth,
)
from app.repositories.types import DROIT_EN_ATTENTE
from app.services.types import InscriptionForm

logger = logging.getLogger(__name__)
router = APIRouter()

MESSAGE_NEUTRE_INSCRIPTION = (
    "Votre demande a été prise en compte. Vous recevrez un email dès qu'un "
    "administrateur l'aura traitée."
)


@router.get("/login")
def login_page(request: Request):
    if get_current_user(request) is not None:
        return RedirectResponse(url="/", status_code=303)
    return render(
        request,
        "login.html",
        {"sso_actif": get_oidc_service().enabled},
    )


@router.get("/auth/sso")
async def sso_demarrer(request: Request):
    """Démarre le flux OIDC vers l'IdP de France Data Réseau."""
    service = get_oidc_service()
    if not service.enabled:
        raise HTTPException(status_code=404, detail="Page introuvable")
    try:
        url = await service.authorize_redirect_url(request)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("SSO : démarrage impossible (%s)", type(exc).__name__)
        flash(request, "Le service d'authentification est momentanément indisponible.",
              "error")
        return RedirectResponse(url="/login", status_code=303)
    return RedirectResponse(url=url, status_code=303)


@router.get("/auth/callback")
async def sso_callback(request: Request):
    """Retour de l'IdP : email vérifié → même pipeline que le magic link."""
    service = get_oidc_service()
    if not service.enabled:
        raise HTTPException(status_code=404, detail="Page introuvable")
    email = await service.fetch_verified_email(request)
    if email is None:
        flash(request, "La connexion via France Data Réseau a échoué. Réessayez.",
              "error")
        return RedirectResponse(url="/login", status_code=303)
    utilisateur = await asyncio.to_thread(
        get_utilisateur_repository().get_by_email, email
    )
    if utilisateur is None:
        # Liste fermée (cadrage 2026-08-27) : identité vérifiée par l'IdP mais
        # aucun compte applicatif -> accès refusé. Les comptes sont créés par un
        # administrateur (pas d'auto-inscription).
        flash(request, "Votre compte n'est pas encore autorisé sur la "
                       "plateforme. Contactez un administrateur FNCCR.", "error")
        return RedirectResponse(url="/login", status_code=303)
    open_user_session(request, str(utilisateur.get("email", "")))
    if utilisateur.get("droits") == DROIT_EN_ATTENTE:
        return RedirectResponse(url="/acces-refuse", status_code=303)
    flash(request, f"Bienvenue, {utilisateur.get('prenom', '')} !")
    return RedirectResponse(url="/", status_code=303)


@router.get("/inscription")
def inscription_page(request: Request):
    collectivites = get_collectivite_repository().list_sorted()
    return render(
        request,
        "inscription.html",
        {
            "collectivites": collectivites,
            "prefill_email": request.session.pop("prefill_email", ""),
        },
    )


@router.post("/inscription")
@limiter.limit("5/minute")
def inscription_submit(
    request: Request,
    prenom: str = Form(""),
    nom: str = Form(""),
    email: str = Form(""),
    organisation: str = Form(""),
    collectivite: str = Form("0"),
    csrf_token: str = Form(""),
):
    verify_csrf(request, csrf_token)
    collectivites = get_collectivite_repository()
    try:
        collectivite_id = int(collectivite or 0)
    except ValueError:
        collectivite_id = 0
    try:
        formulaire = InscriptionForm(
            prenom=prenom,
            nom=nom,
            email=email,
            organisation=organisation,
            collectivite_id=max(0, collectivite_id),
            collectivite_nom=collectivites.get_nom(collectivite_id)
            if collectivite_id
            else "",
        )
    except ValidationError:
        flash(
            request,
            "Formulaire incomplet ou invalide — vérifiez le prénom, le nom, "
            "et l'adresse email.",
            "error",
        )
        return RedirectResponse(url="/inscription", status_code=303)
    get_auth_service().register(formulaire)
    # Même message que l'email existe déjà ou non (anti-énumération)
    flash(request, MESSAGE_NEUTRE_INSCRIPTION)
    return RedirectResponse(url="/login", status_code=303)


@router.get("/acces-refuse")
def acces_refuse_page(request: Request):
    utilisateur = get_current_user(request)
    droits = utilisateur.get("droits", "") if utilisateur else DROIT_EN_ATTENTE
    return render(request, "acces_refuse.html", {"droits": droits}, user=utilisateur)


@router.post("/demande-modification")
@limiter.limit("5/minute")
def demande_modification(request: Request, csrf_token: str = Form("")):
    verify_csrf(request, csrf_token)
    utilisateur = require_auth(request)
    if get_auth_service().request_elevation(utilisateur):
        flash(
            request,
            "Votre demande de modification a été envoyée. Un administrateur la "
            "validera prochainement.",
        )
    else:
        flash(request, "Action non autorisée.", "error")
    return RedirectResponse(url="/", status_code=303)


@router.get("/logout")
def logout(request: Request):
    close_user_session(request)
    return RedirectResponse(url="/login", status_code=303)
