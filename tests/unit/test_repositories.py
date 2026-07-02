"""Repository de base : helpers Grist, cache, batching PATCH, erreurs sobres."""

import pytest

from app.repositories.base import (
    BaseGristRepository,
    GristError,
    extract_values,
    first_value,
    ref_ids,
    to_reflist,
)
from app.repositories.cache import TableCache


class RepoTest(BaseGristRepository[dict]):
    table_id = "BDD_Test"


@pytest.fixture
def repo(fake_grist, cache):
    fake_grist.records["BDD_Test"] = [
        {"id": 1, "nom": "Alpha", "refs": ["L", 2, 3]},
        {"id": 2, "nom": "Beta"},
    ]
    return RepoTest(fake_grist, cache)


# --- Helpers (pièges Grist n°3 et n°6) ---


def test_ref_ids_reflist():
    assert ref_ids(["L", 4, 5]) == [4, 5]


def test_ref_ids_ref_simple_et_vide():
    assert ref_ids(7) == [7]
    assert ref_ids(0) == []
    assert ref_ids(None) == []
    assert ref_ids(True) == []  # un booléen n'est pas un id


def test_to_reflist():
    assert to_reflist([1, 2]) == ["L", 1, 2]
    assert to_reflist([]) == ["L"]


def test_extract_values_tolerant():
    assert extract_values(["L", "a", " b "]) == ["a", "b"]
    assert extract_values(["x", "y"]) == ["x", "y"]  # liste simple (formule)
    assert extract_values(" seul ") == ["seul"]
    assert extract_values(None) == []
    assert extract_values("") == []


def test_first_value():
    assert first_value({"statut": ["L", "Commune", "EPCI"]}, "statut") == "Commune"
    assert first_value({}, "statut") == ""


# --- Lectures et cache ---


def test_list_all_met_en_cache(repo, fake_grist):
    repo.list_all()
    repo.list_all()
    appels = [c for c in fake_grist.calls if c[0] == "list_records"]
    assert len(appels) == 1


def test_get_par_id(repo):
    assert repo.get(2)["nom"] == "Beta"
    assert repo.get(99) is None


# --- Écritures : invalidation du cache DANS le repository ---


def test_create_invalide_le_cache(repo, fake_grist):
    repo.list_all()
    new_id = repo.create({"nom": "Gamma"})
    assert new_id > 0
    noms = [r["nom"] for r in repo.list_all()]
    assert "Gamma" in noms  # relecture fraîche après écriture


def test_update_invalide_le_cache(repo):
    repo.list_all()
    repo.update(1, {"nom": "Alpha2"})
    assert repo.get(1)["nom"] == "Alpha2"


def test_add_to_reflist_sans_ecraser(repo, fake_grist):
    repo.add_to_reflist(1, "refs", 9)
    assert repo.get(1)["refs"] == ["L", 2, 3, 9]


def test_add_to_reflist_deja_present_sans_ecriture(repo, fake_grist):
    repo.add_to_reflist(1, "refs", 2)
    assert not [c for c in fake_grist.calls if c[0] == "update_records"]


# --- Batching PATCH homogène + repli unitaire (piège n°2) ---


def test_update_many_groupe_par_champs_homogenes(repo, fake_grist):
    repo.update_many([
        {"id": 1, "nom": "A"},
        {"id": 2, "nom": "B"},
        {"id": 1, "refs": ["L", 8]},
    ])
    lots = [c[2] for c in fake_grist.calls if c[0] == "update_records"]
    assert len(lots) == 2  # {nom} x2 et {refs} x1, jamais mélangés
    tailles = sorted(len(lot) for lot in lots)
    assert tailles == [1, 2]


def test_update_many_repli_unitaire_sur_400(repo, fake_grist):
    fake_grist.echec_batch = True
    repo.update_many([{"id": 1, "nom": "A"}, {"id": 2, "nom": "B"}])
    assert repo.get(1)["nom"] == "A"
    assert repo.get(2)["nom"] == "B"


# --- Erreurs sobres (jamais de doc ID ni d'URL) ---


def test_erreur_http_reformulee(repo, fake_grist):
    fake_grist.statuts_forces["list_records"] = 403
    with pytest.raises(GristError) as excinfo:
        repo.list_all()
    message = str(excinfo.value)
    assert "doc-factice" not in message
    assert "http" not in message.lower()


def test_erreur_reseau_reformulee(cache):
    import requests

    class GristInjoignable:
        def list_records(self, *a, **k):
            raise requests.ConnectionError("https://grist.exemple.test/api/docs/doc-factice")

        def add_records(self, *a, **k):
            raise requests.ConnectionError("injoignable")

        def update_records(self, *a, **k):
            raise requests.ConnectionError("injoignable")

        def list_cols(self, *a, **k):
            raise requests.ConnectionError("injoignable")

    repo = RepoTest(GristInjoignable(), cache)
    with pytest.raises(GristError) as excinfo:
        repo.list_all()
    assert "doc-factice" not in str(excinfo.value)


def test_sous_classe_sans_table_id_refusee(fake_grist):
    class SansTable(BaseGristRepository[dict]):
        pass

    with pytest.raises(ValueError):
        SansTable(fake_grist, TableCache())
