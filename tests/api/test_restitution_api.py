"""Restitution : page, API JSON (structure v1), 401, absence de données sensibles."""

from tests.conftest import connecter


def test_page_restitution_accessible_aux_visiteurs(client):
    connecter(client, "visiteur@exemple.fr")
    page = client.get("/cartographie")
    assert page.status_code == 200
    assert "Ma Collectivité" in page.text
    assert "/static/vendor/leaflet/leaflet.js" in page.text  # auto-hébergé
    assert "unpkg.com" not in page.text  # plus de CDN


def test_page_admin_a_le_selecteur_ma_collectivite(client):
    connecter(client, "admin@exemple.fr")
    page = client.get("/cartographie")
    assert "select-ma-coll" in page.text
    assert "Ville Exemple" in page.text


def test_api_sans_session_401(client):
    reponse = client.get("/api/cartographie/donnees")
    assert reponse.status_code == 401
    assert reponse.json() == {"error": "Non autorisé"}


def test_api_en_attente_401(client):
    connecter(client, "attente@exemple.fr")
    assert client.get("/api/cartographie/donnees").status_code == 401


def test_api_structure_conforme_v1(client):
    connecter(client, "visiteur@exemple.fr")
    reponse = client.get("/api/cartographie/donnees")
    assert reponse.status_code == 200
    assert reponse.headers["cache-control"] == "private"
    data = reponse.json()

    assert set(data.keys()) == {"collectivites", "stats", "filtres"}
    assert set(data["stats"].keys()) == {
        "nb_collectivites", "nb_projets", "par_connectivite",
        "par_avancement", "par_domaine", "nb_cas_usages",
    }
    assert set(data["filtres"].keys()) == {
        "couvertures", "statuts", "domaines", "connectivites",
        "avancements", "cas_usages",
    }

    ville = next(c for c in data["collectivites"] if c["id"] == 5)
    assert set(ville.keys()) == {
        "id", "nom", "siren", "statut", "couverture", "dep", "num_dep", "reg",
        "site_web", "adresse", "url_logo", "lat", "lng", "nb_projets", "projets",
    }
    assert ville["statut"] == "EPCI"  # première valeur de la ChoiceList
    assert ville["dep"] == "Gironde"  # nom résolu depuis la référence
    assert ville["lat"] == 44.85  # coordonnées STOCKÉES (pas de géocodage)
    assert ville["nb_projets"] == 1

    projet = ville["projets"][0]
    assert set(projet.keys()) == {
        "id", "nom", "domaine", "avancement", "connectivite", "echelle",
        "description", "cas_usages", "partenaires", "programmes", "documents",
    }
    assert projet["connectivite"] == ["LoRaWAN"]
    assert projet["domaine"] == ["Gestion de l'éclairage public"]
    assert projet["cas_usages"][0]["nom"] == "Éclairage intelligent"
    assert projet["partenaires"][0]["nom"] == "Opérateur Réseau"


def test_api_stats_et_filtres(client):
    connecter(client, "visiteur@exemple.fr")
    data = client.get("/api/cartographie/donnees").json()
    assert data["stats"]["nb_collectivites"] == 2
    assert data["stats"]["nb_projets"] == 2  # dédupliqués
    assert data["stats"]["par_connectivite"] == {"LoRaWAN": 1}
    assert "Gestion de l'éclairage public" in data["filtres"]["domaines"]
    assert data["filtres"]["statuts"] == ["EPCI", "Syndicat"]
