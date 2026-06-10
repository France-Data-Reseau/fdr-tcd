"""
Application FastAPI — Formulaire de saisie pour Grist FNCCR.
"""

import os
import secrets
import logging
from datetime import datetime
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

import grist_client as grist
import email_utils
from data_lists import DEPARTEMENTS, REGIONS, CONNECTIVITES, DEP_NUM_TO_REGION

load_dotenv()

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("app")

# --- Configuration ---
SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    SECRET_KEY = secrets.token_urlsafe(32)
    logger.warning("SECRET_KEY non défini dans .env — clé aléatoire générée (non persistante)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initialisation de l'application...")
    try:
        await grist.startup()
        logger.info("Connexion Grist OK")
    except Exception as e:
        logger.error("Erreur lors de l'initialisation Grist : %s", e)
    yield


app = FastAPI(lifespan=lifespan, debug=True)

# --- Session sécurisée ---
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    https_only=os.getenv("ENVIRONMENT") == "production",
    same_site="lax",
    max_age=3600,  # 1 heure
)


# --- Headers de sécurité HTTP ---
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net https://unpkg.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://api-adresse.data.gouv.fr; "
            "frame-ancestors 'self';"
        )
        if os.getenv("ENVIRONMENT") == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


app.add_middleware(SecurityHeadersMiddleware)

# --- Rate limiting ---
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Convertir le mapping en JSON pour le JS côté client
import json
DEP_TO_REGION_JSON = json.dumps(DEP_NUM_TO_REGION, ensure_ascii=False)
templates.env.globals["dep_to_region_json"] = DEP_TO_REGION_JSON
templates.env.globals["grist_field"] = grist.get_field_value
templates.env.globals["user"] = None
templates.env.globals["csrf_token_field"] = (
    lambda token: f'<input type="hidden" name="csrf_token" value="{token}">'
)


async def verify_projet_access(user: dict, projet_id: int) -> dict:
    """Vérifie que l'utilisateur a accès au projet. Retourne le record projet."""
    record = await grist.get_record("projets", projet_id)
    if not record:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    if user["droits"] == "Editeur" and user.get("collectivite_id"):
        coll_ref = record["fields"].get("collectivite_s_porteuse_s_")
        projet_coll_id = None
        if coll_ref and isinstance(coll_ref, list) and len(coll_ref) > 1:
            projet_coll_id = coll_ref[1]
        if projet_coll_id != user["collectivite_id"]:
            raise HTTPException(status_code=403, detail="Accès refusé : ce projet n'appartient pas à votre collectivité")
    return record


# ============================================================
# Helpers
# ============================================================

def flash(request: Request, message: str, category: str = "success"):
    if "flash" not in request.session:
        request.session["flash"] = []
    request.session["flash"].append({"message": message, "category": category})


def get_flashed_messages(request: Request) -> list[dict]:
    return request.session.pop("flash", [])


def parse_bool_field(value: str | None) -> bool:
    return bool(value)


def get_user_session(request: Request) -> dict | None:
    """Retourne les infos utilisateur stockées en session, ou None."""
    return request.session.get("user")


def safe_int(value, default: int = 0) -> int:
    """Convertit une valeur en entier de manière sécurisée."""
    if value is None or value == "":
        return default
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return default


# --- CSRF ---

def get_csrf_token(request: Request) -> str:
    """Génère ou récupère un token CSRF de session."""
    if "csrf_token" not in request.session:
        request.session["csrf_token"] = secrets.token_urlsafe(32)
    return request.session["csrf_token"]


def verify_csrf(request: Request, form) -> bool:
    """Vérifie le token CSRF du formulaire. Lève HTTPException si invalide."""
    token = form.get("csrf_token", "")
    session_token = request.session.get("csrf_token", "")
    if not token or not session_token or token != session_token:
        raise HTTPException(status_code=403, detail="Token CSRF invalide — rechargez la page et réessayez.")
    return True


def require_auth(request: Request) -> RedirectResponse | None:
    """Vérifie que l'utilisateur est connecté (Viewer autorisé).
    Retourne une RedirectResponse si non autorisé, None si OK."""
    user = get_user_session(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    if user["droits"] == "En attente":
        return RedirectResponse(url="/acces-refuse", status_code=303)
    return None


def require_editor(request: Request) -> RedirectResponse | None:
    """Vérifie que l'utilisateur a les droits d'édition (Editeur/Administrateur).
    Bloque les Visiteurs, Extention et En attente."""
    user = get_user_session(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    if user["droits"] == "En attente":
        return RedirectResponse(url="/acces-refuse", status_code=303)
    if user["droits"] in ("Visiteur", "Extention"):
        return RedirectResponse(url="/", status_code=303)
    return None


def require_admin(request: Request) -> RedirectResponse | None:
    """Réservé aux administrateurs. Redirige sinon."""
    user = get_user_session(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    if user["droits"] != "Administrateur":
        return RedirectResponse(url="/", status_code=303)
    return None


# Droits attribuables depuis la console administrateur
DROITS_ATTRIBUABLES = ["Administrateur", "Editeur", "Visiteur", "En attente"]


# ============================================================
# Auth : Login / Inscription / Logout
# ============================================================

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    # Si déjà connecté, rediriger
    user = get_user_session(request)
    if user and user["droits"] in ("Administrateur", "Editeur", "Visiteur", "Extention"):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse("login.html", {
        "request": request,
        "messages": get_flashed_messages(request),
        "csrf_token": get_csrf_token(request),
    })


@app.post("/login")
@limiter.limit("10/minute")
async def login_submit(request: Request):
    form = await request.form()
    verify_csrf(request, form)
    email = form.get("email", "").strip()
    if not email:
        flash(request, "Veuillez renseigner votre adresse email.", "error")
        return RedirectResponse(url="/login", status_code=303)

    user = await grist.get_user_by_email(email)
    if not user:
        # Email inconnu → rediriger vers inscription
        request.session["prefill_email"] = email
        flash(request, "Adresse email non reconnue. Veuillez vous inscrire.", "error")
        return RedirectResponse(url="/inscription", status_code=303)

    droits = user["fields"].get("Droits", "")
    collectivite_id = user["fields"].get("Collectivite", 0)

    # Stocker en session
    request.session["user"] = {
        "id": user["id"],
        "email": user["fields"].get("Email", ""),
        "prenom": user["fields"].get("Prenom", ""),
        "nom": user["fields"].get("Nom", ""),
        "organisation": user["fields"].get("Organisation", ""),
        "droits": droits,
        "collectivite_id": collectivite_id,
    }

    if droits == "En attente":
        return RedirectResponse(url="/acces-refuse", status_code=303)

    flash(request, f"Bienvenue, {user['fields'].get('Prenom', '')} !")
    return RedirectResponse(url="/", status_code=303)


@app.get("/inscription", response_class=HTMLResponse)
async def inscription_page(request: Request):
    prefill_email = request.session.pop("prefill_email", "")
    collectivites = grist.get_ref_records("collectivites")
    collectivites_sorted = sorted(collectivites, key=lambda r: r["fields"].get("nom", ""))
    return templates.TemplateResponse("inscription.html", {
        "request": request,
        "prefill_email": prefill_email,
        "collectivites": collectivites_sorted,
        "messages": get_flashed_messages(request),
        "csrf_token": get_csrf_token(request),
    })


@app.post("/inscription")
@limiter.limit("5/minute")
async def inscription_submit(request: Request):
    form = await request.form()
    verify_csrf(request, form)
    email = form.get("Email", "").strip()
    if not email:
        flash(request, "L'adresse email est obligatoire.", "error")
        return RedirectResponse(url="/inscription", status_code=303)

    # Vérifier si l'email existe déjà
    existing = await grist.get_user_by_email(email)
    if existing:
        flash(request, "Cette adresse email est déjà enregistrée. Connectez-vous.", "error")
        return RedirectResponse(url="/login", status_code=303)

    collectivite_id = safe_int(form.get("Collectivite"), 0)
    fields = {
        "Prenom": form.get("Prenom", "").strip(),
        "Nom": form.get("Nom", "").strip(),
        "Email": email,
        "Organisation": form.get("Organisation", "").strip(),
        "Collectivite": collectivite_id if collectivite_id else 0,
        "Droits": "En attente",
        "Date_inscription": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

    try:
        await grist.create_user(fields)
        # Notifier les administrateurs (sans bloquer si l'email échoue / SMTP absent)
        collectivite_nom = (
            grist.get_record_name("collectivites", collectivite_id)
            if collectivite_id else ""
        )
        await email_utils.notify_new_user(
            prenom=fields["Prenom"],
            nom=fields["Nom"],
            email=email,
            organisation=fields.get("Organisation", ""),
            collectivite=collectivite_nom,
        )
        flash(request, "Votre demande d'accès a été envoyée. Un administrateur la validera prochainement.")
        request.session["user"] = {
            "id": 0,
            "email": email,
            "prenom": fields["Prenom"],
            "nom": fields["Nom"],
            "organisation": fields.get("Organisation", ""),
            "droits": "En attente",
            "collectivite_id": collectivite_id,
        }
        return RedirectResponse(url="/acces-refuse", status_code=303)
    except Exception as e:
        logger.error("Erreur création utilisateur : %s", e)
        flash(request, "Une erreur s'est produite lors de l'inscription. Veuillez réessayer.", "error")
        return RedirectResponse(url="/inscription", status_code=303)


@app.get("/acces-refuse", response_class=HTMLResponse)
async def acces_refuse_page(request: Request):
    user = get_user_session(request)
    droits = user["droits"] if user else ""
    return templates.TemplateResponse("acces_refuse.html", {
        "request": request,
        "droits": droits,
        "messages": get_flashed_messages(request),
    })


@app.post("/demande-modification")
async def demande_modification(request: Request):
    """Un Visiteur demande à passer Editeur. Son statut passe à Extention."""
    form = await request.form()
    verify_csrf(request, form)
    user = get_user_session(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    if user["droits"] not in ("Visiteur",):
        flash(request, "Action non autorisée.", "error")
        return RedirectResponse(url="/", status_code=303)
    try:
        await grist.update_record("utilisateurs", user["id"], {"Droits": "Extention"})
        user["droits"] = "Extention"
        request.session["user"] = user
        flash(request, "Votre demande de modification a été envoyée. Un administrateur la validera prochainement.")
    except Exception as e:
        logger.error("Erreur demande modification : %s", e)
        flash(request, "Une erreur s'est produite. Veuillez réessayer.", "error")
    return RedirectResponse(url="/", status_code=303)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


# ============================================================
# Page 0 : Menu principal
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def menu(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    user = get_user_session(request)
    pending_count = 0
    if user and user["droits"] == "Administrateur":
        try:
            users = await grist.get_all_records("utilisateurs")
            pending_count = sum(
                1 for u in users if u["fields"].get("Droits") == "En attente"
            )
        except Exception as e:
            logger.error("Erreur comptage comptes en attente : %s", e)
    return templates.TemplateResponse("menu.html", {
        "request": request,
        "messages": get_flashed_messages(request),
        "user": user,
        "pending_count": pending_count,
        "csrf_token": get_csrf_token(request),
    })


# ============================================================
# Console Administrateur : gestion des droits utilisateurs
# ============================================================

@app.get("/admin", response_class=HTMLResponse)
async def admin_console(request: Request):
    redirect = require_admin(request)
    if redirect:
        return redirect
    users = await grist.get_all_records("utilisateurs")
    # Comptes « En attente » en premier, puis ordre alphabétique
    users_sorted = sorted(
        users,
        key=lambda r: (
            r["fields"].get("Droits") != "En attente",
            (r["fields"].get("Nom") or "").lower(),
            (r["fields"].get("Prenom") or "").lower(),
        ),
    )
    pending_count = sum(1 for u in users if u["fields"].get("Droits") == "En attente")
    collectivites = grist.get_ref_records("collectivites")
    collectivites_sorted = sorted(
        collectivites, key=lambda r: (r["fields"].get("nom") or "").lower()
    )
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "user": get_user_session(request),
        "users": users_sorted,
        "collectivites": collectivites_sorted,
        "droits_options": DROITS_ATTRIBUABLES,
        "pending_count": pending_count,
        "messages": get_flashed_messages(request),
        "csrf_token": get_csrf_token(request),
    })


@app.post("/admin/utilisateur/{user_id}")
async def admin_update_user(request: Request, user_id: int):
    redirect = require_admin(request)
    if redirect:
        return redirect
    form = await request.form()
    verify_csrf(request, form)
    current = get_user_session(request)

    droits = form.get("droits", "").strip()
    collectivite_id = safe_int(form.get("collectivite"), 0)

    # Garde-fou : un administrateur ne peut pas se retirer à lui-même le rôle Admin
    if user_id == current["id"] and droits != "Administrateur":
        flash(request, "Vous ne pouvez pas retirer votre propre rôle Administrateur.", "error")
        return RedirectResponse(url="/admin", status_code=303)

    fields = {"Collectivite": collectivite_id}
    if droits in DROITS_ATTRIBUABLES:
        fields["Droits"] = droits

    try:
        await grist.update_record("utilisateurs", user_id, fields)
        flash(request, "Utilisateur mis à jour.")
    except Exception as e:
        logger.error("Erreur mise à jour utilisateur %s : %s", user_id, e)
        flash(request, "Une erreur s'est produite lors de la mise à jour.", "error")
    return RedirectResponse(url="/admin", status_code=303)


# ============================================================
# Page 1 : Accueil complétion
# ============================================================

@app.get("/completion", response_class=HTMLResponse)
async def accueil(request: Request):
    redirect = require_editor(request)
    if redirect:
        return redirect

    user = get_user_session(request)
    collectivites = grist.get_ref_records("collectivites")
    collectivites_sorted = sorted(collectivites, key=lambda r: r["fields"].get("nom", ""))

    # Editeur : accès uniquement à sa collectivité
    if user["droits"] == "Editeur":
        if user["collectivite_id"]:
            return RedirectResponse(
                url=f"/collectivite/{user['collectivite_id']}", status_code=303
            )
        else:
            flash(request, "Votre compte n'est associé à aucune collectivité. Contactez un administrateur.", "error")
            return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse("accueil.html", {
        "request": request,
        "collectivites": collectivites_sorted,
        "messages": get_flashed_messages(request),
        "user": user,
    })


# ============================================================
# Page 2 : Collectivité
# ============================================================

def _collectivite_choices() -> dict:
    return {
        "statut": grist.get_choices("collectivites.statut"),
        "couverture": grist.get_choices("collectivites.couverture"),
        "departements": DEPARTEMENTS,
        "regions": REGIONS,
    }


@app.get("/collectivite/nouveau", response_class=HTMLResponse)
async def collectivite_nouveau(request: Request):
    redirect = require_editor(request)
    if redirect:
        return redirect
    return templates.TemplateResponse("collectivite.html", {
        "request": request,
        "mode": "creation",
        "record": None,
        "record_id": None,
        "projets_lies": [],
        "choices": _collectivite_choices(),
        "messages": get_flashed_messages(request),
        "user": get_user_session(request),
        "csrf_token": get_csrf_token(request),
    })


@app.get("/collectivite/{record_id}", response_class=HTMLResponse)
async def collectivite_modifier(request: Request, record_id: int):
    redirect = require_editor(request)
    if redirect:
        return redirect

    user = get_user_session(request)
    # Editeur : ne peut voir que sa collectivité
    if user["droits"] == "Editeur" and user["collectivite_id"] and user["collectivite_id"] != record_id:
        raise HTTPException(status_code=403, detail="Accès restreint à votre collectivité")

    record = await grist.get_record("collectivites", record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Collectivité introuvable")

    # Récupérer les projets liés
    # Méthode 1: via les champs RefList de la collectivité
    projet_ids = set()
    for ref_field in ["projet_s_", "Projets_Liste_des_projets_3_"]:
        ref_val = record["fields"].get(ref_field)
        if ref_val and isinstance(ref_val, list) and len(ref_val) > 1:
            projet_ids.update(ref_val[1:])

    # Méthode 2 (fallback): recherche inverse via collectivite_s_porteuse_s_ des projets
    all_projets = await grist.get_all_records("projets")
    for p in all_projets:
        coll_ref = p["fields"].get("collectivite_s_porteuse_s_")
        if coll_ref and isinstance(coll_ref, list) and record_id in coll_ref[1:]:
            projet_ids.add(p["id"])

    projets_lies = []
    if projet_ids:
        for p in all_projets:
            if p["id"] in projet_ids:
                projets_lies.append(p)

    return templates.TemplateResponse("collectivite.html", {
        "request": request,
        "mode": "edition",
        "record": record,
        "record_id": record_id,
        "projets_lies": projets_lies,
        "choices": _collectivite_choices(),
        "messages": get_flashed_messages(request),
        "user": get_user_session(request),
        "csrf_token": get_csrf_token(request),
    })


def _extract_collectivite_fields(form) -> dict:
    return {
        "nom": form.get("nom", ""),
        "siren": safe_int(form.get("siren"), 0),
        "statut": form.get("statut", ""),
        "couverture": form.get("couverture", ""),
        "num_dep": form.get("num_dep", ""),
        "dep": form.get("dep", ""),
        "reg": form.get("reg", ""),
        "site_web": form.get("site_web", ""),
        "adresse": form.get("adresse", ""),
    }


@app.post("/collectivite/nouveau")
async def collectivite_creer(request: Request):
    redirect = require_editor(request)
    if redirect:
        return redirect
    form = await request.form()
    verify_csrf(request, form)
    fields = _extract_collectivite_fields(form)
    try:
        result = await grist.create_record("collectivites", fields)
        new_id = result.get("records", [{}])[0].get("id")
        await grist.init_ref_cache()
        flash(request, "Collectivité créée avec succès !")
        return RedirectResponse(url=f"/collectivite/{new_id}", status_code=303)
    except Exception as e:
        logger.error("Erreur création collectivité : %s", e)
        flash(request, "Une erreur s'est produite lors de la création. Veuillez réessayer.", "error")
        return RedirectResponse(url="/collectivite/nouveau", status_code=303)


@app.post("/collectivite/{record_id}")
async def collectivite_update(request: Request, record_id: int):
    redirect = require_editor(request)
    if redirect:
        return redirect

    user = get_user_session(request)
    # IDOR : Éditeur ne peut modifier que sa propre collectivité
    if user["droits"] == "Editeur" and user.get("collectivite_id") and user["collectivite_id"] != record_id:
        raise HTTPException(status_code=403, detail="Accès restreint à votre collectivité")

    form = await request.form()
    verify_csrf(request, form)
    fields = _extract_collectivite_fields(form)
    try:
        await grist.update_record("collectivites", record_id, fields)
        await grist.init_ref_cache()
        flash(request, "Collectivité mise à jour avec succès !")
    except Exception as e:
        logger.error("Erreur mise à jour collectivité : %s", e)
        flash(request, "Une erreur s'est produite lors de la mise à jour. Veuillez réessayer.", "error")
    return RedirectResponse(url=f"/collectivite/{record_id}", status_code=303)


# ============================================================
# Page 3 : Projet
# ============================================================

def _projet_choices() -> dict:
    return {
        "avancement": grist.get_choices("projets.avancement"),
        "echelle": grist.get_choices("projets.echelle"),
        "region": REGIONS,
        "connectivites": CONNECTIVITES,
        "domaine_s_": grist.get_choices("projets.domaine_s_"),
        "mutualisation": grist.get_choices("projets.mutualisation"),
        "soutien": grist.get_choices("projets.soutien"),
        "contrat": grist.get_choices("projets.contrat"),
        "departements": DEPARTEMENTS,
    }


@app.get("/projet/nouveau", response_class=HTMLResponse)
async def projet_nouveau(request: Request, collectivite_id: int = 0):
    redirect = require_editor(request)
    if redirect:
        return redirect
    coll_name = grist.get_record_name("collectivites", collectivite_id) if collectivite_id else ""
    return templates.TemplateResponse("projet_form.html", {
        "request": request,
        "mode": "creation",
        "record": None,
        "record_id": None,
        "collectivite_id": collectivite_id,
        "collectivite_nom": coll_name,
        "choices": _projet_choices(),
        "messages": get_flashed_messages(request),
        "sous_formulaires": {},
        "user": get_user_session(request),
        "csrf_token": get_csrf_token(request),
    })


@app.post("/projet/nouveau")
async def projet_creer(request: Request):
    redirect = require_editor(request)
    if redirect:
        return redirect
    form = await request.form()
    verify_csrf(request, form)
    collectivite_id = safe_int(form.get("collectivite_id"), 0)
    fields = _extract_projet_fields(form)

    if collectivite_id:
        fields["collectivite_s_porteuse_s_"] = ["L", collectivite_id]

    try:
        result = await grist.create_record("projets", fields)
        new_id = result.get("records", [{}])[0].get("id")
        logger.info("Projet créé: new_id=%s, collectivite_id=%s", new_id, collectivite_id)

        # Ajouter le projet à la RefList projet_s_ de la collectivité
        if collectivite_id and new_id:
            try:
                await grist.add_to_reflist("collectivites", collectivite_id, "projet_s_", new_id)
                logger.info("Projet %s lié à la collectivité %s via projet_s_", new_id, collectivite_id)
            except Exception as e2:
                logger.error("Erreur liaison projet_s_ : %s", e2, exc_info=True)
            # Aussi mettre à jour le second champ RefList si nécessaire
            try:
                await grist.add_to_reflist("collectivites", collectivite_id, "Projets_Liste_des_projets_3_", new_id)
                logger.info("Projet %s lié à la collectivité %s via Projets_Liste_des_projets_3_", new_id, collectivite_id)
            except Exception as e2:
                logger.error("Erreur liaison Projets_Liste_des_projets_3_ : %s", e2, exc_info=True)

        await grist.init_ref_cache()

        action = form.get("action", "")
        if action == "autre":
            flash(request, "Projet créé avec succès ! Vous pouvez en ajouter un autre.")
            return RedirectResponse(
                url=f"/projet/nouveau?collectivite_id={collectivite_id}",
                status_code=303
            )

        flash(request, "Projet créé avec succès !")
        return RedirectResponse(
            url=f"/projet/{new_id}?collectivite_id={collectivite_id}",
            status_code=303
        )
    except Exception as e:
        logger.error("Erreur création projet : %s", e)
        flash(request, "Une erreur s'est produite lors de la création du projet. Veuillez réessayer.", "error")
        return RedirectResponse(
            url=f"/projet/nouveau?collectivite_id={collectivite_id}",
            status_code=303
        )


@app.get("/projet/{record_id}", response_class=HTMLResponse)
async def projet_modifier(request: Request, record_id: int, collectivite_id: int = 0):
    redirect = require_editor(request)
    if redirect:
        return redirect
    user = get_user_session(request)
    record = await verify_projet_access(user, record_id)

    if not collectivite_id:
        coll_ref = record["fields"].get("collectivite_s_porteuse_s_")
        if coll_ref and isinstance(coll_ref, list) and len(coll_ref) > 1:
            collectivite_id = coll_ref[1]

    coll_name = grist.get_record_name("collectivites", collectivite_id) if collectivite_id else ""
    projet_nom = record["fields"].get("nom", "")
    sous_formulaires = await _get_sous_formulaires(record_id, projet_nom)

    return templates.TemplateResponse("projet_form.html", {
        "request": request,
        "mode": "edition",
        "record": record,
        "record_id": record_id,
        "collectivite_id": collectivite_id,
        "collectivite_nom": coll_name,
        "choices": _projet_choices(),
        "messages": get_flashed_messages(request),
        "sous_formulaires": sous_formulaires,
        "user": get_user_session(request),
        "csrf_token": get_csrf_token(request),
    })


async def _get_sous_formulaires(projet_id: int, projet_nom: str = "") -> dict:
    result = {}

    cas_records = await grist.get_all_records("cas_d_usage")
    result["cas_usages"] = [
        r for r in cas_records if projet_id in grist.ref_ids(r["fields"].get("projets"))
    ]

    part_records = await grist.get_all_records("partenaires")
    result["partenaires"] = []
    for r in part_records:
        projets_ref = r["fields"].get("Projets")
        if projets_ref and isinstance(projets_ref, list) and projet_id in projets_ref[1:]:
            result["partenaires"].append(r)

    prog_records = await grist.get_all_records("programmes")
    result["programmes"] = []
    for r in prog_records:
        projets_ref = r["fields"].get("projet_s_")
        if projets_ref and isinstance(projets_ref, list) and projet_id in projets_ref[1:]:
            result["programmes"].append(r)

    doc_records = await grist.get_all_records("documents")
    result["documents"] = [r for r in doc_records if r["fields"].get("projet") == projet_id]

    contact_records = await grist.get_all_records("contacts")
    result["contacts"] = [
        r for r in contact_records
        if projet_nom and r["fields"].get("projet_s_") == projet_nom
    ]

    return result


@app.post("/projet/{record_id}")
async def projet_update(request: Request, record_id: int):
    redirect = require_editor(request)
    if redirect:
        return redirect
    user = get_user_session(request)
    await verify_projet_access(user, record_id)

    form = await request.form()
    verify_csrf(request, form)
    collectivite_id = safe_int(form.get("collectivite_id"), 0)
    fields = _extract_projet_fields(form)

    try:
        await grist.update_record("projets", record_id, fields)
        await grist.init_ref_cache()
        flash(request, "Projet mis à jour avec succès !")
    except Exception as e:
        logger.error("Erreur mise à jour projet : %s", e)
        flash(request, "Une erreur s'est produite lors de la mise à jour. Veuillez réessayer.", "error")

    return RedirectResponse(
        url=f"/projet/{record_id}?collectivite_id={collectivite_id}",
        status_code=303
    )


def _extract_projet_fields(form) -> dict:
    return {
        "nom": form.get("nom", ""),
        "description": form.get("description", ""),
        "connectivite_s_": form.get("connectivite_s_", ""),
        "domaine_s_": form.get("domaine_s_", ""),
        "avancement": form.get("avancement", ""),
        "dev_interne": parse_bool_field(form.get("dev_interne")),
        "solution_s_": form.get("solution_s_", ""),
        "echelle": form.get("echelle", ""),
        "mutualisation": form.get("mutualisation", ""),
        "beneficiaires": form.get("beneficiaires", ""),
        "soutien": form.get("soutien", ""),
        "contrat": form.get("contrat", ""),
        "departement_s_": form.get("departement_s_", ""),
        "region": form.get("region", ""),
    }


# ============================================================
# Page 4a : Cas d'usage — sélection par thème
# ============================================================

@app.get("/projet/{projet_id}/cas-usage/nouveau", response_class=HTMLResponse)
async def cas_usage_nouveau(request: Request, projet_id: int, collectivite_id: int = 0, theme: str = ""):
    redirect = require_editor(request)
    if redirect:
        return redirect

    # Un cas d'usage peut être lié à plusieurs projets : on propose tous ceux
    # qui ne sont pas DÉJÀ liés à CE projet.
    all_cas = await grist.get_all_records("cas_d_usage")
    linkable_ids = {
        r["id"] for r in all_cas
        if projet_id not in grist.ref_ids(r["fields"].get("projets"))
    }
    # On garde TOUS les thèmes (même ceux dont tous les cas sont déjà rattachés à
    # un autre projet) avec une liste éventuellement vide → le template affiche
    # alors un message explicite plutôt qu'un thème vide silencieux.
    cas_by_theme = grist.get_cas_usage_by_theme()
    cas_usage_filtered = {
        t: [c for c in cas_by_theme.get(t, []) if c["id"] in linkable_ids]
        for t in grist.get_choices("cas_d_usage.theme")
    }

    return templates.TemplateResponse("cas_usage.html", {
        "request": request,
        "projet_id": projet_id,
        "collectivite_id": collectivite_id,
        "themes": grist.get_choices("cas_d_usage.theme"),
        "cas_usage_by_theme": cas_usage_filtered,
        "selected_theme": theme,
        "messages": get_flashed_messages(request),
        "csrf_token": get_csrf_token(request),
    })


@app.post("/projet/{projet_id}/cas-usage/nouveau")
async def cas_usage_creer(request: Request, projet_id: int):
    redirect = require_editor(request)
    if redirect:
        return redirect
    user = get_user_session(request)
    await verify_projet_access(user, projet_id)

    form = await request.form()
    verify_csrf(request, form)
    collectivite_id = safe_int(form.get("collectivite_id"), 0)

    # Deux formulaires distincts pointent vers cet endpoint :
    #   mode=create → création d'un nouveau cas d'usage (champ "nouveau_nom")
    #   mode=select → liaison de cas d'usage existants (cases "cas_usage_ids")
    mode = form.get("mode", "")
    selected_ids = form.getlist("cas_usage_ids")
    theme = form.get("nouveau_theme", "")

    # Compat : si le mode n'est pas transmis, on déduit d'après les champs présents.
    if not mode:
        mode = "create" if form.get("nouveau_nom") is not None else "select"

    def _retour_formulaire():
        return RedirectResponse(
            url=f"/projet/{projet_id}/cas-usage/nouveau?collectivite_id={collectivite_id}&theme={theme}",
            status_code=303,
        )

    if mode == "create":
        nom = form.get("nouveau_nom", "").strip()
        if not nom:
            flash(request, "Le nom du cas d'usage est obligatoire.", "error")
            return _retour_formulaire()
        try:
            await grist.create_record(
                "cas_d_usage",
                {"nom": nom, "theme": theme, "projets": grist.to_reflist([projet_id])},
            )
            flash(request, "Cas d'usage créé et lié au projet !")
        except Exception as e:
            logger.error("Erreur création cas d'usage : %s", e)
            flash(request, "Une erreur s'est produite. Veuillez réessayer.", "error")
    else:  # mode == "select"
        if not selected_ids:
            flash(request, "Sélectionnez au moins un cas d'usage à lier (ou créez-en un ci-dessous).", "error")
            return _retour_formulaire()
        # Liaison multi-projets : on AJOUTE ce projet à la liste existante du cas.
        all_cas = await grist.get_all_records("cas_d_usage")
        cas_by_id = {r["id"]: r for r in all_cas}
        nb_lies = 0
        for cas_id_str in selected_ids:
            cas_id = safe_int(cas_id_str)
            if not cas_id or cas_id not in cas_by_id:
                continue
            projets = grist.ref_ids(cas_by_id[cas_id]["fields"].get("projets"))
            if projet_id in projets:
                continue
            projets.append(projet_id)
            try:
                await grist.update_record(
                    "cas_d_usage", cas_id, {"projets": grist.to_reflist(projets)}
                )
                nb_lies += 1
            except Exception as e:
                logger.error("Erreur liaison cas d'usage %s : %s", cas_id, e)
        flash(request, f"{nb_lies} cas d'usage lié(s) au projet !")

    theme_redirect = form.get("nouveau_theme", "")
    action = form.get("action", "retour")
    if action == "autre":
        return RedirectResponse(
            url=f"/projet/{projet_id}/cas-usage/nouveau?collectivite_id={collectivite_id}&theme={theme_redirect}",
            status_code=303
        )
    return RedirectResponse(
        url=f"/projet/{projet_id}?collectivite_id={collectivite_id}",
        status_code=303
    )


# ============================================================
# Page 4b : Partenaires — sélection existant ou nouveau
# ============================================================

@app.get("/projet/{projet_id}/partenaire/nouveau", response_class=HTMLResponse)
async def partenaire_nouveau(request: Request, projet_id: int, collectivite_id: int = 0):
    redirect = require_editor(request)
    if redirect:
        return redirect
    return templates.TemplateResponse("partenaire.html", {
        "request": request,
        "projet_id": projet_id,
        "collectivite_id": collectivite_id,
        "partenaires_existants": grist.get_ref_records("partenaires"),
        "choices": {"role_s_": grist.get_choices("partenaires.role_s_")},
        "messages": get_flashed_messages(request),
        "csrf_token": get_csrf_token(request),
    })


@app.post("/projet/{projet_id}/partenaire/nouveau")
async def partenaire_creer(request: Request, projet_id: int):
    redirect = require_editor(request)
    if redirect:
        return redirect
    user = get_user_session(request)
    await verify_projet_access(user, projet_id)

    form = await request.form()
    verify_csrf(request, form)
    collectivite_id = safe_int(form.get("collectivite_id"), 0)

    partenaire_existant_id = form.get("partenaire_existant_id", "")

    if partenaire_existant_id:
        pid = safe_int(partenaire_existant_id)
        if not pid:
            flash(request, "Partenaire invalide.", "error")
        else:
            try:
                await grist.add_to_reflist("partenaires", pid, "Projets", projet_id)
                flash(request, "Partenaire lié au projet !")
            except Exception as e:
                logger.error("Erreur liaison partenaire : %s", e)
                flash(request, "Une erreur s'est produite. Veuillez réessayer.", "error")
    else:
        nom = form.get("nom", "").strip()
        if not nom:
            flash(request, "Le nom du partenaire est obligatoire.", "error")
            return RedirectResponse(
                url=f"/projet/{projet_id}/partenaire/nouveau?collectivite_id={collectivite_id}",
                status_code=303
            )
        fields = {
            "nom": nom,
            "role_s_": form.get("role_s_", ""),
            "url": form.get("url", ""),
            "Projets": ["L", projet_id],
        }
        try:
            await grist.create_record("partenaires", fields)
            await grist.init_ref_cache()
            flash(request, "Partenaire créé avec succès !")
        except Exception as e:
            logger.error("Erreur création partenaire : %s", e)
            flash(request, "Une erreur s'est produite. Veuillez réessayer.", "error")

    action = form.get("action", "retour")
    if action == "autre":
        return RedirectResponse(
            url=f"/projet/{projet_id}/partenaire/nouveau?collectivite_id={collectivite_id}",
            status_code=303
        )
    return RedirectResponse(
        url=f"/projet/{projet_id}?collectivite_id={collectivite_id}",
        status_code=303
    )


# ============================================================
# Page 4c : Programmes — sélection existant ou nouveau
# ============================================================

@app.get("/projet/{projet_id}/programme/nouveau", response_class=HTMLResponse)
async def programme_nouveau(request: Request, projet_id: int, collectivite_id: int = 0):
    redirect = require_editor(request)
    if redirect:
        return redirect
    return templates.TemplateResponse("programme.html", {
        "request": request,
        "projet_id": projet_id,
        "collectivite_id": collectivite_id,
        "programmes_existants": grist.get_ref_records("programmes"),
        "choices": {"echelle": grist.get_choices("programmes.echelle")},
        "messages": get_flashed_messages(request),
        "csrf_token": get_csrf_token(request),
    })


@app.post("/projet/{projet_id}/programme/nouveau")
async def programme_creer(request: Request, projet_id: int):
    redirect = require_editor(request)
    if redirect:
        return redirect
    user = get_user_session(request)
    await verify_projet_access(user, projet_id)

    form = await request.form()
    verify_csrf(request, form)
    collectivite_id = safe_int(form.get("collectivite_id"), 0)

    programme_existant_id = form.get("programme_existant_id", "")

    if programme_existant_id:
        pid = safe_int(programme_existant_id)
        if not pid:
            flash(request, "Programme invalide.", "error")
        else:
            try:
                await grist.add_to_reflist("programmes", pid, "projet_s_", projet_id)
                flash(request, "Programme lié au projet !")
            except Exception as e:
                logger.error("Erreur liaison programme : %s", e)
                flash(request, "Une erreur s'est produite. Veuillez réessayer.", "error")
    else:
        nom = form.get("nom", "").strip()
        if not nom:
            flash(request, "Le nom du programme est obligatoire.", "error")
            return RedirectResponse(
                url=f"/projet/{projet_id}/programme/nouveau?collectivite_id={collectivite_id}",
                status_code=303
            )
        fields = {
            "nom": nom,
            "info_web": form.get("info_web", ""),
            "echelle": form.get("echelle", ""),
            "projet_s_": ["L", projet_id],
        }
        try:
            await grist.create_record("programmes", fields)
            await grist.init_ref_cache()
            flash(request, "Programme créé avec succès !")
        except Exception as e:
            logger.error("Erreur création programme : %s", e)
            flash(request, "Une erreur s'est produite. Veuillez réessayer.", "error")

    action = form.get("action", "retour")
    if action == "autre":
        return RedirectResponse(
            url=f"/projet/{projet_id}/programme/nouveau?collectivite_id={collectivite_id}",
            status_code=303
        )
    return RedirectResponse(
        url=f"/projet/{projet_id}?collectivite_id={collectivite_id}",
        status_code=303
    )


# ============================================================
# Page 4d : Documents
# ============================================================

@app.get("/projet/{projet_id}/document/nouveau", response_class=HTMLResponse)
async def document_nouveau(request: Request, projet_id: int, collectivite_id: int = 0):
    redirect = require_editor(request)
    if redirect:
        return redirect
    return templates.TemplateResponse("document.html", {
        "request": request,
        "projet_id": projet_id,
        "collectivite_id": collectivite_id,
        "messages": get_flashed_messages(request),
        "csrf_token": get_csrf_token(request),
    })


@app.post("/projet/{projet_id}/document/nouveau")
async def document_creer(request: Request, projet_id: int):
    redirect = require_editor(request)
    if redirect:
        return redirect
    user = get_user_session(request)
    await verify_projet_access(user, projet_id)

    form = await request.form()
    verify_csrf(request, form)
    collectivite_id = safe_int(form.get("collectivite_id"), 0)
    fields = {
        "titre": form.get("titre", ""),
        "en_ligne": form.get("en_ligne", ""),
        "type": form.get("type", ""),
        "projet": projet_id,
    }
    try:
        await grist.create_record("documents", fields)
        flash(request, "Document créé avec succès !")
    except Exception as e:
        logger.error("Erreur création document : %s", e)
        flash(request, "Une erreur s'est produite. Veuillez réessayer.", "error")

    action = form.get("action", "retour")
    if action == "autre":
        return RedirectResponse(
            url=f"/projet/{projet_id}/document/nouveau?collectivite_id={collectivite_id}",
            status_code=303
        )
    return RedirectResponse(
        url=f"/projet/{projet_id}?collectivite_id={collectivite_id}",
        status_code=303
    )


# ============================================================
# Page 4e : Contacts
# ============================================================

@app.get("/projet/{projet_id}/contact/nouveau", response_class=HTMLResponse)
async def contact_nouveau(request: Request, projet_id: int, collectivite_id: int = 0):
    redirect = require_editor(request)
    if redirect:
        return redirect
    return templates.TemplateResponse("contact.html", {
        "request": request,
        "projet_id": projet_id,
        "collectivite_id": collectivite_id,
        "collectivite_nom": grist.get_record_name("collectivites", collectivite_id) if collectivite_id else "",
        "messages": get_flashed_messages(request),
        "csrf_token": get_csrf_token(request),
    })


@app.post("/projet/{projet_id}/contact/nouveau")
async def contact_creer(request: Request, projet_id: int):
    redirect = require_editor(request)
    if redirect:
        return redirect
    user = get_user_session(request)
    await verify_projet_access(user, projet_id)

    form = await request.form()
    verify_csrf(request, form)
    collectivite_id = safe_int(form.get("collectivite_id"), 0)
    fields = {
        "prenom": form.get("prenom", ""),
        "nom": form.get("nom", ""),
        "elu_e": parse_bool_field(form.get("elu_e")),
        "fonction": form.get("fonction", ""),
        "email": form.get("email", ""),
        "telephone": form.get("telephone", ""),
        "mobile": form.get("mobile", ""),
    }
    # Lien vers la collectivité (Ref simple)
    if collectivite_id:
        fields["collectivite_s_"] = collectivite_id

    # Le champ projet_s_ est de type Text dans Grist (pas RefList)
    # On récupère le nom du projet pour l'ajouter au texte
    projet_record = await grist.get_record("projets", projet_id)
    if projet_record:
        projet_nom = projet_record["fields"].get("nom", "")
        if projet_nom:
            fields["projet_s_"] = projet_nom

    try:
        await grist.create_record("contacts", fields)
        flash(request, "Contact créé avec succès !")
    except Exception as e:
        logger.error("Erreur création contact : %s", e)
        flash(request, "Une erreur s'est produite. Veuillez réessayer.", "error")

    action = form.get("action", "retour")
    if action == "autre":
        return RedirectResponse(
            url=f"/projet/{projet_id}/contact/nouveau?collectivite_id={collectivite_id}",
            status_code=303
        )
    return RedirectResponse(
        url=f"/projet/{projet_id}?collectivite_id={collectivite_id}",
        status_code=303
    )


# ============================================================
# Restitution
# ============================================================

@app.get("/restitution", response_class=HTMLResponse)
async def restitution_page(request: Request):
    redirect = require_auth(request)
    if redirect:
        return redirect
    user = get_user_session(request)
    collectivites = grist.get_ref_records("collectivites")
    collectivites_sorted = sorted(collectivites, key=lambda r: r["fields"].get("nom", ""))
    return templates.TemplateResponse("restitution.html", {
        "request": request,
        "messages": get_flashed_messages(request),
        "user": user,
        "collectivites": collectivites_sorted,
    })


@app.get("/api/restitution/donnees")
async def api_restitution_donnees(request: Request):
    user = get_user_session(request)
    if not user or user["droits"] == "En attente":
        return JSONResponse({"error": "Non autorisé"}, status_code=401)
    data = await grist.get_restitution_data()
    return JSONResponse(data)
