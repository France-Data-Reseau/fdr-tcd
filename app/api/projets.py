"""Fiche projet : création et édition.

Anti-IDOR (B2) : ``require_projet_ownership`` sur GET ET POST (404 uniforme) ;
à la création, la collectivité cible doit appartenir au périmètre de
l'utilisateur (``require_collectivite_ownership``).
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

from app.core.flash import flash
from app.core.security import verify_csrf
from app.core.templating import render
from app.dependencies import (
    get_collectivite_repository,
    get_projet_repository,
    get_projet_service,
    require_collectivite_ownership,
    require_editor,
    require_projet_ownership,
)
from app.repositories.base import ref_ids
from app.repositories.types import UtilisateurRecord
from app.services.types import ProjetForm

router = APIRouter()


@router.get("/projet/nouveau")
def projet_nouveau(
    request: Request,
    collectivite_id: int = 0,
    utilisateur: UtilisateurRecord = Depends(require_editor),
):
    if collectivite_id:
        require_collectivite_ownership(utilisateur, collectivite_id)
    coll_nom = (
        get_collectivite_repository().get_nom(collectivite_id)
        if collectivite_id
        else ""
    )
    return render(
        request,
        "projet_form.html",
        {
            "mode": "creation",
            "record": None,
            "record_id": None,
            "collectivite_id": collectivite_id,
            "collectivite_nom": coll_nom,
            "choices": get_projet_service().form_choices(),
            "sous_formulaires": {},
        },
        user=utilisateur,
    )


@router.post("/projet/nouveau")
def projet_creer(
    request: Request,
    utilisateur: UtilisateurRecord = Depends(require_editor),
    csrf_token: str = Form(""),
    collectivite_id: int = Form(0),
    action: str = Form("save"),
    nom: str = Form(""),
    description: str = Form(""),
    avancement: str = Form(""),
    echelle: str = Form(""),
    mutualisation: str = Form(""),
    soutien: str = Form(""),
    dev_interne: str = Form(""),
    connectivites: list[int] = Form([]),
    solutions: list[int] = Form([]),
    contrats: list[int] = Form([]),
    departements: list[int] = Form([]),
):
    verify_csrf(request, csrf_token)
    if collectivite_id:
        require_collectivite_ownership(utilisateur, collectivite_id)
    try:
        formulaire = ProjetForm(
            nom=nom,
            description=description,
            avancement=avancement,
            echelle=echelle,
            mutualisation=mutualisation,
            soutien=soutien,
            dev_interne=bool(dev_interne),
            connectivites=connectivites,
            solutions=solutions,
            contrats=contrats,
            departements=departements,
        )
    except ValidationError:
        flash(request, "Formulaire invalide — le nom du projet est obligatoire.",
              "error")
        return RedirectResponse(
            url=f"/projet/nouveau?collectivite_id={collectivite_id}", status_code=303
        )
    new_id = get_projet_service().create(formulaire, collectivite_id)

    if action == "autre":
        flash(request, "Projet créé avec succès ! Vous pouvez en ajouter un autre.")
        return RedirectResponse(
            url=f"/projet/nouveau?collectivite_id={collectivite_id}", status_code=303
        )
    flash(request, "Projet créé avec succès !")
    return RedirectResponse(
        url=f"/projet/{new_id}?collectivite_id={collectivite_id}", status_code=303
    )


@router.get("/projet/{record_id}")
def projet_modifier(
    request: Request,
    record_id: int,
    collectivite_id: int = 0,
    utilisateur: UtilisateurRecord = Depends(require_editor),
):
    record = get_projet_repository().get(record_id)
    require_projet_ownership(utilisateur, record)
    assert record is not None  # garanti par require_projet_ownership

    if not collectivite_id:
        porteuses = ref_ids(record.get("collectivites_porteuses"))
        collectivite_id = porteuses[0] if porteuses else 0

    service = get_projet_service()
    return render(
        request,
        "projet_form.html",
        {
            "mode": "edition",
            "record": record,
            "record_id": record_id,
            "collectivite_id": collectivite_id,
            "collectivite_nom": get_collectivite_repository().get_nom(collectivite_id)
            if collectivite_id
            else "",
            "choices": service.form_choices(),
            "sous_formulaires": service.sous_formulaires(record),
        },
        user=utilisateur,
    )


@router.post("/projet/{record_id}")
def projet_update(
    request: Request,
    record_id: int,
    utilisateur: UtilisateurRecord = Depends(require_editor),
    csrf_token: str = Form(""),
    collectivite_id: int = Form(0),
    nom: str = Form(""),
    description: str = Form(""),
    avancement: str = Form(""),
    echelle: str = Form(""),
    mutualisation: str = Form(""),
    soutien: str = Form(""),
    dev_interne: str = Form(""),
    connectivites: list[int] = Form([]),
    solutions: list[int] = Form([]),
    contrats: list[int] = Form([]),
    departements: list[int] = Form([]),
):
    record = get_projet_repository().get(record_id)
    require_projet_ownership(utilisateur, record)
    verify_csrf(request, csrf_token)
    try:
        formulaire = ProjetForm(
            nom=nom,
            description=description,
            avancement=avancement,
            echelle=echelle,
            mutualisation=mutualisation,
            soutien=soutien,
            dev_interne=bool(dev_interne),
            connectivites=connectivites,
            solutions=solutions,
            contrats=contrats,
            departements=departements,
        )
    except ValidationError:
        flash(request, "Formulaire invalide — le nom du projet est obligatoire.",
              "error")
    else:
        get_projet_service().update(record_id, formulaire)
        flash(request, "Projet mis à jour avec succès !")
    return RedirectResponse(
        url=f"/projet/{record_id}?collectivite_id={collectivite_id}", status_code=303
    )
