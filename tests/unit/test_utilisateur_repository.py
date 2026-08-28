"""Repository utilisateurs : recherche par email, normalisation des droits."""

import pytest

from app.repositories.types import TABLE_UTILISATEURS
from app.repositories.utilisateur_repository import GristUtilisateurRepository


@pytest.fixture
def repo(fake_grist, cache):
    fake_grist.records[TABLE_UTILISATEURS] = [
        {"id": 1, "email": "Victor@Exemple.fr", "droits": "Administrateur",
         "nom": "W", "prenom": "Victor", "organisation": "", "collectivite": 0},
        {"id": 2, "email": "editor@exemple.fr", "droits": "Editor",
         "nom": "E", "prenom": "Ed", "organisation": "", "collectivite": 5},
    ]
    return GristUtilisateurRepository(fake_grist, cache)


def test_get_by_email_insensible_a_la_casse(repo):
    utilisateur = repo.get_by_email("  victor@exemple.FR ")
    assert utilisateur is not None
    assert utilisateur["id"] == 1


def test_get_by_email_inconnu(repo):
    assert repo.get_by_email("inconnu@exemple.fr") is None
    assert repo.get_by_email("") is None


def test_droits_anglais_normalises_a_la_lecture(repo):
    utilisateur = repo.get_by_email("editor@exemple.fr")
    assert utilisateur["droits"] == "Editeur"


def test_create_pending_force_en_attente(repo, fake_grist):
    new_id = repo.create_pending({
        "email": "nouveau@exemple.fr", "droits": "Administrateur",  # tentative ignorée
        "nom": "N", "prenom": "P",
    })
    stocke = next(r for r in fake_grist.records[TABLE_UTILISATEURS] if r["id"] == new_id)
    assert stocke["droits"] == "En attente"
