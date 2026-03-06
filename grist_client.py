"""
Client API Grist — encapsule tous les appels à l'API REST de Grist.
Gère la connexion, le cache des tables/colonnes, et les opérations CRUD.
"""

import os
import logging
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("grist_client")

# --- Configuration ---
GRIST_API_KEY = os.getenv("GRIST_API_KEY", "")
GRIST_BASE_URL = "https://grist.francedatareseau.fr"
GRIST_DOC_ID = "4usnoxBdw9ggHsxmhBtThG"
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
    data = await _get("/tables")
    tables = data.get("tables", [])

    mapping = {
        "collectivites": None,
        "projets": None,
        "contacts": None,
        "cas_d_usage": None,
        "partenaires": None,
        "programmes": None,
        "documents": None,
    }

    for t in tables:
        tid = t["id"].lower()
        if tid.startswith("collectivites"):
            mapping["collectivites"] = t["id"]
        elif tid.startswith("projets"):
            mapping["projets"] = t["id"]
        elif tid.startswith("contacts"):
            mapping["contacts"] = t["id"]
        elif tid.startswith("cas_d_usage"):
            mapping["cas_d_usage"] = t["id"]
        elif tid.startswith("partenaires"):
            mapping["partenaires"] = t["id"]
        elif tid.startswith("programmes"):
            mapping["programmes"] = t["id"]
        elif tid.startswith("documents"):
            mapping["documents"] = t["id"]

    TABLE_IDS.update(mapping)
    logger.info("Tables découvertes : %s", TABLE_IDS)


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
            v = rec["fields"].get(field, "")
            if v and isinstance(v, str) and v.strip():
                values.add(v.strip())
        CHOICES_CACHE[f"collectivites.{field}"] = sorted(values)

    # --- Projets ---
    proj_records = await get_all_records("projets")
    for field in ["avancement", "echelle", "region"]:
        values = set()
        for rec in proj_records:
            v = rec["fields"].get(field, "")
            if v and isinstance(v, str) and v.strip():
                values.add(v.strip())
        CHOICES_CACHE[f"projets.{field}"] = sorted(values)

    for field in ["mutualisation", "soutien", "contrat"]:
        values = set()
        for rec in proj_records:
            v = rec["fields"].get(field, "")
            if v and isinstance(v, str) and v.strip():
                for part in v.split(","):
                    part = part.strip().strip('"')
                    if part:
                        values.add(part)
        CHOICES_CACHE[f"projets.{field}"] = sorted(values)

    # --- Cas d'usage : thèmes et mapping thème → cas d'usage ---
    cas_records = await get_all_records("cas_d_usage")
    themes = set()
    CAS_USAGE_BY_THEME.clear()
    for rec in cas_records:
        theme = rec["fields"].get("theme", "")
        nom = rec["fields"].get("nom", "")
        if theme and isinstance(theme, str) and theme.strip():
            theme = theme.strip()
            themes.add(theme)
            if nom:
                CAS_USAGE_BY_THEME.setdefault(theme, []).append({
                    "id": rec["id"],
                    "nom": nom.strip(),
                })
    CHOICES_CACHE["cas_d_usage.theme"] = sorted(themes)

    # Extraire les domaines depuis les thèmes des cas d'usage
    CHOICES_CACHE["projets.domaine_s_"] = sorted(themes)

    # --- Partenaires : rôles ---
    part_records = await get_all_records("partenaires")
    roles = set()
    for rec in part_records:
        v = rec["fields"].get("role_s_", "")
        if v and isinstance(v, str) and v.strip():
            for part_val in v.split(","):
                part_val = part_val.strip().strip('"')
                if part_val:
                    roles.add(part_val)
    CHOICES_CACHE["partenaires.role_s_"] = sorted(roles)

    # --- Programmes : échelle ---
    prog_records = await get_all_records("programmes")
    echelles = set()
    for rec in prog_records:
        v = rec["fields"].get("echelle", "")
        if v and isinstance(v, str) and v.strip():
            echelles.add(v.strip())
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
