"""Vérification (lecture seule) du schéma Grist réel contre le schéma attendu.

Voir la documentation interne du schéma Grist (état au 2026-06-11). On vérifie la
présence des tables et des colonnes dont l'application dépend — pas l'absence
de colonnes supplémentaires (ajouts inoffensifs).

Usage :
- CLI : ``uv run python -m scripts.check_grist_schema`` (exit 1 si divergence) ;
- au démarrage de l'app (lifespan) : log CRITICAL si divergence, sans bloquer.
"""

import logging
import sys

from pygrister.api import GristApi

logger = logging.getLogger(__name__)

# Colonnes minimales requises par l'application, par table.
SCHEMA_ATTENDU: dict[str, set[str]] = {
    "BDD_CasUsages": {"nom", "theme", "projets", "domaine", "connectivites"},
    "BDD_Collectivites": {
        "nom", "siren", "logo", "url_logo", "statut", "couverture", "num_dep",
        "departement", "region", "site_web", "adresse", "latitude", "longitude", "projets",
        "fnccr", "num", "eau", "aode", "tre", "ep", "dec",
    },
    "BDD_Connectivites": {"nom", "projets"},
    "BDD_Contacts": {
        "prenom", "nom", "nom_complet", "elu", "collectivite", "fonction",
        "email", "telephone", "mobile", "projets",
    },
    "BDD_Contrats": {"nom"},
    "BDD_Departements": {"nom", "num_dep", "region", "projets"},
    "BDD_Documents": {"titre", "lien", "projet", "type", "annee"},
    "BDD_Partenaires": {"nom", "roles", "url", "projets"},
    "BDD_Programmes": {"nom", "info_web", "echelle", "projets"},
    "BDD_Projets": {
        "nom", "collectivites_porteuses", "contacts", "description",
        "connectivites", "themes", "avancement", "partenaires", "dev_interne",
        "solutions", "cas_d_usage", "echelle", "mutualisation", "soutien", "programmes",
        "contrats", "departements", "region", "documents",
    },
    "BDD_Solutions": {"nom", "type", "partenaire", "projets"},
    "BDD_Utilisateurs": {
        "nom", "prenom", "email", "organisation", "droits", "collectivite",
        "date_inscription",
    },
}


def verifier_schema(grist: GristApi) -> list[str]:
    """Retourne la liste des divergences (vide = schéma conforme)."""
    divergences: list[str] = []

    status, tables = grist.list_tables()
    if status >= 300:
        return [f"Impossible de lister les tables (HTTP {status})"]
    tables_reelles = {t["id"] for t in tables}

    for table_id, colonnes_attendues in SCHEMA_ATTENDU.items():
        if table_id not in tables_reelles:
            divergences.append(f"Table absente : {table_id}")
            continue
        status, colonnes = grist.list_cols(table_id, hidden=True)
        if status >= 300:
            divergences.append(f"Colonnes illisibles : {table_id} (HTTP {status})")
            continue
        reelles = {c["id"] for c in colonnes}
        for manquante in sorted(colonnes_attendues - reelles):
            divergences.append(f"Colonne absente : {table_id}.{manquante}")

    return divergences


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from app.dependencies import get_grist_api

    divergences = verifier_schema(get_grist_api())
    if divergences:
        for d in divergences:
            logger.error(d)
        logger.error("Schéma Grist DIVERGENT (%d écarts)", len(divergences))
        return 1
    logger.info("Schéma Grist conforme à SCHEMA_GRIST.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
