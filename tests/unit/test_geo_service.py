"""Géo-résolution : cas réels v1 (acronymes, régions, validation, replis)."""

import pytest

from app.services.geo_service import DEP_PREF_COORDS, GeoResolver
from app.services.geocode_client import stored_coords

DEPARTEMENTS = [
    {"id": 1, "nom": "Gironde", "num_dep": "33", "region": "Nouvelle-Aquitaine"},
    {"id": 2, "nom": "Cher", "num_dep": "18", "region": "Centre-Val de Loire"},
    {"id": 3, "nom": "Charente-Maritime", "num_dep": "17", "region": "Nouvelle-Aquitaine"},
    {"id": 4, "nom": "Yvelines", "num_dep": "78", "region": "Île-de-France"},
    {"id": 5, "nom": "Hérault", "num_dep": "34", "region": "Occitanie"},
]


@pytest.fixture
def resolver():
    return GeoResolver(DEPARTEMENTS)  # type: ignore[arg-type]


async def _geocode_aucun(query, expected_dep=None, municipality=False):
    return None


# --- expected_dep : heuristiques v1 ---


def test_num_dep_explicite(resolver):
    assert resolver.expected_dep("Peu importe", num_dep="33") == "33"
    assert resolver.expected_dep("Peu importe", num_dep="2A") == "2A"


def test_acronyme_connu(resolver):
    assert resolver.expected_dep("SIPPEREC") == "75"
    assert resolver.expected_dep("SyDEV") == "85"


def test_numero_dans_le_nom(resolver):
    assert resolver.expected_dep("SDE 22") == "22"


def test_coeur_territorial_nom_de_departement(resolver):
    assert resolver.expected_dep("Gironde Numérique") == "33"
    assert resolver.expected_dep("CD Hérault") == "34"


def test_suffixe_en_departement(resolver):
    assert resolver.expected_dep("Saint-Quentin-en-Yvelines") == "78"


def test_synonyme_territorial(resolver):
    assert resolver.expected_dep("Berry Numérique") == "18"


def test_inconnu(resolver):
    assert resolver.expected_dep("Entité Mystère") is None


# --- city_query ---


def test_city_query_nettoie_les_prefixes(resolver):
    # « La » est un connecteur consommé après le token administratif « CA » —
    # comportement v1 exact (l'API adresse retrouve la commune malgré tout)
    assert resolver.city_query("CA La Rochelle Agglo") == "Rochelle"
    assert resolver.city_query("Communauté de communes du Pays de Lunel") == "Lunel"
    # un nom de département seul ne doit PAS être géocodé comme ville
    assert resolver.city_query("Gironde Numérique") is None


# --- resolve : replis sans réseau ---


async def test_resolve_repli_prefecture(resolver):
    coords = await resolver.resolve(
        {"nom": "SDE 22", "adresse": "", "num_dep": "", "dep": "", "reg": ""},
        _geocode_aucun,
    )
    assert coords == DEP_PREF_COORDS["22"]


async def test_resolve_entite_regionale(resolver):
    coords = await resolver.resolve(
        {"nom": "CR Île-de-France", "adresse": "", "num_dep": "", "dep": "",
         "reg": ""},
        _geocode_aucun,
    )
    assert coords == (48.859, 2.347)  # Paris


async def test_resolve_override_manuel(resolver):
    coords = await resolver.resolve(
        {"nom": "GIP ADINE", "adresse": "", "num_dep": "", "dep": "", "reg": ""},
        _geocode_aucun,
    )
    assert coords is None  # volontairement non placé


async def test_resolve_dep_par_nom_injecte(resolver):
    """Le champ dep (nom du département, résolu depuis Grist) sert de repli."""
    coords = await resolver.resolve(
        {"nom": "Syndicat Mystère", "adresse": "", "num_dep": "",
         "dep": "Charente-Maritime", "reg": ""},
        _geocode_aucun,
    )
    assert coords == DEP_PREF_COORDS["17"]


# --- stored_coords ---


def test_stored_coords_virgule_decimale():
    assert stored_coords({"latitude": "44,85", "longitude": "-0,58"}) == (44.85, -0.58)


def test_stored_coords_absentes_ou_invalides():
    assert stored_coords({"latitude": "", "longitude": ""}) is None
    assert stored_coords({"latitude": "abc", "longitude": "1"}) is None
    assert stored_coords({}) is None
