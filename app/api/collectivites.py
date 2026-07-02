"""Fiche collectivité : création (Éditeur et Administrateur) et édition.

Anti-IDOR centralisé (B2) : ``require_collectivite_ownership`` sur GET ET
POST — un Éditeur hors périmètre reçoit 404. La création est ouverte aux
Éditeurs (décision Victor, parité v1) : les administrateurs sont notifiés
et valident le rattachement via la console admin.
"""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

from app.core.flash import flash
from app.core.security import verify_csrf
from app.core.templating import render
from app.dependencies import (
    get_collectivite_repository,
    get_collectivite_service,
    get_notification_service,
    require_collectivite_ownership,
    require_editor,
)
from app.repositories.types import DROIT_ADMINISTRATEUR, UtilisateurRecord
from app.services.types import CollectiviteForm

router = APIRouter()


@router.get("/collectivite/nouveau")
def collectivite_nouveau(
    request: Request, utilisateur: UtilisateurRecord = Depends(require_editor)
):
    return render(
        request,
        "collectivite.html",
        {
            "mode": "creation",
            "record": None,
            "record_id": None,
            "projets_lies": [],
            "choices": get_collectivite_service().form_choices(),
        },
        user=utilisateur,
    )


@router.post("/collectivite/nouveau")
def collectivite_creer(
    request: Request,
    utilisateur: UtilisateurRecord = Depends(require_editor),
    csrf_token: str = Form(""),
    nom: str = Form(""),
    siren: str = Form(""),
    statut: str = Form(""),
    couverture: str = Form(""),
    departement: str = Form("0"),
    site_web: str = Form(""),
    adresse: str = Form(""),
):
    verify_csrf(request, csrf_token)
    formulaire = _valider_formulaire(
        request, nom, siren, statut, couverture, departement, site_web, adresse
    )
    if formulaire is None:
        return RedirectResponse(url="/collectivite/nouveau", status_code=303)
    new_id = get_collectivite_service().create(formulaire)

    if utilisateur.get("droits") == DROIT_ADMINISTRATEUR:
        flash(request, "Collectivité créée avec succès !")
        return RedirectResponse(url=f"/collectivite/{new_id}", status_code=303)

    # Création par un Éditeur : les admins valident le rattachement via la
    # console (l'Éditeur n'a pas accès à la fiche tant qu'il n'y est pas
    # rattaché — anti-IDOR inchangé).
    get_notification_service().notify_new_collectivite(
        nom=formulaire.nom,
        createur=f"{utilisateur.get('prenom', '')} {utilisateur.get('nom', '')}".strip(),
        email=str(utilisateur.get("email", "")),
    )
    flash(
        request,
        "Collectivité créée ! Un administrateur va valider son rattachement "
        "à votre compte.",
    )
    return RedirectResponse(url="/", status_code=303)


@router.get("/collectivite/{record_id}")
def collectivite_modifier(
    request: Request,
    record_id: int,
    utilisateur: UtilisateurRecord = Depends(require_editor),
):
    require_collectivite_ownership(utilisateur, record_id)
    record = get_collectivite_repository().get(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Page introuvable")
    service = get_collectivite_service()
    return render(
        request,
        "collectivite.html",
        {
            "mode": "edition",
            "record": record,
            "record_id": record_id,
            "projets_lies": service.projets_lies(record),
            "choices": service.form_choices(),
        },
        user=utilisateur,
    )


@router.post("/collectivite/{record_id}")
def collectivite_update(
    request: Request,
    record_id: int,
    utilisateur: UtilisateurRecord = Depends(require_editor),
    csrf_token: str = Form(""),
    nom: str = Form(""),
    siren: str = Form(""),
    statut: str = Form(""),
    couverture: str = Form(""),
    departement: str = Form("0"),
    site_web: str = Form(""),
    adresse: str = Form(""),
):
    require_collectivite_ownership(utilisateur, record_id)
    verify_csrf(request, csrf_token)
    if get_collectivite_repository().get(record_id) is None:
        raise HTTPException(status_code=404, detail="Page introuvable")
    formulaire = _valider_formulaire(
        request, nom, siren, statut, couverture, departement, site_web, adresse
    )
    if formulaire is None:
        return RedirectResponse(url=f"/collectivite/{record_id}", status_code=303)
    get_collectivite_service().update(record_id, formulaire)
    flash(request, "Collectivité mise à jour avec succès !")
    return RedirectResponse(url=f"/collectivite/{record_id}", status_code=303)


def _valider_formulaire(
    request: Request,
    nom: str,
    siren: str,
    statut: str,
    couverture: str,
    departement: str,
    site_web: str,
    adresse: str,
) -> CollectiviteForm | None:
    """Validation Pydantic + contrôle des choix. None = flash posé, à rediriger."""
    try:
        formulaire = CollectiviteForm(
            nom=nom,
            siren=siren,  # pyright: ignore[reportArgumentType] — coercition tolérante
            statut=statut,
            couverture=couverture,
            departement=departement,  # pyright: ignore[reportArgumentType]
            site_web=site_web,
            adresse=adresse,
        )
    except ValidationError:
        flash(
            request,
            "Formulaire invalide — vérifiez le nom, le SIREN et le site web "
            "(adresse http(s) attendue).",
            "error",
        )
        return None
    service = get_collectivite_service()
    if not service.is_valid_choice("statut", formulaire.statut) or not (
        service.is_valid_choice("couverture", formulaire.couverture)
    ):
        flash(request, "Valeur de statut ou de couverture non autorisée.", "error")
        return None
    return formulaire
