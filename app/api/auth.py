"""Routes d'authentification : magic link, inscription, élévation, logout.

Sécurité (voir 02_AUTHENTIFICATION.md / 03_SECURITE.md) :
- réponses NEUTRES au login et à l'inscription (anti-énumération) ;
- le GET /auth/verifier n'a AUCUN effet de bord (les scanners d'emails
  préchargent les liens) : la consommation du jeton se fait au POST ;
- rate limiting par IP (slowapi) + par email ciblé (AuthService) ;
- CSRF vérifié sur tous les POST ; routes synchrones (threadpool FastAPI).
"""

import asyncio
import logging

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
    get_magic_link_service,
    get_notification_service,
    get_oidc_service,
    get_utilisateur_repository,
    require_auth,
)
from app.repositories.types import DROIT_EN_ATTENTE
from app.services.password_service import LONGUEUR_MIN
from app.services.types import (
    ChangePasswordForm,
    InscriptionForm,
    LoginForm,
    PasswordLoginForm,
)

logger = logging.getLogger(__name__)
router = APIRouter()

MESSAGE_NEUTRE_LOGIN = (
    "Si un compte existe pour cette adresse, un lien de connexion vient de lui "
    "être envoyé. Pensez à vérifier vos courriers indésirables."
)
MESSAGE_NEUTRE_INSCRIPTION = (
    "Votre demande a été prise en compte. Vous recevrez un email dès qu'un "
    "administrateur l'aura traitée."
)
MESSAGE_LIEN_INVALIDE = (
    "Ce lien de connexion est invalide ou a expiré. Demandez-en un nouveau."
)
MESSAGE_LOGIN_ECHEC = "Adresse email ou mot de passe incorrect."
MESSAGE_PASSWORD_FAIBLE = (
    f"Le mot de passe doit comporter au moins {LONGUEUR_MIN} caractères "
    "et ne pas être trop courant."
)


@router.get("/login")
def login_page(request: Request):
    if get_current_user(request) is not None:
        return RedirectResponse(url="/", status_code=303)
    return render(
        request,
        "login.html",
        {
            "sso_actif": get_oidc_service().enabled,
            "smtp_actif": get_notification_service().is_configured,
        },
    )


@router.get("/auth/sso")
async def sso_demarrer(request: Request):
    """Démarre le flux OIDC vers l'IdP de France Data Réseau."""
    service = get_oidc_service()
    if not service.enabled:
        raise HTTPException(status_code=404, detail="Page introuvable")
    return await service.authorize_redirect(request)


@router.get("/auth/callback")
async def sso_callback(request: Request):
    """Retour de l'IdP : email vérifié → même pipeline que le magic link."""
    service = get_oidc_service()
    if not service.enabled:
        raise HTTPException(status_code=404, detail="Page introuvable")
    email = await service.fetch_verified_email(request)
    if email is None:
        flash(request, "La connexion via France Data Réseau a échoué. "
                       "Réessayez ou utilisez le lien par email.", "error")
        return RedirectResponse(url="/login", status_code=303)
    utilisateur = await asyncio.to_thread(
        get_utilisateur_repository().get_by_email, email
    )
    if utilisateur is None:
        # Identité vérifiée par l'IdP mais aucun compte applicatif : on
        # l'oriente vers la demande d'accès (pré-remplie)
        request.session["prefill_email"] = email
        flash(request, "Aucun compte n'existe pour cette adresse. "
                       "Remplissez la demande d'accès ci-dessous.", "error")
        return RedirectResponse(url="/inscription", status_code=303)
    open_user_session(request, str(utilisateur.get("email", "")))
    if utilisateur.get("droits") == DROIT_EN_ATTENTE:
        return RedirectResponse(url="/acces-refuse", status_code=303)
    flash(request, f"Bienvenue, {utilisateur.get('prenom', '')} !")
    return RedirectResponse(url="/", status_code=303)


@router.post("/login")
@limiter.limit("10/minute")
def login_submit(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
    csrf_token: str = Form(""),
):
    """Login par mot de passe (chemin principal). Réponse neutre commune à
    tous les échecs (email inconnu, sans hash, ou mauvais mot de passe)."""
    verify_csrf(request, csrf_token)
    try:
        formulaire = PasswordLoginForm(email=email, password=password)
    except ValidationError:
        flash(request, MESSAGE_LOGIN_ECHEC, "error")
        return RedirectResponse(url="/login", status_code=303)
    utilisateur = get_auth_service().authenticate(
        formulaire.email, formulaire.password
    )
    if utilisateur is None:
        flash(request, MESSAGE_LOGIN_ECHEC, "error")
        return RedirectResponse(url="/login", status_code=303)
    open_user_session(request, str(utilisateur.get("email", "")))
    if utilisateur.get("droits") == DROIT_EN_ATTENTE:
        return RedirectResponse(url="/acces-refuse", status_code=303)
    flash(request, f"Bienvenue, {utilisateur.get('prenom', '')} !")
    return RedirectResponse(url="/", status_code=303)


@router.post("/auth/lien-email")
@limiter.limit("5/minute")
def demander_lien_email(
    request: Request, email: str = Form(""), csrf_token: str = Form("")
):
    """Magic link — chemin secondaire, actif uniquement si le SMTP est
    configuré (sinon 404). Réponse neutre (anti-énumération)."""
    verify_csrf(request, csrf_token)
    if not get_notification_service().is_configured:
        raise HTTPException(status_code=404, detail="Page introuvable")
    try:
        formulaire = LoginForm(email=email)
    except ValidationError:
        flash(request, "Veuillez renseigner une adresse email valide.", "error")
        return RedirectResponse(url="/login", status_code=303)
    get_auth_service().request_login(formulaire.email)
    flash(request, MESSAGE_NEUTRE_LOGIN)
    return RedirectResponse(url="/login", status_code=303)


@router.get("/auth/verifier")
def verifier_page(request: Request, token: str = ""):
    """Page de confirmation — aucun effet de bord (jeton non consommé)."""
    if not get_magic_link_service().peek_valid(token):
        flash(request, MESSAGE_LIEN_INVALIDE, "error")
        return RedirectResponse(url="/login", status_code=303)
    return render(request, "confirmation_lien.html", {"token": token})


@router.post("/auth/verifier")
@limiter.limit("10/minute")
def verifier_submit(request: Request, token: str = Form(""), csrf_token: str = Form("")):
    verify_csrf(request, csrf_token)
    utilisateur = get_auth_service().complete_login(token)
    if utilisateur is None:
        flash(request, MESSAGE_LIEN_INVALIDE, "error")
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
    password: str = Form(""),
    password_confirm: str = Form(""),
    csrf_token: str = Form(""),
):
    verify_csrf(request, csrf_token)
    collectivites = get_collectivite_repository()
    try:
        collectivite_id = int(collectivite or 0)
    except ValueError:
        collectivite_id = 0
    if password != password_confirm:
        flash(request, "La confirmation du mot de passe ne correspond pas.", "error")
        return RedirectResponse(url="/inscription", status_code=303)
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
            password=password,
        )
    except ValidationError:
        flash(
            request,
            "Formulaire incomplet ou invalide — vérifiez le prénom, le nom, "
            f"l'adresse email et le mot de passe (au moins {LONGUEUR_MIN} "
            "caractères).",
            "error",
        )
        return RedirectResponse(url="/inscription", status_code=303)
    get_auth_service().register(formulaire)
    # Même message que l'email existe déjà ou non (anti-énumération)
    flash(request, MESSAGE_NEUTRE_INSCRIPTION)
    return RedirectResponse(url="/login", status_code=303)


@router.get("/mon-mot-de-passe")
def mot_de_passe_page(request: Request):
    utilisateur = require_auth(request)
    return render(request, "mon_mot_de_passe.html", user=utilisateur)


@router.post("/mon-mot-de-passe")
@limiter.limit("10/minute")
def mot_de_passe_submit(
    request: Request,
    actuel: str = Form(""),
    nouveau: str = Form(""),
    confirmation: str = Form(""),
    csrf_token: str = Form(""),
):
    verify_csrf(request, csrf_token)
    utilisateur = require_auth(request)
    service = get_auth_service()
    if not service.verify_current_password(utilisateur, actuel):
        flash(request, "Le mot de passe actuel est incorrect.", "error")
        return RedirectResponse(url="/mon-mot-de-passe", status_code=303)
    if nouveau != confirmation:
        flash(request, "La confirmation ne correspond pas au nouveau mot de passe.",
              "error")
        return RedirectResponse(url="/mon-mot-de-passe", status_code=303)
    try:
        ChangePasswordForm(actuel=actuel, nouveau=nouveau)
    except ValidationError:
        flash(request, MESSAGE_PASSWORD_FAIBLE, "error")
        return RedirectResponse(url="/mon-mot-de-passe", status_code=303)
    service.set_password(utilisateur["id"], nouveau)
    flash(request, "Votre mot de passe a été mis à jour.")
    return RedirectResponse(url="/", status_code=303)


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
