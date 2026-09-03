"""Sous-formulaires de projet : cas d'usage, partenaire, programme, document.

Toutes les routes (GET comme POST) vérifient que le PROJET appartient au
périmètre de l'utilisateur (anti-IDOR B2, 404 uniforme). Chaque POST gère
le bouton « …et continuer » (action=autre) — parité v1.
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

from app.core.flash import flash
from app.core.security import verify_csrf
from app.core.templating import render
from app.dependencies import (
    get_projet_repository,
    get_projet_service,
    require_editor,
    require_projet_ownership,
)
from app.repositories.types import ProjetRecord, UtilisateurRecord
from app.services.types import (
    CasUsageCreationForm,
    CasUsageSelectionForm,
    DocumentForm,
    PartenaireForm,
    ProgrammeForm,
)

router = APIRouter()


def _projet_du_perimetre(
    utilisateur: UtilisateurRecord, projet_id: int
) -> ProjetRecord:
    record = get_projet_repository().get(projet_id)
    require_projet_ownership(utilisateur, record)
    assert record is not None  # garanti par require_projet_ownership
    return record


def _retour_projet(projet_id: int, collectivite_id: int) -> RedirectResponse:
    return RedirectResponse(
        url=f"/projet/{projet_id}?collectivite_id={collectivite_id}", status_code=303
    )


def _continuer(
    route: str, projet_id: int, collectivite_id: int, extra: str = ""
) -> RedirectResponse:
    url = f"/projet/{projet_id}/{route}/nouveau?collectivite_id={collectivite_id}{extra}"
    return RedirectResponse(url=url, status_code=303)


# ============================================================
# Cas d'usage — sélection par thème ou création
# ============================================================


@router.get("/projet/{projet_id}/cas-usage/nouveau")
def cas_usage_nouveau(
    request: Request,
    projet_id: int,
    collectivite_id: int = 0,
    theme: str = "",
    utilisateur: UtilisateurRecord = Depends(require_editor),
):
    _projet_du_perimetre(utilisateur, projet_id)
    donnees = get_projet_service().cas_usage_page_data(projet_id)
    return render(
        request,
        "cas_usage.html",
        {
            "projet_id": projet_id,
            "collectivite_id": collectivite_id,
            "selected_theme": theme,
            **donnees,
        },
        user=utilisateur,
    )


@router.post("/projet/{projet_id}/cas-usage/nouveau")
def cas_usage_creer(
    request: Request,
    projet_id: int,
    utilisateur: UtilisateurRecord = Depends(require_editor),
    csrf_token: str = Form(""),
    collectivite_id: int = Form(0),
    action: str = Form("retour"),
    mode: str = Form(""),
    nouveau_nom: str | None = Form(None),
    nouveau_theme: str = Form(""),
    cas_usage_ids: list[int] = Form([]),
):
    _projet_du_perimetre(utilisateur, projet_id)
    verify_csrf(request, csrf_token)
    service = get_projet_service()

    # Compat v1 : si le mode n'est pas transmis, déduit des champs présents
    if not mode:
        mode = "create" if nouveau_nom is not None else "select"

    if mode == "create":
        try:
            formulaire = CasUsageCreationForm(
                nom=nouveau_nom or "", theme=nouveau_theme
            )
        except ValidationError:
            flash(request, "Le nom du cas d'usage est obligatoire.", "error")
            return _continuer(
                "cas-usage", projet_id, collectivite_id, f"&theme={nouveau_theme}"
            )
        service.create_cas_usage(projet_id, formulaire)
        flash(request, "Cas d'usage créé et lié au projet !")
    else:
        try:
            selection = CasUsageSelectionForm(cas_usage_ids=cas_usage_ids)
        except ValidationError:
            flash(
                request,
                "Sélectionnez au moins un cas d'usage à lier (ou créez-en un "
                "ci-dessous).",
                "error",
            )
            return _continuer(
                "cas-usage", projet_id, collectivite_id, f"&theme={nouveau_theme}"
            )
        nb_lies = service.link_cas_usages(projet_id, selection.cas_usage_ids)
        flash(request, f"{nb_lies} cas d'usage lié(s) au projet !")

    if action == "autre":
        return _continuer(
            "cas-usage", projet_id, collectivite_id, f"&theme={nouveau_theme}"
        )
    return _retour_projet(projet_id, collectivite_id)


# ============================================================
# Partenaires — lier un existant ou créer
# ============================================================


@router.get("/projet/{projet_id}/partenaire/nouveau")
def partenaire_nouveau(
    request: Request,
    projet_id: int,
    collectivite_id: int = 0,
    utilisateur: UtilisateurRecord = Depends(require_editor),
):
    _projet_du_perimetre(utilisateur, projet_id)
    donnees = get_projet_service().partenaire_choices()
    return render(
        request,
        "partenaire.html",
        {
            "projet_id": projet_id,
            "collectivite_id": collectivite_id,
            "partenaires_existants": donnees["partenaires_existants"],
            "choices": {"roles": donnees["roles"]},
        },
        user=utilisateur,
    )


@router.post("/projet/{projet_id}/partenaire/nouveau")
def partenaire_creer(
    request: Request,
    projet_id: int,
    utilisateur: UtilisateurRecord = Depends(require_editor),
    csrf_token: str = Form(""),
    collectivite_id: int = Form(0),
    action: str = Form("retour"),
    partenaire_existant_id: int = Form(0),
    nom: str = Form(""),
    roles: str = Form(""),
    url: str = Form(""),
):
    _projet_du_perimetre(utilisateur, projet_id)
    verify_csrf(request, csrf_token)
    service = get_projet_service()

    if partenaire_existant_id:
        if service.link_partenaire(projet_id, partenaire_existant_id):
            flash(request, "Partenaire lié au projet !")
        else:
            flash(request, "Partenaire invalide.", "error")
    else:
        try:
            formulaire = PartenaireForm(nom=nom, roles=roles, url=url)
        except ValidationError:
            flash(request, "Le nom du partenaire est obligatoire (URL http(s) "
                           "si renseignée).", "error")
            return _continuer("partenaire", projet_id, collectivite_id)
        service.create_partenaire(projet_id, formulaire)
        flash(request, "Partenaire créé avec succès !")

    if action == "autre":
        return _continuer("partenaire", projet_id, collectivite_id)
    return _retour_projet(projet_id, collectivite_id)


# ============================================================
# Programmes — lier un existant ou créer
# ============================================================


@router.get("/projet/{projet_id}/programme/nouveau")
def programme_nouveau(
    request: Request,
    projet_id: int,
    collectivite_id: int = 0,
    utilisateur: UtilisateurRecord = Depends(require_editor),
):
    _projet_du_perimetre(utilisateur, projet_id)
    donnees = get_projet_service().programme_choices()
    return render(
        request,
        "programme.html",
        {
            "projet_id": projet_id,
            "collectivite_id": collectivite_id,
            "programmes_existants": donnees["programmes_existants"],
            "choices": {"echelle": donnees["echelle"]},
        },
        user=utilisateur,
    )


@router.post("/projet/{projet_id}/programme/nouveau")
def programme_creer(
    request: Request,
    projet_id: int,
    utilisateur: UtilisateurRecord = Depends(require_editor),
    csrf_token: str = Form(""),
    collectivite_id: int = Form(0),
    action: str = Form("retour"),
    programme_existant_id: int = Form(0),
    nom: str = Form(""),
    info_web: str = Form(""),
    echelle: str = Form(""),
):
    _projet_du_perimetre(utilisateur, projet_id)
    verify_csrf(request, csrf_token)
    service = get_projet_service()

    if programme_existant_id:
        if service.link_programme(projet_id, programme_existant_id):
            flash(request, "Programme lié au projet !")
        else:
            flash(request, "Programme invalide.", "error")
    else:
        try:
            formulaire = ProgrammeForm(nom=nom, info_web=info_web, echelle=echelle)
        except ValidationError:
            flash(request, "Le nom du programme est obligatoire (lien http(s) "
                           "si renseigné).", "error")
            return _continuer("programme", projet_id, collectivite_id)
        service.create_programme(projet_id, formulaire)
        flash(request, "Programme créé avec succès !")

    if action == "autre":
        return _continuer("programme", projet_id, collectivite_id)
    return _retour_projet(projet_id, collectivite_id)


# ============================================================
# Documents
# ============================================================


@router.get("/projet/{projet_id}/document/nouveau")
def document_nouveau(
    request: Request,
    projet_id: int,
    collectivite_id: int = 0,
    utilisateur: UtilisateurRecord = Depends(require_editor),
):
    _projet_du_perimetre(utilisateur, projet_id)
    return render(
        request,
        "document.html",
        {"projet_id": projet_id, "collectivite_id": collectivite_id},
        user=utilisateur,
    )


@router.post("/projet/{projet_id}/document/nouveau")
def document_creer(
    request: Request,
    projet_id: int,
    utilisateur: UtilisateurRecord = Depends(require_editor),
    csrf_token: str = Form(""),
    collectivite_id: int = Form(0),
    action: str = Form("retour"),
    titre: str = Form(""),
    lien: str = Form(""),
    type: str = Form(""),
):
    _projet_du_perimetre(utilisateur, projet_id)
    verify_csrf(request, csrf_token)
    try:
        formulaire = DocumentForm(titre=titre, lien=lien, type=type)
    except ValidationError:
        flash(request, "Le titre du document est obligatoire (lien http(s) "
                       "si renseigné).", "error")
        return _continuer("document", projet_id, collectivite_id)
    get_projet_service().create_document(projet_id, formulaire)
    flash(request, "Document créé avec succès !")

    if action == "autre":
        return _continuer("document", projet_id, collectivite_id)
    return _retour_projet(projet_id, collectivite_id)
