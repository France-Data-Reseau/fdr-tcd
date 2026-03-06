"""
Application FastAPI — Formulaire de saisie pour Grist FNCCR.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

import grist_client as grist
from data_lists import DEPARTEMENTS, REGIONS, CONNECTIVITES, DEP_NUM_TO_REGION

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initialisation de l'application...")
    try:
        await grist.startup()
        logger.info("Connexion Grist OK")
    except Exception as e:
        logger.error("Erreur lors de l'initialisation Grist : %s", e)
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key="fnccr-form-secret-key-change-me")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Convertir le mapping en JSON pour le JS côté client
import json
DEP_TO_REGION_JSON = json.dumps(DEP_NUM_TO_REGION, ensure_ascii=False)
templates.env.globals["dep_to_region_json"] = DEP_TO_REGION_JSON


# ============================================================
# Helpers
# ============================================================

def flash(request: Request, message: str, category: str = "success"):
    if "flash" not in request.session:
        request.session["flash"] = []
    request.session["flash"].append({"message": message, "category": category})


def get_flashed_messages(request: Request) -> list[dict]:
    return request.session.pop("flash", [])


def parse_bool_field(value: str | None) -> str:
    return "checked" if value else ""


# ============================================================
# Page 1 : Accueil
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def accueil(request: Request):
    collectivites = grist.get_ref_records("collectivites")
    collectivites_sorted = sorted(collectivites, key=lambda r: r["fields"].get("nom", ""))
    return templates.TemplateResponse("accueil.html", {
        "request": request,
        "collectivites": collectivites_sorted,
        "messages": get_flashed_messages(request),
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
    return templates.TemplateResponse("collectivite.html", {
        "request": request,
        "mode": "creation",
        "record": None,
        "record_id": None,
        "projets_lies": [],
        "choices": _collectivite_choices(),
        "messages": get_flashed_messages(request),
    })


@app.get("/collectivite/{record_id}", response_class=HTMLResponse)
async def collectivite_modifier(request: Request, record_id: int):
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
    })


def _extract_collectivite_fields(form) -> dict:
    return {
        "nom": form.get("nom", ""),
        "siren": int(form.get("siren")) if form.get("siren") else 0,
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
    form = await request.form()
    fields = _extract_collectivite_fields(form)
    try:
        result = await grist.create_record("collectivites", fields)
        new_id = result.get("records", [{}])[0].get("id")
        await grist.init_ref_cache()
        flash(request, "Collectivité créée avec succès !")
        return RedirectResponse(url=f"/collectivite/{new_id}", status_code=303)
    except Exception as e:
        logger.error("Erreur création collectivité : %s", e)
        flash(request, f"Erreur lors de la création : {e}", "error")
        return RedirectResponse(url="/collectivite/nouveau", status_code=303)


@app.post("/collectivite/{record_id}")
async def collectivite_update(request: Request, record_id: int):
    form = await request.form()
    fields = _extract_collectivite_fields(form)
    try:
        await grist.update_record("collectivites", record_id, fields)
        await grist.init_ref_cache()
        flash(request, "Collectivité mise à jour avec succès !")
    except Exception as e:
        logger.error("Erreur mise à jour collectivité : %s", e)
        flash(request, f"Erreur lors de la mise à jour : {e}", "error")
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
    })


@app.post("/projet/nouveau")
async def projet_creer(request: Request):
    form = await request.form()
    cid_raw = form.get("collectivite_id", "")
    collectivite_id = int(cid_raw) if cid_raw and cid_raw.strip() else 0
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
        flash(request, f"Erreur lors de la création : {e}", "error")
        return RedirectResponse(
            url=f"/projet/nouveau?collectivite_id={collectivite_id}",
            status_code=303
        )


@app.get("/projet/{record_id}", response_class=HTMLResponse)
async def projet_modifier(request: Request, record_id: int, collectivite_id: int = 0):
    record = await grist.get_record("projets", record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Projet introuvable")

    if not collectivite_id:
        coll_ref = record["fields"].get("collectivite_s_porteuse_s_")
        if coll_ref and isinstance(coll_ref, list) and len(coll_ref) > 1:
            collectivite_id = coll_ref[1]

    coll_name = grist.get_record_name("collectivites", collectivite_id) if collectivite_id else ""
    sous_formulaires = await _get_sous_formulaires(record_id)

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
    })


async def _get_sous_formulaires(projet_id: int) -> dict:
    result = {}

    cas_records = await grist.get_all_records("cas_d_usage")
    result["cas_usages"] = [r for r in cas_records if r["fields"].get("projets") == projet_id]

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

    result["contacts"] = []

    return result


@app.post("/projet/{record_id}")
async def projet_update(request: Request, record_id: int):
    form = await request.form()
    collectivite_id = int(form.get("collectivite_id", 0))
    fields = _extract_projet_fields(form)

    try:
        await grist.update_record("projets", record_id, fields)
        await grist.init_ref_cache()
        flash(request, "Projet mis à jour avec succès !")
    except Exception as e:
        logger.error("Erreur mise à jour projet : %s", e)
        flash(request, f"Erreur lors de la mise à jour : {e}", "error")

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
async def cas_usage_nouveau(request: Request, projet_id: int, collectivite_id: int = 0):
    return templates.TemplateResponse("cas_usage.html", {
        "request": request,
        "projet_id": projet_id,
        "collectivite_id": collectivite_id,
        "themes": grist.get_choices("cas_d_usage.theme"),
        "cas_usage_by_theme": grist.get_cas_usage_by_theme(),
        "messages": get_flashed_messages(request),
    })


@app.post("/projet/{projet_id}/cas-usage/nouveau")
async def cas_usage_creer(request: Request, projet_id: int):
    form = await request.form()
    collectivite_id = int(form.get("collectivite_id", 0))

    # Récupérer les cas d'usage sélectionnés (IDs)
    selected_ids = form.getlist("cas_usage_ids")

    if selected_ids:
        # Pour chaque cas d'usage sélectionné, mettre à jour le champ projets
        for cas_id_str in selected_ids:
            cas_id = int(cas_id_str)
            try:
                # Le champ projets est une Ref simple, on le met à jour
                await grist.update_record("cas_d_usage", cas_id, {"projets": projet_id})
            except Exception as e:
                logger.error("Erreur liaison cas d'usage %s : %s", cas_id, e)
        flash(request, f"{len(selected_ids)} cas d'usage lié(s) au projet !")
    else:
        # Création d'un nouveau cas d'usage
        nom = form.get("nouveau_nom", "")
        theme = form.get("nouveau_theme", "")
        if nom:
            fields = {
                "nom": nom,
                "theme": theme,
                "projets": projet_id,
            }
            try:
                await grist.create_record("cas_d_usage", fields)
                flash(request, "Cas d'usage créé et lié au projet !")
            except Exception as e:
                logger.error("Erreur création cas d'usage : %s", e)
                flash(request, f"Erreur : {e}", "error")

    action = form.get("action", "retour")
    if action == "autre":
        return RedirectResponse(
            url=f"/projet/{projet_id}/cas-usage/nouveau?collectivite_id={collectivite_id}",
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
    return templates.TemplateResponse("partenaire.html", {
        "request": request,
        "projet_id": projet_id,
        "collectivite_id": collectivite_id,
        "partenaires_existants": grist.get_ref_records("partenaires"),
        "choices": {"role_s_": grist.get_choices("partenaires.role_s_")},
        "messages": get_flashed_messages(request),
    })


@app.post("/projet/{projet_id}/partenaire/nouveau")
async def partenaire_creer(request: Request, projet_id: int):
    form = await request.form()
    collectivite_id = int(form.get("collectivite_id", 0))

    partenaire_existant_id = form.get("partenaire_existant_id", "")

    if partenaire_existant_id:
        # Lier un partenaire existant à ce projet
        pid = int(partenaire_existant_id)
        try:
            await grist.add_to_reflist("partenaires", pid, "Projets", projet_id)
            flash(request, "Partenaire lié au projet !")
        except Exception as e:
            logger.error("Erreur liaison partenaire : %s", e)
            flash(request, f"Erreur : {e}", "error")
    else:
        # Créer un nouveau partenaire
        fields = {
            "nom": form.get("nom", ""),
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
            flash(request, f"Erreur : {e}", "error")

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
    return templates.TemplateResponse("programme.html", {
        "request": request,
        "projet_id": projet_id,
        "collectivite_id": collectivite_id,
        "programmes_existants": grist.get_ref_records("programmes"),
        "choices": {"echelle": grist.get_choices("programmes.echelle")},
        "messages": get_flashed_messages(request),
    })


@app.post("/projet/{projet_id}/programme/nouveau")
async def programme_creer(request: Request, projet_id: int):
    form = await request.form()
    collectivite_id = int(form.get("collectivite_id", 0))

    programme_existant_id = form.get("programme_existant_id", "")

    if programme_existant_id:
        pid = int(programme_existant_id)
        try:
            await grist.add_to_reflist("programmes", pid, "projet_s_", projet_id)
            flash(request, "Programme lié au projet !")
        except Exception as e:
            logger.error("Erreur liaison programme : %s", e)
            flash(request, f"Erreur : {e}", "error")
    else:
        fields = {
            "nom": form.get("nom", ""),
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
            flash(request, f"Erreur : {e}", "error")

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
    return templates.TemplateResponse("document.html", {
        "request": request,
        "projet_id": projet_id,
        "collectivite_id": collectivite_id,
        "messages": get_flashed_messages(request),
    })


@app.post("/projet/{projet_id}/document/nouveau")
async def document_creer(request: Request, projet_id: int):
    form = await request.form()
    collectivite_id = int(form.get("collectivite_id", 0))
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
        flash(request, f"Erreur : {e}", "error")

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
    return templates.TemplateResponse("contact.html", {
        "request": request,
        "projet_id": projet_id,
        "collectivite_id": collectivite_id,
        "collectivite_nom": grist.get_record_name("collectivites", collectivite_id) if collectivite_id else "",
        "messages": get_flashed_messages(request),
    })


@app.post("/projet/{projet_id}/contact/nouveau")
async def contact_creer(request: Request, projet_id: int):
    form = await request.form()
    collectivite_id = int(form.get("collectivite_id", 0))
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
        flash(request, f"Erreur : {e}", "error")

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
