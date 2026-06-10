"""
Client API Grist — encapsule tous les appels à l'API REST de Grist.
Gère la connexion, le cache des tables/colonnes, et les opérations CRUD.
"""

import os
import asyncio
import logging
import time
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("grist_client")

# --- Configuration ---
GRIST_API_KEY = os.getenv("GRIST_API_KEY", "")
GRIST_BASE_URL = "https://grist.francedatareseau.fr"
GRIST_DOC_ID = os.getenv("GRIST_DOC_ID", "")
API_BASE = f"{GRIST_BASE_URL}/api/docs/{GRIST_DOC_ID}"

HEADERS = {
    "Authorization": f"Bearer {GRIST_API_KEY}",
    "Content-Type": "application/json",
}

# --- Noms réels des tables dans Grist (récupérés au démarrage) ---
TABLE_IDS: dict[str, str] = {}

# --- Cache des options de choix ---
CHOICES_CACHE: dict[str, list[str]] = {}

# --- Cache des records pour les tables de référence ---
REF_CACHE: dict[str, list[dict]] = {}

# --- Cache cas d'usage groupés par thème ---
CAS_USAGE_BY_THEME: dict[str, list[dict]] = {}


# ============================================================
# Client HTTP async
# ============================================================

def _client() -> httpx.AsyncClient:
    """Crée un client httpx async avec timeout."""
    return httpx.AsyncClient(headers=HEADERS, timeout=30.0)


async def _get(path: str, params: dict | None = None) -> dict:
    """GET générique sur l'API Grist."""
    url = f"{API_BASE}{path}"
    logger.info("GET %s", url)
    async with _client() as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


async def _post(path: str, data: dict) -> dict:
    """POST générique sur l'API Grist."""
    url = f"{API_BASE}{path}"
    logger.info("POST %s", url)
    async with _client() as client:
        resp = await client.post(url, json=data)
        resp.raise_for_status()
        return resp.json()


async def _patch(path: str, data: dict) -> dict:
    """PATCH générique sur l'API Grist."""
    url = f"{API_BASE}{path}"
    logger.info("PATCH %s", url)
    async with _client() as client:
        resp = await client.patch(url, json=data)
        resp.raise_for_status()
        return resp.json()


# ============================================================
# Initialisation
# ============================================================

async def init_tables():
    """Récupère la liste des tables Grist et établit le mapping."""
    # Mapping clé interne → nom réel de la table dans Grist
    mapping = {
        "collectivites": "BDD_Collectivites",
        "projets": "BDD_Projets",
        "contacts": "BDD_Contacts",
        "cas_d_usage": "BDD_CasUsages",
        "partenaires": "BDD_Partenaires",
        "programmes": "BDD_Programmes",
        "documents": "BDD_Documents",
        "utilisateurs": "BDD_Utilisateurs",
        "connectivites": "BDD_Connectivites",
    }

    # Le mapping est appliqué immédiatement, la vérification est optionnelle
    TABLE_IDS.update(mapping)

    # Vérification : on récupère les tables existantes pour valider
    try:
        data = await _get("/tables")
        existing = {t["id"] for t in data.get("tables", [])}
        for key, table_id in mapping.items():
            if table_id not in existing:
                logger.warning("Table '%s' (clé '%s') introuvable dans Grist", table_id, key)
    except Exception as e:
        logger.warning("Impossible de valider les tables Grist : %s", e)

    logger.info("Tables configurées : %s", TABLE_IDS)


def _extract_values(v) -> list[str]:
    """Extrait les valeurs d'un champ Grist (string, ChoiceList ['L', ...], ou None)."""
    if not v:
        return []
    if isinstance(v, list) and len(v) > 1 and v[0] == "L":
        return [str(item).strip() for item in v[1:] if item and str(item).strip()]
    if isinstance(v, str) and v.strip():
        return [v.strip()]
    return []


def ref_ids(v) -> list[int]:
    """IDs d'un champ Ref/RefList Grist.
    Accepte ['L', id1, id2, ...] (RefList), un int simple (Ref), ou None.
    Rétro-compatible : marche que le champ soit une référence simple ou multiple.
    """
    if isinstance(v, list) and v and v[0] == "L":
        return [x for x in v[1:] if isinstance(x, int) and x]
    if isinstance(v, int) and v:
        return [v]
    return []


def to_reflist(ids: list[int]) -> list:
    """Format d'écriture d'une RefList Grist : ['L', id1, id2, ...]."""
    return ["L"] + [int(i) for i in ids]


def get_field_value(record: dict, field: str) -> str:
    """Retourne la première valeur d'un champ (string ou ChoiceList) pour comparaison template."""
    v = record.get("fields", {}).get(field)
    values = _extract_values(v)
    return values[0] if values else ""


async def init_choices():
    """
    Récupère les valeurs uniques pour les champs de type choix
    en parcourant les records existants.
    """
    # --- Collectivités ---
    coll_records = await get_all_records("collectivites")
    for field in ["statut", "couverture"]:
        values = set()
        for rec in coll_records:
            values.update(_extract_values(rec["fields"].get(field)))
        CHOICES_CACHE[f"collectivites.{field}"] = sorted(values)

    # --- Projets ---
    proj_records = await get_all_records("projets")
    for field in ["avancement", "echelle", "region", "mutualisation", "soutien", "contrat"]:
        values = set()
        for rec in proj_records:
            values.update(_extract_values(rec["fields"].get(field)))
        CHOICES_CACHE[f"projets.{field}"] = sorted(values)

    # --- Cas d'usage : thèmes et mapping thème → cas d'usage ---
    cas_records = await get_all_records("cas_d_usage")
    themes = set()
    CAS_USAGE_BY_THEME.clear()
    for rec in cas_records:
        theme_vals = _extract_values(rec["fields"].get("theme"))
        nom = rec["fields"].get("nom", "")
        for theme in theme_vals:
            themes.add(theme)
            if nom:
                CAS_USAGE_BY_THEME.setdefault(theme, []).append({
                    "id": rec["id"],
                    "nom": nom.strip() if isinstance(nom, str) else str(nom),
                })
    CHOICES_CACHE["cas_d_usage.theme"] = sorted(themes)

    # Extraire les domaines depuis les thèmes des cas d'usage
    CHOICES_CACHE["projets.domaine_s_"] = sorted(themes)

    # --- Partenaires : rôles ---
    part_records = await get_all_records("partenaires")
    roles = set()
    for rec in part_records:
        roles.update(_extract_values(rec["fields"].get("role_s_")))
    CHOICES_CACHE["partenaires.role_s_"] = sorted(roles)

    # --- Programmes : échelle ---
    prog_records = await get_all_records("programmes")
    echelles = set()
    for rec in prog_records:
        echelles.update(_extract_values(rec["fields"].get("echelle")))
    CHOICES_CACHE["programmes.echelle"] = sorted(echelles)

    logger.info("Choix mis en cache : %s", {k: len(v) for k, v in CHOICES_CACHE.items()})
    logger.info("Cas d'usage par thème : %s thèmes", len(CAS_USAGE_BY_THEME))


async def init_ref_cache():
    """Met en cache les records des tables de référence."""
    for table in ["collectivites", "contacts", "projets", "partenaires", "programmes"]:
        records = await get_all_records(table)
        REF_CACHE[table] = records
    logger.info("Cache de références chargé")


async def startup():
    """Initialisation complète au démarrage de l'app."""
    await init_tables()
    await init_choices()
    await init_ref_cache()


# ============================================================
# Opérations CRUD
# ============================================================

async def get_all_records(table_key: str) -> list[dict]:
    """Récupère tous les records d'une table."""
    table_id = TABLE_IDS.get(table_key)
    if not table_id:
        raise ValueError(f"Table inconnue : {table_key}")
    data = await _get(f"/tables/{table_id}/records", params={"limit": 10000})
    return data.get("records", [])


async def get_record(table_key: str, record_id: int) -> dict | None:
    """Récupère un record par son ID."""
    records = await get_all_records(table_key)
    for rec in records:
        if rec["id"] == record_id:
            return rec
    return None


async def create_record(table_key: str, fields: dict) -> dict:
    """Crée un nouveau record dans une table."""
    table_id = TABLE_IDS.get(table_key)
    if not table_id:
        raise ValueError(f"Table inconnue : {table_key}")
    data = {"records": [{"fields": fields}]}
    return await _post(f"/tables/{table_id}/records", data)


async def update_record(table_key: str, record_id: int, fields: dict) -> dict:
    """Met à jour un record existant."""
    table_id = TABLE_IDS.get(table_key)
    if not table_id:
        raise ValueError(f"Table inconnue : {table_key}")
    data = {"records": [{"id": record_id, "fields": fields}]}
    return await _patch(f"/tables/{table_id}/records", data)


async def add_to_reflist(table_key: str, record_id: int, field: str, new_id: int) -> dict:
    """Ajoute un ID à un champ ReferenceList sans écraser les valeurs existantes."""
    logger.info("add_to_reflist: table=%s, record_id=%s, field=%s, new_id=%s", table_key, record_id, field, new_id)
    record = await get_record(table_key, record_id)
    if not record:
        raise ValueError(f"Record {record_id} introuvable dans {table_key}")

    current = record["fields"].get(field)
    logger.info("add_to_reflist: current value of %s = %s", field, current)
    if current and isinstance(current, list) and len(current) > 1:
        ids = current[1:]
    else:
        ids = []

    if new_id not in ids:
        ids.append(new_id)

    ref_value = ["L"] + ids
    logger.info("add_to_reflist: writing %s = %s", field, ref_value)
    result = await update_record(table_key, record_id, {field: ref_value})
    logger.info("add_to_reflist: result = %s", result)
    return result


def get_choices(key: str) -> list[str]:
    """Retourne les choix mis en cache pour une clé donnée."""
    return CHOICES_CACHE.get(key, [])


def get_cas_usage_by_theme() -> dict[str, list[dict]]:
    """Retourne les cas d'usage groupés par thème."""
    return CAS_USAGE_BY_THEME


def get_ref_records(table_key: str) -> list[dict]:
    """Retourne les records de référence mis en cache."""
    return REF_CACHE.get(table_key, [])


def get_record_name(table_key: str, record_id: int) -> str:
    """Retourne le nom d'un record de référence par son ID."""
    for rec in REF_CACHE.get(table_key, []):
        if rec["id"] == record_id:
            return rec["fields"].get("nom", f"#{record_id}")
    return f"#{record_id}"


# ============================================================
# Utilisateurs
# ============================================================

async def get_user_by_email(email: str) -> dict | None:
    """Recherche un utilisateur par email (insensible à la casse)."""
    records = await get_all_records("utilisateurs")
    email_lower = email.strip().lower()
    for rec in records:
        if rec["fields"].get("Email", "").strip().lower() == email_lower:
            return rec
    return None


async def create_user(fields: dict) -> dict:
    """Crée un nouvel utilisateur avec le statut En attente."""
    fields.setdefault("Droits", "En attente")
    return await create_record("utilisateurs", fields)


# ============================================================
# Géocodage via api-adresse.data.gouv.fr
# ============================================================

GEOCODE_CACHE: dict[str, tuple[float, float] | None] = {}


def _feature_dep(props: dict) -> str:
    """Code département d'un résultat api-adresse (via context ou citycode)."""
    ctx = props.get("context") or ""
    if ctx:
        first = ctx.split(",")[0].strip()
        if first:
            return first
    citycode = props.get("citycode") or ""
    if citycode[:2] in ("2A", "2B"):
        return citycode[:2]
    return citycode[:3] if citycode[:2] == "97" else citycode[:2]


async def geocode_address(
    query: str,
    expected_dep: str | None = None,
    municipality: bool = False,
) -> tuple[float, float] | None:
    """
    Géocode une requête via l'API adresse du gouvernement. Retourne (lat, lng).

    - `municipality=True` restreint aux communes (type=municipality).
    - `expected_dep` : si fourni, on ne retient qu'un résultat situé dans ce
      département. Sinon, aucun résultat n'est renvoyé (le repli centroïde est
      géré par l'appelant) — cela évite de placer un point dans la mauvaise région.
    """
    if not query or not query.strip():
        return None
    query = query.strip()
    cache_key = f"{query}|{expected_dep or ''}|{int(municipality)}"
    if cache_key in GEOCODE_CACHE:
        return GEOCODE_CACHE[cache_key]
    result = None
    try:
        params = {"q": query, "limit": 8}
        if municipality:
            params["type"] = "municipality"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api-adresse.data.gouv.fr/search/", params=params
            )
            resp.raise_for_status()
            features = resp.json().get("features", [])
        if features:
            if expected_dep:
                for feat in features:
                    if _feature_dep(feat.get("properties", {})) == expected_dep:
                        coords = feat["geometry"]["coordinates"]
                        result = (coords[1], coords[0])
                        break
            else:
                coords = features[0]["geometry"]["coordinates"]
                result = (coords[1], coords[0])
    except Exception as e:
        logger.warning("Géocodage échoué pour '%s': %s", query, e)
        return None  # ne pas mettre en cache un échec transitoire (rate-limit…)
    GEOCODE_CACHE[cache_key] = result
    return result


async def _resolve_coords_batch(
    collectivites: list[dict],
) -> dict[int, tuple[float, float] | None]:
    """Résout les coordonnées de toutes les collectivités en parallèle (max 5)."""
    import geo_resolver

    sem = asyncio.Semaphore(5)
    results: dict[int, tuple[float, float] | None] = {}

    async def _geo(rec: dict):
        async with sem:
            results[rec["id"]] = await geo_resolver.resolve(
                rec["fields"], geocode_address
            )

    await asyncio.gather(*[_geo(rec) for rec in collectivites])
    return results


# ============================================================
# Données de restitution
# ============================================================

_RESTITUTION_CACHE: dict | None = None
_RESTITUTION_CACHE_TIME: float = 0


async def get_restitution_data(force_refresh: bool = False) -> dict:
    """Retourne toutes les données structurées pour la page de restitution."""
    global _RESTITUTION_CACHE, _RESTITUTION_CACHE_TIME
    now = time.time()
    if _RESTITUTION_CACHE and not force_refresh and (now - _RESTITUTION_CACHE_TIME) < 300:
        return _RESTITUTION_CACHE

    # Récupérer toutes les tables
    collectivites = await get_all_records("collectivites")
    projets = await get_all_records("projets")
    cas_usages = await get_all_records("cas_d_usage")
    partenaires = await get_all_records("partenaires")
    programmes = await get_all_records("programmes")
    documents = await get_all_records("documents")

    projets_by_id = {p["id"]: p for p in projets}

    # Index cas d'usage par projet (un cas d'usage peut être lié à PLUSIEURS projets)
    cas_by_projet: dict[int, list] = {}
    for cu in cas_usages:
        cas_item = {
            "nom": cu["fields"].get("nom", ""),
            "theme": _extract_values(cu["fields"].get("theme"))[0]
            if _extract_values(cu["fields"].get("theme")) else "",
        }
        for pid in ref_ids(cu["fields"].get("projets")):
            cas_by_projet.setdefault(pid, []).append(cas_item)

    # Index partenaires par projet
    part_by_projet: dict[int, list] = {}
    for pa in partenaires:
        projets_ref = pa["fields"].get("Projets")
        if projets_ref and isinstance(projets_ref, list) and len(projets_ref) > 1:
            for pid in projets_ref[1:]:
                part_by_projet.setdefault(pid, []).append({
                    "nom": pa["fields"].get("nom", ""),
                    "role": pa["fields"].get("role_s_", ""),
                })

    # Index programmes par projet
    prog_by_projet: dict[int, list] = {}
    for pr in programmes:
        projets_ref = pr["fields"].get("projet_s_")
        if projets_ref and isinstance(projets_ref, list) and len(projets_ref) > 1:
            for pid in projets_ref[1:]:
                prog_by_projet.setdefault(pid, []).append({
                    "nom": pr["fields"].get("nom", ""),
                })

    # Index documents par projet
    doc_by_projet: dict[int, list] = {}
    for d in documents:
        pid = d["fields"].get("projet")
        if pid and isinstance(pid, int):
            doc_by_projet.setdefault(pid, []).append({
                "titre": d["fields"].get("titre", ""),
                "type": d["fields"].get("type", ""),
            })

    # Mapping collectivité → IDs projets
    coll_projet_ids: dict[int, set] = {}
    for c in collectivites:
        cid = c["id"]
        coll_projet_ids[cid] = set()
        for ref_field in ["projet_s_", "Projets_Liste_des_projets_3_"]:
            ref_val = c["fields"].get(ref_field)
            if ref_val and isinstance(ref_val, list) and len(ref_val) > 1:
                coll_projet_ids[cid].update(ref_val[1:])
    for p in projets:
        coll_ref = p["fields"].get("collectivite_s_porteuse_s_")
        if coll_ref and isinstance(coll_ref, list) and len(coll_ref) > 1:
            for cid in coll_ref[1:]:
                coll_projet_ids.setdefault(cid, set()).add(p["id"])

    # Résolution géographique parallèle (nettoyage du nom + validation départementale)
    geo_results = await _resolve_coords_batch(collectivites)

    # Construire le résultat
    result_collectivites = []
    for c in collectivites:
        f = c["fields"]
        pid_set = coll_projet_ids.get(c["id"], set())
        c_projets = []
        for pid in pid_set:
            if pid in projets_by_id:
                pf = projets_by_id[pid]["fields"]
                c_projets.append({
                    "id": pid,
                    "nom": pf.get("nom", ""),
                    "domaine": _extract_values(pf.get("domaine_s_")),
                    "avancement": pf.get("avancement", ""),
                    "connectivite": _extract_values(pf.get("connectivite_s_")),
                    "echelle": pf.get("echelle", ""),
                    "description": pf.get("description", ""),
                    "cas_usages": cas_by_projet.get(pid, []),
                    "partenaires": part_by_projet.get(pid, []),
                    "programmes": prog_by_projet.get(pid, []),
                    "documents": doc_by_projet.get(pid, []),
                })

        coords = geo_results.get(c["id"])
        result_collectivites.append({
            "id": c["id"],
            "nom": f.get("nom", ""),
            "siren": f.get("siren", ""),
            "statut": get_field_value(c, "statut"),
            "couverture": get_field_value(c, "couverture"),
            "dep": f.get("dep", ""),
            "num_dep": f.get("num_dep", ""),
            "reg": f.get("reg", ""),
            "site_web": f.get("site_web", ""),
            "adresse": f.get("adresse", ""),
            "url_logo": f.get("url_logo", ""),
            "lat": coords[0] if coords else None,
            "lng": coords[1] if coords else None,
            "nb_projets": len(c_projets),
            "projets": c_projets,
        })

    # Stats globales (dédupliquées)
    seen_ids: set[int] = set()
    unique_projets = []
    for c in result_collectivites:
        for p in c["projets"]:
            if p["id"] not in seen_ids:
                seen_ids.add(p["id"])
                unique_projets.append(p)

    par_connectivite: dict[str, int] = {}
    par_avancement: dict[str, int] = {}
    par_domaine: dict[str, int] = {}
    all_cas_usages: set[str] = set()

    for p in unique_projets:
        for conn in p["connectivite"]:
            par_connectivite[conn] = par_connectivite.get(conn, 0) + 1
        av = p["avancement"]
        if av:
            par_avancement[av] = par_avancement.get(av, 0) + 1
        for dom in p["domaine"]:
            par_domaine[dom] = par_domaine.get(dom, 0) + 1
        for cu in p["cas_usages"]:
            nom = cu.get("nom", "") if isinstance(cu, dict) else str(cu)
            if nom:
                all_cas_usages.add(nom)

    filtres = {
        "couvertures": sorted(set(c["couverture"] for c in result_collectivites if c["couverture"])),
        "statuts": sorted(set(c["statut"] for c in result_collectivites if c["statut"])),
        "domaines": sorted(par_domaine.keys()),
        "connectivites": sorted(par_connectivite.keys()),
        "avancements": sorted(par_avancement.keys()),
        "cas_usages": sorted(all_cas_usages),
    }

    result = {
        "collectivites": result_collectivites,
        "stats": {
            "nb_collectivites": len(result_collectivites),
            "nb_projets": len(unique_projets),
            "par_connectivite": par_connectivite,
            "par_avancement": par_avancement,
            "par_domaine": par_domaine,
            "nb_cas_usages": len(all_cas_usages),
        },
        "filtres": filtres,
    }

    _RESTITUTION_CACHE = result
    _RESTITUTION_CACHE_TIME = now
    return result
